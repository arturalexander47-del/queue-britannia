"""Survive to the Election: a 12-quarter game on top of the real MoJ data.

Everything is vectorised over a leading "scenario" axis S so the same code runs one
real game (S=1) or thousands of simulated futures for the Autopilot and the benchmark.

Quarterly dynamics, per region r:
  receipts_r   = recent receipts x event shocks x noise
  capacity_r   = recent disposals x (1 + fixes + overbooking) + extra courtrooms
  disposals_r  = min(backlog_r + receipts_r, capacity_r)
  backlog_r   += receipts_r - disposals_r
Nationally:
  remand       = remand_0 x backlog / backlog_0                (Little's law, arrivals ~flat)
  sentenced   += inflow_per_disposal x disposals - sentenced / time_served
  occupancy    = (sentenced + remand) / places                  > 100% = game over
"""
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

import config as C
import crack_model as cm

QUARTERS = 12

# ---- ILLUSTRATIVE costs and effects (replace with sourced figures; shown in the app) ----
BUDGET_PER_QUARTER_M = 60.0          # £m a quarter for the minister's discretionary fixes
COURTROOM_COST_M = 0.6               # £m to run one extra courtroom for a quarter
DISPOSALS_PER_ROOM_Q = C.NIGHTINGALE_DISPOSALS_PER_ROOM / 4
PLACE_BUILD_COST_M = 0.05            # £m per emergency prison place (modular units)
PLACE_DELAY_Q = 2                    # quarters before new places open
FUND_SCALE_M = 10.0                  # £m a quarter for a fund to reach ~63% of its max effect
OVERBOOK_LEVELS = [0.0, 0.25, 0.50, 0.75]   # extra trials listed per trial courtroom
OVERBOOK_SLOTS = 4                   # trial courtrooms in a typical court centre on one day
EARLY_RELEASE_STAY_FACTOR = 0.4 / 0.5
PRISON_DRIFT_Q = 300                 # ASSUMPTION: underlying sentenced growth per quarter (recent trend is mixed)
OVERBOOK_REALISM = 0.5               # ASSUMPTION: courts already "float" trials, so only half the theoretical gain is new
DAY_STRENGTH = 20                    # day-to-day variability of trial collapse rates (beta prior strength)
EARLY_RELEASE_POPULARITY = 9         # popularity lost per quarter of early release

EVENTS = [
    # name, probability per quarter, effect dict, Sir Humphrey's take
    ("Barrister strike", 0.08, dict(capacity=-0.10), "The Bar has downed wigs, Minister. Most regrettable."),
    ("Police charging surge", 0.10, dict(receipts=0.10), "The police have been terribly efficient. Most inconvenient."),
    ("Tough new sentencing law", 0.06, dict(stay=0.08), "Parliament has been tough on crime. And on your prisons."),
    ("Crumbling prison wing closed", 0.08, dict(places=-800), "A wing has, ah, fallen down. Concrete, apparently."),
    ("Treasury windfall", 0.06, dict(budget=40.0), "The Treasury has found some money. Nobody knows where."),
    ("Juror shortage", 0.06, dict(capacity=-0.05), "Nobody wants to be a juror, Minister. One can't imagine why."),
]


@dataclass
class Action:
    rooms: int = 0                    # extra courtrooms this quarter
    room_region: str = "Worst wait"   # region name, "Spread evenly" or "Worst wait"
    funds: dict = field(default_factory=dict)  # {fix name: £m this quarter}
    overbook: int = 0                 # index into OVERBOOK_LEVELS
    places: int = 0                   # new emergency prison places to order
    early_release: bool = False

    def cost(self):
        return self.rooms * COURTROOM_COST_M + sum(self.funds.values()) + self.places * PLACE_BUILD_COST_M


class World:
    """Fixed facts derived from the data (regions, rates, reason shares)."""

    def __init__(self, court_q, prison_w, reasons, post):
        last4 = court_q[court_q["qp"] > court_q["qp"].max() - 4]
        latest = court_q[court_q["qp"] == court_q["qp"].max()]
        g = last4.groupby("region")
        self.regions = sorted(g.groups)
        self.receipts = g["receipts"].sum().reindex(self.regions).values / 4
        self.disposals = g["disposals"].sum().reindex(self.regions).values / 4
        self.listed = g["trials_listed"].sum().reindex(self.regions).values / 4
        self.not_eff = g["not_effective"].sum().reindex(self.regions).values / 4
        self.backlog0 = latest.groupby("region")["outstanding"].sum().reindex(self.regions).values
        pw = prison_w.iloc[-1]
        self.remand0 = float(pw["remand"])
        self.sentenced0 = float(pw["population"] - pw["remand"])
        self.places0 = float(pw["operational_capacity"])
        self.stay_q = C.AVG_CUSTODY_WEEKS / 13
        self.inflow_per_disposal = (PRISON_DRIFT_Q + self.sentenced0 / self.stay_q) / self.disposals.sum()
        # fixes: share of not-effective trials each fix targets (national reason shares)
        self.fix_share = {}
        for name, f in C.FIXES.items():
            hit = reasons[(reasons["outcome"] == "ineffective")
                          & reasons["reason"].str.lower().apply(lambda r: any(p in r for p in f["patterns"]))]
            self.fix_share[name] = float(hit["share"].sum())
        # overbooking: extra trials heard and bumped per listed trial, by region and level
        post = post.set_index("court")
        reg_ab = post.groupby("region")[["alpha", "beta"]].mean().reindex(self.regions)
        self.ob_gain = np.zeros((len(OVERBOOK_LEVELS), len(self.regions)))
        self.ob_bumped = np.zeros_like(self.ob_gain)
        slots = OVERBOOK_SLOTS
        for j, (a, b) in enumerate(reg_ab.values):
            mu = a / (a + b)   # same mean rate, but realistic day-to-day spread
            a, b = mu * DAY_STRENGTH, (1 - mu) * DAY_STRENGTH
            curve, _ = cm.overbooking_curve(a, b, slots=slots, max_extra=slots, n_sims=20000)
            base = curve.iloc[0]
            for i, lvl in enumerate(OVERBOOK_LEVELS):
                row = curve.iloc[int(round(lvl * slots))]
                self.ob_gain[i, j] = OVERBOOK_REALISM * (row["utilisation"] - base["utilisation"])
                self.ob_bumped[i, j] = row["exp_bumped"] / slots                # bumped per slot

    def initial(self, S=1):
        R = len(self.regions)
        return dict(
            q=0, backlog=np.tile(self.backlog0, (S, 1)).astype(float),
            sentenced=np.full(S, self.sentenced0), remand=np.full(S, self.remand0),
            places=np.full(S, self.places0), pipeline=np.zeros((S, PLACE_DELAY_Q)),
            stay=np.full(S, self.stay_q), popularity=np.full(S, 50.0),
            budget=np.full(S, BUDGET_PER_QUARTER_M), alive=np.ones(S, bool),
            lost_reason=np.array([""] * S, dtype=object), events=[[] for _ in range(S)],
            bumped_total=np.zeros(S), R=R)


def _copy(st):
    out = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in st.items()}
    out["events"] = [list(e) for e in st["events"]]
    return out


def step(world, st, action: Action, rng, noise=True):
    """Advance one quarter. Returns new state and the list of events drawn (per scenario)."""
    st = _copy(st)
    S, R = st["backlog"].shape
    alive = st["alive"]
    spend = action.cost()
    affordable = st["budget"] >= spend - 1e-9
    # events
    cap_shock, rec_shock, stay_shock = np.zeros(S), np.zeros(S), np.zeros(S)
    place_shock, budget_shock = np.zeros(S), np.zeros(S)
    drawn = [[] for _ in range(S)]
    for name, p, eff, _ in EVENTS:
        hit = rng.random(S) < p
        cap_shock += hit * eff.get("capacity", 0)
        rec_shock += hit * eff.get("receipts", 0)
        stay_shock += hit * eff.get("stay", 0)
        place_shock += hit * eff.get("places", 0)
        budget_shock += hit * eff.get("budget", 0)
        for s in np.where(hit)[0]:
            drawn[s].append(name)
    # courts
    fix_up = np.zeros(R)
    for name, m in action.funds.items():
        reduction = C.FIXES[name]["reduction"] * (1 - np.exp(-m / FUND_SCALE_M))
        fix_up += self_fix(world, name, reduction)
    ob_up = world.ob_gain[action.overbook] * world.listed / world.disposals
    bumped = world.ob_bumped[action.overbook] * world.listed
    rooms = np.zeros(R)
    if action.rooms:
        if action.room_region == "Spread evenly":
            rooms[:] = action.rooms / R
        elif action.room_region == "Worst wait":
            wait = st["backlog"].mean(axis=0) / world.disposals
            rooms[np.argmax(wait)] = action.rooms
        else:
            rooms[world.regions.index(action.room_region)] = action.rooms
    eps = rng.normal(0, 0.04, (S, R)) if noise else np.zeros((S, R))
    receipts = world.receipts * (1 + rec_shock[:, None]) * np.exp(eps)
    capacity = (world.disposals * (1 + fix_up + ob_up + cap_shock[:, None])
                + rooms * DISPOSALS_PER_ROOM_Q) * np.exp(rng.normal(0, 0.03, (S, R)) if noise else 0)
    capacity = np.where(affordable[:, None], capacity, world.disposals * (1 + cap_shock[:, None]))
    disposals = np.minimum(st["backlog"] + receipts, capacity)
    old_total = st["backlog"].sum(axis=1)
    st["backlog"] = st["backlog"] + receipts - disposals
    # prisons
    st["stay"] = st["stay"] * (1 + stay_shock)
    stay = st["stay"] * (EARLY_RELEASE_STAY_FACTOR if action.early_release else 1.0)
    st["sentenced"] = (st["sentenced"] + world.inflow_per_disposal * disposals.sum(axis=1)
                       - st["sentenced"] / stay)
    st["remand"] = world.remand0 * st["backlog"].sum(axis=1) / world.backlog0.sum()
    arriving = st["pipeline"][:, 0].copy()
    st["pipeline"] = np.roll(st["pipeline"], -1, axis=1)
    st["pipeline"][:, -1] = np.where(affordable, action.places, 0)
    st["places"] = st["places"] + arriving + place_shock
    occupancy = (st["sentenced"] + st["remand"]) / st["places"]
    # popularity (satire, but the drivers are real quantities)
    growth = (st["backlog"].sum(axis=1) - old_total) / old_total * 100
    pop = (st["popularity"] - np.clip(2 * growth, -6, 8) - (EARLY_RELEASE_POPULARITY if action.early_release else 0)
           - bumped.sum() / 150 - 4 * (occupancy > 0.99) + 1.0)
    st["popularity"] = np.clip(pop, 0, 100)
    # budget
    st["budget"] = np.where(affordable, st["budget"] - spend, st["budget"]) + BUDGET_PER_QUARTER_M + budget_shock
    st["bumped_total"] = st["bumped_total"] + bumped.sum()
    # losing
    full = alive & (occupancy >= 1.0)
    sacked = alive & ~full & (st["popularity"] <= 5)
    st["lost_reason"] = np.where(full, "Prisons full", np.where(sacked, "Sacked in the reshuffle", st["lost_reason"]))
    st["alive"] = alive & ~full & ~sacked
    st["q"] += 1
    st["occupancy"] = occupancy
    st["wait_q"] = st["backlog"] / np.maximum(disposals, 1)
    st["last_disposals"] = disposals
    for s in range(S):
        st["events"][s].append(drawn[s])
    return st, drawn


def self_fix(world, name, reduction):
    """Extra disposals (fraction) per region if `reduction` of that fix's failures are prevented."""
    return world.not_eff * world.fix_share[name] * reduction / world.disposals


def score(world, st):
    cleared = world.backlog0.sum() - st["backlog"].sum(axis=1)
    s = cleared / 50 + st["popularity"] * 10 + st["budget"]
    return np.where(st["alive"], s, 0.0)


# ---------------------------------------------------------------- Autopilot
def candidate_actions(world, budget, rng, n=40):
    fixes = list(C.FIXES)
    cands = [Action()] + [f(world, {"budget": np.array([budget])}, 0) for f in STRATEGIES.values()]
    cands = [a for a in cands if a.cost() <= budget]
    for _ in range(n * 3):
        a = Action(rooms=int(rng.choice([0, 10, 20, 40, 60, 80, 100])),
                   room_region=str(rng.choice(["Worst wait", "Spread evenly"])),
                   funds={f: float(rng.choice([0, 0, 5, 10, 20])) for f in fixes},
                   overbook=int(rng.integers(0, len(OVERBOOK_LEVELS))),
                   places=int(rng.choice([0, 0, 250, 500, 1000])),
                   early_release=bool(rng.random() < 0.3))
        a.funds = {k: v for k, v in a.funds.items() if v > 0}
        if a.cost() <= budget:
            cands.append(a)
        if len(cands) >= n:
            break
    return cands


def autopilot(world, st, scenarios=30, horizon=4, seed=0):
    """Pick the action that maximises expected score after `horizon` quarters, holding it fixed
    (prison places ordered once), with a heavy penalty on the chance of losing."""
    rng = np.random.default_rng(seed)
    budget = float(st["budget"][0])
    best, best_val = Action(), -np.inf
    base = {k: (np.repeat(v[:1], scenarios, axis=0) if isinstance(v, np.ndarray) else v) for k, v in st.items()}
    base["events"] = [[] for _ in range(scenarios)]
    left = QUARTERS - st["q"]
    for a in candidate_actions(world, budget, rng):
        sim_rng = np.random.default_rng(seed + 1)   # common random numbers across candidates
        s = base
        for h in range(min(horizon, left)):
            s, _ = step(world, s, a if h == 0 else replace(a, places=0), sim_rng)
        val = score(world, s).mean() - 3000 * (1 - s["alive"].mean())
        if val > best_val:
            best, best_val = a, val
    return best


# ---------------------------------------------------------------- Benchmark
STRATEGIES = {
    "Do nothing": lambda w, s, q: Action(),
    "Courts flat out": lambda w, s, q: Action(rooms=min(100, int(s["budget"][0] // COURTROOM_COST_M))),
    "Build prisons": lambda w, s, q: Action(places=min(3000, int(s["budget"][0] // PLACE_BUILD_COST_M) // 250 * 250)),
    "Early release + courts": lambda w, s, q: Action(rooms=90, early_release=True),
}


def play(world, policy, seed, autopilot_scenarios=20):
    rng = np.random.default_rng(seed)
    st = world.initial(1)
    while st["q"] < QUARTERS and st["alive"][0]:
        a = (autopilot(world, st, scenarios=autopilot_scenarios, seed=seed * 100 + st["q"])
             if policy == "Autopilot" else STRATEGIES[policy](world, st, st["q"]))
        if a.cost() > st["budget"][0]:
            a = Action()
        st, _ = step(world, st, a, rng)
    return dict(policy=policy, seed=seed, survived=bool(st["alive"][0]), score=float(score(world, st)[0]),
                backlog=float(st["backlog"].sum()), quarters=int(st["q"]), lost=str(st["lost_reason"][0]))


def benchmark(world, seeds=range(40), include_autopilot=True):
    rows = []
    for seed in seeds:
        for p in list(STRATEGIES) + (["Autopilot"] if include_autopilot else []):
            rows.append(play(world, p, seed))
    df = pd.DataFrame(rows)
    summary = df.groupby("policy").agg(survival_rate=("survived", "mean"), mean_score=("score", "mean"),
                                       median_backlog=("backlog", "median")).sort_values("mean_score", ascending=False)
    return df, summary


if __name__ == "__main__":
    # Pre-compute the benchmark shown in the app:  python game.py
    import data
    d = data.load()
    world = World(d["court_q"], d["prison_w"], d["reasons"], cm.fit(d["court_q"]))
    df, summary = benchmark(world, seeds=range(50))
    df.to_csv(data.DATA_DIR / "benchmark.csv", index=False)
    print(summary)

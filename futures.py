"""Justice Futures: yes/no questions about real Crown Court history, priced by the model.

Every question is asked "as of" an origin quarter. The model only sees data up to and
including that quarter; the answer comes from what really happened afterwards.

Two kinds of question per court and origin quarter o:
  backlog  Will the court's backlog be higher 4 quarters later than it is now?
           Model: flat 4-quarter forecast (receipts - disposals continue at their recent
           average), plus the spread of that forecast's real errors over the 2 years before o.
  collapse Will more than T% of the court's listed trials crack or fail next quarter?
           T is this quarter's rate rounded to the nearest 5%. Model: beta-binomial,
           court mean shrunk towards its region, spread fitted on past quarters.

Run `python futures.py` to rebuild data/futures_questions.csv and print the scorecard.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HORIZON = 4          # quarters ahead for backlog questions
WINDOW = 8           # quarters of history for a court's collapse rate
FIRST_ORIGIN = pd.Period("2018Q1", "Q")
OUT = Path(__file__).parent / "data" / "futures_questions.csv"

# Real context shown alongside questions from these quarters.
ON_THIS_DATE = {
    "2020Q1": "Covid: jury trials were paused across England and Wales in late March.",
    "2020Q2": "Covid lockdown: most Crown Court trials halted, then restarted slowly with distancing.",
    "2020Q3": "Nightingale courts open in hotels, conference centres and theatres.",
    "2022Q2": "Criminal barristers begin strike action over legal aid fees.",
    "2022Q3": "The barristers' strike escalates to an all-out walkout.",
    "2024Q3": "Prisons near full: the government starts releasing some prisoners at 40% of sentence.",
}


def backlog_questions(court_q):
    rows = []
    quarters = sorted(court_q["qp"].unique())
    by_court = {c: g.set_index("qp").sort_index() for c, g in court_q.groupby("court")}
    resolved = []  # (resolution quarter, relative error) of forecasts made so far
    for o in quarters:
        for court, g in by_court.items():
            hist = g.loc[:o]
            if len(hist) < 4 or o not in g.index:
                continue
            B = hist["outstanding"].iloc[-1]
            pred = HORIZON * (hist["receipts"].tail(4).mean() - hist["disposals"].tail(4).mean())
            target = o + HORIZON
            actual = g["outstanding"].get(target)
            if actual is not None:
                resolved.append((target, (actual - B - pred) / max(B, 1)))
            if o < FIRST_ORIGIN or actual is None:
                continue
            # only errors already visible at time o, from the last 2 years (regimes change)
            known = np.array([e for t, e in resolved if o - 8 < t <= o])
            momentum = B - hist["outstanding"].iloc[-5] if len(hist) >= 5 else 0.0
            rows.append(dict(
                kind="backlog", court=court, region=g["region"].iloc[0], origin=str(o), resolves=str(target),
                question=f"Will {court}'s backlog be higher in a year than today's {B:,.0f} cases?",
                now=B, threshold=B, actual_value=actual, outcome=int(actual > B),
                # empirical: share of recent forecast errors that would have tipped the answer to YES
                p_model=float(np.mean(pred / max(B, 1) + known > 0)) if len(known) >= 50 else 0.5,
                p_momentum=0.65 if momentum > 0 else 0.35))
    return pd.DataFrame(rows)


def _fit_concentration(df):
    """Shared beta concentration for quarter-to-quarter collapse rates (max likelihood on a grid)."""
    grid = np.exp(np.linspace(np.log(5), np.log(2000), 60))
    k, n, m = df["k"].values, df["n"].values, df["m"].clip(0.02, 0.98).values
    ll = [stats.betabinom.logpmf(k, n, m * c, (1 - m) * c).sum() for c in grid]
    return float(grid[int(np.argmax(ll))])


def collapse_questions(court_q):
    cq = court_q.copy()
    cq["k"] = cq["trials_cracked"] + cq["trials_ineffective"]
    cq["n"] = cq["trials_listed"].astype(int)
    cq = cq[cq["n"] >= 10]
    cq["k"] = cq[["k", "n"]].min(axis=1).astype(int)
    rows = []
    quarters = sorted(cq["qp"].unique())
    for o in quarters:
        if o < FIRST_ORIGIN or o + 1 > quarters[-1]:
            continue
        win = cq[(cq["qp"] <= o) & (cq["qp"] > o - WINDOW)]
        g = win.groupby("court").agg(k=("k", "sum"), n=("n", "sum"), region=("region", "first"))
        reg = win.groupby("region")[["k", "n"]].sum()
        prior_w = 200  # trials' worth of pull towards the region's rate
        g["m"] = (g["k"] + prior_w * (reg.loc[g["region"], "k"].values / reg.loc[g["region"], "n"].values)) / (g["n"] + prior_w)
        # spread of single quarters around those means, fitted on the same past window
        past = win.merge(g[["m"]], left_on="court", right_index=True)
        conc = _fit_concentration(past)
        now = cq[cq["qp"] == o].set_index("court")
        nxt = cq[cq["qp"] == o + 1].set_index("court")
        for court in now.index.intersection(nxt.index).intersection(g.index):
            rate = now.loc[court, "k"] / now.loc[court, "n"]
            T = round(rate * 20) / 20
            if not 0.05 <= T <= 0.95:
                continue
            n = int(round(win[win["court"] == court]["n"].tail(4).mean()))
            m = g.loc[court, "m"]
            p = float(stats.betabinom.sf(np.floor(T * n), n, m * conc, (1 - m) * conc))
            actual = nxt.loc[court, "k"] / nxt.loc[court, "n"]
            rows.append(dict(
                kind="collapse", court=court, region=g.loc[court, "region"], origin=str(o), resolves=str(o + 1),
                question=f"Will more than {T:.0%} of {court}'s listed trials crack or collapse next quarter?",
                now=rate, threshold=T, actual_value=actual, outcome=int(actual > T), p_model=p,
                p_momentum=0.6 if rate > T else 0.4))
    return pd.DataFrame(rows)


def build(court_q):
    q = pd.concat([backlog_questions(court_q), collapse_questions(court_q)], ignore_index=True)
    q["p_model"] = q["p_model"].clip(0.03, 0.97)
    # base rate: share of the same kind of question answered YES before this origin
    q = q.sort_values(["kind", "resolves"]).reset_index(drop=True)
    for kind, g in q.groupby("kind"):
        base = []
        for o in g["origin"]:
            done = g[g["resolves"] <= o]["outcome"]
            base.append(done.mean() if len(done) >= 30 else 0.5)
        q.loc[g.index, "p_base"] = base
    return q


def scorecard(q):
    """Brier score (lower is better) and simulated betting P&L for each forecaster."""
    out = []
    for kind, g in list(q.groupby("kind")) + [("all", q)]:
        row = dict(kind=kind, questions=len(g), yes_rate=g["outcome"].mean())
        for f in ("model", "base", "momentum"):
            row[f"brier_{f}"] = float(((g[f"p_{f}"] - g["outcome"]) ** 2).mean())
        row["brier_coin"] = 0.25
        out.append(row)
    return pd.DataFrame(out)


def calibration(q, bins=10):
    b = pd.cut(q["p_model"], np.linspace(0, 1, bins + 1), include_lowest=True)
    return (q.groupby(b, observed=True).agg(predicted=("p_model", "mean"), happened=("outcome", "mean"),
                                            questions=("outcome", "size")).reset_index(drop=True))


def bet_pnl(p_you, p_odds, outcome, stake=100.0):
    """Bet `stake` on whichever side you think is underpriced, at fair odds from p_odds."""
    yes = p_you > p_odds
    win = np.where(yes, outcome == 1, outcome == 0)
    price = np.where(yes, p_odds, 1 - p_odds)
    return np.where(win, stake * (1 - price) / price, -stake)


if __name__ == "__main__":
    import data
    q = build(data.load()["court_q"])
    q.to_csv(OUT, index=False)
    print(scorecard(q).round(4).to_string(index=False))
    print(calibration(q).round(3).to_string(index=False))
    for f in ("base", "momentum"):
        print(f"{f} bettor vs model odds, mean P&L per £100 bet:", bet_pnl(q[f"p_{f}"], q["p_model"], q["outcome"]).mean().round(2))

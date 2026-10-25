"""Predict each court's share of listed trials that don't go ahead (cracked + ineffective).

Empirical-Bayes beta-binomial: a court's recent quarters (exponentially weighted)
are shrunk towards its region's average, so small courts don't swing wildly.
"""
import numpy as np
import pandas as pd
from scipy import stats

WINDOW = 8      # quarters of history per court
DECAY = 0.8     # weight per quarter back


def _court_counts(hist):
    """Decay-weighted (not_effective, listed) for one court's history, newest last."""
    h = hist.tail(WINDOW)
    w = DECAY ** np.arange(len(h))[::-1]
    return float((w * h["not_effective"]).sum()), float((w * h["trials_listed"]).sum())


def _prior(rates):
    """Method-of-moments beta prior from a set of court rates."""
    mu = float(np.clip(np.mean(rates), 0.01, 0.99))
    var = float(np.var(rates)) if len(rates) > 1 else mu * (1 - mu) / 50
    strength = np.clip(mu * (1 - mu) / max(var, 1e-6) - 1, 10, 500)
    return mu, strength


def fit(court_q, before=None):
    """Posterior per court using quarters strictly before `before` (a Period), or all data."""
    df = court_q if before is None else court_q[court_q["qp"] < before]
    rows = []
    for court, g in df.groupby("court"):
        s, n = _court_counts(g)
        rows.append(dict(court=court, region=g["region"].iloc[0], s=s, n=n, raw=s / max(n, 1)))
    post = pd.DataFrame(rows)
    _, nat_strength = _prior(post["raw"])
    out = []
    for region, g in post.groupby("region"):
        mu = g["raw"].mean() if len(g) >= 2 else post["raw"].mean()
        a0, b0 = mu * nat_strength, (1 - mu) * nat_strength
        for r in g.itertuples():
            out.append(dict(court=r.court, region=region, alpha=a0 + r.s, beta=b0 + r.n - r.s,
                            raw_rate=r.raw))
    post = pd.DataFrame(out)
    post["p_not_effective"] = post["alpha"] / (post["alpha"] + post["beta"])
    return post


def predictive_interval(alpha, beta, n, level=0.8):
    lo, hi = stats.betabinom.ppf([(1 - level) / 2, (1 + level) / 2], n, alpha, beta)
    return lo / n, hi / n


def backtest(court_q, n_test_quarters=8):
    """Walk-forward: for each test quarter, fit on earlier data only, then score."""
    quarters = sorted(court_q["qp"].unique())[-n_test_quarters:]
    rows = []
    for q in quarters:
        post = fit(court_q, before=q).set_index("court")
        prev = court_q[court_q["qp"] < q]
        last = prev.groupby("court").tail(1).set_index("court")
        nat = last["not_effective"].sum() / last["trials_listed"].sum()
        actual = court_q[court_q["qp"] == q].set_index("court")
        for court, a in actual.iterrows():
            if court not in post.index or a["trials_listed"] == 0:
                continue
            n, k = int(a["trials_listed"]), int(a["not_effective"])
            al, be = post.loc[court, ["alpha", "beta"]]
            p_last = np.clip(last.loc[court, "not_effective"] / max(last.loc[court, "trials_listed"], 1), 0.01, 0.99)
            lo, hi = predictive_interval(al, be, n)
            rows.append(dict(
                quarter=str(q), court=court, actual=k / n,
                model=al / (al + be), last_quarter=p_last, national=nat,
                ll_model=stats.betabinom.logpmf(k, n, al, be) / n,
                ll_last=stats.binom.logpmf(k, n, p_last) / n,
                ll_national=stats.binom.logpmf(k, n, nat) / n,
                covered=lo <= k / n <= hi,
            ))
    res = pd.DataFrame(rows)
    summary = pd.DataFrame({
        "MAE (rate)": [(res[c] - res["actual"]).abs().mean() for c in ("model", "last_quarter", "national")],
        "log-lik per trial": [res["ll_model"].mean(), res["ll_last"].mean(), res["ll_national"].mean()],
    }, index=["Our model", "Last quarter", "National average"])
    return res, summary, float(res["covered"].mean())


def overbooking_curve(alpha, beta, slots=10, max_extra=None, bump_penalty=1.5, n_sims=20000, seed=0):
    """For each list size N >= slots, simulate a court day.

    Each listed trial goes ahead with prob 1 - p, where p ~ Beta(alpha, beta).
    Heard = min(go-ahead, slots); bumped = trials ready to go but no room.
    """
    max_extra = slots * 2 if max_extra is None else max_extra
    rng = np.random.default_rng(seed)
    p = rng.beta(alpha, beta, n_sims)
    rows = []
    for N in range(slots, slots + max_extra + 1):
        go = rng.binomial(N, 1 - p)
        heard = np.minimum(go, slots)
        bumped = np.maximum(go - slots, 0)
        rows.append(dict(listed=N, utilisation=heard.mean() / slots, exp_bumped=bumped.mean(),
                         p_any_bump=(bumped > 0).mean(),
                         objective=heard.mean() - bump_penalty * bumped.mean()))
    df = pd.DataFrame(rows)
    best = int(df.loc[df["objective"].idxmax(), "listed"])
    return df, best


def synthetic_cases(p_court, reasons, mix, n=12, mean_wait_weeks=40, remand_share=0.25, seed=0):
    """Synthetic trial cards sampled from published breakdowns (NOT real cases)."""
    rng = np.random.default_rng(seed)
    risk = np.clip(rng.beta(p_court * 30, (1 - p_court) * 30, n), 0.02, 0.98)
    fail_reasons = reasons.sample(n, replace=True, weights="share", random_state=seed)["reason"].values
    offences = mix.sample(n, replace=True, weights="share", random_state=seed + 1)["offence_group"].values
    return pd.DataFrame(dict(
        case=[f"SYN-{1000 + i}" for i in range(n)],
        offence=offences,
        weeks_waiting=rng.exponential(mean_wait_weeks, n).round().astype(int),
        on_remand=rng.random(n) < remand_share,
        risk_not_going_ahead=risk.round(2),
        likely_reason=fail_reasons,
    )).sort_values("risk_not_going_ahead", ascending=False)

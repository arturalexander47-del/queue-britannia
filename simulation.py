"""Weekly Monte Carlo of Crown Court backlog -> remand -> prison occupancy.

Backlog:   B[t+1] = B[t] + receipts[t] - disposals[t]
Capacity:  disposals <= disposals_per_sitting_day * sitting_days * (1 + trial_share * overbooking_uplift)
Wait:      Little's law, W = backlog / throughput
Remand:    Little's law again, remand = remand arrivals (proportional to receipts) * wait
Sentenced: inflow proportional to disposals, outflow = stock / average time served
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

import config as C


@dataclass
class Levers:
    sitting_days_pct: float = 0.0      # +% sitting days
    nightingale_rooms: int = 0
    overbooking_uplift: float = 0.0    # extra disposals from overbooking, as a fraction of current disposals
    release_point: float = C.BASE_RELEASE_POINT
    extra_prison_places: int = 0
    fix_uplift: float = 0.0            # extra disposals from fixes (barristers, video links...), as a fraction


def baseline_state(court_q, prison_w, region=None):
    """Starting point for the simulation. With `region`, the courts are that region's only;
    prison figures stay national and remand is scaled by the region's share of the backlog."""
    share = 1.0
    if region:
        share = (court_q[(court_q["region"] == region) & (court_q["qp"] == court_q["qp"].max())]["outstanding"].sum()
                 / court_q[court_q["qp"] == court_q["qp"].max()]["outstanding"].sum())
        court_q = court_q[court_q["region"] == region]
    nat = court_q.groupby("qp")[["receipts", "disposals", "outstanding", "sitting_days"]].sum().sort_index()
    recent = nat.tail(4)
    weekly_receipts = recent["receipts"].mean() / 13
    pw = prison_w.tail(52)
    sent = (pw["population"] - pw["remand"]).values
    return dict(
        backlog=float(nat["outstanding"].iloc[-1]),
        receipts_w=float(weekly_receipts),
        # Receipts held at their recent level: trend extrapolation backtested worse than flat.
        receipts_growth_w=0.0,
        disp_per_day=float(recent["disposals"].sum() / recent["sitting_days"].sum()),
        sitting_days_w=float(recent["sitting_days"].mean() / 13),
        remand=float(pw["remand"].iloc[-1]) * share,
        sentenced=float(sent[-1]) * share,
        sentenced_growth_w=float(np.polyfit(np.arange(len(sent)), sent, 1)[0]) * share,
        capacity=float(pw["operational_capacity"].iloc[-1]) * share,
        # Capacity held flat unless the minister adds places: past drift isn't a plan.
        capacity_growth_w=0.0,
        last_week=pd.Timestamp(prison_w["week"].iloc[-1]),
    )


def simulate(state, lev: Levers, weeks=C.HORIZON_WEEKS, runs=C.N_RUNS, seed=C.SEED):
    rng = np.random.default_rng(seed)
    s = state
    B = np.full(runs, s["backlog"])
    sent = np.full(runs, s["sentenced"])
    cap_disp = (s["disp_per_day"] * s["sitting_days_w"] * (1 + lev.sitting_days_pct / 100 + lev.overbooking_uplift
                                                               + lev.fix_uplift)
                + lev.nightingale_rooms * C.NIGHTINGALE_DISPOSALS_PER_ROOM / 52)
    base_disp = s["disp_per_day"] * s["sitting_days_w"]
    W0 = s["backlog"] / base_disp
    stay0 = C.AVG_CUSTODY_WEEKS
    stay = stay0 * lev.release_point / C.BASE_RELEASE_POINT
    # calibrate sentenced inflow so the do-nothing run continues the recent trend
    inflow_per_disposal = (s["sentenced_growth_w"] + s["sentenced"] / stay0) / base_disp
    # persistent per-run uncertainty in growth plus weekly noise
    growth = s["receipts_growth_w"] + rng.normal(0, 0.0008, runs)
    out = {k: np.zeros((weeks, runs)) for k in ("backlog", "wait_weeks", "remand", "occupancy", "prison_pop")}
    for t in range(weeks):
        A = s["receipts_w"] * (1 + growth) ** t * np.exp(rng.normal(0, C.RECEIPTS_NOISE_SD, runs))
        D = np.minimum(B + A, cap_disp * np.exp(rng.normal(0, 0.05, runs)))
        B = B + A - D
        W = B / np.maximum(D, 1)
        # remand follows the smoothed arrival level, not week-to-week noise
        remand = s["remand"] * (1 + growth) ** t * (W / W0)
        sent = sent + inflow_per_disposal * D - sent / stay
        cap = s["capacity"] + s["capacity_growth_w"] * t + lev.extra_prison_places
        out["backlog"][t], out["wait_weeks"][t], out["remand"][t] = B, W, remand
        out["prison_pop"][t] = sent + remand
        out["occupancy"][t] = (sent + remand) / cap
    dates = pd.date_range(s["last_week"] + pd.Timedelta(weeks=1), periods=weeks, freq="W-FRI")
    fans = {k: pd.DataFrame({"week": dates, "p10": np.percentile(v, 10, axis=1),
                             "p50": np.percentile(v, 50, axis=1), "p90": np.percentile(v, 90, axis=1)})
            for k, v in out.items()}
    full = out["occupancy"] >= 1.0
    first_full = np.where(full.any(axis=0), full.argmax(axis=0), np.nan)  # weeks, NaN = never in horizon
    return fans, first_full


def weeks_until_full_summary(first_full):
    never = np.isnan(first_full).mean()
    if never > 0.5:
        return None, never
    return float(np.nanmedian(first_full)), never


def fix_uplift(court_q, reasons, chosen):
    """Extra disposals (fraction of current) if the chosen fixes prevent their share of
    ineffective trials. chosen = {fix name: reduction}. Uses the last 4 quarters."""
    last4 = court_q[court_q["qp"] > court_q["qp"].max() - 4]
    not_eff, disposals = last4["not_effective"].sum(), last4["disposals"].sum()
    out = {}
    for name, reduction in chosen.items():
        pats = C.FIXES[name]["patterns"]
        hit = reasons[(reasons["outcome"] == "ineffective")
                      & reasons["reason"].str.lower().apply(lambda r: any(p in r for p in pats))]
        share = hit["share"].sum()
        out[name] = dict(share_of_failed_trials=share, trials_saved=not_eff * share * reduction,
                         uplift=not_eff * share * reduction / disposals)
    return out


def annual_cost(lev: Levers, state, fixes=()):
    extra_days = state["sitting_days_w"] * 52 * lev.sitting_days_pct / 100
    return (sum(C.FIXES[f]["cost_per_year_gbp"] for f in fixes)
            + extra_days * C.COST_PER_SITTING_DAY_GBP
            + lev.nightingale_rooms * C.COST_PER_NIGHTINGALE_ROOM_YEAR_GBP
            + lev.extra_prison_places * C.COST_PER_PRISON_PLACE_YEAR_GBP)


def _queue_forecast(hist, horizon, window=4):
    """Forecast outstanding cases `horizon` quarters ahead from history only:
    receipts and disposals continue at their average over the last `window` quarters.
    (Extrapolating a linear trend in receipts did worse than "no change" in backtests.)"""
    rec = hist["receipts"].tail(window).mean()
    disp = hist["disposals"].tail(window).mean()
    B = hist["outstanding"].iloc[-1]
    path = []
    for _ in range(horizon):
        B = max(B + rec - min(disp, B + rec), 0)
        path.append(B)
    return np.array(path)


def hindcast(court_q, n_origins=8, horizon=4):
    """Rolling-origin backtest of the national queue model against 'no change'.

    For each origin quarter, forecast the backlog `horizon` quarters ahead using only
    data up to that origin. Returns the most recent full path (for the chart) and the
    mean absolute % error at the horizon for the model and the naive forecast."""
    nat = court_q.groupby("qp")[["receipts", "disposals", "outstanding"]].sum().sort_index()
    errs_model, errs_naive = [], []
    last_origin = len(nat) - horizon
    for o in range(last_origin - n_origins + 1, last_origin + 1):
        hist, fut = nat.iloc[:o], nat.iloc[o:o + horizon]
        pred = _queue_forecast(hist, horizon)
        actual = fut["outstanding"].values
        errs_model.append(abs(pred[-1] - actual[-1]) / actual[-1])
        errs_naive.append(abs(hist["outstanding"].iloc[-1] - actual[-1]) / actual[-1])
    o = last_origin - horizon
    hist, fut = nat.iloc[:o], nat.iloc[o:]
    pred = _queue_forecast(hist, len(fut))
    df = pd.DataFrame(dict(quarter=[str(q) for q in nat.index[o - 8:]],
                           actual=nat["outstanding"].iloc[o - 8:].values))
    df["model"] = [None] * 8 + list(pred)
    df["naive"] = [None] * 8 + [hist["outstanding"].iloc[-1]] * len(fut)
    return df, {"model MAPE": float(np.mean(errs_model)), "naive MAPE": float(np.mean(errs_naive))}

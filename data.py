"""Load the real MoJ data from data/*.csv, or fall back to clearly-labelled DEMO data.

Expected files (person A builds these from the MoJ releases):

data/court_quarterly.csv
    court, region, lat, lon, quarter (e.g. 2019Q3), receipts, disposals, outstanding,
    trials_listed, trials_cracked, trials_ineffective, sitting_days
data/prison_weekly.csv
    week (YYYY-MM-DD), population, remand, operational_capacity
data/crack_reasons.csv  (optional, used for synthetic case cards)
    outcome (cracked|ineffective), reason, share
data/offence_mix.csv    (optional)
    offence_group, share
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"

DEMO_COURTS = [
    # court, region, lat, lon, size (relative caseload)
    ("Oxford", "South East", 51.752, -1.258, 1.0),
    ("Reading", "South East", 51.455, -0.971, 1.1),
    ("Aylesbury", "South East", 51.816, -0.812, 0.8),
    ("Southwark", "London", 51.505, -0.087, 2.2),
    ("Snaresbrook", "London", 51.585, 0.021, 2.5),
    ("Birmingham", "Midlands", 52.483, -1.893, 2.4),
    ("Nottingham", "Midlands", 52.954, -1.150, 1.4),
    ("Manchester", "North West", 53.480, -2.242, 2.6),
    ("Liverpool", "North West", 53.408, -2.991, 2.0),
    ("Leeds", "North East", 53.800, -1.549, 2.0),
    ("Newcastle", "North East", 54.978, -1.617, 1.3),
    ("Bristol", "South West", 51.455, -2.588, 1.5),
    ("Exeter", "South West", 50.718, -3.533, 0.9),
    ("Cardiff", "Wales", 51.481, -3.179, 1.4),
    ("Swansea", "Wales", 51.621, -3.944, 0.8),
]

DEMO_CRACK_REASONS = pd.DataFrame(
    [
        ("cracked", "Late guilty plea", 0.55),
        ("cracked", "Prosecution offered no evidence", 0.25),
        ("cracked", "Plea to alternative charge", 0.20),
        ("ineffective", "Witness absent", 0.25),
        ("ineffective", "Defence not ready / no advocate", 0.30),
        ("ineffective", "Court overlisted / no judge", 0.25),
        ("ineffective", "Defendant absent or ill", 0.20),
    ],
    columns=["outcome", "reason", "share"],
)

DEMO_OFFENCE_MIX = pd.DataFrame(
    [
        ("Violence against the person", 0.30),
        ("Sexual offences", 0.15),
        ("Drug offences", 0.20),
        ("Theft and burglary", 0.15),
        ("Fraud", 0.08),
        ("Public order / weapons", 0.12),
    ],
    columns=["offence_group", "share"],
)


def _quarters(start="2016Q1", end="2025Q2"):
    return pd.period_range(start, end, freq="Q")


def _demo_court_quarterly(seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    qs = _quarters()
    for court, region, lat, lon, size in DEMO_COURTS:
        outstanding = 900 * size
        base_crack = rng.uniform(0.30, 0.45)
        base_ineff = rng.uniform(0.15, 0.28)
        for i, q in enumerate(qs):
            covid = 0.45 if str(q) in ("2020Q2", "2020Q3") else (0.8 if str(q) in ("2020Q4", "2021Q1") else 1.0)
            trend = 1 + 0.012 * i
            receipts = rng.poisson(1100 * size * trend * (0.6 if covid < 1 else 1.0))
            sitting_days = rng.poisson(1500 * size * covid * (1 + 0.0105 * i))
            disposals = min(outstanding + receipts, rng.poisson(sitting_days * 0.72))
            outstanding = outstanding + receipts - disposals
            listed = rng.poisson(260 * size * covid)
            drift = 0.03 * np.sin(i / 5)
            cracked = rng.binomial(listed, np.clip(base_crack + drift, 0.05, 0.9))
            ineff = rng.binomial(listed - cracked, np.clip(base_ineff + 0.002 * i - drift, 0.02, 0.9))
            rows.append(dict(court=court, region=region, lat=lat, lon=lon, quarter=str(q),
                             receipts=receipts, disposals=disposals, outstanding=outstanding,
                             trials_listed=listed, trials_cracked=cracked,
                             trials_ineffective=ineff, sitting_days=sitting_days))
    return pd.DataFrame(rows)


def _demo_prison_weekly(seed=2):
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2016-01-01", "2025-06-27", freq="W-FRI")
    t = np.arange(len(weeks))
    remand = 9000 + 7.5 * t + rng.normal(0, 120, len(t))
    sentenced = 74000 + 6.0 * t + rng.normal(0, 250, len(t))
    cap = 89000 + 6.0 * t
    return pd.DataFrame(dict(week=weeks, population=(remand + sentenced).round(),
                             remand=remand.round(), operational_capacity=cap.round()))


def load():
    """Return dict of DataFrames plus is_demo flag."""
    cq_path = DATA_DIR / "court_quarterly.csv"
    pw_path = DATA_DIR / "prison_weekly.csv"
    is_demo = not (cq_path.exists() and pw_path.exists())
    if is_demo:
        court_q = _demo_court_quarterly()
        prison_w = _demo_prison_weekly()
    else:
        court_q = pd.read_csv(cq_path)
        prison_w = pd.read_csv(pw_path, parse_dates=["week"])
    reasons_path = DATA_DIR / "crack_reasons.csv"
    mix_path = DATA_DIR / "offence_mix.csv"
    reasons = pd.read_csv(reasons_path) if reasons_path.exists() else DEMO_CRACK_REASONS
    mix = pd.read_csv(mix_path) if mix_path.exists() else DEMO_OFFENCE_MIX
    court_q["qp"] = pd.PeriodIndex(court_q["quarter"], freq="Q")
    court_q = court_q.sort_values(["court", "qp"]).reset_index(drop=True)
    court_q["not_effective"] = court_q["trials_cracked"] + court_q["trials_ineffective"]
    return dict(court_q=court_q, prison_w=prison_w.sort_values("week"),
                reasons=reasons, mix=mix, is_demo=is_demo)

"""Turn the official MoJ downloads into the CSVs the app reads (data/*.csv).

Inputs (put them in raw/):
  raw/cc_rdos_tool.xlsx   Crown Court receipts, disposals and open cases tool (CCSQ, gov.uk)
  raw/trials_tool.xlsx    Trial effectiveness at the criminal courts tool (CCSQ, gov.uk)
Both are pivot-table workbooks; the raw rows live in the pivot cache, which we read directly.

Prison figures come from the weekly population bulletins and Offender Management Statistics
(see PRISON_POINTS below, each with its source).

Run:  python build_data.py
"""
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RAW, OUT = HERE / "raw", HERE / "data"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# Approximate town-centre coordinates, for the map only.
COURT_COORDS = {
    "Aylesbury": (51.816, -0.812), "Basildon": (51.576, 0.488), "Birmingham": (52.483, -1.893),
    "Blackfriars": (51.503, -0.104), "Bolton": (53.578, -2.429), "Bournemouth": (50.720, -1.880),
    "Bradford": (53.795, -1.759), "Bristol": (51.455, -2.588), "Cambridge": (52.205, 0.122),
    "Canterbury": (51.280, 1.079), "Cardiff": (51.481, -3.179), "Carlisle": (54.892, -2.932),
    "Central Criminal Court": (51.516, -0.102), "Chelmsford": (51.736, 0.469), "Chester": (53.190, -2.891),
    "Croydon": (51.372, -0.099), "Derby": (52.922, -1.476), "Dorchester": (50.716, -2.437),
    "Durham": (54.776, -1.575), "Exeter": (50.718, -3.533), "Gloucester": (51.864, -2.244),
    "Great Grimsby": (53.567, -0.080), "Guildford": (51.236, -0.570), "Harrow": (51.580, -0.341),
    "Inner London Sessions House": (51.497, -0.100), "Ipswich": (52.057, 1.148), "Isleworth": (51.475, -0.336),
    "Kingston Upon Hull": (53.745, -0.336), "Kingston Upon Thames": (51.412, -0.300), "Leeds": (53.800, -1.549),
    "Leicester": (52.637, -1.140), "Lewes": (50.873, 0.009), "Lincoln": (53.234, -0.538),
    "Liverpool": (53.408, -2.991), "Luton": (51.879, -0.418), "Maidstone": (51.272, 0.523),
    "Manchester Crown Sq": (53.481, -2.251), "Manchester Minshull St": (53.479, -2.237), "Mold": (53.167, -3.142),
    "Newcastle Upon Tyne": (54.978, -1.617), "Newport (Isle of Wight)": (50.701, -1.292),
    "Northampton": (52.240, -0.902), "Norwich": (52.630, 1.297), "Nottingham": (52.954, -1.150),
    "Oxford": (51.752, -1.258), "Plymouth": (50.375, -4.143), "Portsmouth": (50.819, -1.088),
    "Preston": (53.763, -2.703), "Reading": (51.455, -0.971), "Salisbury": (51.069, -1.795),
    "Sheffield": (53.381, -1.470), "Shrewsbury": (52.708, -2.754), "Snaresbrook": (51.585, 0.021),
    "Southampton": (50.909, -1.404), "Southwark": (51.505, -0.087), "St Albans": (51.755, -0.336),
    "Stafford": (52.806, -2.117), "Stoke On Trent": (53.003, -2.179), "Swansea": (51.621, -3.944),
    "Swindon": (51.558, -1.782), "Taunton": (51.015, -3.103), "Teesside": (54.574, -1.235),
    "Truro": (50.263, -5.051), "Warwick": (52.282, -1.585), "Winchester": (51.063, -1.308),
    "Wolverhampton": (52.587, -2.129), "Wood Green": (51.597, -0.109), "Woolwich": (51.491, 0.069),
    "Worcester": (52.192, -2.220), "York": (53.958, -1.080),
}

# Published prison figures. Remand/sentenced only appear quarterly, so weeks in between
# are linearly interpolated (flagged in the CSV).
PRISON_POINTS = [
    # date, population, remand, useable operational capacity, source
    ("2025-06-30", None, 15386 / 0.87, None, "OMSQ Jan-Mar 2026: remand at 30 Jun 2026 was 13% lower than June 2025"),
    ("2025-09-08", 88045, None, 89720, "Weekly bulletin 7 Sep 2026 ('12 months ago' figures)"),
    ("2026-06-30", 85858, 15386, None, "OMSQ Jan-Mar 2026 bulletin"),
    ("2026-09-07", 86868, None, 88943, "Weekly bulletin 7 Sep 2026"),
]


def read_pivot_cache(xlsx_path):
    with zipfile.ZipFile(xlsx_path) as z:
        d = ET.fromstring(z.read("xl/pivotCache/pivotCacheDefinition1.xml"))
        fields, shared = [], []
        for cf in d.iter(NS + "cacheField"):
            fields.append(cf.get("name"))
            si = cf.find(NS + "sharedItems")
            items = None
            if si is not None and len(si):
                items = [float(e.get("v")) if e.tag == NS + "n" else e.get("v") for e in si]
            shared.append(items)
        rows = []
        with z.open("xl/pivotCache/pivotCacheRecords1.xml") as f:
            for _, rec in ET.iterparse(f):
                if rec.tag != NS + "r":
                    continue
                row = []
                for i, e in enumerate(rec):
                    tag = e.tag[len(NS):]
                    if tag == "x":
                        row.append(shared[i][int(e.get("v"))])
                    elif tag == "n":
                        row.append(float(e.get("v")))
                    elif tag == "m":
                        row.append(None)
                    else:
                        row.append(e.get("v"))
                rows.append(row)
                rec.clear()
    return pd.DataFrame(rows, columns=fields)


def build_courts():
    rdos = read_pivot_cache(RAW / "cc_rdos_tool.xlsx")
    rdos = rdos[(rdos["offence_group"] == "00: All offences") & (rdos["crown_court"] != "Unknown")]
    rdos["quarter"] = rdos["year"].astype(int).astype(str) + rdos["quarter"]
    cases = (rdos.pivot_table(index=["crown_court", "region", "quarter"], columns="rdos",
                              values="value", aggfunc="sum", fill_value=0)
             .rename(columns={"1. Receipts": "receipts", "2. Disposals": "disposals", "3. Open": "outstanding"})
             .reset_index())

    trials = read_pivot_cache(RAW / "trials_tool.xlsx")
    trials = trials[(trials["court_type"] == "Crown") & (trials["offence_group"] == "00: All offences")
                    & (trials["trial_effectiveness"] != "4: Vacated trials")]
    trials["quarter"] = trials["year"].astype(int).astype(str) + trials["quarter"]
    t = (trials.pivot_table(index=["crown_court_and_magistrates_lja", "quarter"], columns="trial_effectiveness",
                            values="value", aggfunc="sum", fill_value=0)
         .rename(columns={"1: Effective trials": "trials_effective", "2: Cracked trials": "trials_cracked",
                          "3: Ineffective trials": "trials_ineffective"})
         .reset_index().rename(columns={"crown_court_and_magistrates_lja": "crown_court"}))
    t["trials_listed"] = t[["trials_effective", "trials_cracked", "trials_ineffective"]].sum(axis=1)

    df = cases.merge(t, on=["crown_court", "quarter"], how="inner").rename(columns={"crown_court": "court"})
    df = df[df["court"].isin(COURT_COORDS)]
    df["lat"] = df["court"].map(lambda c: COURT_COORDS[c][0])
    df["lon"] = df["court"].map(lambda c: COURT_COORDS[c][1])
    # Sitting days by court aren't in these tools: use disposals as the capacity measure,
    # so capacity levers scale recent throughput.
    df["sitting_days"] = df["disposals"]
    cols = ["court", "region", "lat", "lon", "quarter", "receipts", "disposals", "outstanding",
            "trials_listed", "trials_cracked", "trials_ineffective", "sitting_days"]
    df = df[cols].sort_values(["court", "quarter"])
    df.to_csv(OUT / "court_quarterly.csv", index=False)

    # Shares of reasons for trials not going ahead, last 4 quarters, for synthetic case cards.
    recent = sorted(trials["quarter"].unique())[-4:]
    r = trials[trials["quarter"].isin(recent) & trials["trial_effectiveness"].isin(["2: Cracked trials", "3: Ineffective trials"])]
    r = r.groupby(["trial_effectiveness", "reason"])["value"].sum().reset_index()
    r["outcome"] = np.where(r["trial_effectiveness"].str.startswith("2"), "cracked", "ineffective")
    r["reason"] = r["reason"].str.replace(r"^\d+\. (Cracked|Ineffective) [Rr]eason: ", "", regex=True)
    r["share"] = r["value"] / r["value"].sum()
    r[r["share"] > 0.005][["outcome", "reason", "share"]].sort_values("share", ascending=False).to_csv(
        OUT / "crack_reasons.csv", index=False)

    # Offence mix of Crown Court receipts, last 4 quarters.
    full = read_pivot_cache(RAW / "cc_rdos_tool.xlsx")
    full["quarter"] = full["year"].astype(int).astype(str) + full["quarter"]
    m = full[(full["rdos"] == "1. Receipts") & full["quarter"].isin(sorted(full["quarter"].unique())[-4:])
             & (full["offence_group"] != "00: All offences")
             & full["offence_group"].str.match(r"^\d\d: [^-]+$")]
    m = m.groupby("offence_group")["value"].sum()
    m = (m / m.sum()).reset_index().rename(columns={"value": "share"})
    m["offence_group"] = m["offence_group"].str.replace(r"^\d\d: ", "", regex=True)
    m.to_csv(OUT / "offence_mix.csv", index=False)
    return df


def build_prison():
    pts = pd.DataFrame(PRISON_POINTS, columns=["week", "population", "remand", "operational_capacity", "source"])
    pts["week"] = pd.to_datetime(pts["week"])
    weeks = pd.date_range(pts["week"].min(), pts["week"].max(), freq="W-MON")
    idx = pd.DatetimeIndex(sorted(set(weeks) | set(pts["week"])))
    s = pts.set_index("week")[["population", "remand", "operational_capacity"]].astype(float).reindex(idx)
    s = s.interpolate(method="time", limit_direction="both")
    s["interpolated"] = ~s.index.isin(pts["week"])
    s = s.reindex(weeks).round()
    s.index.name = "week"
    s.reset_index().to_csv(OUT / "prison_weekly.csv", index=False)
    pts.to_csv(OUT / "prison_sources.csv", index=False)
    return s


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    missing = [f for f in ("cc_rdos_tool.xlsx", "trials_tool.xlsx") if not (RAW / f).exists()]
    if missing:
        sys.exit(f"Put these gov.uk downloads in {RAW}: {missing}")
    courts = build_courts()
    prison = build_prison()
    print(f"courts: {courts['court'].nunique()} courts, {courts['quarter'].min()}-{courts['quarter'].max()}")
    print(f"prison: {len(prison)} weeks, latest population {prison['population'].iloc[-1]:,.0f}")

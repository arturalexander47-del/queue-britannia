"""Queue Britannia: you are the Justice Secretary. Run with:  streamlit run app.py"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config as C
import crack_model as cm
import data
import game as G
import game_tab
import humphrey
import simulation as sim
import style

st.set_page_config(page_title="Queue Britannia", page_icon="⚖️", layout="wide")
style.inject()


@st.cache_data
def load_all():
    d = data.load()
    post = cm.fit(d["court_q"])
    bt_rows, bt_summary, coverage = cm.backtest(d["court_q"])
    hind, hind_metrics = sim.hindcast(d["court_q"])
    state = sim.baseline_state(d["court_q"], d["prison_w"])
    return d, post, bt_rows, bt_summary, coverage, hind, hind_metrics, state


@st.cache_resource
def game_world():
    return G.World(d["court_q"], d["prison_w"], d["reasons"], post)


@st.cache_data
def area_state(region):
    return sim.baseline_state(d["court_q"], d["prison_w"], region=region)


@st.cache_data
def run_sim(state, levers_tuple):
    return sim.simulate(state, sim.Levers(*levers_tuple))


d, post, bt_rows, bt_summary, coverage, hind, hind_metrics, state = load_all()
court_q = d["court_q"]
latest = court_q[court_q["qp"] == court_q["qp"].max()].merge(post, on=["court", "region"])
latest["wait_weeks"] = latest["outstanding"] / (latest["disposals"] / 13)

base_fans, base_full = run_sim(state, tuple(vars(sim.Levers()).values()))
base_weeks, _ = sim.weeks_until_full_summary(base_full)

if d["is_demo"]:
    st.warning("DEMO DATA: synthetic numbers. Drop the real MoJ CSVs into data/ (see data.py) before judging.")


def fan_chart(fan, title, y_label, hline=None):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fan["week"], y=fan["p90"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=fan["week"], y=fan["p10"], fill="tonexty", line=dict(width=0),
                             fillcolor="rgba(212,169,58,0.25)", name="80% range"))
    fig.add_trace(go.Scatter(x=fan["week"], y=fan["p50"], line=dict(color="#d4a93a", width=2), name="median"))
    if hline is not None:
        fig.add_hline(y=hline, line_dash="dash", line_color="red")
    fig.update_layout(title=title, yaxis_title=y_label, height=300, margin=dict(l=10, r=10, t=40, b=10))
    return fig


PLAY, EXPLORE, PROOF = "🗳️ Play the game", "📊 Explore the data", "🔬 How we know it works"
with st.sidebar:
    st.markdown("### Queue Britannia")
    page = st.radio("Go to", [PLAY, EXPLORE, PROOF], label_visibility="collapsed")
    st.caption("**Play** is the game. **Explore** shows the real court and prison data behind it. "
               "**How we know it works** has the backtests and the Autopilot benchmark.")

if page == PLAY:
    game_tab.render(game_world())
else:
    st.title("⚖️ Queue Britannia")
    st.caption("You've just been made Justice Secretary. Congratulations. The system is full.")

# ---------------------------------------------------------------- 1. State of the Nation
if page == EXPLORE:
    st.header("State of the Nation")
    st.caption("Where the backlog is today, by Crown Court (real MoJ data, Apr–Jun 2026).")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cases waiting (Crown Court)", f"{state['backlog']:,.0f}")
    c2.metric("Prison occupancy", f"{(state['sentenced'] + state['remand']) / state['capacity']:.1%}")
    c3.metric("On remand", f"{state['remand']:,.0f}")
    c4.metric("⏳ Weeks until prisons are full", "Already full" if base_weeks == 0 else
              ("Not within 3 years" if base_weeks is None else f"{base_weeks:.0f}"))
    fig = px.scatter_map(latest, lat="lat", lon="lon", size="outstanding", color="wait_weeks",
                            hover_name="court", color_continuous_scale="YlOrRd", size_max=40, zoom=5.2,
                            hover_data={"outstanding": True, "wait_weeks": ":.0f", "lat": False, "lon": False},
                            labels={"wait_weeks": "Weeks of backlog"})
    fig.update_layout(map_style="carto-darkmatter", height=520, margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- 2. The Listing Office
if page == EXPLORE:
    st.divider()
    st.header("The Listing Office: smart overbooking")
    st.caption("Pick a court and see how listing a few extra trials changes how much court time is used.")
    courts = sorted(post["court"])
    court = st.selectbox("Court", courts, index=courts.index("Oxford") if "Oxford" in courts else 0)
    row = post.set_index("court").loc[court]
    lo, hi = cm.predictive_interval(row.alpha, row.beta, 200)
    a, b = st.columns([1, 1])
    a.metric("Predicted share of listed trials that won't go ahead next quarter",
             f"{row.p_not_effective:.0%}", help=f"80% range {lo:.0%}–{hi:.0%}")
    slots = a.slider("Courtroom trial slots per day", 1, 20, 8)
    penalty = a.slider("How bad is bumping a ready trial? (in lost trial-slots)", 0.5, 5.0, C.BUMP_PENALTY, 0.5)
    curve, best = cm.overbooking_curve(row.alpha, row.beta, slots=slots, bump_penalty=penalty)
    listed = a.slider("Trials listed per day", slots, int(curve["listed"].max()), best)
    pick = curve.set_index("listed").loc[listed]
    base_util = curve.iloc[0]["utilisation"]
    yearly_listed = court_q[court_q["court"] == court].tail(4)["trials_listed"].sum()
    extra = yearly_listed * (pick["utilisation"] - base_util)
    a.success(f"Recommended: list **{best}** for {slots} slots.  \nAt {listed}: **+{extra:,.0f} trials heard per year**, "
              f"{pick['p_any_bump']:.0%} of days bump at least one trial.")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=curve["listed"], y=curve["utilisation"], name="Court time used", mode="lines+markers"))
    fig.add_trace(go.Scatter(x=curve["listed"], y=curve["p_any_bump"], name="Chance a ready trial is bumped",
                             mode="lines+markers", yaxis="y"))
    fig.add_vline(x=listed, line_dash="dot")
    fig.update_layout(title="The airline trick: overbook, but not too much", xaxis_title="Trials listed per day",
                      yaxis_tickformat=".0%", height=360, margin=dict(l=10, r=10, t=40, b=10))
    b.plotly_chart(fig, width="stretch")
    st.subheader("This week's list (synthetic cases)")
    st.caption("Synthetic cases sampled from published offence-mix and crack-reason breakdowns. Not real people.")
    wait = latest.set_index("court").loc[court, "wait_weeks"] if court in set(latest["court"]) else 40
    st.dataframe(cm.synthetic_cases(row.p_not_effective, d["reasons"], d["mix"], n=listed,
                                    mean_wait_weeks=wait), hide_index=True, width="stretch")
    # National effect if every court overbooked like this: extra effective trials / current disposals
    last4 = court_q[court_q["qp"] > court_q["qp"].max() - 4]
    st.session_state["overbooking_uplift"] = max(
        0.0, last4["trials_listed"].sum() * (pick["utilisation"] - base_util) / last4["disposals"].sum())
    st.caption("Watch out: 'overlisting' is already a recorded reason for ineffective trials. "
               "Overbooking only helps if it's targeted where trials are most likely to fall through.")

# ---------------------------------------------------------------- 3. The Minister's Desk
if page == EXPLORE:
    st.divider()
    st.header("Sandbox: try policies with no budget or game rules")
    left, right = st.columns([1, 2])
    with left:
        st.subheader("Your levers, Minister")
        regions = sorted(court_q["region"].unique())
        area = st.selectbox("Area", ["England and Wales"] + regions)
        region = None if area == "England and Wales" else area
        a_state = state if region is None else area_state(region)
        a_base_fans, a_base_full = (base_fans, base_full) if region is None else run_sim(
            a_state, tuple(vars(sim.Levers()).values()))
        a_base_weeks, _ = sim.weeks_until_full_summary(a_base_full)
        sd = st.slider(f"Extra court capacity in {area}: sitting days (%)", 0, 30, 0,
                       help="Sitting days by court aren't published, so this scales the area's recent case throughput.")
        ng = st.slider("Nightingale courtrooms", 0, 40 if region is None else 10, 0)
        ob = st.toggle("Smart overbooking (from the Listing Office)", value=False)
        st.markdown("**Fixes for why trials fall through** (effects are assumptions)")
        chosen = {}
        for name, f in C.FIXES.items():
            if st.checkbox(name, help=f["note"]):
                chosen[name] = st.slider(f"{name}: share of those failures prevented (assumption)",
                                         0.0, 1.0, f["reduction"], 0.05, key=f"red_{name}")
        rp = st.select_slider("Automatic release point", options=[0.4, 0.5], value=0.5,
                              format_func=lambda x: f"{x:.0%} of sentence")
        places = st.slider("Emergency prison places", 0, 5000, 0, 500)
    area_q = court_q if region is None else court_q[court_q["region"] == region]
    fixes = sim.fix_uplift(area_q, d["reasons"], chosen)
    levers = sim.Levers(sd, ng, st.session_state.get("overbooking_uplift", 0.0) if ob else 0.0, rp,
                        places if region is None else 0, sum(f["uplift"] for f in fixes.values()))
    fans, first_full = run_sim(a_state, tuple(vars(levers).values()))
    weeks, never = sim.weeks_until_full_summary(first_full)
    backlog_change = (fans["backlog"]["p50"].iloc[-1] / a_base_fans["backlog"]["p50"].iloc[-1] - 1) * 100
    cost = sim.annual_cost(levers, a_state, chosen)
    line, headline = humphrey.react(levers, a_base_weeks, weeks, backlog_change)
    with left:
        if region is None:
            st.metric("⏳ Weeks until prisons are full", "Not within 3 years" if weeks is None else f"{weeks:.0f}",
                      delta=None if (weeks is None or a_base_weeks is None) else f"{weeks - a_base_weeks:+.0f} vs doing nothing")
        st.metric("Backlog in 3 years vs doing nothing", f"{backlog_change:+.0f}%")
        st.metric("Median wait now", f"{fans['wait_weeks']['p50'].iloc[0]:.0f} weeks of backlog")
        st.metric("Annual cost", f"£{cost:,.0f}" if cost else "Set unit costs in config.py")
        st.metric("Chance you survive the next reshuffle",
                  f"{humphrey.career_survival(backlog_change, weeks, cost)}%")
    with right:
        st.info(f"🎩 **Sir Humphrey:** {line}")
        st.error(f"📰 **{headline}**")
        st.plotly_chart(fan_chart(fans["backlog"], f"Crown Court backlog: {area}", "cases"), width="stretch")
        if region is None:
            g1, g2 = st.columns(2)
            g1.plotly_chart(fan_chart(fans["remand"], "Remand population", "people"), width="stretch")
            g2.plotly_chart(fan_chart(fans["occupancy"], "Prison occupancy", "share of capacity", hline=1.0),
                            width="stretch")
        else:
            st.caption("Prison figures are national only, so they appear when Area = England and Wales.")
        if fixes:
            st.markdown("**What the fixes do** (from recorded reasons trials were ineffective, last 4 quarters)")
            st.dataframe(pd.DataFrame([
                dict(Fix=n, **{"Share of failed trials with these reasons": f"{v['share_of_failed_trials']:.1%}",
                               "Trials saved per year (assumed)": f"{v['trials_saved']:,.0f}",
                               "Extra capacity": f"{v['uplift']:.1%}"}) for n, v in fixes.items()]),
                hide_index=True, width="stretch")
        st.markdown(f"**Courts in {area}**")
        table = latest if region is None else latest[latest["region"] == region]
        st.dataframe(table[["court", "region", "outstanding", "wait_weeks", "p_not_effective"]]
                     .sort_values("wait_weeks", ascending=False)
                     .rename(columns={"court": "Court", "region": "Region", "outstanding": "Cases waiting",
                                      "wait_weeks": "Weeks of backlog", "p_not_effective": "Trials not going ahead"})
                     .style.format({"Weeks of backlog": "{:.0f}", "Trials not going ahead": "{:.0%}",
                                    "Cases waiting": "{:,.0f}"}),
                     hide_index=True, width="stretch")

# ---------------------------------------------------------------- 4. Under the Bonnet
if page == PROOF:
    st.header("How we know it works")
    st.subheader("Does the crack-rate model beat simple baselines?")
    st.caption("Walk-forward backtest: each quarter is predicted using only earlier quarters.")
    st.dataframe(bt_summary.style.format("{:.4f}"), width="stretch")
    st.write(f"80% prediction intervals contained the actual rate **{coverage:.0%}** of the time (target: 80%).")
    fig = px.scatter(bt_rows, x="model", y="actual", hover_data=["court", "quarter"],
                     labels={"model": "Predicted rate", "actual": "Actual rate"},
                     title="Predicted vs actual share of trials not going ahead")
    fig.add_shape(type="line", x0=bt_rows["actual"].min(), y0=bt_rows["actual"].min(),
                  x1=bt_rows["actual"].max(), y1=bt_rows["actual"].max(), line=dict(dash="dash"))
    st.plotly_chart(fig, width="stretch")
    st.subheader("Backlog forecast backtest")
    st.caption("Rolling origins: forecast the national backlog 4 quarters ahead using only data up to each origin. "
               "Chart shows the latest 8-quarter-ahead path.")
    fig = go.Figure()
    for col, name in [("actual", "Actual"), ("model", "Queue model"), ("naive", "Naive (no change)")]:
        fig.add_trace(go.Scatter(x=hind["quarter"], y=hind[col], name=name, mode="lines+markers"))
    fig.update_layout(yaxis_title="Outstanding cases", height=360, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width="stretch")
    st.write(f"Mean absolute % error 4 quarters ahead: queue model **{hind_metrics['model MAPE']:.1%}**, "
             f"'no change' **{hind_metrics['naive MAPE']:.1%}**.")
    st.subheader("Data and limits")
    st.markdown(
        "- Aggregate public statistics only: MoJ Criminal Court Statistics Quarterly (Apr–Jun 2026): Crown Court "
        "receipts, disposals and open cases tool, and trial effectiveness tool; HMPPS weekly prison population "
        "bulletin (7 Sep 2026); Offender Management Statistics Quarterly (remand at 30 Jun 2026).\n"
        "- Weekly prison figures between published dates are interpolated (`data/prison_sources.csv`).\n"
        "- Court capacity is measured by disposals (sitting days by court aren't in these tools).\n"
        "- Case cards are **synthetic**, sampled from published breakdowns.\n"
        "- No predictions about individual defendants, victims or witnesses.\n"
        "- Assumptions marked PLACEHOLDER in `config.py` are shown here once sourced.")
    game_tab.render_benchmark(data.DATA_DIR / "benchmark.csv")

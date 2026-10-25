"""The 'Survive to the Election' game: title screen, turns, newspaper between quarters, end screen."""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config as C
import game as G
import humphrey
import style as S

LEADERBOARD = Path(__file__).parent / "data" / "leaderboard.csv"
OB_LABELS = ["None", "Light (+1 trial per 4 courtrooms)", "Medium (+2)", "Heavy (+3)"]


def _new_game(seed):
    world = st.session_state["g_world"]
    st.session_state.update(g_state=world.initial(1), g_rng=np.random.default_rng(seed), g_seed=seed,
                            g_history=[], g_log=[], g_saved=False)


def _apply(action: G.Action):
    st.session_state["g_rooms"] = action.rooms
    st.session_state["g_region"] = action.room_region
    for name in C.FIXES:
        st.session_state[f"g_fund_{name}"] = float(action.funds.get(name, 0.0))
    st.session_state["g_ob"] = OB_LABELS[action.overbook]
    st.session_state["g_places"] = action.places
    st.session_state["g_er"] = action.early_release


def _describe(a: G.Action):
    parts = []
    if a.rooms:
        parts.append(f"{a.rooms} extra courtrooms ({a.room_region.lower()})")
    parts += [f"£{v:.0f}m on {k.lower()}" for k, v in a.funds.items() if v]
    if a.overbook:
        parts.append(f"{OB_LABELS[a.overbook].split(' ')[0].lower()} overbooking")
    if a.places:
        parts.append(f"{a.places:,} prison places ordered")
    if a.early_release:
        parts.append("early release at 40%")
    return ", ".join(parts) or "masterly inactivity"


def render(world):
    st.session_state["g_world"] = world
    if "g_state" not in st.session_state:
        _new_game(seed=int(np.random.default_rng().integers(1, 10_000)))
        st.session_state["g_phase"] = "title"
    phase = st.session_state.get("g_phase", "play")
    if phase == "title":
        return _title()
    if phase == "news":
        return _newspaper()
    s = st.session_state["g_state"]
    q, alive = s["q"], bool(s["alive"][0])
    if not (alive and q < G.QUARTERS):
        _game_over(world, s)
        if st.session_state["g_history"]:
            _charts()
        return

    S.show(S.ribbon(q, G.QUARTERS))
    with st.expander("📖 How to play", expanded=(q == 0)):
        st.markdown(
            "1. Check your four gauges: **cases waiting**, **prison occupancy**, **popularity** and **budget**.\n"
            "2. Make this quarter's choices in **Your red box**: extra courtrooms, funding for fixes, "
            "overbooking, prison places (open 2 quarters later) and, in an emergency, early release.\n"
            "3. Click **🔔 End the quarter** and read the morning papers. Repeat for 12 quarters.\n"
            "4. Stuck? Click **Ask Sir Humphrey**, then **Do what Sir Humphrey says**.\n\n"
            "**You lose** if prisons reach 100% or popularity hits 5. **The catch:** clearing cases sends more "
            "people to prison, so order prison places early.")

    occ = (s["sentenced"][0] + s["remand"][0]) / s["places"][0]
    change = s["backlog"].sum() - world.backlog0.sum()
    pop = float(s["popularity"][0])
    c = st.columns(4)
    c[0].markdown(S.stat("⚖️ Cases waiting", f"{s['backlog'].sum():,.0f}",
                         (f"{'▲' if change > 0 else '▼'} {abs(change):,.0f} since you took office" if round(change)
                          else "the backlog you inherited")), unsafe_allow_html=True)
    c[1].markdown(S.stat("🔒 Prisons", f"{occ:.1%}",
                         f"{s['places'][0] - s['sentenced'][0] - s['remand'][0]:,.0f} spaces left", bar=occ,
                         bar_color=S.RED if occ > 0.97 else S.GOLD, danger=occ > 0.98), unsafe_allow_html=True)
    c[2].markdown(S.stat("📣 Popularity", f"{pop:.0f} / 100", "sacked at 5", bar=pop / 100,
                         bar_color=S.RED if pop < 20 else S.GREEN, danger=pop < 15), unsafe_allow_html=True)
    c[3].markdown(S.stat("💷 Budget", f"£{s['budget'][0]:.0f}m",
                         f"🏗️ {s['pipeline'][0].sum():,.0f} places being built" if s["pipeline"].sum() else
                         f"+£{G.BUDGET_PER_QUARTER_M:.0f}m a quarter"), unsafe_allow_html=True)
    st.write("")
    _turn(world, s)

    if st.session_state["g_history"]:
        _charts()

    with st.expander("How the game works, and which numbers are assumptions"):
        st.markdown(
            "- Starting backlog, receipts, disposals, trial failure rates and reasons by region come from the MoJ "
            "court statistics. Prison population, places and remand come from HMPPS and OMSQ figures.\n"
            "- **Illustrative (replace with sourced figures):** budget, courtroom cost "
            f"(£{G.COURTROOM_COST_M}m a quarter), prison place cost (£{G.PLACE_BUILD_COST_M * 1000:.0f}k), "
            f"cases per extra courtroom ({G.DISPOSALS_PER_ROOM_Q:.0f} a quarter), fund effectiveness, "
            f"underlying prison growth ({G.PRISON_DRIFT_Q} a quarter), event probabilities, popularity rules.\n"
            "- Fixes act only on the recorded reasons trials fail (e.g. 'defence advocate failed to attend'), "
            "so their effect is capped by how common those reasons are.\n"
            "- Overbooking gains come from a Monte Carlo of court days using each region's predicted collapse rate. "
            "Bumped trials annoy everyone (popularity).")


def _title():
    S.show('''<div class="qb-title"><div class="crest">⚖️</div><h1>Queue Britannia</h1>
<div class="tag">A game of courts, cells and career survival</div></div>
<div class="qb-letter"><b>10 Downing Street</b><br><br>Dear Minister,<br><br>
Congratulations on your appointment as Justice Secretary. You inherit a Crown Court backlog of record size
and prisons that are, technically speaking, full.<br><br>
You have <b>three years</b> until the election. Clear the backlog. Do not run out of cells. Do not become
unpopular. Sir Humphrey will assist you, in his way.<br><br>
<i>Yours, the Prime Minister</i><div class="seal">👑</div></div>''')
    _, mid, _ = st.columns([1, 1, 1])
    if mid.button("✒️ Accept the seals of office", type="primary", width="stretch"):
        st.session_state["g_phase"] = "play"
        st.rerun()
    st.caption("Every number at the start comes from real Ministry of Justice and HMPPS data.")


def _newspaper():
    n = st.session_state["g_news"]

    def delta(before, after, fmt, bad_up=True):
        d = after - before
        cls = ("up" if d > 0 else "down") if bad_up else ("down" if d > 0 else "up")
        return f'<span class="{cls}">{"▲" if d > 0 else "▼"} {fmt(abs(d))}</span>'

    events = "".join(f'<span class="event">{S.esc(e.upper())}</span>' for e in n["events"])
    S.show(f'''<div class="qb-paper"><div class="mast">The Daily Queue</div>
<div class="dateline"><span>Quarter {n["q"]} of {G.QUARTERS}</span><span>Price: one sitting day</span>
<span>{"Election special" if n["q"] >= G.QUARTERS else f"{G.QUARTERS - n['q']} quarters to polling day"}</span></div>
{events}<div class="head">{S.esc(n["head"])}</div><div class="deck">{S.esc(n["deck"])}</div>
<div class="cols">
<div>Cases waiting<b>{n["backlog"]:,.0f}</b>{delta(n["backlog0"], n["backlog"], lambda v: f"{v:,.0f}")}</div>
<div>Prisons<b>{n["occ"]:.1%}</b>{delta(n["occ0"], n["occ"], lambda v: f"{v * 100:.1f} pts")}</div>
<div>Popularity<b>{n["pop"]:.0f}</b>{delta(n["pop0"], n["pop"], lambda v: f"{v:.0f}", bad_up=False)}</div></div>
<div class="quote">🎩 Sir Humphrey: "{S.esc(n["quip"])}"</div>
<div style="font-size:.85rem;margin-top:10px">This quarter the Minister chose: {S.esc(n["action"])}.</div></div>''')
    _, mid, _ = st.columns([1, 1, 1])
    label = "See how it ended ➜" if n["over"] else f"➜ On to quarter {n['q'] + 1}"
    if mid.button(label, type="primary", width="stretch"):
        st.session_state["g_phase"] = "play"
        st.rerun()


def _turn(world, s):
    budget = float(s["budget"][0])
    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### 🟥 Your red box: decisions this quarter")
        a, b = st.columns(2)
        rooms = a.slider("Extra courtrooms (this quarter)", 0, 100, key="g_rooms", step=5)
        region = b.selectbox("Where", ["Worst wait", "Spread evenly"] + world.regions, key="g_region")
        funds = {}
        cols = st.columns(len(C.FIXES))
        for col, name in zip(cols, C.FIXES):
            funds[name] = col.slider(f"£m: {name.lower()}", 0.0, 30.0, step=5.0, key=f"g_fund_{name}",
                                     help=C.FIXES[name]["note"])
        a, b = st.columns(2)
        ob = a.select_slider("Overbooking", OB_LABELS, key="g_ob")
        places = b.slider("Order emergency prison places", 0, 3000, step=250, key="g_places")
        er = st.toggle("Early release at 40% of sentence (very unpopular)", key="g_er")
        action = G.Action(rooms=rooms, room_region=region, funds={k: v for k, v in funds.items() if v},
                          overbook=OB_LABELS.index(ob), places=places, early_release=er)
        cost = action.cost()
        st.write(f"**Cost this quarter: £{cost:.1f}m** of £{budget:.0f}m available.")
        go_btn = st.button("🔔 End the quarter", type="primary", disabled=cost > budget + 1e-9)
        if cost > budget + 1e-9:
            st.error("The Treasury says no, Minister. Over budget.")
    with right:
        st.markdown("#### 🎩 Sir Humphrey's Autopilot")
        st.caption("Simulates 30 possible futures for 40 candidate plans, 4 quarters ahead, and picks the one with the "
                   "best expected outcome and least risk of losing.")
        if st.button("Ask Sir Humphrey"):
            with st.spinner("Consulting the Permanent Secretary..."):
                rec = G.autopilot(world, s, scenarios=30, seed=st.session_state["g_seed"] * 100 + s["q"])
            st.session_state["g_rec"] = rec
        rec = st.session_state.get("g_rec")
        if rec is not None:
            st.write(f"*\"If I may, Minister: {_describe(rec)}.\"*  (£{rec.cost():.1f}m)")
            st.button("Do what Sir Humphrey says", on_click=_apply, args=(rec,))
    if go_btn:
        old_occ = (s["sentenced"][0] + s["remand"][0]) / s["places"][0]
        new, drawn = G.step(world, s, action, st.session_state["g_rng"])
        events = drawn[0]
        quips = [e[3] for e in G.EVENTS if e[0] in events]
        occ = (new["sentenced"][0] + new["remand"][0]) / new["places"][0]
        lost = "" if new["alive"][0] else str(new["lost_reason"][0])
        head, deck = humphrey.front_page(action, events, lost)
        line, _ = humphrey.react_quarter(action, new["backlog"].sum() - s["backlog"].sum(), occ)
        st.session_state["g_news"] = dict(
            q=new["q"], events=events, head=head, deck=deck, quip=" ".join(quips) or line, action=_describe(action),
            backlog0=s["backlog"].sum(), backlog=new["backlog"].sum(), occ0=old_occ, occ=occ,
            pop0=float(s["popularity"][0]), pop=float(new["popularity"][0]),
            over=bool(lost) or new["q"] >= G.QUARTERS)
        msg = f"**Quarter {new['q']}:** you chose {_describe(action)}. "
        if events:
            msg += "📰 **" + " · ".join(events).upper() + "**. "
        msg += (f"Backlog now {new['backlog'].sum():,.0f}, prisons at {occ:.1%}, "
                f"popularity {new['popularity'][0]:.0f}.")
        st.session_state["g_log"].append(msg)
        st.session_state["g_history"].append(dict(
            quarter=new["q"], backlog=new["backlog"].sum(), occupancy=occ, popularity=new["popularity"][0],
            budget=new["budget"][0], events=", ".join(events), action=_describe(action)))
        st.session_state["g_state"] = new
        st.session_state.pop("g_rec", None)
        st.session_state["g_phase"] = "news"
        st.rerun()


def _game_over(world, s):
    alive = bool(s["alive"][0])
    sc = float(G.score(world, s)[0])
    if alive:
        if not st.session_state.get("g_celebrated"):
            st.balloons()
            st.session_state["g_celebrated"] = True
        S.show(f'''<div class="qb-end"><div class="big win">🏆 RE-ELECTED!</div>
<p style="font-size:1.3rem">You survived to polling day. Score <b>{sc:,.0f}</b></p>
<p style="opacity:.8">cases cleared ÷ 50 + popularity × 10 + £m left</p></div>''')
    else:
        stamp = "SACKED" if "Sacked" in s["lost_reason"][0] else "PRISONS FULL"
        S.show(f'''<div class="qb-end"><div class="stampbox">{stamp}</div>
<p style="font-size:1.3rem;margin-top:28px">Your term ended in quarter {s["q"]}.</p>
<p><i>Sir Humphrey: "I did warn you, Minister. Several times. In writing."</i></p></div>''')
    seed = st.session_state["g_seed"]
    with st.spinner("Replaying your exact run of events with the Autopilot..."):
        auto = G.play(world, "Autopilot", seed)
    st.write(f"On **your exact sequence of events**, Sir Humphrey's Autopilot "
             f"{'survived' if auto['survived'] else 'lost'} with a score of **{auto['score']:,.0f}** "
             f"and {auto['backlog']:,.0f} cases waiting.")
    if not st.session_state["g_saved"]:
        name = st.text_input("Your name for the leaderboard")
        if st.button("Save score") and name:
            row = pd.DataFrame([dict(name=name[:30], score=round(sc), survived=alive,
                                     backlog=round(s["backlog"].sum()), autopilot=round(auto["score"]))])
            row.to_csv(LEADERBOARD, mode="a", header=not LEADERBOARD.exists(), index=False)
            st.session_state["g_saved"] = True
            st.rerun()
    if LEADERBOARD.exists():
        st.markdown("#### 🏆 Leaderboard")
        st.dataframe(pd.read_csv(LEADERBOARD).sort_values("score", ascending=False).head(10),
                     hide_index=True, width="stretch")
    if st.button("🔁 Play again", type="primary"):
        _new_game(seed=int(np.random.default_rng().integers(1, 10_000)))
        st.session_state["g_phase"] = "title"
        st.session_state.pop("g_celebrated", None)
        st.rerun()


def _charts():
    h = pd.DataFrame(st.session_state["g_history"])
    c1, c2, c3 = st.columns(3)
    fig = go.Figure(go.Scatter(x=h["quarter"], y=h["backlog"], mode="lines+markers"))
    fig.update_layout(title="Cases waiting", height=250, margin=dict(l=10, r=10, t=40, b=10))
    c1.plotly_chart(fig, width="stretch")
    fig = go.Figure(go.Scatter(x=h["quarter"], y=h["occupancy"], mode="lines+markers"))
    fig.add_hline(y=1.0, line_dash="dash", line_color="red")
    fig.update_layout(title="Prison occupancy", yaxis_tickformat=".0%", height=250, margin=dict(l=10, r=10, t=40, b=10))
    c2.plotly_chart(fig, width="stretch")
    fig = go.Figure(go.Scatter(x=h["quarter"], y=h["popularity"], mode="lines+markers"))
    fig.update_layout(title="Popularity", height=250, margin=dict(l=10, r=10, t=40, b=10))
    c3.plotly_chart(fig, width="stretch")
    with st.expander("Your term so far"):
        st.dataframe(h, hide_index=True, width="stretch")


def render_benchmark(path):
    """Screen-4 panel: Autopilot vs simple strategies across simulated futures."""
    if not Path(path).exists():
        st.info("Run `python game.py` to compute the strategy benchmark.")
        return
    df = pd.read_csv(path)
    summ = (df.groupby("policy").agg(**{"Survived to election": ("survived", "mean"),
                                        "Mean score": ("score", "mean"),
                                        "Median cases waiting at the end": ("backlog", "median")})
            .sort_values("Mean score", ascending=False))
    st.subheader("Sir Humphrey's Autopilot vs simple strategies")
    st.caption(f"Each strategy plays the same {df['seed'].nunique()} random futures (events and noise).")
    fig = go.Figure(go.Bar(x=summ.index, y=summ["Survived to election"], text=[f"{v:.0%}" for v in summ["Survived to election"]]))
    fig.update_layout(yaxis_tickformat=".0%", yaxis_title="Survived to the election", height=300,
                      margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width="stretch")
    st.dataframe(summ.style.format({"Survived to election": "{:.0%}", "Mean score": "{:,.0f}",
                                    "Median cases waiting at the end": "{:,.0f}"}), width="stretch")

"""Look and feel: House of Commons green leather, brass, and tabloid front pages.
All CSS and HTML snippets live here so the game logic stays readable."""
import html

import plotly.io as pio
import streamlit as st

GOLD, RED, GREEN, PAPER, INK = "#d4a93a", "#c8102e", "#3fae6a", "#f4ecd8", "#1b1b1b"

# Charts: transparent backgrounds so the green leather shows through.
pio.templates["qb"] = pio.templates["plotly_dark"]
pio.templates["qb"].layout.update(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.18)",
                                  font=dict(family="Georgia, serif", color="#f1e8d0"),
                                  colorway=[GOLD, "#7fb8e6", RED, GREEN, "#c9a0dc"])
pio.templates.default = "qb"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=UnifrakturMaguntia&family=Special+Elite&display=swap');

[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(ellipse at top, rgba(255,255,255,0.07), transparent 60%),
    repeating-linear-gradient(45deg, rgba(0,0,0,0.05) 0 2px, transparent 2px 9px),
    linear-gradient(160deg, #134b34 0%, #0e2a1f 55%, #08170f 100%);
  background-attachment: fixed;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #3a0d12, #1d0608);
  border-right: 3px solid #d4a93a;
}
h1, h2, h3, h4 { font-family: 'Playfair Display', Georgia, serif !important; letter-spacing: .5px; }

/* brass buttons */
button[data-testid="stBaseButton-primary"], .stButton button[kind="primary"] {
  background: linear-gradient(180deg, #f0cf6b, #b8892a) !important; color: #2a1a00 !important;
  border: 2px solid #7a5a12 !important; font-weight: 800 !important; font-size: 1.1rem !important;
  box-shadow: 0 4px 0 #6b4e0e, 0 6px 14px rgba(0,0,0,.45); transition: transform .08s;
}
button[data-testid="stBaseButton-primary"]:hover { transform: translateY(-2px); filter: brightness(1.08); }
button[data-testid="stBaseButton-primary"]:active { transform: translateY(3px); box-shadow: 0 1px 0 #6b4e0e; }

/* cards */
.qb-card { background: rgba(8,23,15,.72); border: 1px solid rgba(212,169,58,.45); border-radius: 14px;
  padding: 14px 16px; box-shadow: 0 6px 20px rgba(0,0,0,.35); animation: rise .5s ease-out both; }
.qb-stat .lab { font-size: .8rem; text-transform: uppercase; letter-spacing: 1.5px; opacity: .75; }
.qb-stat .val { font-family: 'Playfair Display', serif; font-size: 2rem; font-weight: 900; line-height: 1.1; }
.qb-stat .sub { font-size: .85rem; opacity: .85; }
.qb-bar { height: 10px; border-radius: 6px; background: rgba(255,255,255,.12); overflow: hidden; margin-top: 6px; }
.qb-bar > div { height: 100%; border-radius: 6px; animation: grow 1s ease-out both; transform-origin: left; }
.qb-danger { border-color: #c8102e; animation: rise .5s ease-out both, alarm 1s ease-in-out infinite; }

/* title screen */
.qb-title { text-align: center; padding: 6vh 0 2vh; }
.qb-title .crest { font-size: 5rem; animation: swing 3s ease-in-out infinite; display: inline-block; }
.qb-title h1 { font-size: clamp(2.6rem, 8vw, 5.5rem) !important; color: #d4a93a; margin: 0;
  text-shadow: 0 4px 0 #5a3d06, 0 10px 30px rgba(0,0,0,.6); animation: drop .9s cubic-bezier(.2,1.6,.4,1) both; }
.qb-title .tag { font-family: 'Special Elite', monospace; font-size: 1.2rem; opacity: 0;
  animation: fade 1s .8s forwards; }
.qb-letter { max-width: 640px; margin: 3vh auto; background: #f4ecd8; color: #1b1b1b; padding: 26px 30px;
  font-family: 'Special Elite', monospace; border-radius: 4px; box-shadow: 0 16px 40px rgba(0,0,0,.55);
  transform: rotate(-1deg); animation: rise .8s 1.2s ease-out both; position: relative; }
.qb-letter .seal { position: absolute; right: 18px; bottom: -22px; width: 70px; height: 70px; border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, #e0404f, #8b0a1a); color: #f4ecd8; display: flex;
  align-items: center; justify-content: center; font-size: 1.8rem; box-shadow: 0 4px 10px rgba(0,0,0,.5);
  animation: stamp .5s 2s cubic-bezier(.3,1.8,.5,1) both; }

/* countdown ribbon */
.qb-ribbon { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap;
  background: linear-gradient(90deg, #8b0a1a, #c8102e 50%, #8b0a1a); color: #fff; padding: 8px 18px;
  border-radius: 10px; font-family: 'Playfair Display', serif; font-weight: 700; margin-bottom: 10px;
  box-shadow: 0 4px 14px rgba(0,0,0,.4); }
.qb-ribbon .dots span { display: inline-block; width: 13px; height: 13px; border-radius: 50%; margin: 0 2px;
  background: rgba(255,255,255,.25); border: 1px solid rgba(255,255,255,.6); }
.qb-ribbon .dots span.done { background: #d4a93a; border-color: #d4a93a; }
.qb-ribbon .dots span.now { background: #fff; animation: pulse 1s ease-in-out infinite; }

/* newspaper interstitial */
.qb-paper { max-width: 820px; margin: 2vh auto 1vh; background: #f4ecd8; color: #1b1b1b; padding: 18px 30px 26px;
  box-shadow: 0 20px 60px rgba(0,0,0,.6); animation: spin-in .9s cubic-bezier(.2,.9,.3,1.1) both; }
.qb-paper .mast { font-family: 'UnifrakturMaguntia', serif; font-size: clamp(2.2rem, 6vw, 3.8rem); text-align: center;
  border-bottom: 4px double #1b1b1b; line-height: 1.1; }
.qb-paper .dateline { display: flex; justify-content: space-between; font-size: .8rem; text-transform: uppercase;
  letter-spacing: 1px; border-bottom: 1px solid #1b1b1b; padding: 4px 0; margin-bottom: 12px; }
.qb-paper .head { font-family: 'Playfair Display', serif; font-weight: 900; font-size: clamp(1.8rem, 5vw, 3rem);
  line-height: 1.05; text-transform: uppercase; animation: slam .6s .6s cubic-bezier(.3,1.6,.5,1) both; }
.qb-paper .deck { font-style: italic; font-size: 1.1rem; margin: 8px 0 14px; }
.qb-paper .cols { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; border-top: 1px solid #1b1b1b;
  padding-top: 10px; }
.qb-paper .cols div { font-size: .95rem; }
.qb-paper .cols b { font-family: 'Playfair Display', serif; font-size: 1.5rem; display: block; }
.qb-paper .up { color: #c8102e; } .qb-paper .down { color: #1d7a45; }
.qb-paper .quote { margin-top: 14px; padding: 10px 14px; background: rgba(0,0,0,.06); border-left: 4px solid #1b1b1b;
  font-family: 'Special Elite', monospace; }
.qb-paper .event { display: inline-block; background: #c8102e; color: #fff; font-weight: 800; padding: 2px 10px;
  margin: 0 6px 6px 0; transform: rotate(-2deg); animation: stamp .4s 1s both; }

/* end screens */
.qb-end { text-align: center; padding: 4vh 0 1vh; }
.qb-end .big { font-family: 'Playfair Display', serif; font-weight: 900; font-size: clamp(2.6rem, 9vw, 6rem);
  line-height: 1; animation: slam .7s cubic-bezier(.3,1.6,.5,1) both; }
.qb-end .stampbox { display: inline-block; border: 8px solid #c8102e; color: #c8102e; padding: 6px 28px;
  transform: rotate(-8deg); font-family: 'Special Elite', monospace; font-size: clamp(2rem, 7vw, 4.5rem);
  font-weight: 900; background: rgba(244,236,216,.9); animation: stamp .6s .3s cubic-bezier(.3,1.8,.5,1) both; }
.qb-end .win { color: #d4a93a; text-shadow: 0 4px 0 #5a3d06, 0 0 40px rgba(212,169,58,.6); }

@keyframes rise   { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: none; } }
@keyframes fade   { to { opacity: .9; } }
@keyframes grow   { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes drop   { from { opacity: 0; transform: translateY(-80px) scale(1.2); } to { opacity: 1; transform: none; } }
@keyframes swing  { 0%,100% { transform: rotate(-8deg); } 50% { transform: rotate(8deg); } }
@keyframes pulse  { 0%,100% { transform: scale(1); } 50% { transform: scale(1.35); } }
@keyframes alarm  { 0%,100% { box-shadow: 0 0 0 rgba(200,16,46,0); } 50% { box-shadow: 0 0 24px rgba(200,16,46,.9); } }
@keyframes stamp  { from { opacity: 0; transform: scale(3) rotate(-8deg); } to { opacity: 1; transform: scale(1) rotate(-8deg); } }
@keyframes slam   { from { opacity: 0; transform: scale(1.8); } to { opacity: 1; transform: scale(1); } }
@keyframes spin-in { from { opacity: 0; transform: rotate(-540deg) scale(.05); } to { opacity: 1; transform: rotate(-1deg) scale(1); } }
@media (max-width: 640px) { .qb-paper .cols { grid-template-columns: 1fr; } }
</style>
"""

esc = html.escape


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


def show(snippet):
    st.markdown(snippet, unsafe_allow_html=True)


def stat(label, value, sub="", bar=None, bar_color=GOLD, danger=False):
    bar_html = (f'<div class="qb-bar"><div style="width:{min(max(bar, 0), 1) * 100:.0f}%;background:{bar_color}"></div></div>'
                if bar is not None else "")
    return (f'<div class="qb-card qb-stat{" qb-danger" if danger else ""}"><div class="lab">{esc(label)}</div>'
            f'<div class="val">{esc(value)}</div><div class="sub">{sub}</div>{bar_html}</div>')


def ribbon(q, total):
    dots = "".join(f'<span class="{"done" if i < q else "now" if i == q else ""}"></span>' for i in range(total))
    left = total - q
    return (f'<div class="qb-ribbon"><div>🗳️ {left} quarter{"s" if left != 1 else ""} to the election</div>'
            f'<div class="dots">{dots}</div></div>')

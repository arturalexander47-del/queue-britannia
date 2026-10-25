# Queue Britannia

A satirical "you are the Justice Secretary" simulator with a serious forecasting engine inside.

```
pip install -r requirements.txt
streamlit run app.py
```

It now runs on **real MoJ data** in `data/`, built from the official downloads in `raw/` by
`python build_data.py`: 70 Crown Courts, quarterly from 2016 to Apr–Jun 2026, plus prison figures to 7 Sep 2026.
If `data/` is missing, the app falls back to synthetic demo data and shows a yellow banner.

| File | What it does | Owner |
|---|---|---|
| `data.py` | Loads `data/*.csv` or generates demo data. CSV schemas are in the docstring. | A |
| `crack_model.py` | Beta-binomial crack-rate model with regional shrinkage, walk-forward backtest vs baselines, Monte Carlo overbooking curve, synthetic case cards | B |
| `simulation.py` | Weekly Monte Carlo: backlog → wait (Little's law) → remand → prison occupancy, policy levers, hindcast | C |
| `humphrey.py` | Sir Humphrey lines, tabloid headlines, career-survival meter (templates, or Claude if `ANTHROPIC_API_KEY` is set) | D |
| `game.py` | Survive to the Election: quarterly game engine, random events, Sir Humphrey's Autopilot (Monte Carlo optimiser), benchmark (`python game.py` refreshes `data/benchmark.csv`) | B/C |
| `style.py` | Look and feel: background, fonts, animations, title and newspaper screens | D |
| `game_tab.py` | The game screen and leaderboard | D |
| `app.py` | Three sidebar pages: Play, Explore the data, How we know it works | D |
| `config.py` | Every assumption. Replace each **PLACEHOLDER** with a sourced figure. | All |

## How to play

Open the app: it starts on **Play the game** (pages are in the left sidebar). Each of 12 quarters you split the budget between courtrooms, fixes, overbooking and prison places, then click **End the quarter**. Random events hit you. You lose if prisons fill up or popularity hits 5. Click **Ask Sir Humphrey** for the Autopilot's plan. At the end it replays your exact events to show what it would have scored. All costs and game rules marked ILLUSTRATIVE in `game.py` need sourcing.

## Where the data comes from

| File | Source |
|---|---|
| `raw/cc_rdos_tool.xlsx` | MoJ Criminal court statistics quarterly, Apr–Jun 2026: Crown Court receipts, disposals and open cases tool |
| `raw/trials_tool.xlsx` | Same release: Trial effectiveness at the criminal courts tool |
| `raw/prison-pop-7-sept-2026.ods` | HMPPS weekly prison population bulletin, 7 Sep 2026 (also gives 8 Sep 2025) |
| remand figures | Offender Management Statistics Quarterly, Jan–Mar 2026 bulletin (remand 15,386 at 30 Jun 2026) |

The Minister's Desk can run any region on its own and lists its courts. Fixes (more barristers, video links,
better case preparation) work on the recorded reasons trials were ineffective. How much each fix prevents, and
what it costs, are assumptions in `config.py` (FIXES), and the sliders say so.

Known limits: sitting days by court aren't in these tools, so court capacity is measured by disposals.
Weekly prison figures between the published dates are interpolated (see `data/prison_sources.csv`).
To refresh, replace the files in `raw/` with newer releases and re-run `python build_data.py`.

## Sanity checks before the demo

- Screen 4: the model beats both baselines, and interval coverage is near 80%.
- Hindcast error is reasonable. If not, check sitting days and disposals.
- Every PLACEHOLDER in `config.py` has a source.

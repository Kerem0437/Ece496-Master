# ECE496 poster figure kit

This folder is a small, simple add-on for your existing repo.

It was made to address the poster feedback about:
- using **white-background graphs**
- making the figure generation more repeatable
- keeping the data source simple and local

## What is inside

- `build_poster_data.py` reads the current demo CSVs and ML summary files from the repo and builds `poster_data.json` + `poster_data.js`
- `poster_figures.html` is a lightweight local page that renders clean figures from that data
- `generate_poster_figures.py` exports three white-background PNG figures into `output/`

## Suggested folder placement

Drop this folder next to your repo root, then copy `Ece496-Master/` into this folder or update the `REPO` path at the top of `build_poster_data.py`.

## Fast usage

1. Put the `Ece496-Master` repo inside this folder.
2. Run:
   - `python build_poster_data.py`
   - `python generate_poster_figures.py`
3. Open `poster_figures.html` in a browser.

For direct browser loading, `poster_figures.html` uses `poster_data.js`, so you do **not** need a complex app server.

## Output files

- `output/figure_signal_overview.png`
- `output/figure_lstm_overlay.png`
- `output/figure_status_summary.png`

These are ready to drop into a poster or PowerPoint.

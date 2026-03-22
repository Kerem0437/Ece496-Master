# Dashboard

See `../MASTER_RUNBOOK.md` for the full runbook.

Key environment variables:
- `DATA_MODE=demojson` (offline) or `DATA_MODE=influx` (live)
- `ML_SERVICE_URL=http://127.0.0.1:8000`

Live rolling behavior (DATA_MODE=influx):
- charts refresh every `NEXT_PUBLIC_LIVE_CHART_REFRESH_SECONDS` and show last `NEXT_PUBLIC_LIVE_CHART_WINDOW_MINUTES`
- ML refresh every `NEXT_PUBLIC_LIVE_SCORE_REFRESH_SECONDS` and scores last `NEXT_PUBLIC_LIVE_SCORE_WINDOW_MINUTES`


Live archive notes:
- The live API saves rolling measurement windows and ML results under `dashboard/live_captures/<experiment_id>/`.
- By default both charts and ML refresh every 120 seconds, matching the 2-minute archive cadence.

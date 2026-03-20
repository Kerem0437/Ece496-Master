# Dashboard

See `../MASTER_RUNBOOK.md` for the full runbook.

Key environment variables:
- `DATA_MODE=demojson` (offline) or `DATA_MODE=influx` (live)
- `ML_SERVICE_URL=http://127.0.0.1:8000`

Live rolling behavior (DATA_MODE=influx):
- charts refresh every `NEXT_PUBLIC_LIVE_CHART_REFRESH_SECONDS` and show last `NEXT_PUBLIC_LIVE_CHART_WINDOW_MINUTES`
- ML refresh every `NEXT_PUBLIC_LIVE_SCORE_REFRESH_SECONDS` and scores last `NEXT_PUBLIC_LIVE_SCORE_WINDOW_MINUTES`

# ECE496 Master Repo

Start here → **MASTER_RUNBOOK.md**

- Connect (VPN + tunnels)
- Run LIVE pipeline (Pi → MQTT → Influx)
- Train LSTM from `demo/data`
- Serve ML to dashboard **without DB writes**
- Run dashboard in DEMO and LIVE modes
- Rolling live view (2-minute charts + periodic ML scoring + per-sensor flags)

Quickstart:
1) Train + run ML service:
   - `cd ml_service`
   - `python -m venv .venv && activate`
   - `pip install -r requirements.txt`
   - `python train.py --data-dir ../demo/data`
   - `uvicorn server:app --host 127.0.0.1 --port 8000`
2) Run dashboard (demo):
   - set `DATA_MODE=demojson` in `dashboard/.env`
   - `cd dashboard && npm install && npm run dev`

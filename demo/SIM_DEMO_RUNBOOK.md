# Demo mode pipeline (offline) (backup recording)

This is an **offline simulation** that prints realistic logs and updates `dashboard/demo-json/` so the UI changes on refresh.

## Run dashboard (Terminal 1)
```bash
cd dashboard
cp .env.example .env   # Windows: copy .env.example .env
# set: DATA_MODE=demojson
npm install
npm run dev
```
Open: http://localhost:3000/experiments

## Run simulator (Terminal 2)
```bash
cd demo
py demo_realtime_demo.py --duration 30
```
Refresh the browser once or twice while recording to show ml_flag/anomaly_score changes.

> NOTE: This is clearly labeled DEMO MODE MODE (no MQTT/Influx connection).

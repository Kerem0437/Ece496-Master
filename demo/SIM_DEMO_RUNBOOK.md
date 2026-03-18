# Demo mode pipeline (offline)

This runs a **demo mode** pipeline that prints live logs and updates `dashboard/demo-json/` so the dashboard changes on refresh.

## Terminal 1: dashboard
```bash
cd dashboard
cp .env.example .env   # Windows: copy .env.example .env
# set: DATA_MODE=demojson
npm install
npm run dev
```
Open: http://localhost:3000/experiments

## Terminal 2: demo mode logs + updates
```bash
cd demo
py demo_realtime.py --duration 30 --interval 2
```
Refresh the browser once or twice while recording.

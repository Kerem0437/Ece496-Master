# Water Dashboard (T1–T5 Scaffold)

A Vercel-deployable Next.js (App Router) scaffold for a water-quality / spectrometer dashboard.
This version is **mock-data only** and intentionally stops at **T5** (no DB/API integration yet).

## Dashboard Scope (T1)

### What this dashboard is (concept)
The dashboard is the UI layer on top of a secure edge-to-cloud pipeline:

**Pi (edge device)** → **MQTT broker** → **DB (InfluxDB on VM2)** → **ML (LSTM)** → **Dashboard**

Ultimately, this UI will show:
- experiment runs and drill-down details
- time-series curves (spectrometer / sensors)
- experiment metadata (device_id, timestamps, sensor types)
- chain-of-custody / integrity status (hash/signature/cert + derived status)
- ML (LSTM) outputs (anomaly score + flags + model version)

### What pages exist (T4–T5)
1) **Experiments List** (`/experiments`)
   - Browse recent experiments (mock)
   - Filter by device, integrity, ML flag, and time window
   - Click into a run

2) **Experiment Detail** (`/experiments/[experiment_id]`)
   - Header info (device, timestamps, duration, site)
   - Integrity status + custody fields (mock)
   - ML outputs (mock)
   - Time-series visualization placeholder (lightweight SVG line)
   - Raw measurement rows (with “show more”)

### What’s mock now vs. real later
**Mock now (T1–T5):**
- All data comes from `lib/data/mockData.ts`.
- Derived metrics (duration, freshness, min/max/mean) computed in frontend helpers.

**Real later (T6+):**
- Replace mock layer with DB/API integration.
- Keep the same variable names so components don’t need rewrites.

## T2 Design note
Figma design is explicitly omitted for now.
This UI is a functional scaffold to support reviews and integration later.

## Vercel Deployment (T3)

### Deploy
1. Push this repo to GitHub (or other git provider).
2. In Vercel: **New Project** → Import repo.
3. Framework should auto-detect **Next.js**.
4. Build command: `npm run build`
5. Output: default (Next.js)
6. Deploy.

No special `vercel.json` is required.

### Run locally
```bash
npm install
npm run dev


## Real DB mode (Influx + ML)
This dashboard now supports **DATA_MODE=influx**.

1) `cp .env.example .env`
2) Set:
   - `INFLUX_URL=http://<VM1_IP>:8086`
   - `INFLUX_QUERY_TOKEN=<READ_TOKEN>`
3) `npm run dev`

It will query:
- `mqtt_sensor` for raw sensor curves
- `ml_summary` for LSTM outputs (ml_flag/anomaly_score)

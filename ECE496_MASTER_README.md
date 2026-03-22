# ECE496 Master README

This document is the single source of truth for the ECE496 capstone repo: architecture, machine access, data flow, ML behavior, training, dashboard modes, live demo behavior, report generation, and troubleshooting.

It consolidates the uploaded runbooks and the later project decisions made during debugging and model redesign.

---

## 1) Project purpose

Build an end-to-end water-analysis monitoring system with two operating modes:

- **Offline demo mode** for reproducible testing from stored datasets
- **Live mode** for real sensor data streaming from the Raspberry Pi through the broker and database into the dashboard and ML review pipeline

### What the system is meant to do

- collect sensor measurements
- preserve data flow from edge to cloud
- visualize experiments on a dashboard
- run ML-based **data-quality / sensor-anomaly verification**
- flag suspicious runs when observed data deviates from expected per-variable behavior

### What the ML is **not** meant to do

- it is **not** a water contamination classifier
- it should **not** assume “tap water = good” and “everything else = bad”
- it is a **sensor/data verification model** that looks for anomalies such as spikes, gaps, dropouts, impossible jumps, zero-drops, and strong mismatch between observed values and model-based reconstruction

---

## 2) High-level architecture

### LIVE path

**Raspberry Pi → VM1 (Mosquitto broker) → VM2 (InfluxDB) → ML service (read-only) → Dashboard**

### DEMO path

**Demo JSON / CSV files → Dashboard → ML service → Dashboard UI**

### Important design rule

The ML service is **read-only** with respect to the database.

- it reads recent measurements
- scores them
- returns `ml_flag`, `anomaly_score`, per-feature verification results, and predicted curves
- it does **not** write ML results back into InfluxDB

---

## 3) Current ML design (authoritative behavior)

### 3.1 One model per variable

The ML pipeline is designed around **separate models per variable**, not one shared model for every channel.

Examples:
- turbidity model
- pH model
- water temperature model
- air temperature model

This matters because each variable has a different shape, scale, drift pattern, and failure mode.

### 3.2 Gap-fill verification logic

The core idea is **partial observation + prediction of hidden points**.

For a variable with `N` total points:
- the model is given only part of the raw series
- the hidden part is predicted
- the prediction is compared against the actual hidden points
- if the mismatch is too large, that variable is marked suspicious

This is the intended meaning of “actual vs predicted.”

### 3.3 Review modes

The current intended review modes are:

- **Normal mode:** keep **90%** of the raw points, hide and predict **10%**
- **Strict mode:** keep **75%** of the raw points, hide and predict **25%**

Both modes are compared against the same raw timestamps so the predicted curve should look like a **smoothed approximation** of the real signal, not a stitched staircase or repeated-window artifact.

### 3.4 How suspicious status should work

A variable becomes suspicious when one or more of the following are true:

- prediction error against hidden points is too high
- zero-drop fault is detected in a monitored variable
- a sharp impossible jump or dropout occurs
- normal mode and strict mode both fail with sufficiently high error

The suspicious threshold should be **loose enough** that visually similar curves are not incorrectly flagged as suspicious.

### 3.5 Verification labels

The dashboard should not leave reviewed data as `UNKNOWN` once ML has run successfully.

Expected behavior:
- before ML review: `UNKNOWN`
- after successful ML review with valid pipeline execution: `VERIFIED`
- if anomaly conditions are met: overall `SUSPICIOUS`

In other words:
- `verification_status` reflects whether the data was actually reviewed
- `ml_flag` / per-feature flags reflect whether the reviewed result is normal or suspicious

### 3.6 Live zero-drop protection

In live mode, if a monitored signal such as turbidity suddenly drops to `0`, that should immediately contribute to a suspicious decision.

This is intended as a fast safety rule independent of the slower model-based comparison.

---

## 4) Dashboard behavior

### 4.1 Offline demo mode

The dashboard reads from the local demo dataset and shows:
- experiments list
- experiment details
- actual raw data
- ML predicted reconstructions
- per-feature verification results
- overall status and anomaly score

### 4.2 Live mode

When live mode is enabled, the dashboard should:

1. start collecting incoming data for the active experiment
2. save live data dynamically to a local archive folder
3. refresh the dashboard every **2 minutes**
4. rerun the ML review every **2 minutes**
5. reflect updated results on the dashboard

### 4.3 Live archive behavior

In live mode, the dashboard server should save measurement windows and ML results under a folder such as:

```text
/dashboard/live_captures/<experiment_id>/
```

Each update cycle should archive:
- the measurement window used for the refresh
- the ML result for that cycle

### 4.4 Chart behavior

For each modeled variable, the dashboard should show side-by-side charts aligned to the **same timestamps**:

- **Actual**
- **Predicted (normal)**
- **Predicted (strict)**

Do not print ratio labels in titles like `(normal 75/25)`.
Use cleaner labels such as:
- `Predicted (normal)`
- `Predicted (strict)`

The predicted curves must visually read as smooth approximations of the actual series.

### 4.5 Verification note on the detail page

The experiment page should include a small explanatory note stating that verification is based on:
- gap-fill prediction error
- per-variable review
- jump / dropout checks
- zero-drop checks for live monitored channels

---

## 5) Demo report requirements

The local demo output should be **truthful to the trained model currently in use**.

`demo_report.html` should be generated from the same per-variable models used by the live service, not from placeholder logic.

The report should include, where available:
- training loss curves
- validation metrics
- confusion matrix or equivalent classification-style summary for suspicious vs normal review outcomes
- example actual vs predicted overlays
- clean vs suspicious case summaries
- per-feature review summaries

It should be locally hostable, for example:

```bash
cd demo
python demo_onefile.py --out demo_report.html
python -m http.server 8765
```

Then open:

```text
http://127.0.0.1:8765/demo_report.html
```

---

## 6) Machine access and network info

### VM1 (broker VM)
- Public IP: `128.100.23.125`
- SSH: `ssh -p 3245 cenit@128.100.23.125`
- Local IP: `192.168.56.108`
- MQTT internet port: `11883`

### VM2 (database/backend VM)
- Public IP: `128.100.23.125`
- SSH: `ssh -p 3246 cenit@128.100.23.125`
- Local IP: `192.168.56.110`

### Credentials
- user: `cenit`
- password: `cap25stone`

### Constraint
VM1 and VM2 should communicate over their **local network IPs**, not over the public internet path.

### Pi data location
- `/home/raspberry/ece496/data`

---

## 7) Required connectivity before LIVE

Before attempting live mode, make sure:
- ECE VPN is connected
- Tailscale is connected if needed for Pi access

---

## 8) LIVE pipeline runbook

### 8.1 VM2: verify InfluxDB
```bash
sudo systemctl status influxdb
```
If needed:
```bash
sudo systemctl start influxdb
```

### 8.2 VM1: run MQTT → Influx bridge
```bash
python3 mqtt_to_influx.py
```
If HMAC mismatch occurs:
```bash
export MQTT_HMAC_KEY='pi'
```

### 8.3 VM1: verify Mosquitto
```bash
sudo systemctl status mosquitto
```
If needed:
```bash
sudo systemctl restart mosquitto
```

### 8.4 Pi: run publisher
```bash
source venv/bin/activate
sudo -E venv/bin/python3 merge.py
```
Then set broker and run:
```text
setbroker 100.118.44.46 1883
run
```

---

## 9) Tunnels and validation

### Verify broker port reachable
```bash
nc -vz 100.118.44.46 1883
```

### Tunnel MQTT to laptop if needed
```bash
ssh -N -L 1883:192.168.56.108:1883 -p 3245 cenit@128.100.23.125
```

### Tunnel Influx UI to laptop
```bash
ssh -N -L 8086:127.0.0.1:8086 -p 3246 cenit@128.100.23.125
```

Influx UI:
- URL: `http://localhost:8086`
- user: `mtuilisa`
- password: `cap25stone`
- bucket: `capstone`

---

## 10) Training the ML models

### 10.1 Setup
```bash
cd ml_service
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 10.2 Clean retrain
If retraining from scratch, delete old artifacts:

- `ml_service/artifacts/model.pt`
- `ml_service/artifacts/scaler.json`
- `ml_service/artifacts/calibration.json`
- `ml_service/artifacts/feature_models/`
- `ml_service/artifacts/manifest.json`

### 10.3 Train
```bash
python train.py --data-dir ../demo/data --epochs 12 --seq-len 60 --stride 10
```

### 10.4 Expected artifacts
- `ml_service/artifacts/manifest.json`
- `ml_service/artifacts/feature_models/<feature>/model.pt`
- `ml_service/artifacts/feature_models/<feature>/scaler.json`
- `ml_service/artifacts/feature_models/<feature>/calibration.json`

---

## 11) Running the ML service

Start the service:
```bash
cd ml_service
uvicorn server:app --host 127.0.0.1 --port 8000
```

Health check:
```text
http://127.0.0.1:8000/health
```

Expected behavior:
- dashboard calls succeed locally
- service returns `ml_flag`, `anomaly_score`, per-feature results, and predicted series
- terminal logs should clearly report the review result in human-readable language, for example:
  - `Data successfully tuned against model for <experiment_id>; result=NORMAL`
  - or the equivalent suspicious result

---

## 12) Running the dashboard

### 12.1 Demo mode
`dashboard/.env`
```env
DATA_MODE=demojson
ML_SERVICE_URL=http://127.0.0.1:8000
```

Run:
```bash
cd dashboard
npm install
npm run dev
```

### 12.2 Live mode
`dashboard/.env`
```env
DATA_MODE=influx
ML_SERVICE_URL=http://127.0.0.1:8000
INFLUX_URL=http://127.0.0.1:8086
INFLUX_ORG=ECE496
INFLUX_BUCKET=capstone
INFLUX_QUERY_TOKEN=Iu8HJpcELmA79_rBrIPFmCsD6hHb6KzrMDrRiGlq5A6UbTZqVVZBNY2gFvtWpyMw800o4fwz3QdsL_uz8jSeSg==
INFLUX_MEASUREMENT=mqtt_sensor
NEXT_PUBLIC_LIVE_CHART_WINDOW_MINUTES=2
NEXT_PUBLIC_LIVE_SCORE_WINDOW_MINUTES=5
NEXT_PUBLIC_LIVE_CHART_REFRESH_SECONDS=120
NEXT_PUBLIC_LIVE_SCORE_REFRESH_SECONDS=120
NEXT_PUBLIC_LIVE_LIST_REFRESH_SECONDS=120
```

Then:
```bash
cd dashboard
npm run dev
```

---

## 13) Repo verification and debugging

### Windows (PowerShell)
```powershell
.\scripts\verify_repo.ps1
.\scripts\verify_repo.ps1 -Full
```

### macOS/Linux
```bash
./scripts/verify_repo.sh
./scripts/verify_repo.sh --full
```

### Optional debug logging
Windows:
```powershell
set LOG_LEVEL=DEBUG
```
macOS/Linux:
```bash
export LOG_LEVEL=DEBUG
```

### Common failure checks

#### Dashboard says missing Influx token
Set `INFLUX_QUERY_TOKEN` in `dashboard/.env` for live mode.

#### Demo mode shows zero experiments
Check:
- `DATA_MODE=demojson`
- `dashboard/demo-json/experiments.json` exists

#### Live mode shows no data
Check:
- VPN connected
- Influx tunnel running
- InfluxDB active on VM2

#### MQTT path broken
Check:
- Mosquitto active on VM1
- Pi broker IP correct
- broker port reachable

#### ML flags everything suspicious
Check:
- retrain models from mixed demo data
- inspect per-feature error metrics
- verify thresholds are not too strict

---

## 14) Repo structure at a glance

Suggested important directories:

```text
/dashboard
/ml_service
/demo
/scripts
```

Typical responsibilities:
- `dashboard/` → Next.js UI, experiment pages, live polling, dashboard API routes
- `ml_service/` → training, serving, per-feature model artifacts
- `demo/` → reproducible demo datasets and local HTML report generation
- `scripts/` → repository verification and smoke tests

---

## 15) Recommended demo-day sequence

### Preferred live demo
1. Pi publishes live data
2. broker and bridge move data into Influx
3. dashboard updates every 2 minutes
4. ML reruns every 2 minutes
5. suspicious or verified status updates on-screen

### Backup demo
Have a local recorded or reproducible demo showing:
- dashboard pages
- ML status transitions
- normal vs suspicious examples
- terminal logs
- generated local report

---

## 16) Notes on versioning and compatibility

- Next.js was pinned to `14.2.35` in the project notes to address prior issues and security warnings.
- If the dashboard route handling breaks after upgrades, reinstall dependencies cleanly before debugging app logic.

---

## 17) Final operational summary

This repo supports:
- offline reproducible demo mode
- live streaming mode
- per-variable ML verification
- normal and strict gap-fill review
- zero-drop live fault checks
- side-by-side actual vs predicted plots
- truthful local demo report generation

If you only remember one workflow, use this:

1. connect VPN / tunnels
2. train models if needed
3. run ML service
4. run dashboard
5. for live mode, start Pi + bridge + Influx
6. verify the dashboard updates every 2 minutes and ML review reruns automatically


\
# ECE496 Master Runbook (Connect → Train → Run → Demo)

This is the single “master” document for:
- connecting to VM1/VM2/Pi (VPN + tunnels)
- running the live pipeline (Pi → MQTT → Influx)
- training the LSTM (from `demo/data`)
- serving ML to the dashboard **without DB writes**
- running the dashboard in **DEMO** and **LIVE** modes
- live demo behavior (rolling charts + periodic ML scoring)

> **Model scope (team agreement):** ML is **anomaly detection of bad sensor/data** (spikes/dropouts/inconsistent readings).  
> It is **NOT** “water contamination detection” and should not default to “tap good / everything else bad”.

---

## 0) Project goals and non-goals

### Goal
Build an end-to-end system supporting:
1) **DEMO/Test data** (offline, reproducible)  
2) **LIVE data** (Pi → VM1 broker → VM2 Influx → ML → Dashboard)

Dashboard must support switching between demo and live sources.

### Non-goals (for now)
- No Vercel deployment (run locally; “hosted” = services running via code on laptop/VMs).
- No absorbance/wavelength integration required for live demo (ignored for stability).
- No water-quality classification (ML is anomaly detection of bad data/sensor faults).

---

## 1) Architecture (high-level)

**LIVE path**
Pi (publisher) → VM1 (mosquitto broker) → VM2 (InfluxDB) → ML Service (read-only) → Dashboard UI

**DEMO path**
Dashboard reads `dashboard/demo-json` → ML Service scores demo measurements → UI shows ml_flag/anomaly_score

**Key rule:** ML outputs are **served to dashboard via API** and are **NOT written back** to InfluxDB.

---

## 2) Machine access (VM1 / VM2) — from Morteza email

### VM1 (Broker VM)
- Public IP: `128.100.23.125`
- SSH: `ssh -p 3245 cenit@128.100.23.125`
- Internet MQTT port: `11883`
- Local network IP (VM↔VM): `192.168.56.108`

### VM2 (DB/backend VM)
- Public IP: `128.100.23.125`
- SSH: `ssh -p 3246 cenit@128.100.23.125`
- Local network IP (VM↔VM): `192.168.56.110`

Credentials (both):
- user: `cenit`
- password: `cap25stone`

**Important constraint:** VM1 and VM2 communicate via **local IPs only**; no intra-VM communication over internet.

### Raspberry Pi (data location)
- Raw/old files live on the Pi at:
  - `/home/raspberry/ece496/data`
- Live stream is visible on VM2 only when the Pi is actively transmitting:
  - Pi → VM1 → VM2

---

## 3) Prerequisites (before LIVE)
You must be connected to:
- **ECE VPN**
- **Tailscale** (if the Pi is only reachable there)

---

## 4) LIVE pipeline runbook (Pi → MQTT → Influx)

### 4.1 VM2: InfluxDB status
```bash
sudo systemctl status influxdb
```
If not running:
```bash
sudo systemctl start influxdb
```

### 4.2 VM1: bridge (MQTT → Influx writer)
Run:
```bash
python3 mqtt_to_influx.py
```
If HMAC mismatch:
```bash
export MQTT_HMAC_KEY='pi'
```
(Use the exact key the publisher uses.)

### 4.3 VM1: mosquitto status
```bash
sudo systemctl status mosquitto
```
If needed:
```bash
sudo systemctl restart mosquitto
```

### 4.4 Pi: publisher
Activate venv:
```bash
source venv/bin/activate
```
Run publisher with sudo env preserved:
```bash
sudo -E venv/bin/python3 merge.py
```
Point publisher to broker (example):
```text
setbroker 100.118.44.46 1883
run
```

---

## 5) VPN / tunnel debugging + validation

### 5.1 Verify broker port reachable
```bash
nc -vz 100.118.44.46 1883
```
Expected: `succeeded`

### 5.2 Tunnel MQTT to laptop (if networks split)
```bash
ssh -N -L 1883:192.168.56.108:1883 -p 3245 cenit@128.100.23.125
```

### 5.3 Tunnel Influx UI to laptop
```bash
ssh -N -L 8086:127.0.0.1:8086 -p 3246 cenit@128.100.23.125
```
Open:
- `http://localhost:8086`
- user: `mtuilisa`
- password: `cap25stone`
- bucket: `capstone`

---

## 6) ML: Train the LSTM (from `demo/data`)

### 6.1 Install dependencies
```bash
cd ml_service
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 6.2 Train
Training data lives in `demo/data`:
- tap water, rb water, fertilizer water, mb water (and optional 2020 placeholder)

Run training:
```bash
python train.py --data-dir ../demo/data --epochs 6 --seq-len 60 --stride 60
```

Artifacts saved to:
- `ml_service/artifacts/model.pt`
- `ml_service/artifacts/scaler.json`
- `ml_service/artifacts/calibration.json`

**Calibration now includes per-feature quantiles** so the service can output:
- overall anomaly score + flag
- **per-sensor anomaly scores + flags** (e.g., pH suspicious vs turbidity normal)

---

## 7) ML: Serve results to dashboard (NO DB writes)

Start the ML service:
```bash
cd ml_service
uvicorn server:app --host 127.0.0.1 --port 8000
```

Health check:
- `http://127.0.0.1:8000/health`

API endpoints:
- `GET /api/ml/<experiment_id>` (demojson scoring by experiment id)
- `POST /api/ml/score` (live mode: dashboard posts recent measurements; no DB writes)
- Responses include `ml_flag`, `anomaly_score`, and `per_feature` map.

---

## 8) Dashboard: DEMO vs LIVE mode

Dashboard runs locally on:
- `http://localhost:3000`

### 8.1 DEMO mode (offline)
`dashboard/.env`:
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

### 8.2 LIVE mode (Influx)
`dashboard/.env`:
```env
DATA_MODE=influx
ML_SERVICE_URL=http://127.0.0.1:8000
INFLUX_URL=http://127.0.0.1:8086
INFLUX_ORG=ECE496
INFLUX_BUCKET=capstone
INFLUX_QUERY_TOKEN=...   # query token (read-only)
INFLUX_MEASUREMENT=mqtt_sensor
```

Start the Influx tunnel first (section 5.3), then run:
```bash
cd dashboard
npm run dev
```

---

## 9) LIVE UI behavior (rolling windows + periodic ML)

When `DATA_MODE=influx`, the experiment detail page uses a **rolling live view**:

- **Charts** refresh every **60s** and show the **last 2 minutes** of data (x-axis spans ~120 seconds)
- **ML scoring** runs every **120s** on the **last 5 minutes** of data:
  - produces `ml_flag/anomaly_score`
  - produces **per-sensor flags** (e.g., “pH suspicious”)

These are configurable in `dashboard/.env`:
```env
NEXT_PUBLIC_LIVE_CHART_WINDOW_MINUTES=2
NEXT_PUBLIC_LIVE_SCORE_WINDOW_MINUTES=5
NEXT_PUBLIC_LIVE_CHART_REFRESH_SECONDS=60
NEXT_PUBLIC_LIVE_SCORE_REFRESH_SECONDS=120
NEXT_PUBLIC_LIVE_LIST_REFRESH_SECONDS=120
```

---

## 10) Demo-day expectations

### Live demo (preferred)
Show real-time:
Pi → VM1 broker → VM2 Influx → ML reads latest window → dashboard updates

### Backup demo (required)
Have a recording showing:
- dashboard running
- terminal logs
- normal vs suspicious case
- ignore absorbance/wavelength

---

## 11) Open items to confirm
1) Broker IP used by Pi for live: confirm `100.118.44.46` (from notes) or update.
2) Confirm service placement: mosquitto on VM1, influx on VM2.
3) Confirm query token setup for dashboard (read-only token recommended).


---

## Repo verification / debugging

Before demos, run the verifier:

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

### What it checks
- repo structure + missing files
- Python syntax (compileall)
- optional: 1-epoch training smoke test
- optional: Next build (`--run-build`)
- flags large files that can break uploads

Debug logging:
- Python: set `LOG_LEVEL=DEBUG` for verbose logs
- ML service logs every request with timing
- Dashboard API routes log each call

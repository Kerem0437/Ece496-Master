# ECE496 Full System Repo — Dashboard + ML (LSTM) + VM1/VM2 Integration

This is a **single GitHub-ready monorepo** that combines:
- **Dashboard (Next.js)**: `dashboard/`
- **ML + LSTM training/inference (Python)**: `ml-pipeline/`
- **VM1 bridge scripts** (MQTT → Influx): `vm1-bridge/`

## Architecture (matches your VM setup)
- **VM2**: MQTT broker (mosquitto) listening on **1883**
- **VM1**: InfluxDB listening on **8086**
- Flow:
  1) VM2 (publisher) → MQTT topic `demo/496/chat`
  2) VM1 (`vm1-bridge/mqtt_to_influx.py`) subscribes → writes `mqtt_sensor` points into Influx
  3) ML batch job reads `mqtt_sensor` → writes `ml_summary`
  4) Dashboard reads `mqtt_sensor` + `ml_summary` and shows **ML badge/score + plots**

## Repo layout
- `dashboard/` — Next.js app (already works; now wired to Influx + ML)
- `ml-pipeline/` — LSTM autoencoder training + batch inference + secure MQTT publisher
- `vm1-bridge/` — bridge script you run on VM1 (sanitized for GitHub; uses env vars for tokens)

---

# 1) Dependencies

## ML (Python)
- Python 3.10+ recommended
- `pip install -r ml-pipeline/requirements.txt`

## Dashboard (Node)
- Node 18+ recommended
- `npm install` in `dashboard/`

---

# 2) Configuration (VM1 + VM2)

## VM2 (MQTT broker)
- Broker: `VM2_IP:1883`
- Topic: `demo/496/chat`

## VM1 (InfluxDB)
- Influx: `VM1_IP:8086`
- Org: `ECE496`
- Bucket: `capstone`

## Tokens (important)
- `INFLUX_TOKEN` on VM1 bridge can be **write-only** (good practice).
- ML + Dashboard need **READ** access:
  - ML uses `INFLUX_QUERY_TOKEN` to read `mqtt_sensor`
  - Dashboard uses `INFLUX_QUERY_TOKEN` to read `mqtt_sensor` + `ml_summary`
- ML writes `ml_summary` using `INFLUX_WRITE_TOKEN` (can be write-only).

---

# 3) Run the system on the VMs

## Step A — Publish sensor data to MQTT (VM2)
Use the **secure publisher** (compatible with VM1 HMAC verification):

```bash
cd ml-pipeline
cp .env.example .env
# edit .env: MQTT_HOST=VM2_IP, MQTT_PORT=1883, MQTT_HMAC_KEY=...
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python mqtt/pub_secure.py
# then in the prompt:
send 22.5 55.2 120 lab
```

> If your mosquitto is plaintext (no TLS), set `MQTT_TLS=false` in `ml-pipeline/.env` and also remove TLS config from the VM1 bridge (or configure mosquitto TLS).

## Step B — Bridge MQTT → Influx (VM1)
```bash
cd vm1-bridge
export MQTT_HOST=VM2_IP
export MQTT_PORT=1883
export MQTT_TOPIC=demo/496/chat
export MQTT_HMAC_KEY=...            # must match publisher
export INFLUX_URL=http://127.0.0.1:8086
export INFLUX_ORG=ECE496
export INFLUX_BUCKET=capstone
export INFLUX_TOKEN=...             # write token
python3 mqtt_to_influx.py
```

You should see `[bridge] wrote:` lines.

## Step C — Train the LSTM (local or VM2)
Training works on either:
- **synthetic placeholder data** (no DB required), or
- **real Influx data** from VM1

```bash
cd ml-pipeline
source .venv/bin/activate
python -m ml.train_lstm --data synthetic --out artifacts
# real data:
python -m ml.train_lstm --data influx --start -14d --out artifacts
```

This creates:
- `artifacts/lstm_ae.pt`
- `artifacts/normalizer.json`
- `artifacts/calibration.json`

## Step D — Run inference + write ML outputs (VM2 or VM1)
```bash
cd ml-pipeline
source .venv/bin/activate
# real data → writes into Influx measurement ml_summary
python -m ml.infer_batch --data influx --start -7d --artifacts artifacts --write
```

---

# 4) Run the dashboard (connects to DB + ML)

```bash
cd dashboard
cp .env.example .env
# edit .env:
# INFLUX_URL=http://VM1_IP:8086
# INFLUX_QUERY_TOKEN=READ_TOKEN
npm install
npm run dev
```

Open:
- `http://localhost:3000/experiments`

What you should see:
- experiments list derived from `mqtt_sensor` (segmented by time gaps + device/room)
- each experiment row shows `ml_flag` from `ml_summary` (NORMAL / SUSPICIOUS / ...)
- experiment detail shows the actual series and (if present) a predicted/expected curve

---

# 5) Notes on “connecting dashboard to LSTM”
The dashboard is “connected” to the LSTM by reading **the model outputs written back to Influx**:
- Inputs: `mqtt_sensor`
- Outputs: `ml_summary` (experiment_id-tagged)

The LSTM itself is run via:
- `python -m ml.infer_batch --write`
which computes `anomaly_score` + `ml_flag` and writes results into Influx for the dashboard to display.


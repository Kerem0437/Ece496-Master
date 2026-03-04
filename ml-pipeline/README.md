# Xatoms ECE496 — MQTT → Influx → LSTM Anomaly Scoring (Local + VM-ready)

This repo gives you **all code** for:
- Publishing sensor readings over MQTT (VM2 broker, port **1883**) with **HMAC envelope** compatible with your VM1 `mqtt_to_influx` verifier
- Bridging MQTT → InfluxDB (you already have `mqtt_to_influx` on VM1; kept as-is)
- Training an **LSTM autoencoder** (placeholder synthetic data OR real Influx data)
- Batch inference: read recent runs from Influx, compute `anomaly_score` + `ml_flag`, and write results back to Influx as `ml_summary`

## What your port files imply (important)
- **VM2** is running **mosquitto on 1883** (broker).
- **VM1** is running **InfluxDB on 8086**.
- Your `mqtt_to_influx` script on VM1 subscribes to MQTT broker at `192.168.56.108:1883` and writes to local Influx (`127.0.0.1:8086`).
So: **VM2 = MQTT broker**, **VM1 = Influx**.

## Quickstart (local laptop)
1) Create venv and install deps:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Copy env template:
```bash
cp .env.example .env
# edit .env with your IPs/tokens/keys
```

3) Generate synthetic data + train model:
```bash
python -m ml.train_lstm --data synthetic --out artifacts
```

4) Run batch inference (synthetic mode):
```bash
python -m ml.infer_batch --data synthetic --artifacts artifacts
```

## VM integration (how it fits your VMs)
- Run **publisher** on VM2 (or Pi) to publish to broker on **VM2:1883**
- Run **mqtt_to_influx** on VM1 to write points into Influx measurement `mqtt_sensor`
- Run **ml batch inference** on VM2 (or VM1) to query Influx (VM1:8086) and write `ml_summary` back

### IMPORTANT about Influx tokens
Your provided token in `proof_write_only.py` is **write-only** (read denied).
For ML you need a **read-capable token** (or all-access) for `INFLUX_QUERY_TOKEN`.
You can keep write-only token for writing ML outputs if you want.

## Measurements
### Input measurement (from mqtt_to_influx)
- Measurement: `mqtt_sensor`
- Tags: `device`, optionally `room`, `water_type`, `local_csv`
- Fields: numeric/bool fields (e.g., `temp`, `humidity`, `luminosity`)

### Output measurement (this pipeline writes)
- Measurement: `ml_summary`
- Tags: `experiment_id`, `device`, `room` (room optional)
- Fields:
  - `ml_version` (string)
  - `anomaly_score` (float 0–1)
  - `ml_flag` (string: NORMAL/UNKNOWN/SUSPICIOUS/INSUFFICIENT_DATA)
  - `ml_timestamp_utc` (string ISO)
  - `error_raw` (float)
  - `seq_len` (int)
  - `prediction_curve_json` (string JSON with expected vs actual)

## CLI help
```bash
python -m ml.train_lstm -h
python -m ml.infer_batch -h
```

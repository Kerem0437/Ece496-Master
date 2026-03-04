# End-to-end checklist (copy/paste)

## Ports (from your netstat)
- VM2 Mosquitto: **1883**
- VM1 InfluxDB: **8086**

## Step 0 — Env
- [ ] Put certs on publisher + bridge where needed: `~/certs/{ca.crt,client.crt,client.key}`
- [ ] Set `MQTT_HMAC_KEY` identical on VM1 (bridge) and VM2 (publisher)
- [ ] Create Influx token with READ for ML: `INFLUX_QUERY_TOKEN`
- [ ] Keep write-only token for writes: `INFLUX_WRITE_TOKEN` (optional)

## Step 1 — MQTT publish (VM2)
- [ ] `python3 mqtt/pub_secure.py`
- [ ] Send a few rows: `send 22.5 55.2 120 lab`

## Step 2 — MQTT→Influx bridge (VM1)
- [ ] Run your `mqtt_to_influx.py` (already provided)
- [ ] Confirm it prints `wrote:` line protocol
- [ ] Confirm Influx UI shows measurement `mqtt_sensor`

## Step 3 — Train LSTM (local or VM2)
- [ ] `python -m ml.train_lstm --data influx --start -14d --out artifacts`
  - If no data yet: `--data synthetic`

## Step 4 — Batch inference (VM2)
- [ ] `python -m ml.infer_batch --data influx --start -7d --artifacts artifacts --write`
- [ ] In Influx, confirm measurement `ml_summary` has:
  - fields: `ml_flag`, `anomaly_score`, `ml_timestamp_utc`, `ml_version`, `prediction_curve_json` (optional)

## Step 5 — Dashboard hookup (later)
- [ ] Query `ml_summary` by `experiment_id` and join to runs by `(device, room, time)`

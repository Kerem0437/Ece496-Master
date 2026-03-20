# VM1 Bridge (MQTT → InfluxDB)

This is the process that runs on **VM1** to subscribe to MQTT and write sensor fields into InfluxDB on **VM2**.

## Run (on VM1)
Prereqs:
- MQTT broker reachable (usually VM1 itself)
- InfluxDB reachable on VM2 over local network (192.168.56.110)

Example:
```bash
export MQTT_HOST=192.168.56.108
export MQTT_PORT=1883
export MQTT_TOPIC=demo/496/chat

export INFLUX_URL=http://192.168.56.110:8086
export INFLUX_ORG=ECE496
export INFLUX_BUCKET=capstone
export INFLUX_TOKEN=REPLACE_WRITE_TOKEN

# HMAC must match publisher
export MQTT_HMAC_KEY='pi'

python3 mqtt_to_influx.py
```

Notes:
- This bridge writes **sensor values only**.
- ML outputs are **not written to Influx** (served via `ml_service` instead).

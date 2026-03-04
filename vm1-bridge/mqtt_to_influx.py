#!/usr/bin/env python3
import os
import json
import hmac
import hashlib
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WritePrecision
import ssl

CERT_DIR = os.path.expanduser(os.getenv("CERT_DIR", "~/certs"))

# =====================
# MQTT CONFIG (VM2 broker)
# =====================
MQTT_HOST = os.environ.get("MQTT_HOST", "192.168.56.108")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
TOPIC     = os.environ.get("MQTT_TOPIC", "demo/496/chat")

# =====================
# INFLUXDB CONFIG (VM1)
# =====================
INFLUX_TOKEN  = os.environ.get("INFLUX_TOKEN", "")
INFLUX_ORG    = os.environ.get("INFLUX_ORG", "ECE496")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "capstone")
INFLUX_URL    = os.environ.get("INFLUX_URL", "http://127.0.0.1:8086")

MEASUREMENT = os.environ.get("MEASUREMENT", "mqtt_sensor")

# =====================
# SECURITY CONFIG
# =====================
HMAC_ENV_VAR = "MQTT_HMAC_KEY"
MAX_SKEW_SECONDS = int(os.environ.get("MAX_SKEW_SECONDS", "120"))
DEVICE_ALLOWLIST = { d.strip() for d in os.environ.get("DEVICE_ALLOWLIST", "").split(",") if d.strip() }
REQUIRE_TIME_VERIFIED = os.environ.get("REQUIRE_TIME_VERIFIED", "false").lower() == "true"


def get_hmac_key() -> bytes:
    key = os.environ.get(HMAC_ENV_VAR, "")
    if not key:
        raise RuntimeError(
            f"Missing {HMAC_ENV_VAR}. Set it like:\n"
            f"  export {HMAC_ENV_VAR}='a-long-random-secret'\n"
            f"(Must match the publisher.)"
        )
    return key.encode("utf-8")


HMAC_KEY = get_hmac_key()


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_hmac(key: bytes, device_id: str, timestamp: str, data_obj: dict) -> str:
    msg = f"{device_id}|{timestamp}|{canonical_json(data_obj)}".encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def parse_timestamp(ts: str) -> datetime:
    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return t.astimezone(timezone.utc)


def is_fresh(ts_utc: datetime) -> bool:
    now = datetime.now(timezone.utc)
    skew = abs((now - ts_utc).total_seconds())
    return skew <= MAX_SKEW_SECONDS


def verify_payload(payload: dict) -> tuple[bool, str]:
    device = payload.get("device_id")
    ts = payload.get("timestamp")
    digest = payload.get("hash")
    data = payload.get("data")
    time_auth = payload.get("time_authority", {})

    if not device or not ts or not digest or data is None:
        return False, "missing device_id/timestamp/hash/data"

    if DEVICE_ALLOWLIST and str(device) not in DEVICE_ALLOWLIST:
        return False, f"device_id not allowed: {device}"

    try:
        t = parse_timestamp(ts)
    except Exception:
        return False, "bad timestamp format"
    if not is_fresh(t):
        return False, f"timestamp outside freshness window (+/-{MAX_SKEW_SECONDS}s)"

    if REQUIRE_TIME_VERIFIED:
        verified = bool(time_auth.get("verified", False))
        if not verified:
            return False, "time_authority not verified"

    if not isinstance(data, dict):
        return False, "data must be a JSON object/dict for HMAC verification"

    expected = compute_hmac(HMAC_KEY, str(device), str(ts), data)
    if not hmac.compare_digest(str(digest), expected):
        return False, "HMAC mismatch (tampered or wrong key)"

    return True, "ok"


if not INFLUX_TOKEN:
    raise RuntimeError("Missing INFLUX_TOKEN (write token). Put it in env or a systemd service env file.")

influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx.write_api()


def on_message(_client, _userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))

        ok, reason = verify_payload(payload)
        if not ok:
            print(f"[bridge:drop] {reason} | topic={msg.topic}")
            return

        device = payload["device_id"]
        ts = payload["timestamp"]
        data = payload["data"]

        room = data.pop("room", None)
        water_type = data.pop("water_type", None)
        local_csv = data.pop("local_csv", None)

        t = parse_timestamp(ts)
        p = Point(MEASUREMENT).tag("device", str(device))

        if room is not None:
            p = p.tag("room", str(room))
        if water_type is not None:
            p = p.tag("water_type", str(water_type))
        if local_csv is not None:
            p = p.tag("local_csv", str(local_csv))

        wrote_any = False
        for k, v in data.items():
            if isinstance(v, bool):
                p = p.field(k, v); wrote_any = True
            elif isinstance(v, (int, float)):
                p = p.field(k, float(v)); wrote_any = True

        if not wrote_any:
            print("[bridge:warn] no numeric/bool fields found, skipping:", data)
            return

        p = p.time(t, WritePrecision.NS)
        write_api.write(bucket=INFLUX_BUCKET, record=p)
        print("[bridge] wrote:", p.to_line_protocol())

    except Exception as e:
        print("[bridge:error]", repr(e), "payload:", msg.payload[:200])


def main():
    m = mqtt.Client()

    # If your broker is plaintext, remove TLS here and set MQTT_TLS=false in publisher.
    m.tls_set(
        ca_certs=os.path.join(CERT_DIR, "ca.crt"),
        certfile=os.path.join(CERT_DIR, "client.crt"),
        keyfile=os.path.join(CERT_DIR, "client.key"),
        cert_reqs=ssl.CERT_REQUIRED,
        tls_version=ssl.PROTOCOL_TLS_CLIENT,
    )
    m.tls_insecure_set(False)
    m.on_message = on_message
    m.connect(MQTT_HOST, MQTT_PORT, 30)
    m.subscribe(TOPIC, qos=1)

    print(f"[bridge] subscribed to {TOPIC} on {MQTT_HOST}:{MQTT_PORT}")
    m.loop_forever()


if __name__ == "__main__":
    main()

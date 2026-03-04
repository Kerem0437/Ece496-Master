#!/usr/bin/env python3
"""Secure-ish MQTT publisher compatible with VM1 mqtt_to_influx verifier.

Your VM1 bridge expects payload:
  {
    "device_id": "...",
    "timestamp": "2026-01-25T01:09:32Z",
    "hash": <HMAC-SHA256(device_id|timestamp|canonical_json(data))>,
    "data": { ... }  # numeric/bool fields, plus optional tag-ish fields like room
  }

Set env:
  MQTT_HOST, MQTT_PORT, MQTT_TOPIC
  MQTT_TLS=true/false
  CERT_DIR=~/certs (ca.crt, client.crt, client.key)
  MQTT_HMAC_KEY=...  (must match VM1)
"""

import os
import json
import hmac
import hashlib
import socket
import datetime
import ssl
from paho.mqtt.client import Client, MQTT_ERR_NO_CONN


MQTT_HOST = os.getenv("MQTT_HOST", "192.168.56.108")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "demo/496/chat")

MQTT_TLS = os.getenv("MQTT_TLS", "true").lower() == "true"
CERT_DIR = os.path.expanduser(os.getenv("CERT_DIR", "~/certs"))

HMAC_KEY = os.getenv("MQTT_HMAC_KEY", "").encode("utf-8")
if not HMAC_KEY:
    raise SystemExit("Missing MQTT_HMAC_KEY. Must match VM1 mqtt_to_influx.py")

DEVICE_ID = socket.gethostname()


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_hmac(device_id: str, timestamp: str, data_obj: dict) -> str:
    msg = f"{device_id}|{timestamp}|{canonical_json(data_obj)}".encode("utf-8")
    return hmac.new(HMAC_KEY, msg, hashlib.sha256).hexdigest()


def utc_iso_z() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def make_payload(data_obj: dict) -> str:
    ts = utc_iso_z()
    digest = compute_hmac(DEVICE_ID, ts, data_obj)
    return json.dumps({
        "device_id": DEVICE_ID,
        "timestamp": ts,
        "hash": digest,
        "data": data_obj,
        "time_authority": {"verified": True, "source": "system_clock"},
    }, separators=(",", ":"))


def connect_client() -> Client:
    c = Client(client_id=f"pub-{DEVICE_ID}")
    if MQTT_TLS:
        c.tls_set(
            ca_certs=os.path.join(CERT_DIR, "ca.crt"),
            certfile=os.path.join(CERT_DIR, "client.crt"),
            keyfile=os.path.join(CERT_DIR, "client.key"),
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        c.tls_insecure_set(False)
    c.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    c.loop_start()
    return c


def send(c: Client, data_obj: dict):
    payload = make_payload(data_obj)
    res = c.publish(MQTT_TOPIC, payload=payload, qos=1, retain=False)
    if res.rc == MQTT_ERR_NO_CONN:
        print("[pub:ERROR] Not connected, message not delivered.")
    else:
        print(f"[pub] sent → {MQTT_TOPIC} payload={payload}")


def main():
    print(f"[pub] broker={MQTT_HOST}:{MQTT_PORT} topic={MQTT_TOPIC} tls={MQTT_TLS}")
    c = connect_client()

    try:
        while True:
            line = input("> ").strip()
            if not line:
                continue
            if line in ("quit", "exit"):
                break

            # one-line: send <temp> <humidity> <luminosity> [room]
            parts = line.split()
            if parts[0] == "send" and (len(parts) == 4 or len(parts) == 5):
                temp = float(parts[1])
                hum = float(parts[2])
                lum = float(parts[3])
                room = parts[4] if len(parts) == 5 else None

                data = {"temp": temp, "humidity": hum, "luminosity": lum}
                if room:
                    data["room"] = room
                send(c, data)
            else:
                print("Use: send <temp> <humidity> <luminosity> [room] | quit")
    finally:
        try:
            c.loop_stop()
            c.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()

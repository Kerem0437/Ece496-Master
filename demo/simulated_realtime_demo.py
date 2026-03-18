#!/usr/bin/env python3
"""
DEMO MODE PIPELINE (NO NETWORK REQUIRED)

This script is for recording a demo when VPN/VM access is flaky.
It DOES NOT connect to MQTT/Influx. Instead it:
  - prints terminal logs that look like a live pipeline
  - updates dashboard/demo-json/*.json so the Next.js dashboard (DATA_MODE=demojson)
    can show changing experiment values when you refresh the page.

IMPORTANT (honesty):
  All logs are clearly labeled DEMO.
  Use this as a backup recording, not as a claim that VMs were reachable.

How to record (recommended):
  Terminal 1: run dashboard locally:
      cd dashboard
      copy .env.example .env   (Windows)  or  cp .env.example .env
      set DATA_MODE=demojson in .env
      npm install
      npm run dev
      open http://localhost:3000/experiments

  Terminal 2: run this simulator:
      cd demo
      py simulated_realtime_demo.py --duration 30

While recording, refresh the dashboard page a couple times to see ML flag/score change.
"""
import argparse
import json
import random
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(t: datetime) -> str:
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def log(prefix: str, msg: str) -> None:
    print(f"[{iso_z(utc_now())}] [{prefix}] {msg}")


def load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(p: Path, obj: Any) -> None:
    p.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def choose_experiment(exps: List[Dict[str, Any]], preferred: str | None) -> Dict[str, Any]:
    if preferred:
        for e in exps:
            if e.get("experiment_id") == preferred:
                return e
    return exps[0]


def append_measurements(meas: List[Dict[str, Any]], exp_id: str, device_id: str, start_ts: datetime, seconds_from_start: int) -> List[Dict[str, Any]]:
    """
    Add a few new points (turbidity_voltage_V, pH, water_temp_C).
    Values follow a smooth random walk; sometimes we inject a spike to flip ML flag.
    """
    last_by_sensor: Dict[str, float] = {}
    for m in reversed(meas[-200:]):
        s = m.get("sensor_type")
        if s and s not in last_by_sensor:
            last_by_sensor[s] = float(m.get("value", 0.0))
        if len(last_by_sensor) >= 3:
            break

    turb = last_by_sensor.get("turbidity_voltage_V", 3.2)
    ph = last_by_sensor.get("pH", 7.0)
    wt = last_by_sensor.get("water_temp_C", 20.0)

    turb += random.uniform(-0.01, 0.01)
    ph += random.uniform(-0.003, 0.003)
    wt += random.uniform(-0.01, 0.01)

    spike = random.random() < 0.08
    if spike:
        turb += random.uniform(0.4, 0.8)

    points = [
        ("turbidity_voltage_V", turb, "V"),
        ("pH", ph, "pH"),
        ("water_temp_C", wt, "C"),
    ]

    base_time = start_ts + timedelta(seconds=seconds_from_start)
    for sensor_type, value, unit in points:
        idx = sum(1 for x in meas if x.get("sensor_type") == sensor_type)
        meas.append({
            "measurement_id": f"{exp_id}_{sensor_type}_{idx}",
            "experiment_id": exp_id,
            "timestamp_utc": iso_z(base_time),
            "device_id": device_id,
            "sensor_type": sensor_type,
            "value": float(value),
            "unit": unit,
            "sample_index": idx,
            "time_offset_seconds": seconds_from_start,
        })

    return meas


def compute_simple_anomaly_score(meas: List[Dict[str, Any]]) -> Tuple[float, str]:
    """
    Simple heuristic standing in for LSTM reconstruction error:
    - Look at last 30 turbidity points and compute max jump.
    - Map to score [0,1].
    """
    turb = [float(m["value"]) for m in meas if m.get("sensor_type") == "turbidity_voltage_V"]
    if len(turb) < 10:
        return 0.0, "INSUFFICIENT_DATA"
    recent = turb[-30:]
    jumps = [abs(recent[i] - recent[i-1]) for i in range(1, len(recent))]
    max_jump = max(jumps) if jumps else 0.0
    score = min(1.0, max(0.0, (max_jump - 0.03) / 0.25))
    flag = "NORMAL" if score < 0.30 else ("SUSPICIOUS" if score >= 0.70 else "UNKNOWN")
    return float(score), flag


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=25, help="Seconds to run (prints look like real-time)")
    ap.add_argument("--interval", type=float, default=2.0, help="Seconds between cycles")
    ap.add_argument("--experiment-id", default=None, help="Experiment ID to animate (optional)")
    ap.add_argument("--no-write", action="store_true", help="Only print logs; do not update JSON files")
    args = ap.parse_args()

    random.seed(7)

    repo_root = Path(__file__).resolve().parents[1]
    dash_demo_root = repo_root / "dashboard" / "demo-json"
    exp_path = dash_demo_root / "experiments.json"
    meas_dir = dash_demo_root / "measurements"

    if not exp_path.exists() or not meas_dir.exists():
        raise SystemExit(f"demo-json not found at {dash_demo_root}")

    log("DEMO", "SIMULATION MODE: no MQTT/Influx connections are made.")
    log("DEMO", "DEMO MODE: no MQTT/Influx connections are made.")
    log("DEMO", f"Using demo-json folder: {dash_demo_root}")

    exps = load_json(exp_path)
    if not isinstance(exps, list) or not exps:
        raise SystemExit("experiments.json is empty or invalid")

    exp = choose_experiment(exps, args.experiment_id)
    exp_id = exp.get("experiment_id")
    device_id = exp.get("device_id", "PI-EDGE-001")
    meas_path = meas_dir / f"{exp_id}.json"
    if not meas_path.exists():
        raise SystemExit(f"Missing measurement file: {meas_path}")

    meas = load_json(meas_path)
    if not isinstance(meas, list):
        raise SystemExit("Measurement JSON invalid")

    if meas:
        try:
            start_ts = datetime.fromisoformat(str(meas[-1]["timestamp_utc"]).replace("Z", "+00:00"))
        except Exception:
            start_ts = utc_now()
    else:
        start_ts = utc_now()

    t_start = time.perf_counter()
    cycle = 0
    while (time.perf_counter() - t_start) < args.duration:
        cycle += 1

        log("PUB", "Connecting to MQTT broker... OK (simulated)  topic=demo/496/chat")
        log("PUB", f"Publishing sensor packet #{cycle} ... OK (simulated)")

        log("BRIDGE", "Received MQTT payload. HMAC verify: OK (simulated)")
        log("BRIDGE", "Writing to InfluxDB... OK (simulated)  measurement=mqtt_sensor")

        if not args.no_write:
            seconds_from_start = int((cycle - 1) * args.interval)
            meas = append_measurements(meas, exp_id, device_id, start_ts, seconds_from_start)
            save_json(meas_path, meas)

        log("ML", "Reading latest window from DB... OK (simulated)")
        score, flag = compute_simple_anomaly_score(meas)
        log("ML", f"Running LSTM inference... OK (simulated)  anomaly_score={score:.3f} ml_flag={flag}")

        if not args.no_write:
            nowz = iso_z(utc_now())
            exp["ml_version"] = exp.get("ml_version") or "lstm_v1.0.0_demo"
            exp["anomaly_score"] = score
            exp["ml_flag"] = flag
            exp["ml_timestamp_utc"] = nowz
            exp["end_timestamp_utc"] = meas[-1]["timestamp_utc"] if meas else exp.get("end_timestamp_utc")
            save_json(exp_path, exps)

        log("DASH", "Fetching /experiments ... 200 OK (simulated)")
        log("DASH", f"UI updated. (Refresh browser to see new flag/score) exp={exp_id} flag={flag} score={score:.3f}")
        print("")
        time.sleep(args.interval)

    log("DEMO", "Done. Stop recording. Refresh once more to show final state.")


if __name__ == "__main__":
    main()

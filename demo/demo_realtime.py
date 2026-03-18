\
#!/usr/bin/env python3
"""
DEMO MODE PIPELINE (NO NETWORK REQUIRED)

This script is designed for a **screen-recordable demo** when VM/VPN access is flaky.
It does NOT connect to MQTT/Influx. Instead it:
  - prints "pipeline-like" logs in real time
  - updates dashboard/demo-json/*.json so the Next.js dashboard (DATA_MODE=demojson)
    shows changing ML flags/scores after a browser refresh.

How to record:
  Terminal 1 (dashboard):
    cd dashboard
    copy .env.example .env   (Windows) OR cp .env.example .env (Mac/Linux)
    set DATA_MODE=demojson in .env
    npm install
    npm run dev
    open http://localhost:3000/experiments

  Terminal 2 (this script):
    cd demo
    py demo_realtime.py --duration 30 --interval 2

While recording, refresh the dashboard once or twice to show updates.
"""

import argparse
import json
import random
import time
from dataclasses import dataclass
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


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def flag_from_score(score: float) -> str:
    if score < 0.30:
        return "NORMAL"
    if score >= 0.70:
        return "SUSPICIOUS"
    return "UNKNOWN"


@dataclass
class Profile:
    label: str
    base_score: float
    noise: float
    spike_prob: float
    spike_mag: Tuple[float, float]


def build_profiles(exps: List[Dict[str, Any]]) -> Dict[str, Profile]:
    """
    Deterministic mixed demo:
      1st -> NORMAL
      2nd -> UNKNOWN
      3rd -> NORMAL
      4th -> SUSPICIOUS
      rest -> NORMAL
    If an ID contains 'FAULT'/'BAD', force suspicious profile.
    """
    profiles: Dict[str, Profile] = {}

    # default assignment by index
    for i, e in enumerate(exps):
        exp_id = str(e.get("experiment_id", ""))
        if not exp_id:
            continue

        upper = exp_id.upper()
        if "FAULT" in upper or "BAD" in upper:
            profiles[exp_id] = Profile("forced_suspicious", 0.90, 0.06, 0.30, (0.10, 0.25))
            continue

        if i == 0:
            profiles[exp_id] = Profile("normal", 0.12, 0.05, 0.05, (0.02, 0.05))
        elif i == 1:
            profiles[exp_id] = Profile("unknown", 0.50, 0.08, 0.10, (0.04, 0.08))
        elif i == 2:
            profiles[exp_id] = Profile("normal", 0.18, 0.06, 0.06, (0.02, 0.06))
        elif i == 3:
            profiles[exp_id] = Profile("suspicious", 0.86, 0.07, 0.35, (0.10, 0.30))
        else:
            profiles[exp_id] = Profile("normal", 0.20, 0.06, 0.06, (0.02, 0.06))

    # safety: ensure at least one suspicious and one normal exist
    if profiles:
        if not any(p.base_score >= 0.70 for p in profiles.values()):
            first = next(iter(profiles))
            profiles[first] = Profile("suspicious", 0.85, 0.07, 0.30, (0.10, 0.25))
        if not any(p.base_score < 0.30 for p in profiles.values()):
            first = next(iter(profiles))
            profiles[first] = Profile("normal", 0.15, 0.05, 0.05, (0.02, 0.05))

    return profiles


def append_measurements(
    meas: List[Dict[str, Any]],
    exp_id: str,
    device_id: str,
    start_ts: datetime,
    seconds_from_start: int,
    profile: Profile,
) -> List[Dict[str, Any]]:
    """
    Add 3 sensor points. We keep the values smooth so plots look reasonable.
    """
    # last values
    last_by_sensor: Dict[str, float] = {}
    for m in reversed(meas[-200:]):
        s = m.get("sensor_type")
        if s and s not in last_by_sensor:
            last_by_sensor[s] = float(m.get("value", 0.0))
        if len(last_by_sensor) >= 3:
            break

    turb = last_by_sensor.get("turbidity_voltage_V", 3.20)
    ph = last_by_sensor.get("pH", 7.00)
    wt = last_by_sensor.get("water_temp_C", 20.00)

    # smooth drift
    turb += random.uniform(-0.008, 0.008)
    ph += random.uniform(-0.002, 0.002)
    wt += random.uniform(-0.006, 0.006)

    # occasional bump only for suspicious profile (makes plots show an event)
    bump = (profile.base_score >= 0.70) and (random.random() < 0.12)
    if bump:
        turb += random.uniform(0.15, 0.35)

    points = [
        ("turbidity_voltage_V", turb, "V"),
        ("pH", ph, "pH"),
        ("water_temp_C", wt, "C"),
    ]

    t = start_ts + timedelta(seconds=seconds_from_start)
    for sensor_type, value, unit in points:
        idx = sum(1 for x in meas if x.get("sensor_type") == sensor_type)
        meas.append({
            "measurement_id": f"{exp_id}_{sensor_type}_{idx}",
            "experiment_id": exp_id,
            "timestamp_utc": iso_z(t),
            "device_id": device_id,
            "sensor_type": sensor_type,
            "value": float(value),
            "unit": unit,
            "sample_index": idx,
            "time_offset_seconds": seconds_from_start,
        })

    return meas


def next_score(profile: Profile) -> float:
    score = profile.base_score + random.uniform(-profile.noise, profile.noise)
    if random.random() < profile.spike_prob:
        score += random.uniform(profile.spike_mag[0], profile.spike_mag[1])
    return clamp(score)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=30, help="Seconds to run")
    ap.add_argument("--interval", type=float, default=2.0, help="Seconds between cycles")
    ap.add_argument("--experiment-id", default=None, help="Animate a single experiment (optional)")
    ap.add_argument("--no-write", action="store_true", help="Only print logs; do not update JSON files")
    ap.add_argument("--seed", type=int, default=7, help="Deterministic demo seed")
    args = ap.parse_args()

    random.seed(args.seed)

    repo_root = Path(__file__).resolve().parents[1]
    demo_root = repo_root / "dashboard" / "demo-json"
    exp_path = demo_root / "experiments.json"
    meas_dir = demo_root / "measurements"

    if not exp_path.exists() or not meas_dir.exists():
        raise SystemExit(f"demo-json not found at {demo_root}")

    log("DEMO", "DEMO MODE: no MQTT/Influx connections are made.")
    log("DEMO", f"Using demo-json folder: {demo_root}")

    exps = load_json(exp_path)
    if not isinstance(exps, list) or not exps:
        raise SystemExit("experiments.json is empty or invalid")

    # filter selection
    selected: List[Dict[str, Any]] = exps
    if args.experiment_id:
        selected = [e for e in exps if str(e.get("experiment_id")) == args.experiment_id]
        if not selected:
            raise SystemExit(f"No matching experiment_id found: {args.experiment_id}")

    profiles = build_profiles(selected)

    # pre-load measurement data
    meas_by_exp: Dict[str, List[Dict[str, Any]]] = {}
    start_ts_by_exp: Dict[str, datetime] = {}
    device_by_exp: Dict[str, str] = {}
    meas_path_by_exp: Dict[str, Path] = {}

    for e in selected:
        exp_id = str(e.get("experiment_id", ""))
        if not exp_id:
            continue

        device_id = str(e.get("device_id", "PI-EDGE-001"))
        device_by_exp[exp_id] = device_id

        mp = meas_dir / f"{exp_id}.json"
        if not mp.exists():
            raise SystemExit(f"Missing measurement file: {mp}")
        meas_path_by_exp[exp_id] = mp

        meas = load_json(mp)
        if not isinstance(meas, list):
            raise SystemExit(f"Measurement JSON invalid: {mp}")
        meas_by_exp[exp_id] = meas

        if meas:
            try:
                last = datetime.fromisoformat(str(meas[-1]["timestamp_utc"]).replace("Z", "+00:00"))
            except Exception:
                last = utc_now()
        else:
            last = utc_now()
        start_ts_by_exp[exp_id] = last

    log("DEMO", "Profiles: " + " | ".join([f"{k}=>{profiles[k].label}" for k in profiles.keys()]))

    t0 = time.perf_counter()
    cycle = 0
    while (time.perf_counter() - t0) < args.duration:
        cycle += 1
        seconds_from_start = int((cycle - 1) * args.interval)

        log("PUB", "Connected to MQTT broker (demo mode). Publishing packet...")
        log("BRIDGE", "Received packet. Verified. Stored to DB (demo mode).")
        summary_lines: List[str] = []

        for e in selected:
            exp_id = str(e.get("experiment_id", ""))
            if not exp_id:
                continue

            prof = profiles[exp_id]
            meas = meas_by_exp[exp_id]

            if not args.no_write:
                meas = append_measurements(
                    meas=meas,
                    exp_id=exp_id,
                    device_id=device_by_exp[exp_id],
                    start_ts=start_ts_by_exp[exp_id],
                    seconds_from_start=seconds_from_start,
                    profile=prof,
                )
                meas_by_exp[exp_id] = meas
                save_json(meas_path_by_exp[exp_id], meas)

            score = next_score(prof)
            flag = flag_from_score(score)

            # update experiment summary (so dashboard list changes)
            if not args.no_write:
                e["ml_version"] = e.get("ml_version") or "lstm_v1.0.0_demo"
                e["anomaly_score"] = float(score)
                e["ml_flag"] = flag
                e["ml_timestamp_utc"] = iso_z(utc_now())
                e["end_timestamp_utc"] = meas[-1]["timestamp_utc"] if meas else e.get("end_timestamp_utc")

            summary_lines.append(f"{exp_id}: {flag} ({score:.3f})")

        if not args.no_write:
            save_json(exp_path, exps)

        log("ML", "Inference complete (demo mode). Updated experiments:")
        for line in summary_lines[:8]:
            log("ML", line)
        log("DASH", "Refresh browser to see updated flags/scores.")
        print("")

        time.sleep(args.interval)

    log("DEMO", "Done. Refresh once more to show final state.")


if __name__ == "__main__":
    main()

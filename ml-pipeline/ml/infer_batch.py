from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from .config import SETTINGS
from .influx_io import make_influx_clients, query_sensor_data, write_ml_summary
from .preprocessing import segment_into_experiments, SENSOR_COLS, Normalizer
from .model import LSTMAutoencoder
from .synth_data import make_synthetic_runs


@dataclass
class Calibration:
    q50: float
    q95: float
    q99: float
    thresh_normal: float
    thresh_suspicious: float
    ml_version: str
    seq_len: int


def load_normalizer(path: Path) -> Normalizer:
    obj = json.loads(path.read_text(encoding="utf-8"))
    mean = np.array(obj["mean"], dtype=np.float32)
    std = np.array(obj["std"], dtype=np.float32)
    return Normalizer(mean=mean, std=std)


def load_calibration(path: Path) -> Calibration:
    obj = json.loads(path.read_text(encoding="utf-8"))
    return Calibration(
        q50=float(obj["q50"]),
        q95=float(obj["q95"]),
        q99=float(obj["q99"]),
        thresh_normal=float(obj["thresh_normal"]),
        thresh_suspicious=float(obj["thresh_suspicious"]),
        ml_version=str(obj.get("ml_version", SETTINGS.ml_version)),
        seq_len=int(obj.get("seq_len", SETTINGS.seq_len)),
    )


def err_to_score(err: float, calib: Calibration) -> float:
    # robust map: q50 -> 0, q95 -> 1 (clipped). If q95==q50, avoid div0.
    denom = max(1e-12, (calib.q95 - calib.q50))
    score = (err - calib.q50) / denom
    return float(np.clip(score, 0.0, 1.0))


def score_to_flag(score: Optional[float], n_points: int, calib: Calibration) -> str:
    if score is None or n_points < SETTINGS.min_points:
        return "INSUFFICIENT_DATA"
    if score < calib.thresh_normal:
        return "NORMAL"
    if score >= calib.thresh_suspicious:
        return "SUSPICIOUS"
    return "UNKNOWN"


def make_prediction_curve(actual: np.ndarray, recon: np.ndarray, max_points: int = 120) -> Dict[str, Any]:
    # For dashboard overlay: store first max_points of 1 channel (luminosity) + per-step residual
    ch = SENSOR_COLS.index("luminosity") if "luminosity" in SENSOR_COLS else 0
    a = actual[:max_points, ch].tolist()
    e = recon[:max_points, ch].tolist()
    resid = (np.abs(np.array(a) - np.array(e))).tolist()
    return {
        "channel": SENSOR_COLS[ch],
        "actual": a,
        "expected": e,
        "abs_residual": resid,
    }


def main():
    p = argparse.ArgumentParser(description="Batch inference: Influx -> LSTM -> write ml_summary to Influx")
    p.add_argument("--data", choices=["synthetic", "influx"], default="synthetic")
    p.add_argument("--start", default="-7d", help="Influx range start (when --data influx)")
    p.add_argument("--artifacts", default="artifacts", help="Dir containing lstm_ae.pt, normalizer.json, calibration.json")
    p.add_argument("--write", action="store_true", help="Actually write ml_summary to Influx (in synthetic mode still writes if configured)")
    p.add_argument("--limit", type=int, default=50, help="Max experiments to process")
    args = p.parse_args()

    art = Path(args.artifacts)
    norm = load_normalizer(art / "normalizer.json")
    calib = load_calibration(art / "calibration.json")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = LSTMAutoencoder(input_dim=len(SENSOR_COLS)).to(device)
    model.load_state_dict(torch.load(art / "lstm_ae.pt", map_location=device))
    model.eval()

    # ---- load data
    if args.data == "synthetic":
        raw = make_synthetic_runs()
        clients = None
    else:
        clients = make_influx_clients()
        raw = query_sensor_data(clients.query, start=args.start)

    runs = segment_into_experiments(raw)
    if not runs:
        raise SystemExit("No runs found.")

    # process newest first
    runs = sorted(runs, key=lambda r: r.df.index.max(), reverse=True)[: args.limit]

    # ---- per-run score using full run (or last seq_len chunk)
    results = []
    for r in runs:
        arr = r.df[SENSOR_COLS].to_numpy(dtype=np.float32)
        n_points = len(arr)

        if n_points < SETTINGS.min_points:
            score = None
            flag = "INSUFFICIENT_DATA"
            err = None
            curve = None
        else:
            # Use last seq_len points; if shorter, pad by repeating first
            seq_len = calib.seq_len
            if n_points >= seq_len:
                window = arr[-seq_len:]
            else:
                pad = np.repeat(arr[:1], repeats=(seq_len - n_points), axis=0)
                window = np.concatenate([pad, arr], axis=0)

            x = norm.transform(window[None, :, :])  # (1,T,F)
            xt = torch.tensor(x, dtype=torch.float32).to(device)
            with torch.no_grad():
                recon = model(xt).cpu().numpy()[0]     # normalized space
            # back to original space for curve
            recon_orig = norm.inverse(recon)

            err = float(((recon - x[0]) ** 2).mean())
            score = err_to_score(err, calib)
            flag = score_to_flag(score, n_points=n_points, calib=calib)
            curve = make_prediction_curve(actual=window, recon=recon_orig)

        results.append({
            "experiment_id": r.experiment_id,
            "device": r.device,
            "room": r.room,
            "n_points": n_points,
            "error_raw": err,
            "anomaly_score": score,
            "ml_flag": flag,
        })

        print(f"[infer] {r.experiment_id} points={n_points} score={score} flag={flag}")

        if args.write and args.data != "synthetic":
            assert clients is not None
            write_ml_summary(
                client=clients.write,
                experiment_id=r.experiment_id,
                device=r.device,
                room=r.room,
                anomaly_score=score,
                ml_flag=flag,
                ml_version=calib.ml_version,
                error_raw=err,
                seq_len=n_points,
                prediction_curve=curve,
                ts=datetime.now(timezone.utc),
            )

    # In synthetic mode, you can still write if you want (useful for dashboard demo),
    # but you need INFLUX_URL + tokens set.
    if args.write and args.data == "synthetic":
        clients = make_influx_clients()
        for row in results:
            write_ml_summary(
                client=clients.write,
                experiment_id=row["experiment_id"],
                device=row["device"],
                room=row["room"],
                anomaly_score=row["anomaly_score"],
                ml_flag=row["ml_flag"],
                ml_version=calib.ml_version,
                error_raw=row["error_raw"],
                seq_len=row["n_points"],
                prediction_curve=None,
                ts=datetime.now(timezone.utc),
            )

    # save local report
    (art / "latest_inference.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"[done] wrote {len(results)} results to {art / 'latest_inference.json'}")

if __name__ == "__main__":
    main()

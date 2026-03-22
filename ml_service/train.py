#!/usr/bin/env python3
"""
Train per-feature masked gap-fill LSTM models.

This retrains the ML service around the intended review logic:
- each variable gets its own model
- the model only sees a subset of the raw points
- it reconstructs / fills the missing points
- suspiciousness is based on how badly the held-out points are predicted

Artifacts written to:
  ml_service/artifacts/manifest.json
  ml_service/artifacts/feature_models/<feature>/...
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn

try:
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
except Exception:
    pass


try:
    from logging_utils import setup_logging
except Exception:  # pragma: no cover
    from .logging_utils import setup_logging

try:
    from model import LSTMAutoencoder
    from preprocess import FEATURES, load_sensor_csv
except Exception:  # pragma: no cover
    from .model import LSTMAutoencoder
    from .preprocess import FEATURES, load_sensor_csv


MODE_KEEP = {
    "normal": 0.90,
    "strict": 0.75,
}


def feature_windows_from_csvs(csvs: List[Path], feature: str, seq_len: int, stride: int) -> np.ndarray:
    windows: List[np.ndarray] = []
    for path in csvs:
        df = load_sensor_csv(path)
        series = df[feature].to_numpy(dtype=np.float32)
        if len(series) < seq_len:
            continue
        for start in range(0, len(series) - seq_len + 1, stride):
            windows.append(series[start : start + seq_len].reshape(seq_len, 1))
    if not windows:
        return np.zeros((0, seq_len, 1), dtype=np.float32)
    return np.stack(windows, axis=0).astype(np.float32)


def fit_scaler_1d(windows: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    flat = windows.reshape(-1)
    mean = np.array([float(np.mean(flat))], dtype=np.float32)
    std = np.array([float(np.std(flat))], dtype=np.float32)
    std = np.where(std < 1e-6, 1.0, std)
    return mean, std


def scale_1d(windows: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return (windows - mean.reshape(1, 1, 1)) / (std.reshape(1, 1, 1) + 1e-8)


def save_scaler_1d(path: Path, mean: np.ndarray, std: np.ndarray, meta: Dict | None = None) -> None:
    payload: Dict[str, object] = {
        "mean": mean.astype(float).tolist(),
        "std": std.astype(float).tolist(),
    }
    if meta:
        payload["meta"] = meta
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def make_mask(batch: int, seq_len: int, rng: np.random.Generator, min_keep: float, max_keep: float) -> np.ndarray:
    mask = np.ones((batch, seq_len, 1), dtype=np.float32)
    for i in range(batch):
        keep_fraction = float(rng.uniform(min_keep, max_keep))
        keep_count = max(4, min(seq_len - 2, int(round(seq_len * keep_fraction))))
        observed_idx = set(rng.choice(seq_len, size=keep_count, replace=False).tolist())
        observed_idx.add(0)
        observed_idx.add(seq_len - 1)
        cur = np.zeros((seq_len,), dtype=np.float32)
        for idx in observed_idx:
            cur[int(idx)] = 1.0
        # add one contiguous hidden block so the model learns to interpolate spans
        gap = max(2, int(round(seq_len * rng.uniform(0.04, 0.16))))
        start = int(rng.integers(1, max(2, seq_len - gap)))
        cur[start : start + gap] = 0.0
        cur[0] = 1.0
        cur[-1] = 1.0
        if cur.sum() < max(4, seq_len * 0.55):
            topup = rng.choice(seq_len, size=max(0, int(seq_len * 0.60) - int(cur.sum())), replace=False)
            cur[topup] = 1.0
            cur[0] = 1.0
            cur[-1] = 1.0
        mask[i, :, 0] = cur
    return mask


def build_model_input(values_n: np.ndarray, mask: np.ndarray) -> np.ndarray:
    return np.concatenate([values_n * mask, mask], axis=2).astype(np.float32)


def masked_gapfill_loss(pred: torch.Tensor, target: torch.Tensor, observed_mask: torch.Tensor) -> torch.Tensor:
    # observed_mask: 1 means visible to the model; 0 means held out.
    missing_mask = 1.0 - observed_mask
    base = (pred - target) ** 2
    loss_all = base.mean()
    denom_missing = torch.clamp(missing_mask.sum(), min=1.0)
    loss_missing = (base * missing_mask).sum() / denom_missing
    return 0.35 * loss_all + 0.65 * loss_missing


@torch.no_grad()
def masked_mse_per_window(model: nn.Module, windows_n: np.ndarray, keep_fraction: float, seed: int, batch_size: int = 256) -> np.ndarray:
    device = next(model.parameters()).device
    rng = np.random.default_rng(seed)
    errs: List[np.ndarray] = []
    model.eval()
    for start in range(0, len(windows_n), batch_size):
        chunk = windows_n[start : start + batch_size]
        if len(chunk) == 0:
            continue
        mask = make_mask(len(chunk), chunk.shape[1], rng, keep_fraction, keep_fraction)
        x = torch.tensor(build_model_input(chunk, mask), dtype=torch.float32, device=device)
        y = torch.tensor(chunk, dtype=torch.float32, device=device)
        pred = model(x)
        missing = torch.tensor(1.0 - mask, dtype=torch.float32, device=device)
        mse = (((pred - y) ** 2) * missing).sum(dim=(1, 2)) / torch.clamp(missing.sum(dim=(1, 2)), min=1.0)
        errs.append(mse.detach().cpu().numpy())
    return np.concatenate(errs, axis=0) if errs else np.array([], dtype=np.float32)


def collect_csvs(data_dir: Path) -> List[Path]:
    csvs = [
        data_dir / "tap_water_20260315.csv",
        data_dir / "rb_water_20260314.csv",
        data_dir / "fertilizer_water_20260315.csv",
        data_dir / "10hr_mb_water_20260316.csv",
    ]
    optional = data_dir / "tap_water_2020_placeholder.csv"
    if optional.exists():
        csvs.append(optional)
    for path in csvs:
        if not path.exists():
            raise SystemExit(f"Missing training CSV: {path}")
    return csvs


def main() -> None:
    log = setup_logging("ml_train")

    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[1] / "demo" / "data"))
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--seq-len", type=int, default=60)
    ap.add_argument("--stride", type=int, default=10)
    ap.add_argument("--hidden", type=int, default=32)
    ap.add_argument("--layers", type=int, default=1)
    ap.add_argument("--max-windows", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=496)
    args = ap.parse_args()

    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    t0 = time.perf_counter()
    data_dir = Path(args.data_dir)
    csvs = collect_csvs(data_dir)

    art = Path(__file__).resolve().parent / "artifacts"
    feature_root = art / "feature_models"
    if feature_root.exists():
        shutil.rmtree(feature_root)
    feature_root.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    manifest: Dict[str, object] = {
        "version": "gapfill_v1_per_feature",
        "trained_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seq_len": int(args.seq_len),
        "stride": int(args.stride),
        "features": [],
        "mode_keep": MODE_KEEP,
        "feature_models": {},
    }

    for feat in FEATURES:
        log.info("Training per-feature gap-fill model for %s", feat)
        windows = feature_windows_from_csvs(csvs, feat, seq_len=args.seq_len, stride=args.stride)
        if len(windows) == 0:
            log.warning("Skipping %s: not enough windows", feat)
            continue

        if len(windows) > args.max_windows:
            idx = np.random.choice(len(windows), size=args.max_windows, replace=False)
            windows = windows[idx]

        mean, std = fit_scaler_1d(windows)
        windows_n = scale_1d(windows, mean, std)

        model = LSTMAutoencoder(input_dim=2, hidden_dim=args.hidden, num_layers=args.layers, output_dim=1).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        losses: List[float] = []
        rng = np.random.default_rng(args.seed + FEATURES.index(feat) * 97)

        x = torch.tensor(windows_n, dtype=torch.float32)
        loader = torch.utils.data.DataLoader(torch.utils.data.TensorDataset(x), batch_size=64, shuffle=True)

        model.train()
        for ep in range(1, args.epochs + 1):
            ep_losses: List[float] = []
            for (yb,) in loader:
                yb = yb.to(device)
                mask = make_mask(yb.shape[0], yb.shape[1], rng, min_keep=0.72, max_keep=0.95)
                mb = torch.tensor(mask, dtype=torch.float32, device=device)
                xb = torch.tensor(build_model_input(yb.detach().cpu().numpy(), mask), dtype=torch.float32, device=device)
                pred = model(xb)
                loss = masked_gapfill_loss(pred, yb, mb)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                ep_losses.append(float(loss.item()))
            losses.append(float(np.mean(ep_losses)))
            log.info("feature=%s epoch %d/%d loss=%.6f", feat, ep, args.epochs, losses[-1])

        calibration: Dict[str, Dict[str, float]] = {}
        for mode, keep_fraction in MODE_KEEP.items():
            errs = masked_mse_per_window(model, windows_n, keep_fraction=keep_fraction, seed=args.seed + hash((feat, mode)) % 100000)
            if len(errs) == 0:
                q50, q95 = 0.0, 1.0
            else:
                q50 = float(np.quantile(errs, 0.50))
                q95 = float(np.quantile(errs, 0.95))
                if q95 <= q50:
                    q95 = q50 + 1e-6
            q90 = float(np.quantile(errs, 0.90)) if len(errs) else q95
            q99 = float(np.quantile(errs, 0.99)) if len(errs) else max(q95, q50 + 1e-6)
            if q99 <= q95:
                q99 = q95 + max(1e-6, 0.25 * max(q95 - q50, 1e-6))
            calibration[mode] = {
                "keep_fraction": float(keep_fraction),
                "q50": q50,
                "q90": q90,
                "q95": q95,
                "q99": q99,
                "mean": float(np.mean(errs)) if len(errs) else 0.0,
                "std": float(np.std(errs)) if len(errs) else 0.0,
            }

        feat_dir = feature_root / feat
        feat_dir.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), feat_dir / "model.pt")
        save_scaler_1d(feat_dir / "scaler.json", mean, std, meta={"feature": feat})
        (feat_dir / "calibration.json").write_text(
            json.dumps(
                {
                    "feature": feat,
                    "seq_len": int(args.seq_len),
                    "stride": int(args.stride),
                    "losses": losses,
                    "calibration": calibration,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        manifest["features"].append(feat)
        manifest["feature_models"][feat] = {
            "dir": str(feat_dir.relative_to(art)),
            "seq_len": int(args.seq_len),
            "stride": int(args.stride),
            "calibration": calibration,
        }

    (art / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    training_summary = {"trained_at_utc": manifest["trained_at_utc"], "version": manifest["version"], "mode_keep": MODE_KEEP, "feature_models": manifest["feature_models"]}
    (art / "training_summary.json").write_text(json.dumps(training_summary, indent=2) + "\n", encoding="utf-8")
    log.info("Saved per-feature gap-fill artifacts to %s", art)
    log.info("Delete old top-level artifacts if you want a clean tree: %s", art)
    log.info("done in %.2fs", time.perf_counter() - t0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Train LSTM autoencoder using CSVs in demo/data.

Produces:
  ml_service/artifacts/model.pt
  ml_service/artifacts/scaler.json
  ml_service/artifacts/calibration.json

Model purpose:
  - anomaly detection of BAD DATA / sensor faults
  - NOT water contamination classification
  - trained on MIXED water types to avoid "tap vs everything else"
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import List

import numpy as np
import torch
import torch.nn as nn

try:
    from logging_utils import setup_logging
except Exception:  # pragma: no cover
    from .logging_utils import setup_logging
from model import LSTMAutoencoder
from preprocess import load_sensor_csv, build_windows, fit_scaler, scale, save_scaler, FEATURES


def recon_error(model: nn.Module, windows_n: np.ndarray) -> np.ndarray:
    device = next(model.parameters()).device
    model.eval()
    errs = []
    with torch.no_grad():
        x = torch.tensor(windows_n, dtype=torch.float32).to(device)
        for i in range(0, len(x), 256):
            xb = x[i:i + 256]
            recon = model(xb)
            mse = ((recon - xb) ** 2).mean(dim=(1, 2)).detach().cpu().numpy()
            errs.append(mse)
    return np.concatenate(errs, axis=0) if errs else np.array([])


def recon_error_per_feature(model: nn.Module, windows_n: np.ndarray) -> np.ndarray:
    """Return per-feature MSE averaged over time: shape (N, F)."""
    device = next(model.parameters()).device
    model.eval()
    errs = []
    with torch.no_grad():
        x = torch.tensor(windows_n, dtype=torch.float32).to(device)
        for i in range(0, len(x), 256):
            xb = x[i:i + 256]
            recon = model(xb)
            # (B,T,F) -> mean over T => (B,F)
            mse_f = ((recon - xb) ** 2).mean(dim=1).detach().cpu().numpy()
            errs.append(mse_f)
    return np.concatenate(errs, axis=0) if errs else np.zeros((0, windows_n.shape[-1]), dtype=np.float32)


def main() -> None:
    log = setup_logging('ml_train')

    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[1] / "demo" / "data"))
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--seq-len", type=int, default=60)
    ap.add_argument("--stride", type=int, default=60)
    ap.add_argument("--hidden", type=int, default=32)
    ap.add_argument("--layers", type=int, default=1)
    ap.add_argument("--max-windows", type=int, default=2000)
    args = ap.parse_args()

    t0 = time.perf_counter()
    log.info('Starting training (LSTM autoencoder)')
    log.info('Data dir: %s', args.data_dir)
    log.info('Params: epochs=%s seq_len=%s stride=%s hidden=%s layers=%s max_windows=%s', args.epochs, args.seq_len, args.stride, args.hidden, args.layers, args.max_windows)

    data_dir = Path(args.data_dir)

    csvs = [
        data_dir / "tap_water_20260315.csv",
        data_dir / "rb_water_20260314.csv",
        data_dir / "fertilizer_water_20260315.csv",
        data_dir / "10hr_mb_water_20260316.csv",
    ]
    opt = data_dir / "tap_water_2020_placeholder.csv"
    if opt.exists():
        csvs.append(opt)

    for p in csvs:
        if not p.exists():
            raise SystemExit(f"Missing training CSV: {p}")

    windows_all: List[np.ndarray] = []
    for p in csvs:
        df = load_sensor_csv(p)
        w = build_windows(df, seq_len=args.seq_len, stride=args.stride)
        if len(w):
            windows_all.append(w)

    train_windows = np.concatenate(windows_all, axis=0)
    if len(train_windows) == 0:
        raise SystemExit("Not enough data. Try --seq-len 30")

    if len(train_windows) > args.max_windows:
        idx = np.random.choice(len(train_windows), size=args.max_windows, replace=False)
        train_windows = train_windows[idx]

    mean, std = fit_scaler(train_windows)
    train_windows_n = scale(train_windows, mean, std)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = LSTMAutoencoder(input_dim=len(FEATURES), hidden_dim=args.hidden, num_layers=args.layers).to(device)

    optm = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()

    x = torch.tensor(train_windows_n, dtype=torch.float32)
    loader = torch.utils.data.DataLoader(torch.utils.data.TensorDataset(x), batch_size=64, shuffle=True)

    losses = []
    model.train()
    for ep in range(1, args.epochs + 1):
        ep_losses = []
        for (xb,) in loader:
            xb = xb.to(device)
            recon = model(xb)
            loss = loss_fn(recon, xb)
            optm.zero_grad()
            loss.backward()
            optm.step()
            ep_losses.append(float(loss.item()))
        losses.append(float(np.mean(ep_losses)))
        log.info('epoch %d/%d loss=%.6f', ep, args.epochs, losses[-1])

    errs = recon_error(model, train_windows_n)
    q50 = float(np.quantile(errs, 0.50))
    q95 = float(np.quantile(errs, 0.95))

    # per-feature calibration (helps explain which signal looks abnormal)
    errs_f = recon_error_per_feature(model, train_windows_n)  # (N,F)
    q50_vec = np.quantile(errs_f, 0.50, axis=0).astype(float).tolist()
    q95_vec = np.quantile(errs_f, 0.95, axis=0).astype(float).tolist()

    art = Path(__file__).resolve().parent / "artifacts"
    art.mkdir(exist_ok=True)

    torch.save(model.state_dict(), art / "model.pt")
    save_scaler(art / "scaler.json", mean, std, meta={"features": FEATURES})
    (art / "calibration.json").write_text(json.dumps({"q50": q50, "q95": q95, "q50_vec": q50_vec, "q95_vec": q95_vec, "features": FEATURES, "losses": losses}, indent=2) + "\n", encoding="utf-8")

    dt = time.perf_counter() - t0
    log.info('done in %.2fs | saved to %s', dt, art)


if __name__ == "__main__":
    main()

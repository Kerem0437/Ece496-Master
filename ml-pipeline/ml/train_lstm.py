from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm

from .config import SETTINGS
from .influx_io import make_influx_clients, query_sensor_data
from .preprocessing import segment_into_experiments, fit_normalizer, make_sequences, SENSOR_COLS
from .model import LSTMAutoencoder
from .synth_data import make_synthetic_runs


def set_seed(seed: int = 7) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def compute_errors(model: nn.Module, loader: DataLoader, device: torch.device) -> np.ndarray:
    model.eval()
    errs = []
    with torch.no_grad():
        for (x,) in loader:
            x = x.to(device)
            recon = model(x)
            mse = ((recon - x) ** 2).mean(dim=(1, 2))  # per-sample
            errs.append(mse.detach().cpu().numpy())
    return np.concatenate(errs, axis=0) if errs else np.array([])


def main():
    p = argparse.ArgumentParser(description="Train LSTM autoencoder for anomaly scoring.")
    p.add_argument("--data", choices=["synthetic", "influx"], default="synthetic", help="Training data source")
    p.add_argument("--start", default="-14d", help="Influx range start (when --data influx)")
    p.add_argument("--out", default="artifacts", help="Output dir for model + normalizer + calibration")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--hidden", type=int, default=64)
    p.add_argument("--layers", type=int, default=2)
    p.add_argument("--lr", type=float, default=1e-3)
    args = p.parse_args()

    set_seed(7)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # ---- load data
    if args.data == "synthetic":
        raw = make_synthetic_runs()
    else:
        clients = make_influx_clients()
        raw = query_sensor_data(clients.query, start=args.start)

    runs = segment_into_experiments(raw)
    if not runs:
        raise SystemExit("No runs found. (If influx: check token READ + INFLUX_URL + measurement name.)")

    # ---- normalize + sequences
    norm = fit_normalizer(runs)

    # only train on sequences; any short run gets skipped here
    X, meta = make_sequences(runs, seq_len=SETTINGS.seq_len)
    if len(X) == 0:
        raise SystemExit("No sequences created. Try lowering SEQ_LEN or MIN_POINTS.")

    Xn = norm.transform(X)

    # ---- torch setup
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = LSTMAutoencoder(input_dim=len(SENSOR_COLS), hidden_dim=args.hidden, num_layers=args.layers).to(device)

    ds = TensorDataset(torch.tensor(Xn, dtype=torch.float32))
    loader = DataLoader(ds, batch_size=args.batch, shuffle=True, drop_last=False)

    optim = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = nn.MSELoss()

    # ---- train
    model.train()
    for epoch in range(1, args.epochs + 1):
        losses = []
        for (x,) in tqdm(loader, desc=f"epoch {epoch}/{args.epochs}"):
            x = x.to(device)
            recon = model(x)
            loss = loss_fn(recon, x)
            optim.zero_grad()
            loss.backward()
            optim.step()
            losses.append(loss.item())
        print(f"[train] epoch={epoch} loss={float(np.mean(losses)):.6f}")

    # ---- calibrate error -> score mapping (quantiles)
    eval_loader = DataLoader(ds, batch_size=args.batch, shuffle=False, drop_last=False)
    errs = compute_errors(model, eval_loader, device=device)
    q50 = float(np.quantile(errs, 0.50))
    q95 = float(np.quantile(errs, 0.95))
    q99 = float(np.quantile(errs, 0.99))
    print(f"[calib] mse q50={q50:.6f} q95={q95:.6f} q99={q99:.6f}")

    # ---- save artifacts
    torch.save(model.state_dict(), out / "lstm_ae.pt")

    (out / "normalizer.json").write_text(json.dumps({
        "sensor_cols": SENSOR_COLS,
        "mean": norm.mean.tolist(),
        "std": norm.std.tolist(),
    }, indent=2), encoding="utf-8")

    (out / "calibration.json").write_text(json.dumps({
        "ml_version": SETTINGS.ml_version,
        "seq_len": SETTINGS.seq_len,
        "q50": q50,
        "q95": q95,
        "q99": q99,
        "thresh_normal": SETTINGS.thresh_normal,
        "thresh_suspicious": SETTINGS.thresh_suspicious,
    }, indent=2), encoding="utf-8")

    print(f"[done] saved to {out.resolve()}")

if __name__ == "__main__":
    main()

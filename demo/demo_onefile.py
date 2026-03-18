#!/usr/bin/env python3
"""
ECE496 ONE-FILE DEMO (sensor CSVs -> LSTM -> HTML report)

Goal:
  Run ONE command, produce ONE HTML file showing:
    - data summary
    - training stats + runtime
    - anomaly scoring results (bad-data detection)
    - quantitative test (F1 on injected faults)
    - plots (time series + reconstruction overlay)

This demo uses local CSVs (no Influx needed) so it works anywhere.

Usage (Windows PowerShell):
  cd demo
  py demo_onefile.py --data-dir data --out demo_report.html --no-plots
  start demo_report.html

Key decisions from team chat:
  - We treat "contaminated water" as NOT inherently bad.
  - We detect "bad data" (sensor faults) by injecting spikes/dropouts/flatlines
    and measuring reconstruction error.
  - Turbidity NTU calibration is ignored; we use turbidity_voltage_V.
"""

import argparse
import base64
import math
import os
import platform
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

# Matplotlib is optional (use --no-plots to skip)
try:
    import matplotlib.pyplot as plt  # type: ignore
    HAVE_PLOT = True
except Exception:
    HAVE_PLOT = False

# -----------------------------
# Config (fast demo defaults)
# -----------------------------
FEATURES = [
    "air_temp_C",
    "air_humidity_pct",
    "pH",
    "turbidity_voltage_V",
    "water_temp_C",
    "absorbance",              # may be empty/NaN; we fill
    "uv_absorbance_mean_all",  # optional, from tapWater_uv_features.csv
    "uv_absorbance_254nm",
    "uv_absorbance_365nm",
    "uv_absorbance_450nm",
]

DEFAULT_EPOCHS = 3
DEFAULT_SEQ_LEN = 60          # with 10s sampling, 60 steps ~ 10 min window
DEFAULT_STRIDE = 60
DEFAULT_BATCH = 64
DEFAULT_HIDDEN = 32
DEFAULT_LAYERS = 1

# Runtime caps (keeps demo fast and stable on laptops)
MAX_TRAIN_WINDOWS = 400
MAX_TEST_WINDOWS = 120


def utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# -----------------------------
# Model: LSTM Autoencoder
# -----------------------------
class LSTMAutoencoder(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, num_layers: int, dropout: float = 0.1):
        super().__init__()
        self.encoder = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.decoder = nn.LSTM(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.to_hidden = nn.Linear(hidden_dim, hidden_dim)
        self.out = nn.Linear(hidden_dim, input_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B,T,F)
        _, (h, c) = self.encoder(x)           # (L,B,H)
        h_last = h[-1]                        # (B,H)
        B, T, _ = x.shape
        dec_in_step = torch.tanh(self.to_hidden(h_last)).unsqueeze(1)  # (B,1,H)
        dec_in = dec_in_step.repeat(1, T, 1)  # (B,T,H)
        y, _ = self.decoder(dec_in, (h, c))   # (B,T,H)
        return self.out(y)                    # (B,T,F)


# -----------------------------
# Helpers
# -----------------------------
@dataclass
class Stage:
    name: str
    start: float
    end: float = 0.0

    def stop(self):
        self.end = time.perf_counter()

    @property
    def seconds(self) -> float:
        return max(0.0, self.end - self.start)


def stage(name: str) -> Stage:
    return Stage(name=name, start=time.perf_counter())


def b64_png(fig) -> str:
    bio = BytesIO()
    fig.savefig(bio, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(bio.getvalue()).decode("ascii")


def html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# -----------------------------
# Data loading
# -----------------------------
def load_sensor_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    # Some files had dtimestamp typo
    if "timestamp" not in df.columns and "dtimestamp" in df.columns:
        df = df.rename(columns={"dtimestamp": "timestamp"})
    if "timestamp" not in df.columns:
        raise ValueError(f"{path.name}: missing timestamp column")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    # Standardize expected columns
    for col in ["water_type", "air_temp_C", "air_humidity_pct", "pH", "turbidity_voltage_V", "water_temp_C", "absorbance"]:
        if col not in df.columns:
            df[col] = np.nan

    # numeric coercion
    for col in ["air_temp_C", "air_humidity_pct", "pH", "turbidity_voltage_V", "water_temp_C", "absorbance"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def load_uv_features(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    for c in df.columns:
        if c != "timestamp":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def merge_uv(sensor_df: pd.DataFrame, uv_df: pd.DataFrame) -> pd.DataFrame:
    """Merge UV features into sensor_df by nearest timestamp within 5 seconds."""
    a = sensor_df.sort_values("timestamp").copy()
    b = uv_df.sort_values("timestamp").copy()

    merged = pd.merge_asof(
        a,
        b,
        on="timestamp",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=5),
    )

    # rename UV columns to match FEATURES
    ren = {
        "absorbance_mean_all": "uv_absorbance_mean_all",
        "absorbance_254nm": "uv_absorbance_254nm",
        "absorbance_365nm": "uv_absorbance_365nm",
        "absorbance_450nm": "uv_absorbance_450nm",
    }
    for src, dst in ren.items():
        if src in merged.columns:
            merged = merged.rename(columns={src: dst})
        else:
            merged[dst] = np.nan

    return merged


def ensure_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for f in FEATURES:
        if f not in out.columns:
            out[f] = np.nan
    # absorbance placeholder
    out["absorbance"] = pd.to_numeric(out["absorbance"], errors="coerce").fillna(0.0)
    return out


def summarize_df(df: pd.DataFrame) -> Dict:
    t0 = df["timestamp"].min()
    t1 = df["timestamp"].max()
    dt = df["timestamp"].diff().dt.total_seconds().dropna()
    return {
        "rows": int(len(df)),
        "start": str(t0),
        "end": str(t1),
        "duration_hours": float((t1 - t0).total_seconds() / 3600.0) if pd.notna(t0) and pd.notna(t1) else None,
        "median_step_s": float(dt.median()) if len(dt) else None,
    }


# -----------------------------
# Windowing + normalization
# -----------------------------
def thin(df: pd.DataFrame, max_rows: int = 2400) -> pd.DataFrame:
    """Downsample by stride to keep runtime stable."""
    if len(df) <= max_rows:
        return df
    step = max(1, len(df) // max_rows)
    return df.iloc[::step].reset_index(drop=True)


def build_windows(df: pd.DataFrame, seq_len: int, stride: int) -> np.ndarray:
    x = df[FEATURES].to_numpy(dtype=np.float32)
    x = pd.DataFrame(x).ffill().bfill().fillna(0.0).to_numpy(dtype=np.float32)

    if len(x) < seq_len:
        return np.zeros((0, seq_len, x.shape[1]), dtype=np.float32)

    windows = []
    for i in range(0, len(x) - seq_len + 1, stride):
        windows.append(x[i:i + seq_len])
    return np.stack(windows, axis=0)


def fit_scaler(windows: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    flat = windows.reshape(-1, windows.shape[-1])
    mean = flat.mean(axis=0)
    std = flat.std(axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    return mean.astype(np.float32), std.astype(np.float32)


def scale(w: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return (w - mean) / (std + 1e-8)


def unscale(w: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return w * (std + 1e-8) + mean


# -----------------------------
# Fault injection (bad data)
# -----------------------------
def inject_fault(window: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    w = window.copy()
    T, _ = w.shape
    candidates = [
        FEATURES.index("turbidity_voltage_V"),
        FEATURES.index("pH"),
        FEATURES.index("water_temp_C"),
    ]
    f = int(rng.choice(candidates))
    mode = rng.choice(["spike", "dropout", "flatline"], p=[0.4, 0.3, 0.3])
    i = int(rng.integers(low=max(1, T // 5), high=max(2, 4 * T // 5)))

    if mode == "spike":
        w[i:i + 3, f] += float(rng.uniform(3.0, 6.0))
    elif mode == "dropout":
        w[i:i + 10, f] = 0.0
    else:
        w[i:i + 20, f] = w[i, f]
    return w


# -----------------------------
# Train + score
# -----------------------------
def train_model(windows_n: np.ndarray, epochs: int, batch: int, hidden: int, layers: int) -> Tuple[LSTMAutoencoder, Dict]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = LSTMAutoencoder(input_dim=windows_n.shape[-1], hidden_dim=hidden, num_layers=layers).to(device)

    optim = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()

    x = torch.tensor(windows_n, dtype=torch.float32)
    ds = torch.utils.data.TensorDataset(x)
    loader = torch.utils.data.DataLoader(ds, batch_size=batch, shuffle=True, drop_last=False)

    losses: List[float] = []
    model.train()
    for ep in range(1, epochs + 1):
        ep_losses: List[float] = []
        for (xb,) in loader:
            xb = xb.to(device)
            recon = model(xb)
            loss = loss_fn(recon, xb)
            optim.zero_grad()
            loss.backward()
            optim.step()
            ep_losses.append(float(loss.item()))
        losses.append(float(np.mean(ep_losses)))

    meta = {
        "device": str(device),
        "epochs": int(epochs),
        "batch": int(batch),
        "hidden": int(hidden),
        "layers": int(layers),
        "losses": losses,
    }
    return model, meta


def recon_error(model: LSTMAutoencoder, windows_n: np.ndarray) -> np.ndarray:
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


def score_from_err(err: float, q50: float, q95: float) -> float:
    denom = max(1e-12, (q95 - q50))
    return float(np.clip((err - q50) / denom, 0.0, 1.0))


def flag_from_score(score: float, normal_thr: float = 0.30, suspicious_thr: float = 0.70) -> str:
    if score < normal_thr:
        return "NORMAL"
    if score >= suspicious_thr:
        return "SUSPICIOUS"
    return "UNKNOWN"


def f1_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    if tp == 0:
        return 0.0
    precision = tp / max(1, (tp + fp))
    recall = tp / max(1, (tp + fn))
    if precision + recall == 0:
        return 0.0
    return float(2 * precision * recall / (precision + recall))


# -----------------------------
# HTML report
# -----------------------------
def make_report(out_path: Path, context: Dict) -> None:
    css = """
    body{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto; margin:24px; color:#111}
    h1{margin:0 0 8px 0}
    .sub{color:#444;margin:0 0 16px 0}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
    .card{border:1px solid #ddd;border-radius:12px;padding:14px}
    .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}
    table{border-collapse:collapse;width:100%}
    th,td{border-bottom:1px solid #eee;padding:8px;text-align:left;font-size:13px}
    .pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;border:1px solid #ccc}
    .pill.N{background:#e7f7ed;border-color:#b7e0c5}
    .pill.S{background:#fde8e8;border-color:#f2b8b5}
    .pill.U{background:#eef2ff;border-color:#c7d2fe}
    .log{background:#0b1020;color:#d1d5db;border-radius:12px;padding:12px;white-space:pre-wrap;font-size:12px}
    img{max-width:100%}
    """

    def pill(flag: str) -> str:
        c = "U"
        if flag == "NORMAL":
            c = "N"
        if flag == "SUSPICIOUS":
            c = "S"
        return f'<span class="pill {c}">{flag}</span>'

    parts: List[str] = []
    parts.append(f'<!doctype html><html><head><meta charset="utf-8"/><title>ECE496 LSTM Demo Report</title><style>{css}</style></head><body>')
    parts.append(f"<h1>ECE496 LSTM Demo Report</h1>")
    parts.append(f"<p class='sub'>Generated: <span class='mono'>{html_escape(context['generated_at'])}</span> • Purpose: detect <b>bad sensor/data</b> (not contaminated water)</p>")

    # System + timings
    parts.append('<div class="grid">')
    parts.append('<div class="card"><h3>Runtime / System</h3><table>')
    for k, v in context["system"].items():
        parts.append(f"<tr><th>{html_escape(str(k))}</th><td class='mono'>{html_escape(str(v))}</td></tr>")
    parts.append('</table></div>')
    parts.append('<div class="card"><h3>Stage Timings (transaction-like)</h3><table>')
    for row in context["timings"]:
        parts.append(f"<tr><th class='mono'>{html_escape(row['stage'])}</th><td>{row['seconds']:.3f}s</td></tr>")
    parts.append('</table></div>')
    parts.append('</div>')

    # Data summaries
    parts.append('<div class="card"><h3>Datasets loaded</h3><table>')
    parts.append("<tr><th>name</th><th>rows</th><th>duration_h</th><th>median_step_s</th><th>water_type</th></tr>")
    for d in context["data_summaries"]:
        parts.append(
            "<tr>"
            f"<td class='mono'>{html_escape(d['name'])}</td>"
            f"<td>{d['rows']}</td>"
            f"<td>{(d['duration_hours'] or 0):.2f}</td>"
            f"<td>{(d['median_step_s'] or 0):.1f}</td>"
            f"<td class='mono'>{html_escape(str(d.get('water_type','—')))}</td>"
            "</tr>"
        )
    parts.append("</table></div>")

    # Model
    m = context["model"]
    parts.append('<div class="grid">')
    parts.append('<div class="card"><h3>Model</h3><table>')
    for k, v in m.items():
        if k == "losses":
            continue
        parts.append(f"<tr><th>{html_escape(str(k))}</th><td class='mono'>{html_escape(str(v))}</td></tr>")
    parts.append("</table></div>")
    parts.append('<div class="card"><h3>Training loss</h3>')
    parts.append("<div class='mono' style='font-size:12px'>loss per epoch: " + ", ".join(f"{x:.5f}" for x in m["losses"]) + "</div>")
    if context.get("loss_plot_b64"):
        parts.append(f"<img src='data:image/png;base64,{context['loss_plot_b64']}'/>")
    parts.append("</div>")
    parts.append("</div>")

    # Results
    parts.append('<div class="card"><h3>Anomaly scoring results (per dataset)</h3>')
    parts.append("<p class='sub'>Score is 0–1 derived from reconstruction MSE quantiles (q50→0, q95→1).</p>")
    parts.append("<table><tr><th>dataset</th><th>score</th><th>flag</th><th>mse_raw</th><th>notes</th></tr>")
    for r in context["results"]:
        parts.append(
            "<tr>"
            f"<td class='mono'>{html_escape(r['name'])}</td>"
            f"<td>{r['score']:.3f}</td>"
            f"<td>{pill(r['flag'])}</td>"
            f"<td>{r['mse']:.6f}</td>"
            f"<td>{html_escape(r['note'])}</td>"
            "</tr>"
        )
    parts.append("</table></div>")

    # Quant test
    q = context["quant"]
    parts.append('<div class="grid">')
    parts.append('<div class="card"><h3>Quantitative test (synthetic faults)</h3><table>')
    for k in ["n_clean", "n_faulty", "threshold_score", "f1", "precision", "recall"]:
        parts.append(f"<tr><th>{k}</th><td class='mono'>{html_escape(str(q[k]))}</td></tr>")
    parts.append("</table></div>")
    parts.append('<div class="card"><h3>Confusion matrix</h3>')
    if context.get("cm_plot_b64"):
        parts.append(f"<img src='data:image/png;base64,{context['cm_plot_b64']}'/>")
    else:
        parts.append("<div class='sub'>Plot disabled.</div>")
    parts.append("</div>")
    parts.append("</div>")

    # Plots
    parts.append('<div class="card"><h3>Plots</h3>')
    if context.get("series_plots", []):
        for p in context["series_plots"]:
            parts.append(f"<h4 class='mono'>{html_escape(p['title'])}</h4>")
            parts.append(f"<img src='data:image/png;base64,{p['b64']}'/>")
    else:
        parts.append("<div class='sub'>Plots disabled.</div>")
    parts.append("</div>")

    # Logs
    parts.append('<div class="card"><h3>Run log</h3>')
    parts.append(f"<div class='log'>{html_escape(context['log'])}</div></div>")

    parts.append("</body></html>")
    out_path.write_text("\n".join(parts), encoding="utf-8")


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data", help="Folder containing the CSVs")
    ap.add_argument("--out", default="demo_report.html", help="HTML report output path")
    ap.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    ap.add_argument("--seq-len", type=int, default=DEFAULT_SEQ_LEN)
    ap.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-plots", action="store_true", help="Disable matplotlib plots for extra speed")
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    log_lines: List[str] = []
    timings: List[Dict] = []

    def log(msg: str) -> None:
        line = f"[{utc_now_z()}] {msg}"
        log_lines.append(line)
        print(line)

    data_dir = Path(args.data_dir)

    # Required datasets
    files = {
        "tap_water": data_dir / "tap_water_20260315.csv",
        "rb_water": data_dir / "rb_water_20260314.csv",
        "fertilizer_water": data_dir / "fertilizer_water_20260315.csv",
        "mb_10hr": data_dir / "10hr_mb_water_20260316.csv",
    }

    # Optional datasets
    opt_files = {
        "tap_water_2020": data_dir / "tap_water_2020_placeholder.csv",
        "uv_features": data_dir / "tapWater_uv_features.csv",
    }

    # Stage 1: load
    st = stage("load_csvs")
    for k, p in files.items():
        if not p.exists():
            raise SystemExit(f"Missing required file {k}: {p.resolve()}")

    tap = load_sensor_csv(files["tap_water"])
    rb = load_sensor_csv(files["rb_water"])
    fert = load_sensor_csv(files["fertilizer_water"])
    mb = load_sensor_csv(files["mb_10hr"])

    tap2020 = None
    if opt_files["tap_water_2020"].exists():
        tap2020 = load_sensor_csv(opt_files["tap_water_2020"])

    # UV features merged only into tap (optional)
    if opt_files["uv_features"].exists():
        uv = load_uv_features(opt_files["uv_features"])
        tap = merge_uv(tap, uv)
        uv_rows = len(uv)
    else:
        uv_rows = 0

    # Ensure all features exist
    tap = ensure_features(tap)
    rb = ensure_features(rb)
    fert = ensure_features(fert)
    mb = ensure_features(mb)
    if tap2020 is not None:
        tap2020 = ensure_features(tap2020)

    st.stop()
    timings.append({"stage": st.name, "seconds": st.seconds})
    log(f"Loaded CSVs. tap={len(tap)} rb={len(rb)} fert={len(fert)} mb={len(mb)} tap2020={'yes' if tap2020 is not None else 'no'} uv_rows={uv_rows}")

    # Stage 2: windowing + scaler
    st = stage("windowing")
    seq_len = int(args.seq_len)
    stride = int(args.stride)

    tap_t = thin(tap)
    rb_t = thin(rb)
    fert_t = thin(fert)
    mb_t = thin(mb)
    tap2020_t = thin(tap2020) if tap2020 is not None else None

    w_tap = build_windows(tap_t, seq_len=seq_len, stride=stride)
    w_rb = build_windows(rb_t, seq_len=seq_len, stride=stride)
    w_fert = build_windows(fert_t, seq_len=seq_len, stride=stride)
    w_mb = build_windows(mb_t, seq_len=seq_len, stride=stride)
    w_tap2020 = build_windows(tap2020_t, seq_len=seq_len, stride=stride) if tap2020_t is not None else np.zeros((0, seq_len, len(FEATURES)), dtype=np.float32)

    train_windows = np.concatenate([w_tap, w_rb, w_fert, w_mb, w_tap2020], axis=0)
    if len(train_windows) == 0:
        raise SystemExit("Not enough rows for chosen --seq-len. Try --seq-len 30.")

    mean, std = fit_scaler(train_windows)
    train_windows_n = scale(train_windows, mean, std)

    # cap training windows for stable runtime
    if len(train_windows_n) > MAX_TRAIN_WINDOWS:
        idx = np.random.choice(len(train_windows_n), size=MAX_TRAIN_WINDOWS, replace=False)
        train_windows_n = train_windows_n[idx]

    st.stop()
    timings.append({"stage": st.name, "seconds": st.seconds})
    log(f"Windowed: train_windows={train_windows_n.shape} features={len(FEATURES)} seq_len={seq_len}")

    # Stage 3: train
    st = stage("train_lstm")
    model, model_meta = train_model(
        windows_n=train_windows_n,
        epochs=int(args.epochs),
        batch=DEFAULT_BATCH,
        hidden=DEFAULT_HIDDEN,
        layers=DEFAULT_LAYERS,
    )
    st.stop()
    timings.append({"stage": st.name, "seconds": st.seconds})
    log(f"Trained LSTM AE. final_loss={model_meta['losses'][-1]:.6f} device={model_meta['device']}")

    # Stage 4: calibrate
    st = stage("calibration")
    errs_train = recon_error(model, train_windows_n)
    q50 = float(np.quantile(errs_train, 0.50))
    q95 = float(np.quantile(errs_train, 0.95))
    st.stop()
    timings.append({"stage": st.name, "seconds": st.seconds})
    log(f"Calibrated errors: q50={q50:.6f} q95={q95:.6f}")

    # Stage 5: score clean sets
    st = stage("score_clean_sets")

    def score_dataset(name: str, w: np.ndarray) -> Tuple[float, float, str]:
        wn = scale(w, mean, std)
        errs = recon_error(model, wn)
        err = float(errs.mean()) if len(errs) else float("inf")
        score = score_from_err(err, q50, q95)
        flag = flag_from_score(score)
        return score, err, flag

    results = []
    datasets = [
        ("tap_water", w_tap),
        ("rb_water", w_rb),
        ("fertilizer_water", w_fert),
        ("mb_10hr", w_mb),
    ]
    if len(w_tap2020) > 0:
        datasets.append(("tap_water_2020", w_tap2020))

    for name, w in datasets:
        score, err, flag = score_dataset(name, w)
        results.append({"name": name, "score": score, "mse": err, "flag": flag, "note": "clean dataset (no injected faults)"})
        log(f"{name}: score={score:.3f} flag={flag} mse={err:.6f}")

    st.stop()
    timings.append({"stage": st.name, "seconds": st.seconds})

    # Stage 6: quant test (fault injection)
    st = stage("quant_test")
    rng = np.random.default_rng(args.seed + 1)

    base = np.concatenate([w_tap, w_rb, w_tap2020], axis=0) if len(w_tap2020) else np.concatenate([w_tap, w_rb], axis=0)
    if len(base) < 20:
        base = train_windows

    n = min(MAX_TEST_WINDOWS, len(base))
    clean = base[:n]
    faulty = np.stack([inject_fault(clean[i], rng) for i in range(n)], axis=0)

    X = np.concatenate([clean, faulty], axis=0)
    y_true = np.concatenate([np.zeros(n, dtype=int), np.ones(n, dtype=int)], axis=0)

    Xn = scale(X, mean, std)
    errs = recon_error(model, Xn)
    scores = np.array([score_from_err(float(e), q50, q95) for e in errs], dtype=float)

    thr_grid = np.linspace(0.1, 0.9, 17)
    best = (0.0, 0.7)
    for thr in thr_grid:
        y_pred = (scores >= thr).astype(int)
        f1 = f1_score(y_true, y_pred)
        if f1 > best[0]:
            best = (float(f1), float(thr))

    best_f1, best_thr = best
    y_pred = (scores >= best_thr).astype(int)

    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)

    st.stop()
    timings.append({"stage": st.name, "seconds": st.seconds})
    log(f"Quant test: thr={best_thr:.2f} f1={best_f1:.3f} precision={precision:.3f} recall={recall:.3f}")

    # Optional plots
    loss_plot_b64 = None
    cm_plot_b64 = None
    series_plots: List[Dict[str, str]] = []

    if HAVE_PLOT and (not args.no_plots):
        # loss plot
        fig = plt.figure()
        plt.plot(model_meta["losses"])
        plt.title("Training loss (MSE)")
        plt.xlabel("epoch")
        plt.ylabel("loss")
        loss_plot_b64 = b64_png(fig)

        # confusion matrix
        cm = np.array(
            [[int(((y_true == 0) & (y_pred == 0)).sum()), fp], [fn, tp]], dtype=int
        )
        fig = plt.figure()
        plt.imshow(cm, interpolation="nearest")
        plt.title("Confusion matrix (synthetic faults)")
        plt.xticks([0, 1], ["pred_clean", "pred_fault"])
        plt.yticks([0, 1], ["true_clean", "true_fault"])
        for (i, j), v in np.ndenumerate(cm):
            plt.text(j, i, str(v), ha="center", va="center")
        cm_plot_b64 = b64_png(fig)

        # time series plots (pH + turbidity_voltage_V)
        def plot_series(df: pd.DataFrame, title: str) -> str:
            fig = plt.figure(figsize=(10, 3.5))
            t = df["timestamp"]
            plt.plot(t, df["turbidity_voltage_V"], label="turbidity_voltage_V")
            plt.plot(t, df["pH"], label="pH")
            plt.legend(loc="best")
            plt.title(title)
            plt.xlabel("timestamp (UTC)")
            plt.tight_layout()
            return b64_png(fig)

        series_plots.append({"title": "tap_water: pH + turbidity_voltage_V", "b64": plot_series(tap_t, "tap_water")})
        series_plots.append({"title": "rb_water: pH + turbidity_voltage_V", "b64": plot_series(rb_t, "rb_water")})
        series_plots.append({"title": "fertilizer_water: pH + turbidity_voltage_V", "b64": plot_series(fert_t, "fertilizer_water")})
        series_plots.append({"title": "mb_10hr: pH + turbidity_voltage_V", "b64": plot_series(mb_t, "mb_10hr")})
        if tap2020_t is not None:
            series_plots.append({"title": "tap_water_2020: pH + turbidity_voltage_V", "b64": plot_series(tap2020_t, "tap_water_2020")})

        # reconstruction overlay for turbidity_voltage_V on first tap window
        if len(w_tap) > 0:
            device = next(model.parameters()).device
            w0 = w_tap[0:1]
            w0n = scale(w0, mean, std)
            with torch.no_grad():
                x = torch.tensor(w0n, dtype=torch.float32).to(device)
                recon_n = model(x).cpu().numpy()[0]
            recon = unscale(recon_n, mean, std)
            actual = w0[0]
            fi = FEATURES.index("turbidity_voltage_V")

            fig = plt.figure(figsize=(10, 3.2))
            plt.plot(actual[:, fi], label="actual")
            plt.plot(recon[:, fi], label="reconstructed")
            plt.title("Reconstruction overlay (turbidity_voltage_V) — tap window 0")
            plt.xlabel("timestep")
            plt.ylabel("value")
            plt.legend(loc="best")
            plt.tight_layout()
            series_plots.append({"title": "Reconstruction overlay (tap window 0)", "b64": b64_png(fig)})

    # Build report context
    data_summaries = []
    for name, df in [
        ("tap_water", tap),
        ("rb_water", rb),
        ("fertilizer_water", fert),
        ("mb_10hr", mb),
    ]:
        s = summarize_df(df)
        s["name"] = name
        s["water_type"] = df["water_type"].iloc[0] if "water_type" in df.columns and len(df) else "—"
        data_summaries.append(s)
    if tap2020 is not None:
        s = summarize_df(tap2020)
        s["name"] = "tap_water_2020"
        s["water_type"] = tap2020["water_type"].iloc[0] if "water_type" in tap2020.columns and len(tap2020) else "—"
        data_summaries.append(s)

    context = {
        "generated_at": utc_now_z(),
        "system": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "torch": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cpu_cores": os.cpu_count(),
            "seq_len": seq_len,
            "features": ", ".join(FEATURES),
        },
        "timings": timings,
        "data_summaries": data_summaries,
        "model": model_meta,
        "results": results,
        "quant": {
            "n_clean": int(n),
            "n_faulty": int(n),
            "threshold_score": round(float(best_thr), 3),
            "f1": round(float(best_f1), 3),
            "precision": round(float(precision), 3),
            "recall": round(float(recall), 3),
        },
        "loss_plot_b64": loss_plot_b64,
        "cm_plot_b64": cm_plot_b64,
        "series_plots": series_plots,
        "log": "\n".join(log_lines),
    }

    out_path = Path(args.out)
    make_report(out_path, context)
    log(f"Wrote HTML report -> {out_path.resolve()}")


if __name__ == "__main__":
    main()
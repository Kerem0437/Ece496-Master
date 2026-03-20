from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple, Dict

import numpy as np
import pandas as pd

# Live demo stability: ignore absorbance/wavelength.
FEATURES = [
    "air_temp_C",
    "air_humidity_pct",
    "pH",
    "turbidity_voltage_V",
    "water_temp_C",
]

DEFAULT_SEQ_LEN = 60
DEFAULT_STRIDE = 60


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in FEATURES:
        if c not in out.columns:
            out[c] = np.nan
    out[FEATURES] = out[FEATURES].apply(pd.to_numeric, errors="coerce")
    out[FEATURES] = out[FEATURES].ffill().bfill().fillna(0.0)
    return out


def load_sensor_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "timestamp" not in df.columns and "dtimestamp" in df.columns:
        df = df.rename(columns={"dtimestamp": "timestamp"})
    if "timestamp" not in df.columns:
        raise ValueError(f"{path.name}: missing timestamp column")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return ensure_columns(df)


def measurements_json_to_df(measurements: List[dict]) -> pd.DataFrame:
    if not measurements:
        return pd.DataFrame(columns=["timestamp"] + FEATURES)

    rows = []
    for m in measurements:
        ts = m.get("timestamp_utc") or m.get("timestamp")
        st = m.get("sensor_type")
        val = m.get("value")
        if ts is None or st is None:
            continue
        rows.append((ts, st, val))

    df = pd.DataFrame(rows, columns=["timestamp", "sensor_type", "value"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

    wide = df.pivot_table(index="timestamp", columns="sensor_type", values="value", aggfunc="mean").reset_index()
    wide = wide.rename(columns={"timestamp": "timestamp"})
    return ensure_columns(wide)


def build_windows(df: pd.DataFrame, seq_len: int = DEFAULT_SEQ_LEN, stride: int = DEFAULT_STRIDE) -> np.ndarray:
    x = df[FEATURES].to_numpy(dtype=np.float32)
    if len(x) < seq_len:
        return np.zeros((0, seq_len, len(FEATURES)), dtype=np.float32)
    windows = []
    for i in range(0, len(x) - seq_len + 1, stride):
        windows.append(x[i:i + seq_len])
    return np.stack(windows, axis=0).astype(np.float32)


def fit_scaler(windows: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    flat = windows.reshape(-1, windows.shape[-1])
    mean = flat.mean(axis=0)
    std = flat.std(axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    return mean.astype(np.float32), std.astype(np.float32)


def scale(w: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return (w - mean) / (std + 1e-8)


def save_scaler(path: Path, mean: np.ndarray, std: np.ndarray, meta: Dict | None = None) -> None:
    obj = {"mean": mean.tolist(), "std": std.tolist(), "features": FEATURES}
    if meta:
        obj["meta"] = meta
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def load_scaler(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    mean = np.array(obj["mean"], dtype=np.float32)
    std = np.array(obj["std"], dtype=np.float32)
    return mean, std

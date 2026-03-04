from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import List, Optional, Dict, Tuple

import numpy as np
import pandas as pd

from .config import SETTINGS


SENSOR_COLS = ["temp", "humidity", "luminosity"]


@dataclass
class ExperimentRun:
    experiment_id: str
    device: str
    room: Optional[str]
    df: pd.DataFrame  # indexed by time, contains SENSOR_COLS


def _safe_room(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() != "nan" else None


def segment_into_experiments(raw: pd.DataFrame) -> List[ExperimentRun]:
    """Segment time series into 'experiments' by time gaps.

    Group key: (device, room). Within each group, split runs when time gap > GAP_SPLIT_MIN.
    """
    if raw.empty:
        return []

    df = raw.copy()
    df = df.sort_values("_time")
    df["_time"] = pd.to_datetime(df["_time"], utc=True)
    df["device"] = df["device"].astype(str)
    df["room"] = df["room"].apply(_safe_room)

    runs: List[ExperimentRun] = []
    gap = timedelta(minutes=SETTINGS.gap_split_min)

    for (device, room), g in df.groupby(["device", "room"], dropna=False):
        g = g.sort_values("_time").reset_index(drop=True)

        # Only keep rows where we have at least one sensor value
        has_any = g[SENSOR_COLS].notna().any(axis=1)
        g = g.loc[has_any].copy()
        if g.empty:
            continue

        # Split by time gap
        t = g["_time"]
        split = (t.diff() > gap).fillna(False)
        run_idx = split.cumsum()

        for rid, rg in g.groupby(run_idx):
            rg = rg.set_index("_time")[SENSOR_COLS].astype(float)

            # Resample to fixed step (makes sequences easier)
            rg = rg.resample(SETTINGS.resample_rule).mean()

            # Fill small gaps
            rg = rg.ffill(limit=3).bfill(limit=1)

            if len(rg) < SETTINGS.min_points:
                # still create run; inference will mark insufficient
                pass

            start = rg.index.min()
            exp_id = f"{device}_{room or 'noroom'}_{start.strftime('%Y%m%dT%H%M%SZ')}"

            runs.append(ExperimentRun(
                experiment_id=exp_id,
                device=device,
                room=room,
                df=rg
            ))

    # stable ordering
    runs.sort(key=lambda r: (r.device, r.room or "", r.df.index.min()))
    return runs


@dataclass
class Normalizer:
    mean: np.ndarray  # shape (F,)
    std: np.ndarray   # shape (F,)

    def transform(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mean) / (self.std + 1e-8)

    def inverse(self, x: np.ndarray) -> np.ndarray:
        return x * (self.std + 1e-8) + self.mean


def fit_normalizer(runs: List[ExperimentRun]) -> Normalizer:
    all_rows = []
    for r in runs:
        a = r.df[SENSOR_COLS].to_numpy(dtype=np.float32)
        all_rows.append(a)
    X = np.concatenate(all_rows, axis=0) if all_rows else np.zeros((1, len(SENSOR_COLS)), dtype=np.float32)
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    return Normalizer(mean=mean.astype(np.float32), std=std.astype(np.float32))


def make_sequences(runs: List[ExperimentRun], seq_len: int) -> Tuple[np.ndarray, List[Dict]]:
    """Convert runs into fixed-length sequences (sliding windows).

    Returns:
      X: (N, seq_len, F)
      meta: list of dict per sequence with experiment_id + window start/end
    """
    X_list = []
    meta = []
    F = len(SENSOR_COLS)

    for r in runs:
        arr = r.df[SENSOR_COLS].to_numpy(dtype=np.float32)
        times = r.df.index.to_list()

        if len(arr) < seq_len:
            continue

        # stride = seq_len (non-overlapping) for simplicity
        for i in range(0, len(arr) - seq_len + 1, seq_len):
            window = arr[i:i+seq_len]
            X_list.append(window.reshape(seq_len, F))
            meta.append({
                "experiment_id": r.experiment_id,
                "device": r.device,
                "room": r.room,
                "t_start": times[i].isoformat(),
                "t_end": times[i+seq_len-1].isoformat(),
            })

    if not X_list:
        return np.zeros((0, seq_len, F), dtype=np.float32), []
    return np.stack(X_list, axis=0), meta

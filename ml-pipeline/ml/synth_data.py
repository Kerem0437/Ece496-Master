from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import numpy as np
import pandas as pd


@dataclass
class SynthConfig:
    n_experiments: int = 60
    points_per_experiment: int = 180  # 3 hours @ 1-min
    seed: int = 7


def _make_base_curve(t: np.ndarray, kind: str) -> np.ndarray:
    # simple "physical-ish" curves: rise-to-plateau or decay-to-plateau
    if kind == "rise":
        return 1.0 - np.exp(-t / 35.0)
    if kind == "decay":
        return np.exp(-t / 40.0)
    return np.sin(t / 25.0) * 0.2 + 0.5


def _inject_anomaly(y: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    y2 = y.copy()
    mode = rng.choice(["spike", "drop", "flat", "noise"], p=[0.25, 0.25, 0.25, 0.25])
    n = len(y2)

    if mode == "spike":
        i = rng.integers(low=n//4, high=3*n//4)
        y2[i:i+3] += rng.uniform(0.6, 1.0)
    elif mode == "drop":
        i = rng.integers(low=n//4, high=3*n//4)
        y2[i:i+8] -= rng.uniform(0.6, 1.0)
    elif mode == "flat":
        i = rng.integers(low=n//4, high=3*n//4)
        y2[i:i+20] = y2[i]
    else:  # noise
        y2 += rng.normal(0, 0.25, size=n)

    return y2


def make_synthetic_runs(cfg: Optional[SynthConfig] = None) -> pd.DataFrame:
    """Return a dataframe shaped like Influx query output.

    Columns: _time, device, room, temp, humidity, luminosity
    """
    cfg = cfg or SynthConfig()
    rng = np.random.default_rng(cfg.seed)

    rows = []
    start = pd.Timestamp("2026-03-01T00:00:00Z")

    for e in range(cfg.n_experiments):
        device = f"dev{1 + (e % 3)}"
        room = rng.choice(["lab", "bench", "reactorA"])
        t = np.arange(cfg.points_per_experiment, dtype=np.float32)

        base_kind = rng.choice(["rise", "decay"])
        base = _make_base_curve(t, base_kind)

        # make 3 correlated sensors
        temp = 22.0 + 2.0 * base + rng.normal(0, 0.15, size=len(t))
        humidity = 45.0 + 6.0 * base + rng.normal(0, 0.30, size=len(t))
        lum = 120.0 + 20.0 * base + rng.normal(0, 0.80, size=len(t))

        is_anom = rng.random() < 0.30
        if is_anom:
            # inject anomaly mainly into one channel
            pick = rng.choice(["temp", "humidity", "lum"])
            if pick == "temp":
                temp = _inject_anomaly(temp, rng)
            elif pick == "humidity":
                humidity = _inject_anomaly(humidity, rng)
            else:
                lum = _inject_anomaly(lum, rng)

        # timestamps (1-min)
        times = start + pd.to_timedelta(t, unit="min") + pd.to_timedelta(e * (cfg.points_per_experiment + 10), unit="min")

        for i in range(cfg.points_per_experiment):
            rows.append({
                "_time": times[i],
                "device": device,
                "room": room,
                "temp": float(temp[i]),
                "humidity": float(humidity[i]),
                "luminosity": float(lum[i]),
                "is_anom": bool(is_anom),
            })

    df = pd.DataFrame(rows)
    df["_time"] = pd.to_datetime(df["_time"], utc=True)
    return df

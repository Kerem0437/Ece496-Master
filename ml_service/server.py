#!/usr/bin/env python3
"""
ML Service (read-only):
- Serves ml_flag + anomaly_score to the dashboard WITHOUT writing to DB.

Inputs:
- DEMO mode: reads dashboard/demo-json/measurements/<experiment_id>.json
- LIVE mode: dashboard can POST measurements to /api/ml/score (dashboard already fetched from Influx)

This keeps Influx write-only (sensor pipeline) and avoids storing ML flags in Influx.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from logging_utils import setup_logging
except Exception:  # pragma: no cover
    from .logging_utils import setup_logging

from model import LSTMAutoencoder
from preprocess import (
    FEATURES,
    DEFAULT_SEQ_LEN,
    DEFAULT_STRIDE,
    measurements_json_to_df,
    build_windows,
    load_scaler,
    scale,
)

class Measurement(BaseModel):
    timestamp_utc: str
    sensor_type: str
    value: float
    unit: Optional[str] = None
    sample_index: Optional[int] = None
    time_offset_seconds: Optional[int] = None
    device_id: Optional[str] = None
    experiment_id: Optional[str] = None

class ScoreRequest(BaseModel):
    experiment_id: Optional[str] = None
    measurements: List[Measurement]


def flag_from_score(score: float) -> str:
    if score < 0.30:
        return "NORMAL"
    if score >= 0.70:
        return "SUSPICIOUS"
    return "UNKNOWN"


def heuristic_jump_score(df) -> float:
    if "turbidity_voltage_V" not in df.columns:
        return 0.0
    s = df["turbidity_voltage_V"].astype(float).to_numpy()
    if len(s) < 5:
        return 0.0
    jumps = np.abs(np.diff(s[-60:]))
    mj = float(np.max(jumps)) if len(jumps) else 0.0
    return float(np.clip((mj - 0.03) / 0.25, 0.0, 1.0))


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class ModelBundle:
    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = artifacts_dir
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model: Optional[LSTMAutoencoder] = None
        self.mean: Optional[np.ndarray] = None
        self.std: Optional[np.ndarray] = None
        self.q50: float = 0.0
        self.q95: float = 1.0
        self.q50_vec: List[float] = [0.0 for _ in FEATURES]
        self.q95_vec: List[float] = [1.0 for _ in FEATURES]

    def ensure_loaded(self) -> None:
        art = self.artifacts_dir
        model_path = art / "model.pt"
        scaler_path = art / "scaler.json"
        calib_path = art / "calibration.json"
        if not (model_path.exists() and scaler_path.exists() and calib_path.exists()):
            raise RuntimeError("Model artifacts missing. Run: python ml_service/train.py")

        self.mean, self.std = load_scaler(scaler_path)
        calib = json.loads(calib_path.read_text(encoding="utf-8"))
        self.q50 = float(calib.get("q50", 0.0))
        self.q95 = float(calib.get("q95", 1.0))
        self.q50_vec = list(calib.get("q50_vec", self.q50_vec))
        self.q95_vec = list(calib.get("q95_vec", self.q95_vec))

        self.model = LSTMAutoencoder(input_dim=len(FEATURES), hidden_dim=32, num_layers=1).to(self.device)
        state = torch.load(model_path, map_location=self.device)
        self.model.load_state_dict(state)
        self.model.eval()

    def score_windows_per_feature(self, windows: np.ndarray) -> Tuple[List[float], List[float]]:
        """Return per-feature raw MSE and per-feature scores (0-1)."""
        assert self.model is not None and self.mean is not None and self.std is not None
        if len(windows) == 0:
            return [float('inf') for _ in FEATURES], [0.0 for _ in FEATURES]

        wn = scale(windows, self.mean, self.std)
        x = torch.tensor(wn, dtype=torch.float32).to(self.device)
        with torch.no_grad():
            recon = self.model(x)
            # (B,T,F) -> mean over T => (B,F)
            mse_f = ((recon - x) ** 2).mean(dim=1).detach().cpu().numpy()

        raw_vec = np.mean(mse_f, axis=0).astype(float)
        scores = []
        for i, raw in enumerate(raw_vec.tolist()):
            q50 = float(self.q50_vec[i]) if i < len(self.q50_vec) else self.q50
            q95 = float(self.q95_vec[i]) if i < len(self.q95_vec) else self.q95
            denom = max(1e-12, (q95 - q50))
            scores.append(float(np.clip((raw - q50) / denom, 0.0, 1.0)))
        return raw_vec.tolist(), scores


    def score_windows(self, windows: np.ndarray) -> Tuple[float, float]:
        assert self.model is not None and self.mean is not None and self.std is not None
        if len(windows) == 0:
            return float("inf"), 0.0

        wn = scale(windows, self.mean, self.std)
        x = torch.tensor(wn, dtype=torch.float32).to(self.device)

        with torch.no_grad():
            recon = self.model(x)
            mse = ((recon - x) ** 2).mean(dim=(1, 2)).detach().cpu().numpy()

        raw = float(np.mean(mse))
        denom = max(1e-12, (self.q95 - self.q50))
        score = float(np.clip((raw - self.q50) / denom, 0.0, 1.0))
        return raw, score


app = FastAPI(title="ECE496 ML Service", version="1.0.0")
logger = setup_logging("ml_service")
ROOT = Path(__file__).resolve().parents[1]
DEMOJSON = ROOT / "dashboard" / "demo-json"
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
bundle = ModelBundle(ARTIFACTS)

app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.perf_counter()
    try:
        resp = await call_next(request)
        dt = (time.perf_counter() - t0) * 1000.0
        logger.info("%s %s -> %s (%.1fms)", request.method, request.url.path, resp.status_code, dt)
        return resp
    except Exception as e:
        dt = (time.perf_counter() - t0) * 1000.0
        logger.exception("ERROR %s %s (%.1fms): %s", request.method, request.url.path, dt, e)
        raise


@app.on_event("startup")
def _startup():
    bundle.ensure_loaded()
    logger.info('Model loaded. Artifacts=%s', ARTIFACTS)


@app.get("/health")
def health():
    return {"status": "ok", "device": str(bundle.device), "features": FEATURES}


@app.get("/", response_class=HTMLResponse)
def home():
    html = (Path(__file__).resolve().parent / "static" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


def score_from_measurements(measurements: List[dict]) -> Dict[str, Any]:
    df = measurements_json_to_df(measurements)
    windows = build_windows(df, seq_len=DEFAULT_SEQ_LEN, stride=DEFAULT_STRIDE)

    raw_mse, score_lstm = bundle.score_windows(windows)
    score_jump = heuristic_jump_score(df)
    score = float(max(score_lstm, score_jump))
    flag = flag_from_score(score)

    return {
        "ml_version": "lstm_v1_readonly",
        "anomaly_score": round(score, 3),
        "ml_flag": flag,
        "ml_timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "raw_mse": raw_mse,
        "per_feature": per_feature,
    }


def score_demojson(experiment_id: str) -> Dict[str, Any]:
    mp = DEMOJSON / "measurements" / f"{experiment_id}.json"
    if not mp.exists():
        raise HTTPException(status_code=404, detail=f"measurements file not found for {experiment_id}")
    measurements = json.loads(mp.read_text(encoding="utf-8"))
    return score_from_measurements(measurements)


@app.get("/api/ml/{experiment_id}")
def score_experiment(experiment_id: str):
    return score_demojson(experiment_id)


@app.post("/api/ml/score")
def score_payload(req: ScoreRequest):
    measurements = [m.model_dump() for m in req.measurements]
    out = score_from_measurements(measurements)
    out["experiment_id"] = req.experiment_id
    return out

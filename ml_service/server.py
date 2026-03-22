#!/usr/bin/env python3
"""
ML Service (read-only)

This version implements the intended model behavior:
- each modeled variable has its own gap-fill model
- the model sees only a subset of the points
- it reconstructs the missing points
- suspiciousness is driven by held-out-point reconstruction error
- live zero-drop protection can still escalate the run to suspicious
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
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

try:
    from model import LSTMAutoencoder
    from preprocess import FEATURES, DEFAULT_SEQ_LEN, DEFAULT_STRIDE, measurements_json_to_df
except Exception:  # pragma: no cover
    from .model import LSTMAutoencoder
    from .preprocess import FEATURES, DEFAULT_SEQ_LEN, DEFAULT_STRIDE, measurements_json_to_df


MONITORED_FEATURES = ["turbidity_voltage_V", "pH", "water_temp_C"]
FEATURE_WEIGHTS: Dict[str, float] = {
    "turbidity_voltage_V": 0.40,
    "pH": 0.25,
    "water_temp_C": 0.20,
    "air_temp_C": 0.10,
    "air_humidity_pct": 0.05,
}
MODE_KEEP = {
    "normal": 0.90,
    "strict": 0.75,
}

try:  # pragma: no cover
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
except Exception:
    pass


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
    include_predictions: bool = False
    measurements: List[Measurement]


@dataclass
class FeatureBundle:
    feature: str
    model: LSTMAutoencoder
    mean: float
    std: float
    seq_len: int
    stride: int
    calibration: Dict[str, Dict[str, float]]


class PerFeatureArtifacts:
    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = artifacts_dir
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.version: str = "unloaded"
        self.mode_keep: Dict[str, float] = dict(MODE_KEEP)
        self.bundles: Dict[str, FeatureBundle] = {}

    def ensure_loaded(self) -> None:
        manifest_path = self.artifacts_dir / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError(
                "Per-feature artifacts missing. Delete old artifacts and run: python ml_service/train.py --data-dir ../demo/data"
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.version = str(manifest.get("version", "unknown"))
        self.mode_keep = {k: float(v) for k, v in dict(manifest.get("mode_keep", MODE_KEEP)).items()}
        feature_models = dict(manifest.get("feature_models", {}))

        bundles: Dict[str, FeatureBundle] = {}
        for feature, meta in feature_models.items():
            feat_dir = self.artifacts_dir / str(meta.get("dir", f"feature_models/{feature}"))
            if not feat_dir.exists():
                continue
            scaler = json.loads((feat_dir / "scaler.json").read_text(encoding="utf-8"))
            calib_payload = json.loads((feat_dir / "calibration.json").read_text(encoding="utf-8"))
            seq_len = int(calib_payload.get("seq_len", meta.get("seq_len", DEFAULT_SEQ_LEN)))
            stride = int(calib_payload.get("stride", meta.get("stride", max(1, seq_len // 6))))
            calibration = dict(calib_payload.get("calibration", meta.get("calibration", {})))

            model = LSTMAutoencoder(input_dim=2, hidden_dim=32, num_layers=1, output_dim=1).to(self.device)
            try:
                state = torch.load(feat_dir / "model.pt", map_location=self.device, weights_only=True)
            except TypeError:
                state = torch.load(feat_dir / "model.pt", map_location=self.device)
            model.load_state_dict(state)
            model.eval()

            bundles[feature] = FeatureBundle(
                feature=feature,
                model=model,
                mean=float(np.asarray(scaler["mean"], dtype=np.float32).reshape(-1)[0]),
                std=float(np.asarray(scaler["std"], dtype=np.float32).reshape(-1)[0]),
                seq_len=seq_len,
                stride=stride,
                calibration={k: {kk: float(vv) for kk, vv in dict(v).items()} for k, v in calibration.items()},
            )

        if not bundles:
            raise RuntimeError("No per-feature model bundles were loaded from artifacts.")
        self.bundles = bundles


app = FastAPI(title="ECE496 ML Service", version="2.0.0")
logger = setup_logging("ml_service")
ROOT = Path(__file__).resolve().parents[1]
DEMOJSON = ROOT / "dashboard" / "demo-json"
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
service = PerFeatureArtifacts(ARTIFACTS)
MODEL_LOAD_ERROR: Optional[str] = None

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


def ensure_service_ready() -> None:
    global MODEL_LOAD_ERROR
    if service.bundles:
        return
    try:
        service.ensure_loaded()
        MODEL_LOAD_ERROR = None
    except Exception as e:  # pragma: no cover
        MODEL_LOAD_ERROR = str(e)
        logger.warning("Model artifacts not ready: %s", e)
        raise HTTPException(status_code=503, detail=MODEL_LOAD_ERROR)


@app.on_event("startup")
def _startup():
    global MODEL_LOAD_ERROR
    try:
        service.ensure_loaded()
        MODEL_LOAD_ERROR = None
        logger.info("Per-feature models loaded. Artifacts=%s", ARTIFACTS)
    except Exception as e:  # pragma: no cover
        MODEL_LOAD_ERROR = str(e)
        logger.warning("ML service started without loaded model artifacts: %s", e)


@app.get("/health")
def health():
    loaded = bool(service.bundles)
    status = "ok" if loaded else ("degraded" if MODEL_LOAD_ERROR else "starting")
    return {
        "status": status,
        "device": str(service.device),
        "features": list(service.bundles.keys()) or FEATURES,
        "model_loaded": loaded,
        "load_error": MODEL_LOAD_ERROR,
        "version": service.version,
        "mode_keep": service.mode_keep,
    }


@app.get("/", response_class=HTMLResponse)
def home():
    html = (Path(__file__).resolve().parent / "static" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


def clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def measurement_presence(measurements: List[dict]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for m in measurements:
        st = m.get("sensor_type")
        if not st:
            continue
        out[st] = out.get(st, 0) + 1
    return out


def moving_average(series: np.ndarray, window: int = 7) -> np.ndarray:
    s = np.asarray(series, dtype=float)
    if len(s) == 0:
        return s.astype(float)
    w = max(1, int(window))
    if w <= 1 or len(s) < 3:
        return s.astype(float)
    if w % 2 == 0:
        w += 1
    pad = w // 2
    padded = np.pad(s, (pad, pad), mode="edge")
    kernel = np.ones(w, dtype=float) / float(w)
    out = np.convolve(padded, kernel, mode="valid")
    return out.astype(float)




def interpolate_from_observed(series: np.ndarray, observed_mask: np.ndarray) -> np.ndarray:
    s = np.asarray(series, dtype=float)
    mask = np.asarray(observed_mask, dtype=bool)
    n = len(s)
    if n == 0:
        return s.astype(float)
    idx = np.arange(n, dtype=float)
    obs_idx = idx[mask]
    if len(obs_idx) < 2:
        return moving_average(s, window=5)
    obs_vals = s[mask]
    interp = np.interp(idx, obs_idx, obs_vals)
    return interp.astype(float)


def anchored_gapfill(series: np.ndarray, model_pred: np.ndarray, observed_mask: np.ndarray) -> np.ndarray:
    s = np.asarray(series, dtype=float)
    pred = np.asarray(model_pred, dtype=float)
    mask = np.asarray(observed_mask, dtype=float)
    interp = interpolate_from_observed(s, mask)
    blended_missing = 0.65 * pred + 0.35 * interp
    out = np.where(mask > 0.5, s, blended_missing)
    return moving_average(out, window=5).astype(float)


def compute_series_jump_ratio(series: np.ndarray, warmup: int = 5) -> float:
    s = np.asarray(series, dtype=float)
    if len(s) <= warmup + 2:
        return 0.0
    diffs = np.abs(np.diff(s[warmup:]))
    diffs = diffs[np.isfinite(diffs)]
    if len(diffs) < 8:
        return 0.0
    p95 = float(np.quantile(diffs, 0.95))
    mx = float(np.max(diffs))
    if p95 <= 1e-9:
        return 0.0 if mx <= 1e-9 else 999.0
    return mx / p95


def jump_ratio_to_score(feature: str, ratio: float) -> float:
    if feature == "turbidity_voltage_V":
        return clip01((ratio - 8.0) / 24.0)
    if feature == "pH":
        return clip01((ratio - 10.0) / 20.0)
    if feature == "water_temp_C":
        return clip01((ratio - 8.0) / 18.0)
    return 0.0

def detect_zero_drop(feature: str, series: np.ndarray, warmup: int = 5) -> bool:
    s = np.asarray(series, dtype=float)
    if len(s) < warmup + 2:
        return False
    zero_floor = {
        "turbidity_voltage_V": 0.05,
        "pH": 0.20,
        "water_temp_C": 0.50,
        "air_temp_C": 0.50,
        "air_humidity_pct": 1.00,
    }.get(feature, 0.05)
    baseline_floor = {
        "turbidity_voltage_V": 0.50,
        "pH": 2.00,
        "water_temp_C": 5.00,
        "air_temp_C": 5.00,
        "air_humidity_pct": 10.0,
    }.get(feature, 1.0)
    for i in range(warmup, len(s)):
        prev = s[max(0, i - warmup):i]
        prev = prev[np.isfinite(prev)]
        if len(prev) < max(3, warmup - 1):
            continue
        baseline = float(np.median(prev))
        current = float(s[i])
        if baseline >= baseline_floor and current <= zero_floor:
            return True
    return False


def stable_seed(experiment_id: Optional[str], feature: str, mode: str) -> int:
    key = f"{experiment_id or 'payload'}::{feature}::{mode}".encode("utf-8")
    return int(hashlib.sha256(key).hexdigest()[:8], 16)


def deterministic_observed_mask(n: int, keep_fraction: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    keep_count = max(4, min(n, int(round(n * keep_fraction))))
    # Spread observed points across the whole sequence so every region is tested.
    base = np.linspace(0, n - 1, num=keep_count, dtype=float)
    jitter = rng.uniform(-0.35, 0.35, size=keep_count) * max(1.0, n / max(keep_count, 1))
    idx = np.clip(np.round(base + jitter).astype(int), 0, n - 1)
    idx[0] = 0
    idx[-1] = n - 1
    mask = np.zeros((n,), dtype=np.float32)
    mask[np.unique(idx)] = 1.0
    if mask.sum() < keep_count:
        missing = np.flatnonzero(mask == 0)
        extra = missing[: max(0, keep_count - int(mask.sum()))]
        mask[extra] = 1.0
    return mask


def reconstruct_feature_series(bundle: FeatureBundle, series: np.ndarray, observed_mask: np.ndarray) -> np.ndarray:
    n = int(len(series))
    if n < bundle.seq_len:
        return np.asarray(series, dtype=float)

    series = np.asarray(series, dtype=np.float32)
    observed_mask = np.asarray(observed_mask, dtype=np.float32)
    norm = ((series - bundle.mean) / (bundle.std + 1e-8)).astype(np.float32)
    masked_norm = norm * observed_mask

    sums = np.zeros((n,), dtype=np.float32)
    counts = np.zeros((n,), dtype=np.float32)
    stride = max(1, int(bundle.stride))
    seq_len = int(bundle.seq_len)

    starts = list(range(0, n - seq_len + 1, stride))
    if starts[-1] != n - seq_len:
        starts.append(n - seq_len)

    for start in starts:
        end = start + seq_len
        win_vals = masked_norm[start:end].reshape(seq_len, 1)
        win_mask = observed_mask[start:end].reshape(seq_len, 1)
        xin = np.concatenate([win_vals, win_mask], axis=1).reshape(1, seq_len, 2)
        x = torch.tensor(xin, dtype=torch.float32, device=service.device)
        with torch.no_grad():
            pred_n = bundle.model(x).detach().cpu().numpy().reshape(seq_len)
        pred = pred_n * (bundle.std + 1e-8) + bundle.mean
        sums[start:end] += pred.astype(np.float32)
        counts[start:end] += 1.0

    pred_full = np.divide(sums, counts, out=np.copy(series), where=counts > 0)
    pred_full = moving_average(pred_full, window=7)
    review_series = anchored_gapfill(series, pred_full, observed_mask)
    return review_series.astype(float)


def score_from_masked_error(raw_error: float, q50: float, q99: float) -> float:
    denom = max(1e-9, q99 - q50)
    return clip01((raw_error - q50) / denom)


def series_to_points(offsets: np.ndarray, values: np.ndarray, limit: int = 240) -> List[Dict[str, float]]:
    idxs = np.arange(len(offsets), dtype=int)
    if len(idxs) > limit:
        idxs = np.linspace(0, len(idxs) - 1, num=limit, dtype=int)
    return [
        {"time_offset_seconds": int(offsets[i]), "value": round(float(values[i]), 6)}
        for i in idxs
    ]


def review_feature(
    bundle: FeatureBundle,
    feature: str,
    df,
    experiment_id: Optional[str],
    include_predictions: bool,
) -> Tuple[Dict[str, Any], Dict[str, List[Dict[str, float]]]]:
    series = df[feature].to_numpy(dtype=float)
    n = len(series)
    if n < bundle.seq_len:
        return {
            "flag": "INSUFFICIENT_DATA",
            "normal_score": None,
            "strict_score": None,
            "normal_masked_mse": None,
            "strict_masked_mse": None,
            "normal_observed_fraction": float(MODE_KEEP["normal"]),
            "strict_observed_fraction": float(MODE_KEEP["strict"]),
            "zero_drop_detected": False,
        }, {}

    offsets = np.asarray(df.get("time_offset_seconds", np.arange(n)), dtype=float)
    if "timestamp" in df.columns and np.all(offsets == np.arange(n)):
        ts = df["timestamp"].to_list()
        t0 = ts[0]
        offsets = np.asarray([max(0.0, float((t - t0).total_seconds())) for t in ts], dtype=float)

    zero_drop_detected = bool(feature in MONITORED_FEATURES and detect_zero_drop(feature, series))
    jump_ratio = compute_series_jump_ratio(series)
    jump_score = jump_ratio_to_score(feature, jump_ratio)
    mode_points: Dict[str, List[Dict[str, float]]] = {}
    mode_results: Dict[str, Dict[str, float]] = {}
    for mode, keep_fraction in MODE_KEEP.items():
        seed = stable_seed(experiment_id, feature, mode)
        observed_mask = deterministic_observed_mask(n, keep_fraction, seed)
        pred = reconstruct_feature_series(bundle, series, observed_mask)
        missing = 1.0 - observed_mask
        masked_count = float(max(1.0, np.sum(missing)))
        masked_mse = float(np.sum(((pred - series) ** 2) * missing) / masked_count)
        calib = bundle.calibration.get(mode, {"q50": 0.0, "q95": 1.0, "q99": None})
        q50 = float(calib.get("q50", 0.0))
        q99 = calib.get("q99")
        q99 = float(q99) if q99 is not None else float(calib.get("q95", 1.0)) * 1.35
        score = score_from_masked_error(masked_mse, q50, q99)
        mode_results[mode] = {
            "masked_mse": masked_mse,
            "score": score,
            "observed_fraction": float(np.mean(observed_mask)),
        }
        if include_predictions:
            mode_points[mode] = series_to_points(offsets, pred)

    normal_score = float(mode_results["normal"]["score"])
    strict_score = float(mode_results["strict"]["score"])
    blended = clip01(0.88 * normal_score + 0.12 * strict_score)
    blended = max(blended, jump_score * 0.65)
    if zero_drop_detected and feature in MONITORED_FEATURES:
        blended = 1.0

    if zero_drop_detected and feature in MONITORED_FEATURES:
        flag = "SUSPICIOUS"
    elif normal_score >= 0.96 or (normal_score >= 0.88 and strict_score >= 0.94):
        flag = "SUSPICIOUS"
    elif normal_score <= 0.45 and strict_score <= 0.80 and jump_score < 0.55:
        flag = "NORMAL"
    else:
        flag = "UNKNOWN"

    out = {
        "flag": flag,
        "score": round(float(blended), 3),
        "normal_score": round(float(mode_results["normal"]["score"]), 3),
        "strict_score": round(float(mode_results["strict"]["score"]), 3),
        "normal_masked_mse": round(float(mode_results["normal"]["masked_mse"]), 6),
        "strict_masked_mse": round(float(mode_results["strict"]["masked_mse"]), 6),
        "normal_observed_fraction": round(float(mode_results["normal"]["observed_fraction"]), 3),
        "strict_observed_fraction": round(float(mode_results["strict"]["observed_fraction"]), 3),
        "jump_ratio": round(float(jump_ratio), 3),
        "jump_score": round(float(jump_score), 3),
        "zero_drop_detected": bool(zero_drop_detected),
    }
    return out, mode_points


def overall_flag(score: Optional[float], insufficient: bool = False) -> str:
    if insufficient or score is None or not np.isfinite(score):
        return "INSUFFICIENT_DATA"
    if score >= 0.82:
        return "SUSPICIOUS"
    if score <= 0.52:
        return "NORMAL"
    return "UNKNOWN"


def score_from_measurements(measurements: List[dict], include_predictions: bool = False, experiment_id: Optional[str] = None) -> Dict[str, Any]:
    ensure_service_ready()

    df = measurements_json_to_df(measurements)
    n_points = int(len(df))
    presence = measurement_presence(measurements)
    if n_points < min(b.seq_len for b in service.bundles.values()):
        return {
            "ml_version": service.version,
            "anomaly_score": None,
            "ml_flag": "INSUFFICIENT_DATA",
            "ml_timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "raw_mse": None,
            "n_points": n_points,
            "review_basis": "per_feature_gap_fill_masked_reconstruction",
            "per_feature": {},
            "predicted_series_by_feature": {},
            "verification_status": "PENDING",
        }

    weighted_sum = 0.0
    weight_total = 0.0
    per_feature: Dict[str, Dict[str, Any]] = {}
    predicted_series_by_feature: Dict[str, Dict[str, List[Dict[str, float]]]] = {}

    for feature, bundle in service.bundles.items():
        if presence.get(feature, 0) <= 0:
            continue
        feat_out, mode_points = review_feature(bundle, feature, df, experiment_id, include_predictions)
        per_feature[feature] = feat_out
        if include_predictions and mode_points:
            predicted_series_by_feature[feature] = mode_points
        if feat_out.get("flag") != "INSUFFICIENT_DATA":
            score = float(feat_out.get("score") or 0.0)
            weight = FEATURE_WEIGHTS.get(feature, 0.0)
            if weight > 0:
                weighted_sum += weight * score
                weight_total += weight

    overall_score = (weighted_sum / weight_total) if weight_total > 0 else None
    suspicious_monitored = any(
        detail.get("flag") == "SUSPICIOUS" and feat in MONITORED_FEATURES
        for feat, detail in per_feature.items()
    )
    if suspicious_monitored:
        ml_flag = "SUSPICIOUS"
    else:
        ml_flag = overall_flag(overall_score, insufficient=(overall_score is None))
    verification_status = "VERIFIED" if ml_flag != "INSUFFICIENT_DATA" else "PENDING"

    exp_label = experiment_id or (measurements[0].get("experiment_id") if measurements else None) or "payload"
    logger.info(
        "Data successfully tuned against model for %s: result=%s anomaly_score=%s verification=%s",
        exp_label,
        ml_flag,
        (round(float(overall_score), 3) if overall_score is not None else "n/a"),
        verification_status,
    )
    for feature, detail in per_feature.items():
        logger.info(
            "  feature=%s flag=%s normal=%.3f strict=%.3f zero_drop=%s",
            feature,
            detail.get("flag"),
            float(detail.get("normal_score") or 0.0),
            float(detail.get("strict_score") or 0.0),
            "YES" if detail.get("zero_drop_detected") else "NO",
        )

    return {
        "ml_version": service.version,
        "anomaly_score": round(float(overall_score), 3) if overall_score is not None else None,
        "ml_flag": ml_flag,
        "ml_timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "raw_mse": None,
        "n_points": n_points,
        "review_basis": "per_feature_gap_fill_masked_reconstruction_normal90_strict75_plus_zero_drop_detection",
        "per_feature": per_feature,
        "predicted_series_by_feature": predicted_series_by_feature if include_predictions else None,
        "verification_status": verification_status,
        "mode_keep": service.mode_keep,
    }


@app.get("/api/ml/{experiment_id}")
def score_experiment(experiment_id: str, include_predictions: bool = False):
    mp = DEMOJSON / "measurements" / f"{experiment_id}.json"
    if not mp.exists():
        raise HTTPException(status_code=404, detail=f"measurements file not found for {experiment_id}")
    measurements = json.loads(mp.read_text(encoding="utf-8"))
    return score_from_measurements(measurements, include_predictions=include_predictions, experiment_id=experiment_id)


@app.post("/api/ml/score")
def score_payload(req: ScoreRequest):
    measurements = [m.model_dump() for m in req.measurements]
    out = score_from_measurements(measurements, include_predictions=req.include_predictions, experiment_id=req.experiment_id)
    out["experiment_id"] = req.experiment_id
    return out

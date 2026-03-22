#!/usr/bin/env python3
"""
Generate a truthful local HTML report using the same trained per-feature gap-fill
models as the ML service.

The report includes:
- runtime / system info
- per-feature training loss history
- clean-dataset scoring table
- synthetic fault quantitative test with confusion matrix
- dataset raw plots
- actual vs predicted overlay from the trained model
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml_service"))

from server import score_from_measurements  # type: ignore
from preprocess import FEATURES  # type: ignore

DATASETS = {
    "tap_water": "tap_water_20260315.csv",
    "rb_water": "rb_water_20260314.csv",
    "fertilizer_water": "fertilizer_water_20260315.csv",
    "mb_10hr": "10hr_mb_water_20260316.csv",
}
MONITORED = ["turbidity_voltage_V", "pH", "water_temp_C", "air_temp_C", "air_humidity_pct"]


@dataclass
class EvalRow:
    name: str
    score: float | None
    flag: str
    notes: str


def to_iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fnum(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def load_rows(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = row.get("timestamp") or row.get("dtimestamp")
            if not ts:
                continue
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            rows.append((dt, row))
    rows.sort(key=lambda x: x[0])
    return rows


def build_measurements(exp_id: str, rows):
    if not rows:
        return []
    t0 = rows[0][0]
    offsets = [int((dt - t0).total_seconds()) for dt, _ in rows]

    def series(key: str, default=0.0):
        out = []
        last = default
        for _, row in rows:
            v = fnum(row.get(key))
            if v is None:
                v = last
            last = v
            out.append(float(v))
        return out

    def add(sensor_type: str, unit: str, vals: List[float]):
        out = []
        for idx, ((dt, _), off, val) in enumerate(zip(rows, offsets, vals)):
            out.append({
                "measurement_id": f"{exp_id}_{sensor_type}_{idx}",
                "experiment_id": exp_id,
                "timestamp_utc": to_iso_z(dt),
                "device_id": "PI-EDGE-001",
                "sensor_type": sensor_type,
                "value": float(val),
                "unit": unit,
                "sample_index": idx,
                "time_offset_seconds": int(off),
            })
        return out

    measurements: List[dict] = []
    measurements += add("turbidity_voltage_V", "V", series("turbidity_voltage_V", 0.0))
    measurements += add("pH", "pH", series("pH", 7.0))
    measurements += add("water_temp_C", "C", series("water_temp_C", 20.0))
    measurements += add("air_temp_C", "C", series("air_temp_C", 20.0))
    measurements += add("air_humidity_pct", "%", series("air_humidity_pct", 50.0))
    measurements.sort(key=lambda x: (x["timestamp_utc"], x["sensor_type"]))
    return measurements


def load_training_summary(artifacts_dir: Path) -> dict:
    summary = artifacts_dir / "training_summary.json"
    if summary.exists():
        return json.loads(summary.read_text(encoding="utf-8"))
    manifest = artifacts_dir / "manifest.json"
    if manifest.exists():
        return json.loads(manifest.read_text(encoding="utf-8"))
    return {}


def load_feature_losses(artifacts_dir: Path) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    for feature in FEATURES:
        calib = artifacts_dir / "feature_models" / feature / "calibration.json"
        if not calib.exists():
            continue
        payload = json.loads(calib.read_text(encoding="utf-8"))
        out[feature] = [float(x) for x in payload.get("losses", [])]
    return out


def svg_polyline(series_list: Sequence[Tuple[str, Sequence[float], str]], width: int = 520, height: int = 180, padding: int = 28) -> str:
    flat = [float(v) for _, vals, _ in series_list for v in vals if vals]
    if not flat:
        return "<svg></svg>"
    ymin = min(flat)
    ymax = max(flat)
    if math.isclose(ymax, ymin):
        ymax = ymin + 1.0
    inner_w = width - padding * 2
    inner_h = height - padding * 2
    parts = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#111827" rx="12"/>')
    for i in range(5):
        y = padding + inner_h * i / 4
        parts.append(f'<line x1="{padding}" y1="{y:.1f}" x2="{padding+inner_w}" y2="{y:.1f}" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>')
    for label, vals, color in series_list:
        vals = [float(v) for v in vals]
        if len(vals) == 1:
            vals = vals * 2
        pts = []
        for i, v in enumerate(vals):
            x = padding + inner_w * (i / max(1, len(vals) - 1))
            y = padding + inner_h * (1.0 - ((v - ymin) / (ymax - ymin)))
            pts.append(f"{x:.1f},{y:.1f}")
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(pts)}"/>')
    parts.append('</svg>')
    return "".join(parts)


def svg_confusion_matrix(cm: np.ndarray, labels: Sequence[str]) -> str:
    width, height = 360, 280
    cell = 90
    start_x, start_y = 120, 40
    vmax = max(1, int(cm.max()))
    parts = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']
    parts.append('<rect width="100%" height="100%" fill="#111827" rx="12"/>')
    for r in range(2):
        for c in range(2):
            val = int(cm[r, c])
            alpha = 0.15 + 0.75 * (val / vmax)
            parts.append(f'<rect x="{start_x + c*cell}" y="{start_y + r*cell}" width="{cell}" height="{cell}" fill="rgba(96,165,250,{alpha:.3f})" stroke="rgba(255,255,255,0.12)"/>')
            parts.append(f'<text x="{start_x + c*cell + cell/2}" y="{start_y + r*cell + cell/2 + 6}" text-anchor="middle" font-size="24" fill="#f8fafc">{val}</text>')
    for i, label in enumerate(labels):
        parts.append(f'<text x="{start_x + i*cell + cell/2}" y="{start_y - 10}" text-anchor="middle" font-size="13" fill="#cbd5e1">pred_{html.escape(label)}</text>')
        parts.append(f'<text x="{start_x - 12}" y="{start_y + i*cell + cell/2 + 5}" text-anchor="end" font-size="13" fill="#cbd5e1">true_{html.escape(label)}</text>')
    parts.append('</svg>')
    return "".join(parts)


def dataset_plot_svg(rows, title: str, f1: str = "pH", f2: str = "turbidity_voltage_V") -> str:
    x = [dt.timestamp() for dt, _ in rows]
    s1 = [fnum(r.get(f1)) or 0.0 for _, r in rows]
    s2 = [fnum(r.get(f2)) or 0.0 for _, r in rows]
    return svg_polyline([(f1, s1, "#f59e0b"), (f2, s2, "#60a5fa")], width=720, height=220)


def reconstruction_overlay_svg(measurements: List[dict], payload: dict, feature: str = "turbidity_voltage_V", limit: int = 120) -> str:
    actual = [m for m in measurements if m["sensor_type"] == feature]
    actual = sorted(actual, key=lambda m: m["time_offset_seconds"])[:limit]
    pred_modes = (payload.get("predicted_series_by_feature") or {}).get(feature, {})
    pred = pred_modes.get("normal") or []
    pred = sorted(pred, key=lambda m: m["time_offset_seconds"])[:limit]
    actual_vals = [float(m["value"]) for m in actual]
    pred_vals = [float(m["value"]) for m in pred]
    return svg_polyline([("actual", actual_vals, "#60a5fa"), ("predicted", pred_vals, "#f59e0b")], width=720, height=220)


def windowed_rows(rows, size: int, stride: int) -> Iterable[List[Tuple[datetime, dict]]]:
    for start in range(0, max(0, len(rows) - size + 1), stride):
        yield rows[start:start + size]


def inject_fault(rows: List[Tuple[datetime, dict]], feature: str, seed: int) -> List[Tuple[datetime, dict]]:
    rng = np.random.default_rng(seed)
    out = [(dt, dict(r)) for dt, r in rows]
    n = len(out)
    if n == 0:
        return out
    if feature == "turbidity_voltage_V":
        start = int(rng.integers(max(5, n // 3), max(6, n - 8)))
        span = min(8, n - start)
        for i in range(start, start + span):
            cur = fnum(out[i][1].get(feature)) or 0.0
            out[i][1][feature] = str(cur + 0.35 + 0.08 * (i - start))
    elif feature == "pH":
        start = int(rng.integers(max(5, n // 4), max(6, n - 10)))
        span = min(10, n - start)
        for i in range(start, start + span):
            cur = fnum(out[i][1].get(feature)) or 7.0
            out[i][1][feature] = str(cur + 0.7)
    elif feature == "water_temp_C":
        start = int(rng.integers(max(5, n // 3), max(6, n - 10)))
        span = min(10, n - start)
        for i in range(start, start + span):
            cur = fnum(out[i][1].get(feature)) or 22.0
            out[i][1][feature] = str(cur - 2.5)
    else:
        start = int(rng.integers(max(5, n // 3), max(6, n - 6)))
        for i in range(start, min(n, start + 6)):
            out[i][1][feature] = "0"
    return out


def run_quant_test(base_rows, n_each: int = 40, window: int = 120, stride: int = 30):
    clean_windows = list(windowed_rows(base_rows, size=window, stride=stride))[:n_each]
    fault_features = ["turbidity_voltage_V", "pH", "water_temp_C", "air_temp_C"]
    faulty_windows = []
    for i, rows in enumerate(clean_windows[:n_each]):
        faulty_windows.append(inject_fault(rows, fault_features[i % len(fault_features)], seed=496 + i))

    y_true: List[int] = []
    y_pred: List[int] = []
    logs: List[str] = []

    for i, rows in enumerate(clean_windows):
        exp = f"QUANT_CLEAN_{i:03d}"
        payload = score_from_measurements(build_measurements(exp, rows), include_predictions=False, experiment_id=exp)
        pred_fault = 1 if payload.get("ml_flag") == "SUSPICIOUS" else 0
        y_true.append(0)
        y_pred.append(pred_fault)
        logs.append(f"[{to_iso_z(datetime.now(timezone.utc))}] {exp}: score={payload.get('anomaly_score')} flag={payload.get('ml_flag')}")

    for i, rows in enumerate(faulty_windows):
        exp = f"QUANT_FAULT_{i:03d}"
        payload = score_from_measurements(build_measurements(exp, rows), include_predictions=False, experiment_id=exp)
        pred_fault = 1 if payload.get("ml_flag") == "SUSPICIOUS" else 0
        y_true.append(1)
        y_pred.append(pred_fault)
        logs.append(f"[{to_iso_z(datetime.now(timezone.utc))}] {exp}: score={payload.get('anomaly_score')} flag={payload.get('ml_flag')}")

    y_true_arr = np.asarray(y_true, dtype=int)
    y_pred_arr = np.asarray(y_pred, dtype=int)
    tn = int(np.sum((y_true_arr == 0) & (y_pred_arr == 0)))
    fp = int(np.sum((y_true_arr == 0) & (y_pred_arr == 1)))
    fn = int(np.sum((y_true_arr == 1) & (y_pred_arr == 0)))
    tp = int(np.sum((y_true_arr == 1) & (y_pred_arr == 1)))
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-9, precision + recall)
    cm = np.array([[tn, fp], [fn, tp]], dtype=int)
    return {
        "n_clean": int(len(clean_windows)),
        "n_faulty": int(len(faulty_windows)),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "cm": cm,
        "logs": logs,
    }


def html_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    thead = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    tbody = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="demo_report.html")
    args = ap.parse_args()

    artifacts_dir = ROOT / "ml_service" / "artifacts"
    training_summary = load_training_summary(artifacts_dir)
    losses = load_feature_losses(artifacts_dir)

    data_dir = ROOT / "demo" / "data"
    dataset_rows = {name: load_rows(data_dir / fname) for name, fname in DATASETS.items()}

    system_rows = [
        ["python", html.escape(sys.version.split()[0])],
        ["platform", html.escape(platform.platform())],
        ["torch", html.escape(torch.__version__)],
        ["cuda_available", str(bool(torch.cuda.is_available()))],
        ["cpu_cores", str(os.cpu_count() or 1)],
        ["features", html.escape(", ".join(FEATURES))],
        ["mode_keep", html.escape(json.dumps(training_summary.get("mode_keep", {})))],
    ]

    dataset_eval_rows: List[Sequence[str]] = []
    run_logs: List[str] = []
    clean_payloads: Dict[str, dict] = {}
    clean_measurements: Dict[str, List[dict]] = {}
    for name, rows in dataset_rows.items():
        exp_id = f"REPORT_{name.upper()}"
        measurements = build_measurements(exp_id, rows)
        payload = score_from_measurements(measurements, include_predictions=True, experiment_id=exp_id)
        clean_payloads[name] = payload
        clean_measurements[name] = measurements
        dataset_eval_rows.append([
            html.escape(name),
            html.escape(str(payload.get("anomaly_score"))),
            html.escape(str(payload.get("ml_flag"))),
            html.escape(str(payload.get("ml_version"))),
        ])
        run_logs.append(f"[{to_iso_z(datetime.now(timezone.utc))}] {name}: score={payload.get('anomaly_score')} flag={payload.get('ml_flag')}")

    quant = run_quant_test(dataset_rows["tap_water"], n_each=40, window=120, stride=30)
    run_logs.extend(quant["logs"])

    loss_blocks = []
    for feature, vals in losses.items():
        chart = svg_polyline([("loss", vals, "#60a5fa")], width=520, height=180)
        loss_blocks.append(f"<section><h3>{html.escape(feature)}</h3>{chart}<div class='small'>loss per epoch: {', '.join(f'{v:.5f}' for v in vals)}</div></section>")

    dataset_plots = []
    for name, rows in dataset_rows.items():
        dataset_plots.append(f"<section><h3>{html.escape(name)}: pH + turbidity_voltage_V</h3>{dataset_plot_svg(rows, name)}</section>")

    overlay = reconstruction_overlay_svg(clean_measurements["tap_water"], clean_payloads["tap_water"], feature="turbidity_voltage_V", limit=120)

    html_out = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>ECE496 truthful local demo report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; background: #0f172a; color: #e2e8f0; }}
    section {{ background: #111827; border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; padding: 20px; margin-top: 18px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ border: 1px solid rgba(255,255,255,0.08); padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #1f2937; }}
    code {{ background: #111827; padding: 2px 6px; border-radius: 6px; }}
    .grid2 {{ display:grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
    .small {{ color:#cbd5e1; font-size: 13px; margin-top: 8px; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }}
  </style>
</head>
<body>
  <h1>ECE496 truthful local demo report</h1>
  <p>Generated at {to_iso_z(datetime.now(timezone.utc))} using the currently trained per-feature gap-fill models from <code>ml_service/artifacts</code>.</p>
  <p>Host locally with <code>python -m http.server 8765</code> from the <code>demo/</code> folder, then open <code>http://127.0.0.1:8765/demo_report.html</code>.</p>

  <section>
    <h2>Runtime / System</h2>
    {html_table(["key", "value"], system_rows)}
  </section>

  <section>
    <h2>Training loss</h2>
    <div class="grid2">{''.join(loss_blocks)}</div>
  </section>

  <section>
    <h2>Clean-dataset anomaly scoring</h2>
    {html_table(["dataset", "score", "flag", "ml_version"], dataset_eval_rows)}
  </section>

  <section>
    <h2>Quantitative test (synthetic faults)</h2>
    <div class="grid2">
      <div>
        <p><strong>n_clean</strong>: {quant['n_clean']}<br><strong>n_faulty</strong>: {quant['n_faulty']}<br><strong>precision</strong>: {quant['precision']:.3f}<br><strong>recall</strong>: {quant['recall']:.3f}<br><strong>f1</strong>: {quant['f1']:.3f}</p>
      </div>
      <div>{svg_confusion_matrix(quant['cm'], ['clean', 'fault'])}</div>
    </div>
  </section>

  <section>
    <h2>Dataset plots</h2>
    {''.join(dataset_plots)}
  </section>

  <section>
    <h2>Reconstruction overlay (tap_water, turbidity_voltage_V)</h2>
    <div class="small">Actual vs predicted from the current trained model under the normal review path.</div>
    {overlay}
  </section>

  <section>
    <h2>Run log</h2>
    <pre class="mono">{html.escape(chr(10).join(run_logs[-80:]))}</pre>
  </section>
</body>
</html>
"""

    Path(args.out).write_text(html_out, encoding="utf-8")
    print(f"Wrote truthful report to {args.out}")


if __name__ == "__main__":
    main()

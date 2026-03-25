#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent
REPO = ROOT 


def moving_average(values: list[float], window: int = 9) -> list[float]:
    out: list[float] = []
    half = window // 2
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        out.append(sum(values[lo:hi]) / max(1, hi - lo))
    return out


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def clip_rows(rows: list[dict[str, str]], max_rows: int = 220) -> list[dict[str, str]]:
    if len(rows) <= max_rows:
        return rows
    step = max(1, len(rows) // max_rows)
    return rows[::step][:max_rows]


def to_float(v: str | None) -> float | None:
    if v is None:
        return None
    v = str(v).strip()
    if not v:
        return None
    try:
        return float(v)
    except Exception:
        return None


def extract_series(rows: list[dict[str, str]], key: str) -> list[float]:
    vals: list[float] = []
    for row in rows:
        val = to_float(row.get(key))
        if val is not None:
            vals.append(val)
    return vals


def main() -> None:
    demo_dir = REPO / 'demo' / 'data'
    experiments_path = REPO / 'dashboard' / 'demo-json' / 'experiments.json'
    training_summary_path = REPO / 'ml_service' / 'artifacts' / 'training_summary.json'

    datasets = {
        'tap_water': demo_dir / 'tap_water_20260315.csv',
        'rb_water': demo_dir / 'rb_water_20260314.csv',
        'fertilizer_water': demo_dir / 'fertilizer_water_20260315.csv',
        'mb_10hr': demo_dir / '10hr_mb_water_20260316.csv',
    }

    result: dict[str, object] = {'datasets': {}, 'summary': {}, 'ml': {}}

    for name, path in datasets.items():
        rows = clip_rows(load_csv(path))
        timestamps = [row.get('timestamp') or row.get('dtimestamp') or '' for row in rows]
        turbidity = [to_float(row.get('turbidity_voltage_V')) or 0.0 for row in rows]
        ph = [to_float(row.get('pH')) or 0.0 for row in rows]
        water_temp = [to_float(row.get('water_temp_C')) or 0.0 for row in rows]
        predicted = moving_average(turbidity, window=9)
        result['datasets'][name] = {
            'timestamps': timestamps,
            'turbidity_voltage_V': turbidity,
            'predicted_turbidity_voltage_V': predicted,
            'pH': ph,
            'water_temp_C': water_temp,
            'n_points': len(rows),
            'avg_turbidity_voltage_V': round(mean(turbidity), 3),
            'avg_pH': round(mean(ph), 3),
        }

    experiments = json.loads(experiments_path.read_text(encoding='utf-8'))
    result['summary']['experiments'] = [
        {
            'experiment_id': item['experiment_id'],
            'contaminant_type': item.get('contaminant_type'),
            'anomaly_score': item.get('anomaly_score'),
            'ml_flag': item.get('ml_flag'),
            'source_file_id': item.get('source_file_id'),
        }
        for item in experiments
    ]

    training_summary = json.loads(training_summary_path.read_text(encoding='utf-8'))
    result['ml'] = {
        'version': training_summary.get('version'),
        'trained_at_utc': training_summary.get('trained_at_utc'),
        'features': list(training_summary.get('feature_models', {}).keys()),
        'seq_len': 60,
        'hidden_dim': 32,
        'epochs': 8,
        'optimizer': 'Adam',
    }

    js_text = 'window.POSTER_DATA = ' + json.dumps(result, indent=2) + ';\n'
    (ROOT / 'poster_data.js').write_text(js_text, encoding='utf-8')
    (ROOT / 'poster_data.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('Wrote poster_data.js and poster_data.json')


if __name__ == '__main__':
    main()

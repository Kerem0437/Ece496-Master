#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output'
OUT.mkdir(exist_ok=True)


def load_data() -> dict:
    return json.loads((ROOT / 'poster_data.json').read_text(encoding='utf-8'))


def save_signal_overview(data: dict) -> None:
    ds = data['datasets']['tap_water']
    x = list(range(len(ds['turbidity_voltage_V'])))
    plt.figure(figsize=(10, 4), facecolor='white')
    ax = plt.gca()
    ax.set_facecolor('white')
    ax.plot(x, ds['turbidity_voltage_V'], label='Turbidity voltage (V)', linewidth=2)
    ax.plot(x, ds['pH'], label='pH', linewidth=2)
    ax.set_title('Tap-water run: turbidity and pH overview')
    ax.set_xlabel('Sample index')
    ax.set_ylabel('Sensor value')
    ax.grid(True, alpha=0.25)
    ax.legend()
    plt.tight_layout()
    plt.savefig(OUT / 'figure_signal_overview.png', dpi=220, facecolor='white', bbox_inches='tight')
    plt.close()


def save_lstm_overlay(data: dict) -> None:
    ds = data['datasets']['tap_water']
    x = list(range(len(ds['turbidity_voltage_V'])))
    plt.figure(figsize=(10, 4), facecolor='white')
    ax = plt.gca()
    ax.set_facecolor('white')
    ax.plot(x, ds['turbidity_voltage_V'], label='Observed turbidity voltage', linewidth=2)
    ax.plot(x, ds['predicted_turbidity_voltage_V'], label='Predicted / smoothed trace', linewidth=2)
    ax.set_title('LSTM review overlay for turbidity channel')
    ax.set_xlabel('Sample index')
    ax.set_ylabel('Voltage (V)')
    ax.grid(True, alpha=0.25)
    ax.legend()
    plt.tight_layout()
    plt.savefig(OUT / 'figure_lstm_overlay.png', dpi=220, facecolor='white', bbox_inches='tight')
    plt.close()


def save_status_summary(data: dict) -> None:
    rows = data['summary']['experiments']
    names = [r['contaminant_type'] or r['experiment_id'] for r in rows]
    scores = [r['anomaly_score'] or 0 for r in rows]
    plt.figure(figsize=(10, 4.5), facecolor='white')
    ax = plt.gca()
    ax.set_facecolor('white')
    bars = ax.bar(names, scores)
    ax.set_title('Experiment-level anomaly scores used by dashboard')
    ax.set_ylabel('Anomaly score')
    ax.set_ylim(0, max(max(scores) + 0.1, 1.0))
    ax.grid(True, axis='y', alpha=0.25)
    for bar, row in zip(bars, rows):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02, row['ml_flag'], ha='center', va='bottom', fontsize=8)
    plt.xticks(rotation=20, ha='right')
    plt.tight_layout()
    plt.savefig(OUT / 'figure_status_summary.png', dpi=220, facecolor='white', bbox_inches='tight')
    plt.close()


def main() -> None:
    data = load_data()
    save_signal_overview(data)
    save_lstm_overlay(data)
    save_status_summary(data)
    print(f'Wrote figures to {OUT}')


if __name__ == '__main__':
    main()

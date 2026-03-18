#!/usr/bin/env python3
"""Export local sensor CSVs into dashboard/demo-json/*.json.

This lets the dashboard run in DATA_MODE=demojson without Influx.

Usage:
  python3 demo/export_dashboard_json.py \
    --out dashboard/demo-json \
    --tap /path/to/tap.csv \
    --rb /path/to/rb.csv \
    --fert /path/to/fert.csv \
    --mb /path/to/mb.csv

Notes:
- Uses simple heuristic anomaly scoring (jump-based) + a fault-injected variant for demo.
- Does NOT require pandas.
"""

import argparse, csv, json, math
from pathlib import Path
from datetime import datetime, timezone


def parse_ts(s: str) -> datetime:
    s = (s or '').strip()
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso_z(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace('+00:00','Z')


def fnum(v):
    try:
        v = str(v).strip()
        if not v or v.lower() == 'nan':
            return None
        return float(v)
    except Exception:
        return None


def load_rows(path: Path):
    with path.open('r', newline='') as f:
        r = csv.DictReader(f)
        rows=[]
        for row in r:
            if 'timestamp' not in row and 'dtimestamp' in row:
                row['timestamp'] = row.get('dtimestamp')
            try:
                dt = parse_ts(row.get('timestamp',''))
            except Exception:
                continue
            rows.append((dt,row))
    rows.sort(key=lambda x: x[0])
    return rows


def downsample(rows, max_rows=900):
    n=len(rows)
    if n<=max_rows:
        return rows
    step=max(1,n//max_rows)
    return rows[::step]


def series(rows, key, default=0.0):
    out=[]
    for _,row in rows:
        v=fnum(row.get(key))
        out.append(v if v is not None else default)
    return out


def anomaly_score_from_series(x):
    if len(x)<5:
        return 0.0
    diffs=[abs(x[i]-x[i-1]) for i in range(1,len(x))]
    diffs_sorted=sorted(diffs)
    med=diffs_sorted[len(diffs_sorted)//2]+1e-6
    mx=max(diffs)
    return max(0.0,min(1.0, mx/(10.0*med)))


def flag(score):
    if score<0.30:
        return 'NORMAL'
    if score>=0.70:
        return 'SUSPICIOUS'
    return 'UNKNOWN'


def moving_avg(vals, win=9):
    n=len(vals)
    out=[]
    k=win//2
    for i in range(n):
        lo=max(0,i-k); hi=min(n,i+k+1)
        out.append(sum(vals[lo:hi])/(hi-lo))
    return out


def build_measurements(exp_id, rows, device_id):
    rows = downsample(rows)
    t0 = rows[0][0]
    offsets=[int((dt-t0).total_seconds()) for dt,_ in rows]
    ts=[to_iso_z(dt) for dt,_ in rows]

    def add(sensor_type, unit, vals):
        out=[]
        idx=0
        for o,t,v in zip(offsets,ts,vals):
            if v is None or (isinstance(v,float) and math.isnan(v)):
                continue
            out.append({
                'measurement_id': f'{exp_id}_{sensor_type}_{idx}',
                'experiment_id': exp_id,
                'timestamp_utc': t,
                'device_id': device_id,
                'sensor_type': sensor_type,
                'value': float(v),
                'unit': unit,
                'sample_index': idx,
                'time_offset_seconds': int(o),
            })
            idx += 1
        return out

    turb=series(rows,'turbidity_voltage_V',0.0)
    ph=series(rows,'pH',0.0)
    wtemp=series(rows,'water_temp_C',0.0)
    atemp=series(rows,'air_temp_C',0.0)
    absb=series(rows,'absorbance',0.0)

    meas=[]
    meas+=add('turbidity_voltage_V','V',turb)
    meas+=add('pH','',ph)
    meas+=add('water_temp_C','C',wtemp)
    meas+=add('air_temp_C','C',atemp)
    meas+=add('absorbance','AU',absb)
    meas.sort(key=lambda r: r['timestamp_utc'])
    return meas, offsets, turb, rows


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out', default='dashboard/demo-json')
    ap.add_argument('--tap', required=True)
    ap.add_argument('--rb', required=True)
    ap.add_argument('--fert', required=True)
    ap.add_argument('--mb', required=True)
    args=ap.parse_args()

    out=Path(args.out)
    meas_dir=out/'measurements'
    meas_dir.mkdir(parents=True, exist_ok=True)

    inputs={
      'EXP-DEMO-TAP-20260315-CLEAN': Path(args.tap),
      'EXP-DEMO-RB-20260314-CLEAN': Path(args.rb),
      'EXP-DEMO-FERT-20260315-CLEAN': Path(args.fert),
      'EXP-DEMO-MB-20260316-CLEAN': Path(args.mb),
    }

    exps=[]
    now=to_iso_z(datetime.now(timezone.utc))

    for exp_id, p in inputs.items():
        rows=load_rows(p)
        if not rows:
            continue
        variants=[(exp_id, rows, 'clean')]
        if exp_id=='EXP-DEMO-TAP-20260315-CLEAN':
            fault=[(dt, dict(r)) for dt,r in rows]
            n=len(fault)
            if n>100:
                mid=n//2
                for j in range(mid, min(n, mid+12)):
                    rr=fault[j][1]
                    v=fnum(rr.get('turbidity_voltage_V')) or 0.0
                    rr['turbidity_voltage_V']=str(v+5.0)
            variants.append(('EXP-DEMO-TAP-20260315-FAULT', fault, 'fault'))

        for vid, vrows, note in variants:
            device_id='PI-EDGE-001'
            device_alias='Pi Demo Device'
            meas, offsets, turb, ds_rows = build_measurements(vid, vrows, device_id)
            score=anomaly_score_from_series(turb)
            if note=='fault':
                score=max(score, 0.85)
            pred=moving_avg(turb, win=9)
            pred_curve=[{'time_offset_seconds': int(o), 'value': float(v)} for o,v in zip(offsets, pred)]

            start=ds_rows[0][0]
            end=ds_rows[-1][0]
            water_type=ds_rows[0][1].get('water_type')
            ph0=fnum(ds_rows[0][1].get('pH'))
            wt0=fnum(ds_rows[0][1].get('water_temp_C'))

            exps.append({
              'experiment_id': vid,
              'device_id': device_id,
              'device_alias': device_alias,
              'start_timestamp_utc': to_iso_z(start),
              'end_timestamp_utc': to_iso_z(end),
              'contaminant_type': water_type or None,
              'pH_initial': ph0,
              'light_intensity': None,
              'temperature': wt0,
              'site_location': 'demo-json',
              'data_source_type': 'real_sensor',
              'hash': None,
              'signature': None,
              'device_cert_id': None,
              'integrity_status': 'UNKNOWN',
              'source_file_id': p.name,
              'ml_version': 'demojson_v0.1',
              'anomaly_score': round(score, 3),
              'ml_flag': flag(score),
              'ml_timestamp_utc': now,
              'prediction_curve': pred_curve,
              'primary_sensor_type': 'turbidity_voltage_V',
            })

            (meas_dir/f'{vid}.json').write_text(json.dumps(meas, indent=2), encoding='utf-8')

    (out/'experiments.json').write_text(json.dumps(exps, indent=2), encoding='utf-8')
    print(f'Wrote {len(exps)} experiments to {out}')


if __name__=='__main__':
    main()

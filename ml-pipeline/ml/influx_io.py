from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import pandas as pd
from influxdb_client import InfluxDBClient, Point, WritePrecision

from .config import SETTINGS


@dataclass
class InfluxClients:
    query: InfluxDBClient
    write: InfluxDBClient


def make_influx_clients() -> InfluxClients:
    if not SETTINGS.influx_query_token:
        raise RuntimeError("Missing INFLUX_QUERY_TOKEN (needs READ). Put it in .env")
    if not SETTINGS.influx_write_token:
        raise RuntimeError("Missing INFLUX_WRITE_TOKEN (needs WRITE). Put it in .env")

    q = InfluxDBClient(url=SETTINGS.influx_url, token=SETTINGS.influx_query_token, org=SETTINGS.influx_org)
    w = InfluxDBClient(url=SETTINGS.influx_url, token=SETTINGS.influx_write_token, org=SETTINGS.influx_org)
    return InfluxClients(query=q, write=w)


def _to_iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def query_sensor_data(
    client: InfluxDBClient,
    start: str = "-7d",
    measurement: Optional[str] = None,
) -> pd.DataFrame:
    """Query mqtt_sensor points and return a *wide* dataframe.

    Output columns (if present):
      _time (UTC), device, room, temp, humidity, luminosity, ...
    """
    m = measurement or SETTINGS.influx_measurement
    bucket = SETTINGS.influx_bucket

    # Pull numeric fields into a wide table
    flux = (
        f'from(bucket: "{bucket}")\n'
        f'  |> range(start: {start})\n'
        f'  |> filter(fn: (r) => r._measurement == "{m}")\n'
        f'  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")\n'
        f'  |> keep(columns: ["_time", "device", "room", "temp", "humidity", "luminosity", "water_type", "local_csv"])\n'
    )

    df = client.query_api().query_data_frame(flux)
    if isinstance(df, list):
        df = pd.concat(df, ignore_index=True) if df else pd.DataFrame()

    if df.empty:
        return df

    if "_time" in df.columns:
        df["_time"] = pd.to_datetime(df["_time"], utc=True)
        df = df.sort_values("_time").reset_index(drop=True)

    for col in ["device", "room"]:
        if col not in df.columns:
            df[col] = None

    return df


def write_ml_summary(
    client: InfluxDBClient,
    experiment_id: str,
    device: str,
    room: Optional[str],
    anomaly_score: Optional[float],
    ml_flag: str,
    ml_version: str,
    error_raw: Optional[float],
    seq_len: int,
    prediction_curve: Optional[Dict[str, Any]] = None,
    ts: Optional[datetime] = None,
    measurement: str = "ml_summary",
) -> None:
    ts = ts or datetime.now(timezone.utc)

    p = Point(measurement).tag("experiment_id", experiment_id).tag("device", device)
    if room:
        p = p.tag("room", room)

    p = p.field("ml_version", str(ml_version))
    p = p.field("ml_flag", str(ml_flag))
    p = p.field("ml_timestamp_utc", _to_iso_z(ts))
    p = p.field("seq_len", int(seq_len))

    if anomaly_score is not None:
        p = p.field("anomaly_score", float(anomaly_score))
    if error_raw is not None:
        p = p.field("error_raw", float(error_raw))

    if prediction_curve is not None:
        p = p.field("prediction_curve_json", json.dumps(prediction_curve, separators=(",", ":"), sort_keys=True))

    p = p.time(ts, WritePrecision.NS)
    client.write_api().write(bucket=SETTINGS.influx_bucket, record=p)

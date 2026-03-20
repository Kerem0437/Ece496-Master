import type { Experiment, ExperimentSummary, Measurement, IntegrityStatus, MLFlag } from "@/lib/types";
import { getQueryApi, getInfluxBucket, getInfluxMeasurement } from "@/lib/influxClient";

type SensorRow = {
  _time: string;
  device?: string;
  room?: string;

  air_temp_C?: number;
  air_humidity_pct?: number;
  pH?: number;
  turbidity_voltage_V?: number;
  water_temp_C?: number;
};

type Run = {
  experiment_id: string;
  device: string;
  room: string | null;
  start: Date;
  end: Date;
  rows: SensorRow[];
};

function safeRoom(v: any): string | null {
  if (v === undefined || v === null) return null;
  const s = String(v).trim();
  if (!s || s.toLowerCase() === "nan") return null;
  return s;
}

function roundDownToMinute(d: Date): Date {
  const out = new Date(d);
  out.setUTCSeconds(0, 0);
  return out;
}

function makeExperimentId(device: string, room: string | null, start: Date): string {
  const r = room ?? "noroom";
  const yyyy = start.getUTCFullYear().toString().padStart(4, "0");
  const MM = (start.getUTCMonth() + 1).toString().padStart(2, "0");
  const dd = start.getUTCDate().toString().padStart(2, "0");
  const HH = start.getUTCHours().toString().padStart(2, "0");
  const mm = start.getUTCMinutes().toString().padStart(2, "0");
  const ss = start.getUTCSeconds().toString().padStart(2, "0");
  return `${device}_${r}_${yyyy}${MM}${dd}T${HH}${mm}${ss}Z`;
}

function parseExperimentId(experiment_id: string): { device: string; room: string | null; startUtc: Date } {
  const parts = experiment_id.split("_");
  if (parts.length < 3) throw new Error(`Bad experiment_id format: ${experiment_id}`);
  const ts = parts[parts.length - 1];
  const roomPart = parts[parts.length - 2];
  const device = parts.slice(0, -2).join("_");
  const room = roomPart === "noroom" ? null : roomPart;

  const m = ts.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/);
  if (!m) throw new Error(`Bad timestamp in experiment_id: ${experiment_id}`);
  const [_, y, mo, d, h, mi, s] = m;
  const startUtc = new Date(Date.UTC(+y, +mo - 1, +d, +h, +mi, +s));
  return { device, room, startUtc };
}

function integrityDefault(): IntegrityStatus {
  return "UNKNOWN";
}

function mlDefault(): MLFlag {
  return "UNKNOWN";
}

/**
 * Query all supported sensor fields for the last N days/hours.
 * NOTE: This expects the MQTT→Influx bridge to write fields with these names.
 */
async function querySensorRows(start: string): Promise<SensorRow[]> {
  const q = getQueryApi();
  const bucket = getInfluxBucket();
  const measurement = getInfluxMeasurement();

  const flux = [
    `from(bucket: "${bucket}")`,
    `  |> range(start: ${start})`,
    `  |> filter(fn: (r) => r._measurement == "${measurement}")`,
    `  |> filter(fn: (r) => r._field == "air_temp_C" or r._field == "air_humidity_pct" or r._field == "pH" or r._field == "turbidity_voltage_V" or r._field == "water_temp_C")`,
    `  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")`,
    `  |> keep(columns: ["_time","device","room","air_temp_C","air_humidity_pct","pH","turbidity_voltage_V","water_temp_C"])`,
  ].join("\n");

  const rows = await q.collectRows<any>(flux);
  return rows.map((r) => ({
    _time: String(r._time),
    device: r.device ? String(r.device) : undefined,
    room: r.room ? String(r.room) : undefined,
    air_temp_C: r.air_temp_C !== undefined ? Number(r.air_temp_C) : undefined,
    air_humidity_pct: r.air_humidity_pct !== undefined ? Number(r.air_humidity_pct) : undefined,
    pH: r.pH !== undefined ? Number(r.pH) : undefined,
    turbidity_voltage_V: r.turbidity_voltage_V !== undefined ? Number(r.turbidity_voltage_V) : undefined,
    water_temp_C: r.water_temp_C !== undefined ? Number(r.water_temp_C) : undefined,
  }));
}

/**
 * Segment sensor stream into "runs" using a gap threshold (minutes).
 * This yields stable experiment IDs even for continuous streaming.
 */
function segmentRuns(rows: SensorRow[], gapSplitMin: number): Run[] {
  const clean = rows
    .filter((r) => !!r.device)
    .map((r) => ({ ...r, device: String(r.device) }))
    .sort((a, b) => new Date(a._time).getTime() - new Date(b._time).getTime());

  const out: Run[] = [];
  const gapMs = gapSplitMin * 60 * 1000;

  let cur: Run | null = null;
  let prevTime: number | null = null;

  for (const r of clean) {
    const t = new Date(r._time);
    const device = String(r.device);
    const room = safeRoom(r.room);
    const tMs = t.getTime();

    const startNew =
      !cur ||
      cur.device !== device ||
      cur.room !== room ||
      (prevTime !== null && tMs - prevTime > gapMs);

    if (startNew) {
      if (cur) {
        cur.end = new Date(prevTime ?? cur.start.getTime());
        out.push(cur);
      }
      const start = roundDownToMinute(t);
      cur = {
        experiment_id: makeExperimentId(device, room, start),
        device,
        room,
        start,
        end: start,
        rows: [],
      };
    }

    cur!.rows.push(r);
    prevTime = tMs;
  }

  if (cur) {
    cur.end = new Date(prevTime ?? cur.start.getTime());
    out.push(cur);
  }

  return out;
}

function buildMeasurements(run: Run): Measurement[] {
  const startMs = run.start.getTime();
  const measurements: Measurement[] = [];

  const push = (sensor_type: string, value: number, unit: string, idx: number, tIso: string, offsetSec: number) => {
    measurements.push({
      measurement_id: `${run.experiment_id}_${sensor_type}_${idx}`,
      experiment_id: run.experiment_id,
      timestamp_utc: tIso,
      device_id: run.device,
      sensor_type,
      value,
      unit,
      sample_index: idx,
      time_offset_seconds: offsetSec,
    });
  };

  const idx: Record<string, number> = {
    air_temp_C: 0,
    air_humidity_pct: 0,
    pH: 0,
    turbidity_voltage_V: 0,
    water_temp_C: 0,
  };

  for (const r of run.rows) {
    const t = new Date(r._time);
    const tIso = t.toISOString();
    const offsetSec = Math.max(0, Math.floor((t.getTime() - startMs) / 1000));

    if (r.air_temp_C !== undefined) push("air_temp_C", Number(r.air_temp_C), "C", idx.air_temp_C++, tIso, offsetSec);
    if (r.air_humidity_pct !== undefined) push("air_humidity_pct", Number(r.air_humidity_pct), "%", idx.air_humidity_pct++, tIso, offsetSec);
    if (r.pH !== undefined) push("pH", Number(r.pH), "pH", idx.pH++, tIso, offsetSec);
    if (r.turbidity_voltage_V !== undefined) push("turbidity_voltage_V", Number(r.turbidity_voltage_V), "V", idx.turbidity_voltage_V++, tIso, offsetSec);
    if (r.water_temp_C !== undefined) push("water_temp_C", Number(r.water_temp_C), "C", idx.water_temp_C++, tIso, offsetSec);
  }

  measurements.sort((a, b) => new Date(a.timestamp_utc).getTime() - new Date(b.timestamp_utc).getTime());
  return measurements;
}

export async function getExperimentsFromInflux(opts?: { start?: string; gapSplitMin?: number }): Promise<ExperimentSummary[]> {
  const start = opts?.start ?? "-14d";
  const gapSplitMin = opts?.gapSplitMin ?? Number(process.env.GAP_SPLIT_MIN ?? "5");

  const rows = await querySensorRows(start);
  const runs = segmentRuns(rows, gapSplitMin);

  return runs.map((run) => {
    const sensor_types: string[] = [];
    if (run.rows.some(r => r.air_temp_C !== undefined)) sensor_types.push("air_temp_C");
    if (run.rows.some(r => r.air_humidity_pct !== undefined)) sensor_types.push("air_humidity_pct");
    if (run.rows.some(r => r.pH !== undefined)) sensor_types.push("pH");
    if (run.rows.some(r => r.turbidity_voltage_V !== undefined)) sensor_types.push("turbidity_voltage_V");
    if (run.rows.some(r => r.water_temp_C !== undefined)) sensor_types.push("water_temp_C");

    return {
      experiment_id: run.experiment_id,
      device_id: run.device,
      device_alias: run.device,
      start_timestamp_utc: run.start.toISOString(),
      end_timestamp_utc: run.end.toISOString(),
      integrity_status: integrityDefault(),
      ml_flag: mlDefault(), // filled by ML service (no DB writes)
      sensor_types,
    };
  });
}

export async function getExperimentByIdFromInflux(experiment_id: string): Promise<Experiment | null> {
  const { device, room, startUtc } = parseExperimentId(experiment_id);
  const gapSplitMin = Number(process.env.GAP_SPLIT_MIN ?? "5");

  // query a bit before start in case rounding
  const start = new Date(startUtc.getTime() - 6 * 60 * 60 * 1000);
  const startFlux = start.toISOString();

  const q = getQueryApi();
  const bucket = getInfluxBucket();
  const measurement = getInfluxMeasurement();

  const flux = [
    `from(bucket: "${bucket}")`,
    `  |> range(start: time(v: "${startFlux}"))`,
    `  |> filter(fn: (r) => r._measurement == "${measurement}")`,
    `  |> filter(fn: (r) => r.device == "${device}")`,
    room ? `  |> filter(fn: (r) => r.room == "${room}")` : "",
    `  |> filter(fn: (r) => r._field == "air_temp_C" or r._field == "air_humidity_pct" or r._field == "pH" or r._field == "turbidity_voltage_V" or r._field == "water_temp_C")`,
    `  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")`,
    `  |> keep(columns: ["_time","device","room","air_temp_C","air_humidity_pct","pH","turbidity_voltage_V","water_temp_C"])`,
  ].filter(Boolean).join("\n");

  const rows = (await q.collectRows<any>(flux)).map((r) => ({
    _time: String(r._time),
    device: r.device ? String(r.device) : undefined,
    room: r.room ? String(r.room) : undefined,
    air_temp_C: r.air_temp_C !== undefined ? Number(r.air_temp_C) : undefined,
    air_humidity_pct: r.air_humidity_pct !== undefined ? Number(r.air_humidity_pct) : undefined,
    pH: r.pH !== undefined ? Number(r.pH) : undefined,
    turbidity_voltage_V: r.turbidity_voltage_V !== undefined ? Number(r.turbidity_voltage_V) : undefined,
    water_temp_C: r.water_temp_C !== undefined ? Number(r.water_temp_C) : undefined,
  })) as SensorRow[];

  const runs = segmentRuns(rows, gapSplitMin);
  const run = runs.find(r => r.experiment_id === experiment_id);
  if (!run) return null;

  // choose primary series
  const primary = run.rows.some(r => r.turbidity_voltage_V !== undefined) ? "turbidity_voltage_V"
    : (run.rows.some(r => r.pH !== undefined) ? "pH" : "water_temp_C");

  return {
    experiment_id,
    device_id: run.device,
    device_alias: run.device,
    start_timestamp_utc: run.start.toISOString(),
    end_timestamp_utc: run.end.toISOString(),

    contaminant_type: null,
    pH_initial: null,
    light_intensity: null,
    temperature: null,
    site_location: run.room ? `room:${run.room}` : null,
    data_source_type: "real_sensor",

    hash: null,
    signature: null,
    device_cert_id: null,
    integrity_status: integrityDefault(),
    source_file_id: null,

    ml_version: null,
    anomaly_score: null,
    ml_flag: mlDefault(),
    ml_timestamp_utc: null,

    prediction_curve: null,
    primary_sensor_type: primary,
  };
}

export async function getMeasurementsByExperimentIdFromInflux(experiment_id: string): Promise<Measurement[]> {
  const exp = await getExperimentByIdFromInflux(experiment_id);
  if (!exp) return [];

  const start = new Date(exp.start_timestamp_utc).toISOString();
  const end = exp.end_timestamp_utc ? new Date(exp.end_timestamp_utc).toISOString() : null;

  const { device, room } = parseExperimentId(experiment_id);
  const q = getQueryApi();
  const bucket = getInfluxBucket();
  const measurement = getInfluxMeasurement();

  const flux = [
    `from(bucket: "${bucket}")`,
    `  |> range(start: time(v: "${start}")${end ? `, stop: time(v: "${end}")` : ""})`,
    `  |> filter(fn: (r) => r._measurement == "${measurement}")`,
    `  |> filter(fn: (r) => r.device == "${device}")`,
    room ? `  |> filter(fn: (r) => r.room == "${room}")` : "",
    `  |> filter(fn: (r) => r._field == "air_temp_C" or r._field == "air_humidity_pct" or r._field == "pH" or r._field == "turbidity_voltage_V" or r._field == "water_temp_C")`,
    `  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")`,
    `  |> keep(columns: ["_time","device","room","air_temp_C","air_humidity_pct","pH","turbidity_voltage_V","water_temp_C"])`,
  ].filter(Boolean).join("\n");

  const rows = (await q.collectRows<any>(flux)).map((r) => ({
    _time: String(r._time),
    device: r.device ? String(r.device) : undefined,
    room: r.room ? String(r.room) : undefined,
    air_temp_C: r.air_temp_C !== undefined ? Number(r.air_temp_C) : undefined,
    air_humidity_pct: r.air_humidity_pct !== undefined ? Number(r.air_humidity_pct) : undefined,
    pH: r.pH !== undefined ? Number(r.pH) : undefined,
    turbidity_voltage_V: r.turbidity_voltage_V !== undefined ? Number(r.turbidity_voltage_V) : undefined,
    water_temp_C: r.water_temp_C !== undefined ? Number(r.water_temp_C) : undefined,
  })) as SensorRow[];

  const startUtc = new Date(exp.start_timestamp_utc);
  const endUtc = exp.end_timestamp_utc ? new Date(exp.end_timestamp_utc) : new Date(rows[rows.length - 1]?._time ?? exp.start_timestamp_utc);

  const run: Run = {
    experiment_id,
    device,
    room,
    start: startUtc,
    end: endUtc,
    rows,
  };

  return buildMeasurements(run);
}


/**
 * LIVE list-mode helper:
 * Fetch a small recent window of measurements for an experiment and send to ML service.
 * This avoids reading/writing any ML rows in Influx (DB stays sensor-only).
 */

/**
 * LIVE window helper (time-based):
 * Fetch measurements for the last `windowMinutes` minutes for a given experiment.
 * Used for rolling 2-minute charts and rolling-window ML scoring.
 */
export async function getRecentWindowMeasurementsFromInflux(
  experiment_id: string,
  windowMinutes: number
): Promise<Measurement[]> {
  const { device, room } = parseExperimentId(experiment_id);

  const q = getQueryApi();
  const bucket = getInfluxBucket();
  const measurement = getInfluxMeasurement();

  const flux = [
    `from(bucket: "${bucket}")`,
    `  |> range(start: -${Math.max(1, Math.floor(windowMinutes))}m)`,
    `  |> filter(fn: (r) => r._measurement == "${measurement}")`,
    `  |> filter(fn: (r) => r.device == "${device}")`,
    room ? `  |> filter(fn: (r) => r.room == "${room}")` : "",
    `  |> filter(fn: (r) => r._field == "air_temp_C" or r._field == "air_humidity_pct" or r._field == "pH" or r._field == "turbidity_voltage_V" or r._field == "water_temp_C")`,
    `  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")`,
    `  |> keep(columns: ["_time","device","room","air_temp_C","air_humidity_pct","pH","turbidity_voltage_V","water_temp_C"])`,
    `  |> sort(columns: ["_time"])`,
  ].filter(Boolean).join("\n");

  const rows = (await q.collectRows<any>(flux)).map((r) => ({
    _time: String(r._time),
    device: r.device ? String(r.device) : undefined,
    room: r.room ? String(r.room) : undefined,
    air_temp_C: r.air_temp_C !== undefined ? Number(r.air_temp_C) : undefined,
    air_humidity_pct: r.air_humidity_pct !== undefined ? Number(r.air_humidity_pct) : undefined,
    pH: r.pH !== undefined ? Number(r.pH) : undefined,
    turbidity_voltage_V: r.turbidity_voltage_V !== undefined ? Number(r.turbidity_voltage_V) : undefined,
    water_temp_C: r.water_temp_C !== undefined ? Number(r.water_temp_C) : undefined,
  })) as SensorRow[];

  // Build Measurement[] with time_offset_seconds relative to first point in this window.
  const bySensor: Record<string, number> = {};
  const out: Measurement[] = [];
  const t0 = rows.length ? new Date(rows[0]._time).getTime() : Date.now();

  const push = (sensor_type: string, value: number, unit: string, tIso: string) => {
    const idx = bySensor[sensor_type] ?? 0;
    bySensor[sensor_type] = idx + 1;
    const t = new Date(tIso).getTime();
    const offsetSec = Math.max(0, Math.floor((t - t0) / 1000));

    out.push({
      measurement_id: `${experiment_id}_${sensor_type}_${idx}`,
      experiment_id,
      timestamp_utc: tIso,
      device_id: device,
      sensor_type,
      value,
      unit,
      sample_index: idx,
      time_offset_seconds: offsetSec,
    });
  };

  for (const r of rows) {
    const tIso = new Date(r._time).toISOString();
    if (r.air_temp_C !== undefined) push("air_temp_C", Number(r.air_temp_C), "C", tIso);
    if (r.air_humidity_pct !== undefined) push("air_humidity_pct", Number(r.air_humidity_pct), "%", tIso);
    if (r.pH !== undefined) push("pH", Number(r.pH), "pH", tIso);
    if (r.turbidity_voltage_V !== undefined) push("turbidity_voltage_V", Number(r.turbidity_voltage_V), "V", tIso);
    if (r.water_temp_C !== undefined) push("water_temp_C", Number(r.water_temp_C), "C", tIso);
  }

  out.sort((a, b) => new Date(a.timestamp_utc).getTime() - new Date(b.timestamp_utc).getTime());
  return out;
}

export async function getLatestWindowMeasurementsFromInflux(
  experiment_id: string,
  windowPoints: number = 400
): Promise<Measurement[]> {
  const { device, room, startUtc } = parseExperimentId(experiment_id);

  const q = getQueryApi();
  const bucket = getInfluxBucket();
  const measurement = getInfluxMeasurement();

  const startIso = startUtc.toISOString();

  const flux = [
    `from(bucket: "${bucket}")`,
    `  |> range(start: time(v: "${startIso}"))`,
    `  |> filter(fn: (r) => r._measurement == "${measurement}")`,
    `  |> filter(fn: (r) => r.device == "${device}")`,
    room ? `  |> filter(fn: (r) => r.room == "${room}")` : "",
    `  |> filter(fn: (r) => r._field == "air_temp_C" or r._field == "air_humidity_pct" or r._field == "pH" or r._field == "turbidity_voltage_V" or r._field == "water_temp_C")`,
    `  |> sort(columns: ["_time"])`,
    `  |> tail(n: ${windowPoints})`,
    `  |> keep(columns: ["_time","device","room","_field","_value"])`,
  ].filter(Boolean).join("\n");

  const rows = await q.collectRows<any>(flux);

  // build measurement list
  const bySensor: Record<string, number> = {};
  const out: Measurement[] = [];

  for (const r of rows) {
    const sensor_type = String(r._field);
    const t = new Date(String(r._time));
    const offsetSec = Math.max(0, Math.floor((t.getTime() - startUtc.getTime()) / 1000));
    const idx = bySensor[sensor_type] ?? 0;
    bySensor[sensor_type] = idx + 1;

    // units
    let unit = "—";
    if (sensor_type === "air_temp_C") unit = "C";
    if (sensor_type === "water_temp_C") unit = "C";
    if (sensor_type === "air_humidity_pct") unit = "%";
    if (sensor_type === "pH") unit = "pH";
    if (sensor_type === "turbidity_voltage_V") unit = "V";

    out.push({
      measurement_id: `${experiment_id}_${sensor_type}_win_${idx}`,
      experiment_id,
      timestamp_utc: t.toISOString(),
      device_id: device,
      sensor_type,
      value: Number(r._value),
      unit,
      sample_index: idx,
      time_offset_seconds: offsetSec,
    });
  }

  out.sort((a, b) => new Date(a.timestamp_utc).getTime() - new Date(b.timestamp_utc).getTime());
  return out;
}

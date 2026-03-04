import type { Experiment, ExperimentSummary, Measurement, MLFlag, IntegrityStatus } from "@/lib/types";
import { getQueryApi, INFLUX_BUCKET, INFLUX_MEASUREMENT, ML_MEASUREMENT } from "@/lib/influxClient";

type SensorRow = {
  _time: string;
  device?: string;
  room?: string;
  temp?: number;
  humidity?: number;
  luminosity?: number;
};

type MLSummaryRow = {
  experiment_id?: string;
  device?: string;
  room?: string;
  ml_version?: string;
  anomaly_score?: number;
  ml_flag?: string;
  ml_timestamp_utc?: string;
  prediction_curve_json?: string;
  error_raw?: number;
  seq_len?: number;
  _time?: string;
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
  // Must match Python: f"{device}_{room or 'noroom'}_{start.strftime('%Y%m%dT%H%M%SZ')}"
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

  // ts: YYYYMMDDTHHMMSSZ
  const m = ts.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/);
  if (!m) throw new Error(`Bad timestamp in experiment_id: ${experiment_id}`);
  const [_, y, mo, d, h, mi, s] = m;
  const startUtc = new Date(Date.UTC(+y, +mo - 1, +d, +h, +mi, +s));
  return { device, room, startUtc };
}

async function querySensorRows(start: string): Promise<SensorRow[]> {
  const q = getQueryApi();
  const flux = [
    `from(bucket: "${INFLUX_BUCKET}")`,
    `  |> range(start: ${start})`,
    `  |> filter(fn: (r) => r._measurement == "${INFLUX_MEASUREMENT}")`,
    `  |> filter(fn: (r) => r._field == "temp" or r._field == "humidity" or r._field == "luminosity")`,
    `  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")`,
    `  |> keep(columns: ["_time","device","room","temp","humidity","luminosity"])`,
  ].join("\n");

  const rows = await q.collectRows<any>(flux);
  return rows.map((r) => ({
    _time: String(r._time),
    device: r.device ? String(r.device) : undefined,
    room: r.room ? String(r.room) : undefined,
    temp: r.temp !== undefined ? Number(r.temp) : undefined,
    humidity: r.humidity !== undefined ? Number(r.humidity) : undefined,
    luminosity: r.luminosity !== undefined ? Number(r.luminosity) : undefined,
  }));
}

async function queryLatestMlSummaryMap(start: string): Promise<Map<string, MLSummaryRow>> {
  const q = getQueryApi();
  const flux = [
    `from(bucket: "${INFLUX_BUCKET}")`,
    `  |> range(start: ${start})`,
    `  |> filter(fn: (r) => r._measurement == "${ML_MEASUREMENT}")`,
    `  |> group(columns: ["experiment_id"])`,
    `  |> last()`,
    `  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")`,
    `  |> keep(columns: ["_time","experiment_id","device","room","ml_version","anomaly_score","ml_flag","ml_timestamp_utc","prediction_curve_json","error_raw","seq_len"])`,
  ].join("\n");

  const rows = await q.collectRows<any>(flux);
  const m = new Map<string, MLSummaryRow>();
  for (const r of rows) {
    const id = r.experiment_id ? String(r.experiment_id) : "";
    if (!id) continue;
    m.set(id, {
      experiment_id: id,
      device: r.device ? String(r.device) : undefined,
      room: r.room ? String(r.room) : undefined,
      ml_version: r.ml_version ? String(r.ml_version) : undefined,
      anomaly_score: r.anomaly_score !== undefined ? Number(r.anomaly_score) : undefined,
      ml_flag: r.ml_flag ? String(r.ml_flag) : undefined,
      ml_timestamp_utc: r.ml_timestamp_utc ? String(r.ml_timestamp_utc) : undefined,
      prediction_curve_json: r.prediction_curve_json ? String(r.prediction_curve_json) : undefined,
      error_raw: r.error_raw !== undefined ? Number(r.error_raw) : undefined,
      seq_len: r.seq_len !== undefined ? Number(r.seq_len) : undefined,
      _time: r._time ? String(r._time) : undefined,
    });
  }
  return m;
}

type Run = {
  experiment_id: string;
  device: string;
  room: string | null;
  start: Date;
  end: Date;
  rows: SensorRow[];
};

function segmentRuns(rows: SensorRow[], gapSplitMin: number): Run[] {
  // group by (device, room), split by time gaps
  const byKey = new Map<string, SensorRow[]>();
  for (const r of rows) {
    const device = r.device ? String(r.device) : "unknown_device";
    const room = safeRoom(r.room);
    const key = `${device}|||${room ?? "noroom"}`;
    const arr = byKey.get(key) ?? [];
    arr.push(r);
    byKey.set(key, arr);
  }

  const runs: Run[] = [];
  const gapMs = gapSplitMin * 60 * 1000;

  for (const [key, arr] of byKey.entries()) {
    arr.sort((a, b) => new Date(a._time).getTime() - new Date(b._time).getTime());
    const [device, roomPart] = key.split("|||");
    const room = roomPart === "noroom" ? null : roomPart;

    // filter rows with at least one sensor value
    const clean = arr.filter(r => r.temp !== undefined || r.humidity !== undefined || r.luminosity !== undefined);
    if (clean.length === 0) continue;

    let startIdx = 0;
    for (let i = 1; i <= clean.length; i++) {
      const prev = new Date(clean[i - 1]._time).getTime();
      const curr = i < clean.length ? new Date(clean[i]._time).getTime() : null;

      const isSplit = curr !== null ? (curr - prev) > gapMs : true;
      if (isSplit) {
        const slice = clean.slice(startIdx, i);
        const start = roundDownToMinute(new Date(slice[0]._time));
        const end = new Date(slice[slice.length - 1]._time);
        const experiment_id = makeExperimentId(device, room, start);
        runs.push({ experiment_id, device, room, start, end, rows: slice });
        startIdx = i;
      }
    }
  }

  runs.sort((a, b) => b.end.getTime() - a.end.getTime()); // newest first
  return runs;
}

function mlFlagOrDefault(v: any): MLFlag {
  const s = String(v ?? "").toUpperCase();
  if (s === "NORMAL" || s === "SUSPICIOUS" || s === "UNKNOWN" || s === "INSUFFICIENT_DATA") return s as MLFlag;
  return "UNKNOWN";
}

function integrityDefault(): IntegrityStatus {
  return "UNKNOWN";
}

function predictionCurveFromJson(prediction_curve_json?: string): { time_offset_seconds: number; value: number }[] | null {
  if (!prediction_curve_json) return null;
  try {
    const obj = JSON.parse(prediction_curve_json);
    // Our Python writes either:
    //  - {channel, actual, expected, abs_residual}   OR
    //  - {time_offsets_sec, expected_values, actual_values}
    const offsets: number[] =
      obj.time_offsets_sec ?? obj.time_offsets_seconds ?? obj.time_offsets ?? null;

    const expected: number[] =
      obj.expected_values ?? obj.expected ?? null;

    if (Array.isArray(offsets) && Array.isArray(expected) && offsets.length === expected.length) {
      return offsets.map((t: number, i: number) => ({ time_offset_seconds: Number(t), value: Number(expected[i]) }));
    }

    // fallback: if only expected list, assume 60s step
    if (Array.isArray(expected)) {
      return expected.map((v: number, i: number) => ({ time_offset_seconds: i * 60, value: Number(v) }));
    }
    return null;
  } catch {
    return null;
  }
}

function buildMeasurements(run: Run): Measurement[] {
  const startMs = run.start.getTime();
  const measurements: Measurement[] = [];
  let idxTemp = 0, idxHum = 0, idxLum = 0;

  for (const r of run.rows) {
    const t = new Date(r._time);
    const tIso = t.toISOString();
    const offsetSec = Math.max(0, Math.floor((t.getTime() - startMs) / 1000));

    if (r.temp !== undefined) {
      measurements.push({
        measurement_id: `${run.experiment_id}_temp_${idxTemp}`,
        experiment_id: run.experiment_id,
        timestamp_utc: tIso,
        device_id: run.device,
        sensor_type: "temp",
        value: Number(r.temp),
        unit: "C",
        sample_index: idxTemp,
        time_offset_seconds: offsetSec,
      });
      idxTemp++;
    }
    if (r.humidity !== undefined) {
      measurements.push({
        measurement_id: `${run.experiment_id}_humidity_${idxHum}`,
        experiment_id: run.experiment_id,
        timestamp_utc: tIso,
        device_id: run.device,
        sensor_type: "humidity",
        value: Number(r.humidity),
        unit: "%",
        sample_index: idxHum,
        time_offset_seconds: offsetSec,
      });
      idxHum++;
    }
    if (r.luminosity !== undefined) {
      measurements.push({
        measurement_id: `${run.experiment_id}_luminosity_${idxLum}`,
        experiment_id: run.experiment_id,
        timestamp_utc: tIso,
        device_id: run.device,
        sensor_type: "luminosity",
        value: Number(r.luminosity),
        unit: "lux",
        sample_index: idxLum,
        time_offset_seconds: offsetSec,
      });
      idxLum++;
    }
  }

  // stable ordering
  measurements.sort((a, b) => new Date(a.timestamp_utc).getTime() - new Date(b.timestamp_utc).getTime());
  return measurements;
}

export async function getExperimentsFromInflux(opts?: { start?: string; gapSplitMin?: number }): Promise<ExperimentSummary[]> {
  const start = opts?.start ?? "-14d";
  const gapSplitMin = opts?.gapSplitMin ?? Number(process.env.GAP_SPLIT_MIN ?? "5");

  const rows = await querySensorRows(start);
  const runs = segmentRuns(rows, gapSplitMin);

  const mlMap = await queryLatestMlSummaryMap("-30d");

  return runs.map((run) => {
    const ml = mlMap.get(run.experiment_id);
    const ml_flag = ml ? mlFlagOrDefault(ml.ml_flag) : "UNKNOWN";

    const sensor_types: string[] = [];
    // include only sensors present in the run
    const hasTemp = run.rows.some(r => r.temp !== undefined);
    const hasHum = run.rows.some(r => r.humidity !== undefined);
    const hasLum = run.rows.some(r => r.luminosity !== undefined);
    if (hasTemp) sensor_types.push("temp");
    if (hasHum) sensor_types.push("humidity");
    if (hasLum) sensor_types.push("luminosity");

    return {
      experiment_id: run.experiment_id,
      device_id: run.device,
      device_alias: run.device,
      start_timestamp_utc: run.start.toISOString(),
      end_timestamp_utc: run.end.toISOString(),
      integrity_status: integrityDefault(),
      ml_flag,
      sensor_types,
    };
  });
}

export async function getExperimentByIdFromInflux(experiment_id: string): Promise<Experiment | null> {
  const { device, room, startUtc } = parseExperimentId(experiment_id);
  const gapSplitMin = Number(process.env.GAP_SPLIT_MIN ?? "5");

  // Pull a window around the experiment start to find exact segment
  const start = new Date(startUtc.getTime() - 6 * 60 * 60 * 1000); // -6h buffer
  const startFlux = start.toISOString();

  const q = getQueryApi();
  const flux = [
    `from(bucket: "${INFLUX_BUCKET}")`,
    `  |> range(start: time(v: "${startFlux}"))`,
    `  |> filter(fn: (r) => r._measurement == "${INFLUX_MEASUREMENT}")`,
    `  |> filter(fn: (r) => r.device == "${device}")`,
    room ? `  |> filter(fn: (r) => r.room == "${room}")` : "",
    `  |> filter(fn: (r) => r._field == "temp" or r._field == "humidity" or r._field == "luminosity")`,
    `  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")`,
    `  |> keep(columns: ["_time","device","room","temp","humidity","luminosity"])`,
  ].filter(Boolean).join("\n");

  const rows = (await q.collectRows<any>(flux)).map((r) => ({
    _time: String(r._time),
    device: r.device ? String(r.device) : undefined,
    room: r.room ? String(r.room) : undefined,
    temp: r.temp !== undefined ? Number(r.temp) : undefined,
    humidity: r.humidity !== undefined ? Number(r.humidity) : undefined,
    luminosity: r.luminosity !== undefined ? Number(r.luminosity) : undefined,
  })) as SensorRow[];

  const runs = segmentRuns(rows, gapSplitMin);
  const run = runs.find(r => r.experiment_id === experiment_id);
  if (!run) return null;

  // ML summary for this experiment
  const mlMap = await queryLatestMlSummaryMap("-30d");
  const ml = mlMap.get(experiment_id);

  const prediction_curve = predictionCurveFromJson(ml?.prediction_curve_json);

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

    ml_version: ml?.ml_version ?? null,
    anomaly_score: ml?.anomaly_score !== undefined ? Number(ml.anomaly_score) : null,
    ml_flag: ml ? mlFlagOrDefault(ml.ml_flag) : "UNKNOWN",
    ml_timestamp_utc: ml?.ml_timestamp_utc ?? null,

    prediction_curve: prediction_curve ?? null,

    primary_sensor_type: "luminosity",
  };
}

export async function getMeasurementsByExperimentIdFromInflux(experiment_id: string): Promise<Measurement[]> {
  const exp = await getExperimentByIdFromInflux(experiment_id);
  if (!exp) return [];

  const start = new Date(exp.start_timestamp_utc).toISOString();
  const end = exp.end_timestamp_utc ? new Date(exp.end_timestamp_utc).toISOString() : null;

  const { device, room } = parseExperimentId(experiment_id);
  const q = getQueryApi();

  const flux = [
    `from(bucket: "${INFLUX_BUCKET}")`,
    `  |> range(start: time(v: "${start}")${end ? `, stop: time(v: "${end}")` : ""})`,
    `  |> filter(fn: (r) => r._measurement == "${INFLUX_MEASUREMENT}")`,
    `  |> filter(fn: (r) => r.device == "${device}")`,
    room ? `  |> filter(fn: (r) => r.room == "${room}")` : "",
    `  |> filter(fn: (r) => r._field == "temp" or r._field == "humidity" or r._field == "luminosity")`,
    `  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")`,
    `  |> keep(columns: ["_time","device","room","temp","humidity","luminosity"])`,
  ].filter(Boolean).join("\n");

  const rows = (await q.collectRows<any>(flux)).map((r) => ({
    _time: String(r._time),
    device: r.device ? String(r.device) : undefined,
    room: r.room ? String(r.room) : undefined,
    temp: r.temp !== undefined ? Number(r.temp) : undefined,
    humidity: r.humidity !== undefined ? Number(r.humidity) : undefined,
    luminosity: r.luminosity !== undefined ? Number(r.luminosity) : undefined,
  })) as SensorRow[];

  // Build a run-like structure for measurement conversion
  const startUtc = new Date(exp.start_timestamp_utc);
  const endUtc = exp.end_timestamp_utc ? new Date(exp.end_timestamp_utc) : new Date(rows[rows.length - 1]?._time ?? exp.start_timestamp_utc);

  const run: Run = {
    experiment_id,
    device: device,
    room: room,
    start: startUtc,
    end: endUtc,
    rows,
  };

  return buildMeasurements(run);
}

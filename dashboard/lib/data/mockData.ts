import type { Experiment, ExperimentSummary, Measurement, PredictionPoint } from "@/lib/types";
import { sensorTypesFromMeasurements } from "@/lib/utils";

/**
 * Mock data layer (T1–T5).
 * Why this exists:
 * - Keeps data access in one place (do NOT scatter mock logic across pages).
 * - Allows swapping to DB/API later without rewriting UI.
 *
 * Important: variable names match the required master list exactly.
 */

// --- Helpers to build consistent timestamps in UTC ---
function isoNowMinusMinutes(minutes: number): string {
  return new Date(Date.now() - minutes * 60 * 1000).toISOString();
}
function isoNowMinusHours(hours: number): string {
  return new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
}

// --- Mock experiments (at least 6 across 2 devices) ---
const experiments: Experiment[] = [
  {
    experiment_id: "EXP-2026-02-01-A01",
    device_id: "PI-EDGE-001",
    device_alias: "Pi Lab Bench A",
    start_timestamp_utc: isoNowMinusMinutes(38),
    end_timestamp_utc: isoNowMinusMinutes(7),

    contaminant_type: "dye_simulant_blue",
    pH_initial: 7.2,
    light_intensity: 520,
    temperature: 24.8,
    site_location: "UofT Lab - Station A",
    data_source_type: "lab_instrument",

    hash: "0x8b2f4e...a01",
    signature: "sig_ed25519...a01",
    device_cert_id: "cert_PI-EDGE-001_v1",
    integrity_status: "VALID",
    source_file_id: "archive://EXP-2026-02-01-A01.csv",

    ml_version: "lstm_v0.3.2",
    anomaly_score: 0.12,
    ml_flag: "NORMAL",
    ml_timestamp_utc: isoNowMinusMinutes(6),

    prediction_curve: buildPredictionCurve(0, 60, 10, 0.02),
    primary_sensor_type: "spectrometer"
  },
  {
    experiment_id: "EXP-2026-02-01-A02",
    device_id: "PI-EDGE-001",
    device_alias: "Pi Lab Bench A",
    start_timestamp_utc: isoNowMinusHours(6),
    end_timestamp_utc: isoNowMinusHours(5.7),

    contaminant_type: "dye_simulant_red",
    pH_initial: 6.6,
    light_intensity: 610,
    temperature: 25.5,
    site_location: "UofT Lab - Station A",
    data_source_type: "lab_instrument",

    hash: "0x1c9d77...a02",
    signature: "sig_ed25519...a02",
    device_cert_id: "cert_PI-EDGE-001_v1",
    integrity_status: "INVALID",
    source_file_id: "archive://EXP-2026-02-01-A02.csv",

    ml_version: "lstm_v0.3.2",
    anomaly_score: 0.91,
    ml_flag: "SUSPICIOUS",
    ml_timestamp_utc: isoNowMinusHours(5.6),

    prediction_curve: buildPredictionCurve(0, 60, 10, 0.06),
    primary_sensor_type: "spectrometer"
  },
  {
    experiment_id: "EXP-2026-01-31-B01",
    device_id: "PI-EDGE-002",
    device_alias: "Pi Field Rig B",
    start_timestamp_utc: isoNowMinusHours(28),
    end_timestamp_utc: isoNowMinusHours(27.8),

    contaminant_type: null, // optional; show "—"
    pH_initial: 7.0,
    light_intensity: 430,
    temperature: 23.1,
    site_location: "Pilot Site - Rig B",
    data_source_type: "real_sensor",

    hash: "0x55af19...b01",
    signature: null, // missing -> keep UI stable
    device_cert_id: "cert_PI-EDGE-002_v1",
    integrity_status: "UNKNOWN",
    source_file_id: "archive://EXP-2026-01-31-B01.csv",

    ml_version: null,
    anomaly_score: null,
    ml_flag: "UNKNOWN",
    ml_timestamp_utc: null,

    prediction_curve: null,
    primary_sensor_type: "spectrometer"
  },
  {
    experiment_id: "EXP-2026-01-31-B02",
    device_id: "PI-EDGE-002",
    device_alias: "Pi Field Rig B",
    start_timestamp_utc: isoNowMinusHours(14),
    end_timestamp_utc: null, // ongoing
    contaminant_type: "unknown_mixture_masked",
    pH_initial: 7.8,
    light_intensity: 300,
    temperature: 26.2,
    site_location: "Pilot Site - Rig B",
    data_source_type: "real_sensor",

    hash: "0x7aa1bc...b02",
    signature: "sig_ed25519...b02",
    device_cert_id: "cert_PI-EDGE-002_v1",
    integrity_status: "VALID",
    source_file_id: "archive://EXP-2026-01-31-B02.csv",

    ml_version: "lstm_v0.3.1",
    anomaly_score: 0.45,
    ml_flag: "INSUFFICIENT_DATA",
    ml_timestamp_utc: isoNowMinusHours(1.2),

    prediction_curve: null,
    primary_sensor_type: "spectrometer"
  },
  {
    experiment_id: "EXP-2026-01-30-A03",
    device_id: "PI-EDGE-001",
    device_alias: "Pi Lab Bench A",
    start_timestamp_utc: isoNowMinusHours(60),
    end_timestamp_utc: isoNowMinusHours(59.5),

    contaminant_type: "dye_simulant_green",
    pH_initial: 5.9,
    light_intensity: 700,
    temperature: 24.2,
    site_location: "UofT Lab - Station A",
    data_source_type: "simulated",

    hash: "0x2f0c88...a03",
    signature: "sig_ed25519...a03",
    device_cert_id: "cert_PI-EDGE-001_v1",
    integrity_status: "VALID",
    source_file_id: "archive://EXP-2026-01-30-A03.csv",

    ml_version: "lstm_v0.3.0",
    anomaly_score: 0.08,
    ml_flag: "NORMAL",
    ml_timestamp_utc: isoNowMinusHours(59.4),

    prediction_curve: buildPredictionCurve(0, 60, 10, 0.01),
    primary_sensor_type: "spectrometer"
  },
  {
    experiment_id: "EXP-2026-01-30-B03",
    device_id: "PI-EDGE-002",
    device_alias: "Pi Field Rig B",
    start_timestamp_utc: isoNowMinusHours(80),
    end_timestamp_utc: isoNowMinusHours(79.7),

    contaminant_type: "pilot_sample_masked",
    pH_initial: null,
    light_intensity: null,
    temperature: 22.7,
    site_location: "Pilot Site - Rig B",
    data_source_type: "real_sensor",

    hash: null,
    signature: null,
    device_cert_id: null,
    integrity_status: "UNKNOWN",
    source_file_id: null,

    ml_version: "lstm_v0.2.9",
    anomaly_score: 0.33,
    ml_flag: "UNKNOWN",
    ml_timestamp_utc: isoNowMinusHours(79.6),

    prediction_curve: null,
    primary_sensor_type: "spectrometer"
  }
];

// --- Mock measurements keyed by experiment_id ---
const measurementsByExperimentId: Record<string, Measurement[]> = Object.fromEntries(
  experiments.map((e) => [e.experiment_id, buildMeasurementsForExperiment(e)])
);

// ---- Public API (T4–T5) ----

export function getExperiments(): ExperimentSummary[] {
  return experiments.map((e) => {
    const ms = measurementsByExperimentId[e.experiment_id] ?? [];
    const sensor_types = sensorTypesFromMeasurements(ms);

    return {
      experiment_id: e.experiment_id,
      device_id: e.device_id,
      device_alias: e.device_alias,
      start_timestamp_utc: e.start_timestamp_utc,
      end_timestamp_utc: e.end_timestamp_utc,
      integrity_status: e.integrity_status,
      ml_flag: e.ml_flag,
      sensor_types
    };
  });
}

export function getExperimentById(experiment_id: string): Experiment | null {
  return experiments.find((e) => e.experiment_id === experiment_id) ?? null;
}

export function getMeasurementsByExperimentId(experiment_id: string): Measurement[] {
  return measurementsByExperimentId[experiment_id] ?? [];
}

// ---- Internal mock builders ----

function buildPredictionCurve(startSec: number, endSec: number, stepSec: number, noise: number): PredictionPoint[] {
  const points: PredictionPoint[] = [];
  for (let t = startSec; t <= endSec; t += stepSec) {
    // A smooth-ish decay curve for placeholder predicted values
    const base = 1.0 * Math.exp(-t / 80);
    const jitter = (Math.sin(t / 7) * noise);
    points.push({ time_offset_seconds: t, value: Number((base + jitter).toFixed(4)) });
  }
  return points;
}

function buildMeasurementsForExperiment(exp: Experiment): Measurement[] {
  // We generate a small multi-sensor set: spectrometer + temperature + pH (sometimes).
  // This gives the list view real "sensor types involved" and allows detail charting.

  const start = new Date(exp.start_timestamp_utc).getTime();
  const totalSeconds = 60;
  const stepSeconds = 5;

  const rows: Measurement[] = [];
  let sample_index = 0;

  for (let t = 0; t <= totalSeconds; t += stepSeconds) {
    const timestamp_utc = new Date(start + t * 1000).toISOString();

    // spectrometer value: decay with variability
    const decay = Math.exp(-t / 55);
    const wobble = 0.03 * Math.sin(t / 6);
    const anomalyBoost = exp.ml_flag === "SUSPICIOUS" ? (t > 30 ? 0.15 : 0) : 0;
    const valueSpect = Number((decay + wobble + anomalyBoost).toFixed(4));

    rows.push({
      measurement_id: `${exp.experiment_id}::M-${String(sample_index).padStart(3, "0")}`,
      experiment_id: exp.experiment_id,
      timestamp_utc,
      device_id: exp.device_id,
      sensor_type: "spectrometer",
      value: valueSpect,
      unit: "absorbance",
      sample_index,
      time_offset_seconds: t
    });

    // temperature (slight drift)
    rows.push({
      measurement_id: `${exp.experiment_id}::T-${String(sample_index).padStart(3, "0")}`,
      experiment_id: exp.experiment_id,
      timestamp_utc,
      device_id: exp.device_id,
      sensor_type: "temperature",
      value: Number(((exp.temperature ?? 24) + 0.1 * Math.sin(t / 10)).toFixed(2)),
      unit: "°C",
      sample_index,
      time_offset_seconds: t
    });

    // pH only for some experiments (to exercise optionality)
    if (exp.pH_initial !== null && exp.pH_initial !== undefined && exp.experiment_id.endsWith("A01")) {
      rows.push({
        measurement_id: `${exp.experiment_id}::P-${String(sample_index).padStart(3, "0")}`,
        experiment_id: exp.experiment_id,
        timestamp_utc,
        device_id: exp.device_id,
        sensor_type: "pH",
        value: Number((exp.pH_initial + 0.02 * Math.cos(t / 12)).toFixed(2)),
        unit: "pH",
        sample_index,
        time_offset_seconds: t
      });
    }

    sample_index++;
  }

  return rows;
}

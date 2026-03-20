import type { Experiment, ExperimentSummary, MLFlag, Measurement } from "@/lib/types";

const ML_URL = process.env.ML_SERVICE_URL ?? "http://127.0.0.1:8000";

type MlResult = {
  ml_version?: string;
  anomaly_score?: number;
  ml_flag?: MLFlag;
  ml_timestamp_utc?: string;
  per_feature?: Record<string, { raw_mse?: number | null; score?: number | null; flag?: MLFlag }>;
};

async function safeFetchJson<T>(url: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(url, { ...init, cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function fetchMlForExperimentId(experiment_id: string): Promise<MlResult | null> {
  return await safeFetchJson<MlResult>(`${ML_URL}/api/ml/${encodeURIComponent(experiment_id)}`);
}

/**
 * LIVE mode path: dashboard already fetched measurements from Influx.
 * We POST the measurement list to ML service for scoring (no DB writes).
 */
export async function scoreMeasurements(experiment_id: string, measurements: Measurement[]): Promise<MlResult | null> {
  const payload = {
    experiment_id,
    measurements: measurements.map((m) => ({
      experiment_id: m.experiment_id,
      timestamp_utc: m.timestamp_utc,
      sensor_type: m.sensor_type,
      value: m.value,
      unit: m.unit,
      sample_index: m.sample_index,
      time_offset_seconds: m.time_offset_seconds,
      device_id: m.device_id,
    })),
  };

  return await safeFetchJson<MlResult>(`${ML_URL}/api/ml/score`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function mergeMlIntoSummary(s: ExperimentSummary, ml: MlResult | null): ExperimentSummary {
  if (!ml) return s;
  return {
    ...s,
    ml_flag: (ml.ml_flag ?? s.ml_flag),
    per_feature: (ml.per_feature ?? s.per_feature),
  };
}

export function mergeMlIntoExperiment(e: Experiment, ml: MlResult | null): Experiment {
  if (!ml) return e;
  return {
    ...e,
    ml_version: ml.ml_version ?? e.ml_version,
    anomaly_score: ml.anomaly_score ?? e.anomaly_score,
    ml_flag: (ml.ml_flag ?? e.ml_flag),
    ml_timestamp_utc: ml.ml_timestamp_utc ?? e.ml_timestamp_utc,
    per_feature: (ml.per_feature ?? e.per_feature),
  };
}

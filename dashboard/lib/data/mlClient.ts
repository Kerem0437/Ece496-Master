import type { Experiment, ExperimentSummary, FeatureSeriesMap, MLFlag, Measurement } from "@/lib/types";

const ML_URL = process.env.ML_SERVICE_URL ?? "http://127.0.0.1:8000";

type MlResult = {
  ml_version?: string;
  anomaly_score?: number;
  ml_flag?: MLFlag;
  ml_timestamp_utc?: string;
  review_basis?: string;
  verification_status?: "VERIFIED" | "PENDING";
  mode_keep?: Record<string, number>;
  per_feature?: Record<string, {
    score?: number | null;
    normal_score?: number | null;
    strict_score?: number | null;
    normal_masked_mse?: number | null;
    strict_masked_mse?: number | null;
    normal_observed_fraction?: number | null;
    strict_observed_fraction?: number | null;
    zero_drop_detected?: boolean | null;
    jump_ratio?: number | null;
    jump_score?: number | null;
    flag?: MLFlag;
  }>;
  predicted_series_by_feature?: FeatureSeriesMap | null;
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

export async function fetchMlForExperimentId(experiment_id: string, include_predictions = false): Promise<MlResult | null> {
  const qs = include_predictions ? "?include_predictions=1" : "";
  return await safeFetchJson<MlResult>(`${ML_URL}/api/ml/${encodeURIComponent(experiment_id)}${qs}`);
}

export async function scoreMeasurements(experiment_id: string, measurements: Measurement[], include_predictions = false): Promise<MlResult | null> {
  const payload = {
    experiment_id,
    include_predictions,
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
    predicted_series_by_feature: (ml.predicted_series_by_feature ?? e.predicted_series_by_feature),
  };
}

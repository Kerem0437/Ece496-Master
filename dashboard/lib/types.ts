export type IntegrityStatus = "VALID" | "INVALID" | "UNKNOWN" | "VERIFIED";
export type MLFlag = "NORMAL" | "SUSPICIOUS" | "UNKNOWN" | "INSUFFICIENT_DATA";

export type DataSourceType = "real_sensor" | "lab_instrument" | "simulated";

export type PredictionPoint = {
  time_offset_seconds: number;
  value: number;
};

export type PredictionModes = {
  normal?: PredictionPoint[];
  strict?: PredictionPoint[];
};

export type FeatureSeriesMap = Record<string, PredictionModes>;

export type PerFeatureScore = {
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
};

export type PerFeatureMap = Record<string, PerFeatureScore>;

export type Experiment = {
  experiment_id: string;
  device_id: string;
  device_alias: string;
  start_timestamp_utc: string;
  end_timestamp_utc: string | null;
  contaminant_type: string | null;
  pH_initial: number | null;
  light_intensity: number | null;
  temperature: number | null;
  site_location: string | null;
  data_source_type: DataSourceType;
  hash: string | null;
  signature: string | null;
  device_cert_id: string | null;
  integrity_status: IntegrityStatus;
  source_file_id: string | null;
  ml_version: string | null;
  anomaly_score: number | null;
  ml_flag: MLFlag;
  per_feature?: PerFeatureMap | null;
  predicted_series_by_feature?: FeatureSeriesMap | null;
  ml_timestamp_utc: string | null;
  prediction_curve: PredictionPoint[] | null;
  primary_sensor_type?: string | null;
};

export type Measurement = {
  measurement_id: string;
  experiment_id: string;
  timestamp_utc: string;
  device_id: string;
  sensor_type: string;
  value: number;
  unit: string;
  sample_index: number;
  time_offset_seconds: number;
};

export type ExperimentSummary = {
  experiment_id: string;
  device_id: string;
  device_alias: string;
  start_timestamp_utc: string;
  end_timestamp_utc: string | null;
  integrity_status: IntegrityStatus;
  ml_flag: MLFlag;
  per_feature?: PerFeatureMap | null;
  sensor_types: string[];
};

// Keep types aligned with the required master variable names.
// Why: when T6+ replaces mock data with real DB/API, types remain stable.

export type IntegrityStatus = "VALID" | "INVALID" | "UNKNOWN";
export type MLFlag = "NORMAL" | "SUSPICIOUS" | "UNKNOWN" | "INSUFFICIENT_DATA";

export type DataSourceType = "real_sensor" | "lab_instrument" | "simulated";

export type PredictionPoint = {
  time_offset_seconds: number;
  value: number;
};

export type Experiment = {
  // Required identifiers
  experiment_id: string;

  // Time + device
  device_id: string;
  device_alias: string;

  start_timestamp_utc: string;
  end_timestamp_utc: string | null;

  // Experiment metadata
  contaminant_type: string | null;
  pH_initial: number | null;
  light_intensity: number | null;
  temperature: number | null;
  site_location: string | null;
  data_source_type: DataSourceType;

  // Integrity / custody
  hash: string | null;
  signature: string | null;
  device_cert_id: string | null;
  integrity_status: IntegrityStatus;
  source_file_id: string | null;

  // ML outputs
  ml_version: string | null;
  anomaly_score: number | null;
  ml_flag: MLFlag;
  ml_timestamp_utc: string | null;

  // Optional predicted curve (placeholder allowed)
  prediction_curve: PredictionPoint[] | null;

  // Optional convenience fields (not required by spec, but helpful)
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

  // You may later add per-measurement integrity/ml fields if needed,
  // but T1–T5 focuses on experiment-level status.
};

// Summary object for list view (T4).
export type ExperimentSummary = {
  experiment_id: string;
  device_id: string;
  device_alias: string;

  start_timestamp_utc: string;
  end_timestamp_utc: string | null;

  integrity_status: IntegrityStatus;
  ml_flag: MLFlag;

  // Used by list view "Sensor types involved"
  sensor_types: string[];
};

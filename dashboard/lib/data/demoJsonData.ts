import fs from "fs";
import path from "path";
import type { Experiment, ExperimentSummary, Measurement } from "@/lib/types";

/**
 * demojson data source:
 * Reads from dashboard/demo-json (committed test dataset).
 * This works offline (no VPN).
 */
const ROOT = process.cwd();
const DEMO_DIR = path.join(ROOT, "demo-json");
const EXP_PATH = path.join(DEMO_DIR, "experiments.json");
const MEAS_DIR = path.join(DEMO_DIR, "measurements");

function readJson<T>(p: string): T {
  return JSON.parse(fs.readFileSync(p, "utf-8")) as T;
}

export function getExperimentsFromDemoJson(): ExperimentSummary[] {
  const exps = readJson<Experiment[]>(EXP_PATH);

  return exps.map((e) => ({
    experiment_id: e.experiment_id,
    device_id: e.device_id,
    device_alias: e.device_alias,
    start_timestamp_utc: e.start_timestamp_utc,
    end_timestamp_utc: e.end_timestamp_utc,
    integrity_status: e.integrity_status,
    ml_flag: e.ml_flag,
    sensor_types: [], // filled from measurements on demand / or by ML service
  }));
}

export function getExperimentByIdFromDemoJson(experiment_id: string): Experiment | null {
  const exps = readJson<Experiment[]>(EXP_PATH);
  return exps.find((e) => e.experiment_id === experiment_id) ?? null;
}

export function getMeasurementsByExperimentIdFromDemoJson(experiment_id: string): Measurement[] {
  const p = path.join(MEAS_DIR, `${experiment_id}.json`);
  if (!fs.existsSync(p)) return [];
  return readJson<Measurement[]>(p);
}

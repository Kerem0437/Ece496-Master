import type { Experiment, ExperimentSummary, Measurement, MLFlag, IntegrityStatus } from "@/lib/types";
import { promises as fs } from "fs";
import path from "path";

function demoRoot(): string {
  // dashboard/ is the Next.js project root
  return path.join(process.cwd(), "demo-json");
}

async function readJson<T>(p: string): Promise<T> {
  const raw = await fs.readFile(p, "utf-8");
  return JSON.parse(raw) as T;
}

async function loadExperiments(): Promise<Experiment[]> {
  const p = path.join(demoRoot(), "experiments.json");
  return await readJson<Experiment[]>(p);
}

function mlFlagOrDefault(v: any): MLFlag {
  const s = String(v ?? "").toUpperCase();
  if (s === "NORMAL" || s === "SUSPICIOUS" || s === "UNKNOWN" || s === "INSUFFICIENT_DATA") return s as MLFlag;
  return "UNKNOWN";
}

function integrityOrDefault(v: any): IntegrityStatus {
  const s = String(v ?? "").toUpperCase();
  if (s === "VALID" || s === "INVALID" || s === "UNKNOWN") return s as IntegrityStatus;
  return "UNKNOWN";
}

export async function getExperimentsFromDemoJson(): Promise<ExperimentSummary[]> {
  const exps = await loadExperiments();

  // Build sensor_types list from measurement file existence (fast) using a fixed set
  // (We avoid reading all measurement points for list page.)
  const defaultSensors = ["turbidity_voltage_V", "pH", "water_temp_C", "air_temp_C", "absorbance"];

  return exps.map((e) => ({
    experiment_id: e.experiment_id,
    device_id: e.device_id,
    device_alias: e.device_alias,
    start_timestamp_utc: e.start_timestamp_utc,
    end_timestamp_utc: e.end_timestamp_utc,
    integrity_status: integrityOrDefault(e.integrity_status),
    ml_flag: mlFlagOrDefault(e.ml_flag),
    sensor_types: defaultSensors,
  }));
}

export async function getExperimentByIdFromDemoJson(experiment_id: string): Promise<Experiment | null> {
  const exps = await loadExperiments();
  const exp = exps.find((e) => e.experiment_id === experiment_id);
  if (!exp) return null;

  // Normalize enums
  exp.integrity_status = integrityOrDefault(exp.integrity_status);
  exp.ml_flag = mlFlagOrDefault(exp.ml_flag);
  return exp;
}

export async function getMeasurementsByExperimentIdFromDemoJson(experiment_id: string): Promise<Measurement[]> {
  const p = path.join(demoRoot(), "measurements", `${experiment_id}.json`);
  try {
    return await readJson<Measurement[]>(p);
  } catch {
    return [];
  }
}

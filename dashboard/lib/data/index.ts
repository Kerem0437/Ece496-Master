import type { Experiment, ExperimentSummary, Measurement } from "@/lib/types";
import { getExperiments, getExperimentById, getMeasurementsByExperimentId } from "@/lib/data/mockData";
import {
  getExperimentsFromInflux,
  getExperimentByIdFromInflux,
  getMeasurementsByExperimentIdFromInflux
} from "@/lib/data/influxData";

const MODE = (process.env.DATA_MODE ?? "influx").toLowerCase();

export async function fetchExperiments(): Promise<ExperimentSummary[]> {
  if (MODE === "mock") return getExperiments();
  return await getExperimentsFromInflux();
}

export async function fetchExperimentById(experiment_id: string): Promise<Experiment | null> {
  if (MODE === "mock") return getExperimentById(experiment_id);
  return await getExperimentByIdFromInflux(experiment_id);
}

export async function fetchMeasurementsByExperimentId(experiment_id: string): Promise<Measurement[]> {
  if (MODE === "mock") return getMeasurementsByExperimentId(experiment_id);
  return await getMeasurementsByExperimentIdFromInflux(experiment_id);
}

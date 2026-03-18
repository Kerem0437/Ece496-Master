import type { Experiment, ExperimentSummary, Measurement } from "@/lib/types";
import { getExperiments, getExperimentById, getMeasurementsByExperimentId } from "@/lib/data/mockData";

// DATA_MODE options:
//   mock     -> built-in mockData (no DB)
//   demojson -> reads local JSON files under dashboard/demo-json (no DB)
//   influx    -> queries InfluxDB from server components (needs VPN/network)
const MODE = (process.env.DATA_MODE ?? "mock").toLowerCase();

export async function fetchExperiments(): Promise<ExperimentSummary[]> {
  if (MODE === "mock") return getExperiments();
  if (MODE === "demojson") {
    const { getExperimentsFromDemoJson } = await import("./demoJsonData");
    return await getExperimentsFromDemoJson();
  }
  const { getExperimentsFromInflux } = await import("./influxData");
  return await getExperimentsFromInflux();
}

export async function fetchExperimentById(experiment_id: string): Promise<Experiment | null> {
  if (MODE === "mock") return getExperimentById(experiment_id);
  if (MODE === "demojson") {
    const { getExperimentByIdFromDemoJson } = await import("./demoJsonData");
    return await getExperimentByIdFromDemoJson(experiment_id);
  }
  const { getExperimentByIdFromInflux } = await import("./influxData");
  return await getExperimentByIdFromInflux(experiment_id);
}

export async function fetchMeasurementsByExperimentId(experiment_id: string): Promise<Measurement[]> {
  if (MODE === "mock") return getMeasurementsByExperimentId(experiment_id);
  if (MODE === "demojson") {
    const { getMeasurementsByExperimentIdFromDemoJson } = await import("./demoJsonData");
    return await getMeasurementsByExperimentIdFromDemoJson(experiment_id);
  }
  const { getMeasurementsByExperimentIdFromInflux } = await import("./influxData");
  return await getMeasurementsByExperimentIdFromInflux(experiment_id);
}

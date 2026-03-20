import type { Experiment, ExperimentSummary, Measurement } from "@/lib/types";
import { getExperiments, getExperimentById, getMeasurementsByExperimentId } from "@/lib/data/mockData";
import {
  getExperimentsFromDemoJson,
  getExperimentByIdFromDemoJson,
  getMeasurementsByExperimentIdFromDemoJson,
} from "@/lib/data/demoJsonData";
import { fetchMlForExperimentId, mergeMlIntoSummary, mergeMlIntoExperiment, scoreMeasurements } from "@/lib/data/mlClient";

const MODE = (process.env.DATA_MODE ?? "mock").toLowerCase();

/**
 * Data modes:
 *  - mock: in-code mock dataset
 *  - demojson: reads dashboard/demo-json (offline reproducible)
 *  - influx: reads InfluxDB on VM2 (requires VPN + SSH tunnel)
 *
 * ML is served by a separate ML service (ML_SERVICE_URL) and is NOT written back to DB.
 */
export async function fetchExperiments(): Promise<ExperimentSummary[]> {
  let base: ExperimentSummary[];

  if (MODE === "mock") base = getExperiments();
  else if (MODE === "demojson") base = getExperimentsFromDemoJson();
  else {
    const { getExperimentsFromInflux } = await import("./influxData");
    base = await getExperimentsFromInflux();
  }

  // Attach ML flags (list view).
  // demojson: ML service can score by experiment_id (reads local JSON).
  // influx: we fetch a small latest window per experiment and POST it to ML service.
  const max = Number(process.env.ML_MAX_LIST ?? "20");
  const slice = base.slice(0, max);

  if (MODE === "influx") {
    const { getLatestWindowMeasurementsFromInflux } = await import("./influxData");
    const scored = await Promise.allSettled(
      slice.map(async (e) => {
        const win = await getLatestWindowMeasurementsFromInflux(e.experiment_id);
        const ml = await scoreMeasurements(e.experiment_id, win);
        return mergeMlIntoSummary(e, ml);
      })
    );
    const merged = scored.map((r, i) => (r.status === "fulfilled" ? r.value : slice[i]));
    return merged.concat(base.slice(max));
  }

  const mlResults = await Promise.allSettled(slice.map((e) => fetchMlForExperimentId(e.experiment_id)));
  const merged = slice.map((e, i) => {
    const r = mlResults[i];
    return mergeMlIntoSummary(e, r.status === "fulfilled" ? r.value : null);
  });

  return merged.concat(base.slice(max));
}

export async function fetchExperimentByIdexport async function fetchExperimentById(experiment_id: string): Promise<Experiment | null> {
  let exp: Experiment | null;

  if (MODE === "mock") exp = getExperimentById(experiment_id);
  else if (MODE === "demojson") exp = getExperimentByIdFromDemoJson(experiment_id);
  else {
    const { getExperimentByIdFromInflux } = await import("./influxData");
    exp = await getExperimentByIdFromInflux(experiment_id);
  }
  if (!exp) return null;

  // Attach ML details (detail view)
  // For demojson: ML service reads local JSON by experiment_id.
  // For influx: we compute ML from the latest window by POSTing measurements.
  if (MODE === "influx") {
    const minutes = Number(process.env.NEXT_PUBLIC_LIVE_SCORE_WINDOW_MINUTES ?? process.env.LIVE_SCORE_WINDOW_MINUTES ?? "5");
    const { getRecentWindowMeasurementsFromInflux } = await import("./influxData");
    const win = await getRecentWindowMeasurementsFromInflux(experiment_id, minutes);
    const ml = await scoreMeasurements(experiment_id, win);
    return mergeMlIntoExperiment(exp, ml);
  } else {
    const ml = await fetchMlForExperimentId(experiment_id);
    return mergeMlIntoExperiment(exp, ml);
  }
}

export async function fetchMeasurementsByExperimentId(experiment_id: string): Promise<Measurement[]> {
  if (MODE === "mock") return getMeasurementsByExperimentId(experiment_id);
  if (MODE === "demojson") return getMeasurementsByExperimentIdFromDemoJson(experiment_id);
  const { getMeasurementsByExperimentIdFromInflux } = await import("./influxData");
  return await getMeasurementsByExperimentIdFromInflux(experiment_id);
}
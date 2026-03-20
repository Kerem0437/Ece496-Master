import { fetchExperiments } from "@/lib/data";
import ExperimentsClient from "./ExperimentsClient";

export default async function ExperimentsPage() {
  const experiments = await fetchExperiments();

  return (
    <div>
      <h1 className="h1">Experiments</h1>
      <p className="sub">
        List view with filtering/sorting. Data source:
        <span className="mono"> {process.env.DATA_MODE ?? "influx"}</span>
        <span className="sub"> • Live auto-refresh uses NEXT_PUBLIC_LIVE_LIST_REFRESH_SECONDS</span>
      </p>
      <ExperimentsClient experiments={experiments} mode={(process.env.DATA_MODE ?? "mock").toLowerCase()} />
    </div>
  );
}

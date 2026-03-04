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
      </p>
      <ExperimentsClient experiments={experiments} />
    </div>
  );
}

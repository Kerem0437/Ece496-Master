import Link from "next/link";
import Card from "@/components/Card";
import StatusPill from "@/components/StatusPill";
import ChartPlaceholder from "@/components/ChartPlaceholder";

import { fetchExperimentById, fetchMeasurementsByExperimentId } from "@/lib/data";
import LiveView from "./LiveView";
import type { FeatureSeriesMap, IntegrityStatus, Measurement } from "@/lib/types";

import {
  computeDurationSeconds,
  computeStats,
  formatUtc,
  safe,
} from "@/lib/utils";

function toActualPoints(measurements: Measurement[], sensor_type: string) {
  return measurements
    .filter((m) => m.sensor_type === sensor_type)
    .sort((a, b) => (a.time_offset_seconds ?? 0) - (b.time_offset_seconds ?? 0))
    .map((m) => ({ x: m.time_offset_seconds ?? 0, y: m.value }));
}

function unitForSensor(measurements: Measurement[], sensor_type: string) {
  return measurements.find((m) => m.sensor_type === sensor_type)?.unit ?? "—";
}

export default async function ExperimentDetailPage({
  params,
}: {
  params: Promise<{ experiment_id: string }>;
}) {
  const { experiment_id: rawExperimentId } = await params;
  const experiment_id = decodeURIComponent(rawExperimentId);

  const experiment = await fetchExperimentById(experiment_id);
  if (!experiment) {
    return (
      <div>
        <h1 className="h1">Experiment not found</h1>
        <p className="sub">
          No experiment exists with ID <span className="mono">{experiment_id}</span>.
        </p>
        <Link className="btn" href="/experiments">← Back to Experiments</Link>
      </div>
    );
  }

  if ((process.env.DATA_MODE ?? "").toLowerCase() === "influx") {
    return (
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <div>
            <h1 className="h1">Experiment Detail (Live)</h1>
            <p className="sub">ID: <span className="mono">{experiment.experiment_id}</span></p>
          </div>
          <Link className="btn" href="/experiments">← Back to Experiments</Link>
        </div>
        <LiveView experiment_id={experiment.experiment_id} />
      </div>
    );
  }

  const measurements = await fetchMeasurementsByExperimentId(experiment_id);
  const experiment_duration_seconds = computeDurationSeconds(
    experiment.start_timestamp_utc,
    experiment.end_timestamp_utc,
  );

  const sensorTypes = Array.from(new Set(measurements.map((m) => m.sensor_type)));
  const predictedByFeature = (experiment.predicted_series_by_feature ?? {}) as FeatureSeriesMap;
  const chartSensorTypes = Array.from(new Set([...sensorTypes, ...Object.keys(predictedByFeature)])).sort();

  const primarySensor = experiment.primary_sensor_type ?? (measurements[0]?.sensor_type ?? "spectrometer");
  const primarySeries = measurements.filter((m) => m.sensor_type === primarySensor);
  const stats = computeStats(primarySeries.map((m) => m.value));

  const verificationStatus: IntegrityStatus = experiment.ml_timestamp_utc ? "VERIFIED" : experiment.integrity_status;
  const showWarning = experiment.integrity_status === "INVALID" || experiment.ml_flag === "SUSPICIOUS";

  const DEFAULT_N = 18;
  const shown = measurements.slice(0, DEFAULT_N);
  const remaining = Math.max(0, measurements.length - DEFAULT_N);

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div>
          <h1 className="h1">Experiment Detail</h1>
          <p className="sub">
            ID: <span className="mono">{experiment.experiment_id}</span>
          </p>
        </div>
        <Link className="btn" href="/experiments">← Back</Link>
      </div>

      {showWarning && (
        <div className="bannerWarn">
          Warning: this experiment is flagged as {verificationStatus} and {experiment.ml_flag}.
        </div>
      )}

      <div className="grid2">
        <Card title="Header" subtitle="Experiment identity and timing (T5)">
          <div className="kv">
            <div className="k">experiment_id</div><div className="v mono">{safe(experiment.experiment_id)}</div>
            <div className="k">device_id</div><div className="v mono">{safe(experiment.device_id)}</div>
            <div className="k">device_alias</div><div className="v">{safe(experiment.device_alias)}</div>
            <div className="k">site_location</div><div className="v">{safe(experiment.site_location)}</div>
            <div className="k">start_timestamp_utc</div><div className="v mono">{formatUtc(experiment.start_timestamp_utc)}</div>
            <div className="k">end_timestamp_utc</div>
            <div className="v mono">
              {experiment.end_timestamp_utc ? formatUtc(experiment.end_timestamp_utc) : "ongoing"}
            </div>
            <div className="k">experiment_duration_seconds</div><div className="v mono">{experiment_duration_seconds}</div>
            <div className="k">record_count</div><div className="v mono">{measurements.length}</div>
          </div>
        </Card>

        <Card title="Status" subtitle="Per-feature gap-fill verification">
          <div className="badgeRow" style={{ marginBottom: 10 }}>
            <StatusPill kind="integrity" value={verificationStatus} />
            <StatusPill kind="ml" value={experiment.ml_flag} />
          </div>

          <div className="kv">
            <div className="k">verification_status</div><div className="v mono">{verificationStatus}</div>
            <div className="k">raw_integrity_status</div><div className="v mono">{safe(experiment.integrity_status)}</div>
            <div className="k">source_file_id</div><div className="v mono">{safe(experiment.source_file_id)}</div>
            <div className="k">ml_version</div><div className="v mono">{safe(experiment.ml_version)}</div>
            <div className="k">anomaly_score</div><div className="v mono">{safe(experiment.anomaly_score)}</div>
            <div className="k">ml_timestamp_utc</div><div className="v mono">{safe(experiment.ml_timestamp_utc ? formatUtc(experiment.ml_timestamp_utc) : "—")}</div>
          </div>

          {experiment.per_feature ? (
            <div style={{ marginTop: 14, display: "grid", gap: 8 }}>
              <div className="small">
                Each modeled variable is reviewed twice: <span className="mono">normal</span> keeps about 90% of points and predicts the missing 10%; <span className="mono">strict</span> keeps about 75% and predicts the remaining 25%.
              </div>
              <div style={{ display: "grid", gap: 8 }}>
                {Object.entries(experiment.per_feature).map(([feature, value]) => (
                  <div key={feature} style={{ display: "grid", gridTemplateColumns: "minmax(180px, 1fr) auto auto auto auto", gap: 10, alignItems: "center", border: "1px solid rgba(15,23,42,0.12)", borderRadius: 12, padding: 10 }}>
                    <div className="mono">{feature}</div>
                    <StatusPill kind="ml" value={value.flag ?? "UNKNOWN"} />
                    <div className="small">normal: <span className="mono">{value.normal_score ?? "—"}</span> • strict: <span className="mono">{value.strict_score ?? "—"}</span></div>
                    <div className="small">normal mse: <span className="mono">{value.normal_masked_mse ?? "—"}</span> • strict mse: <span className="mono">{value.strict_masked_mse ?? "—"}</span></div>
                    <div className="small">jump: <span className="mono">{value.jump_ratio ?? "—"}</span> • jump score: <span className="mono">{value.jump_score ?? "—"}</span> • zero-drop: <span className="mono">{value.zero_drop_detected ? "YES" : "NO"}</span></div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </Card>
      </div>

      <div className="grid2">
        <Card title="Metadata" subtitle="Experiment context fields (T5)">
          <div className="kv">
            <div className="k">contaminant_type</div><div className="v">{safe(experiment.contaminant_type)}</div>
            <div className="k">pH_initial</div><div className="v mono">{safe(experiment.pH_initial)}</div>
            <div className="k">light_intensity</div><div className="v mono">{safe(experiment.light_intensity)}</div>
            <div className="k">temperature</div><div className="v mono">{safe(experiment.temperature)}</div>
            <div className="k">data_source_type</div><div className="v mono">{safe(experiment.data_source_type)}</div>
          </div>
        </Card>

        <Card title="Quick Stats" subtitle={`Computed from primary series: ${primarySensor}`}>
          <div className="kv">
            <div className="k">value_min</div><div className="v mono">{stats.value_min}</div>
            <div className="k">value_max</div><div className="v mono">{stats.value_max}</div>
            <div className="k">value_mean</div><div className="v mono">{stats.value_mean}</div>
          </div>
          <div className="small" style={{ marginTop: 10 }}>
            The predicted curves below are not a generic smoothing overlay. They come from the trained per-variable gap-fill models, which only see a subset of the raw points and reconstruct the rest.
          </div>
        </Card>
      </div>

      <Card title="ML verification note" subtitle="What is being verified on this page.">
        <div className="small" style={{ display: "grid", gap: 8 }}>
          <div>The run becomes <span className="mono">VERIFIED</span> once the ML service completes the review and returns a timestamped result.</div>
          <div>For each modeled variable, the service creates two hidden-point tests: <span className="mono">normal</span> (~90% raw shown, ~10% hidden) and <span className="mono">strict</span> (~75% raw shown, ~25% hidden).</div>
          <div>The hidden points are reconstructed by that variable’s own model and then re-anchored to the observed raw points so the review curve remains a faithful approximation of the real signal. A variable is only marked suspicious when the hidden-point error is meaningfully high, not just because the strict review is slightly off.</div>
          <div>Monitored live variables also have zero-drop protection, so a sudden collapse to zero can immediately escalate the run to suspicious even if the reconstruction score looks acceptable.</div>
        </div>
      </Card>

      <Card title="All variables: actual vs ML predicted" subtitle="Each variable is shown against its own per-variable model. The default predicted curve is the normal review; the strict review is shown separately as a tougher check.">
        <div style={{ display: "grid", gap: 16 }}>
          {chartSensorTypes.map((sensor_type) => {
            const actualPoints = toActualPoints(measurements, sensor_type);
            const predictedModes = predictedByFeature[sensor_type] ?? {};
            const normalPoints = predictedModes.normal ?? [];
            const strictPoints = predictedModes.strict ?? [];
            const unit = unitForSensor(measurements, sensor_type);
            return (
              <div key={sensor_type} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                <ChartPlaceholder
                  title={`Actual: ${sensor_type}`}
                  unit={unit}
                  points={actualPoints}
                />
                {normalPoints.length > 0 ? (
                  <ChartPlaceholder
                    title={`Predicted: ${sensor_type}`}
                    unit={unit}
                    points={normalPoints.map((p) => ({ x: p.time_offset_seconds, y: p.value }))}
                  />
                ) : (
                  <Card title={`Predicted: ${sensor_type}`} subtitle="This variable is not currently modeled.">
                    <div className="small">No normal-mode prediction was returned for <span className="mono">{sensor_type}</span>.</div>
                  </Card>
                )}
                {strictPoints.length > 0 ? (
                  <ChartPlaceholder
                    title={`Predicted (Strict Review): ${sensor_type}`}
                    unit={unit}
                    points={strictPoints.map((p) => ({ x: p.time_offset_seconds, y: p.value }))}
                  />
                ) : (
                  <Card title={`Predicted (Strict Review): ${sensor_type}`} subtitle="This variable is not currently modeled.">
                    <div className="small">No strict-mode prediction was returned for <span className="mono">{sensor_type}</span>.</div>
                  </Card>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      <Card title="Raw measurements" subtitle="First N records (T5). Shows all required measurement fields.">
        <div className="tableWrap" style={{ boxShadow: "none" }}>
          <table style={{ minWidth: 980 }}>
            <thead>
              <tr>
                <th>measurement_id</th>
                <th>timestamp_utc</th>
                <th>sensor_type</th>
                <th>value</th>
                <th>unit</th>
                <th>sample_index</th>
                <th>time_offset_seconds</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((m) => (
                <tr key={m.measurement_id}>
                  <td className="mono">{m.measurement_id}</td>
                  <td className="mono">{formatUtc(m.timestamp_utc)}</td>
                  <td className="mono">{m.sensor_type}</td>
                  <td className="mono">{m.value}</td>
                  <td className="mono">{m.unit}</td>
                  <td className="mono">{m.sample_index}</td>
                  <td className="mono">{m.time_offset_seconds}</td>
                </tr>
              ))}
              {shown.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ padding: 18, color: "#475569" }}>
                    No measurements found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {remaining > 0 ? (
          <div style={{ marginTop: 10 }} className="small">
            Showing first <span className="mono">{DEFAULT_N}</span> of <span className="mono">{measurements.length}</span>.
          </div>
        ) : (
          <div style={{ marginTop: 10 }} className="small">
            Showing all <span className="mono">{measurements.length}</span> records.
          </div>
        )}
      </Card>
    </div>
  );
}

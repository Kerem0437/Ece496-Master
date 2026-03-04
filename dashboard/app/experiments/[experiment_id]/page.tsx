import Link from "next/link";
import Card from "@/components/Card";
import StatusPill from "@/components/StatusPill";
import ChartPlaceholder from "@/components/ChartPlaceholder";

import { fetchExperimentById, fetchMeasurementsByExperimentId } from "@/lib/data";

import {
  computeDurationSeconds,
  computeStats,
  formatUtc,
  safe
} from "@/lib/utils";

export default async function ExperimentDetailPage({ params }: { params: { experiment_id: string } }) {
  const experiment_id = decodeURIComponent(params.experiment_id);

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

  const measurements = await fetchMeasurementsByExperimentId(experiment_id);
  const experiment_duration_seconds = computeDurationSeconds(
    experiment.start_timestamp_utc,
    experiment.end_timestamp_utc
  );

  // For chart: we show the primary spectrometer series (if present), otherwise first sensor_type.
  const primarySensor = experiment.primary_sensor_type ?? (measurements[0]?.sensor_type ?? "spectrometer");
  const primarySeries = measurements.filter(m => m.sensor_type === primarySensor);

  const stats = computeStats(primarySeries.map(m => m.value));

  const showWarning = experiment.integrity_status === "INVALID" || experiment.ml_flag === "SUSPICIOUS";

  // Raw table pagination (simple: show first N, then allow expand)
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
          Warning: This experiment is flagged as{" "}
          {experiment.integrity_status === "INVALID" ? "INTEGRITY INVALID" : "OK"}{" "}
          and{" "}
          {experiment.ml_flag === "SUSPICIOUS" ? "ML SUSPICIOUS" : "ML OK"}.
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

        <Card title="Status" subtitle="Integrity + ML outputs (T5)">
          <div className="badgeRow" style={{ marginBottom: 10 }}>
            <StatusPill kind="integrity" value={experiment.integrity_status} />
            <StatusPill kind="ml" value={experiment.ml_flag} />
          </div>

          <div className="kv">
            <div className="k">integrity_status</div><div className="v mono">{safe(experiment.integrity_status)}</div>
            <div className="k">hash</div><div className="v mono">{safe(experiment.hash)}</div>
            <div className="k">signature</div><div className="v mono">{safe(experiment.signature)}</div>
            <div className="k">device_cert_id</div><div className="v mono">{safe(experiment.device_cert_id)}</div>
            <div className="k">source_file_id</div><div className="v mono">{safe(experiment.source_file_id)}</div>

            <div className="k" style={{ marginTop: 12 }}>ml_version</div><div className="v mono">{safe(experiment.ml_version)}</div>
            <div className="k">anomaly_score</div><div className="v mono">{safe(experiment.anomaly_score)}</div>
            <div className="k">ml_timestamp_utc</div><div className="v mono">{safe(experiment.ml_timestamp_utc ? formatUtc(experiment.ml_timestamp_utc) : "—")}</div>
          </div>
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
            These are frontend-derived (T5). Later you can compute server-side if needed.
          </div>
        </Card>
      </div>

      <Card title="Time-series" subtitle="Lightweight placeholder chart (no chart library yet)">
        <div style={{ display: "grid", gap: 12 }}>
          <ChartPlaceholder
            title={`Actual series (${primarySensor})`}
            unit={primarySeries[0]?.unit ?? "—"}
            points={primarySeries.map((m) => ({
              x: m.time_offset_seconds,
              y: m.value
            }))}
          />

          {experiment.prediction_curve && experiment.prediction_curve.length > 0 ? (
            <ChartPlaceholder
              title="Predicted series (prediction_curve)"
              unit={primarySeries[0]?.unit ?? "—"}
              points={experiment.prediction_curve.map((p) => ({
                x: p.time_offset_seconds,
                y: p.value
              }))}
            />
          ) : (
            <div className="small">
              No <span className="mono">prediction_curve</span> provided for this experiment (mock). That’s OK.
            </div>
          )}
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
                  <td colSpan={7} style={{ padding: 18, color: "#94a3b8" }}>
                    No measurements found for this experiment (mock).
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {remaining > 0 ? (
          <div style={{ marginTop: 10 }} className="small">
            Showing first <span className="mono">{DEFAULT_N}</span> of{" "}
            <span className="mono">{measurements.length}</span>. (Mock pagination)
            <br />
            In T6+, you can implement real pagination via API/DB queries.
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

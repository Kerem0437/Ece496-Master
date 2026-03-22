"use client";

import { useEffect, useMemo, useState } from "react";
import Card from "@/components/Card";
import StatusPill from "@/components/StatusPill";
import ChartPlaceholder from "@/components/ChartPlaceholder";
import type { IntegrityStatus, Measurement, MLFlag, PerFeatureMap } from "@/lib/types";

type MlPayload = {
  ml_version?: string;
  anomaly_score?: number;
  ml_flag?: MLFlag;
  ml_timestamp_utc?: string;
  per_feature?: PerFeatureMap | null;
};

function toPoints(measurements: Measurement[], sensor_type: string) {
  const series = measurements
    .filter((m) => m.sensor_type === sensor_type)
    .sort((a, b) => (a.time_offset_seconds ?? 0) - (b.time_offset_seconds ?? 0));

  return series.map((m) => ({ x: m.time_offset_seconds ?? 0, y: m.value }));
}

export default function LiveView({ experiment_id }: { experiment_id: string }) {
  const chartWindowMin = Number(process.env.NEXT_PUBLIC_LIVE_CHART_WINDOW_MINUTES ?? "2");
  const scoreWindowMin = Number(process.env.NEXT_PUBLIC_LIVE_SCORE_WINDOW_MINUTES ?? "2");
  const chartRefreshSec = Number(process.env.NEXT_PUBLIC_LIVE_CHART_REFRESH_SECONDS ?? "120");
  const scoreRefreshSec = Number(process.env.NEXT_PUBLIC_LIVE_SCORE_REFRESH_SECONDS ?? "120");

  const [measurements, setMeasurements] = useState<Measurement[]>([]);
  const [ml, setMl] = useState<MlPayload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function refreshMeasurements() {
    try {
      const r = await fetch(`/api/live/measurements?experiment_id=${encodeURIComponent(experiment_id)}&minutes=${chartWindowMin}`, { cache: "no-store" });
      const j = await r.json();
      setMeasurements(j.measurements ?? []);
      setErr(null);
    } catch (e: any) {
      setErr(String(e));
    }
  }

  async function refreshMl() {
    try {
      const r = await fetch(`/api/live/ml?experiment_id=${encodeURIComponent(experiment_id)}&minutes=${scoreWindowMin}`, { cache: "no-store" });
      const j = await r.json();
      setMl(j.ml ?? null);
      setErr(null);
    } catch (e: any) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    refreshMeasurements();
    refreshMl();

    const refreshBoth = () => {
      refreshMeasurements();
      refreshMl();
    };
    const intervalSec = Math.max(10, Math.min(chartRefreshSec, scoreRefreshSec));
    const t1 = setInterval(refreshBoth, intervalSec * 1000);
    return () => {
      clearInterval(t1);
    };
  }, [experiment_id]);

  const sensorTypes = useMemo(() => {
    const set = new Set(measurements.map((m) => m.sensor_type));
    return Array.from(set);
  }, [measurements]);

  const verificationStatus: IntegrityStatus = ml?.ml_timestamp_utc ? "VERIFIED" : "UNKNOWN";
  const per = ml?.per_feature ?? null;
  const zeroDropDetected = Object.values(per ?? {}).some((v) => Boolean(v?.zero_drop_detected));

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <Card
        title="Live rolling view"
        subtitle={`Collects a rolling ${chartWindowMin} minute window, archives it to disk, and refreshes both charts and ML every ${chartRefreshSec}s.`}
      >
        <div className="sub" style={{ marginTop: 6 }}>
          Data source: <span className="mono">live (influx)</span> • ML served by <span className="mono">ml_service</span> (no DB writes) • snapshots archived under <span className="mono">dashboard/live_captures</span>
        </div>
        <div className="small" style={{ marginTop: 8 }}>
          Live protection: if a monitored variable suddenly falls to zero after a stable baseline, the stream is automatically marked suspicious.
        </div>
        {err ? <div className="sub" style={{ color: "#fca5a5" }}>Error: {err}</div> : null}
      </Card>

      <Card title="ML status (rolling window)">
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <StatusPill kind="integrity" value={verificationStatus} />
          <StatusPill kind="ml" value={(ml?.ml_flag ?? "UNKNOWN")} />
          <div className="sub">anomaly_score: <span className="mono">{ml?.anomaly_score ?? "—"}</span></div>
          <div className="sub">timestamp: <span className="mono">{ml?.ml_timestamp_utc ?? "—"}</span></div>
        </div>
        {zeroDropDetected ? (
          <div className="small" style={{ marginTop: 10, color: "#fcd34d" }}>
            Zero-drop protection fired: one or more monitored channels abruptly dropped to zero, so the live stream was escalated to suspicious.
          </div>
        ) : null}

        {per ? (
          <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
            <div className="sub">Per-sensor flags (computed from reconstruction error, jump analysis, and zero-drop protection):</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 10 }}>
              {Object.entries(per).map(([k, v]) => (
                <div key={k} style={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, padding: 10 }}>
                  <div className="mono" style={{ fontSize: 13 }}>{k}</div>
                  <div style={{ marginTop: 6, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                    <StatusPill kind="ml" value={(v.flag ?? "UNKNOWN")} />
                    <div className="sub">score: <span className="mono">{(v.score ?? "—") as any}</span></div>
                    <div className="sub">zero-drop: <span className="mono">{v.zero_drop_detected ? "YES" : "NO"}</span></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="sub" style={{ marginTop: 10 }}>Per-sensor details not available.</div>
        )}
      </Card>

      {sensorTypes.includes("pH") ? (
        <ChartPlaceholder title={`pH (last ${chartWindowMin} min)`} unit="pH" points={toPoints(measurements, "pH")} />
      ) : null}
      {sensorTypes.includes("turbidity_voltage_V") ? (
        <ChartPlaceholder title={`turbidity_voltage_V (last ${chartWindowMin} min)`} unit="V" points={toPoints(measurements, "turbidity_voltage_V")} />
      ) : null}
      {sensorTypes.includes("water_temp_C") ? (
        <ChartPlaceholder title={`water_temp_C (last ${chartWindowMin} min)`} unit="C" points={toPoints(measurements, "water_temp_C")} />
      ) : null}
      {sensorTypes.includes("air_temp_C") ? (
        <ChartPlaceholder title={`air_temp_C (last ${chartWindowMin} min)`} unit="C" points={toPoints(measurements, "air_temp_C")} />
      ) : null}
      {sensorTypes.includes("air_humidity_pct") ? (
        <ChartPlaceholder title={`air_humidity_pct (last ${chartWindowMin} min)`} unit="%" points={toPoints(measurements, "air_humidity_pct")} />
      ) : null}
    </div>
  );
}

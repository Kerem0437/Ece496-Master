"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { ExperimentSummary, IntegrityStatus, MLFlag } from "@/lib/types";
import { computeFreshnessMinutes, formatUtc, unique } from "@/lib/utils";
import StatusPill from "@/components/StatusPill";
import Card from "@/components/Card";

type Props = { experiments: ExperimentSummary[]; mode: string };

export default function ExperimentsClient({ experiments, mode }: Props) {
  const router = useRouter();
  const refreshSeconds = Number(process.env.NEXT_PUBLIC_LIVE_LIST_REFRESH_SECONDS ?? "120");

  useEffect(() => {
    if (mode !== "influx") return;
    const t = setInterval(() => router.refresh(), Math.max(15, refreshSeconds) * 1000);
    return () => clearInterval(t);
  }, [mode, router, refreshSeconds]);

  // Simple, local UI state for filters (T4 requirement).
  const [device_id, setDeviceId] = useState<string>("ALL");
  const [integrity_status, setIntegrityStatus] = useState<IntegrityStatus | "ALL">("ALL");
  const [ml_flag, setMlFlag] = useState<MLFlag | "ALL">("ALL");
  const [lastHours, setLastHours] = useState<number>(99999); // default: show all (demo-friendly)

  const deviceOptions = useMemo(() => ["ALL", ...unique(experiments.map(e => e.device_id))], [experiments]);

  const filtered = useMemo(() => {
    const now = new Date();

    return experiments
      .filter((e) => {
        if (device_id !== "ALL" && e.device_id !== device_id) return false;
        if (integrity_status !== "ALL" && e.integrity_status !== integrity_status) return false;
        if (ml_flag !== "ALL" && e.ml_flag !== ml_flag) return false;

        // time window filter based on start_timestamp_utc
        const start = new Date(e.start_timestamp_utc);
        const cutoff = new Date(now.getTime() - lastHours * 60 * 60 * 1000);
        return start >= cutoff;
      })
      .sort((a, b) => new Date(b.start_timestamp_utc).getTime() - new Date(a.start_timestamp_utc).getTime());
  }, [experiments, device_id, integrity_status, ml_flag, lastHours]);

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <Card
        title="Filters"
        subtitle="Client-side filters (mock). Later can be replaced with server-side query params."
      >
        <div className="controls">
          <div className="control">
            <label>device_id</label>
            <select value={device_id} onChange={(e) => setDeviceId(e.target.value)}>
              {deviceOptions.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </div>

          <div className="control">
            <label>integrity_status</label>
            <select
              value={integrity_status}
              onChange={(e) => setIntegrityStatus(e.target.value as any)}
            >
              <option value="ALL">ALL</option>
              <option value="VALID">VALID</option>
              <option value="INVALID">INVALID</option>
              <option value="UNKNOWN">UNKNOWN</option>
            </select>
          </div>

          <div className="control">
            <label>ml_flag</label>
            <select value={ml_flag} onChange={(e) => setMlFlag(e.target.value as any)}>
              <option value="ALL">ALL</option>
              <option value="NORMAL">NORMAL</option>
              <option value="SUSPICIOUS">SUSPICIOUS</option>
              <option value="UNKNOWN">UNKNOWN</option>
              <option value="INSUFFICIENT_DATA">INSUFFICIENT_DATA</option>
            </select>
          </div>

          <div className="control">
            <label>last N hours</label>
            <input
              type="number"
              value={lastHours}
              min={1}
              max={999999}
              onChange={(e) => setLastHours(Number(e.target.value))}
              style={{ width: 80 }}
            />
          </div>

          <div className="small" style={{ alignSelf: "center", marginLeft: 6 }}>
            showing <span className="mono">{filtered.length}</span> / <span className="mono">{experiments.length}</span>
          </div>
        </div>
      </Card>

      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Experiment ID</th>
              <th>Start time (UTC)</th>
              <th>Device</th>
              <th>Sensor types</th>
              <th>Integrity</th>
              <th>ML flag</th>
              <th>Freshness</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((e) => {
              const freshness_minutes = computeFreshnessMinutes(e.start_timestamp_utc);

              return (
                <tr
                  key={e.experiment_id}
                  onClick={() => router.push(`/experiments/${encodeURIComponent(e.experiment_id)}`)}
                  title="Click to open details"
                >
                  <td className="mono">{e.experiment_id}</td>
                  <td>
                    <div className="mono">{formatUtc(e.start_timestamp_utc)}</div>
                    {e.end_timestamp_utc ? (
                      <div className="small">ended: <span className="mono">{formatUtc(e.end_timestamp_utc)}</span></div>
                    ) : (
                      <div className="small">ongoing</div>
                    )}
                  </td>
                  <td>
                    <div className="mono">{e.device_id}</div>
                    <div className="small">{e.device_alias}</div>
                  </td>
                  <td className="mono">{e.sensor_types.join(", ")}</td>
                  <td><StatusPill kind="integrity" value={e.integrity_status} /></td>
                  <td><StatusPill kind="ml" value={e.ml_flag} /></td>
                  <td>
                    <div className="mono">{freshness_minutes}</div>
                    <div className="small">minutes ago</div>
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: 18, color: "#94a3b8" }}>
                  No experiments match the selected filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

    </div>
  );
}

import type { Measurement } from "./types";

export function unique<T>(items: T[]): T[] {
  return Array.from(new Set(items));
}

export function formatUtc(iso: string): string {
  // Keep formatting stable and explicit (UTC shown).
  // Example: 2026-02-01T20:15:00Z
  try {
    const d = new Date(iso);
    return d.toISOString().replace(".000Z", "Z");
  } catch {
    return iso;
  }
}

export function computeFreshnessMinutes(start_timestamp_utc: string): number {
  const now = Date.now();
  const start = new Date(start_timestamp_utc).getTime();
  const diffMs = Math.max(0, now - start);
  return Math.floor(diffMs / (60 * 1000));
}

export function computeDurationSeconds(start_timestamp_utc: string, end_timestamp_utc: string | null): number {
  const start = new Date(start_timestamp_utc).getTime();
  const end = end_timestamp_utc ? new Date(end_timestamp_utc).getTime() : Date.now();
  return Math.max(0, Math.floor((end - start) / 1000));
}

export function computeStats(values: number[]): { value_min: string; value_max: string; value_mean: string } {
  if (values.length === 0) {
    return { value_min: "—", value_max: "—", value_mean: "—" };
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const mean = values.reduce((a, b) => a + b, 0) / values.length;

  return {
    value_min: min.toFixed(4),
    value_max: max.toFixed(4),
    value_mean: mean.toFixed(4)
  };
}

export function safe(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return String(v);
  if (typeof v === "string" && v.trim() === "") return "—";
  return String(v);
}

export function sensorTypesFromMeasurements(measurements: Measurement[]): string[] {
  return unique(measurements.map(m => m.sensor_type)).sort();
}

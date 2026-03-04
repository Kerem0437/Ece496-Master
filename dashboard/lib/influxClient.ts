import { InfluxDB } from "@influxdata/influxdb-client";

function requireEnv(name: string, fallback?: string): string {
  const v = process.env[name] ?? fallback;
  if (!v) {
    throw new Error(
      `Missing env var ${name}. Add it to dashboard/.env (see dashboard/.env.example).`
    );
  }
  return v;
}

export const INFLUX_URL = requireEnv("INFLUX_URL", "http://127.0.0.1:8086");
export const INFLUX_ORG = requireEnv("INFLUX_ORG", "ECE496");
export const INFLUX_BUCKET = requireEnv("INFLUX_BUCKET", "capstone");

// IMPORTANT: keep token server-side (DO NOT prefix with NEXT_PUBLIC_)
export const INFLUX_QUERY_TOKEN = requireEnv("INFLUX_QUERY_TOKEN");

export const INFLUX_MEASUREMENT = process.env.INFLUX_MEASUREMENT ?? "mqtt_sensor";
export const ML_MEASUREMENT = process.env.ML_MEASUREMENT ?? "ml_summary";

export function getQueryApi() {
  const db = new InfluxDB({ url: INFLUX_URL, token: INFLUX_QUERY_TOKEN });
  return db.getQueryApi(INFLUX_ORG);
}

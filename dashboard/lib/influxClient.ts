import { InfluxDB } from "@influxdata/influxdb-client";

function requireEnv(name: string, fallback?: string): string {
  const v = process.env[name] ?? fallback;
  if (!v) {
    // Called only when DATA_MODE=influx.
    // For public deployments (Vercel) where VM1 is not reachable, set DATA_MODE=mock.
    throw new Error(
      `Missing env var ${name}. If deploying without DB access, set DATA_MODE=mock. Otherwise add it to dashboard/.env (see dashboard/.env.example).`
    );
  }
  return v;
}

export function getInfluxUrl(): string {
  return requireEnv("INFLUX_URL", "http://127.0.0.1:8086");
}

export function getInfluxOrg(): string {
  return requireEnv("INFLUX_ORG", "ECE496");
}

export function getInfluxBucket(): string {
  return requireEnv("INFLUX_BUCKET", "capstone");
}

export function getInfluxQueryToken(): string {
  // IMPORTANT: server-side only; do not prefix with NEXT_PUBLIC_
  return requireEnv("INFLUX_QUERY_TOKEN");
}

export function getInfluxMeasurement(): string {
  return process.env.INFLUX_MEASUREMENT ?? "mqtt_sensor";
}

export function getMlMeasurement(): string {
  return process.env.ML_MEASUREMENT ?? "ml_summary";
}

export function getQueryApi() {
  const db = new InfluxDB({ url: getInfluxUrl(), token: getInfluxQueryToken() });
  return db.getQueryApi(getInfluxOrg());
}

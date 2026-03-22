import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { logInfo, logWarn, logError } from "@/lib/logger";

async function persistLiveSnapshot(experiment_id: string, kind: "measurements" | "ml", payload: any) {
  const baseDir = path.join(process.cwd(), "live_captures", experiment_id);
  await mkdir(baseDir, { recursive: true });
  const now = new Date();
  const bucket = new Date(Math.floor(now.getTime() / 120000) * 120000);
  const stamp = bucket.toISOString().replace(/[:.]/g, "-");
  await writeFile(path.join(baseDir, `${kind}_${stamp}.json`), JSON.stringify(payload, null, 2));
  await writeFile(path.join(baseDir, `${kind}_latest.json`), JSON.stringify(payload, null, 2));
}

export async function GET(req: Request) {
  const t0 = Date.now();
  const pathname = new URL(req.url).pathname;

  try {
    logInfo("api", `GET ${pathname}`);

    const url = new URL(req.url);
    const experiment_id = url.searchParams.get("experiment_id");
    const minutes = Number(url.searchParams.get("minutes") ?? "2");

    if (!experiment_id) {
      logWarn("api", "missing experiment_id");
      return NextResponse.json({ error: "missing experiment_id" }, { status: 400 });
    }

    const { getRecentWindowMeasurementsFromInflux } = await import("@/lib/data/influxData");
    const measurements = await getRecentWindowMeasurementsFromInflux(experiment_id, minutes);

    const { scoreMeasurements } = await import("@/lib/data/mlClient");
    const ml = await scoreMeasurements(experiment_id, measurements);
    const payload = { experiment_id, minutes, scored_at_utc: new Date().toISOString(), ml };
    await persistLiveSnapshot(experiment_id, "ml", payload);

    const dt = Date.now() - t0;
    logInfo("api", `OK ${pathname} in ${dt}ms`);
    return NextResponse.json(payload, { status: 200 });
  } catch (e: any) {
    const dt = Date.now() - t0;
    logError("api", `ERROR ${pathname} in ${dt}ms`, String(e));
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

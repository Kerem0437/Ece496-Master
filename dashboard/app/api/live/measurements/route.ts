import { NextResponse } from "next/server";
import { logInfo, logError } from "@/lib/logger";

export async function GET(req: Request) {
  const t0 = Date.now();
  try {
    logInfo('api', `GET ${new URL(req.url).pathname}`);

  const url = new URL(req.url);
  const experiment_id = url.searchParams.get("experiment_id");
  const minutes = Number(url.searchParams.get("minutes") ?? "2");

  if (!experiment_id) {
      const dt = Date.now() - t0;

      logInfo(\'api\', `OK in ${dt}ms`);

      return NextResponse.json({ error: "missing experiment_id" }, { status: 400 });
  }

  const { getRecentWindowMeasurementsFromInflux } = await import("@/lib/data/influxData");
  const measurements = await getRecentWindowMeasurementsFromInflux(experiment_id, minutes);
    return NextResponse.json({ experiment_id, minutes, measurements }, { status: 200 });

  } catch (e: any) {
    const dt = Date.now() - t0;
    logError('api', `ERROR in ${dt}ms`, String(e));
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

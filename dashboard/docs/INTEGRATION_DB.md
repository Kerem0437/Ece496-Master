
# INTEGRATION: Database (Influx) — T6/T7/T8

## Purpose
Formalize how the dashboard will read experiments + measurements from real storage later (InfluxDB on VM2), while remaining mock-driven today.

## Data Flow (future)
Pi → MQTT Broker → Subscriber/Ingest Service → InfluxDB (VM2) → (optional ML writes back) → Dashboard

## Why API-based access (not direct Influx from browser)
- VM2 often sits behind VPN / restricted network paths.
- You never want to expose Influx credentials/tokens in a public browser bundle.
- An API/proxy layer allows:
  - authentication
  - query shaping
  - caching
  - audit logging
  - hiding internal DB topology

## What is mock vs real
**Mock (NOW):**
- `MockDataProvider` wraps `lib/data/mockData.ts`.

**Real (LATER):**
- `InfluxApiProvider` would call a Next.js API route (or external gateway) that is allowed to query Influx securely.

## “Turn it on” later
1) Implement API routes (example: `app/api/influx/experiments/route.ts`) that proxy queries to VM2.
2) Replace placeholder methods in `InfluxApiProvider` to call those routes.
3) Set `DATA_PROVIDER_MODE=influx`.

## Code location
- Interface + providers: `lib/data/dataProvider.ts`
- Current consumers:
  - `/app/experiments/page.tsx`
  - `/app/experiments/[experiment_id]/page.tsx`

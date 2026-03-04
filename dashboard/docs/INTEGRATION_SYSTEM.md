# INTEGRATION: System Status / Health — T14

## Purpose
Provide a “system status” page to demonstrate infra awareness:
- DB status
- MQTT broker status
- ML service status

## Current behavior
All checks are mocked and returned as structured objects.

## Future behavior
- Implement real health endpoints:
  - `GET /health/db`
  - `GET /health/mqtt`
  - `GET /health/ml`
- The dashboard calls these endpoints and displays results.

## “Turn it on” later
1) Implement health endpoints on VM(s) or API gateway.
2) Implement Next.js API routes if direct access requires VPN/proxy.
3) Replace mocked logic in `lib/system/healthChecks.ts`.

## Code location
- Health module: `lib/system/healthChecks.ts`
- Page: `app/system/page.tsx`

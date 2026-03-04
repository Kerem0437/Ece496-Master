# INTEGRATION: Live / Recent Data — T12

## Purpose
Provide a demo-friendly live view that will later represent real-time ingestion.

## Current (mock) behavior
`/live` simulates new measurements arriving using a client-side timer.
No networking, no MQTT.

## Future (real) behavior options
### Option A: MQTT in backend, WebSocket to browser
- Server subscribes to MQTT topics
- Browser connects via WebSocket to receive new points

### Option B: Server-Sent Events (SSE)
- Server streams updates
- Browser receives push events over HTTP

### Option C: Polling
- Browser polls API endpoint every N seconds
- Simplest but least real-time

## “Turn it on” later
1) Add a Next.js API route that either:
   - proxies from MQTT subscriber, or
   - reads newest points from DB
2) Replace mock stream with subscription to that endpoint.

## Code location
- Mock stream: `lib/live/mockStream.ts`
- Live page: `app/live/page.tsx`

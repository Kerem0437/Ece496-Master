# INTEGRATION: Devices / Multi-device support — T13

## Purpose
Represent multiple edge gateways (Pis/spectrometers) cleanly across the UI:
- consistent device naming
- site/location metadata
- future filtering and monitoring

## Current behavior
Mock experiments already contain:
- `device_id`
- `device_alias`
- `site_location`

We additionally introduce a DeviceRegistry as the authoritative mapping layer.

## Future behavior
- DeviceRegistry could be sourced from:
  - a config file
  - a DB table
  - an admin UI
- It can also link to device cert metadata for integrity verification.

## “Turn it on” later
1) Move device registry data into a persistent store.
2) Provide an API route to read it.
3) Keep UI unchanged — only the registry’s data source changes.

## Code location
- Registry: `lib/devices/deviceRegistry.ts`

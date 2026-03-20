# Troubleshooting / Debugging (ECE496)

## 1) Run the verifier first
Windows:
```powershell
.\scripts\verify_repo.ps1
.\scripts\verify_repo.ps1 -Full
```

macOS/Linux:
```bash
./scripts/verify_repo.sh
./scripts/verify_repo.sh --full
```

## 2) Enable verbose logs
Python components (ml_service/train.py, ml_service/server.py):
```bash
# Windows PowerShell
set LOG_LEVEL=DEBUG
# macOS/Linux
export LOG_LEVEL=DEBUG
```

Dashboard:
- The Next.js API routes (`/api/live/*`) log every call + duration in the terminal where you run `npm run dev`.

## 3) Common failures

### A) Dashboard shows “Missing INFLUX_QUERY_TOKEN”
Fix: set the env var in `dashboard/.env` (LIVE mode only).  
DEMO mode does not need it.

### B) Dashboard shows 0 experiments in DEMO mode
Check:
- `dashboard/.env` has `DATA_MODE=demojson`
- `dashboard/demo-json/experiments.json` exists

### C) LIVE mode: no data appears
Check:
- ECE VPN connected
- Influx tunnel up: `ssh -N -L 8086:127.0.0.1:8086 -p 3246 cenit@128.100.23.125`
- Influx running on VM2: `sudo systemctl status influxdb`

### D) MQTT path broken
Check:
- mosquitto running on VM1
- Pi publisher points to correct broker IP/port
- broker port reachable from laptop: `nc -vz <broker_ip> 1883`

### E) ML flags always suspicious
- Confirm model was trained on mixed data (`demo/data` has multiple water types)
- Re-train:
  `python ml_service/train.py --data-dir demo/data`
- Use `LOG_LEVEL=DEBUG` and inspect raw MSE / per-feature scores.

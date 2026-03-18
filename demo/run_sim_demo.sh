\
#!/usr/bin/env bash
set -euo pipefail
echo "[DEMO] Starting demo realtime pipeline demo (no network)..."
python3 ./demo_realtime_demo.py --duration 30 --interval 2.0
echo "[DEMO] Done. Refresh dashboard to show final state."

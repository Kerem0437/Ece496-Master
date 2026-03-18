\
# Run SIMULATED realtime demo (Terminal 2)
# From repo root: cd demo; .\run_sim_demo.ps1

Write-Host "[DEMO] Starting demo realtime pipeline demo (no network)..." -ForegroundColor Cyan
py .\demo_realtime_demo.py --duration 30 --interval 2.0
Write-Host "[DEMO] Done. Refresh dashboard to show final state." -ForegroundColor Cyan

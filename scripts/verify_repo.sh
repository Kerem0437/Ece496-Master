\
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"

EXTRA=()
if [[ "${1:-}" == "--full" ]]; then
  EXTRA+=("--full")
fi
if [[ "${1:-}" == "--run-build" || "${2:-}" == "--run-build" ]]; then
  EXTRA+=("--run-build")
fi

echo "ECE496 verify starting..."
echo "Repo root: $ROOT"
"$PY" "$ROOT/scripts/verify_repo.py" "${EXTRA[@]}"

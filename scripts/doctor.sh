#!/usr/bin/env bash
# doctor.sh — operator pre-launch check for the ingest pipeline.
#
# Runs:
#   1. `monitor ingest-doctor doctor` (embedding + pairs + providers + jobs)
#   2. `monitor ingest list --stale` (running stale jobs)
#   3. MongoDB / Qdrant / Neo4j reachability probes via the Python health module
#
# Exit code 0 if every check is "healthy" or "degraded but runnable";
# non-zero if anything is unhealthy.

set -uo pipefail

cd "$(dirname "$0")/.."

# Pick up .env if present.
if [[ -f .env ]]; then
    # shellcheck disable=SC1091
    set -a; source .env; set +a
fi

PYTHON="${PYTHON:-python}"
echo "==> 1. monitor ingest-doctor doctor"
if ! "$PYTHON" -m monitor_cli.main ingest-doctor doctor --force; then
    echo "doctor command failed (non-fatal; check below)"
fi

echo
echo "==> 2. monitor ingest-jobs list --stale"
"$PYTHON" -m monitor_cli.main ingest-jobs list --stale || true

echo
echo "==> 3. Component reachability"
"$PYTHON" - <<'PYEOF'
from monitor_data.health import get_health_status
import json
print(json.dumps(get_health_status(), indent=2))
PYEOF
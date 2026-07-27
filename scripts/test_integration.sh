#!/usr/bin/env bash
# =============================================================================
# MONITOR — Integration test runner
#
# Starts docker services (Neo4j, MongoDB, Qdrant, MinIO, PostgreSQL, Redis),
# waits for health checks, runs integration tests, then tears down.
#
# Usage:
#   ./scripts/test_integration.sh              # run all integration tests
#   ./scripts/test_integration.sh -k filter     # pass extra pytest args
#   ./scripts/test_integration.sh --keep-up     # don't tear down after
#
# Environment variables:
#   RUN_INTEGRATION=1   set automatically (required by pytest markers)
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✔${NC}  $*"; }
info() { echo -e "${CYAN}→${NC}  $*"; }
warn() { echo -e "${YELLOW}!${NC}  $*"; }
err()  { echo -e "${RED}✘${NC}  $*" >&2; }

# Parse args
KEEP_UP=false
PYTEST_ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--keep-up" ]]; then
        KEEP_UP=true
    else
        PYTEST_ARGS+=("$arg")
    fi
done

# ── Pre-flight checks ────────────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
    err "docker is not installed or not on PATH"
    exit 1
fi

if ! docker info &>/dev/null 2>&1; then
    err "docker daemon is not running"
    exit 1
fi

# Load .env for docker compose
if [[ -f "$REPO_ROOT/.env" ]]; then
    set -o allexport
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +o allexport
else
    warn ".env not found — using defaults from docker-compose.yml"
fi

INFRA_FILE="$REPO_ROOT/infra/docker-compose.yml"
SERVICES=(neo4j mongodb qdrant minio postgres redis)

# ── Cleanup trap ─────────────────────────────────────────────────────────────

cleanup() {
    if [[ "$KEEP_UP" == "true" ]]; then
        warn "Keeping services running (--keep-up)"
        return
    fi
    info "Tearing down docker services..."
    docker compose --env-file "$REPO_ROOT/.env" -f "$INFRA_FILE" stop "${SERVICES[@]}" 2>/dev/null || true
    ok "Services stopped"
}
trap cleanup EXIT

# ── Start services ───────────────────────────────────────────────────────────

info "Starting docker services: ${SERVICES[*]}"
docker compose --env-file "$REPO_ROOT/.env" -f "$INFRA_FILE" up -d "${SERVICES[@]}" 2>&1 | grep -E "Started|Running|Created|Recreated" || true
ok "Services started"

# ── Wait for health checks ───────────────────────────────────────────────────

wait_for_port() {
    local port="$1" label="$2" timeout="${3:-30}"
    local elapsed=0
    printf "   Waiting for %s on :%s " "$label" "$port"
    until nc -z 127.0.0.1 "$port" 2>/dev/null; do
        printf "."
        sleep 1
        elapsed=$((elapsed + 1))
        if [[ $elapsed -ge $timeout ]]; then
            echo
            err "$label did not become ready on :$port after ${timeout}s"
            return 1
        fi
    done
    echo " ready"
}

wait_for_port 7687  "Neo4j Bolt"   45
wait_for_port 27017 "MongoDB"      30
wait_for_port 6333  "Qdrant"       30
wait_for_port 9000  "MinIO"        20
wait_for_port 5432  "PostgreSQL"   30
wait_for_port 6379  "Redis"        15

ok "All services healthy"

# ── Run integration tests ────────────────────────────────────────────────────

info "Running integration tests..."
export RUN_INTEGRATION=1

if [[ ${#PYTEST_ARGS[@]} -gt 0 ]]; then
    uv run pytest packages tests -m integration -q --tb=short "${PYTEST_ARGS[@]}"
else
    uv run pytest packages tests -m integration -q --tb=short
fi

ok "Integration tests passed"
#!/usr/bin/env bash
# =============================================================================
# MONITOR — compose helpers
#
# Shared shell utilities for docker-compose orchestration. Sourced by both
# `dev.sh` and the `make infra-*` targets so there is a single source of truth
# for "start services", "wait for ports", and "check HTTP health".
#
# Functions exported:
#   wait_for_port  PORT LABEL [TIMEOUT_SECONDS]
#   http_ready     URL
#   wait_for_http  URL LABEL [TIMEOUT_SECONDS]
#   compose_up     COMPOSE_CMD SERVICE [SERVICE ...]
#   compose_stop   COMPOSE_CMD SERVICE [SERVICE ...]
#   compose_ps     COMPOSE_CMD SERVICE [SERVICE ...]
#   wait_ports     PORT[:LABEL] [PORT[:LABEL] ...]   # label is optional
#
# All functions use port 127.0.0.1 for checks (Docker maps host ports there).
# Colors are only emitted if stdout is a TTY — safe to call from non-interactive
# scripts (CI, Makefile).
# =============================================================================

if [[ -n "${COMPOSE_HELPERS_LOADED:-}" ]]; then
    return 0
fi
COMPOSE_HELPERS_LOADED=1

if [[ -t 1 ]]; then
    _RED='\033[0;31m'; _GREEN='\033[0;32m'; _YELLOW='\033[1;33m'; _CYAN='\033[0;36m'; _NC='\033[0m'
else
    _RED=''; _GREEN=''; _YELLOW=''; _CYAN=''; _NC=''
fi
ok()   { echo -e "${_GREEN}✔${_NC}  $*"; }
info() { echo -e "${_CYAN}→${_NC}  $*"; }
warn() { echo -e "${_YELLOW}!${_NC}  $*"; }
err()  { echo -e "${_RED}✘${_NC}  $*"; }

# wait_for_port PORT LABEL [TIMEOUT_SECONDS]
wait_for_port() {
    local port="$1"; local label="$2"; local timeout="${3:-30}"
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

# http_ready URL  → returns 0 if URL returns 2xx
http_ready() {
    local url="$1"
    curl -fsS --max-time 2 "$url" >/dev/null 2>&1
}

# wait_for_http URL LABEL [TIMEOUT_SECONDS]
wait_for_http() {
    local url="$1"; local label="$2"; local timeout="${3:-30}"
    local elapsed=0
    printf "   Waiting for %s at %s " "$label" "$url"
    until http_ready "$url"; do
        printf "."
        sleep 1
        elapsed=$((elapsed + 1))
        if [[ $elapsed -ge $timeout ]]; then
            echo
            err "$label did not become healthy at $url after ${timeout}s"
            return 1
        fi
    done
    echo " ready"
}

# compose_up COMPOSE_CMD SERVICE [SERVICE ...]
# Runs `docker compose up -d` on the listed services and pipes output through
# a status-line filter so the dev log stays readable.
compose_up() {
    local compose_cmd="$1"; shift
    info "Starting infra services: $*"
    # shellcheck disable=SC2086
    $compose_cmd up -d "$@" 2>&1 | grep -E "Started|Running|Created|Recreated" || true
    ok "docker compose up -d complete"
}

# compose_stop COMPOSE_CMD SERVICE [SERVICE ...]
compose_stop() {
    local compose_cmd="$1"; shift
    info "Stopping infra services: $*"
    # shellcheck disable=SC2086
    $compose_cmd stop "$@" >/dev/null 2>&1 || true
    ok "docker compose stop complete"
}

# compose_ps COMPOSE_CMD SERVICE [SERVICE ...]
compose_ps() {
    local compose_cmd="$1"; shift
    $compose_cmd ps "$@"
}

# wait_ports PORT[:LABEL] [PORT[:LABEL] ...]
# Wait for multiple ports in sequence. LABEL is optional (defaults to PORT).
# Example: wait_ports 7687:Neo4j 27017:MongoDB 5432:Postgres
wait_ports() {
    local entry port label
    for entry in "$@"; do
        port="${entry%%:*}"
        if [[ "$entry" == *:* ]]; then
            label="${entry#*:}"
        else
            label="$entry"
        fi
        wait_for_port "$port" "$label"
    done
}

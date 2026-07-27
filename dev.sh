#!/usr/bin/env bash
# =============================================================================
# MONITOR — dev runner
#
# Usage:
#   ./dev.sh                  start everything (reuse running services where possible)
#   ./dev.sh restart          kill everything first, then start fresh
#   ./dev.sh stop             stop the main stack
#   ./dev.sh shutdown|down    gracefully stop the full local runtime, including approved aux services
#   ./dev.sh status           show what's running
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$ROOT/infra"
BACKEND_DIR="$ROOT/packages/ui/backend"
FRONTEND_DIR="$ROOT/packages/ui/frontend"
VENV="$ROOT/.venv"
PIDS_DIR="$ROOT/.run"
BACKEND_PID="$PIDS_DIR/backend.pid"
FRONTEND_PID="$PIDS_DIR/frontend.pid"
BACKEND_LOG="$PIDS_DIR/backend.log"
FRONTEND_LOG="$PIDS_DIR/frontend.log"
FRONTEND_TMUX_SESSION="${FRONTEND_TMUX_SESSION:-monitor-frontend}"

# Shared shell helpers (colors, wait_for_port, wait_for_http, compose_up/stop/ps).
# Used by `make infra-*` targets as well.
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/compose_helpers.sh"

# Resolve npm — nvm installs node outside the default PATH for non-interactive shells
if [[ -z "$(command -v npm 2>/dev/null)" ]]; then
    NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    # shellcheck disable=SC1091
    [[ -s "$NVM_DIR/nvm.sh" ]] && source "$NVM_DIR/nvm.sh" 2>/dev/null || true
fi
NPM="$(command -v npm 2>/dev/null || true)"
[[ -z "$NPM" ]] && { err "npm not found — run 'nvm install' or install Node.js"; exit 1; }

# Services that need a restart when code changes require it
NEEDS_RESTART="${1:-}"

# ── helpers ───────────────────────────────────────────────────────────────────

is_running() {
    local pid_file="$1"
    [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

tmux_session_running() {
    local session="$1"
    command -v tmux >/dev/null 2>&1 && tmux has-session -t "$session" 2>/dev/null
}

frontend_process_running() {
    tmux_session_running "$FRONTEND_TMUX_SESSION" || is_running "$FRONTEND_PID"
}

frontend_pid_label() {
    if [[ -f "$FRONTEND_PID" ]]; then
        cat "$FRONTEND_PID"
    elif tmux_session_running "$FRONTEND_TMUX_SESSION"; then
        echo "tmux:$FRONTEND_TMUX_SESSION"
    else
        echo "unknown"
    fi
}

kill_pid_file() {
    local pid_file="$1"
    local label="$2"
    if [[ -f "$pid_file" ]]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            # Wait up to 5 s for clean exit
            for _ in {1..10}; do
                kill -0 "$pid" 2>/dev/null || break
                sleep 0.5
            done
            kill -9 "$pid" 2>/dev/null || true
            ok "Stopped $label (pid $pid)"
        fi
        rm -f "$pid_file"
    fi
}

stop_frontend_process() {
    if tmux_session_running "$FRONTEND_TMUX_SESSION"; then
        tmux kill-session -t "$FRONTEND_TMUX_SESSION" 2>/dev/null || true
        rm -f "$FRONTEND_PID"
        ok "Stopped Next.js frontend (tmux: $FRONTEND_TMUX_SESSION)"
        return
    fi

    kill_pid_file "$FRONTEND_PID" "Next.js frontend"
}

# wait_for_port / http_ready / wait_for_http come from
# scripts/lib/compose_helpers.sh (sourced at the top of this file).

start_backend_process() {
    local backend_port="$1"
    info "Starting FastAPI backend on :$backend_port..."
    cd "$BACKEND_DIR"
    nohup env PYTHONPATH="$ROOT/packages/data-layer/src:$ROOT/packages/agents/src:$BACKEND_DIR/src" \
        "$VENV/bin/uvicorn" monitor_ui.main:app \
        --app-dir "$BACKEND_DIR/src" \
        --host 0.0.0.0 --port "$backend_port" --reload \
        --reload-dir "$ROOT/packages/agents/src" \
        --reload-dir "$ROOT/packages/data-layer/src" \
        --reload-dir "$BACKEND_DIR/src" \
        --log-level info \
        </dev/null \
        >> "$BACKEND_LOG" 2>&1 &
    echo $! > "$BACKEND_PID"
    cd "$ROOT"
    wait_for_http "http://127.0.0.1:${backend_port}/api/health" "FastAPI backend" 20
    ok "FastAPI backend started (pid $(cat "$BACKEND_PID"))"
}

frontend_ready() {
    local frontend_port="$1"
    curl -fsS --max-time 5 "http://127.0.0.1:${frontend_port}/settings" >/dev/null 2>&1
}

wait_for_frontend() {
    local frontend_port="$1"; local timeout="${2:-60}"
    local elapsed=0
    printf "   Waiting for Next.js frontend at http://127.0.0.1:%s/settings " "$frontend_port"
    until frontend_ready "$frontend_port"; do
        if ! frontend_process_running; then
            echo
            err "Next.js frontend exited before /settings became healthy"
            return 1
        fi
        printf "."
        sleep 1
        elapsed=$((elapsed + 1))
        if [[ $elapsed -ge $timeout ]]; then
            echo
            err "Next.js frontend did not become healthy after ${timeout}s"
            return 1
        fi
    done
    echo " ready"
}

clear_next_cache() {
    if [[ -d "$FRONTEND_DIR/.next" ]]; then
        info "Clearing generated Next.js cache..."
        rm -rf "$FRONTEND_DIR/.next"
    fi
}

start_frontend_process() {
    local frontend_port="$1"
    local backend_port="$2"
    local api_url="${NEXT_PUBLIC_API_URL:-http://localhost:${backend_port}}"
    local backend_url="${BACKEND_URL:-http://localhost:${backend_port}}"
    info "Starting Next.js frontend on :$frontend_port..."
    clear_next_cache

    if command -v tmux >/dev/null 2>&1; then
        local cmd
        printf -v cmd 'exec env NEXT_PUBLIC_API_URL=%q BACKEND_URL=%q PORT=%q %q run dev >> %q 2>&1' \
            "$api_url" "$backend_url" "$frontend_port" "$NPM" "$FRONTEND_LOG"
        tmux new-session -d -s "$FRONTEND_TMUX_SESSION" -c "$FRONTEND_DIR" "$cmd"
        tmux display-message -p -t "$FRONTEND_TMUX_SESSION" "#{pane_pid}" > "$FRONTEND_PID" 2>/dev/null || true
    else
        cd "$FRONTEND_DIR"
        env NEXT_PUBLIC_API_URL="$api_url" \
            BACKEND_URL="$backend_url" \
            PORT="$frontend_port" "$NPM" run dev >> "$FRONTEND_LOG" 2>&1 &
        echo $! > "$FRONTEND_PID"
        cd "$ROOT"
    fi

    wait_for_frontend "$frontend_port" 60
    ok "Next.js frontend started (pid $(frontend_pid_label))"
}

# ── status ────────────────────────────────────────────────────────────────────

cmd_status() {
    if [[ -f "$ROOT/.env" ]]; then
        set -o allexport
        # shellcheck disable=SC1091
        source "$ROOT/.env"
        set +o allexport
    fi
    # Also load token overrides (.env.tokens kept out of .env for security)
    if [[ -f "$ROOT/.env.tokens" ]]; then
        set -o allexport
        # shellcheck disable=SC1091
        source "$ROOT/.env.tokens"
        set +o allexport
    fi

    echo
    echo "  Docker services:"
    local services=(monitor-neo4j monitor-mongodb monitor-qdrant monitor-minio monitor-postgres)
    for svc in "${services[@]}"; do
        if docker ps --filter "name=$svc" --filter "status=running" --format "{{.Names}}" 2>/dev/null | grep -q "$svc"; then
            ok "  $svc"
        else
            warn "  $svc (not running)"
        fi
    done

    echo
    echo "  Python processes:"
    local backend_port="${UI_PORT:-8000}"
    if is_running "$BACKEND_PID"; then
        if http_ready "http://127.0.0.1:${backend_port}/api/health"; then
            ok "  backend   (pid $(cat "$BACKEND_PID"), log: .run/backend.log)"
        else
            warn "  backend   (pid $(cat "$BACKEND_PID"), not answering /api/health)"
        fi
    elif http_ready "http://127.0.0.1:${backend_port}/api/health"; then
        ok "  backend   (external on :$backend_port, pid file missing/stale)"
    else
        warn "  backend   (not running)"
    fi

    echo
    echo "  Frontend:"
    local frontend_port="${FRONTEND_PORT:-3000}"
    if frontend_process_running; then
        if frontend_ready "$frontend_port"; then
            ok "  frontend  (pid $(frontend_pid_label), log: .run/frontend.log)"
        else
            warn "  frontend  (pid $(frontend_pid_label), /settings is not healthy)"
        fi
    elif frontend_ready "$frontend_port"; then
        ok "  frontend  (external on :$frontend_port, pid file missing/stale)"
    else
        warn "  frontend  (not running)"
    fi
    echo
}

# ── stop ──────────────────────────────────────────────────────────────────────

cmd_stop() {
    info "Stopping processes..."

    if command -v tmux >/dev/null 2>&1 && tmux has-session -t monitor 2>/dev/null; then
        tmux kill-session -t monitor 2>/dev/null || true
        ok "Stopped tmux session 'monitor'"
    fi

    stop_frontend_process
    kill_pid_file "$BACKEND_PID"  "FastAPI backend"



    info "Stopping docker services..."
    docker compose --env-file "$ROOT/.env" -f "$INFRA_DIR/docker-compose.yml" stop 2>/dev/null || true
    ok "All services stopped"
}

# ── start ─────────────────────────────────────────────────────────────────────

cmd_start() {
    mkdir -p "$PIDS_DIR"

    # ── Load env ──────────────────────────────────────────────────────────────
    if [[ -f "$ROOT/.env" ]]; then
        # Export only — do not let unset vars abort the script
        set -o allexport
        # shellcheck disable=SC1091
        source "$ROOT/.env"
        set +o allexport
    else
        warn ".env not found — copy env.example to .env and fill in your values"
        exit 1
    fi
    # Also load token overrides
    if [[ -f "$ROOT/.env.tokens" ]]; then
        set -o allexport
        # shellcheck disable=SC1091
        source "$ROOT/.env.tokens"
        set +o allexport
    fi

    # ── Docker infra ──────────────────────────────────────────────────────────
    info "Starting infrastructure (docker compose)..."

    # Detect which services are already healthy vs which need starting
    docker compose --env-file "$ROOT/.env" -f "$INFRA_DIR/docker-compose.yml" up -d \
        neo4j mongodb qdrant minio postgres opensearch 2>&1 | grep -E "Started|Running|Created|Recreated" || true

    ok "Infrastructure up"

    # Wait for the most critical ports before proceeding
    wait_for_port 7687  "Neo4j Bolt"  45
    wait_for_port 27017 "MongoDB"     30
    wait_for_port 5432  "PostgreSQL"  30

    # ── FastAPI backend ───────────────────────────────────────────────────────
    local backend_port="${UI_PORT:-8000}"
    local backend_health_url="http://127.0.0.1:${backend_port}/api/health"
    if is_running "$BACKEND_PID"; then
        if http_ready "$backend_health_url"; then
            ok "FastAPI backend already running (pid $(cat "$BACKEND_PID")) — skipping"
        else
            warn "FastAPI backend pid $(cat "$BACKEND_PID") is not answering /api/health — restarting"
            kill_pid_file "$BACKEND_PID" "FastAPI backend"
            start_backend_process "$backend_port"
        fi
    elif nc -z 127.0.0.1 "$backend_port" 2>/dev/null; then
        warn "Port :$backend_port is already in use but .run/backend.pid is stale/missing — validating backend health"
        wait_for_http "$backend_health_url" "FastAPI backend" 5
        ok "FastAPI backend already reachable on :$backend_port — skipping"
    else
        start_backend_process "$backend_port"
    fi

    # ── Next.js frontend ──────────────────────────────────────────────────────
    local frontend_port="${FRONTEND_PORT:-3000}"
    if frontend_process_running; then
        if frontend_ready "$frontend_port"; then
            ok "Next.js frontend already running (pid $(frontend_pid_label)) — skipping"
        else
            warn "Next.js frontend pid $(frontend_pid_label) is not serving /settings — restarting"
            stop_frontend_process
            start_frontend_process "$frontend_port" "$backend_port"
        fi
    elif nc -z 127.0.0.1 "$frontend_port" 2>/dev/null; then
        if frontend_ready "$frontend_port"; then
            ok "Next.js frontend already reachable on :$frontend_port — skipping"
        else
            err "Port :$frontend_port is in use but /settings is not healthy"
            echo "   Stop the process using :$frontend_port or run ./dev.sh restart"
            exit 1
        fi
    else
        start_frontend_process "$frontend_port" "$backend_port"
    fi

    echo
    ok "MONITOR is running"
    echo "   Frontend  → http://localhost:${frontend_port}"
    echo "   Backend   → http://localhost:${backend_port}"
    echo "   API docs  → http://localhost:${backend_port}/docs"
    echo "   Neo4j     → http://localhost:7474"
    echo "   MinIO     → http://localhost:9001"
    echo "   PostgreSQL→ localhost:5432  (db: monitor)"
    echo "   Logs      → tail -f .run/backend.log  |  tail -f .run/frontend.log"
    echo
}

# ── dispatch ──────────────────────────────────────────────────────────────────

case "${NEEDS_RESTART}" in
    stop|shutdown|down)
        cmd_stop
        ;;
    restart)
        cmd_stop
        sleep 1
        cmd_start
        ;;
    status)
        cmd_status
        ;;
    ""|start)
        cmd_start
        ;;
    *)
        echo "Usage: $0 [start|stop|shutdown|down|restart|status]"
        exit 1
        ;;
esac

#!/usr/bin/env bash
# =============================================================================
# MONITOR — tmux dev launcher
#
# Usage:
#   ./tmux-dev.sh           attach to (or create) the monitor session
#   ./tmux-dev.sh kill      stop the session and all docker services
#
# Layout (single window, 4 panes):
#
#   ┌─────────────────────┬──────────────────────┐
#   │                     │                      │
#   │  0: infra (docker)  │  1: backend (uvicorn)│
#   │                     │                      │
#   ├─────────────────────┴──────────────────────┤
#   │                                            │
#   │         2: frontend (next.js)              │
#   │                                            │
#   └────────────────────────────────────────────┘
#
# =============================================================================
set -euo pipefail

SESSION="monitor"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$ROOT/infra"
BACKEND_DIR="$ROOT/packages/ui/backend"
FRONTEND_DIR="$ROOT/packages/ui/frontend"
VENV="$ROOT/.venv"

# ── colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✔${NC}  $*"; }
info() { echo -e "${CYAN}→${NC}  $*"; }
err()  { echo -e "${RED}✘${NC}  $*"; exit 1; }

# ── pre-flight ────────────────────────────────────────────────────────────────
command -v tmux  >/dev/null 2>&1 || err "tmux is not installed (sudo apt install tmux)"
command -v docker >/dev/null 2>&1 || err "docker is not installed"

[[ -f "$ROOT/.env" ]] || err ".env not found — copy env.example to .env and fill in your values"

# ── kill command ──────────────────────────────────────────────────────────────
if [[ "${1:-}" == "kill" ]]; then
    info "Stopping tmux session '$SESSION'..."
    tmux kill-session -t "$SESSION" 2>/dev/null && ok "Session killed" || true
    ok "Done (containers still running — use './tmux-dev.sh stopall' to also stop docker)"
    exit 0
fi

if [[ "${1:-}" == "stopall" ]]; then
    exec "$ROOT/dev.sh" shutdown
fi

# ── attach if already running ─────────────────────────────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
    if [[ -n "${TMUX:-}" ]]; then
        current=$(tmux display-message -p '#S' 2>/dev/null || echo "")
        if [[ "$current" == "$SESSION" ]]; then
            ok "Already inside session '$SESSION' — nothing to do"
            exit 0
        fi
        exec tmux switch-client -t "$SESSION"
    else
        exec tmux attach-session -t "$SESSION"
    fi
fi

# ── build the session ─────────────────────────────────────────────────────────
info "Creating tmux session '$SESSION'..."

# Env loader: set -o allexport exports every bare KEY=VALUE line to child processes
LOAD_ENV="set -o allexport; source '$ROOT/.env'; set +o allexport"

# ── containers: always start detached so they survive tmux death ──────────────
info "Starting docker containers (detached)..."
set -o allexport; source "$ROOT/.env"; set +o allexport
docker compose --env-file "$ROOT/.env" -f "$INFRA_DIR/docker-compose.yml" \
    up -d neo4j mongodb qdrant minio postgres opensearch
ok "Containers started"

# ── window 0: infra logs ──────────────────────────────────────────────────────
tmux new-session -d -s "$SESSION" -n "infra"
tmux send-keys -t "$SESSION:infra" \
    "docker compose --env-file '$ROOT/.env' -f '$INFRA_DIR/docker-compose.yml' logs -f neo4j mongodb qdrant minio postgres" \
    Enter

# ── window 1: backend (uvicorn) ───────────────────────────────────────────────
tmux new-window -t "$SESSION" -n "backend"
tmux send-keys -t "$SESSION:backend" \
    "$LOAD_ENV && source '$VENV/bin/activate' && \
    echo '→ Waiting for infra (neo4j, mongo, postgres)...' && \
    until nc -z 127.0.0.1 7687 && nc -z 127.0.0.1 27017 && nc -z 127.0.0.1 5432; do sleep 2; done && \
    echo '→ Starting FastAPI backend...' && \
    cd '$ROOT' && \
    PYTHONPATH='$ROOT/packages/data-layer/src:$ROOT/packages/agents/src:$BACKEND_DIR/src' \
    '$VENV/bin/uvicorn' monitor_ui.main:app \
        --app-dir '$BACKEND_DIR/src' \
        --host 0.0.0.0 --port 8001 --reload --log-level info" \
    Enter

# ── window 2: frontend (next.js) ──────────────────────────────────────────────
tmux new-window -t "$SESSION" -n "frontend"
tmux send-keys -t "$SESSION:frontend" \
    "$LOAD_ENV && \
    echo '→ Waiting for backend (:8001)...' && \
    until nc -z 127.0.0.1 8001; do sleep 2; done && \
    echo '→ Starting Next.js frontend...' && \
    cd '$FRONTEND_DIR' && npm run dev" \
    Enter

# ── window 3: shell (scratch) ─────────────────────────────────────────────────
tmux new-window -t "$SESSION" -n "shell"
tmux send-keys -t "$SESSION:shell" \
    "$LOAD_ENV && source '$VENV/bin/activate' && cd '$ROOT'" \
    Enter

# Status bar
tmux set-option -t "$SESSION" status-right \
    "#[fg=green]Neo4j :7474  Postgres :5432  Backend :8001  Frontend :3000#[default]"
tmux set-option -t "$SESSION" status-right-length 80
tmux set-option -t "$SESSION" status-style "bg=black,fg=white"

# Switch to backend window on attach
tmux select-window -t "$SESSION:backend"

ok "Session ready"
echo ""
echo "  Frontend  → http://localhost:3000"
echo "  Backend   → http://localhost:8001/docs"
echo "  Neo4j     → http://localhost:7474"
echo "  MinIO     → http://localhost:9001"
echo "  Postgres  → localhost:5432  (db: monitor)"
echo ""
echo "  Kill all  → ./tmux-dev.sh kill"
echo ""

if [[ -n "${TMUX:-}" ]]; then
    exec tmux switch-client -t "$SESSION"
else
    exec tmux attach-session -t "$SESSION"
fi

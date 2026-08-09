#!/bin/bash
# LAIN MCP Server Manager - Ensures singleton HTTP server for all agents
# Usage: ./lain-server-manager.sh [start|stop|status|restart]

set -e

LAIN_BIN="/home/sebastian/.local/lain/lain"
LAIN_MODEL="/home/sebastian/.local/lain/models/all-MiniLM-L6-v2.onnx"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDFILE="$PROJECT_ROOT/.lain/server.pid"
LOGFILE="$PROJECT_ROOT/.lain/server.log"
PORT="${LAIN_PORT:-9999}"

ensure_dirs() {
    mkdir -p "$PROJECT_ROOT/.lain"
}

is_running() {
    if [[ -f "$PIDFILE" ]]; then
        local pid=$(cat "$PIDFILE" 2>/dev/null || echo "")
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            # Verify it's actually LAIN on the expected port
            if curl -s "http://localhost:$PORT/mcp" -X POST \
                -H "Content-Type: application/json" \
                -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
                >/dev/null 2>&1; then
                return 0
            fi
        fi
    fi
    # Check if anything is listening on the port
    if command -v ss >/dev/null 2>&1 && ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
        return 0
    elif command -v netstat >/dev/null 2>&1 && netstat -tlnp 2>/dev/null | grep -q ":$PORT "; then
        return 0
    fi
    return 1
}

start_server() {
    ensure_dirs
    
    if is_running; then
        echo "LAIN server owner already running on port $PORT (PID: $(cat "$PIDFILE" 2>/dev/null || echo 'unknown'))"
        return 0
    fi
    
    echo "Starting LAIN MCP server on port $PORT..."
    
    # Remove stale PID file
    rm -f "$PIDFILE"
    
    local cmd=("$LAIN_BIN"
        --workspace "$PROJECT_ROOT"
        --transport http
        --port "$PORT"
        --embedding-model "$LAIN_MODEL"
    )
    
    # Start in background with nohup
    nohup "${cmd[@]}" > "$LOGFILE" 2>&1 &
    local pid=$!
    
    # Save PID
    echo $pid > "$PIDFILE"
    
    # Wait for server to be ready
    local attempts=0
    local max_attempts=30
    while [[ $attempts -lt $max_attempts ]]; do
        if curl -s "http://localhost:$PORT/mcp" -X POST \
            -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
            >/dev/null 2>&1; then
            echo "✓ LAIN server ready on http://localhost:$PORT"
            echo "  PID: $pid"
            echo "  Log: $LOGFILE"
            return 0
        fi
        sleep 0.5
        attempts=$((attempts+1))
    done
    
    echo "✗ Failed to start LAIN server (timeout)"
    echo "Check logs: $LOGFILE"
    rm -f "$PIDFILE"
    return 1
}

stop_server() {
    if ! is_running; then
        echo "LAIN server not running"
        rm -f "$PIDFILE"
        return 0
    fi
    
    local pid=$(cat "$PIDFILE" 2>/dev/null || echo "")
    if [[ -n "$pid" ]]; then
        echo "Stopping LAIN server (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        # Wait for process to actually stop
        local attempts=0
        while kill -0 "$pid" 2>/dev/null && [[ $attempts -lt 10 ]]; do
            sleep 0.5
            attempts=$((attempts+1))
        done
        # Force kill if still running
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
    fi
    
    rm -f "$PIDFILE"
    echo "✓ LAIN server stopped"
}

status() {
    if is_running; then
        local pid=$(cat "$PIDFILE" 2>/dev/null || echo "unknown")
        echo "✓ LAIN server running on port $PORT (PID: $pid)"
        
        # Show health check
        echo ""
        echo "Health check:"
        curl -s -X POST "http://localhost:$PORT/mcp" \
            -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_health","arguments":{}},"id":1}' \
            2>/dev/null | head -20 || echo "  (health check failed)"
    else
        echo "✗ LAIN server not running"
        return 1
    fi
}

# Main command handler
case "${1:-start}" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        stop_server
        sleep 1
        start_server
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 [start|stop|restart|status]"
        echo ""
        echo "Environment variables:"
        echo "  LAIN_PORT - HTTP port (default: 9999)"
        exit 1
        ;;
esac

# LAIN Shared Server - Quick Reference Files

> Copy these files directly into your project. No edits needed except `PROJECT_ROOT` in the proxy if your structure differs.

---

## File 1: `scripts/lain-server-manager.sh`

```bash
#!/bin/bash
# LAIN MCP Server Manager - Ensures singleton HTTP server for all agents

set -e

LAIN_BIN="${LAIN_BIN:-$HOME/.local/lain/lain}"
LAIN_MODEL="${LAIN_MODEL:-$HOME/.local/lain/models/all-MiniLM-L6-v2.onnx}"
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
        echo "LAIN server already running on port $PORT (PID: $(cat "$PIDFILE" 2>/dev/null || echo 'unknown'))"
        return 0
    fi
    
    echo "Starting LAIN MCP server on port $PORT..."
    rm -f "$PIDFILE"
    
    nohup "$LAIN_BIN" \
        --workspace "$PROJECT_ROOT" \
        --transport http \
        --port "$PORT" \
        --embedding-model "$LAIN_MODEL" \
        > "$LOGFILE" 2>&1 &
    
    local pid=$!
    echo $pid > "$PIDFILE"
    
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
        ((attempts++))
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
        local attempts=0
        while kill -0 "$pid" 2>/dev/null && [[ $attempts -lt 10 ]]; do
            sleep 0.5
            ((attempts++))
        done
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
    else
        echo "✗ LAIN server not running"
        return 1
    fi
}

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
        echo "Environment:"
        echo "  LAIN_PORT - HTTP port (default: 9999)"
        exit 1
        ;;
esac
```

---

## File 2: `scripts/lain-mcp-proxy.sh`

```bash
#!/bin/bash
# LAIN MCP Proxy - Bridges HTTP server to stdio for MCP clients

set -e

LAIN_PORT="${LAIN_PORT:-9999}"
LAIN_URL="http://localhost:$LAIN_PORT/mcp"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Ensure the HTTP server is running
if ! curl -s "$LAIN_URL" -X POST \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
    >/dev/null 2>&1; then
    
    "$PROJECT_ROOT/scripts/lain-server-manager.sh" start >/dev/null 2>&1 || true
    sleep 2
fi

# Check again
if ! curl -s "$LAIN_URL" -X POST \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
    >/dev/null 2>&1; then
    echo '{"jsonrpc":"2.0","error":{"code":-32000,"message":"LAIN HTTP server not available on port '$LAIN_PORT'"},"id":null}' >&2
    exit 1
fi

# Bridge: read JSON-RPC from stdin, forward to HTTP, write response to stdout
while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    
    response=$(curl -s -X POST "$LAIN_URL" \
        -H "Content-Type: application/json" \
        -d "$line" 2>/dev/null)
    
    if [[ -n "$response" ]]; then
        echo "$response"
    fi
done
```

---

## File 3: `.vscode/mcp.json`

```json
{
  "servers": {
    "lain": {
      "type": "stdio",
      "command": "${workspaceFolder}/scripts/lain-mcp-proxy.sh",
      "env": {
        "LAIN_PORT": "9999"
      }
    }
  }
}
```

---

## File 4: `.vscode/settings.json` (optional)

```json
{
  "github.copilot.chat.codeGeneration.useInstructionFiles": true,
  "github.copilot.chat.codeGeneration.instructions": [
    {
      "file": "CLAUDE.md"
    },
    {
      "file": "AGENTS.md"
    }
  ]
}
```

---

## File 5: `.continue/config.yaml` snippet

```yaml
mcpServers:
  - name: lain
    transport: stdio
    command: /absolute/path/to/your/project/scripts/lain-mcp-proxy.sh
    env:
      LAIN_PORT: "9999"
```

---

## Installation Commands

```bash
# Make scripts executable
chmod +x scripts/lain-server-manager.sh
chmod +x scripts/lain-mcp-proxy.sh

# Start server manually (optional - proxy auto-starts)
./scripts/lain-server-manager.sh start

# Check status
./scripts/lain-server-manager.sh status
```

---

## Testing the Connection

```bash
# Test HTTP server directly
curl -X POST http://localhost:9999/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_health","arguments":{}},"id":1}'

# Test via proxy
echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_health","arguments":{}},"id":1}' | ./scripts/lain-mcp-proxy.sh
```

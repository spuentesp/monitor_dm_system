# LAIN Shared Server Setup

> **Use Case**: Running a single LAIN instance shared across multiple AI agents (GitHub Copilot, Continue.dev, Claude Code, etc.)

## The Problem

By default, LAIN uses `stdio` transport, which means **each MCP client spawns its own LAIN process**. If you use both GitHub Copilot and Continue.dev, you'd have:
- Two separate LAIN processes
- Two separate code graphs in memory
- Duplicate LSP connections
- Wasted resources

## The Solution: HTTP Server + STDIO Proxy

```
┌─────────────────────────────────────────┐
│         LAIN HTTP Server                │
│         Port: 9999                       │
│    (Singleton - One Instance)           │
│    Persistent graph, shared state     │
└─────────────────┬───────────────────────┘
                  │
      ┌───────────┴───────────┐
      │                       │
┌─────▼──────┐          ┌─────▼──────┐
│ MCP Proxy  │          │ MCP Proxy  │
│ (Agent 1)  │          │ (Agent 2)  │
│   stdio    │          │   stdio    │
│   in/out   │          │   in/out   │
└────────────┘          └────────────┘
```

**How it works**:
1. LAIN runs as an HTTP server (one instance)
2. Each agent connects via a thin `stdio` proxy script
3. The proxy forwards requests to the shared HTTP server
4. If the server isn't running, the proxy auto-starts it

## Installation

### 1. Install LAIN

```bash
curl -fsSL https://raw.githubusercontent.com/spuentesp/lain/main/install.sh | bash
```

With ONNX model (optional, for semantic search):
```bash
mkdir -p ~/.local/lain/models
curl -L -o ~/.local/lain/models/all-MiniLM-L6-v2.onnx \
  "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx/model.onnx"
curl -L -o ~/.local/lain/models/tokenizer.json \
  "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/tokenizer.json"
```

### 2. Project Setup

Create these files in your project:

#### `scripts/lain-server-manager.sh`

```bash
#!/bin/bash
# LAIN MCP Server Manager - Ensures singleton HTTP server

set -e

LAIN_BIN="${LAIN_BIN:-$HOME/.local/lain/lain}"
LAIN_MODEL="${LAIN_MODEL:-$HOME/.local/lain/models/all-MiniLM-L6-v2.onnx}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDFILE="$PROJECT_ROOT/.lain/server.pid"
LOGFILE="$PROJECT_ROOT/.lain/server.log"
PORT="${LAIN_PORT:-9999}"

ensure_dirs() { mkdir -p "$PROJECT_ROOT/.lain"; }

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
    return 1
}

start_server() {
    ensure_dirs
    if is_running; then
        echo "LAIN server already running on port $PORT"
        return 0
    fi
    
    rm -f "$PIDFILE"
    nohup "$LAIN_BIN" \
        --workspace "$PROJECT_ROOT" \
        --transport http \
        --port "$PORT" \
        --embedding-model "$LAIN_MODEL" \
        > "$LOGFILE" 2>&1 &
    
    echo $! > "$PIDFILE"
    
    # Wait for ready
    for i in {1..30}; do
        if curl -s "http://localhost:$PORT/mcp" -X POST \
            -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
            >/dev/null 2>&1; then
            echo "✓ LAIN server ready on http://localhost:$PORT"
            return 0
        fi
        sleep 0.5
    done
    
    echo "✗ Failed to start"; rm -f "$PIDFILE"; return 1
}

stop_server() {
    if [[ -f "$PIDFILE" ]]; then
        kill "$(cat "$PIDFILE")" 2>/dev/null || true
        rm -f "$PIDFILE"
    fi
    echo "✓ LAIN server stopped"
}

status() {
    if is_running; then
        echo "✓ Running on port $PORT (PID: $(cat "$PIDFILE"))"
    else
        echo "✗ Not running"
    fi
}

case "${1:-start}" in
    start) start_server ;;
    stop) stop_server ;;
    restart) stop_server; sleep 1; start_server ;;
    status) status ;;
esac
```

#### `scripts/lain-mcp-proxy.sh`

```bash
#!/bin/bash
# STDIO-to-HTTP proxy for LAIN MCP
# Ensures singleton server is running, then bridges stdio to HTTP

set -e

LAIN_PORT="${LAIN_PORT:-9999}"
LAIN_URL="http://localhost:$LAIN_PORT/mcp"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Auto-start if not running
if ! curl -s "$LAIN_URL" -X POST \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
    >/dev/null 2>&1; then
    "$PROJECT_ROOT/scripts/lain-server-manager.sh" start >/dev/null 2>&1 || true
    sleep 2
fi

# Bridge stdio to HTTP
while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    response=$(curl -s -X POST "$LAIN_URL" \
        -H "Content-Type: application/json" \
        -d "$line" 2>/dev/null)
    [[ -n "$response" ]] && echo "$response"
done
```

Make them executable:
```bash
chmod +x scripts/lain-server-manager.sh scripts/lain-mcp-proxy.sh
```

## Editor Configuration

### VS Code + GitHub Copilot

Create `.vscode/mcp.json`:

```json
{
  "servers": {
    "lain": {
      "type": "stdio",
      "command": "/path/to/your/project/scripts/lain-mcp-proxy.sh",
      "env": {
        "LAIN_PORT": "9999"
      }
    }
  }
}
```

Optional `.vscode/settings.json` for Copilot instructions:

```json
{
  "github.copilot.chat.codeGeneration.useInstructionFiles": true,
  "github.copilot.chat.codeGeneration.instructions": [
    { "file": "CLAUDE.md" },
    { "file": "AGENTS.md" }
  ]
}
```

### Continue.dev

Add to `.continue/config.yaml`:

```yaml
mcpServers:
  - name: lain
    transport: stdio
    command: /path/to/your/project/scripts/lain-mcp-proxy.sh
    env:
      LAIN_PORT: "9999"
```

### Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "lain": {
      "command": "/path/to/your/project/scripts/lain-mcp-proxy.sh",
      "env": {
        "LAIN_PORT": "9999"
      }
    }
  }
}
```

## Usage

### Check Status

```bash
./scripts/lain-server-manager.sh status
```

Output:
```
✓ Running on port 9999 (PID: 804849)
```

### Stop Server

```bash
./scripts/lain-server-manager.sh stop
```

### Restart

```bash
./scripts/lain-server-manager.sh restart
```

### Manual Start (optional)

The proxy auto-starts the server, but you can pre-warm:

```bash
./scripts/lain-server-manager.sh start
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LAIN_PORT` | `9999` | HTTP port for the shared server |
| `LAIN_BIN` | `~/.local/lain/lain` | Path to lain binary |
| `LAIN_MODEL` | `~/.local/lain/models/all-MiniLM-L6-v2.onnx` | Path to ONNX model |

## Multiple Projects

You can run **multiple LAIN servers** on different ports for different projects:

**Project A**:
```bash
export LAIN_PORT=9999
./scripts/lain-server-manager.sh start
```

**Project B**:
```bash
export LAIN_PORT=9998
./scripts/lain-server-manager.sh start
```

Each project manages its own server independently.

## Troubleshooting

### "LAIN HTTP server not available"

The proxy couldn't connect. Check:
```bash
./scripts/lain-server-manager.sh status
cat .lain/server.log
```

### Port already in use

Change the port:
```bash
export LAIN_PORT=9998
./scripts/lain-server-manager.sh start
```

Then update all `LAIN_PORT` values in your editor configs.

### Graph not updating

The server maintains a volatile overlay. To sync to git HEAD:

```bash
# Via HTTP API
curl -X POST http://localhost:9999/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"sync_state","arguments":{}},"id":1}'
```

Or restart the server.

## How It Works (Detailed)

1. **HTTP Server Mode**: LAIN runs with `--transport http` exposing JSON-RPC at `POST /mcp`
2. **PID Tracking**: The manager writes the PID to `.lain/server.pid`
3. **Health Checks**: The manager verifies the process is actually responding, not just existing
4. **Proxy Bridge**: The proxy script:
   - Checks if HTTP server is up
   - Auto-starts it if needed (via the manager)
   - Reads JSON-RPC from stdin (from MCP client)
   - POSTs to HTTP server
   - Writes HTTP response to stdout (back to MCP client)
5. **Singleton Guarantee**: Only one HTTP server per port; proxies are stateless thin clients

## Benefits

| Aspect | Per-Process (stdio) | Shared (HTTP + Proxy) |
|--------|---------------------|----------------------|
| Memory | N × ~100MB | ~100MB total |
| Graph Build Time | N × slow | Once, shared |
| LSP Connections | N × duplicated | Shared |
| Consistency | May drift | Single source of truth |
| Startup Time | Each client waits | Instant (already running) |

## Credits

This setup pattern was contributed by the community for teams using multiple AI agents simultaneously.

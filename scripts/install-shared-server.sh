#!/bin/bash
# One-liner installer for LAIN shared server setup
# Usage: curl -fsSL .../install-shared-server.sh | bash
# Or: ./install-shared-server.sh

set -e

REPO_URL="https://raw.githubusercontent.com/spuentesp/lain/main"
INSTALL_DIR="${INSTALL_DIR:-./lain-shared-server}"

echo "LAIN Shared Server Setup Installer"
echo "==================================="
echo ""

# Create directory
mkdir -p "$INSTALL_DIR/scripts"

echo "Downloading server manager..."
curl -fsSL "$REPO_URL/examples/shared-server/lain-server-manager.sh" \
  -o "$INSTALL_DIR/scripts/lain-server-manager.sh" 2>/dev/null || {
  echo "Error: Could not download. Using embedded version..."
  cat > "$INSTALL_DIR/scripts/lain-server-manager.sh" << 'MANAGER_EOF'
#!/bin/bash
set -e
LAIN_BIN="${LAIN_BIN:-$HOME/.local/lain/lain}"
LAIN_MODEL="${LAIN_MODEL:-$HOME/.local/lain/models/all-MiniLM-L6-v2.onnx}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDFILE="$PROJECT_ROOT/.lain/server.pid"
LOGFILE="$PROJECT_ROOT/.lain/server.log"
PORT="${LAIN_PORT:-9999}"

ensure_dirs() { mkdir -p "$PROJECT_ROOT/.lain"; }

is_running() {
    if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
        curl -s "http://localhost:$PORT/mcp" -X POST \
            -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' >/dev/null 2>&1 && return 0
    fi
    return 1
}

start_server() {
    ensure_dirs
    if is_running; then echo "LAIN already running on port $PORT"; return 0; fi
    echo "Starting LAIN MCP server on port $PORT..."
    rm -f "$PIDFILE"
    nohup "$LAIN_BIN" --workspace "$PROJECT_ROOT" --transport http --port "$PORT" \
        --embedding-model "$LAIN_MODEL" > "$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"
    for i in {1..30}; do
        curl -s "http://localhost:$PORT/mcp" -X POST -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' >/dev/null 2>&1 && \
            { echo "✓ LAIN ready on http://localhost:$PORT"; return 0; }
        sleep 0.5
    done
    echo "✗ Failed to start"; rm -f "$PIDFILE"; return 1
}

stop_server() {
    [[ -f "$PIDFILE" ]] && { kill "$(cat "$PIDFILE")" 2>/dev/null || true; rm -f "$PIDFILE"; }
    echo "✓ LAIN server stopped"
}

case "${1:-start}" in start) start_server ;; stop) stop_server ;; restart) stop_server; sleep 1; start_server ;; status) is_running && echo "✓ Running" || echo "✗ Not running" ;; *) echo "Usage: $0 [start|stop|restart|status]" ;; esac
MANAGER_EOF
}

echo "Downloading MCP proxy..."
curl -fsSL "$REPO_URL/examples/shared-server/lain-mcp-proxy.sh" \
  -o "$INSTALL_DIR/scripts/lain-mcp-proxy.sh" 2>/dev/null || {
  cat > "$INSTALL_DIR/scripts/lain-mcp-proxy.sh" << 'PROXY_EOF'
#!/bin/bash
set -e
LAIN_PORT="${LAIN_PORT:-9999}"
LAIN_URL="http://localhost:$LAIN_PORT/mcp"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! curl -s "$LAIN_URL" -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' >/dev/null 2>&1; then
    "$PROJECT_ROOT/scripts/lain-server-manager.sh" start >/dev/null 2>&1 || true
    sleep 2
fi

while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    response=$(curl -s -X POST "$LAIN_URL" -H "Content-Type: application/json" -d "$line" 2>/dev/null)
    [[ -n "$response" ]] && echo "$response"
done
PROXY_EOF
}

chmod +x "$INSTALL_DIR/scripts/lain-server-manager.sh"
chmod +x "$INSTALL_DIR/scripts/lain-mcp-proxy.sh"

# Create VS Code config
cat > "$INSTALL_DIR/.vscode-mcp.json" << 'EOF'
{
  "servers": {
    "lain": {
      "type": "stdio",
      "command": "${workspaceFolder}/scripts/lain-mcp-proxy.sh",
      "env": { "LAIN_PORT": "9999" }
    }
  }
}
EOF

# Create Continue.dev config snippet
cat > "$INSTALL_DIR/continue-snippet.yaml" << 'EOF'
mcpServers:
  - name: lain
    transport: stdio
    command: /path/to/your/project/scripts/lain-mcp-proxy.sh
    env:
      LAIN_PORT: "9999"
EOF

echo ""
echo "========================================"
echo "Setup complete in: $INSTALL_DIR"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Copy .vscode-mcp.json to .vscode/mcp.json"
echo "2. Update continue-snippet.yaml with your project path"
echo "3. Run: ./scripts/lain-server-manager.sh start"
echo ""
echo "Files created:"
ls -la "$INSTALL_DIR/scripts/"
echo ""

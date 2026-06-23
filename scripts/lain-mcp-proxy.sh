#!/bin/bash
# LAIN MCP Proxy - Bridges HTTP server to stdio for MCP clients
# Usage: This script is called by MCP clients (VS Code, Continue.dev) as a stdio transport
# It forwards all stdin to the HTTP server and returns responses on stdout

set -e

LAIN_PORT="${LAIN_PORT:-9999}"
LAIN_URL="http://localhost:$LAIN_PORT/mcp"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Ensure the HTTP server is running
if ! curl -s "$LAIN_URL" -X POST \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
    >/dev/null 2>&1; then
    
    # Try to start it
    "$PROJECT_ROOT/scripts/lain-server-manager.sh" start >/dev/null 2>&1 || true
    
    # Wait a moment for server to start
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

# Main loop: read JSON-RPC requests from stdin, forward to HTTP, write response to stdout
while IFS= read -r line || [[ -n "$line" ]]; do
    # Skip empty lines
    [[ -z "$line" ]] && continue
    
    # Forward to HTTP server and output response
    response=$(curl -s -X POST "$LAIN_URL" \
        -H "Content-Type: application/json" \
        -d "$line" 2>/dev/null)
    
    if [[ -n "$response" ]]; then
        echo "$response"
    fi
done

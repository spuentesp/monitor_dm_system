#!/bin/bash
# Setup script for LAIN MCP server with GitHub Copilot and Continue.dev
# Uses HTTP server with proxy for singleton pattern (shared across all agents)

set -e

LAIN_BIN="/home/sebastian/.local/lain/lain"
LAIN_MODEL="/home/sebastian/.local/lain/models/all-MiniLM-L6-v2.onnx"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAIN_PORT="${LAIN_PORT:-9999}"

echo "========================================"
echo "LAIN MCP Server Setup"
echo "========================================"
echo "Project: $PROJECT_ROOT"
echo "LAIN binary: $LAIN_BIN"
echo "HTTP Port: $LAIN_PORT"
echo ""

# Verify LAIN is installed
if [[ ! -x "$LAIN_BIN" ]]; then
    echo "Error: LAIN not found at $LAIN_BIN"
    echo "Please install LAIN first:"
    echo "  curl -fsSL https://raw.githubusercontent.com/spuentesp/lain/main/install.sh | bash"
    exit 1
fi

# Verify model exists
if [[ ! -f "$LAIN_MODEL" ]]; then
    echo "Warning: ONNX model not found at $LAIN_MODEL"
    echo "Semantic search will be unavailable, but all other features work."
fi

# Make scripts executable
chmod +x "$PROJECT_ROOT/scripts/lain-server-manager.sh"
chmod +x "$PROJECT_ROOT/scripts/lain-mcp-proxy.sh"

echo "Step 1: Creating VS Code settings for GitHub Copilot..."

# Create VS Code settings directory
VSCODE_DIR="$PROJECT_ROOT/.vscode"
mkdir -p "$VSCODE_DIR"

# VS Code MCP config using the proxy (which ensures singleton HTTP server)
cat > "$VSCODE_DIR/mcp.json" << EOF
{
  "servers": {
    "lain": {
      "type": "stdio",
      "command": "$PROJECT_ROOT/scripts/lain-mcp-proxy.sh",
      "env": {
        "LAIN_PORT": "$LAIN_PORT"
      }
    }
  }
}
EOF

echo "  Created: $VSCODE_DIR/mcp.json"

# Additional VS Code settings for better Copilot integration
cat > "$VSCODE_DIR/settings.json" << EOF
{
  "github.copilot.chat.codeGeneration.useInstructionFiles": true,
  "github.copilot.chat.codeGeneration.instructions": [
    {
      "file": "CLAUDE.md"
    },
    {
      "file": "AGENTS.md"
    }
  ],
  "mcp": {
    "servers": {
      "lain": {
        "type": "stdio",
        "command": "$PROJECT_ROOT/scripts/lain-mcp-proxy.sh",
        "env": {
          "LAIN_PORT": "$LAIN_PORT"
        }
      }
    }
  }
}
EOF

echo "  Created: $VSCODE_DIR/settings.json"

echo ""
echo "Step 2: Updating Continue.dev config..."

# Check if Continue config exists
CONTINUE_CONFIG="$PROJECT_ROOT/.continue/config.yaml"
if [[ -f "$CONTINUE_CONFIG" ]]; then
    # Check if LAIN is already configured
    if grep -q "name: lain" "$CONTINUE_CONFIG" 2>/dev/null; then
        echo "  LAIN already configured in Continue.dev"
    else
        # Append LAIN config
        cat >> "$CONTINUE_CONFIG" << EOF

# LAIN MCP Server Configuration
# Shared singleton server - proxy ensures HTTP server is running
mcpServers:
  - name: lain
    transport: stdio
    command: $PROJECT_ROOT/scripts/lain-mcp-proxy.sh
    env:
      LAIN_PORT: $LAIN_PORT
EOF
        echo "  Updated: $CONTINUE_CONFIG"
    fi
else
    echo "  Warning: Continue.dev config not found at $CONTINUE_CONFIG"
    echo "  Please manually add LAIN to your Continue.dev MCP servers"
fi

echo ""
echo "Step 3: Starting LAIN HTTP server (singleton)..."
"$PROJECT_ROOT/scripts/lain-server-manager.sh" start

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "Architecture:"
echo "  ┌─────────────────────────────────────────┐"
echo "  │         LAIN HTTP Server                │"
echo "  │         Port: $LAIN_PORT                    │"
echo "  │         (Singleton - One Instance)      │"
echo "  └─────────────────┬───────────────────────┘"
echo "                    │"
echo "        ┌───────────┴───────────┐"
echo "        │                       │"
echo "  ┌─────▼──────┐          ┌─────▼──────┐"
echo "  │ MCP Proxy  │          │ MCP Proxy  │"
echo "  │ (VS Code)  │          │(Continue)  │"
echo "  └─────┬──────┘          └─────┬──────┘"
echo "        │                       │"
echo "  ┌─────▼──────┐          ┌─────▼──────┐"
echo "  │GitHub Cop- │          │ Continue   │"
echo "  │   ilot     │          │   .dev     │"
echo "  └────────────┘          └────────────┘"
echo ""
echo "Next Steps:"
echo "1. Reload VS Code window (Cmd/Ctrl+Shift+P: 'Developer: Reload Window')"
echo "2. For Continue.dev: reload the extension or restart"
echo "3. Both agents now share ONE LAIN server instance"
echo ""
echo "Management commands:"
echo "  ./scripts/lain-server-manager.sh status   - Check server status"
echo "  ./scripts/lain-server-manager.sh stop     - Stop the server"
echo "  ./scripts/lain-server-manager.sh restart  - Restart the server"
echo ""
echo "LAIN Tools available (30+ total):"
echo "  query_graph          - Graph-based code queries with pipeline"
echo "  get_blast_radius     - Find everything affected by a change"
echo "  get_call_chain       - Trace paths between functions"
echo "  semantic_search      - Find code by meaning (semantic similarity)"
echo "  find_anchors         - Identify stable architectural pillars"
echo "  explore_architecture - High-level module structure"
echo "  trace_dependency     - Full transitive dependencies"
echo "  find_dead_code       - Potentially unreachable code"
echo "  suggest_refactor_targets - High-coupling, low-stability nodes"
echo "  run_build/run_tests  - Build with architectural error context"
echo ""

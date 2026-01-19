---
description: Start SERENA MCP server for development
---

# Start SERENA MCP Server

This workflow starts the SERENA MCP server which provides semantic code analysis tools for agents.

## Prerequisites

1. **uv installed**: 
   ```bash
   uv --version
   ```
   If not installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`

2. **SERENA accessible**:
   ```bash
   uvx --from git+https://github.com/oraios/serena serena --version
   ```

## Quick Start

// turbo
1. Start the SERENA MCP server in background:
   ```bash
   bash scripts/start-serena-mcp.sh
   ```

2. Check server status:
   ```bash
   bash scripts/status-serena-mcp.sh
   ```

3. View logs (optional):
   ```bash
   tail -f .serena/serena-mcp.log
   ```

## Stop Server

When done:
```bash
bash scripts/stop-serena-mcp.sh
```

## Manual Start (Foreground)

If you want to run in foreground for debugging:
```bash
uvx --from git+https://github.com/oraios/serena serena start-mcp-server \
  --project /home/sebas/monitor2 \
  --context ide
```

Press `Ctrl+C` to stop.

## Troubleshooting

### Server won't start
```bash
# Check if already running
bash scripts/status-serena-mcp.sh

# Check logs
cat .serena/serena-mcp.log

# Kill any stuck processes
pkill -f "serena start-mcp-server"
```

### Can't find uvx
```bash
# Add to PATH
export PATH="$HOME/.local/bin:$PATH"

# Make permanent
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## Integration with MCP Clients

See `.agent/mcp-servers.json` for configuration with Claude Desktop, Codex, or other MCP clients.

## What SERENA Provides

- **Code Navigation**: Find symbols, references, definitions
- **Code Editing**: Replace functions, insert code at symbol level
- **Semantic Search**: Search code patterns intelligently
- **File Operations**: Read, create, modify files
- **Project Tools**: Onboarding, shell commands, memory storage

See `docs/SERENA_QUICK_REFERENCE.md` for common use cases.

#!/bin/bash
# Stop SERENA MCP Server

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$PROJECT_ROOT/.serena/serena-mcp.pid"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

if [ ! -f "$PIDFILE" ]; then
    echo -e "${YELLOW}⚠ SERENA MCP server is not running (no PID file found)${NC}"
    exit 0
fi

PID=$(cat "$PIDFILE")

if ! ps -p "$PID" > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ SERENA MCP server is not running (stale PID file)${NC}"
    rm "$PIDFILE"
    exit 0
fi

echo -e "${YELLOW}🛑 Stopping SERENA MCP server (PID: $PID)...${NC}"
kill "$PID"

# Wait for graceful shutdown
sleep 2

# Force kill if still running
if ps -p "$PID" > /dev/null 2>&1; then
    echo -e "${RED}⚠ Forcing shutdown...${NC}"
    kill -9 "$PID"
fi

rm "$PIDFILE"
echo -e "${GREEN}✓ SERENA MCP server stopped${NC}"

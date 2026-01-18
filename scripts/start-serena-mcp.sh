#!/bin/bash
# SERENA MCP Server Auto-Start Script for MONITOR
# This script ensures SERENA is running when you start development

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$PROJECT_ROOT/.serena/serena-mcp.pid"
LOGFILE="$PROJECT_ROOT/.serena/serena-mcp.log"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}   SERENA MCP Server for MONITOR${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if uv is installed
if ! command -v uvx &> /dev/null; then
    echo -e "${RED}✗ Error: 'uvx' (uv) is not installed${NC}"
    echo "  Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Check if already running
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠ SERENA MCP server is already running (PID: $OLD_PID)${NC}"
        echo ""
        echo "To stop it: kill $OLD_PID"
        echo "To view logs: tail -f $LOGFILE"
        exit 0
    else
        # Stale PID file
        rm "$PIDFILE"
    fi
fi

echo -e "${GREEN}📍 Project:${NC} $PROJECT_ROOT"
echo -e "${GREEN}📦 Context:${NC} ide"
echo -e "${GREEN}📝 Logs:${NC} $LOGFILE"
echo ""

# Start SERENA in background
echo -e "${YELLOW}🚀 Starting SERENA MCP server...${NC}"

nohup uvx --from git+https://github.com/oraios/serena serena start-mcp-server \
  --project "$PROJECT_ROOT" \
  --context ide \
  > "$LOGFILE" 2>&1 &

# Save PID
echo $! > "$PIDFILE"

# Wait a moment for startup
sleep 2

# Check if still running
if ps -p $(cat "$PIDFILE") > /dev/null 2>&1; then
    echo -e "${GREEN}✓ SERENA MCP server started successfully!${NC}"
    echo ""
    echo -e "  ${GREEN}PID:${NC} $(cat $PIDFILE)"
    echo -e "  ${GREEN}Logs:${NC} tail -f $LOGFILE"
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${YELLOW}MCP Server Ready${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "To stop: bash scripts/stop-serena-mcp.sh"
    echo "To view logs: tail -f $LOGFILE"
    echo ""
else
    echo -e "${RED}✗ Failed to start SERENA MCP server${NC}"
    echo "Check logs: cat $LOGFILE"
    rm "$PIDFILE"
    exit 1
fi

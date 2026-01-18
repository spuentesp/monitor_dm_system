#!/bin/bash
# Check SERENA MCP Server Status

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$PROJECT_ROOT/.serena/serena-mcp.pid"
LOGFILE="$PROJECT_ROOT/.serena/serena-mcp.log"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}   SERENA MCP Server Status${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if PID file exists
if [ ! -f "$PIDFILE" ]; then
    echo -e "${RED}✗ Status: NOT RUNNING${NC}"
    echo "  No PID file found"
    echo ""
    echo "To start: bash scripts/start-serena-mcp.sh"
    exit 1
fi

PID=$(cat "$PIDFILE")

# Check if process is running
if ps -p "$PID" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Status: RUNNING${NC}"
    echo ""
    echo -e "  ${GREEN}PID:${NC} $PID"
    echo -e "  ${GREEN}Project:${NC} $PROJECT_ROOT"
    echo -e "  ${GREEN}Log file:${NC} $LOGFILE"
    echo ""
    
    # Show last few log lines
    if [ -f "$LOGFILE" ]; then
        echo -e "${YELLOW}Recent logs:${NC}"
        echo "─────────────────────────────────────────"
        tail -n 5 "$LOGFILE" 2>/dev/null || echo "  (no logs yet)"
        echo "─────────────────────────────────────────"
        echo ""
        echo "View full logs: tail -f $LOGFILE"
    fi
    
    echo ""
    echo "To stop: bash scripts/stop-serena-mcp.sh"
else
    echo -e "${RED}✗ Status: NOT RUNNING${NC}"
    echo "  Stale PID file found (process $PID not running)"
    echo ""
    rm "$PIDFILE"
    echo "To start: bash scripts/start-serena-mcp.sh"
    exit 1
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

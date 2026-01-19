# SERENA Auto-Start Setup

## 🎯 Goal
Make SERENA MCP server start automatically when you begin working on MONITOR.

---

## ✅ Quick Start (Recommended)

Add this to your shell startup file (`.bashrc` or `.zshrc`):

```bash
# Auto-start SERENA for MONITOR project
if [ "$PWD" = "$HOME/monitor2" ] || [[ "$PWD" == "$HOME/monitor2/"* ]]; then
    # Only start if not already running
    if [ ! -f "$HOME/monitor2/.serena/serena-mcp.pid" ]; then
        echo "🚀 Auto-starting SERENA MCP server..."
        bash "$HOME/monitor2/scripts/start-serena-mcp.sh"
    fi
fi
```

**What this does**:
- Checks if you're in the MONITOR project directory
- Starts SERENA automatically if not already running
- Runs in background so you can continue working

---

## 🔧 Setup Instructions

### 1. Add to Shell Startup

```bash
# Edit your shell config
nano ~/.bashrc  # or ~/.zshrc if using zsh

# Add the auto-start code above
# Save and exit (Ctrl+X, Y, Enter)

# Reload shell
source ~/.bashrc
```

### 2. Test It

```bash
# Navigate to project
cd ~/monitor2

# SERENA should auto-start now
# Check status
bash scripts/status-serena-mcp.sh
```

---

## 🎮 Manual Control

Even with auto-start enabled, you can manually control SERENA:

```bash
# Start manually
bash scripts/start-serena-mcp.sh

# Check status
bash scripts/status-serena-mcp.sh

# Stop
bash scripts/stop-serena-mcp.sh

# View logs
tail -f .serena/serena-mcp.log
```

---

## 🚀 Alternative: systemd Service (Linux)

For more robust auto-start, create a systemd user service:

### 1. Create Service File

```bash
mkdir -p ~/.config/systemd/user
nano ~/.config/systemd/user/serena-monitor.service
```

### 2. Add Service Configuration

```ini
[Unit]
Description=SERENA MCP Server for MONITOR
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/sebas/monitor2
ExecStart=/home/sebas/.local/bin/uvx --from git+https://github.com/oraios/serena serena start-mcp-server --project /home/sebas/monitor2 --context ide
Restart=on-failure
RestartSec=5
StandardOutput=append:/home/sebas/monitor2/.serena/serena-mcp.log
StandardError=append:/home/sebas/monitor2/.serena/serena-mcp.log

[Install]
WantedBy=default.target
```

### 3. Enable and Start

```bash
# Reload systemd
systemctl --user daemon-reload

# Enable auto-start on login
systemctl --user enable serena-monitor.service

# Start now
systemctl --user start serena-monitor.service

# Check status
systemctl --user status serena-monitor.service
```

### 4. Control Service

```bash
# Start
systemctl --user start serena-monitor

# Stop
systemctl --user stop serena-monitor

# Restart
systemctl --user restart serena-monitor

# View logs
journalctl --user -u serena-monitor -f
```

---

## 🔌 MCP Client Integration

For integration with Claude Desktop, Codex, or other MCP clients, add to their config:

### Claude Desktop (.config/Claude/claude_desktop_config.json)

```json
{
  "mcpServers": {
    "monitor-data-layer": {
      "command": "monitor-data",
      "args": []
    },
    "serena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
        "start-mcp-server",
        "--project",
        "/home/sebas/monitor2",
        "--context",
        "ide"
      ]
    }
  }
}
```

### Codex (~/.config/codex/mcp.json)

```json
{
  "mcpServers": {
    "serena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
        "start-mcp-server",
        "--project",
        "/home/sebas/monitor2",
        "--context",
        "ide"
      ]
    }
  }
}
```

---

## 📋 Verification Checklist

✅ **uv installed**: `uv --version`  
✅ **SERENA accessible**: `uvx --from git+https://github.com/oraios/serena serena --version`  
✅ **Auto-start configured**: Added to `.bashrc` or systemd  
✅ **Server starts**: `bash scripts/start-serena-mcp.sh`  
✅ **Status checks work**: `bash scripts/status-serena-mcp.sh`  
✅ **MCP client configured**: Added to Claude Desktop/Codex config  

---

## 🎯 Recommended Setup

For MONITOR development, we recommend:

1. **Shell auto-start** (simple, works everywhere)
2. **Background mode** (doesn't block terminal)
3. **Log monitoring** (tail -f .serena/serena-mcp.log in separate terminal)

This ensures SERENA is always available when you're coding, without manual intervention.

---

## 🆘 Troubleshooting

### Server keeps restarting
```bash
# Check logs
cat .serena/serena-mcp.log

# Common issues:
# - Python LSP not installed: pip install python-lsp-server
# - Port already in use: Check for duplicate processes
```

### Auto-start not working
```bash
# Test the condition manually
cd ~/monitor2
bash scripts/start-serena-mcp.sh

# Check .bashrc was sourced
source ~/.bashrc

# Verify auto-start code is in .bashrc
grep -A 5 "Auto-start SERENA" ~/.bashrc
```

### Can't connect from MCP client
```bash
# Verify server is running
bash scripts/status-serena-mcp.sh

# Check MCP client config
# Ensure paths are absolute, not relative
```

---

**Next Steps**: Choose your preferred auto-start method and set it up! 🚀

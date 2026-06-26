#!/usr/bin/env fish
# claude-provider.fish — Toggle Claude Code between Anthropic and MiniMax M3
#
# Usage:
#   claude-provider minimax    # switch to MiniMax M3
#   claude-provider anthropic   # switch back to Anthropic defaults
#   claude-provider status      # show current provider
#
# MiniMax API key is read from $MINIMAX_API_KEY env var, or from
# ~/.config/claude-provider/minimax_key (a plain-text file you create once).
#
# Setup (one-time):
#   mkdir -p ~/.config/claude-provider
#   echo "your-minimax-api-key-here" > ~/.config/claude-provider/minimax_key
#   chmod 600 ~/.config/claude-provider/minimax_key
#
# Or just export MINIMAX_API_KEY in your fish config.

set -g SETTINGS_FILE "$HOME/.claude/settings.json"
set -g KEY_FILE "$HOME/.config/claude-provider/minimax_key"
set -g BACKUP_FILE "$HOME/.config/claude-provider/settings.anthropic.bak.json"

# ── Helpers ──────────────────────────────────────────────────────────────────

function _get_minimax_key
    # Prefer env var
    if set -q MINIMAX_API_KEY && test -n "$MINIMAX_API_KEY"
        echo "$MINIMAX_API_KEY"
        return 0
    end
    # Fall back to file
    if test -f "$KEY_FILE"
        cat "$KEY_FILE" | string trim
        return 0
    end
    return 1
end

function _ensure_dirs
    mkdir -p "$HOME/.claude"
    mkdir -p "$HOME/.config/claude-provider"
end

function _read_settings
    if test -f "$SETTINGS_FILE"
        cat "$SETTINGS_FILE"
    else
        echo '{}'
    end
end

function _write_settings
    set -l content $argv[1]
    echo "$content" > "$SETTINGS_FILE"
end

function _backup_anthropic
    _ensure_dirs
    if test -f "$SETTINGS_FILE"
        # Only back up if the current settings don't already look like MiniMax
        if not grep -q "api.minimax" "$SETTINGS_FILE" 2>/dev/null
            cp "$SETTINGS_FILE" "$BACKUP_FILE"
            echo "✓ Backed up current Anthropic settings to $BACKUP_FILE"
        end
    end
end

# ── Switch to MiniMax ─────────────────────────────────────────────────────────

function _switch_to_minimax
    _ensure_dirs

    set -l key (_get_minimax_key)
    if test $status -ne 0 -o -z "$key"
        echo "ERROR: No MiniMax API key found."
        echo ""
        echo "Set it via one of:"
        echo "  set -Ux MINIMAX_API_KEY 'your-key-here'"
        echo "  echo 'your-key' > $KEY_FILE"
        return 1
    end

    # Back up current Anthropic config before overwriting
    _backup_anthropic

    # Build the new settings, preserving any existing non-env keys
    set -l current (_read_settings)
    set -l base_url "https://api.minimax.io/anthropic"

    # Allow China endpoint override
    if set -q MINIMAX_REGION && test "$MINIMAX_REGION" = "china"
        set base_url "https://api.minimaxi.com/anthropic"
    end

    # Use python to merge JSON properly
    set -l new_settings (python3 -c "
import json, sys

current = json.loads(sys.argv[1])
base_url = sys.argv[2]
key = sys.argv[3]

current.setdefault('env', {})
current['env']['ANTHROPIC_BASE_URL'] = base_url
current['env']['ANTHROPIC_AUTH_TOKEN'] = key
current['env']['CLAUDE_CODE_AUTO_COMPACT_WINDOW'] = '1000000'
current['env']['ANTHROPIC_MODEL'] = 'MiniMax-M3[1m]'
current['env']['ANTHROPIC_DEFAULT_SONNET_MODEL'] = 'MiniMax-M3[1m]'
current['env']['ANTHROPIC_DEFAULT_OPUS_MODEL'] = 'MiniMax-M3[1m]'
current['env']['ANTHROPIC_DEFAULT_HAIKU_MODEL'] = 'MiniMax-M3[1m]'

print(json.dumps(current, indent=2))
" "$current" "$base_url" "$key")

    if test $status -ne 0
        echo "ERROR: Failed to build settings JSON. Is python3 installed?"
        return 1
    end

    _write_settings "$new_settings"

    # Clear any Anthropic env vars from the current shell session
    set -e ANTHROPIC_AUTH_TOKEN 2>/dev/null
    set -e ANTHROPIC_BASE_URL 2>/dev/null

    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║  Switched to MiniMax M3                              ║"
    echo "╠══════════════════════════════════════════════════════╣"
    echo "║  Base URL: $base_url"
    echo "║  Model:    MiniMax-M3[1m]                            ║"
    echo "║  Context:  1,000,000 tokens                          ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""
    echo "Anthropic backup saved at: $BACKUP_FILE"
    echo ""
    echo "Run 'claude' to start. Verify with /status and /model inside Claude Code."
end

# ── Switch to Anthropic ───────────────────────────────────────────────────────

function _switch_to_anthropic
    _ensure_dirs

    if not test -f "$BACKUP_FILE"
        # No backup — just strip the MiniMax env keys
        if test -f "$SETTINGS_FILE"
            set -l current (_read_settings)
            set -l new_settings (python3 -c "
import json, sys
current = json.loads(sys.argv[1])
if 'env' in current:
    for k in ['ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_AUTO_COMPACT_WINDOW',
              'ANTHROPIC_MODEL', 'ANTHROPIC_DEFAULT_SONNET_MODEL',
              'ANTHROPIC_DEFAULT_OPUS_MODEL', 'ANTHROPIC_DEFAULT_HAIKU_MODEL']:
        current['env'].pop(k, None)
    if not current['env']:
        del current['env']
print(json.dumps(current, indent=2))
" "$current")
            _write_settings "$new_settings"
        end
        echo ""
        echo "✓ Removed MiniMax overrides from settings.json"
        echo "  (No Anthropic backup existed — using Claude Code defaults)"
        echo ""
        echo "Run 'claude' to start with Anthropic."
        return 0
    end

    # Restore from backup
    cp "$BACKUP_FILE" "$SETTINGS_FILE"
    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║  Switched to Anthropic (restored from backup)        ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""
    echo "Restored from: $BACKUP_FILE"
    echo ""
    echo "Run 'claude' to start with Anthropic."
end

# ── Show Status ───────────────────────────────────────────────────────────────

function _show_status
    if not test -f "$SETTINGS_FILE"
        echo "No settings.json found at $SETTINGS_FILE"
        echo "Provider: Anthropic (default — no config)"
        return 0
    end

    set -l content (cat "$SETTINGS_FILE")

    if echo "$content" | grep -q "api.minimax"
        echo "Provider: MiniMax M3"
        echo ""
        echo "Settings ($SETTINGS_FILE):"
        echo "$content" | python3 -m json.tool 2>/dev/null || echo "$content"
    else
        echo "Provider: Anthropic (default or custom)"
        echo ""
        echo "Settings ($SETTINGS_FILE):"
        echo "$content" | python3 -m json.tool 2>/dev/null || echo "$content"
    end

    echo ""
    if test -f "$BACKUP_FILE"
        echo "Anthropic backup: $BACKUP_FILE ✓"
    else
        echo "Anthropic backup: none (will strip MiniMax keys on switch)"
    end

    if set -q MINIMAX_API_KEY && test -n "$MINIMAX_API_KEY"
        echo "MINIMAX_API_KEY: set in env ✓"
    else if test -f "$KEY_FILE"
        echo "MiniMax key file: $KEY_FILE ✓"
    else
        echo "MiniMax key: NOT SET ⚠"
    end
end

# ── Main ─────────────────────────────────────────────────────────────────────

set -l cmd $argv[1]

switch "$cmd"
    case minimax mm
        _switch_to_minimax
    case anthropic anthropic-default default
        _switch_to_anthropic
    case status
        _show_status
    case '' --help -h help
        echo "claude-provider — Toggle Claude Code between Anthropic and MiniMax M3"
        echo ""
        echo "Usage:"
        echo "  claude-provider minimax     Switch to MiniMax M3"
        echo "  claude-provider anthropic   Switch back to Anthropic defaults"
        echo "  claude-provider status      Show current provider and settings"
        echo ""
        echo "MiniMax API key (one of):"
        echo "  set -Ux MINIMAX_API_KEY 'your-key'   (fish universal var)"
        echo "  echo 'your-key' > $KEY_FILE"
        echo ""
        echo "For China endpoint: set -Ux MINIMAX_REGION china"
    case '*'
        echo "Unknown command: $cmd"
        echo "Run 'claude-provider help' for usage."
        return 1
end
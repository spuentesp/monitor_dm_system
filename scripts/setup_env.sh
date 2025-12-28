#!/usr/bin/env bash
#
# Setup environment variables for MONITOR
#
# Usage:
#   ./scripts/setup_env.sh           # Interactive setup
#   ./scripts/setup_env.sh --check   # Check if .env exists and has required vars
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
ENV_EXAMPLE="$ROOT_DIR/.env.example"

# Required variables (no defaults allowed)
REQUIRED_VARS=(
    "NEO4J_PASSWORD"
)

# Check mode
if [[ "${1:-}" == "--check" ]]; then
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "❌ .env file not found"
        echo "   Run: ./scripts/setup_env.sh"
        exit 1
    fi

    missing=()
    for var in "${REQUIRED_VARS[@]}"; do
        value=$(grep "^${var}=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-)
        if [[ -z "$value" ]]; then
            missing+=("$var")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "❌ Missing required variables in .env:"
        for var in "${missing[@]}"; do
            echo "   - $var"
        done
        exit 1
    fi

    echo "✓ .env is configured correctly"
    exit 0
fi

# Interactive setup
echo "═══════════════════════════════════════════════════════════════════"
echo "  MONITOR Environment Setup"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

if [[ -f "$ENV_FILE" ]]; then
    echo "⚠️  .env file already exists at $ENV_FILE"
    read -p "   Overwrite? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "   Keeping existing .env"
        exit 0
    fi
fi

if [[ ! -f "$ENV_EXAMPLE" ]]; then
    echo "❌ .env.example not found at $ENV_EXAMPLE"
    exit 1
fi

# Copy template
cp "$ENV_EXAMPLE" "$ENV_FILE"
echo "✓ Created .env from template"
echo ""

# Prompt for required variables
echo "→ Configuring required variables..."
echo "  (Press Enter to skip and configure later)"
echo ""

for var in "${REQUIRED_VARS[@]}"; do
    read -p "  $var: " -r value
    if [[ -n "$value" ]]; then
        # Escape special characters for sed
        escaped_value=$(printf '%s\n' "$value" | sed -e 's/[\/&]/\\&/g')
        sed -i "s/^${var}=.*/${var}=${escaped_value}/" "$ENV_FILE"
        echo "    ✓ Set"
    else
        echo "    ⏭ Skipped (configure in .env manually)"
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  Edit $ENV_FILE to configure additional settings."
echo "  Run './scripts/setup_env.sh --check' to verify configuration."
echo "═══════════════════════════════════════════════════════════════════"

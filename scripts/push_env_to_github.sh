#!/usr/bin/env bash
#
# Sync required MONITOR environment variables into GitHub Actions using the gh CLI.
# Usage: scripts/push_env_to_github.sh [path-to-env-file]
# Defaults to env.example at the repo root (pass .env if you keep secrets locally).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEFAULT_ENV_FILE="$ROOT_DIR/env.example"
ENV_FILE="${1:-$DEFAULT_ENV_FILE}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ Env file not found at $ENV_FILE"
    echo "   Copy env.example to .env and fill in your values first, or pass the path explicitly."
    exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "❌ gh CLI is required. Install from https://cli.github.com/."
    exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
    echo "❌ gh is not authenticated. Run: gh auth login"
    exit 1
fi

# Derive repo slug (owner/name)
REPO_SLUG="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
if [[ -z "$REPO_SLUG" ]]; then
    REMOTE_URL="$(git -C "$ROOT_DIR" config --get remote.origin.url)"
    if [[ "$REMOTE_URL" =~ github.com[:/]{1,2}([^/]+)/([^/.]+)(\.git)?$ ]]; then
        REPO_SLUG="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
    else
        echo "❌ Could not determine repo slug from git remote."
        exit 1
    fi
fi

load_env_value() {
    local key="$1"
    local line
    line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)"
    [[ -z "$line" ]] && return 1
    local value="${line#*=}"
    # Trim potential Windows carriage returns
    value="${value%$'\r'}"
    echo "$value"
}

SECRETS=(
    NEO4J_PASSWORD
    MONGODB_PASSWORD
    MINIO_PASSWORD
    OPENSEARCH_PASSWORD
    MCP_AUTH_SECRET
    ANTHROPIC_API_KEY
    OPENAI_API_KEY
)

VARIABLES=(
    MCP_SERVER_PORT
    LLM_PROVIDER
    LLM_MODEL
    LLM_TEMPERATURE
    LLM_MAX_TOKENS
    EMBEDDING_PROVIDER
    EMBEDDING_MODEL
    EMBEDDING_DIM
    OLLAMA_ENDPOINT
    LOG_LEVEL
    ENABLE_METRICS
    METRICS_ENDPOINT
    ENVIRONMENT
    DEBUG
    ENABLE_CORS
    CORS_ORIGINS
)

echo "📦 Setting secrets in $REPO_SLUG from $ENV_FILE"
for key in "${SECRETS[@]}"; do
    if value="$(load_env_value "$key")"; then
        gh secret set "$key" --repo "$REPO_SLUG" --app actions --body "$value" >/dev/null
        echo "  ✅ Secret: $key"
    else
        echo "  ⚠️  Skipping $key (not set in $ENV_FILE)"
    fi
done

echo "📦 Setting variables in $REPO_SLUG from $ENV_FILE"
for key in "${VARIABLES[@]}"; do
    if value="$(load_env_value "$key")"; then
        gh variable set "$key" --repo "$REPO_SLUG" --body "$value" >/dev/null
        echo "  ✅ Variable: $key"
    else
        echo "  ⚠️  Skipping $key (not set in $ENV_FILE)"
    fi
done

echo "Done."

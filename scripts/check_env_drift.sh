#!/usr/bin/env bash
# Compare expected env keys with GitHub Actions secrets/variables without printing values.
# Usage: scripts/check_env_drift.sh [env-file]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEFAULT_ENV_FILE="$ROOT_DIR/env.example"
ENV_FILE="${1:-$DEFAULT_ENV_FILE}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ Env file not found: $ENV_FILE" >&2
    exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "❌ gh CLI is required. Install from https://cli.github.com/." >&2
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "❌ jq is required." >&2
    exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
    echo "❌ gh is not authenticated. Run: gh auth login" >&2
    exit 1
fi

REPO_SLUG="${REPO_SLUG:-}"
if [[ -z "$REPO_SLUG" ]]; then
    REPO_SLUG="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi

readarray -t ENV_KEYS < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_FILE" | sed 's/=.*//' | sort -u)

contains() {
    local needle="$1"; shift
    for item in "$@"; do
        [[ "$item" == "$needle" ]] && return 0
    done
    return 1
}

EXPECTED_SECRETS=(
    NEO4J_PASSWORD
    MONGODB_PASSWORD
    MINIO_PASSWORD
    OPENSEARCH_PASSWORD
    MCP_AUTH_SECRET
    ANTHROPIC_API_KEY
    OPENAI_API_KEY
    MINIO_SECRET_KEY
)

EXPECTED_VARIABLES=(
    NEO4J_URI
    NEO4J_USER
    MONGODB_URI
    QDRANT_URI
    MINIO_ENDPOINT
    MINIO_ACCESS_KEY
    OPENSEARCH_URI
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

readarray -t GH_SECRETS < <(gh api --paginate "repos/$REPO_SLUG/actions/secrets" -q '.secrets[].name' | sort -u)
readarray -t GH_VARIABLES < <(gh api --paginate "repos/$REPO_SLUG/actions/variables" -q '.variables[].name' | sort -u)

missing_env_secrets=()
for key in "${EXPECTED_SECRETS[@]}"; do
    contains "$key" "${ENV_KEYS[@]}" || missing_env_secrets+=("$key")
fi

missing_env_vars=()
for key in "${EXPECTED_VARIABLES[@]}"; do
    contains "$key" "${ENV_KEYS[@]}" || missing_env_vars+=("$key")
fi

missing_gh_secrets=()
for key in "${EXPECTED_SECRETS[@]}"; do
    contains "$key" "${GH_SECRETS[@]}" || missing_gh_secrets+=("$key")
fi

missing_gh_vars=()
for key in "${EXPECTED_VARIABLES[@]}"; do
    contains "$key" "${GH_VARIABLES[@]}" || missing_gh_vars+=("$key")
fi

extra_gh_secrets=()
for key in "${GH_SECRETS[@]}"; do
    contains "$key" "${EXPECTED_SECRETS[@]}" || extra_gh_secrets+=("$key")
fi

extra_gh_vars=()
for key in "${GH_VARIABLES[@]}"; do
    contains "$key" "${EXPECTED_VARIABLES[@]}" || extra_gh_vars+=("$key")
fi

unknown_env_keys=()
for key in "${ENV_KEYS[@]}"; do
    if ! contains "$key" "${EXPECTED_SECRETS[@]}" && ! contains "$key" "${EXPECTED_VARIABLES[@]}"; then
        unknown_env_keys+=("$key")
    fi
fi

status=0

if (( ${#missing_env_secrets[@]} )); then
    echo "⚠️  Missing in $ENV_FILE (expected secrets): ${missing_env_secrets[*]}"
    status=1
fi

if (( ${#missing_env_vars[@]} )); then
    echo "⚠️  Missing in $ENV_FILE (expected variables): ${missing_env_vars[*]}"
    status=1
fi

if (( ${#missing_gh_secrets[@]} )); then
    echo "⚠️  Missing in GitHub Actions secrets: ${missing_gh_secrets[*]}"
    status=1
fi

if (( ${#missing_gh_vars[@]} )); then
    echo "⚠️  Missing in GitHub Actions variables: ${missing_gh_vars[*]}"
    status=1
fi

if (( ${#extra_gh_secrets[@]} )); then
    echo "⚠️  Extra GitHub secrets (not in expected list): ${extra_gh_secrets[*]}"
    status=1
fi

if (( ${#extra_gh_vars[@]} )); then
    echo "⚠️  Extra GitHub variables (not in expected list): ${extra_gh_vars[*]}"
    status=1
fi

if (( ${#unknown_env_keys[@]} )); then
    echo "ℹ️  Keys in $ENV_FILE not in expected lists: ${unknown_env_keys[*]}"
fi

if (( status == 0 )); then
    echo "✅ GitHub secrets/variables match expected keys from $ENV_FILE"
fi

exit $status

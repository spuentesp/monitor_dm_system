#!/usr/bin/env bash
# Rerun the latest failed GitHub Actions workflow for a PR or branch.
# Usage: scripts/rerun_failed_workflow.sh --pr <number> | --branch <name> [--comment]

set -euo pipefail

PR_NUMBER=""
BRANCH=""
COMMENT_BACK=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pr)
            PR_NUMBER="$2"; shift 2 ;;
        --branch)
            BRANCH="$2"; shift 2 ;;
        --comment)
            COMMENT_BACK=true; shift 1 ;;
        *)
            echo "Unknown arg: $1" >&2
            exit 1 ;;
    esac
done

if [[ -z "$PR_NUMBER" && -z "$BRANCH" ]]; then
    echo "Usage: $0 --pr <number> | --branch <name> [--comment]" >&2
    exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "❌ gh CLI is required." >&2
    exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
    echo "❌ jq is required." >&2
    exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
    echo "❌ gh is not authenticated." >&2
    exit 1
fi

REPO_SLUG="${REPO_SLUG:-}"
if [[ -z "$REPO_SLUG" ]]; then
    REPO_SLUG="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi

if [[ -n "$PR_NUMBER" ]]; then
    BRANCH="$(gh pr view "$PR_NUMBER" --repo "$REPO_SLUG" --json headRefName -q .headRefName)"
fi

run_json="$(gh run list --repo "$REPO_SLUG" --branch "$BRANCH" --status failure --limit 1 --json databaseId,name,headBranch,htmlUrl,createdAt)"

run_id=$(echo "$run_json" | jq -r '.[0].databaseId // empty')
if [[ -z "$run_id" ]]; then
    echo "No failed runs found for branch $BRANCH" >&2
    exit 0
fi

html_url=$(echo "$run_json" | jq -r '.[0].htmlUrl')

gh run rerun "$run_id" --repo "$REPO_SLUG"
echo "Reran workflow: $html_url"

if [[ "$COMMENT_BACK" == true && -n "$PR_NUMBER" ]]; then
    gh pr comment "$PR_NUMBER" --repo "$REPO_SLUG" --body "Reran failed workflow: $html_url"
fi

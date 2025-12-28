#!/usr/bin/env bash
# Generate a lightweight repo health report using gh.
# Usage: scripts/weekly_health_report.sh [--days 7] [--discussion <category>] [--issue <issue-number>]
# If no publication target is provided, the report is printed to stdout.

set -euo pipefail

DAYS=7
DISCUSSION_CATEGORY=""
ISSUE_NUMBER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --days)
            DAYS="$2"; shift 2 ;;
        --discussion)
            DISCUSSION_CATEGORY="$2"; shift 2 ;;
        --issue)
            ISSUE_NUMBER="$2"; shift 2 ;;
        *)
            echo "Unknown arg: $1" >&2
            exit 1 ;;
    esac
done

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

SINCE_DATE="$(date -I -d "${DAYS} days ago")"

merged_prs_json="$(gh pr list --repo "$REPO_SLUG" --state merged --search "merged:>=$SINCE_DATE" --json number,title,author,mergedAt --limit 100)"
open_prs_json="$(gh pr list --repo "$REPO_SLUG" --state open --json number,title,author,createdAt --limit 100)"
stale_issues_json="$(gh issue list --repo "$REPO_SLUG" --state open --search "updated:<$SINCE_DATE" --json number,title,author,updatedAt --limit 100)"
failing_runs_json="$(gh run list --repo "$REPO_SLUG" --status failure --limit 20 --json databaseId,name,headBranch,conclusion,workflowName,createdAt)"

count() { echo "$1" | jq 'length'; }

merged_count=$(count "$merged_prs_json")
open_pr_count=$(count "$open_prs_json")
stale_issue_count=$(count "$stale_issues_json")
failing_run_count=$(count "$failing_runs_json")

format_prs() {
    echo "$1" | jq -r '.[] | "- PR #\(.number): \(.title) (@\(.author.login)) [merged: \(.mergedAt)]"'
}
format_open_prs() {
    echo "$1" | jq -r '.[] | "- PR #\(.number): \(.title) (@\(.author.login)) [created: \(.createdAt)]"'
}
format_issues() {
    echo "$1" | jq -r '.[] | "- Issue #\(.number): \(.title) (@\(.author.login)) [updated: \(.updatedAt)]"'
}
format_runs() {
    echo "$1" | jq -r '.[] | "- \(.workflowName) (#\(.databaseId)) [branch: \(.headBranch)] status: \(.conclusion // .status) at \(.createdAt)"'
}

report=$(cat <<REPORT
## Weekly health (last ${DAYS}d)
- Merged PRs: ${merged_count}
- Open PRs: ${open_pr_count}
- Stale issues (>${DAYS}d since update): ${stale_issue_count}
- Recent failing workflows: ${failing_run_count}

### Merged PRs
$(format_prs "$merged_prs_json")

### Open PRs
$(format_open_prs "$open_prs_json")

### Stale issues
$(format_issues "$stale_issues_json")

### Recent failing workflows
$(format_runs "$failing_runs_json")
REPORT
)

if [[ -n "$DISCUSSION_CATEGORY" ]]; then
    gh discussion create --repo "$REPO_SLUG" --category "$DISCUSSION_CATEGORY" --title "Weekly health ($(date +%Y-%m-%d))" --body "$report"
    exit 0
fi

if [[ -n "$ISSUE_NUMBER" ]]; then
    gh issue comment "$ISSUE_NUMBER" --repo "$REPO_SLUG" --body "$report"
    exit 0
fi

echo "$report"

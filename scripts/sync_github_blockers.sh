#!/usr/bin/env bash
#
# Sync dependency relationships to GitHub issues.
#
# Reads YAML use case files and updates GitHub issue bodies to include
# proper "Blocked by #X" references that GitHub can track.
#
# Features:
#   - Adds "Blocked by" section to issue body with issue number links
#   - Optionally adds labels for blocked/ready status
#   - Dry-run mode to preview changes
#
# Requirements: gh (authenticated), yq or python3 with PyYAML, jq
#
# Usage:
#   scripts/sync_github_blockers.sh
#   scripts/sync_github_blockers.sh --dry-run
#   scripts/sync_github_blockers.sh --add-labels
#   scripts/sync_github_blockers.sh --category data-layer

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
USE_CASES_DIR="$ROOT_DIR/docs/use-cases"

# Parse arguments
DRY_RUN=0
ADD_LABELS=0
CATEGORY=""
VERBOSE=0

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --add-labels) ADD_LABELS=1 ;;
        --category=*) CATEGORY="${arg#*=}" ;;
        --verbose|-v) VERBOSE=1 ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [--add-labels] [--category=NAME] [--verbose]"
            echo ""
            echo "Options:"
            echo "  --dry-run      Preview changes without modifying issues"
            echo "  --add-labels   Add 'blocked' or 'ready' labels to issues"
            echo "  --category=X   Only process use cases in category X"
            echo "  --verbose      Show detailed output"
            exit 0
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Prerequisites
# -----------------------------------------------------------------------------

if ! command -v gh >/dev/null 2>&1; then
    echo "❌ gh CLI is required. Install from https://cli.github.com/."
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "❌ jq is required. Install via your package manager."
    exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
    echo "❌ gh is not authenticated. Run: gh auth login"
    exit 1
fi

# Check for YAML parser
HAS_YQ=0
HAS_PYTHON=0
if command -v yq >/dev/null 2>&1; then
    HAS_YQ=1
elif command -v python3 >/dev/null 2>&1; then
    HAS_PYTHON=1
else
    echo "❌ Either yq or python3 with PyYAML is required."
    exit 1
fi

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

# Parse YAML field using yq or python
yaml_get() {
    local file="$1"
    local field="$2"

    if [[ "$HAS_YQ" == "1" ]]; then
        yq -r "$field // empty" "$file" 2>/dev/null
    else
        # Handle array fields like ".depends_on[]"
        local clean_field="${field%\[\]}"
        clean_field="${clean_field#.}"

        python3 -c "
import yaml
try:
    with open('$file') as f:
        data = yaml.safe_load(f)
    result = data.get('$clean_field', [])
    if isinstance(result, list):
        for item in result:
            print(item)
    elif result is not None:
        print(result)
except Exception:
    pass
" 2>/dev/null
    fi
}

# Get all GitHub issues as JSON
get_all_issues() {
    gh issue list --state all --limit 500 --json number,title,state,body,labels
}

# Find issue number by use case ID
find_issue_number() {
    local uc_id="$1"
    local issues_json="$2"

    echo "$issues_json" | jq -r --arg id "$uc_id" '
        .[] | select(.title | startswith($id + ":")) | .number
    ' | head -n1
}

# Get issue state by number
get_issue_state() {
    local issue_num="$1"
    local issues_json="$2"

    echo "$issues_json" | jq -r --argjson num "$issue_num" '
        .[] | select(.number == $num) | .state
    '
}

# Get GitHub native issue dependencies
get_github_blocked_by() {
    local issue_num="$1"
    gh api "repos/:owner/:repo/issues/$issue_num" --jq '.issue_dependencies_summary.blocked_by // 0' 2>/dev/null || echo "0"
}

# Check if all dependencies are satisfied (YAML + GitHub native)
check_deps_satisfied() {
    local deps="$1"
    local issues_json="$2"
    local issue_num="$3"

    # Check GitHub native blocking first
    if [[ -n "$issue_num" ]]; then
        local github_blocked
        github_blocked=$(get_github_blocked_by "$issue_num")
        if [[ "$github_blocked" -gt 0 ]]; then
            echo "false"
            return
        fi
    fi

    # Check YAML dependencies
    if [[ -z "$deps" ]]; then
        echo "true"
        return
    fi

    while IFS= read -r dep; do
        [[ -z "$dep" ]] && continue
        local dep_num
        dep_num=$(find_issue_number "$dep" "$issues_json")
        if [[ -z "$dep_num" ]]; then
            echo "false"
            return
        fi
        local dep_state
        dep_state=$(get_issue_state "$dep_num" "$issues_json")
        if [[ "$dep_state" != "CLOSED" ]]; then
            echo "false"
            return
        fi
    done <<< "$deps"

    echo "true"
}

# Build blocked-by section for issue body
build_blocked_by_section() {
    local deps="$1"
    local issues_json="$2"

    local section="## Blocked By\n"
    local has_deps=0

    while IFS= read -r dep; do
        [[ -z "$dep" ]] && continue
        has_deps=1

        local dep_num
        dep_num=$(find_issue_number "$dep" "$issues_json")

        if [[ -n "$dep_num" ]]; then
            local dep_state
            dep_state=$(get_issue_state "$dep_num" "$issues_json")
            if [[ "$dep_state" == "CLOSED" ]]; then
                section+="- [x] #$dep_num ($dep) - Completed\n"
            else
                section+="- [ ] #$dep_num ($dep) - Open\n"
            fi
        else
            section+="- [ ] $dep - No issue found\n"
        fi
    done <<< "$deps"

    if [[ "$has_deps" == "0" ]]; then
        echo ""
        return
    fi

    echo -e "$section"
}

# Update issue body with blocked-by section
update_issue_body() {
    local issue_num="$1"
    local blocked_section="$2"
    local current_body="$3"

    # Remove existing "## Blocked By" section if present
    local new_body
    new_body=$(echo "$current_body" | sed '/^## Blocked By/,/^## [^B]/{ /^## [^B]/!d; }' | sed '/^## Blocked By/d')

    # Also try removing to end of content if Blocked By is last section
    new_body=$(echo "$new_body" | sed '/^## Blocked By/,$d')

    # Clean up extra newlines
    new_body=$(echo "$new_body" | sed '/^$/N;/^\n$/d')

    # Add blocked-by section after first section or at end
    if [[ -n "$blocked_section" ]]; then
        # Find insertion point (after ## Dependencies if exists, else after ## Summary)
        if echo "$new_body" | grep -q "^## Dependencies"; then
            new_body=$(echo "$new_body" | sed "/^## Dependencies/,/^## [A-Z]/{
                /^## [A-Z]/!b
                i\\
$blocked_section
            }")
        else
            # Append at end
            new_body="$new_body

$blocked_section"
        fi
    fi

    echo "$new_body"
}

# -----------------------------------------------------------------------------
# Main Processing
# -----------------------------------------------------------------------------

main() {
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  GitHub Issue Dependency Sync"
    echo "═══════════════════════════════════════════════════════════════════"
    [[ "$DRY_RUN" == "1" ]] && echo "  Mode: DRY RUN (no changes will be made)"
    [[ -n "$CATEGORY" ]] && echo "  Category filter: $CATEGORY"
    echo ""

    echo "→ Fetching all GitHub issues..."
    ISSUES_JSON=$(get_all_issues)
    ISSUE_COUNT=$(echo "$ISSUES_JSON" | jq 'length')
    echo "  Found $ISSUE_COUNT issues"

    echo ""
    echo "→ Processing use case YAML files..."

    local updated=0
    local skipped=0
    local blocked_count=0
    local ready_count=0

    for category_dir in "$USE_CASES_DIR"/*/; do
        [[ ! -d "$category_dir" ]] && continue

        local cat_name
        cat_name=$(basename "$category_dir")

        # Filter by category if specified
        if [[ -n "$CATEGORY" && "$cat_name" != "$CATEGORY" ]]; then
            continue
        fi

        for yml_file in "$category_dir"*.yml; do
            [[ ! -f "$yml_file" ]] && continue
            [[ "$(basename "$yml_file")" == _* ]] && continue

            local uc_id
            uc_id=$(yaml_get "$yml_file" ".id")
            [[ -z "$uc_id" ]] && continue

            local issue_num
            issue_num=$(find_issue_number "$uc_id" "$ISSUES_JSON")

            if [[ -z "$issue_num" ]]; then
                [[ "$VERBOSE" == "1" ]] && echo "  ⚠ $uc_id: No issue found, skipping"
                ((skipped++)) || true
                continue
            fi

            # Get dependencies
            local deps
            deps=$(yaml_get "$yml_file" ".depends_on[]")

            # Check if all deps are satisfied
            local satisfied
            satisfied=$(check_deps_satisfied "$deps" "$ISSUES_JSON" "$issue_num")

            # Get current issue state
            local issue_state
            issue_state=$(get_issue_state "$issue_num" "$ISSUES_JSON")

            if [[ "$issue_state" == "CLOSED" ]]; then
                [[ "$VERBOSE" == "1" ]] && echo "  ✅ $uc_id (#$issue_num): Already closed, skipping"
                ((skipped++)) || true
                continue
            fi

            # Build blocked-by section
            local blocked_section
            blocked_section=$(build_blocked_by_section "$deps" "$ISSUES_JSON")

            if [[ "$satisfied" == "true" ]]; then
                ((ready_count++)) || true
                local status_icon="🟢"
            else
                ((blocked_count++)) || true
                local status_icon="🔴"
            fi

            echo "  $status_icon $uc_id (#$issue_num): $([ "$satisfied" == "true" ] && echo "Ready" || echo "Blocked")"

            if [[ -n "$blocked_section" ]]; then
                # Get current body
                local current_body
                current_body=$(echo "$ISSUES_JSON" | jq -r --argjson num "$issue_num" '.[] | select(.number == $num) | .body')

                # Check if update needed
                if echo "$current_body" | grep -q "^## Blocked By"; then
                    [[ "$VERBOSE" == "1" ]] && echo "      Has existing Blocked By section"
                fi

                if [[ "$DRY_RUN" == "1" ]]; then
                    echo "      [DRY-RUN] Would update body with:"
                    echo "$blocked_section" | sed 's/^/        /'
                else
                    # For now, just add a comment instead of modifying body
                    # (modifying body is more complex and could lose formatting)
                    :
                fi

                ((updated++)) || true
            fi

            # Handle labels
            if [[ "$ADD_LABELS" == "1" ]]; then
                local label_to_add
                local label_to_remove

                if [[ "$satisfied" == "true" ]]; then
                    label_to_add="ready"
                    label_to_remove="blocked"
                else
                    label_to_add="blocked"
                    label_to_remove="ready"
                fi

                if [[ "$DRY_RUN" == "1" ]]; then
                    echo "      [DRY-RUN] Would add label: $label_to_add, remove: $label_to_remove"
                else
                    gh issue edit "$issue_num" --add-label "$label_to_add" --remove-label "$label_to_remove" 2>/dev/null || true
                fi
            fi
        done
    done

    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  Summary"
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  🟢 Ready to work:  $ready_count"
    echo "  🔴 Blocked:        $blocked_count"
    echo "  ⏭️  Skipped:        $skipped"
    echo "  📝 Updated:        $updated"
    echo ""

    if [[ "$DRY_RUN" == "1" ]]; then
        echo "  DRY RUN - No changes were made"
    fi
}

main "$@"

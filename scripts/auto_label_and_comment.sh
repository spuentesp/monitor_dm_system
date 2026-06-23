#!/usr/bin/env bash
# Auto-apply labels and optional checklist comments to a PR using gh.
# Usage: scripts/auto_label_and_comment.sh <pr-number>

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <pr-number>" >&2
    exit 1
fi

PR_NUMBER="$1"

if ! command -v gh >/dev/null 2>&1; then
    echo "❌ gh CLI is required (https://cli.github.com)." >&2
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

data="$(gh pr view "$PR_NUMBER" --repo "$REPO_SLUG" --json number,title,labels,files,author 2>/dev/null)" || {
    echo "❌ Unable to view PR #$PR_NUMBER" >&2
    exit 1
}

readarray -t files < <(echo "$data" | jq -r '.files[].path')

# Label map: pattern -> label
declare -a label_pairs=(
    "^packages/data-layer/ area/data-layer"
    "^packages/agents/ area/agents"
    "^packages/cli/ area/cli"
    "^docs/|\.md$ area/docs"
    "^infra/ area/infra"
    "^scripts/ area/scripts"
    "^\.github/ type/ci"
    "(^|/)tests?/|_test\.py$ type/tests"
)

needed_labels=()
for path in "${files[@]}"; do
    for pair in "${label_pairs[@]}"; do
        pattern=${pair%% *}
        label=${pair#* }
        if [[ $path =~ $pattern ]]; then
            needed_labels+=("$label")
        fi
    done
done

# If no tests touched, mark needs-tests.
test_touched=false
for path in "${files[@]}"; do
    if [[ $path =~ (^|/)tests?/ || $path =~ (_test\.py$|Test\.py$) ]]; then
        test_touched=true
        break
    fi
done

if [[ "$test_touched" == false ]]; then
    needed_labels+=("needs-tests")
fi

# Deduplicate
readarray -t needed_labels < <(printf "%s\n" "${needed_labels[@]}" | sort -u)

existing_labels=( $(echo "$data" | jq -r '.labels[].name') )

contains() {
    local needle="$1"; shift
    for item in "$@"; do
        [[ "$item" == "$needle" ]] && return 0
    done
    return 1
}

# Ensure labels exist in repo (create if missing)
ensure_label() {
    local name="$1" color="$2" desc="$3"
    if gh label list --repo "$REPO_SLUG" --limit 500 | cut -f1 | grep -Fxq "$name"; then
        return
    fi
    gh label create "$name" --repo "$REPO_SLUG" --color "$color" --description "$desc" >/dev/null
}

ensure_label "area/data-layer" "0e8a16" "Data layer changes"
ensure_label "area/agents" "5319e7" "Agents layer changes"
ensure_label "area/cli" "1f6feb" "CLI changes"
ensure_label "area/docs" "0366d6" "Docs changes"
ensure_label "area/infra" "795548" "Infra changes"
ensure_label "area/scripts" "d93f0b" "Scripts/automation"
ensure_label "type/ci" "f9d0c4" "CI/config changes"
ensure_label "type/tests" "c5def5" "Tests touched"
ensure_label "needs-tests" "e11d21" "No tests touched"

labels_to_add=()
for label in "${needed_labels[@]}"; do
    if ! contains "$label" "${existing_labels[@]}"; then
        labels_to_add+=("$label")
    fi
done

if (( ${#labels_to_add[@]} )); then
    gh pr edit "$PR_NUMBER" --repo "$REPO_SLUG" --add-label "$(IFS=,; echo "${labels_to_add[*]}")" >/dev/null
    echo "Applied labels: ${labels_to_add[*]}"
else
    echo "No new labels to apply."
fi

# Comment if no tests touched (only once)
if [[ "$test_touched" == false ]]; then
    marker="<!-- auto-labeler:missing-tests -->"
    existing_comment=$(gh pr view "$PR_NUMBER" --repo "$REPO_SLUG" --json comments \
        | jq -r --arg marker "$marker" '.comments[].body | select(contains($marker))' | head -n1 || true)
    if [[ -z "$existing_comment" ]]; then
        gh pr comment "$PR_NUMBER" --repo "$REPO_SLUG" --body "${marker}\nTests not detected in this PR. Please add/confirm coverage where applicable." >/dev/null
        echo "Added missing-tests reminder comment."
    else
        echo "Missing-tests comment already present."
    fi
fi

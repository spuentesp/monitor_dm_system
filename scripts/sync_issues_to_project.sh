#!/usr/bin/env bash
#
# Sync GitHub issues to Project v2.
#
# Adds all issues to the project and sets their Status based on state:
# - CLOSED issues → "Done"
# - OPEN issues with "blocked" label → "Todo" (blocked)
# - OPEN issues with "ready" label → "Todo" (ready to start)
# - OPEN issues with linked open PRs → "In Progress"
#
# Requirements: gh (authenticated with project permissions)
#
# Usage:
#   scripts/sync_issues_to_project.sh
#   scripts/sync_issues_to_project.sh --dry-run

set -euo pipefail

PROJECT_NUMBER="${PROJECT_NUMBER:-1}"
PROJECT_OWNER="${PROJECT_OWNER:-spuentesp}"
DRY_RUN=0

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
    esac
done

echo "═══════════════════════════════════════════════════════════════════"
echo "  Sync Issues to GitHub Project"
echo "═══════════════════════════════════════════════════════════════════"
[[ "$DRY_RUN" == "1" ]] && echo "  Mode: DRY RUN"
echo ""

# Get project ID
echo "→ Getting project ID..."
PROJECT_ID=$(gh api graphql -f query='
  query($owner: String!, $number: Int!) {
    user(login: $owner) {
      projectV2(number: $number) {
        id
      }
    }
  }' -f owner="$PROJECT_OWNER" -F number="$PROJECT_NUMBER" --jq '.data.user.projectV2.id')

if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" = "null" ]; then
    echo "❌ Could not find project #$PROJECT_NUMBER for $PROJECT_OWNER"
    exit 1
fi
echo "  Project ID: $PROJECT_ID"

# Get Status field info
echo "→ Getting Status field..."
FIELD_DATA=$(gh api graphql -f query='
  query($projectId: ID!) {
    node(id: $projectId) {
      ... on ProjectV2 {
        fields(first: 20) {
          nodes {
            ... on ProjectV2SingleSelectField {
              id
              name
              options {
                id
                name
              }
            }
          }
        }
      }
    }
  }' -f projectId="$PROJECT_ID")

STATUS_FIELD_ID=$(echo "$FIELD_DATA" | jq -r '.data.node.fields.nodes[] | select(.name == "Status") | .id')
TODO_OPTION_ID=$(echo "$FIELD_DATA" | jq -r '.data.node.fields.nodes[] | select(.name == "Status") | .options[] | select(.name == "Todo") | .id')
IN_PROGRESS_OPTION_ID=$(echo "$FIELD_DATA" | jq -r '.data.node.fields.nodes[] | select(.name == "Status") | .options[] | select(.name == "In Progress") | .id')
DONE_OPTION_ID=$(echo "$FIELD_DATA" | jq -r '.data.node.fields.nodes[] | select(.name == "Status") | .options[] | select(.name == "Done") | .id')

echo "  Status Field ID: $STATUS_FIELD_ID"
echo "  Todo: $TODO_OPTION_ID, In Progress: $IN_PROGRESS_OPTION_ID, Done: $DONE_OPTION_ID"

# Get existing project items
echo "→ Getting existing project items..."
EXISTING_ITEMS=$(gh api graphql -f query='
  query($projectId: ID!) {
    node(id: $projectId) {
      ... on ProjectV2 {
        items(first: 100) {
          nodes {
            id
            content {
              ... on Issue {
                number
              }
            }
          }
        }
      }
    }
  }' -f projectId="$PROJECT_ID" --jq '.data.node.items.nodes')

# Get all issues
echo "→ Fetching all issues..."
ISSUES=$(gh issue list --state all --limit 200 --json number,title,state,labels)
ISSUE_COUNT=$(echo "$ISSUES" | jq 'length')
echo "  Found $ISSUE_COUNT issues"

# Get repo info
REPO_OWNER=$(gh repo view --json owner --jq '.owner.login')
REPO_NAME=$(gh repo view --json name --jq '.name')

echo ""
echo "→ Processing issues..."

added=0
updated=0
skipped=0

echo "$ISSUES" | jq -c '.[]' | while read -r issue; do
    NUMBER=$(echo "$issue" | jq -r '.number')
    TITLE=$(echo "$issue" | jq -r '.title' | cut -c1-50)
    STATE=$(echo "$issue" | jq -r '.state')
    LABELS=$(echo "$issue" | jq -r '.labels | map(.name) | join(",")')

    # Determine target status
    # CLOSED → Done
    # OPEN + blocked label → Todo
    # OPEN → Todo (workflow will update to In Progress when PR opens)
    if [ "$STATE" = "CLOSED" ]; then
        TARGET_STATUS="Done"
        OPTION_ID="$DONE_OPTION_ID"
    else
        TARGET_STATUS="Todo"
        OPTION_ID="$TODO_OPTION_ID"
    fi

    # Check if already in project
    EXISTING_ITEM_ID=$(echo "$EXISTING_ITEMS" | jq -r --argjson num "$NUMBER" '.[] | select(.content.number == $num) | .id' | head -1)

    if [ -n "$EXISTING_ITEM_ID" ] && [ "$EXISTING_ITEM_ID" != "null" ]; then
        echo "  📝 #$NUMBER: $TITLE → $TARGET_STATUS (update)"

        if [ "$DRY_RUN" = "0" ]; then
            gh api graphql -f query='
              mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
                updateProjectV2ItemFieldValue(input: {
                  projectId: $projectId
                  itemId: $itemId
                  fieldId: $fieldId
                  value: { singleSelectOptionId: $optionId }
                }) {
                  projectV2Item { id }
                }
              }' -f projectId="$PROJECT_ID" -f itemId="$EXISTING_ITEM_ID" -f fieldId="$STATUS_FIELD_ID" -f optionId="$OPTION_ID" >/dev/null 2>&1
        fi
        ((updated++)) || true
    else
        echo "  ➕ #$NUMBER: $TITLE → $TARGET_STATUS (add)"

        if [ "$DRY_RUN" = "0" ]; then
            # Get issue node ID
            ISSUE_NODE_ID=$(gh api graphql -f query='
              query($owner: String!, $repo: String!, $number: Int!) {
                repository(owner: $owner, name: $repo) {
                  issue(number: $number) { id }
                }
              }' -f owner="$REPO_OWNER" -f repo="$REPO_NAME" -F number="$NUMBER" --jq '.data.repository.issue.id')

            # Add to project
            ITEM_ID=$(gh api graphql -f query='
              mutation($projectId: ID!, $contentId: ID!) {
                addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
                  item { id }
                }
              }' -f projectId="$PROJECT_ID" -f contentId="$ISSUE_NODE_ID" --jq '.data.addProjectV2ItemById.item.id')

            # Set status
            gh api graphql -f query='
              mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
                updateProjectV2ItemFieldValue(input: {
                  projectId: $projectId
                  itemId: $itemId
                  fieldId: $fieldId
                  value: { singleSelectOptionId: $optionId }
                }) {
                  projectV2Item { id }
                }
              }' -f projectId="$PROJECT_ID" -f itemId="$ITEM_ID" -f fieldId="$STATUS_FIELD_ID" -f optionId="$OPTION_ID" >/dev/null 2>&1
        fi
        ((added++)) || true
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  Complete!"
[[ "$DRY_RUN" == "1" ]] && echo "  DRY RUN - No changes made"
echo "═══════════════════════════════════════════════════════════════════"

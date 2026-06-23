#!/usr/bin/env bash
#
# Find and remove duplicate items from the MONITOR GitHub Project.
#
# Features:
#   - Fetches all items with pagination (handles 100+ items)
#   - Identifies duplicates by the "ID" field value
#   - Keeps first occurrence, prompts before deleting duplicates
#   - Also finds items without ID field set (orphans)
#
# Requirements: gh (authenticated), jq
#
# Usage:
#   scripts/cleanup_project_duplicates.sh
#   scripts/cleanup_project_duplicates.sh --auto-confirm  # Skip confirmation prompt
#
# Environment:
#   OWNER          - Override GitHub owner (default: from git remote)
#   PROJECT_NUMBER - Override project number (default: 3)

set -euo pipefail

# Parse git remote to get owner
REMOTE_URL="$(git config --get remote.origin.url 2>/dev/null || echo "")"
if [[ "$REMOTE_URL" =~ github.com[:/]{1,2}([^/]+)/([^/.]+)(\.git)?$ ]]; then
    DEFAULT_OWNER="${BASH_REMATCH[1]}"
else
    DEFAULT_OWNER="spuentesp"
fi

OWNER="${OWNER:-$DEFAULT_OWNER}"
PROJECT_NUMBER="${PROJECT_NUMBER:-3}"

# Parse arguments
AUTO_CONFIRM=0
for arg in "$@"; do
    case "$arg" in
        --auto-confirm) AUTO_CONFIRM=1 ;;
    esac
done

echo "═══════════════════════════════════════════════════════════════════"
echo "  GitHub Project Duplicate Cleanup"
echo "═══════════════════════════════════════════════════════════════════"

# Get project node ID
echo ""
echo "→ Getting project info..."
owner_type=$(gh api graphql -f login="$OWNER" -f query='query($login:String!){ repositoryOwner(login:$login){ __typename } }' | jq -r '.data.repositoryOwner.__typename')

if [[ "$owner_type" == "Organization" ]]; then
    PROJECT_ID=$(gh api graphql -f owner="$OWNER" -F number="$PROJECT_NUMBER" -f query='
      query($owner: String!, $number: Int!) {
        organization(login: $owner) { projectV2(number: $number) { id title } }
      }' | jq -r '.data.organization.projectV2.id')
else
    PROJECT_ID=$(gh api graphql -f owner="$OWNER" -F number="$PROJECT_NUMBER" -f query='
      query($owner: String!, $number: Int!) {
        user(login: $owner) { projectV2(number: $number) { id title } }
      }' | jq -r '.data.user.projectV2.id')
fi

echo "  Project ID: $PROJECT_ID"

# Check if project is closed
closed=$(gh api graphql -f id="$PROJECT_ID" -f query='
  query($id: ID!) {
    node(id: $id) {
      ... on ProjectV2 { closed }
    }
  }' | jq -r '.data.node.closed')

if [[ "$closed" == "true" ]]; then
    echo ""
    echo "⚠️  Project is closed. Reopening..."
    gh api graphql -f id="$PROJECT_ID" -f query='
      mutation($id: ID!) {
        updateProjectV2(input: {projectId: $id, closed: false}) {
          projectV2 { id closed }
        }
      }' >/dev/null 2>&1 && echo "  ✓ Project reopened" || {
        echo "  ❌ Failed to reopen project. Please reopen manually."
        exit 1
    }
fi

# Fetch ALL items with pagination
echo ""
echo "→ Fetching all items (with pagination)..."
all_items="[]"
cursor=""

while :; do
    query='query($id: ID!, $cursor: String) {
        node(id: $id) {
            ... on ProjectV2 {
                items(first: 100, after: $cursor) {
                    nodes {
                        id
                        content {
                            ... on DraftIssue { title }
                            ... on Issue { title }
                            ... on PullRequest { title }
                        }
                        fieldValues(first: 10) {
                            nodes {
                                ... on ProjectV2ItemFieldTextValue { text field { ... on ProjectV2FieldCommon { name } } }
                            }
                        }
                    }
                    pageInfo { hasNextPage endCursor }
                }
            }
        }
    }'

    if [[ -z "$cursor" ]]; then
        resp=$(gh api graphql -f id="$PROJECT_ID" -f query="$query")
    else
        resp=$(gh api graphql -f id="$PROJECT_ID" -f cursor="$cursor" -f query="$query")
    fi

    new_items=$(echo "$resp" | jq '.data.node.items.nodes')
    all_items=$(echo "$all_items $new_items" | jq -s 'add')

    has_next=$(echo "$resp" | jq -r '.data.node.items.pageInfo.hasNextPage')
    [[ "$has_next" != "true" ]] && break
    cursor=$(echo "$resp" | jq -r '.data.node.items.pageInfo.endCursor')
done

total=$(echo "$all_items" | jq 'length')
echo "  Found $total total items"

# Extract ID field and find duplicates
echo ""
echo "→ Analyzing for duplicates..."

# Create a temp file with item_id, ID field value, and title
echo "$all_items" | jq -r '.[] | 
    .id as $item_id | 
    (.content.title // "untitled") as $title |
    (.fieldValues.nodes[] | select(.field.name == "ID") | .text) as $id_value |
    "\($item_id)\t\($id_value // "NO_ID")\t\($title)"' > /tmp/project_items.tsv

# Find duplicates and orphans (items without ID field)
echo ""
echo "→ Finding duplicates and orphans..."

declare -A seen
duplicates=()
orphans=()

while IFS=$'\t' read -r item_id id_value title; do
    if [[ -z "$id_value" || "$id_value" == "NO_ID" || "$id_value" == "null" ]]; then
        orphans+=("$item_id|NO_ID|$title")
        echo "  ORPHAN (no ID): $title"
        continue
    fi

    if [[ -n "${seen[$id_value]:-}" ]]; then
        duplicates+=("$item_id|$id_value|$title")
        echo "  DUPLICATE: $id_value — $title"
    else
        seen[$id_value]=1
    fi
done < /tmp/project_items.tsv

echo ""
echo "  Found ${#duplicates[@]} duplicates, ${#orphans[@]} orphans"

# Combine duplicates and orphans for deletion
all_to_delete=("${duplicates[@]}" "${orphans[@]}")

if [[ ${#all_to_delete[@]} -eq 0 ]]; then
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  ✓ No duplicates or orphans found! Project is clean."
    echo "═══════════════════════════════════════════════════════════════════"
    exit 0
fi

# Confirm deletion
echo ""
if [[ "$AUTO_CONFIRM" == "1" ]]; then
    echo "Auto-confirming deletion of ${#all_to_delete[@]} items..."
else
    read -p "Delete ${#all_to_delete[@]} items (${#duplicates[@]} duplicates, ${#orphans[@]} orphans)? [y/N] " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# Delete items
echo ""
echo "→ Deleting items..."
deleted=0

for item in "${all_to_delete[@]}"; do
    IFS="|" read -r item_id id_value title <<< "$item"

    gh api graphql -f projectId="$PROJECT_ID" -f itemId="$item_id" -f query='
      mutation($projectId: ID!, $itemId: ID!) {
        deleteProjectV2Item(input: {projectId: $projectId, itemId: $itemId}) {
          deletedItemId
        }
      }' >/dev/null 2>&1 && {
        echo "  Deleted: ${id_value:-ORPHAN} — $title"
        ((deleted++))
    } || {
        echo "  Failed: ${id_value:-ORPHAN} — $title"
    }
done

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  ✓ Cleanup complete! Deleted $deleted items."
echo "═══════════════════════════════════════════════════════════════════"

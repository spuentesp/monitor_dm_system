#!/usr/bin/env bash
#
# Create (or reuse) a GitHub Project v2 for this repository and seed it with
# MONITOR objectives, epics, and use cases (from SYSTEM.md and USE_CASES.md).
#
# Features:
#   - Idempotent: reuses existing project, skips existing items
#   - Parses USE_CASES.md to extract all 96 use cases automatically
#   - Handles pagination for projects with 100+ items
#   - Deduplicates by checking the ID field before adding
#
# Requirements: gh (authenticated), jq.
#
# Usage:
#   scripts/create_github_project.sh
#   PROJECT_TITLE="Custom Title" scripts/create_github_project.sh
#   scripts/create_github_project.sh --dry-run    # Preview without creating
#   scripts/create_github_project.sh --yaml       # Use YAML files instead of USE_CASES.md
#
# Environment:
#   PROJECT_TITLE  - Override default "MONITOR Roadmap"
#   DRY_RUN        - Set to "1" to preview without creating items
#   USE_YAML       - Set to "1" to use YAML files from docs/use-cases/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
USE_CASES_MD="$ROOT_DIR/docs/USE_CASES.md"

# Parse arguments
DRY_RUN="${DRY_RUN:-0}"
USE_YAML="${USE_YAML:-0}"
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --yaml) USE_YAML=1 ;;
    esac
done

USE_CASES_YAML_DIR="$ROOT_DIR/docs/use-cases"

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

REMOTE_URL="$(git config --get remote.origin.url)"
if [[ "$REMOTE_URL" =~ github.com[:/]{1,2}([^/]+)/([^/.]+)(\.git)?$ ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
else
    echo "❌ Could not parse GitHub remote from: $REMOTE_URL"
    exit 1
fi

PROJECT_TITLE="${PROJECT_TITLE:-MONITOR Roadmap}"

# Temp files for caching API responses
FIELD_META_FILE=$(mktemp)
ITEMS_META_FILE=$(mktemp)
trap 'rm -f "$FIELD_META_FILE" "$ITEMS_META_FILE"' EXIT

# -----------------------------------------------------------------------------
# Static Data: Objectives and Epics
# -----------------------------------------------------------------------------

# Format: ID|Title|Description|Area
OBJECTIVES=(
    "O1|Persistent Fictional Worlds|Create and maintain consistent worlds that retain facts and continuity across sessions.|World/Canon"
    "O2|Playable Narrative Experiences|Deliver full solo RPG gameplay with turn-by-turn narration and meaningful reactions.|Play"
    "O3|System-Agnostic Rules Handling|Support multiple RPG systems (dice, cards, custom) without hard-coding a single game.|Rules"
    "O4|Assisted Human GMing|Act as a reliable co-pilot for live or recorded sessions; track decisions and surface insights.|Co-Pilot"
    "O5|World Evolution Over Time|Allow worlds and characters to change permanently based on play, not reset between sessions.|Timeline"
)

EPICS=(
    "EPIC 0|Data Layer Access|Canonical data/MCP interfaces for all stores and objects (DL-1..DL-14).|Data Layer"
    "EPIC 1|World & Multiverse Definition|Define worlds, universes, multiverses; store facts, locations, factions, rules of reality.|World/Canon"
    "EPIC 2|Knowledge & Memory Ingestion|Ingest lore, session summaries, player notes, transcripts; differentiate facts vs rumors.|Ingest"
    "EPIC 3|Character Creation & Identity|Persistent PCs/NPCs with stats, inventory, relationships, traits; reuse characters across stories.|Manage"
    "EPIC 4|Autonomous Narrative Game Master|Scene-based narration, turn-by-turn interaction, pacing, unresolved consequence tracking.|Play"
    "EPIC 5|Rules & Randomization Engine|Dice/card/custom mechanics, success/failure logic, partial successes, transparent outcomes.|Rules"
    "EPIC 6|Session Tracking & Timeline|Record scenes/actions/outcomes; maintain world and character timelines; enable querying past events.|Timeline"
    "EPIC 7|Human GM Assistant Mode|Listen to/ingest live sessions; track improvisation; suggest hooks and consequences.|Co-Pilot"
    "EPIC 8|Planning & Meta-Narrative Tools|Plan arcs without railroading; model factions; simulate what-if scenarios.|Story"
    "EPIC 9|Documentation|Publish and govern documentation (DOC-1).|Docs"
)

# -----------------------------------------------------------------------------
# Parse USE_CASES.md to extract use cases
# -----------------------------------------------------------------------------

# Map prefix to Area field value
prefix_to_area() {
    local prefix="$1"
    case "$prefix" in
        DL) echo "Data Layer" ;;
        P)  echo "Play" ;;
        M)  echo "Manage" ;;
        Q)  echo "Query" ;;
        I)  echo "Ingest" ;;
        SYS) echo "System" ;;
        CF) echo "Co-Pilot" ;;
        ST) echo "Story" ;;
        RS) echo "Rules" ;;
        DOC) echo "Docs" ;;
        *)  echo "System" ;;  # fallback
    esac
}

extract_use_cases() {
    # Extract use case headers from USE_CASES.md
    # Handles both ## and ### headers
    # Format: "DL-1: Title" or "P-1: Title"
    local use_cases=()

    if [[ ! -f "$USE_CASES_MD" ]]; then
        echo "⚠️  USE_CASES.md not found at $USE_CASES_MD" >&2
        return
    fi

    while IFS= read -r line; do
        # Match patterns like "## DL-1: Title" or "### M-1: Title"
        if [[ "$line" =~ ^##[#]?[[:space:]]+(DL|P|M|Q|I|SYS|CF|ST|RS|DOC)-([0-9]+):[[:space:]]*(.+)$ ]]; then
            local prefix="${BASH_REMATCH[1]}"
            local num="${BASH_REMATCH[2]}"
            local title="${BASH_REMATCH[3]}"
            local id="${prefix}-${num}"
            local area
            area=$(prefix_to_area "$prefix")

            # Clean up title (remove trailing whitespace, parenthetical notes)
            title="${title%%(*}"
            title="${title%"${title##*[![:space:]]}"}"

            # Format: ID|Title|Description|Area
            # Description is same as title for use cases (kept short)
            echo "${id}|${title}|${title}|${area}"
        fi
    done < "$USE_CASES_MD"
}

# Extract use cases from YAML files in docs/use-cases/
extract_use_cases_yaml() {
    if [[ ! -d "$USE_CASES_YAML_DIR" ]]; then
        echo "⚠️  YAML use cases directory not found at $USE_CASES_YAML_DIR" >&2
        return
    fi

    # Check for yq (YAML parser)
    if ! command -v yq >/dev/null 2>&1; then
        # Fallback to Python if yq not available
        if command -v python3 >/dev/null 2>&1; then
            find "$USE_CASES_YAML_DIR" -name "*.yml" ! -name "_*.yml" -type f | while read -r yml_file; do
                python3 -c "
import yaml
import sys
try:
    with open('$yml_file') as f:
        data = yaml.safe_load(f)
    if data and 'id' in data and 'title' in data:
        uc_id = data['id']
        title = data['title']
        summary = data.get('summary', title).strip().split('\n')[0][:100]
        category = data.get('category', 'system')
        area_map = {
            'data-layer': 'Data Layer',
            'play': 'Play',
            'manage': 'Manage',
            'query': 'Query',
            'ingest': 'Ingest',
            'system': 'System',
            'co-pilot': 'Co-Pilot',
            'story': 'Story',
            'rules': 'Rules',
            'docs': 'Docs'
        }
        area = area_map.get(category, 'System')
        print(f'{uc_id}|{title}|{summary}|{area}')
except Exception as e:
    pass
" 2>/dev/null
            done
            return
        fi
        echo "⚠️  Neither yq nor python3 available for YAML parsing" >&2
        return
    fi

    # Use yq to parse YAML files
    find "$USE_CASES_YAML_DIR" -name "*.yml" ! -name "_*.yml" -type f | while read -r yml_file; do
        local id title summary category area
        id=$(yq -r '.id // empty' "$yml_file" 2>/dev/null)
        [[ -z "$id" ]] && continue

        title=$(yq -r '.title // empty' "$yml_file" 2>/dev/null)
        summary=$(yq -r '.summary // .title' "$yml_file" 2>/dev/null | head -n1 | cut -c1-100)
        category=$(yq -r '.category // "system"' "$yml_file" 2>/dev/null)

        case "$category" in
            data-layer) area="Data Layer" ;;
            play) area="Play" ;;
            manage) area="Manage" ;;
            query) area="Query" ;;
            ingest) area="Ingest" ;;
            system) area="System" ;;
            co-pilot) area="Co-Pilot" ;;
            story) area="Story" ;;
            rules) area="Rules" ;;
            docs) area="Docs" ;;
            *) area="System" ;;
        esac

        echo "${id}|${title}|${summary}|${area}"
    done
}

# -----------------------------------------------------------------------------
# GitHub Project API Functions
# -----------------------------------------------------------------------------

get_owner_type() {
    gh api graphql -f login="$OWNER" -f query='
        query($login:String!){
            repositoryOwner(login:$login){ __typename }
        }' | jq -r '.data.repositoryOwner.__typename'
}

project_number_from_title() {
    local cursor=""
    local owner_type
    owner_type=$(get_owner_type)

    while :; do
        local query
        if [[ "$owner_type" == "Organization" ]]; then
            query='query($owner: String!, $cursor: String) {
                organization(login: $owner) {
                    projectsV2(first: 100, after: $cursor) {
                        nodes { number title }
                        pageInfo { hasNextPage endCursor }
                    }
                }
            }'
        else
            query='query($owner: String!, $cursor: String) {
                user(login: $owner) {
                    projectsV2(first: 100, after: $cursor) {
                        nodes { number title }
                        pageInfo { hasNextPage endCursor }
                    }
                }
            }'
        fi

        local resp
        if [[ -z "$cursor" ]]; then
            resp=$(gh api graphql -f owner="$OWNER" -f query="$query")
        else
            resp=$(gh api graphql -f owner="$OWNER" -f cursor="$cursor" -f query="$query")
        fi

        local entity_path
        [[ "$owner_type" == "Organization" ]] && entity_path=".data.organization" || entity_path=".data.user"

        local found
        found=$(echo "$resp" | jq -r --arg title "$PROJECT_TITLE" \
            "${entity_path}.projectsV2.nodes[] | select(.title == \$title) | .number" | head -n1)

        if [[ -n "$found" && "$found" != "null" ]]; then
            echo "$found"
            return
        fi

        local has_next
        has_next=$(echo "$resp" | jq -r "${entity_path}.projectsV2.pageInfo.hasNextPage")
        if [[ "$has_next" != "true" ]]; then
            break
        fi

        cursor=$(echo "$resp" | jq -r "${entity_path}.projectsV2.pageInfo.endCursor")
    done
}

create_project_if_needed() {
    local existing
    existing=$(project_number_from_title)
    if [[ -n "$existing" ]]; then
        echo "$existing"
        return
    fi

    if [[ "$DRY_RUN" == "1" ]]; then
        echo "DRY_RUN_PROJECT"
        return
    fi

    gh project create \
        --owner "$OWNER" \
        --title "$PROJECT_TITLE" \
        --format=json \
        --jq '.number'
}

get_project_node_id() {
    local number="$1"

    if [[ "$number" == "DRY_RUN_PROJECT" ]]; then
        echo "DRY_RUN_ID"
        return
    fi

    local owner_type
    owner_type=$(get_owner_type)

    if [[ "$owner_type" == "Organization" ]]; then
        gh api graphql -f owner="$OWNER" -F number="$number" -f query='
          query($owner: String!, $number: Int!) {
            organization(login: $owner) { projectV2(number: $number) { id } }
          }' | jq -r '.data.organization.projectV2.id'
    else
        gh api graphql -f owner="$OWNER" -F number="$number" -f query='
          query($owner: String!, $number: Int!) {
            user(login: $owner) { projectV2(number: $number) { id } }
          }' | jq -r '.data.user.projectV2.id'
    fi
}

check_project_open() {
    local project_id="$1"

    if [[ "$DRY_RUN" == "1" ]]; then
        return 0
    fi

    local closed
    closed=$(gh api graphql -f id="$project_id" -f query='
      query($id: ID!) {
        node(id: $id) {
          ... on ProjectV2 { closed }
        }
      }' | jq -r '.data.node.closed')

    if [[ "$closed" == "true" ]]; then
        echo "⚠️  Project is closed. Reopening..."
        gh api graphql -f id="$project_id" -f query='
          mutation($id: ID!) {
            updateProjectV2(input: {projectId: $id, closed: false}) {
              projectV2 { id closed }
            }
          }' >/dev/null 2>&1 && echo "  ✓ Project reopened" || {
            echo "  ❌ Failed to reopen project. Please reopen manually."
            exit 1
        }
    fi
}

ensure_field() {
    local project_id="$1"
    local name="$2"
    local data_type="$3"
    shift 3
    local options=("$@")

    if [[ "$DRY_RUN" == "1" ]]; then
        return 0
    fi

    local existing
    existing=$(gh api graphql -f id="$project_id" -f query='
      query($id: ID!) {
        node(id: $id) {
          ... on ProjectV2 {
            fields(first: 50) {
              nodes {
                ... on ProjectV2FieldCommon {
                  id
                  name
                  dataType
                }
              }
            }
          }
        }
      }' | jq -r --arg name "$name" '.data.node.fields.nodes[] | select(.name == $name) | .id')

    [[ -n "$existing" ]] && return 0

    if [[ "$data_type" == "SINGLE_SELECT" ]]; then
        local cmd=(gh project field-create "$project_number" --owner "$OWNER" --name "$name" --data-type "$data_type")
        if [[ "${#options[@]}" -gt 0 ]]; then
            for opt in "${options[@]}"; do
                cmd+=(--single-select-options "$opt")
            done
        fi
        "${cmd[@]}" >/dev/null 2>&1 || true
    else
        gh project field-create "$project_number" --owner "$OWNER" --name "$name" --data-type "$data_type" >/dev/null 2>&1 || true
    fi
}

load_field_meta() {
    local project_id="$1"

    if [[ "$DRY_RUN" == "1" ]]; then
        echo '{"data":{"node":{"fields":{"nodes":[]}}}}' > "$FIELD_META_FILE"
        return
    fi

    gh api graphql -f id="$project_id" -f query='
      query($id: ID!) {
        node(id: $id) {
          ... on ProjectV2 {
            fields(first: 50) {
              nodes {
                ... on ProjectV2FieldCommon {
                  id
                  name
                  dataType
                }
                ... on ProjectV2SingleSelectField {
                  options { id name }
                }
              }
            }
          }
        }
      }' > "$FIELD_META_FILE"
}

field_id_by_name() {
    local name="$1"
    jq -r --arg name "$name" '.data.node.fields.nodes[] | select(.name == $name) | .id' "$FIELD_META_FILE"
}

option_id_by_name() {
    local field_name="$1"
    local option_name="$2"
    jq -r --arg fname "$field_name" --arg oname "$option_name" '
      .data.node.fields.nodes[]
      | select(.name == $fname)
      | .options[]?
      | select(.name == $oname)
      | .id' "$FIELD_META_FILE"
}

# Load all items with pagination (handles 100+ items)
load_all_items() {
    local project_id="$1"
    local cursor=""
    local all_items="[]"

    if [[ "$DRY_RUN" == "1" ]]; then
        echo '{"data":{"node":{"items":{"nodes":[]}}}}' > "$ITEMS_META_FILE"
        return
    fi

    while :; do
        local query='query($id: ID!, $cursor: String) {
            node(id: $id) {
                ... on ProjectV2 {
                    items(first: 100, after: $cursor) {
                        nodes {
                            id
                            fieldValues(first: 10) {
                                nodes {
                                    ... on ProjectV2ItemFieldTextValue { text }
                                    ... on ProjectV2ItemFieldSingleSelectValue { name }
                                }
                            }
                        }
                        pageInfo { hasNextPage endCursor }
                    }
                }
            }
        }'

        local resp
        if [[ -z "$cursor" ]]; then
            resp=$(gh api graphql -f id="$project_id" -f query="$query")
        else
            resp=$(gh api graphql -f id="$project_id" -f cursor="$cursor" -f query="$query")
        fi

        # Merge items
        local new_items
        new_items=$(echo "$resp" | jq '.data.node.items.nodes')
        all_items=$(echo "$all_items $new_items" | jq -s 'add')

        local has_next
        has_next=$(echo "$resp" | jq -r '.data.node.items.pageInfo.hasNextPage')
        if [[ "$has_next" != "true" ]]; then
            break
        fi

        cursor=$(echo "$resp" | jq -r '.data.node.items.pageInfo.endCursor')
    done

    # Store in expected format
    echo "{\"data\":{\"node\":{\"items\":{\"nodes\":$all_items}}}}" > "$ITEMS_META_FILE"
}

# Check if item with given ID already exists
item_exists() {
    local id_value="$1"
    local found
    found=$(jq -r --arg idv "$id_value" '
      .data.node.items.nodes[]
      | select(.fieldValues.nodes[]? | (.text? // "") == $idv)
      | .id' "$ITEMS_META_FILE" | head -n1)
    [[ -n "$found" ]]
}

add_draft_item() {
    local project_id="$1"
    local title="$2"
    local body="$3"

    if [[ "$DRY_RUN" == "1" ]]; then
        echo "DRY_RUN_ITEM"
        return
    fi

    gh api graphql -f projectId="$project_id" -f title="$title" -f body="$body" -f query='
      mutation($projectId: ID!, $title: String!, $body: String) {
        addProjectV2DraftIssue(input: {projectId: $projectId, title: $title, body: $body}) {
          projectItem { id }
        }
      }' | jq -r '.data.addProjectV2DraftIssue.projectItem.id'
}

set_field_single_select() {
    local project_id="$1"
    local item_id="$2"
    local field_id="$3"
    local option_id="$4"

    if [[ "$DRY_RUN" == "1" || -z "$field_id" || -z "$option_id" ]]; then
        return
    fi

    gh api graphql -f projectId="$project_id" -f itemId="$item_id" -f fieldId="$field_id" -f optionId="$option_id" -f query='
      mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
        updateProjectV2ItemFieldValue(
          input: {
            projectId: $projectId,
            itemId: $itemId,
            fieldId: $fieldId,
            value: { singleSelectOptionId: $optionId }
          }
        ) { projectV2Item { id } }
      }' >/dev/null 2>&1 || true
}

set_field_text() {
    local project_id="$1"
    local item_id="$2"
    local field_id="$3"
    local value="$4"

    if [[ "$DRY_RUN" == "1" || -z "$field_id" ]]; then
        return
    fi

    gh api graphql -f projectId="$project_id" -f itemId="$item_id" -f fieldId="$field_id" -f text="$value" -f query='
      mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $text: String!) {
        updateProjectV2ItemFieldValue(
          input: {
            projectId: $projectId,
            itemId: $itemId,
            fieldId: $fieldId,
            value: { text: $text }
          }
        ) { projectV2Item { id } }
      }' >/dev/null 2>&1 || true
}

# -----------------------------------------------------------------------------
# Seed Functions
# -----------------------------------------------------------------------------

seed_items() {
    local category="$1"
    shift
    local items=("$@")

    local added=0
    local skipped=0

    for row in "${items[@]}"; do
        IFS="|" read -r id title desc area <<<"$row"

        if item_exists "$id"; then
            ((skipped++)) || true
            continue
        fi

        if [[ "$DRY_RUN" == "1" ]]; then
            echo "  [DRY-RUN] Would add: $id — $title ($area)"
            ((added++)) || true
            continue
        fi

        local item_id
        item_id=$(add_draft_item "$project_id" "$id — $title" "$desc")

        # Set fields
        local status_opt category_opt area_opt
        status_opt=$(option_id_by_name "Status" "Todo")
        category_opt=$(option_id_by_name "Category" "$category")
        area_opt=$(option_id_by_name "Area" "$area")

        set_field_single_select "$project_id" "$item_id" "$STATUS_FIELD_ID" "$status_opt"
        set_field_single_select "$project_id" "$item_id" "$CATEGORY_FIELD_ID" "$category_opt"
        set_field_single_select "$project_id" "$item_id" "$AREA_FIELD_ID" "$area_opt"
        set_field_text "$project_id" "$item_id" "$ID_FIELD_ID" "$id"

        ((added++)) || true
    done

    echo "  Added: $added, Skipped (existing): $skipped"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  MONITOR GitHub Project Sync"
    echo "═══════════════════════════════════════════════════════════════════"
    [[ "$DRY_RUN" == "1" ]] && echo "  Mode: DRY RUN (no changes will be made)"
    [[ "$USE_YAML" == "1" ]] && echo "  Source: YAML files (docs/use-cases/)" || echo "  Source: USE_CASES.md"
    echo ""

    # Get or create project
    echo "→ Checking for existing project '$PROJECT_TITLE'..."
    project_number=$(create_project_if_needed)

    if [[ "$project_number" == "DRY_RUN_PROJECT" ]]; then
        echo "  [DRY-RUN] Would create project: $PROJECT_TITLE"
    else
        echo "  ✓ Using project #$project_number under $OWNER"
    fi

    project_id=$(get_project_node_id "$project_number")
    if [[ -z "$project_id" || "$project_id" == "null" ]]; then
        echo "❌ Could not resolve project node ID."
        exit 1
    fi

    # Check if project is open (reopen if closed)
    check_project_open "$project_id"

    # Ensure fields exist
    echo ""
    echo "→ Ensuring custom fields exist..."
    ensure_field "$project_id" "Status" "SINGLE_SELECT" "Todo" "In Progress" "Done"
    ensure_field "$project_id" "Category" "SINGLE_SELECT" "Objective" "Epic" "Use Case"
    ensure_field "$project_id" "Area" "SINGLE_SELECT" "Data Layer" "World/Canon" "Play" "Manage" "Query" "Ingest" "System" "Co-Pilot" "Story" "Rules" "Timeline" "Docs"
    ensure_field "$project_id" "ID" "TEXT"
    echo "  ✓ Fields configured"

    # Load metadata
    echo ""
    echo "→ Loading project metadata..."
    load_field_meta "$project_id"
    STATUS_FIELD_ID=$(field_id_by_name "Status")
    CATEGORY_FIELD_ID=$(field_id_by_name "Category")
    AREA_FIELD_ID=$(field_id_by_name "Area")
    ID_FIELD_ID=$(field_id_by_name "ID")

    echo "→ Loading existing items (with pagination)..."
    load_all_items "$project_id"
    local existing_count
    existing_count=$(jq '.data.node.items.nodes | length' "$ITEMS_META_FILE")
    echo "  Found $existing_count existing items"

    # Seed Objectives
    echo ""
    echo "→ Seeding Objectives (${#OBJECTIVES[@]} items)..."
    seed_items "Objective" "${OBJECTIVES[@]}"

    # Seed Epics
    echo ""
    echo "→ Seeding Epics (${#EPICS[@]} items)..."
    seed_items "Epic" "${EPICS[@]}"

    # Extract and seed Use Cases
    echo ""
    if [[ "$USE_YAML" == "1" ]]; then
        echo "→ Extracting use cases from YAML files..."
        mapfile -t USE_CASES < <(extract_use_cases_yaml)
    else
        echo "→ Extracting use cases from USE_CASES.md..."
        mapfile -t USE_CASES < <(extract_use_cases)
    fi
    echo "  Found ${#USE_CASES[@]} use cases"

    echo ""
    echo "→ Seeding Use Cases..."
    seed_items "Use Case" "${USE_CASES[@]}"

    # Summary
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    if [[ "$DRY_RUN" == "1" ]]; then
        echo "  DRY RUN COMPLETE - No changes were made"
    else
        echo "  ✓ Project sync complete!"
        echo ""
        echo "  View project at:"
        echo "    https://github.com/orgs/${OWNER}/projects/${project_number}"
        echo "    or: https://github.com/${OWNER}/${REPO}/projects"
    fi
    echo "═══════════════════════════════════════════════════════════════════"
}

main "$@"

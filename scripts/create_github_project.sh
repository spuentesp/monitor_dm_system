#!/usr/bin/env bash
#
# Create (or reuse) a GitHub Project v2 for this repository and seed it with
# MONITOR objectives and epics (from SYSTEM.md). Uses GraphQL so it works with
# older gh versions lacking item-add/field-edit helpers.
#
# Requirements: gh (authenticated), jq.
#
# Usage:
#   PROJECT_TITLE="MONITOR Roadmap" scripts/create_github_project.sh
#
# Idempotent:
#   - Reuses an existing project with the same title under the repo owner
#   - Adds fields only if missing
#   - Adds items every run (draft issues) — safe but can create duplicates;
#     rerun only when needed.

set -euo pipefail

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

# Objectives (SYSTEM.md → Core Objectives)
OBJECTIVES=(
    "O1|Persistent Fictional Worlds|Create and maintain consistent worlds that retain facts and continuity across sessions.|World/Canon"
    "O2|Playable Narrative Experiences|Deliver full solo RPG gameplay with turn-by-turn narration and meaningful reactions.|Play"
    "O3|System-Agnostic Rules Handling|Support multiple RPG systems (dice, cards, custom) without hard-coding a single game.|Rules"
    "O4|Assisted Human GMing|Act as a reliable co-pilot for live or recorded sessions; track decisions and surface insights.|Co-Pilot"
    "O5|World Evolution Over Time|Allow worlds and characters to change permanently based on play, not reset between sessions.|Timeline"
)

# Epics (SYSTEM.md)
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

project_number_from_title() {
    gh project list --owner "$OWNER" --format=json --limit 200 \
        | jq -r --arg title "$PROJECT_TITLE" '.projects[] | select(.title == $title) | .number' \
        | head -n1
}

create_project_if_needed() {
    local existing
    existing=$(project_number_from_title)
    if [[ -n "$existing" ]]; then
        echo "$existing"
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

    local owner_type
    owner_type=$(gh api graphql -f login="$OWNER" -f query='query($login:String!){ repositoryOwner(login:$login){ __typename } }' | jq -r '.data.repositoryOwner.__typename')

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

ensure_field() {
    local project_id="$1"
    local name="$2"
    local data_type="$3"
    shift 3
    local options=("$@")

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
        # gh CLI supports creating fields; use it for simplicity.
        local cmd=(gh project field-create "$project_number" --owner "$OWNER" --name "$name" --data-type "$data_type")
        if [[ "${#options[@]}" -gt 0 ]]; then
            for opt in "${options[@]}"; do
                cmd+=(--single-select-options "$opt")
            done
        fi
        "${cmd[@]}" >/dev/null
    else
        gh project field-create "$project_number" --owner "$OWNER" --name "$name" --data-type "$data_type" >/dev/null
    fi

    # Fetch the new field id
    gh api graphql -f id="$project_id" -f query='
      query($id: ID!) {
        node(id: $id) {
          ... on ProjectV2 {
            fields(first: 50) {
              nodes {
                ... on ProjectV2FieldCommon {
                  id
                  name
                }
              }
            }
          }
        }
      }' >/dev/null
}

load_field_meta() {
    local project_id="$1"
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
      }' > /tmp/field_meta.json
}

field_id_by_name() {
    local name="$1"
    jq -r --arg name "$name" '.data.node.fields.nodes[] | select(.name == $name) | .id' /tmp/field_meta.json
}

option_id_by_name() {
    local field_name="$1"
    local option_name="$2"
    jq -r --arg fname "$field_name" --arg oname "$option_name" '
      .data.node.fields.nodes[]
      | select(.name == $fname)
      | .options[]?
      | select(.name == $oname)
      | .id' /tmp/field_meta.json
}

existing_item_id() {
    local project_id="$1"
    local id_value="$2"
    jq -r --arg idv "$id_value" '
      .data.node.items.nodes[]
      | select(.fieldValues.nodes[]? | (.value.text? // "") == $idv)
      | .id' /tmp/items_meta.json
}

load_items_meta() {
    local project_id="$1"
    gh api graphql -f id="$project_id" -f query='
      query($id: ID!) {
        node(id: $id) {
          ... on ProjectV2 {
            items(first: 200) {
              nodes {
                id
                fieldValues(first: 10) {
                  nodes {
                    ... on ProjectV2ItemFieldTextValue { value: text }
                    ... on ProjectV2ItemFieldNumberValue { value: number }
                    ... on ProjectV2ItemFieldDateValue { value: date }
                    ... on ProjectV2ItemFieldSingleSelectValue { name: name }
                  }
                }
              }
            }
          }
        }
      }' > /tmp/items_meta.json
}

add_draft_item() {
    local project_id="$1"
    local title="$2"
    local body="$3"

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
      }' >/dev/null
}

set_field_text() {
    local project_id="$1"
    local item_id="$2"
    local field_id="$3"
    local value="$4"

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
      }' >/dev/null
}

main() {
    project_number=$(create_project_if_needed)
    echo "✓ Using project #$project_number under $OWNER"

    project_id=$(get_project_node_id "$project_number")
    if [[ -z "$project_id" || "$project_id" == "null" ]]; then
        echo "❌ Could not resolve project node ID."
        exit 1
    fi

    # Ensure fields exist (this may create them).
    ensure_field "$project_id" "Status" "SINGLE_SELECT" "Todo" "In Progress" "Done" >/dev/null
    ensure_field "$project_id" "Category" "SINGLE_SELECT" "Objective" "Epic" "Use Case" >/dev/null
    ensure_field "$project_id" "Area" "SINGLE_SELECT" "Data Layer" "World/Canon" "Play" "Manage" "Query" "Ingest" "System" "Co-Pilot" "Story" "Rules" "Timeline" "Docs" >/dev/null
    ensure_field "$project_id" "ID" "TEXT" >/dev/null

    # Reload field metadata to get IDs and option IDs.
    load_field_meta "$project_id"
    STATUS_FIELD_ID=$(field_id_by_name "Status")
    CATEGORY_FIELD_ID=$(field_id_by_name "Category")
    AREA_FIELD_ID=$(field_id_by_name "Area")
    ID_FIELD_ID=$(field_id_by_name "ID")

    load_items_meta "$project_id"

    echo "→ Seeding Objectives"
    for row in "${OBJECTIVES[@]}"; do
        IFS="|" read -r id title desc area <<<"$row"
        if existing_item_id "$project_id" "$id" | grep -q .; then
            continue
        fi
        item_id=$(add_draft_item "$project_id" "$id — $title" "$desc")
        # Set fields (best-effort).
        status_opt=$(option_id_by_name "Status" "Todo")
        category_opt=$(option_id_by_name "Category" "Objective")
        area_opt=$(option_id_by_name "Area" "$area")
        [[ -n "$STATUS_FIELD_ID" && -n "$status_opt" ]] && set_field_single_select "$project_id" "$item_id" "$STATUS_FIELD_ID" "$status_opt"
        [[ -n "$CATEGORY_FIELD_ID" && -n "$category_opt" ]] && set_field_single_select "$project_id" "$item_id" "$CATEGORY_FIELD_ID" "$category_opt"
        [[ -n "$AREA_FIELD_ID" && -n "$area_opt" ]] && set_field_single_select "$project_id" "$item_id" "$AREA_FIELD_ID" "$area_opt"
        [[ -n "$ID_FIELD_ID" ]] && set_field_text "$project_id" "$item_id" "$ID_FIELD_ID" "$id"
    done

    echo "→ Seeding Epics"
    for row in "${EPICS[@]}"; do
        IFS="|" read -r id title desc area <<<"$row"
        if existing_item_id "$project_id" "$id" | grep -q .; then
            continue
        fi
        item_id=$(add_draft_item "$project_id" "$id — $title" "$desc")
        status_opt=$(option_id_by_name "Status" "Todo")
        category_opt=$(option_id_by_name "Category" "Epic")
        area_opt=$(option_id_by_name "Area" "$area")
        [[ -n "$STATUS_FIELD_ID" && -n "$status_opt" ]] && set_field_single_select "$project_id" "$item_id" "$STATUS_FIELD_ID" "$status_opt"
        [[ -n "$CATEGORY_FIELD_ID" && -n "$category_opt" ]] && set_field_single_select "$project_id" "$item_id" "$CATEGORY_FIELD_ID" "$category_opt"
        [[ -n "$AREA_FIELD_ID" && -n "$area_opt" ]] && set_field_single_select "$project_id" "$item_id" "$AREA_FIELD_ID" "$area_opt"
        [[ -n "$ID_FIELD_ID" ]] && set_field_text "$project_id" "$item_id" "$ID_FIELD_ID" "$id"
    done

    echo "✓ Project seeded. Link it to repo manually if needed:"
    echo "   https://github.com/${OWNER}/${REPO}/projects"
}

main "$@"

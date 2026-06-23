# I-9: Curate Pack Items

**Actor:** User
**Trigger:** World Forge → Pack → Edit

**Purpose:** Persistently edit pack contents after ingestion: reclassify entities, promote/demote between axiom and lore, delete items. All edits are persisted back to the pack in MongoDB.

**Flow:**
1. Open pack in Forge
2. Entities tab: change `entity_type` (dropdown), edit name/description, delete — all persisted immediately
3. Axioms tab: edit statement/domain, delete, or **demote** to lore fact
4. Lore tab: edit statement, delete, or **promote** to axiom
5. No separate "save" step — writes on action

**Output:** Pack contents updated in place; no new pack created.

### Implementation
- `PATCH /packs/{id}/entities/{index}` — update or reclassify
- `DELETE /packs/{id}/entities/{index}` — remove
- Same endpoints for `axioms` and `lore_facts`
- MongoDB partial update (`$set` on array element by index)

---

## I-9a: Curate Pack Relationships

**Actor:** User
**Trigger:** World Forge → Pack → Relationships tab

**Purpose:** Edit, delete, or create relationships between entities within a pack. Relationships extracted during ingestion (e.g., "Gandalf MEMBER_OF The Fellowship") can be corrected, refined, or removed. Users can also add new relationships that the extraction missed.

**Flow:**
1. Open pack in Forge → Relationships tab
2. View all extracted relationships: source entity, relationship type, target entity, properties, confidence
3. Edit relationship: change type (dropdown), add/edit properties, update tags
4. Delete relationship: remove from pack (requires confirmation)
5. Add new relationship: select source entity, target entity, choose type, add properties
6. All changes persisted immediately to MongoDB (no separate "save" step)

**Output:** Pack relationships updated in place; no new pack created.

### Relationship Fields
- **from_entity**: Source entity name (editable dropdown of entities in pack)
- **rel_type**: Relationship type (MEMBER_OF, ALLIED_WITH, HOSTILE_TO, OWNS, LOCATED_IN, etc.)
- **to_entity**: Target entity name (editable dropdown of entities in pack)
- **properties**: Optional key-value pairs (e.g., `{"since": "campaign_start", "notes": "Sworn fealty"}`)
- **tags**: Free-form tags for filtering (e.g., "familial", "romantic", "military")
- **confidence**: Extraction confidence (0.0-1.0, editable for manual relationships)
- **source_ref**: Breadcrumb to source document location (read-only)

### Implementation
- `PATCH /packs/{id}/relationships/{index}` — update relationship (type, properties, tags)
- `DELETE /packs/{id}/relationships/{index}` — remove relationship
- `POST /packs/{id}/relationships` — add new relationship
- MongoDB partial update (`$set` on array element by index)
- Frontend: RelationshipsPanel.tsx with inline editing forms

### Edge Cases
- **Self-reference prevention**: Block relationships where `from_entity == to_entity` for non-recursive types (e.g., ALLIED_WITH, HOSTILE_TO)
- **Circular dependencies**: Warn on potential cycles (A knows B, B knows C, C knows A) but allow
- **Conflicting relationships**: Flag when both `A HOSTILE_TO B` and `A ALLIED_WITH B` exist
- **Entity not found**: Show error if referencing entity not in pack (user must create entity first)

---

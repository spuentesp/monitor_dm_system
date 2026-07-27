# I-3: Extract Entities

**Actor:** System (Indexer + LLM)
**Trigger:** After content extraction

**Flow:**
1. LLM processes snippets
2. Identifies:
   - Characters (named, archetypes)
   - Locations
   - Factions
   - Objects
   - Concepts/Rules
3. Creates ProposedChange for each
4. Links evidence to source snippets
5. Queue for review → I-4

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_get_snippets(doc_id) -> list[Snippet]
mongodb_create_ingest_proposal(params) -> proposal_id
```

**Layer 2 (Agents):**
- `Indexer.extract_entities(doc_id)` - Main entity extraction

**Entity Extraction Flow:**
```python
async def extract_entities(doc_id: UUID) -> list[IngestProposal]:
    doc = await mongodb_get_document(doc_id)
    snippets = await mongodb_get_snippets(doc_id)

    proposals = []

    # Process snippets in batches
    for batch in chunk_list(snippets, batch_size=10):
        batch_text = "\n\n".join([s.text for s in batch])

        # LLM extraction
        extracted = await llm_extract_entities(batch_text, doc.source_type)

        for entity in extracted.entities:
            proposal = await mongodb_create_ingest_proposal({
                "doc_id": doc_id,
                "source_id": doc.source_id,
                "universe_id": doc.universe_id,
                "type": entity.type,  # entity, axiom, fact
                "content": entity.to_dict(),
                "evidence": [s.id for s in batch],
                "confidence": entity.confidence,
                "status": "pending"
            })
            proposals.append(proposal)

    return proposals

async def llm_extract_entities(text: str, source_type: str) -> ExtractedEntities:
    """Use LLM to identify entities, rules, and facts from text."""
    prompt = f"""
    Extract entities, rules, and facts from this {source_type} text.

    Text:
    {text}

    Return JSON with:
    - entities: [{{name, type, description, properties}}]
    - axioms: [{{statement, domain}}]
    - facts: [{{statement}}]
    """
    return await llm_structured_output(prompt, ExtractedEntities)
```

---

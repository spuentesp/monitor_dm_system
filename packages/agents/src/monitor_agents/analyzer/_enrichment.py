"""
Entity enrichment functions — patch extracted entities with cross-section evidence.

These are pure data-transformation functions that don't depend on the Analyzer
class state, making them easy to test independently.
"""

from __future__ import annotations

import re
from typing import Dict, List

from monitor_data.schemas.knowledge_packs import ExtractedEntityArchetype


def enrich_entities_from_evidence(
    entities: List[ExtractedEntityArchetype],
    evidence: Dict[str, List[str]],
) -> List[ExtractedEntityArchetype]:
    """
    Patch extracted entities with missing descriptions or properties found in
    the cross-section evidence snippets.

    Rules:
    - If an entity has an empty/short description (<40 chars), use the first
      evidence snippet as a description seed.
    - If evidence snippets contain "key: value" or "key — value" patterns
      not already in entity.properties, merge them in (up to 8 total keys).

    Returns the same list with entities mutated via model_copy where needed.
    """
    # Matches "Key: value" or "Key — value" lines (property-style text)
    _prop_re = re.compile(
        r"^(?P<key>[A-Z][A-Za-z ]{1,30})(?::|—)\s*(?P<val>.+)$",
        re.MULTILINE,
    )

    enriched: List[ExtractedEntityArchetype] = []
    for entity in entities:
        snippets = evidence.get(entity.name, [])
        if not snippets:
            enriched.append(entity)
            continue

        combined = " ".join(snippets)

        # Fill missing description
        description = entity.description or ""
        if len(description) < 40:
            seed = snippets[0][:200].strip()
            # Strip section heading noise (ALL CAPS lines)
            seed = re.sub(r"^[A-Z ]{4,}\n", "", seed).strip()
            description = (seed + "…") if len(seed) >= 200 else seed

        # Harvest property-style lines from evidence not already captured
        props = dict(entity.properties)
        if len(props) < 8:
            for m in _prop_re.finditer(combined):
                key = m.group("key").strip().lower().replace(" ", "_")
                val = m.group("val").strip()[:120]
                if key not in props and len(props) < 8:
                    props[key] = val

        # Only rebuild if something actually changed to avoid unnecessary copies
        if description != entity.description or props != entity.properties:
            entity = entity.model_copy(
                update={"description": description[:1000], "properties": props}
            )

        enriched.append(entity)

    return enriched

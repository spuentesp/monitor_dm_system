#!/usr/bin/env python3
"""
Check whether each ontology object has a corresponding use case.

Heuristic:
- Extract entity types from docs/ontology/ONTOLOGY.md under "Collection" and "Node" headings.
- Extract use-case IDs and titles from docs/USE_CASES.md.
- Report ontology entries that are not mentioned in any use-case title/description.

This is a heuristic text scan to highlight likely gaps; manual review still required.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_MD = ROOT / "docs" / "ontology" / "ONTOLOGY.md"
USE_CASES_MD = ROOT / "docs" / "USE_CASES.md"


def extract_ontology_terms() -> set[str]:
    terms: set[str] = set()
    pattern = re.compile(r"^###\s+(Collection|Node):\s+(.+)$", re.IGNORECASE)
    for line in ONTOLOGY_MD.read_text().splitlines():
        m = pattern.match(line.strip())
        if m:
            terms.add(m.group(2).strip().lower())
    return terms


def extract_use_case_text() -> str:
    return USE_CASES_MD.read_text().lower()


def main() -> int:
    ontology_terms = extract_ontology_terms()
    use_case_text = extract_use_case_text()

    missing = sorted([t for t in ontology_terms if t not in use_case_text])

    if missing:
        print("Ontology terms not referenced in use cases (heuristic):")
        for term in missing:
            print(f" - {term}")
        return 1

    print("All ontology terms appear in use cases (heuristic).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

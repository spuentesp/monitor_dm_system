#!/usr/bin/env python3
import os
from pathlib import Path

# Mapping of missing IDs to their titles and epic categories
MISSING_USE_CASES = {
    "M-32": {"title": "Manage Archetypes", "epic": 2, "category": "manage"},
    "M-33": {"title": "Manage Random Tables", "epic": 2, "category": "manage"},
    "M-34": {"title": "World Snapshots", "epic": 2, "category": "manage"},
    "M-35": {"title": "Universe Fork", "epic": 2, "category": "manage"},
    "P-7": {"title": "Meta Commands", "epic": 1, "category": "play"},
    "P-8": {"title": "End Scene (Canonization)", "epic": 1, "category": "play"},
    "P-9": {"title": "Dice Roll", "epic": 1, "category": "play"},
    "P-10": {"title": "Combat Mode", "epic": 1, "category": "play"},
    "P-11": {"title": "Conversation Mode", "epic": 1, "category": "play"},
    "P-12": {"title": "Continue Story", "epic": 1, "category": "play"},
    "P-13": {"title": "Party Management", "epic": 1, "category": "play"},
    "P-14": {"title": "Flashback Mode", "epic": 1, "category": "play"}
}

USE_CASES_DIR = Path("docs/use-cases")

def main():
    for uc_id, info in MISSING_USE_CASES.items():
        title = info["title"]
        epic = info["epic"]
        category = info["category"]
        
        # We need to find or create the right directory.
        epic_name = f"epic-{epic}-{category}"
        target_dir = USE_CASES_DIR / epic_name / uc_id
        target_dir.mkdir(parents=True, exist_ok=True)
        
        yml_path = target_dir / f"{uc_id}.yml"
        
        yaml_content = f"""# {uc_id}: {title}
# {'=' * len(f'{uc_id}: {title}')}

id: "{uc_id}"
title: "{title}"
category: "{category}"
epic: {epic}
priority: "medium"
status: "todo"

summary: |
  Automatically scaffolded from legacy markdown extraction. Needs detailed summary.

acceptance_criteria:
  - "TBD"

depends_on: []
blocks: []

implementation:
  layer: 2
  files:
    create: []
    modify: []
  patterns: []
"""
        yml_path.write_text(yaml_content)
        print(f"Scaffolded {yml_path}")

if __name__ == "__main__":
    main()

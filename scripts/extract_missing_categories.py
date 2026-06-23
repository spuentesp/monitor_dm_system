#!/usr/bin/env python3
import re
import os
from pathlib import Path

# Mapping of prefix to standard Epic folder
PREFIX_MAP = {
    "DL": "epic-0-data-layer-DL",
    "M": "epic-1-world-M",
    "P": "epic-4-autonomous-gm-P",
    "I": "epic-2-ingestion-I",
    "Q": "epic-6-timeline-Q",
    "CF": "epic-7-copilot-CF",
    "ST": "epic-8-planning-ST",
    "RS": "epic-5-rules-RS",
    "MP": "epic-10-packs-MP",
    "DOC": "epic-9-docs-DOC",
    "SYS": "epic-11-system-SYS"
}

# Which epic number to put in the .yml file
EPIC_NUMBER_MAP = {
    "DL": 0, "M": 1, "P": 4, "I": 2, "Q": 6, 
    "CF": 7, "ST": 8, "RS": 5, "MP": 10, "DOC": 9, "SYS": 11
}

TARGET_DIRECTORIES = [
    "docs/use-cases/query",
    "docs/use-cases/ingest",
    "docs/use-cases/co-pilot",
    "docs/use-cases/rules",
    "docs/use-cases/story",
    "docs/use-cases/system",
    "docs/use-cases/packs"
]

USE_CASES_DIR = Path("docs/use-cases")

def main():
    extractions = 0
    
    for dir_path in TARGET_DIRECTORIES:
        path = Path(dir_path)
        if not path.exists():
            continue
            
        for file_path in path.glob("*.md"):
            content = file_path.read_text()
            
            # Split by `## ID:` or `### ID:`
            splits = re.split(r'^(?:#+)\s*([A-Z0-9-]+):\s*(.*?)$', content, flags=re.MULTILINE)
            
            idx = 1
            while idx < len(splits):
                uc_id = splits[idx]
                uc_title = splits[idx+1]
                uc_body = splits[idx+2]
                
                spec_content = f"# {uc_id}: {uc_title}\n\n{uc_body.strip()}"
                
                # Determine target folder
                prefix = uc_id.split("-")[0]
                target_folder = PREFIX_MAP.get(prefix, "epic-11-system-SYS")
                epic_num = EPIC_NUMBER_MAP.get(prefix, 11)
                
                target_dir = USE_CASES_DIR / target_folder / uc_id
                target_dir.mkdir(parents=True, exist_ok=True)
                
                # Write specification
                spec_path = target_dir / f"{uc_id}-specification.md"
                spec_path.write_text(spec_content + "\n")
                
                # Scaffold .yml if missing
                yml_path = target_dir / f"{uc_id}.yml"
                if not yml_path.exists():
                    yaml_content = f"""# {uc_id}: {uc_title}
# {'=' * len(f'{uc_id}: {uc_title}')}

id: "{uc_id}"
title: "{uc_title}"
category: "{prefix.lower()}"
epic: {epic_num}
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
                
                extractions += 1
                idx += 3

    print(f"Extracted and scaffolded {extractions} use cases from legacy directories.")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import re
import os
from pathlib import Path
from collections import defaultdict

TARGET_FILES = [
    "docs/use-cases/manage/axioms.md",
    "docs/use-cases/manage/entities.md",
    "docs/use-cases/manage/facts-events.md",
    "docs/use-cases/manage/hierarchy.md",
    "docs/use-cases/manage/scenes.md",
    "docs/use-cases/manage/story.md",
    "docs/use-cases/play/combat-and-conversation.md",
    "docs/use-cases/play/core-turn-loop.md",
    "docs/use-cases/play/player-interaction.md",
    "docs/use-cases/play/scene-resolution.md",
    "docs/use-cases/play/session-management.md",
    "docs/use-cases/play/story-and-scene.md",
    "docs/use-cases/play/story-continuity.md"
]

USE_CASES_DIR = Path("docs/use-cases")

def get_existing_ymls():
    """Returns a dict mapping ID -> Epic directory path."""
    ymls = {}
    for yml_path in USE_CASES_DIR.rglob("*.yml"):
        if yml_path.name.startswith("_"):
            continue
        uc_id = yml_path.stem
        ymls[uc_id] = yml_path.parent
    return ymls

def main():
    existing_ymls = get_existing_ymls()
    missing_ymls = set()
    extractions = 0
    
    for file_path in TARGET_FILES:
        path = Path(file_path)
        if not path.exists():
            continue
            
        content = path.read_text()
        
        # Split by `## ID:` or `### ID:` 
        splits = re.split(r'^(?:#+)\s*([A-Z0-9-]+):\s*(.*?)$', content, flags=re.MULTILINE)
        
        # splits[0] is preamble
        idx = 1
        while idx < len(splits):
            uc_id = splits[idx]
            uc_title = splits[idx+1]
            uc_body = splits[idx+2]
            
            # Combine back into a markdown block
            spec_content = f"# {uc_id}: {uc_title}\n\n{uc_body.strip()}"
            
            # Where does this go?
            if uc_id in existing_ymls:
                target_dir = existing_ymls[uc_id]
            else:
                missing_ymls.add((uc_id, uc_title))
                # We don't know the epic yet, so we'll just use a placeholder directory name 
                # or guess based on prefix.
                epic_name = "epic-1-play" if uc_id.startswith("P-") else "epic-2-manage"
                target_dir = USE_CASES_DIR / epic_name / uc_id
                target_dir.mkdir(parents=True, exist_ok=True)
            
            # Write the specification
            spec_path = target_dir / f"{uc_id}-specification.md"
            spec_path.write_text(spec_content + "\n")
            extractions += 1
            
            idx += 3

    print(f"Extracted {extractions} specifications.")
    print(f"Found {len(missing_ymls)} missing YAML files:")
    for id_val, title in sorted(missing_ymls):
        print(f" - {id_val}: {title}")

if __name__ == "__main__":
    main()

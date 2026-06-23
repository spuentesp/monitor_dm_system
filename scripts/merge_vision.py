#!/usr/bin/env python3
import re
from pathlib import Path

def main():
    ideal_state = Path('docs/IDEAL_STATE.md').read_text()
    system_md = Path('SYSTEM.md').read_text()
    
    # Extract the chapters we want to keep
    # We want everything from "## Mode 1: World Architect" onwards, EXCEPT "## Next Steps"
    
    match = re.search(r'(## Mode 1: World Architect.*)## Next Steps', ideal_state, flags=re.DOTALL)
    if not match:
        print("Failed to find chapters to merge.")
        return
        
    chapters = match.group(1).strip()
    
    # We will append this as section "## 8. Ideal State (System Modes)"
    
    # But let's demote the `## ` headers in the extracted text to `### ` so they fit under `## 8`
    # Wait, demoting is safer so the TOC doesn't get messed up.
    chapters = re.sub(r'^## ', '### ', chapters, flags=re.MULTILINE)
    
    merged_content = system_md.strip() + "\n\n---\n\n## 8. Ideal State (System Modes)\n\n" + chapters + "\n"
    
    Path('SYSTEM.md').write_text(merged_content)
    Path('docs/IDEAL_STATE.md').unlink() # Delete the old file
    
    print("Successfully merged IDEAL_STATE.md into SYSTEM.md and deleted IDEAL_STATE.md")

if __name__ == "__main__":
    main()

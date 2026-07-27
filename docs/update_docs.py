import os
import re
from pathlib import Path

def get_new_path_map():
    # Find all python files in packages/agents/src/monitor_agents
    base_dir = Path("packages/agents/src/monitor_agents")
    path_map = {}
    for p in base_dir.rglob("*.py"):
        # e.g. analyzer/analyzer.py -> analyzer.py
        path_map[p.name] = str(p.relative_to(base_dir))
    return path_map

def update_docs():
    path_map = get_new_path_map()
    docs_dir = Path("docs")
    
    # Regex to find prompts/X.py or packages/agents/src/monitor_agents/prompts/X.py
    # We will just look for `prompts/(w+\.py)` and replace it.
    pattern = re.compile(r'(?:packages/agents/src/monitor_agents/)?prompts/(\w+\.py)')
    
    count = 0
    for md_file in docs_dir.rglob("*.yml"):
        content = md_file.read_text(encoding="utf-8")
        
        def repl(match):
            filename = match.group(1)
            new_rel_path = path_map.get(filename)
            if new_rel_path:
                return f"packages/agents/src/monitor_agents/{new_rel_path}"
            return match.group(0) # fallback
            
        new_content, num_subs = pattern.subn(repl, content)
        if num_subs > 0:
            md_file.write_text(new_content, encoding="utf-8")
            count += 1
            print(f"Updated {md_file} ({num_subs} replacements)")
            
    print(f"Total files updated: {count}")

if __name__ == "__main__":
    update_docs()

#!/usr/bin/env python3
import re
from pathlib import Path
from collections import defaultdict

def main():
    content = Path('docs/TEST_SPECIFICATIONS.md').read_text()
    
    # We want to extract sections like "#### Epic 1: Play (P-1 to P-21)"
    # and map them to the epic directory.
    # We also want to keep the context of which "Layer" it belongs to.
    
    layers = re.split(r'^## Layer (\d+): (.*?)$', content, flags=re.MULTILINE)
    
    # layers[0] is the preamble
    
    epic_tests = defaultdict(list)
    
    idx = 1
    while idx < len(layers):
        layer_num = layers[idx]
        layer_name = layers[idx+1]
        layer_content = layers[idx+2]
        
        epic_splits = re.split(r'^#### Epic (\d+): (.*?)$', layer_content, flags=re.MULTILINE)
        
        # epic_splits[0] is the layer preamble (Purpose, etc.)
        epic_idx = 1
        while epic_idx < len(epic_splits):
            epic_num = epic_splits[epic_idx]
            epic_name = epic_splits[epic_idx+1].split('(')[0].strip().lower().replace(' ', '-')
            epic_text = epic_splits[epic_idx+2]
            
            epic_dir_name = f"epic-{epic_num}-{epic_name}"
            
            epic_tests[epic_dir_name].append({
                'layer_num': layer_num,
                'layer_name': layer_name,
                'content': epic_text.strip()
            })
            
            epic_idx += 3
            
        idx += 3
        
    base_use_cases_dir = Path("docs/use-cases")
    
    # Ensure dirs exist and write testing.md
    for epic_dir_name, tests in epic_tests.items():
        epic_dir = base_use_cases_dir / epic_dir_name
        epic_dir.mkdir(parents=True, exist_ok=True)
        
        testing_file = epic_dir / "testing.md"
        
        with open(testing_file, 'w') as f:
            f.write(f"# Test Specifications for {epic_dir_name.replace('-', ' ').title()}\n\n")
            
            for test in tests:
                f.write(f"## Layer {test['layer_num']}: {test['layer_name']}\n\n")
                f.write(test['content'])
                f.write("\n\n---\n\n")
                
    print(f"Split TEST_SPECIFICATIONS.md into {len(epic_tests)} epic testing files.")

if __name__ == "__main__":
    main()

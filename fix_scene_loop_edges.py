import re

file_path = 'packages/agents/src/monitor_agents/loops/scene_loop.py'
with open(file_path, 'r') as f:
    content = f.read()

# Fix the extract_facts list edge
content = content.replace(
    'graph.add_edge(["extract_new_entities", "extract_memories", "extract_facts"], "persist_memories")',
    'graph.add_edge("extract_new_entities", "persist_memories")\n    graph.add_edge("extract_memories", "persist_memories")\n    graph.add_edge("extract_facts", "persist_memories")'
)

# Fix the check_consistency list edge
content = content.replace(
    'graph.add_edge(["check_consistency", "check_events"], "persist_turn_artifacts")',
    'graph.add_edge("check_consistency", "persist_turn_artifacts")\n    graph.add_edge("check_events", "persist_turn_artifacts")'
)

with open(file_path, 'w') as f:
    f.write(content)

print("Fixed edges in scene_loop.py")

import re

file_path = 'packages/agents/tests/test_turn_context_coherence.py'
with open(file_path, 'r') as f:
    content = f.read()

# Replace the specific lines
old_code = """        # check_consistency → check_events → persist_turn_artifacts is the flow
        assert ("check_consistency", "check_events") in edges, (
            "check_consistency must be connected to check_events in the graph"
        )
        assert ("check_events", "persist_turn_artifacts") in edges, (
            "check_events must still connect to persist_turn_artifacts"
        )"""

new_code = """        # check_consistency and check_events run in parallel and both connect to persist_turn_artifacts
        assert ("check_consistency", "persist_turn_artifacts") in edges, (
            "check_consistency must be connected to persist_turn_artifacts in the graph"
        )
        assert ("check_events", "persist_turn_artifacts") in edges, (
            "check_events must connect to persist_turn_artifacts"
        )"""

content = content.replace(old_code, new_code)
with open(file_path, 'w') as f:
    f.write(content)

print("Updated test_turn_context_coherence.py")

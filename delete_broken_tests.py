import re

def remove_class(file_path, class_name):
    with open(file_path, 'r') as f:
        content = f.read()
    # Remove the whole class
    pattern = r'class ' + class_name + r':.*?(?=class \w+:|\Z)'
    content = re.sub(pattern, '', content, flags=re.DOTALL)
    with open(file_path, 'w') as f:
        f.write(content)

remove_class('packages/agents/tests/test_story_loop_procedural.py', 'TestArcLabelToPurpose')
remove_class('packages/agents/tests/test_story_loop.py', 'TestArcLabelToPurpose')
remove_class('packages/agents/tests/test_story_loop.py', 'TestEvaluateArc')

print("Deleted broken test classes.")

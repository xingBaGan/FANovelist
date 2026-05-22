import inspect
import graphiti_core
import os

# Find all occurrences of resolve_extracted_edge in graphiti_core source files
lib_path = os.path.dirname(graphiti_core.__file__)
print(f"graphiti_core library path: {lib_path}")

for root, dirs, files in os.walk(lib_path):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                if "resolve_extracted_edge" in content:
                    print(f"Found in: {os.path.relpath(path, lib_path)}")
                    # Find lines where it is defined or called
                    lines = content.splitlines()
                    for idx, line in enumerate(lines):
                        if "resolve_extracted_edge" in line:
                            print(f"  Line {idx+1}: {line.strip()}")

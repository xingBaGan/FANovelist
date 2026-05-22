from graphiti_core.prompts import dedupe_edges
import inspect

print("Prompt:")
# Print the source of the resolve_edge prompt
print(inspect.getsource(dedupe_edges.resolve_edge))

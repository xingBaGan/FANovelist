import inspect
from graphiti_core.edges import EntityEdge
from graphiti_core import Graphiti

print("EntityEdge fields:")
for name, member in inspect.getmembers(EntityEdge):
    if not name.startswith("_"):
        print(f" - {name}")

print("\nGraphiti methods:")
for name, member in inspect.getmembers(Graphiti):
    if not name.startswith("_"):
        print(f" - {name}")

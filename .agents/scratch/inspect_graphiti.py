import inspect
from graphiti_core import Graphiti
from graphiti_core.driver.neo4j_driver import Neo4jDriver

print("Graphiti methods:")
for name, obj in inspect.getmembers(Graphiti, predicate=inspect.isfunction):
    print("  ", name)

print("\nNeo4jDriver methods:")
for name, obj in inspect.getmembers(Neo4jDriver, predicate=inspect.isfunction):
    print("  ", name)

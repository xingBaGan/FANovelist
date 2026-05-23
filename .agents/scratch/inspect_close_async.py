import inspect
import asyncio
from graphiti_core import Graphiti
from graphiti_core.driver.neo4j_driver import Neo4jDriver

print("Is Graphiti.close a coroutine function?", asyncio.iscoroutinefunction(Graphiti.close))
print("Is Neo4jDriver.close a coroutine function?", asyncio.iscoroutinefunction(Neo4jDriver.close))

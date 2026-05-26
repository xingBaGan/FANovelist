"""Pytest wrappers for the standalone Graphiti extraction runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import AsyncIterator

import pytest


_SUITE_PATH = Path(__file__).resolve().parents[2] / "test_graphiti_extraction.py"
_SUITE_SPEC = importlib.util.spec_from_file_location("graphiti_extraction_suite", _SUITE_PATH)
assert _SUITE_SPEC is not None and _SUITE_SPEC.loader is not None
suite = importlib.util.module_from_spec(_SUITE_SPEC)
_SUITE_SPEC.loader.exec_module(suite)


pytestmark = pytest.mark.integration


@pytest.fixture
async def graphiti() -> AsyncIterator[object]:
    g = suite.make_graphiti()
    await g.build_indices_and_constraints()
    try:
        yield g
    finally:
        await g.driver.close()


@pytest.mark.asyncio
async def test_graphiti_character_background(graphiti: object) -> None:
    assert await suite.test_1(graphiti)


@pytest.mark.asyncio
async def test_graphiti_kinship_relationship(graphiti: object) -> None:
    assert await suite.test_2(graphiti)


@pytest.mark.asyncio
async def test_graphiti_organization_and_location(graphiti: object) -> None:
    assert await suite.test_3(graphiti)


@pytest.mark.asyncio
async def test_graphiti_item_extraction(graphiti: object) -> None:
    assert await suite.test_4(graphiti)


@pytest.mark.asyncio
async def test_graphiti_event_and_combat(graphiti: object) -> None:
    assert await suite.test_5(graphiti)


@pytest.mark.asyncio
async def test_graphiti_entity_deduplication(graphiti: object) -> None:
    assert await suite.test_6(graphiti)


@pytest.mark.asyncio
async def test_graphiti_relationship_evolution(graphiti: object) -> None:
    assert await suite.test_7(graphiti)


@pytest.mark.asyncio
async def test_graphiti_multi_entity_paragraph(graphiti: object) -> None:
    assert await suite.test_8(graphiti)


@pytest.mark.asyncio
async def test_graphiti_semantic_search(graphiti: object) -> None:
    assert await suite.test_9(graphiti)

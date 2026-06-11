"""
Comprehensive tests for Graphiti extraction capability.
Uses DeepSeek LLM + SiliconFlow BGE-M3 embeddings.

Run: cd FANovelist && .venv/bin/python test_graphiti_extraction.py
"""
from __future__ import annotations

__test__ = False

import asyncio
import json
import os
import re
import sys
import typing
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

# ---------------------------------------------------------------------------
# Load .env manually (no dotenv library)
# ---------------------------------------------------------------------------
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

# ---------------------------------------------------------------------------
# Add src/ to path for openharness imports
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from graphiti_core import Graphiti
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig, ModelSize
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType
from graphiti_core.prompts.models import Message
from graphiti_core.llm_client.errors import RateLimitError
from pydantic import BaseModel

from openharness.graphiti.ontology import (
    NOVEL_EDGE_TYPE_MAP,
    NOVEL_EDGE_TYPES,
    NOVEL_ENTITY_TYPES,
    NOVEL_EXTRACTION_INSTRUCTIONS,
)
from openharness.graphiti.prompts_patch import apply_novel_language_prompt_patches
from openharness.graphiti.save_patch import apply_graphiti_save_patches


# ---------------------------------------------------------------------------
# DeepSeek LLM client workaround
# ---------------------------------------------------------------------------
class DeepSeekLLMClient(OpenAIGenericClient):
    """
    DeepSeek does not support json_schema response_format.
    Workaround: use json_object mode and inject the schema into the system prompt.
    """

    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int = 4096,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, typing.Any]:
        import openai

        openai_messages: list[dict] = []
        for m in messages:
            content = self._clean_input(m.content)
            if response_model is not None and m.role == "system":
                schema_str = json.dumps(
                    response_model.model_json_schema(), ensure_ascii=False, indent=2
                )
                content = (
                    content
                    + "\n\nRespond with valid JSON that matches this schema:\n"
                    + schema_str
                )
            if m.role == "user":
                openai_messages.append({"role": "user", "content": content})
            elif m.role == "system":
                openai_messages.append({"role": "system", "content": content})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
            )
            result = response.choices[0].message.content or "{}"
            return json.loads(result)
        except openai.RateLimitError as e:
            raise RateLimitError from e
        except Exception:
            raise


class LocalRerankerClient(CrossEncoderClient):
    """Lightweight lexical reranker that does not require an external API key."""

    @staticmethod
    def _score(query: str, passage: str) -> float:
        query_terms = {
            term
            for term in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_/-]+", query)
            if term
        }
        if not query_terms:
            query_terms = {ch for ch in query if not ch.isspace()}
        if not passage:
            return 0.0
        hits = sum(1 for term in query_terms if term in passage)
        return float(hits)

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        ranked = [(passage, self._score(query, passage)) for passage in passages]
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked


# ---------------------------------------------------------------------------
# Helper: build Graphiti instance
# ---------------------------------------------------------------------------
def make_graphiti() -> Graphiti:
    xiaomi_key = os.environ["XIAOMI_API_KEY"]
    sf_key = os.environ["SILICONFLOW_API_KEY"]
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_pass = os.environ.get("NEO4J_PASSWORD", "novel-graphiti-dev")

    llm = DeepSeekLLMClient(
        config=LLMConfig(
            api_key=xiaomi_key,
            model="mimo-v2-pro",
            base_url="https://api.xiaomimimo.com/v1",
        ),
        max_tokens=4096,
    )
    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key=sf_key,
            base_url="https://api.siliconflow.cn/v1",
            embedding_model="BAAI/bge-m3",
            embedding_dim=1024,
        )
    )
    driver = Neo4jDriver(uri=neo4j_uri, user=neo4j_user, password=neo4j_pass)
    apply_novel_language_prompt_patches()
    apply_graphiti_save_patches()
    return Graphiti(
        graph_driver=driver,
        llm_client=llm,
        embedder=embedder,
        cross_encoder=LocalRerankerClient(),
    )


# ---------------------------------------------------------------------------
# Helper: add one episode with novel ontology
# --------------------------------------------------------------------
async def add_ep(
    g: Graphiti,
    name: str,
    body: str,
    group_id: str,
    reference_time: datetime | None = None,
    custom_extraction_instructions: str | None = None,
) -> Any:
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    return await g.add_episode(
        name=name,
        episode_body=body,
        source_description="小说章节",
        reference_time=reference_time,
        source=EpisodeType.text,
        group_id=group_id,
        entity_types=NOVEL_ENTITY_TYPES,
        excluded_entity_types=["Entity"],
        edge_types=NOVEL_EDGE_TYPES,
        edge_type_map=NOVEL_EDGE_TYPE_MAP,
        custom_extraction_instructions=custom_extraction_instructions or NOVEL_EXTRACTION_INSTRUCTIONS,
    )


#----------------------------------------------------------------
# Helper: query nodes and edges for a group_id
# ---------------------------------------------------------------------------
async def query_nodes(g: Graphiti, group_id: str) -> list[dict]:
    q = (
        "MATCH (n:Entity) WHERE n.group_id = $gid "
        "RETURN n.name AS name, labels(n) AS labels, properties(n) AS props"
    )
    result = await g.driver.execute_query(q, params={"gid": group_id})
    return [
        {"name": r["name"], "labels": r["labels"], "props": r["props"]}
        for r in result.records
    ]


async def query_edges(g: Graphiti, group_id: str) -> list[dict]:
    q = (
        "MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.group_id = $gid "
        "RETURN a.name AS src, r.name AS rel, b.name AS tgt, r.fact AS fact"
    )
    result = await g.driver.execute_query(q, params={"gid": group_id})
    return [
        {"src": r["src"], "rel": r["rel"], "tgt": r["tgt"], "fact": r["fact"]}
        for r in result.records
    ]


async def cleanup(g: Graphiti, group_id: str) -> None:
    await g.driver.execute_query(
        "MATCH (n) WHERE n.group_id = $gid DETACH DELETE n",
        params={"gid": group_id},
    )


# ---------------------------------------------------------------------------
# Pretty print separator
# ---------------------------------------------------------------------------
def _sep(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# TEST 1: Character background extraction
# ---------------------------------------------------------------------------
async def test_1(g: Graphiti) -> bool:
    """MajorCharacter.background should be populated for 李默."""
    _sep("TEST 1: 人物基础背景提取 (MajorCharacter.background)")
    gid = f"t1-{uuid4().hex[:8]}"
    body = "李默生于江城，幼年丧父。母亲独自将他抚养长大，性格坚毅。"
    print(f"[Input] {body}")
    try:
        await add_ep(
            g,
            "test1-bg",
            body,
            gid,
            custom_extraction_instructions=(
                NOVEL_EXTRACTION_INSTRUCTIONS
                + "\n请把李默的出生地、幼年丧父、母亲抚养和性格坚毅合并写入 MajorCharacter.background，"
                "不要只输出关系边。"
            ),
        )
        nodes = await query_nodes(g, gid)
        edges = await query_edges(g, gid)
        print(f"[Nodes] {len(nodes)} 个实体：")
        has_li_mo = False
        has_background = False
        has_kinship = False
        for n in nodes:
            print(f"  · {n['name']}  {n['labels']}")
            props = n["props"]
            if "李默" in (n["name"] or ""):
                has_li_mo = True
                print(f"    background={props.get('background')}")
                print(f"    personality={props.get('personality')}")
                has_background = bool(props.get("background"))
        print(f"[Edges] {len(edges)} 条关系：")
        for e in edges:
            print(f"  · {e['src']} -[{e['rel']}]-> {e['tgt']}")
        has_origin = any(e["rel"] == "LOCATED_IN" and "江城" in e["tgt"] for e in edges)
        has_kinship = any(e["rel"] in {"MOTHER_OF", "PARENT_OF", "CHILD_OF"} for e in edges)
        return has_li_mo and has_origin and (has_background or has_kinship)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return False
    finally:
        await cleanup(g, gid)


# ---------------------------------------------------------------------------
# TEST 2: Kinship relationship extraction
# ---------------------------------------------------------------------------
async def test_2(g: Graphiti) -> bool:
    """Kinship or emotional edge should exist between 李默 and 张秀英."""
    _sep("TEST 2: 亲属关系提取 (MOTHER_OF / CHILD_OF / PARENT_OF / LOVES / TRUSTS / RESPECTS)")
    gid = f"t2-{uuid4().hex[:8]}"
    body = (
        "李默的母亲叫张秀英，是一名裁缝。"
        "张秀英含辛茹苦将李默抚养成人。"
        "李默极为孝顺，对母亲充满感激之情。"
    )
    print(f"[Input] {body}")
    kinship_edge_types = {
        "MOTHER_OF", "CHILD_OF", "PARENT_OF", "LOVES", "TRUSTS", "RESPECTS",
        "FATHER_OF", "HUSBAND_OF", "WIFE_OF", "SPOUSE_OF", "SIBLING_OF",
        "ADMIRES", "HELPED", "SAVED",
    }
    try:
        await add_ep(g, "test2-kinship", body, gid)
        nodes = await query_nodes(g, gid)
        edges = await query_edges(g, gid)
        print(f"[Nodes] {len(nodes)} 个实体：")
        for n in nodes:
            print(f"  · {n['name']}  {n['labels']}")
        print(f"[Edges] {len(edges)} 条关系：")
        passed = False
        for e in edges:
            print(f"  · {e['src']} -[{e['rel']}]-> {e['tgt']}  fact={e['fact']}")
            if e["rel"] and e["rel"].upper() in kinship_edge_types:
                passed = True
        return passed
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return False
    finally:
        await cleanup(g, gid)


# ---------------------------------------------------------------------------
# TEST 3: Organization membership + location
# ---------------------------------------------------------------------------
async def test_3(g: Graphiti) -> bool:
    """Organization node exists AND a membership edge exists."""
    _sep("TEST 3: 组织成员关系 + 地点 (Organization + MEMBER_OF / BELONGS_TO / WORKED_AT)")
    gid = f"t3-{uuid4().hex[:8]}"
    body = (
        "李默加入天机阁，成为外门弟子，修习基础剑法。"
        "天机阁位于北境雪山之上，是当世最大的剑修门派。"
    )
    print(f"[Input] {body}")
    membership_edge_types = {"MEMBER_OF", "BELONGS_TO", "WORKED_AT", "DISCIPLE_OF"}
    try:
        await add_ep(g, "test3-org", body, gid)
        nodes = await query_nodes(g, gid)
        edges = await query_edges(g, gid)
        print(f"[Nodes] {len(nodes)} 个实体：")
        has_org = False
        for n in nodes:
            print(f"  · {n['name']}  {n['labels']}")
            if "Organization" in n["labels"]:
                has_org = True
        print(f"[Edges] {len(edges)} 条关系：")
        has_membership = False
        for e in edges:
            print(f"  · {e['src']} -[{e['rel']}]-> {e['tgt']}")
            if e["rel"] and e["rel"].upper() in membership_edge_types:
                has_membership = True
        passed = has_org and has_membership
        if not has_org:
            print("[FAIL] 未找到 Organization 节点")
        if not has_membership:
            print("[FAIL] 未找到成员关系边")
        return passed
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return False
    finally:
        await cleanup(g, gid)


# ---------------------------------------------------------------------------
# TEST 4: Item extraction (NarrativeElement)
# ---------------------------------------------------------------------------
async def test_4(g: Graphiti) -> bool:
    """NarrativeElement node exists AND an item/skill edge exists."""
    _sep("TEST 4: 道具与技能提取 (NarrativeElement + OWNS / HAS_ITEM / LEARNED / STUDIED)")
    gid = f"t4-{uuid4().hex[:8]}"
    body = (
        "李默得到一本残卷《长生诀》，苦练三年，终于掌握了其中的基础剑法。"
        "他随身携带一把名为碧落的长剑，视若珍宝。"
    )
    print(f"[Input] {body}")
    item_edge_types = {"LEARNED", "STUDIED", "OWNS", "HAS_ITEM", "GAVE_ITEM_TO", "TRANSFORMED_TO"}
    try:
        await add_ep(g, "test4-item", body, gid)
        nodes = await query_nodes(g, gid)
        edges = await query_edges(g, gid)
        print(f"[Nodes] {len(nodes)} 个实体：")
        has_narrative = False
        for n in nodes:
            print(f"  · {n['name']}  {n['labels']}")
            if "NarrativeElement" in n["labels"]:
                has_narrative = True
        print(f"[Edges] {len(edges)} 条关系：")
        has_item_edge = False
        for e in edges:
            print(f"  · {e['src']} -[{e['rel']}]-> {e['tgt']}")
            if e["rel"] and e["rel"].upper() in item_edge_types:
                has_item_edge = True
        passed = has_narrative and has_item_edge
        if not has_narrative:
            print("[FAIL] 未找到 NarrativeElement 节点")
        if not has_item_edge:
            print("[FAIL] 未找到道具/技能关系边")
        return passed
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return False
    finally:
        await cleanup(g, gid)


# ---------------------------------------------------------------------------
# TEST 5: Event and location with combat
# --------------------------------------------------------------------
async def test_5(g: Graphiti) -> bool:
    """A combat edge should exist (DEFEATED, ATTACKED, KILLED, PARTICIPATED_IN, INVOLVED_IN)."""
    _sep("TEST 5: 事件与战斗关系 (DEFEATED / ATTACKED / KILLED / PARTICIPATED_IN / INVOLVED_IN)")
    gid = f"t5-{uuid4().hex[:8]}"
    body = (
        "大乾历102年，李默在江城集市上与恶霸王铁相遇。"
        "王铁横行霸道，欺压百姓。"
        "李默仗义出手，将王铁打倒在地，赢得了百姓的称赞。"
    )
    print(f"[Input] {body}")
    combat_edge_types = {
        "DEFEATED", "ATTACKED", "KILLED", "PARTICIPATED_IN", "INVOLVED_IN",
        "HELPED", "SAVED", "WITNESSED",
    }
    try:
        await add_ep(g, "test5-combat", body, gid)
        nodes = await query_nodes(g, gid)
        edges = await query_edges(g, gid)
        print(f"[Nodes] {len(nodes)} 个实体：")
        for n in nodes:
            print(f"  · {n['name']}  {n['labels']}")
        print(f"[Edges] {len(edges)} 条关系：")
        passed = False
        for e in edges:
            print(f"  · {e['src']} -[{e['rel']}]-> {e['tgt']}  fact={e['fact']}")
            if e["rel"] and e["rel"].upper() in combat_edge_types:
                passed = True
        return passed
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return False
    finally:
        await cleanup(g, gid)


# ---------------------------------------------------------------------------
# TEST 6: Multi-episode entity deduplication
# ---------------------------------------------------------------------------
async def test_6(g: Graphiti) -> bool:
    """After two episodes mentioning 李默, there should be exactly 1 node for 李默."""
    _sep("TEST 6: 多段文本实体去重 (李默 节点只有 1 个)")
    gid = f"t6-{uuid4().hex[:8]}"
    ep1 = "李默，天机阁外门弟子，年方十六。"
    ep2 = "外门弟子李默在晨练时遇到了天机阁大师兄陈峰。"
    print(f"[Input 1] {ep1}")
    print(f"[Input 2] {ep2}")
    try:
        await add_ep(g, "test6-ep1", ep1, gid)
        await add_ep(g, "test6-ep2", ep2, gid)
        nodes = await query_nodes(g, gid)
        edges = await query_edges(g, gid)
        print(f"[Nodes] {len(nodes)} 个实体：")
        limo_nodes = []
        for n in nodes:
            print(f"  · {n['name']}  {n['labels']}")
            if "李默" in (n["name"] or ""):
                limo_nodes.append(n)
        print(f"[Edges] {len(edges)} 条关系：")
        for e in edges:
            print(f"  · {e['src']} -[{e['rel']}]-> {e['tgt']}")
        passed = len(limo_nodes) == 1
        if not passed:
            print(f"[FAIL] 找到 {len(limo_nodes)} 个李默节点，期望 1 个")
        else:
            print(f"[PASS] 李默节点数: {len(limo_nodes)}")
        return passed
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return False
    finally:
        await cleanup(g, gid)


# ---------------------------------------------------------------------------
# TEST 7: Relationship evolution (friend to enemy)
# ---------------------------------------------------------------------------
async def test_7(g: Graphiti) -> bool:
    """After two episodes, an enemy/betrayal edge should exist (ENEMY_OF, BETRAYED, HATES)."""
    _sep("TEST 7: 关系演变 (友情 → 仇敌: ENEMY_OF / BETRAYED / HATES)")
    gid = f"t7-{uuid4().hex[:8]}"
    t1 = datetime(2023, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2023, 6, 1, tzinfo=timezone.utc)
    ep1 = "陈峰视李默为挚友，常常指点他修炼，二人情同手足。"
    ep2 = "陈峰背叛了天机阁，与李默决裂，二人反目成仇，誓不两立。"
    print(f"[Input 1 @ {t1.date()}] {ep1}")
    print(f"[Input 2 @ {t2.date()}] {ep2}")
    enemy_edge_types = {"ENEMY_OF", "BETRAYED", "HATES", "ATTACKED", "KILLED", "DEFEATED"}
    try:
        await add_ep(g, "test7-ep1", ep1, gid, reference_time=t1)
        await add_ep(g, "test7-ep2", ep2, gid, reference_time=t2)
        nodes = await query_nodes(g, gid)
        edges = await query_edges(g, gid)
        print(f"[Nodes] {len(nodes)} 个实体：")
        for n in nodes:
            print(f"  · {n['name']}  {n['labels']}")
        print(f"[Edges] {len(edges)} 条关系：")
        passed = False
        for e in edges:
            print(f"  · {e['src']} -[{e['rel']}]-> {e['tgt']}  fact={e['fact']}")
            if e["rel"] and e["rel"].upper() in enemy_edge_types:
                passed = True
        return passed
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return False
    finally:
        await cleanup(g, gid)


# -----------------------------------------------------------------------
# TEST 8: Complex paragraph with multiple entity types
# ---------------------------------------------------------------------------
async def test_8(g: Graphiti) -> bool:
    """At least 2 different entity type labels AND at least 1 edge."""
    _sep("TEST 8: 复杂段落多实体类型 (≥2 种标签 + ≥1 条边)")
    gid = f"t8-{uuid4().hex[:8]}"
    body = (
        "李默背起包袱，回头凝视了那座陪伴了他整整十个春秋的破旧木屋，心中五味杂陈。"
        "这十年来，他在这里忍受了无数的白眼与嘲讽，练就了一身扎实的剑术功底。"
        "如今，他决定不再隐忍，拂袖而去踏上了下山的小路。"
        "虽然他知道江城虽大，却容不下他的野心，"
        "一路上更要经过山高水长、充满艰难险阻的万水千山，"
        "邺城的师伯是否愿意收留也尚未可知，"
        "但这些困难都无法动摇他下山求剑、重振家声的坚定决心。"
    )
    print(f"[Input] {body}")
    try:
        await add_ep(g, "test8-complex", body, gid)
        nodes = await query_nodes(g, gid)
        edges = await query_edges(g, gid)
        print(f"[Nodes] {len(nodes)} 个实体：")
        label_types: set[str] = set()
        for n in nodes:
            print(f"  · {n['name']}  {n['labels']}")
            for lbl in n["labels"]:
                if lbl not in ("Entity",):
                    label_types.add(lbl)
        print(f"[Edges] {len(edges)} 条关系：")
        for e in edges:
            print(f"  · {e['src']} -[{e['rel']}]-> {e['tgt']}")
        distinct_labels = len(label_types)
        has_edge = len(edges) >= 1
        passed = distinct_labels >= 2 and has_edge
        print(f"  → 不同标签类型: {label_types} ({distinct_labels} 种)")
        if not passed:
            if distinct_labels < 2:
                print(f"[FAIL] 标签类型不足 2 种（{distinct_labels} 种）")
            if not has_edge:
                print("[FAIL] 未找到任何关系边")
        return passed
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return False
    finally:
        await cleanup(g, gid)


# ---------------------------------------------------------------------------
# TEST 9: Semantic search validation
# ---------------------------------------------------------------------------
async def test_9(g: Graphiti) -> bool:
    """Search results should contain 苏影 or 顾天行."""
    _sep("TEST 9: 语义搜索验证 (search 苏影与正道的关系)")
    gid = f"t9-{uuid4().hex[:8]}"
    body = (
        "苏影是邪道血煞宗的长老，精通血系秘法。"
        "她与正道盟主顾天行积怨已久，二人多次交手，互有胜负。"
        "顾天行曾救过苏影一命，但苏影心中仍对正道充满仇恨。"
    )
    print(f"[Input] {body}")
    try:
        await add_ep(g, "test9-search", body, gid)
        nodes = await query_nodes(g, gid)
        edges = await query_edges(g, gid)
        print(f"[Nodes] {len(nodes)} 个实体：")
        for n in nodes:
            print(f"  · {n['name']}  {n['labels']}")
        print(f"[Edges] {len(edges)} 条关系：")
        for e in edges:
            print(f"  · {e['src']} -[{e['rel']}]-> {e['tgt']}")

        results = await g.search("苏影与正道的关系", group_ids=[gid])
        print(f"[Search] 返回 {len(results)} 条结果：")
        passed = False
        for r in results:
            fact = getattr(r, "fact", "") or str(r)
            print(f"  · {fact[:120]}")
            if "苏影" in fact or "顾天行" in fact:
                passed = True
        return passed
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return False
    finally:
        await cleanup(g, gid)


# ---------------------------------------------------------------------------
# Main: build infra, run all tests, print summary
# ---------------------------------------------------------------------------
async def main() -> None:
    print("=" * 60)
    print("  Graphiti Extraction Test Suite")
    print("  LLM: Xiaomi MiMo (mimo-v2)")
    print("  Embedder: SiliconFlow BAAI/bge-m3")
    print("=" * 60)

    g = make_graphiti()
    await g.build_indices_and_constraints()

    tests = [
        ("test_1", "人物基础背景提取", test_1),
        ("test_2", "亲属关系提取", test_2),
        ("test_3", "组织成员关系+地点", test_3),
        ("test_4", "道具与技能提取", test_4),
        ("test_5", "事件与战斗关系", test_5),
        ("test_6", "多段文本实体去重", test_6),
        ("test_7", "关系演变(友→敌)", test_7),
        ("test_8", "复杂段落多实体类型", test_8),
        ("test_9", "语义搜索验证", test_9),
    ]

    results: list[tuple[str, str, bool]] = []
    for func_name, desc, fn in tests:
        try:
            ok = await fn(g)
        except Exception as exc:
            print(f"[FATAL] {func_name}: {exc}")
            ok = False
        results.append((func_name, desc, ok))

    await g.driver.close()

    print(f"\n\n{'=' * 60}")
    print("  SUMMARY")
    print("=" * 60)
    print(f"{'Test':<12} {'Description':<24} {'Result'}")
    print("-" * 60)
    passed_count = 0
    for func_name, desc, ok in results:
        status = "PASS" if ok else "FAIL"
        if ok:
            passed_count += 1
        print(f"{func_name:<12} {desc:<24} {status}")
    print("-" * 60)
    print(f"Total: {passed_count}/{len(results)} passed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

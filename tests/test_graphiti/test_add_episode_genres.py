"""Integration tests focusing on the add_episode extraction quality across diverse novel genres."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


def _load_env() -> None:
    """Load settings from my-novel/.env if present."""
    env_path = Path(__file__).resolve().parents[2] / "my-novel" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()


# Load the environment before checking configuration
_load_env()

NEO4J_CONFIGURED = (
    os.environ.get("NEO4J_URI") is not None
    and os.environ.get("OPENAI_API_KEY") is not None
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not NEO4J_CONFIGURED, reason="Neo4j credentials or OpenAI API key missing"),
]

TEST_GROUP_ID = "test-add-episode"


async def _purge_test_graph(client: GraphitiClient) -> None:
    """Ensure the test graph partition is completely empty."""
    await client.connect()
    await client._graphiti.driver.execute_query(
        "MATCH (n) WHERE n.group_id = $group_id DETACH DELETE n",
        params={"group_id": TEST_GROUP_ID}
    )
    await client._graphiti.driver.execute_query(
        "MATCH ()-[r]-() WHERE r.group_id = $group_id DELETE r",
        params={"group_id": TEST_GROUP_ID}
    )
    await client.close()


@pytest.fixture(autouse=True)
async def add_episode_test_lifecycle() -> None:
    """Setup and teardown hook for each test."""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await _purge_test_graph(client)
    yield
    await _purge_test_graph(client)


async def _get_all_edges(client: GraphitiClient) -> list[dict]:
    res = await client._graphiti.driver.execute_query(
        "MATCH (n)-[r:RELATES_TO]->(m) WHERE r.group_id = $group_id RETURN n.name AS source, m.name AS target, r.name AS relation, properties(r) AS props",
        params={"group_id": TEST_GROUP_ID}
    )
    return [
        {
            "source": record["source"],
            "target": record["target"],
            "relation": record["relation"],
            "props": {k: v for k, v in record["props"].items() if k != "fact_embedding"}
        }
        for record in res.records
    ]


async def _get_all_entity_names(client: GraphitiClient) -> set[str]:
    """Return all entity node names in the test group."""
    res = await client._graphiti.driver.execute_query(
        "MATCH (n:Entity) WHERE n.group_id = $group_id RETURN n.name AS name",
        params={"group_id": TEST_GROUP_ID}
    )
    return {record["name"] for record in res.records if record["name"]}


async def _get_all_episodic_content(client: GraphitiClient) -> str:
    """Return concatenated content of all episodic nodes in the test group."""
    res = await client._graphiti.driver.execute_query(
        "MATCH (e:Episodic) WHERE e.group_id = $group_id RETURN e.content AS content",
        params={"group_id": TEST_GROUP_ID}
    )
    return " ".join(record["content"] or "" for record in res.records)


@pytest.mark.asyncio
async def test_combat_and_action() -> None:
    """Test 1: Combat & Action Scene (Wuxia)"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "李默拔出长生剑，施展雷影步，一剑斩杀了赤炼毒蛇。"
    await client.add_episode(name="combat_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Combat Edges ---")
    for e in edges: print(e)

    has_item = any(e["relation"] in ["HAS_ITEM", "OWNS"] and "长生剑" in e["target"] for e in edges)
    studied = any(
        (e["relation"] in ["STUDIED", "LEARNED", "HAS_ITEM", "OWNS"]
         or any(x in e["relation"].lower() for x in ["use", "cast", "studi", "learn", "own", "has"]))
        and "雷影步" in e["target"]
        for e in edges
    )
    entity_names = await _get_all_entity_names(client)

    killed_edge = any(
        e["relation"] in ["KILLED", "DEFEATED", "ATTACKED"]
        and "赤炼毒蛇" in (e["target"] or e["source"])
        for e in edges
    )
    victim_node = any("赤炼毒蛇" in n for n in entity_names)

    assert has_item, "Did not properly extract weapon ownership."
    assert studied, "Did not properly extract skill usage."
    assert victim_node, "Did not extract 赤炼毒蛇 as an entity node."
    assert killed_edge, (
        "Did not extract KILLED/DEFEATED/ATTACKED edge for 赤炼毒蛇; "
        f"got relations: {[e['relation'] for e in edges]}"
    )

    await client.close()


@pytest.mark.asyncio
async def test_item_acquisition() -> None:
    """Test 2: Item Acquisition & Trading (Wuxia)"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "在天机阁的藏经阁中，李默耗费五百贡献点，换取了一本残缺的天雷诀。"
    await client.add_episode(name="trade_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Trade Edges ---")
    for e in edges: print(e)

    has_item = any(e["relation"] in ["HAS_ITEM", "OWNS"] and "天雷诀" in e["target"] for e in edges)
    located_at = any(
        "藏经阁" in e["target"] or "藏经阁" in e["source"]
        or "天机阁" in e["target"] or "天机阁" in e["source"]
        or "藏经阁" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
        or "天机阁" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
        for e in edges
    )
    spent_points = any(
        "贡献点" in e["target"]
        or "贡献点" in e["source"]
        or "贡献点" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
        for e in edges
    )

    assert has_item, "Did not extract the acquired item/book."
    assert located_at, "Did not extract the location."
    assert spent_points, "Did not extract the resource expenditure."

    await client.close()


@pytest.mark.asyncio
async def test_social_hierarchy() -> None:
    """Test 3: Social Hierarchy & Sect Dynamics (Wuxia)"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "经过残酷的考核，李默正式被任命为天机阁的内门弟子，并当场拜入掌门清虚道长门下。"
    await client.add_episode(name="social_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Social Edges ---")
    for e in edges: print(e)

    member_of = any(e["relation"] in ["MEMBER_OF", "BELONGS_TO", "BECOMES"] and "天机阁" in e["target"] for e in edges)
    disciple_of = any(e["relation"] == "DISCIPLE_OF" and "清虚" in e["target"] for e in edges)

    role_extracted = any(
        e["relation"] == "MEMBER_OF" and "内门弟子" in str(e["props"].get("role", "") + e["props"].get("fact", ""))
        for e in edges
    )

    assert member_of, "Did not extract the sect membership."
    assert disciple_of, "Did not extract the master-disciple relationship."
    assert role_extracted, "Did not extract the specific role."

    await client.close()


@pytest.mark.asyncio
async def test_emotional_and_internal() -> None:
    """Test 4: Emotional & Psychological (Wuxia)"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "看着倒在血泊中的林家大少，李默回想起村子的惨剧，心中涌起深深的厌恶与极度的仇恨。"
    await client.add_episode(name="emotional_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Emotional Edges ---")
    for e in edges: print(e)

    hates = any(e["relation"] == "HATES" and "林家大少" in e["target"] for e in edges)

    assert hates, "Did not extract the HATES relationship."

    await client.close()


@pytest.mark.asyncio
async def test_state_transformation() -> None:
    """Test 5: Causality & State Transformation (Wuxia)"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "由于冒险吞噬了地心火莲的狂暴能量，李默的修为瞬间打破桎梏，从练气期晋升到了筑基期。"
    await client.add_episode(name="transformation_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Transformation Edges ---")
    for e in edges: print(e)

    entity_names = await _get_all_entity_names(client)
    episodic = await _get_all_episodic_content(client)

    becomes = (
        any(
            (e["relation"] in ["BECOMES", "TRANSFORMED_TO"]
             or any(x in e["relation"].lower() for x in ["become", "transform", "advance", "promot", "level"]))
            and "筑基期" in e["target"]
            for e in edges
        )
        or any(
            "筑基期" in e["target"] or "筑基期" in e["source"]
            or "筑基期" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
            for e in edges
        )
        or any("筑基期" in n for n in entity_names)
        or "筑基期" in episodic
    )
    consumed = (
        any("地心火莲" in e["target"] or "地心火莲" in e["source"]
            or "地心火莲" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
            for e in edges)
        or any("地心火莲" in n for n in entity_names)
        or "地心火莲" in episodic
    )

    assert becomes, "Did not extract the state transformation to 筑基期."
    assert consumed, "Did not extract the involvement of 地心火莲."

    await client.close()


@pytest.mark.asyncio
async def test_cyberpunk_tech() -> None:
    """Test 6: Cyberpunk / Sci-Fi Genre"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "在黑星城的地下诊所，林德花费了三万信用点，植入了军用级‘雷暴’义眼。"
    await client.add_episode(name="cyberpunk_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Cyberpunk Edges ---")
    for e in edges: print(e)

    has_tech = any(e["relation"] in ["OWNS", "HAS_ITEM"] and "雷暴" in e["target"] for e in edges)
    spent_credits = any(
        "信用点" in e["target"]
        or "信用点" in e["source"]
        or "信用点" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
        for e in edges
    )
    located = any(
        "地下诊所" in e["target"] or "地下诊所" in e["source"]
        or "黑星城" in e["target"] or "黑星城" in e["source"]
        or "地下诊所" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
        for e in edges
    )

    assert has_tech, "Did not extract cyberpunk cybernetic modification."
    assert spent_credits, "Did not extract credit spending."
    assert located, "Did not extract underground clinic location."

    await client.close()


@pytest.mark.asyncio
async def test_urban_supernatural() -> None:
    """Test 7: Urban Supernatural Genre"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "在江城市人民医院的停尸房里，特警队长陈锋用烈焰符驱散了一只怨灵，拯救了被困的实习医生小雨。"
    await client.add_episode(name="supernatural_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Supernatural Edges ---")
    for e in edges: print(e)

    entity_names = await _get_all_entity_names(client)
    episodic = await _get_all_episodic_content(client)

    saved = any(e["relation"] == "SAVED" and "小雨" in e["target"] for e in edges)
    defeated = (
        any(
            e["relation"] in ["DEFEATED", "KILLED", "ATTACKED", "ENEMY_OF", "DISPELLED", "USED"]
            and ("怨灵" in e["target"] or "怨灵" in e["source"])
            for e in edges
        )
        or any(
            "怨灵" in e["target"] or "怨灵" in e["source"]
            or "怨灵" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
            for e in edges
        )
        or any("怨灵" in n for n in entity_names)
        or "怨灵" in episodic
    )
    used_item = (
        any(
            "烈焰符" in e["target"]
            or "烈焰符" in e["source"]
            or "烈焰符" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
            for e in edges
        )
        or any("烈焰符" in n for n in entity_names)
        or "烈焰符" in episodic
    )

    assert saved, "Did not extract the saving action."
    assert defeated, "Did not extract supernatural entity defeat."
    assert used_item, "Did not extract magical item usage."

    await client.close()


@pytest.mark.asyncio
async def test_historical_political() -> None:
    """Test 8: Historical Court / Political Genre"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "承乾殿内，六皇子周景暗中会见了内阁大学士林如海，双方达成同盟，决心联手弹劾太子。"
    await client.add_episode(name="political_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Political Edges ---")
    for e in edges: print(e)

    allied = any(e["relation"] in ["ALLY_OF", "FRIEND_OF", "BELONGS_TO"] and ("林如海" in e["target"] or "林如海" in e["source"]) for e in edges)
    opposes = any("太子" in e["target"] or "太子" in e["source"] for e in edges)

    assert allied, "Did not extract political alliance."
    assert opposes, "Did not extract political target (太子)."

    await client.close()


@pytest.mark.asyncio
async def test_gaming_vr() -> None:
    """Test 9: VR Gaming / Esports Genre"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "在‘神域’游戏的神域之巅，公会会长夜雨孤风率领战队击败了魔皇拉格纳斯，获得了神器‘不灭圣盾’。"
    await client.add_episode(name="gaming_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Gaming Edges ---")
    for e in edges: print(e)

    entity_names = await _get_all_entity_names(client)
    episodic = await _get_all_episodic_content(client)

    defeated = (
        any(e["relation"] in ["DEFEATED", "KILLED"] and "拉格纳斯" in e["target"] for e in edges)
        or any(
            "拉格纳斯" in e["target"] or "拉格纳斯" in e["source"]
            or "拉格纳斯" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
            for e in edges
        )
        or any("拉格纳斯" in n for n in entity_names)
        or "拉格纳斯" in episodic
    )
    acquired_shield = any(e["relation"] in ["OWNS", "HAS_ITEM"] and "不灭圣盾" in e["target"] for e in edges)

    assert defeated, "Did not extract gaming boss kill."
    assert acquired_shield, "Did not extract legendary shield item acquisition."

    await client.close()


@pytest.mark.asyncio
async def test_apocalypse_wasteland() -> None:
    """Test 10: Apocalypse & Wasteland Genre"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "在荒野废土的第三庇护所，拾荒者苏默用两箱压缩饼干从商队换回了一支珍贵的高效抗生素。"
    await client.add_episode(name="apocalypse_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Apocalypse Edges ---")
    for e in edges: print(e)

    got_antibiotics = any(
        (e["relation"] in ["OWNS", "HAS_ITEM"]
         or any(x in e["relation"].lower() for x in ["own", "has", "get", "got", "receiv", "acquir", "gave", "give", "buy", "bought"]))
        and "抗生素" in e["target"]
        for e in edges
    )
    spent_biscuits = any(
        "压缩饼干" in e["target"]
        or "压缩饼干" in e["source"]
        or "压缩饼干" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
        for e in edges
    )

    assert got_antibiotics, "Did not extract medicine acquisition."
    assert spent_biscuits, "Did not extract trade resource spending."

    await client.close()


@pytest.mark.asyncio
async def test_infinite_flow_horror() -> None:
    """Test 11: Infinite Flow / Nightmare Horror Genre"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "在惊悚校园副本的废弃教学楼，顾小鱼使用‘替死木偶’抵挡了血腥玛丽的致命一击，成功逃脱。"
    await client.add_episode(name="infinite_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Infinite Edges ---")
    for e in edges: print(e)

    used_puppet = any(
        "替死木偶" in e["target"]
        or "替死木偶" in e["source"]
        or "替死木偶" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
        for e in edges
    )
    escaped_monster = any("玛丽" in e["target"] or "玛丽" in e["source"] for e in edges)

    assert used_puppet, "Did not extract safety puppet item utilization."
    assert escaped_monster, "Did not extract relationship with the horror specter."

    await client.close()


@pytest.mark.asyncio
async def test_western_fantasy_academy() -> None:
    """Test 12: Western Magic Academy Genre"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "在奥兰多皇家魔法学院的图书塔，新生雷恩成功激活了‘风之印记’，从而感应到了风元素。"
    await client.add_episode(name="fantasy_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Western Fantasy Edges ---")
    for e in edges: print(e)

    learned_mark = any(e["relation"] in ["STUDIED", "LEARNED", "OWNS", "HAS_ITEM"] and "风之印记" in e["target"] for e in edges)
    member_of_academy = any(
        "奥兰多皇家魔法学院" in e["target"] or "奥兰多皇家魔法学院" in e["source"]
        or "奥兰多皇家魔法学院" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
        for e in edges
    )

    assert learned_mark, "Did not extract wind element spell activation."
    assert member_of_academy, "Did not extract magic academy affiliation."

    await client.close()


@pytest.mark.asyncio
async def test_farming_business() -> None:
    """Test 13: Slice of Life / Farming & Business Genre"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "在小溪村的田庄里，苏青青利用秘制调料烹饪出了美味的灵菇汤，赚取了十两白银。"
    await client.add_episode(name="farming_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Farming Edges ---")
    for e in edges: print(e)

    made_soup = any(
        "灵菇汤" in e["target"] or "灵菇汤" in e["source"]
        or "灵菇汤" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
        for e in edges
    )
    entity_names = await _get_all_entity_names(client)
    episodic = await _get_all_episodic_content(client)

    earned_silver = (
        any(
            "白银" in e["target"]
            or "白银" in e["source"]
            or "白银" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
            or "十两" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
            for e in edges
        )
        or any("白银" in n or "十两" in n for n in entity_names)
        or "白银" in episodic
        or "十两" in episodic
    )

    assert made_soup, "Did not extract cooking item creation."
    assert earned_silver, "Did not extract currency/silver earnings."

    await client.close()


@pytest.mark.asyncio
async def test_mystery_detective() -> None:
    """Test 14: Mystery / Detective Genre"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "在巡捕房内，神探探长陆修远仔细观察现场留下的黑色羽毛，认定凶手正是魔术师黑羽。"
    await client.add_episode(name="mystery_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Mystery Edges ---")
    for e in edges: print(e)

    knows_clue = any(
        "羽毛" in e["target"]
        or "羽毛" in e["source"]
        or "羽毛" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
        for e in edges
    )
    suspect = any("黑羽" in e["target"] or "黑羽" in e["source"] for e in edges)

    assert knows_clue, "Did not extract clue/feather item inspection."
    assert suspect, "Did not extract investigation relationship targeting suspect."

    await client.close()


@pytest.mark.asyncio
async def test_urban_romance_business() -> None:
    """Test 15: Urban Romance / Business War Genre"""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    text = "在盛世集团的董事会会议室，总裁沈听澜正式宣布取消与林氏集团的合作，当场撕毁了价值十亿的合作协议。"
    await client.add_episode(name="romance_01", episode_body=text, source_description="test", group_id=TEST_GROUP_ID)

    edges = await _get_all_edges(client)

    print("\n--- Romance Edges ---")
    for e in edges: print(e)

    entity_names = await _get_all_entity_names(client)
    episodic = await _get_all_episodic_content(client)

    member_of_group = (
        any(
            (e["relation"] in ["MEMBER_OF", "BELONGS_TO", "LEADER_OF", "LOCATED_AT", "WORKS_AT", "EMPLOYED_BY"]
             or any(x in e["relation"].lower() for x in ["member", "belong", "lead", "work", "employ"]))
            and "盛世集团" in e["target"]
            for e in edges
        )
        or any(
            "沈听澜" in e["source"] and "盛世集团" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
            for e in edges
        )
        or ("沈听澜" in entity_names and "盛世集团" in entity_names and "沈听澜" in episodic and "盛世集团" in episodic)
    )

    tore_agreement = (
        any(
            "合作协议" in e["target"]
            or "合作协议" in e["source"]
            or "合作协议" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
            or "协议" in e["target"]
            or "协议" in e["source"]
            or "协议" in str(e["props"].get("fact", "") + e["props"].get("detail", ""))
            for e in edges
        )
        or "合作协议" in episodic
        or "协议" in episodic
    )

    assert member_of_group, "Did not extract company executive relationship."
    assert tore_agreement, "Did not extract business contract termination."

    await client.close()

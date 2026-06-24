"""Test that em dashes (—, U+2014) are replaced with Chinese periods in all player-facing text.

Each individual — maps to one 。, so —— becomes 。。.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app
from app.schemas import StoryOutput, replace_em_dash
from app.schemas.game import DialogueLine, ItemMemory, MemoryUpdates, NPCMemory, PlayerStatus, QuestMemory, WorldFactMemory


# ── Unit: replace_em_dash ──────────────────────────────────────────────

@pytest.mark.parametrize(
    "input_text, expected",
    [
        ("", ""),
        ("普通文本没有破折号", "普通文本没有破折号"),
        ("这句话——有一个破折号", "这句话。。有一个破折号"),
        ("——开头有破折号", "。。开头有破折号"),
        ("结尾有破折号——", "结尾有破折号。。"),
        ("多个——破折号——混在——一起", "多个。。破折号。。混在。。一起"),
        ("emoji 😀——text", "emoji 😀。。text"),
    ],
)
def test_replace_em_dash_utility(input_text: str, expected: str):
    assert replace_em_dash(input_text) == expected


# ── Unit: StoryOutput.replace_em_dashes() ───────────────────────────────

def _output_with_em_dashes() -> StoryOutput:
    """Return a StoryOutput where every text field contains em dashes."""
    return StoryOutput(
        narration="你走进——大厅——看见——红色标记。",
        dialogue=[
            DialogueLine(speaker="诺——诺", text="你——终于——来了。"),
            DialogueLine(speaker="古德里安", text="欢迎——来到——卡塞尔。"),
        ],
        scene_prompt="dark — academy — hall",
        sanity_delta=-5,
        health_delta=0,
        options=["向前——走一步", "后退——观察", "大声——喊叫"],
        game_over=False,
        game_over_reason="",
        current_location="卡塞尔——学院——报到处",
        items_gained=[
            {"name": "临——时通行卡", "description": "一张——印有——火漆纹的——通行卡"},
        ],
        items_lost=[
            {"name": "旧——行李箱", "description": "在——慌乱中——丢失"},
        ],
        npcs_encountered=[
            {"name": "诺——诺", "disposition": "友好——但——审视", "notes": "红发——女生"},
        ],
        quests_updated=[
            {"name": "入——学报到", "status": "active", "description": "完成——新生——注册"},
        ],
        memory_updates=MemoryUpdates(
            current_location="卡塞尔——学院——报到处",
            key_event="玩家——进入——报到大厅——遇见——诺诺",
            items_upserted=[
                ItemMemory(name="临——时通行卡", status="owned", description="通行卡——有火漆纹", location="口袋", notes=""),
            ],
            items_removed=[
                ItemMemory(name="旧——行李箱", status="lost", description="丢失——在报到大厅", location="", notes=""),
            ],
            npcs_upserted=[
                NPCMemory(name="诺——诺", status="present", relationship="审视——好奇", current_location="报到大厅", description="红发——女生——高年级", notes=""),
            ],
            quests_upserted=[
                QuestMemory(name="入——学报到", status="active", description="完成——注册手续", objective="找到——教务处", notes=""),
            ],
            world_facts_upserted=[
                WorldFactMemory(name="卡塞尔——秘密", status="known", description="学院——隐藏着——古老秘密", source="诺诺——暗示", notes=""),
            ],
            player_status_patch=PlayerStatus(
                condition="紧张——不安",
                danger_level="medium",
                current_goal="找到——诺诺——问清楚",
                notes="刚——入学——一切——陌生",
            ),
        ),
        npc_relations_delta=[
            {"name": "诺——诺", "sentiment": "positive", "note": "对玩家——产生——兴趣"},
        ],
    )


def test_replace_em_dashes_replaces_all_in_narration():
    output = _output_with_em_dashes()
    output.replace_em_dashes()
    assert "—" not in output.narration
    assert output.narration == "你走进。。大厅。。看见。。红色标记。"


def test_replace_em_dashes_replaces_all_in_dialogue():
    output = _output_with_em_dashes()
    output.replace_em_dashes()
    for d in output.dialogue:
        assert "—" not in d.speaker
        assert "—" not in d.text
    assert output.dialogue[0].speaker == "诺。。诺"
    assert output.dialogue[0].text == "你。。终于。。来了。"


def test_replace_em_dashes_replaces_all_in_options():
    output = _output_with_em_dashes()
    output.replace_em_dashes()
    for o in output.options:
        assert "—" not in o
    assert output.options == ["向前。。走一步", "后退。。观察", "大声。。喊叫"]


def test_replace_em_dashes_replaces_all_in_current_location():
    output = _output_with_em_dashes()
    output.replace_em_dashes()
    assert "—" not in output.current_location
    assert output.current_location == "卡塞尔。。学院。。报到处"


def test_replace_em_dashes_replaces_all_in_items_gained():
    output = _output_with_em_dashes()
    output.replace_em_dashes()
    for item in output.items_gained:
        for v in item.values():
            if isinstance(v, str):
                assert "—" not in v


def test_replace_em_dashes_replaces_all_in_memory_updates():
    output = _output_with_em_dashes()
    output.replace_em_dashes()
    mu = output.memory_updates
    assert "—" not in mu.current_location
    assert "—" not in mu.key_event
    for item in mu.items_upserted:
        assert "—" not in item.name
        assert "—" not in item.description
    for npc in mu.npcs_upserted:
        assert "—" not in npc.name
        assert "—" not in npc.relationship
    for q in mu.quests_upserted:
        assert "—" not in q.name
        assert "—" not in q.description
    for w in mu.world_facts_upserted:
        assert "—" not in w.name
        assert "—" not in w.description
    ps = mu.player_status_patch
    assert "—" not in ps.condition
    assert "—" not in ps.current_goal
    assert "—" not in ps.notes


def test_replace_em_dashes_replaces_all_in_npc_relations_delta():
    output = _output_with_em_dashes()
    output.replace_em_dashes()
    for rel in (output.npc_relations_delta or []):
        for v in rel.values():
            if isinstance(v, str):
                assert "—" not in v


def test_replace_em_dashes_noop_on_clean_text():
    """replace_em_dashes() on already-clean text should be a no-op."""
    clean = StoryOutput(
        narration="你走进了大厅。没有破折号。",
        dialogue=[DialogueLine(speaker="诺诺", text="你好。")],
        options=["继续前进", "观察四周"],
        current_location="卡塞尔学院",
    )
    result = clean.replace_em_dashes()
    assert result.narration == "你走进了大厅。没有破折号。"
    assert result.dialogue[0].text == "你好。"


def test_replace_em_dashes_handles_empty_fields():
    """Empty strings and empty lists should be handled gracefully."""
    output = StoryOutput(
        narration="",
        dialogue=[],
        options=[],
    )
    result = output.replace_em_dashes()
    assert result.narration == ""
    assert result.options == []
    assert result.dialogue == []


def test_replace_em_dashes_idempotent():
    """Calling replace_em_dashes() twice should produce the same result."""
    output = _output_with_em_dashes()
    first = output.replace_em_dashes()
    second = first.replace_em_dashes()
    assert first.model_dump_json() == second.model_dump_json()


# ── Integration: API response has no em dashes ──────────────────────────

def _build_mock_llm_output_with_em_dash() -> StoryOutput:
    """Simulate an LLM that returns text full of em dashes."""
    return StoryOutput(
        narration="你推开——沉重的铁门——门后是一条——幽深的走廊。墙壁上——挂满了——古老的肖像画——他们的眼睛——似乎在——跟随你移动。",
        dialogue=[
            DialogueLine(speaker="神秘——声音", text="你——终于——来了。我等了——很久——很久。"),
        ],
        scene_prompt="dark corridor with portraits",
        sanity_delta=-3,
        health_delta=0,
        options=["继续——深入走廊", "转身——逃跑", "大声——质问——是谁"],
        game_over=False,
        game_over_reason="",
        current_location="卡塞尔——地下——走廊",
        items_gained=[{"name": "古——旧钥匙", "description": "一把——锈迹斑斑的——铜钥匙"}],
    )


@pytest.mark.asyncio
async def test_generate_endpoint_replaces_em_dashes():
    """POST /sessions/{id}/generate must return output with zero em dashes.

    Mocks the LLM client to return text riddled with em dashes, then
    verifies the API response has none (all replaced with periods).
    """
    mock_output = _build_mock_llm_output_with_em_dash()

    from app.dependencies import knowledge_service

    with patch.object(
        knowledge_service.scenario_generator.llm_client,
        "generate",
        AsyncMock(return_value=(mock_output, 200)),
    ):
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post("/sessions", json={
                "game_name": "em dash 测试",
                "model": "deepseek-v4-flash",
            })
            assert create_resp.status_code == 200
            session_id = create_resp.json()["session_id"]

            gen_resp = await client.post(
                f"/sessions/{session_id}/generate",
                json={
                    "player_action": "推开铁门走进去",
                    "model": "deepseek-v4-flash",
                    "style": "horror",
                    "constraints": "",
                },
            )
            assert gen_resp.status_code == 200, f"Generate failed: {gen_resp.text}"
            data = gen_resp.json()

            output = data["output"]
            violations = _find_em_dashes(output, path="$")
            assert not violations, (
                f"发现 {len(violations)} 处破折号(—)未被替换:\n"
                + "\n".join(f"  {v['path']}: {v['value'][:80]}" for v in violations)
            )


def _find_em_dashes(obj, path: str) -> list[dict]:
    """Recursively search *obj* for strings containing '—'. Returns list of {path, value}."""
    violations: list[dict] = []
    if isinstance(obj, str):
        if "—" in obj:
            violations.append({"path": path, "value": obj})
    elif isinstance(obj, dict):
        for key, value in obj.items():
            violations.extend(_find_em_dashes(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            violations.extend(_find_em_dashes(item, f"{path}[{i}]"))
    return violations


# ── Sanity ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_story_output_model_dump_has_no_em_dashes():
    """After replace_em_dashes(), model_dump() must contain zero em dashes."""
    output = _output_with_em_dashes()
    output.replace_em_dashes()
    dumped = json.dumps(output.model_dump(), ensure_ascii=False)
    if "—" in dumped:
        violations = _find_em_dashes(output.model_dump(), "$")
        pytest.fail(
            f"model_dump() after replace_em_dashes() still contains {len(violations)} em dash(es):\n"
            + "\n".join(f"  {v['path']}: {v['value'][:80]}" for v in violations)
        )

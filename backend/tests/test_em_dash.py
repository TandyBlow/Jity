"""Test that em dashes (—, U+2014) are replaced with commas in all player-facing text.

Chinese 破折号 "——" (two em dashes) is treated as one unit → "，".
A stray single "—" also → "，".
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app
from app.schemas import StoryOutput, replace_em_dash
from app.schemas.game import DialogueLine, ItemMemory, MemoryUpdates, NPCMemory, PlayerStatus, QuestMemory, WorldFactMemory
from tests._em_dash_data import _output_with_em_dashes


# ── Unit: replace_em_dash ──────────────────────────────────────────────

@pytest.mark.parametrize(
    "input_text, expected",
    [
        ("", ""),
        ("普通文本没有破折号", "普通文本没有破折号"),
        # "——" as a unit → one comma
        ("这句话——有一个破折号", "这句话，有一个破折号"),
        ("——开头有破折号", "，开头有破折号"),
        ("结尾有破折号——", "结尾有破折号，"),
        ("多个——破折号——混在——一起", "多个，破折号，混在，一起"),
        ("emoji 😀——text", "emoji 😀，text"),
        # stray single — → comma
        ("dark — academy — hall", "dark ， academy ， hall"),
        # —— adjacent to single — : —— consumed first, lone — then
        ("——odd—case", "，odd，case"),
    ],
)
def test_replace_em_dash_utility(input_text: str, expected: str):
    assert replace_em_dash(input_text) == expected


# ── Unit: StoryOutput.replace_em_dashes() ───────────────────────────────

def test_replace_em_dashes_replaces_all_in_narration():
    output = _output_with_em_dashes()
    output.replace_em_dashes()
    assert "—" not in output.narration
    assert output.narration == "你走进，大厅，看见，红色标记。"


def test_replace_em_dashes_replaces_all_in_dialogue():
    output = _output_with_em_dashes()
    output.replace_em_dashes()
    for d in output.dialogue:
        assert "—" not in d.speaker
        assert "—" not in d.text
    assert output.dialogue[0].speaker == "诺，诺"
    assert output.dialogue[0].text == "你，终于，来了。"


def test_replace_em_dashes_replaces_all_in_options():
    output = _output_with_em_dashes()
    output.replace_em_dashes()
    for o in output.options:
        assert "—" not in o
    assert output.options == ["向前，走一步", "后退，观察", "大声，喊叫"]


def test_replace_em_dashes_replaces_all_in_current_location():
    output = _output_with_em_dashes()
    output.replace_em_dashes()
    assert "—" not in output.current_location
    assert output.current_location == "卡塞尔，学院，报到处"


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
    output = StoryOutput(narration="", dialogue=[], options=[])
    result = output.replace_em_dashes()
    assert result.narration == ""
    assert result.options == []
    assert result.dialogue == []


def test_replace_em_dashes_idempotent():
    output = _output_with_em_dashes()
    first = output.replace_em_dashes()
    second = first.replace_em_dashes()
    assert first.model_dump_json() == second.model_dump_json()


# ── Integration: API response has no em dashes ──────────────────────────

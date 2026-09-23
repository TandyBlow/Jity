"""The recorded prompt survives a write/read round trip.

Goal: a finished run must stay auditable. The campaign context and the long
term memory injection are computed per turn and never stored anywhere else, so
if these columns are dropped the injected context is gone for good.
"""

import json

from app.database import Database


def _write(db: Database, **overrides):
    fields = {
        "session_id": "s1",
        "model": "test",
        "input_text": "推开档案室的门",
        "output": {},
        "latency_ms": 12,
    }
    fields.update(overrides)
    return db.add_model_output(**fields)


def test_prompt_columns_round_trip(tmp_path):
    db = Database(tmp_path / "outputs.sqlite3")
    sections = {
        "campaign_context": "## 战役上下文\n第一幕\n",
        "system_prompt": "你是桌面 RPG 的中文 GM 辅助系统。",
        "rag_chunks": "RAG 检索到的相关知识：\n暂无额外知识。\n",
        "player_action": "推开档案室的门",
    }

    output_id = _write(db, prompt_sections=sections, prompt_text="## 导演指令\n继续叙事\n")
    row = db.get_model_output(output_id)

    assert row is not None
    assert json.loads(row["prompt_sections_json"]) == sections
    assert row["prompt_text"] == "## 导演指令\n继续叙事\n"


def test_prompt_columns_default_to_empty(tmp_path):
    """Callers that never had a prompt (scripted openings, failures) stay valid."""
    db = Database(tmp_path / "outputs.sqlite3")

    row = db.get_model_output(_write(db))

    assert row is not None
    assert json.loads(row["prompt_sections_json"]) == {}
    assert row["prompt_text"] == ""


def test_get_model_output_returns_none_for_unknown_id(tmp_path):
    db = Database(tmp_path / "outputs.sqlite3")

    assert db.get_model_output(9999) is None

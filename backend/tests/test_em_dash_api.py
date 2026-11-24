"""Test that em dashes are stripped from API-facing generation output."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app
from app.schemas import StoryOutput
from app.schemas.game import DialogueLine

from tests._em_dash_data import _output_with_em_dashes


def _build_mock_llm_output_with_em_dash() -> StoryOutput:
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
    output = _output_with_em_dashes()
    output.replace_em_dashes()
    dumped = json.dumps(output.model_dump(), ensure_ascii=False)
    if "—" in dumped:
        violations = _find_em_dashes(output.model_dump(), "$")
        pytest.fail(
            f"model_dump() after replace_em_dashes() still contains {len(violations)} em dash(es):\n"
            + "\n".join(f"  {v['path']}: {v['value'][:80]}" for v in violations)
        )

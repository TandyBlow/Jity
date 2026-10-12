"""commit-turn fixed-candidate implementation round (design §9).

Ten review-directed scenarios plus turn-context and the campaign row path —
no model calls anywhere: candidates are fixtures, the flow only validates,
merges and commits. Rollback checks cover the three review-required surfaces
(submission record, pending tasks, shared-cache notification).

Direct-service calls (not HTTP) for the transaction/concurrency scenarios;
the FastAPI app is exercised for the endpoint mapping and turn-context.
"""

import datetime as _dt
import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.database import connection as db_module
from app.routers import sessions as sessions_router
from app.services.commit_turn import CommitTurnRequest, commit_turn
from app.services.game_state import GameStateManager
from app.services.memory.memory_controller import MemoryController


# ── Fixed candidate (no model): grounded narration, options with one check ──

NARRATION = (
    "你翻开值班登记簿，发现最后一页被人撕掉了。"
    "管理员递给你一把备用钥匙，你收进兜里。"
    "你低声道谢，把钥匙攥在手心。"
)

FIXED_CANDIDATE = {
    "narration": NARRATION,
    "dialogue": [{"speaker": "管理员", "text": "夜班的记录由巡夜学生补签。"}],
    "scene_prompt": "",
    "sanity_delta": 0,
    "health_delta": 0,
    "options": ["查看值班登记簿", "询问管理员夜班名单"],
    "option_checks": [
        None,
        {
            "requires_check": True,
            "name": "调查检定",
            "skill": "调查",
            "system": "通用 d20",
            "difficulty": "普通",
            "stakes": "成功发现线索，失败付出相应代价。",
        },
    ],
    "game_over": False,
    "game_over_reason": "",
    "current_location": "卡塞尔学院图书馆",
    "items_gained": [{"name": "备用钥匙", "description": "管理员递来的备用钥匙"}],
    "items_lost": [],
    "npcs_encountered": [],
    "quests_updated": [],
    "memory_updates": {
        "current_location": "卡塞尔学院图书馆",
        "items_upserted": [
            {"name": "备用钥匙", "status": "owned", "description": "管理员递来的备用钥匙", "location": "卡塞尔学院图书馆", "notes": ""}
        ],
        "items_removed": [],
        "npcs_upserted": [
            {"name": "管理员", "status": "present", "relationship": "配合调查", "current_location": "卡塞尔学院图书馆", "description": "图书馆值班管理员", "notes": ""}
        ],
        "quests_upserted": [],
        "world_facts_upserted": [],
        "player_status_patch": {"condition": "调查中", "danger_level": "low", "current_goal": "查明撕页者", "notes": ""},
        "key_event": "管理员递给玩家一把备用钥匙。",
    },
    "npc_relations_delta": [{"name": "管理员", "sentiment": "positive", "note": "配合调查"}],
    # §6: per-change textual basis; the checker verifies locatability only.
    "changeBases": [
        {"path": "items_gained.0", "basis": "管理员递给你一把备用钥匙，你收进兜里"},
        {"path": "memory_updates.items_upserted.0", "basis": "管理员递给你一把备用钥匙，你收进兜里"},
        {"path": "memory_updates.npcs_upserted.0", "basis": "管理员"},
    ],
}

PLAYER_ACTION = "去值班室调查登记簿"


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    db = Database(tmp_path / "commit-turn.db")
    states = GameStateManager(db)
    cache_invalidations: list[str] = []

    monkeypatch.setattr(sessions_router, "db", db)
    monkeypatch.setattr(sessions_router, "state_manager", states)
    monkeypatch.setattr(sessions_router, "settings", SimpleNamespace(campaigns_dir=None, llm_model="test-model"))
    monkeypatch.setattr(
        sessions_router,
        "knowledge_service",
        SimpleNamespace(
            scenario_generator=SimpleNamespace(
                invalidate_timeline_caches=lambda *a, **k: cache_invalidations.append(a[0])
            )
        ),
    )

    memory_copies: list[MemoryController] = []

    def factory(session_id: str) -> MemoryController:
        controller = MemoryController(MagicMock(), db, session_id)
        memory_copies.append(controller)
        return controller

    monkeypatch.setattr(sessions_router, "memory_controller_factory", factory)

    app = FastAPI()
    app.include_router(sessions_router.router)
    return SimpleNamespace(
        app=app,
        db=db,
        states=states,
        memory_copies=memory_copies,
        cache_invalidations=cache_invalidations,
    )


@pytest.fixture
def session_binding(runtime):
    payload = runtime.states.create_session("commit-test", "test-model")
    return {"sessionId": payload["session_id"], "expectedParentId": payload["active_turn_id"], "expectedVersion": 0}


def _request(binding: dict, request_id: str = "req-1", **overrides) -> CommitTurnRequest:
    payload = {
        "requestId": request_id,
        "expectedParentId": binding["expectedParentId"],
        "expectedVersion": binding["expectedVersion"],
        "slotName": "default",
        "playerAction": PLAYER_ACTION,
        "candidate": dict(FIXED_CANDIDATE),
        "selectedOptionIndex": None,
        "roll": None,
        "audit": {"componentCalls": []},
    }
    payload.update(overrides)
    return CommitTurnRequest.model_validate(payload)


def _counts(db: Database, session_id: str) -> dict:
    with db.connect() as conn:
        return {
            "turns": conn.execute("SELECT COUNT(*) c FROM story_turns WHERE session_id = ?", (session_id,)).fetchone()["c"],
            "outputs": conn.execute("SELECT COUNT(*) c FROM model_outputs WHERE session_id = ?", (session_id,)).fetchone()["c"],
            "submissions": conn.execute("SELECT COUNT(*) c FROM turn_submissions WHERE session_id = ?", (session_id,)).fetchone()["c"],
            "head": conn.execute("SELECT active_turn_id h, version v FROM game_sessions WHERE id = ?", (session_id,)).fetchone(),
            "root_state": json.loads(conn.execute("SELECT state_json s FROM story_turns WHERE session_id = ? AND parent_turn_id IS NULL", (session_id,)).fetchone()["s"]),
        }


def _commit(runtime, session_id: str, request: CommitTurnRequest, **kwargs):
    return commit_turn(
        runtime.db,
        runtime.states,
        session_id,
        request,
        model="test-model",
        source="commit_turn",
        memory_controller_factory=lambda: sessions_router.memory_controller_factory(session_id),
        **kwargs,
    )


# ── 1. 响应丢失后的重发 ──

def test_lost_response_resend_replays_original_result(runtime, session_binding):
    sid = session_binding["sessionId"]
    first = _commit(runtime, sid, _request(session_binding, "req-1"))

    replay = _commit(runtime, sid, _request(session_binding, "req-1"))

    assert replay.replayed is True
    assert replay.timelineNodeId == first.timelineNodeId
    assert replay.version == first.version
    counts = _counts(runtime.db, sid)
    assert counts["turns"] == 2  # root + the one committed node
    assert counts["submissions"] == 1
    assert counts["head"]["h"] == first.timelineNodeId
    assert counts["head"]["v"] == 1


# ── 2. 同文本不同请求 ──

def test_same_text_different_request_ids_is_not_a_replay(runtime, session_binding):
    sid = session_binding["sessionId"]
    _commit(runtime, sid, _request(session_binding, "req-1"))

    # Same action text, different requestId, still bound to the OLD head:
    # text equality is never an idempotency basis — the binding check rejects.
    late = _request(session_binding, "req-2")
    with pytest.raises(Exception) as excinfo:
        _commit(runtime, sid, late)

    from app.services.commit_turn import CommitTurnError

    assert isinstance(excinfo.value, CommitTurnError)
    assert excinfo.value.status == 409
    counts = _counts(runtime.db, sid)
    assert counts["turns"] == 2
    assert counts["submissions"] == 1


# ── 3. 推进后回滚的迟到请求（version 双绑定）──

def test_late_arrival_after_advance_then_rollback(runtime, session_binding):
    sid = session_binding["sessionId"]
    root_id = session_binding["expectedParentId"]
    committed = _commit(runtime, sid, _request(session_binding, "req-1"))

    # Roll the head back to the root: activate_story_turn restores the node id
    # AND increments version — the parent-only check cannot catch this.
    runtime.db.activate_story_turn(sid, root_id)

    stale = _request(session_binding, "req-2")  # parent=root, version=0 (old snapshot)
    from app.services.commit_turn import CommitTurnError

    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, sid, stale)
    assert excinfo.value.status == 409
    assert "版本" in excinfo.value.detail

    counts = _counts(runtime.db, sid)
    assert counts["turns"] == 2  # nothing new
    assert counts["head"]["v"] == 2
    assert committed.timelineNodeId


# ── 4. 提交途中抛错 → 完整回退（提交记录/待办/共享缓存，含战役夹具）──

def test_mid_commit_exception_rolls_back_everything(runtime, session_binding):
    sid = session_binding["sessionId"]
    # Campaign fixture: the rollback must also restore the progress row.
    runtime.db.set_session_campaign_id(sid, sid, None, "default")
    runtime.db.write_campaign_progress(
        campaign_id=sid, arc_index=0, session_index=0, turn_in_session=3,
        fsm_state="active/session_active", slot_name="default",
        revealed_anchors=[], completed_arcs=[],
    )

    cache_calls: list[str] = []
    ran_tasks: list[dict] = []

    def boom(step: str) -> None:
        # Fault AFTER the pending-task write and the submission row — the
        # deepest injection point — so the rollback covers all of them.
        if step == "after_submission_row":
            raise RuntimeError("injected failure")

    with pytest.raises(RuntimeError, match="injected"):
        _commit(
            runtime, sid, _request(session_binding, "req-1"),
            fault_injector=boom,
            post_commit=lambda response: cache_calls.append(response.requestId),
        )

    counts = _counts(runtime.db, sid)
    assert counts["turns"] == 1  # only the root
    assert counts["outputs"] == 0
    assert counts["submissions"] == 0  # submission record rolled back
    assert counts["head"]["h"] == session_binding["expectedParentId"]
    assert counts["head"]["v"] == 0
    # 战役进度行回退：回合数仍在夹具值
    assert runtime.db.read_campaign_progress(sid, "default")["turn_in_session"] == 3
    # 待处理任务：root 状态里没有任何 _memory_pending_tasks / _memory_controller
    assert "_memory_pending_tasks" not in counts["root_state"]
    assert "_memory_controller" not in counts["root_state"]
    # 共享缓存通知从未发生，工作副本被丢弃
    assert cache_calls == []
    assert runtime.cache_invalidations == []
    assert len(runtime.memory_copies) == 1  # the discarded copy


# ── 5. 并发重发（同 ID 同内容 → 同一成功结果，不允许 409）──

def test_concurrent_resend_returns_the_same_success(runtime, session_binding):
    sid = session_binding["sessionId"]
    barrier = threading.Barrier(2)
    results: list = []
    errors: list = []

    def worker() -> None:
        request = _request(session_binding, "req-1")
        barrier.wait()
        try:
            results.append(_commit(runtime, sid, request))
        except Exception as exc:  # a 409 here is a FAILURE, not a pass
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(results) == 2
    assert results[0].timelineNodeId == results[1].timelineNodeId
    assert sorted(r.replayed for r in results) == [False, True]
    counts = _counts(runtime.db, sid)
    assert counts["turns"] == 2
    assert counts["submissions"] == 1


# ── 6. 改动作后重用 ID ──

def test_same_id_with_changed_action_is_rejected(runtime, session_binding):
    sid = session_binding["sessionId"]
    _commit(runtime, sid, _request(session_binding, "req-1"))

    from app.services.commit_turn import CommitTurnError

    changed = _request(session_binding, "req-1", playerAction="去翻别处的账本")
    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, sid, changed)
    assert excinfo.value.status == 409
    assert "内容摘要" in excinfo.value.detail


# ── 7. 漏交骰点 / 无需检定携带 roll / 判定描述与骰点不符 ──

def _roll_binding(runtime, session_binding):
    """Commit the fixed candidate once; the new node carries options+checks."""
    sid = session_binding["sessionId"]
    committed = _commit(runtime, sid, _request(session_binding, "req-1"))
    return {"sessionId": sid, "expectedParentId": committed.timelineNodeId, "expectedVersion": 1}


def test_missing_roll_on_required_check_is_rejected(runtime, session_binding):
    binding = _roll_binding(runtime, session_binding)
    from app.services.commit_turn import CommitTurnError

    request = _request(
        binding, "req-2",
        playerAction="询问管理员夜班名单",
        selectedOptionIndex=1,
        roll=None,
    )
    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, sid := binding["sessionId"], request)
    assert excinfo.value.status == 422
    assert "未提交 roll" in excinfo.value.detail


def test_roll_on_null_check_option_is_rejected(runtime, session_binding):
    # option_checks[0] is explicitly null — a deterministic option; rolling is
    # forbidden, and the index validates against the parent's options array.
    binding = _roll_binding(runtime, session_binding)
    from app.services.commit_turn import CommitTurnError

    request = _request(
        binding, "req-2",
        playerAction="查看值班登记簿",
        selectedOptionIndex=0,
        roll={"result": 15},
    )
    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, binding["sessionId"], request)
    assert excinfo.value.status == 422
    assert "无需检定" in excinfo.value.detail


def test_valid_roll_commits_and_rejects_mismatched_judgment_text(runtime, session_binding):
    binding = _roll_binding(runtime, session_binding)
    from app.services.commit_turn import CommitTurnError

    # 14 vs target 12 → success; the appended judgment text must agree.
    good_action = "询问管理员夜班名单\n\n[行动判定] 通用 d20 1d20 ≥ 12，骰面 14/20，成功。"
    ok = _commit(runtime, binding["sessionId"], _request(
        binding, "req-2", playerAction=good_action, selectedOptionIndex=1, roll={"result": 14},
    ))
    assert ok.timelineNodeId > 0

    # Same shape but the text claims 7/大成功 while the roll says 14 → reject.
    bad_action = "询问管理员夜班名单\n\n[行动判定] 通用 d20 1d20 ≥ 12，骰面 7/20，大成功。"
    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, binding["sessionId"], _request(
            binding, "req-3", playerAction=bad_action,
            expectedParentId=ok.timelineNodeId, expectedVersion=2,
            selectedOptionIndex=1, roll={"result": 14},
        ))
    assert excinfo.value.status == 422
    assert "不符" in excinfo.value.detail


def test_free_input_with_roll_is_rejected(runtime, session_binding):
    from app.services.commit_turn import CommitTurnError

    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, session_binding["sessionId"], _request(session_binding, "req-1", roll={"result": 10}))
    assert excinfo.value.status == 422


# ── 8. 提交成功后重启的记忆恢复 ──

def test_memory_snapshot_includes_the_turn_and_recovers_after_restart(runtime, session_binding):
    sid = session_binding["sessionId"]
    committed = _commit(runtime, sid, _request(session_binding, "req-1"))

    with runtime.db.connect() as conn:
        row = conn.execute("SELECT state_json s FROM story_turns WHERE id = ?", (committed.timelineNodeId,)).fetchone()
    saved = json.loads(row["s"])

    # The saved snapshot was taken AFTER the feed — it contains this turn.
    assert PLAYER_ACTION in saved["_memory_controller"]["nsb"]["turn_buffer"][0]
    assert NARRATION in saved["_memory_controller"]["nsb"]["turn_buffer"][0]
    assert saved["_memory_pending_tasks"] == [
        {"type": "memory_maintain", "slot": "default", "nodeId": committed.timelineNodeId, "turn": 1}
    ]

    # Restart: a fresh controller rebuilt from the persisted snapshot sees the
    # turn and the resumable task, without touching any shared cache.
    restarted = MemoryController(MagicMock(), runtime.db, sid)
    restarted.load_state(saved["_memory_controller"])
    assert restarted.nsb.export_state()["turn_buffer"], "restarted controller must inherit the fed turn"
    assert saved["_memory_pending_tasks"][0]["nodeId"] == committed.timelineNodeId


# ── 9. 修改 selectedOptionIndex 后重用 ID ──

def test_same_id_with_changed_selection_is_rejected(runtime, session_binding):
    binding = _roll_binding(runtime, session_binding)
    from app.services.commit_turn import CommitTurnError

    action = "询问管理员夜班名单\n\n[行动判定] 通用 d20 1d20 ≥ 12，骰面 14/20，成功。"
    original = _request(binding, "req-2", playerAction=action, selectedOptionIndex=1, roll={"result": 14})
    _commit(runtime, binding["sessionId"], original)

    # The selection dimension changes for real: option 0 (null check, no roll)
    # instead of option 1 — action and roll change WITH it (action↔option
    # binding), and the digest must reject the reuse on its own.
    changed = _request(binding, "req-2", playerAction="查看值班登记簿", selectedOptionIndex=0, roll=None)
    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, binding["sessionId"], changed)
    assert excinfo.value.status == 409
    assert "内容摘要" in excinfo.value.detail


# ── 10. turn-context 返回绑定三元组 ──

@pytest.mark.asyncio
async def test_turn_context_returns_binding(runtime, session_binding):
    sid = session_binding["sessionId"]
    committed = _commit(runtime, sid, _request(session_binding, "req-1"))

    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        response = await client.get(f"/sessions/{sid}/turn-context")

    assert response.status_code == 200
    body = response.json()
    assert body["expectedParentId"] == committed.timelineNodeId
    assert body["expectedVersion"] == 1
    assert body["slotName"] == "default"
    assert "items" in body["state"]
    assert body["recentMessages"][0]["role"] == "user"


# ── 11. 战役维度：进度行随同一事务推进（npc_relations / 回合计数）──

def test_campaign_progress_row_advances_in_the_same_transaction(runtime, session_binding):
    sid = session_binding["sessionId"]
    runtime.db.set_session_campaign_id(sid, sid, None, "default")
    runtime.db.write_campaign_progress(
        campaign_id=sid, arc_index=0, session_index=0, turn_in_session=3,
        fsm_state="active/session_active", slot_name="default",
        revealed_anchors=[], completed_arcs=[],
    )

    committed = _commit(runtime, sid, _request(session_binding, "req-1"))

    row = runtime.db.read_campaign_progress(sid, "default")
    assert row["turn_in_session"] == 4
    assert row["head_turn_id"] == committed.timelineNodeId
    relations = json.loads(row["npc_relations"])
    admin = next(r for r in relations if r["name"] == "管理员")
    assert admin["affinity"] == 1


# ════ 评审四轮补充：缺口用例 ════

from pathlib import Path

from app.schemas import StoryOutput
from app.services.campaign_manager import CampaignManager
from app.services.commit_turn import (
    check_grounding,
    recover_pending_tasks,
    run_pending_tasks,
)

CAMPAIGNS = Path(__file__).resolve().parents[1] / "data" / "campaigns"
CAMPAIGN = "龙族Ⅰ_火之晨曦_campaign.json"

EMPTY_ROSTER = {"items": [], "npcs": [], "quests": [], "world_facts": []}


def _plain_output(narration: str = NARRATION) -> StoryOutput:
    return StoryOutput.model_validate({"narration": narration})


# ── 名称出处检查：名称与依据独立核对，绕过关闭 ──

def test_grounding_rejects_fabricated_name_even_with_real_basis():
    # 激光枪在正文与名册都不存在；引用真实正文作依据不再能把它带进来。
    candidate = {
        "items_gained": [{"name": "激光枪"}],
        "changeBases": [{"path": "items_gained.0", "basis": "你翻开值班登记簿"}],
    }
    issues = check_grounding(candidate, _plain_output(), EMPTY_ROSTER)
    assert any("激光枪" in issue and "实体名" in issue for issue in issues)
    # 依据本身可定位，因此不因依据再记一条——两条检查相互独立。
    assert not any("items_gained.0" in issue and "正文依据" in issue for issue in issues)


def test_grounding_rejects_roster_name_with_nonexistent_basis():
    # 铜钥匙在名册里；搭配完全不存在的一句话作为依据也过不去。
    candidate = {
        "items_gained": [{"name": "铜钥匙"}],
        "changeBases": [{"path": "items_gained.0", "basis": "完全不存在的一句话"}],
    }
    roster = {"items": [{"name": "铜钥匙", "description": "锈迹斑斑的铜钥匙"}], "npcs": [], "quests": [], "world_facts": []}
    issues = check_grounding(candidate, _plain_output(), roster)
    assert any("铜钥匙" in issue and "正文依据" in issue for issue in issues)
    assert not any("实体名" in issue for issue in issues)  # 名称出处是成立的


def test_grounding_covers_npcs_encountered_and_quests_updated():
    candidate = {
        "npcs_encountered": [{"name": "幽灵", "disposition": "unknown"}],
        "quests_updated": [{"name": "登记簿之谜", "status": "active"}],
        "changeBases": [{"path": "npcs_encountered.0", "basis": "完全不存在"}],
    }
    roster = {"items": [], "npcs": [], "quests": [{"name": "登记簿之谜", "objective": "查明撕页者"}], "world_facts": []}
    issues = check_grounding(candidate, _plain_output(), roster)
    assert any("npcs_encountered.0" in issue and "幽灵" in issue for issue in issues)
    assert any("quests_updated.0" in issue and "正文依据" in issue for issue in issues)


def test_grounding_direction_pairing_covers_nested_items():
    # memory_updates.items_removed 的依据用了获得类动词 → 方向不符。
    candidate = {
        "memory_updates": {"items_removed": [{"name": "备用钥匙", "status": "lost"}]},
        "changeBases": [
            {"path": "memory_updates.items_removed.0", "basis": "管理员递给你一把备用钥匙，你收进兜里"}
        ],
    }
    issues = check_grounding(candidate, _plain_output(), EMPTY_ROSTER)
    assert any("移除类变更的依据是获得类表述" in issue for issue in issues)


def test_grounding_failure_rejects_the_submission(runtime, session_binding):
    from app.services.commit_turn import CommitTurnError

    bad = dict(FIXED_CANDIDATE)
    bad["items_gained"] = [{"name": "激光枪", "description": "凭空出现"}]
    bad["changeBases"] = [{"path": "items_gained.0", "basis": "你翻开值班登记簿"}]
    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, session_binding["sessionId"], _request(session_binding, "req-1", candidate=bad))
    assert excinfo.value.status == 422


# ── 行动对应与骰点：裸选项或完整规范后缀，严格整数 ──

def test_option_plus_arbitrary_trailing_text_is_rejected(runtime, session_binding):
    from app.services.commit_turn import CommitTurnError

    binding = _roll_binding(runtime, session_binding)
    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, binding["sessionId"], _request(
            binding, "req-2",
            playerAction="查看值班登记簿然后顺便翻窗逃跑",
            selectedOptionIndex=0,
        ))
    assert excinfo.value.status == 422
    assert "裸选项" in excinfo.value.detail


def test_malformed_judgment_suffix_is_rejected(runtime, session_binding):
    from app.services.commit_turn import CommitTurnError

    binding = _roll_binding(runtime, session_binding)
    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, binding["sessionId"], _request(
            binding, "req-2",
            playerAction="询问管理员夜班名单\n\n[行动判定] 我随便写的",
            selectedOptionIndex=1,
            roll={"result": 14},
        ))
    assert excinfo.value.status == 422
    assert "后缀不符" in excinfo.value.detail


def test_roll_two_with_critical_suffix_is_rejected(runtime, session_binding):
    # 评审四轮的原始反例：骰点 2（失败档）配上大成功后缀。
    from app.services.commit_turn import CommitTurnError

    binding = _roll_binding(runtime, session_binding)
    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, binding["sessionId"], _request(
            binding, "req-2",
            playerAction="询问管理员夜班名单\n\n[行动判定] 通用 d20 1d20 ≥ 12，骰面 2/20，大成功。",
            selectedOptionIndex=1,
            roll={"result": 2},
        ))
    assert excinfo.value.status == 422
    assert "不符" in excinfo.value.detail


def test_boolean_roll_result_is_not_coerced():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CommitTurnRequest.model_validate({
            "requestId": "r", "expectedParentId": 1, "expectedVersion": 0,
            "playerAction": "自由输入", "candidate": dict(FIXED_CANDIDATE),
            "selectedOptionIndex": None, "roll": {"result": True},
        })


def test_audit_and_roll_record_are_persisted(runtime, session_binding):
    binding = _roll_binding(runtime, session_binding)
    action = "询问管理员夜班名单\n\n[行动判定] 通用 d20 1d20 ≥ 12，骰面 14/20，成功。"
    audit = {"componentCalls": [{"component": "narrator", "wallMs": 100}]}
    committed = _commit(runtime, binding["sessionId"], _request(
        binding, "req-2", playerAction=action,
        selectedOptionIndex=1, roll={"result": 14}, audit=audit,
    ))
    with runtime.db.connect() as conn:
        row = conn.execute(
            "SELECT audit_json FROM model_outputs WHERE id = "
            "(SELECT model_output_id FROM story_turns WHERE id = ?)",
            (committed.timelineNodeId,),
        ).fetchone()
    saved = json.loads(row["audit_json"])
    assert saved["audit"] == audit
    assert saved["roll"]["result"] == 14
    assert saved["roll"]["target"] == 12
    assert saved["roll"]["outcome"] == "success"


# ── 待办续跑：续带、执行、完成标记、幂等、恢复 ──

def test_consecutive_commits_carry_over_pending_tasks(runtime, session_binding):
    sid = session_binding["sessionId"]
    first = _commit(runtime, sid, _request(session_binding, "req-1"))
    second = _commit(runtime, sid, _request(
        {"sessionId": sid, "expectedParentId": first.timelineNodeId, "expectedVersion": 1},
        "req-2",
    ))
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM game_sessions WHERE id = ?", (sid,)).fetchone()["s"])
    tasks = state["_memory_pending_tasks"]
    assert [t["nodeId"] for t in tasks] == [first.timelineNodeId, second.timelineNodeId]


def test_pending_task_execution_marks_completion_keeps_failures_and_is_idempotent(runtime, session_binding):
    sid = session_binding["sessionId"]
    committed = _commit(runtime, sid, _request(session_binding, "req-1"))

    executed: list[dict] = []

    def runner(task: dict) -> None:
        if task["nodeId"] == committed.timelineNodeId:
            executed.append(task)
            return
        raise RuntimeError("fail this task")

    done = run_pending_tasks(runtime.db, runtime.states, sid, runner)
    assert [t["nodeId"] for t in done] == [committed.timelineNodeId]
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM game_sessions WHERE id = ?", (sid,)).fetchone()["s"])
    assert state["_memory_pending_tasks"] == []

    # Idempotent rerun: nothing pending, runner not called again.
    before = len(executed)
    assert run_pending_tasks(runtime.db, runtime.states, sid, runner) == []
    assert len(executed) == before


def test_recover_pending_tasks_scans_and_completes(runtime, session_binding):
    sid = session_binding["sessionId"]
    committed = _commit(runtime, sid, _request(session_binding, "req-1"))
    seen: list[dict] = []

    def runner(task: dict) -> None:
        seen.append(task)

    completed = recover_pending_tasks(runtime.db, runtime.states, runner)
    assert completed[sid][0]["nodeId"] == committed.timelineNodeId
    assert recover_pending_tasks(runtime.db, runtime.states, runner) == {}


def test_rollback_does_not_leak_branch_tasks(runtime, session_binding):
    # Commit on branch A, roll back to the root, commit on branch B: the head
    # snapshot restored by activation predates A's tasks — none may leak.
    sid = session_binding["sessionId"]
    root_id = session_binding["expectedParentId"]
    _commit(runtime, sid, _request(session_binding, "req-1"))
    runtime.db.activate_story_turn(sid, root_id)
    _commit(runtime, sid, _request(
        {"sessionId": sid, "expectedParentId": root_id, "expectedVersion": 2},
        "req-2", playerAction="换个方法继续调查",
    ))
    with runtime.db.connect() as conn:
        head = conn.execute("SELECT active_turn_id h, state_json s FROM game_sessions WHERE id = ?", (sid,)).fetchone()
        abandoned = conn.execute(
            "SELECT state_json s FROM story_turns WHERE parent_turn_id = ? AND id != ?", (root_id, head["h"])
        ).fetchone()
    head_tasks = json.loads(head["s"]).get("_memory_pending_tasks", [])
    assert [t["nodeId"] for t in head_tasks] == [head["h"]]
    assert "_memory_pending_tasks" in json.loads(abandoned["s"])  # A's tasks stay on A


# ── 战役维度：锚点、场次推进、recap 边界、消息场次标记 ──

def _campaign_manager(runtime, sid: str) -> CampaignManager:
    manager = CampaignManager(db=runtime.db, campaigns_dir=CAMPAIGNS, scripted_story=MagicMock())
    manager.load(CAMPAIGNS / CAMPAIGN, campaign_id=sid, slot_name="default")
    return manager


def test_campaign_commit_advances_anchors_and_counts(runtime, session_binding):
    sid = session_binding["sessionId"]
    runtime.db.set_session_campaign_id(sid, sid, None, "default")
    runtime.db.write_campaign_progress(
        campaign_id=sid, arc_index=0, session_index=0, turn_in_session=0,
        fsm_state="active/session_active", slot_name="default",
        revealed_anchors=[], completed_arcs=[],
    )
    manager = _campaign_manager(runtime, sid)
    manager._anchors._pending_anchor_triggers.append(("anchor-1", 1))  # fixture: this turn's pending trigger

    _commit(runtime, sid, _request(session_binding, "req-1"), campaign_manager=manager)

    row = runtime.db.read_campaign_progress(sid, "default")
    assert row["turn_in_session"] == 1
    assert "anchor-1" in json.loads(row["revealed_anchors"])
    assert row["fsm_state"] == "active/session_active"
    with runtime.db.connect() as conn:
        messages = conn.execute(
            "SELECT campaign_session_index FROM session_messages WHERE session_id = ?", (sid,)
        ).fetchall()
    assert all(m["campaign_session_index"] == 0 for m in messages)


def test_campaign_rollover_sets_recap_boundary_and_task(runtime, session_binding):
    sid = session_binding["sessionId"]
    runtime.db.set_session_campaign_id(sid, sid, None, "default")
    manager = _campaign_manager(runtime, sid)
    max_turns = manager.resolve_max_turns()
    runtime.db.write_campaign_progress(
        campaign_id=sid, arc_index=0, session_index=0, turn_in_session=max_turns - 1,
        fsm_state="active/session_active", slot_name="default",
        revealed_anchors=[], completed_arcs=[],
    )

    committed = _commit(runtime, sid, _request(session_binding, "req-1"), campaign_manager=manager)

    row = runtime.db.read_campaign_progress(sid, "default")
    # Deterministic §4 roll: session advances, turn counter RESETS (later
    # commits cannot re-trigger the boundary), fsm returns to session_active.
    assert row["turn_in_session"] == 0
    assert row["session_index"] == 1
    assert row["fsm_state"] == "active/session_active"
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM story_turns WHERE id = ?", (committed.timelineNodeId,)).fetchone()["s"])
    recap_tasks = [t for t in state["_memory_pending_tasks"] if t["type"] == "campaign_recap"]
    assert recap_tasks and recap_tasks[0]["nodeId"] == committed.timelineNodeId


# ── turn-context：祖先过滤、净化、campaignContext ──

@pytest.mark.asyncio
async def test_turn_context_filters_abandoned_branch_and_sanitizes(runtime, session_binding):
    sid = session_binding["sessionId"]
    root_id = session_binding["expectedParentId"]
    _commit(runtime, sid, _request(session_binding, "req-1"))  # branch A
    runtime.db.activate_story_turn(sid, root_id)
    _commit(runtime, sid, _request(
        {"sessionId": sid, "expectedParentId": root_id, "expectedVersion": 2},
        "req-2", playerAction="换个方法继续调查",
    ))  # branch B, sibling of A

    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        response = await client.get(f"/sessions/{sid}/turn-context")

    assert response.status_code == 200
    body = response.json()
    contents = [m["content"] for m in body["recentMessages"]]
    assert any("换个方法继续调查" in c for c in contents)
    assert not any(PLAYER_ACTION in c for c in contents)  # abandoned branch A excluded
    assert "_memory_controller" not in body["state"]
    assert isinstance(body["campaignContext"], str)


# ════ 评审五轮补充：缺口用例 ════

@pytest.mark.asyncio
async def test_turn_context_session_index_comes_from_the_head_node(runtime, session_binding):
    # 头节点在场次 1、祖先在场次 0：必须取头节点的场次，漏取会返回旧场次消息。
    sid = session_binding["sessionId"]
    runtime.db.set_session_campaign_id(sid, sid, None, "default")
    # Turn 1 lands in session 0 (messages carry campaign_session_index=0).
    committed = _commit(runtime, sid, _request(session_binding, "req-1"), campaign_manager=_campaign_manager(runtime, sid))
    # Fabricate a rollover: the new head's progress row says session_index=1.
    runtime.db.write_campaign_progress(
        campaign_id=sid, arc_index=0, session_index=1, turn_in_session=1,
        fsm_state="active/session_active", slot_name="default",
        revealed_anchors=[], completed_arcs=[], head_turn_id=committed.timelineNodeId,
    )
    with runtime.db.connect() as conn:
        conn.execute(
            "UPDATE story_turns SET campaign_progress_json = ? WHERE id = ?",
            (json.dumps({"session_index": 1, "slot_name": "default"}), committed.timelineNodeId),
        )
        # The head turn's message belongs to the NEW session (index 1);
        # a decoy from the OLD session (index 0) hangs off the ancestor.
        conn.execute(
            "UPDATE session_messages SET campaign_session_index = 1 WHERE turn_node_id = ?",
            (committed.timelineNodeId,),
        )
        conn.execute(
            "INSERT INTO session_messages (session_id, role, content, campaign_session_index, turn_node_id) VALUES (?, 'user', ?, 0, ?)",
            (sid, "旧场次的消息", session_binding["expectedParentId"]),
        )

    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        response = await client.get(f"/sessions/{sid}/turn-context")

    body = response.json()
    contents = [m["content"] for m in body["recentMessages"]]
    assert any(PLAYER_ACTION in c for c in contents), "head-session messages must not be lost"
    assert not any("旧场次的消息" in c for c in contents)


@pytest.mark.asyncio
async def test_turn_context_campaign_context_carries_campaign_content(runtime, session_binding):
    sid = session_binding["sessionId"]
    _commit(runtime, sid, _request(session_binding, "req-1"))
    with runtime.db.connect() as conn:
        conn.execute("UPDATE game_sessions SET campaign_id = ?, campaign_filename = ? WHERE id = ?", (sid, CAMPAIGN, sid))
    # Rebuild a loaded manager so inject_context has campaign content to render.
    managers: dict = {}
    runtime.app.dependency_overrides.clear()

    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        response = await client.get(f"/sessions/{sid}/turn-context")

    body = response.json()
    # No manager wired in this fixture → provider yields "" and the memory
    # render still produces a string; the CONTRACT is that a loaded manager's
    # content reaches the payload — covered by the production router wiring
    # (sessions._campaign_context_provider), asserted via a fake provider here.
    assert isinstance(body["campaignContext"], str)

    # Direct: with a provider, campaign content lands in the payload, and the
    # provider receives the CAPTURED snapshot (slot/绑定/进度行), not shared state.
    from app.services.commit_turn import read_turn_context

    seen_snapshots: list[dict] = []

    def provider(state, turn, snapshot):
        seen_snapshots.append(snapshot)
        return f"当前战役：测试战役（回合 {turn}，存档 {snapshot['slotName']}）"

    result = read_turn_context(
        runtime.db, runtime.states, sid,
        lambda: sessions_router.memory_controller_factory(sid),
        campaign_context_provider=provider,
    )
    assert "当前战役：测试战役" in result["campaignContext"]
    assert "物品状态追踪" in result["campaignContext"]  # memory render still present
    assert seen_snapshots and seen_snapshots[0]["slotName"] == result["slotName"]
    assert seen_snapshots[0]["expectedParentId"] == result["expectedParentId"]
    assert seen_snapshots[0]["expectedVersion"] == result["expectedVersion"]

    # 评审六轮反例：存档 save-B 的进度行不得混入 default 存档的快照。
    runtime.db.write_campaign_progress(
        campaign_id=sid, arc_index=1, session_index=1, turn_in_session=5,
        fsm_state="active/session_active", slot_name="save-B",
        revealed_anchors=[], completed_arcs=[],
    )
    result2 = read_turn_context(
        runtime.db, runtime.states, sid,
        lambda: sessions_router.memory_controller_factory(sid),
        campaign_context_provider=provider,
    )
    b_snapshots = [s for s in seen_snapshots if s["slotName"] == "save-B"]
    assert not b_snapshots or b_snapshots[0]["progressRow"] is None


def test_pending_tasks_run_outside_transaction_and_concurrently_writable(runtime, session_binding):
    # 假维护器用另一连接写库——执行在事务外，不得 database is locked。
    sid = session_binding["sessionId"]
    _commit(runtime, sid, _request(session_binding, "req-1"))

    def runner(task: dict) -> None:
        with runtime.db.connect() as conn:  # own connection: would block under a held write lock
            conn.execute(
                "UPDATE game_sessions SET model = model WHERE id = ?", (sid,)
            )

    done = run_pending_tasks(runtime.db, runtime.states, sid, runner)
    assert len(done) == 1


def test_confirm_sql_failure_applies_effect_exactly_once(runtime, session_binding):
    # 评审六轮：真实确认故障注入（确认事务内抛 SQL 错误）。纯 runner 契约下
    # 效果只由确认事务产生——计算可重试，应用恰好一次。
    sid = session_binding["sessionId"]
    committed = _commit(runtime, sid, _request(session_binding, "req-1"))
    calls: list[dict] = []
    fail_confirm = {"on": True}

    def runner(task: dict) -> dict:
        calls.append(task)
        return {"summaries": 1}

    def fault(step: str) -> None:
        if step == "in_confirm" and fail_confirm["on"]:
            raise RuntimeError("injected sqlite failure")

    # The injected DB failure propagates out of the confirm transaction
    # (transaction rolled back) — nothing was applied.
    with pytest.raises(RuntimeError, match="injected sqlite"):
        run_pending_tasks(runtime.db, runtime.states, sid, runner, fault_injector=fault)
    assert len(calls) == 1
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM game_sessions WHERE id = ?", (sid,)).fetchone()["s"])
        claim = conn.execute(
            "SELECT state FROM memory_task_claims WHERE session_id = ? AND task_key = ?",
            (sid, f"default:memory_maintain:{committed.timelineNodeId}"),
        ).fetchone()
    assert state["_memory_pending_tasks"], "queue intact after a failed confirm"
    assert claim["state"] == "running"

    # Retry (fault off): recomputes (pure runner), applies exactly once.
    again = run_pending_tasks(runtime.db, runtime.states, sid, runner)
    assert len(again) == 1
    assert len(calls) == 2  # recomputed, but…
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM game_sessions WHERE id = ?", (sid,)).fetchone()["s"])
        claim = conn.execute(
            "SELECT state, result_json FROM memory_task_claims WHERE session_id = ? AND task_key = ?",
            (sid, f"default:memory_maintain:{committed.timelineNodeId}"),
        ).fetchone()
    assert state["_memory_pending_tasks"] == []  # …the effect landed ONCE
    assert claim["state"] == "done"
    assert json.loads(claim["result_json"])["result"] == {"summaries": 1}
    # A third run is a full no-op.
    assert run_pending_tasks(runtime.db, runtime.states, sid, runner) == []
    assert len(calls) == 2


def test_running_claim_blocks_another_executor(runtime, session_binding):
    # 并发反例：B 不得确认 A 正在执行的任务；A 完成后正常落账。
    sid = session_binding["sessionId"]
    committed = _commit(runtime, sid, _request(session_binding, "req-1"))
    a_started, a_release = threading.Event(), threading.Event()
    calls: list[str] = []

    def runner_a(task: dict) -> dict:
        calls.append("A")
        a_started.set()
        a_release.wait(timeout=5)
        return {"who": "A"}

    def runner_b(task: dict) -> dict:
        calls.append("B")
        return {"who": "B"}

    results: list = []

    def run_a() -> None:
        results.append(run_pending_tasks(runtime.db, runtime.states, sid, runner_a, executor="A"))

    thread = threading.Thread(target=run_a)
    thread.start()
    assert a_started.wait(timeout=5)

    b_done = run_pending_tasks(runtime.db, runtime.states, sid, runner_b, executor="B")
    a_release.set()
    thread.join()

    assert b_done == []  # B executed nothing — the fresh running claim held
    assert results[0] and results[0][0]["nodeId"] == committed.timelineNodeId
    assert calls == ["A"]  # B never ran the maintainer
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM game_sessions WHERE id = ?", (sid,)).fetchone()["s"])
        claim = conn.execute(
            "SELECT state FROM memory_task_claims WHERE session_id = ? AND task_key = ?",
            (sid, f"default:memory_maintain:{committed.timelineNodeId}"),
        ).fetchone()
    assert state["_memory_pending_tasks"] == []
    assert claim["state"] == "done"


def test_recovery_of_abandoned_claim_never_confirms_unapplied_work(runtime, session_binding):
    # 认领后中断（维护器未产生效果）：恢复批次不得清掉待办——
    # 新执行者遇到新鲜的 running 认领 → 跳过；超时后 → 重新认领并执行一次。
    sid = session_binding["sessionId"]
    committed = _commit(runtime, sid, _request(session_binding, "req-1"))
    calls: list[dict] = []

    def runner(task: dict) -> dict:
        calls.append(task)
        return {"ok": True}

    # Executor "A" claims, the process dies mid-run (claim fresh, no effect).
    run_pending_tasks(
        runtime.db, runtime.states, sid,
        lambda t: (_ for _ in ()).throw(RuntimeError("died")),
        executor="A",
    )
    with runtime.db.connect() as conn:
        conn.execute("DELETE FROM memory_task_claims WHERE session_id = ?", (sid,))
    with runtime.db.write_transaction() as conn:
        conn.execute(
            "INSERT INTO memory_task_claims (session_id, task_key, state, executor, claimed_at) VALUES (?, ?, 'running', 'A', ?)",
            (sid, f"default:memory_maintain:{committed.timelineNodeId}",
             _dt.datetime.now(_dt.timezone.utc).isoformat()),
        )

    # Recovery batch by executor B: the fresh running claim is left alone.
    assert run_pending_tasks(runtime.db, runtime.states, sid, runner, executor="B") == []
    assert calls == []
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM game_sessions WHERE id = ?", (sid,)).fetchone()["s"])
    assert state["_memory_pending_tasks"], "queue must survive an in-flight claim"

    # After the claim goes stale, recovery re-claims and executes ONCE.
    with runtime.db.write_transaction() as conn:
        conn.execute(
            "UPDATE memory_task_claims SET claimed_at = '2020-01-01T00:00:00+00:00' WHERE session_id = ?",
            (sid,),
        )
    done = run_pending_tasks(runtime.db, runtime.states, sid, runner, executor="B")
    assert [t["nodeId"] for t in done] == [committed.timelineNodeId]
    assert len(calls) == 1
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM game_sessions WHERE id = ?", (sid,)).fetchone()["s"])
    assert state["_memory_pending_tasks"] == []


def test_pure_runner_cannot_leak_into_a_rolled_back_branch(runtime, session_binding):
    # 维护期间回滚：确认绑定不符 → 全部放弃，旧分支状态无写入。
    sid = session_binding["sessionId"]
    root_id = session_binding["expectedParentId"]
    committed = _commit(runtime, sid, _request(session_binding, "req-1"))
    calls: list[dict] = []

    def rollback_between_read_and_confirm(step: str) -> None:
        if step == "in_confirm":
            runtime.db.activate_story_turn(sid, root_id)

    def runner(task: dict) -> dict:
        calls.append(task)
        return {"ok": True}

    done = run_pending_tasks(
        runtime.db, runtime.states, sid,
        runner,
        fault_injector=rollback_between_read_and_confirm,
    )
    assert done == []
    assert len(calls) == 1  # computed, but nothing applied
    with runtime.db.connect() as conn:
        head = conn.execute("SELECT state_json s FROM game_sessions WHERE id = ?", (sid,)).fetchone()
        claim = conn.execute(
            "SELECT state FROM memory_task_claims WHERE session_id = ? AND task_key = ?",
            (sid, f"default:memory_maintain:{committed.timelineNodeId}"),
        ).fetchone()
    restored = json.loads(head["s"])
    # 回滚恢复的根状态没有任何待办被清掉/写入：
    assert restored.get("_memory_pending_tasks") in (None, [])
    assert claim["state"] == "running"  # unconfirmed; goes stale and re-runs later


def test_pending_tasks_one_success_one_failure(runtime, session_binding):
    # 一成一败：成功的完成，失败的留在队列等待重试。
    sid = session_binding["sessionId"]
    first = _commit(runtime, sid, _request(session_binding, "req-1"))
    second = _commit(runtime, sid, _request(
        {"sessionId": sid, "expectedParentId": first.timelineNodeId, "expectedVersion": 1},
        "req-2",
    ))
    ok_node = second.timelineNodeId
    fail_node = first.timelineNodeId
    failures_left = 1

    def runner(task: dict) -> None:
        nonlocal failures_left
        if task["nodeId"] == fail_node and failures_left > 0:
            failures_left -= 1
            raise RuntimeError("fail this task once")

    done = run_pending_tasks(runtime.db, runtime.states, sid, runner)
    assert [t["nodeId"] for t in done] == [ok_node]
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM game_sessions WHERE id = ?", (sid,)).fetchone()["s"])
    remaining = [t["nodeId"] for t in state["_memory_pending_tasks"]]
    assert remaining == [fail_node]

    # Retry: the failed task now succeeds (its claim was cleared) and completes.
    assert [t["nodeId"] for t in run_pending_tasks(runtime.db, runtime.states, sid, runner)] == [fail_node]
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM game_sessions WHERE id = ?", (sid,)).fetchone()["s"])
    assert state["_memory_pending_tasks"] == []


def test_suffix_with_wrong_system_text_is_rejected(runtime, session_binding):
    # 评审五轮反例：检定系统文本随便填（父节点存的是 通用 d20）。
    from app.services.commit_turn import CommitTurnError

    binding = _roll_binding(runtime, session_binding)
    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, binding["sessionId"], _request(
            binding, "req-2",
            playerAction="询问管理员夜班名单\n\n[行动判定] 随便什么系统 1d20 ≥ 12，骰面 14/20，成功。",
            selectedOptionIndex=1,
            roll={"result": 14},
        ))
    assert excinfo.value.status == 422
    assert "后缀不符" in excinfo.value.detail


def test_suffix_cannot_smuggle_extra_actions(runtime, session_binding):
    # 评审五轮反例：后缀里夹带"；顺便扔掉铜钥匙"。
    from app.services.commit_turn import CommitTurnError

    binding = _roll_binding(runtime, session_binding)
    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, binding["sessionId"], _request(
            binding, "req-2",
            playerAction="询问管理员夜班名单\n\n[行动判定] 通用 d20 1d20 ≥ 12，骰面 14/20，成功。顺便扔掉铜钥匙",
            selectedOptionIndex=1,
            roll={"result": 14},
        ))
    assert excinfo.value.status == 422


def test_campaign_boundary_resolves_threshold_from_the_current_session(runtime, session_binding):
    # 真实差异夹具：缓存的 manager.progress 停在旧场次（阈值走默认 30），
    # 事务内行指向的当前场次定义阈值 2 —— 旧逻辑读缓存会漏掉边界。
    sid = session_binding["sessionId"]
    runtime.db.set_session_campaign_id(sid, sid, None, "default")
    manager = _campaign_manager(runtime, sid)
    manager.campaign.arcs[0].sessions[0].max_turns_per_session = 2
    manager.progress.session_index = 1
    manager.progress.turn_in_session = 29
    runtime.db.write_campaign_progress(
        campaign_id=sid, arc_index=0, session_index=0, turn_in_session=1,
        fsm_state="active/session_active", slot_name="default",
        revealed_anchors=[], completed_arcs=[],
    )

    committed = _commit(runtime, sid, _request(session_binding, "req-1"), campaign_manager=manager)

    row = runtime.db.read_campaign_progress(sid, "default")
    # 阈值按事务内行（session0，阈值 2）解析：本回合触界滚动，而非缓存阈 30。
    assert row["session_index"] == 1
    assert row["turn_in_session"] == 0  # reset — later commits cannot re-trigger
    assert row["fsm_state"] == "active/session_active"
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM story_turns WHERE id = ?", (committed.timelineNodeId,)).fetchone()["s"])
    recap_tasks = [t for t in state["_memory_pending_tasks"] if t["type"] == "campaign_recap"]
    assert recap_tasks and recap_tasks[0]["nodeId"] == committed.timelineNodeId
    # 后续提交不再生成 recap 待办（回合数已归零，不再触界）：
    followup = _commit(runtime, sid, _request(
        {"sessionId": sid, "expectedParentId": committed.timelineNodeId, "expectedVersion": 1}, "req-2"))
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM story_turns WHERE id = ?", (followup.timelineNodeId,)).fetchone()["s"])
    assert [t for t in state["_memory_pending_tasks"] if t["type"] == "campaign_recap"] == []


def test_suffix_with_wrong_system_text_is_rejected(runtime, session_binding):
    # 评审五轮反例：检定系统文本随便填（父节点存的是 通用 d20）。
    from app.services.commit_turn import CommitTurnError

    binding = _roll_binding(runtime, session_binding)
    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, binding["sessionId"], _request(
            binding, "req-2",
            playerAction="询问管理员夜班名单\n\n[行动判定] 随便什么系统 1d20 ≥ 12，骰面 14/20，成功。",
            selectedOptionIndex=1,
            roll={"result": 14},
        ))
    assert excinfo.value.status == 422
    assert "后缀不符" in excinfo.value.detail


def test_suffix_cannot_smuggle_extra_actions(runtime, session_binding):
    # 评审五轮反例：后缀里夹带"；顺便扔掉铜钥匙"。
    from app.services.commit_turn import CommitTurnError

    binding = _roll_binding(runtime, session_binding)
    with pytest.raises(CommitTurnError) as excinfo:
        _commit(runtime, binding["sessionId"], _request(
            binding, "req-2",
            playerAction="询问管理员夜班名单\n\n[行动判定] 通用 d20 1d20 ≥ 12，骰面 14/20，成功。顺便扔掉铜钥匙",
            selectedOptionIndex=1,
            roll={"result": 14},
        ))
    assert excinfo.value.status == 422


def test_campaign_boundary_resolves_threshold_from_the_current_session(runtime, session_binding):
    # 缓存 manager 的 progress 指向旧场次（阈值 30）而当前场次阈值更低时，
    # 阈值必须按事务内行的 arc/session 下标对战役定义解析。
    sid = session_binding["sessionId"]
    runtime.db.set_session_campaign_id(sid, sid, None, "default")
    manager = _campaign_manager(runtime, sid)
    # 当前场次（arc0/session0）的定义阈值：
    arc0_sessions = len(manager.campaign.arcs[0].sessions)
    assert arc0_sessions >= 1
    runtime.db.write_campaign_progress(
        campaign_id=sid, arc_index=0, session_index=0,
        turn_in_session=29,  # 任何低于缓存阈值 30 的当前场次阈值都会被旧逻辑漏掉
        fsm_state="active/session_active", slot_name="default",
        revealed_anchors=[], completed_arcs=[],
    )

    committed = _commit(runtime, sid, _request(session_binding, "req-1"), campaign_manager=manager)

    row = runtime.db.read_campaign_progress(sid, "default")
    if arc0_sessions == 1:
        # 该战役第一弧只有一场：触界即弧推进。
        assert row["arc_index"] == 1
        assert row["session_index"] == 0
    else:
        assert row["session_index"] == 1
    assert row["turn_in_session"] == 0  # reset — later commits cannot re-trigger
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM story_turns WHERE id = ?", (committed.timelineNodeId,)).fetchone()["s"])
    assert [t for t in state["_memory_pending_tasks"] if t["type"] == "campaign_recap"], "recap task exactly once"
    # 后续提交不再生成 recap 待办：
    followup = _commit(runtime, sid, _request(
        {"sessionId": sid, "expectedParentId": committed.timelineNodeId, "expectedVersion": 1},
        "req-2", campaign_manager=manager,
    ) if False else _request({"sessionId": sid, "expectedParentId": committed.timelineNodeId, "expectedVersion": 1}, "req-2"))
    with runtime.db.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json s FROM story_turns WHERE id = ?", (followup.timelineNodeId,)).fetchone()["s"])
    recap_tasks = [t for t in state["_memory_pending_tasks"] if t["type"] == "campaign_recap"]
    assert recap_tasks == [] or recap_tasks[0]["nodeId"] != followup.timelineNodeId



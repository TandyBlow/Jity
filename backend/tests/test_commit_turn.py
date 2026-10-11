"""commit-turn fixed-candidate implementation round (design §9).

Ten review-directed scenarios plus turn-context and the campaign row path —
no model calls anywhere: candidates are fixtures, the flow only validates,
merges and commits. Rollback checks cover the three review-required surfaces
(submission record, pending tasks, shared-cache notification).

Direct-service calls (not HTTP) for the transaction/concurrency scenarios;
the FastAPI app is exercised for the endpoint mapping and turn-context.
"""

import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.database import Database
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


# ── 4. 提交途中抛错 → 完整回退（提交记录/待处理任务/共享缓存）──

def test_mid_commit_exception_rolls_back_everything(runtime, session_binding):
    sid = session_binding["sessionId"]

    def boom(step: str) -> None:
        if step == "after_story_turn":
            raise RuntimeError("injected failure")

    with pytest.raises(RuntimeError, match="injected"):
        _commit(runtime, sid, _request(session_binding, "req-1"), fault_injector=boom)

    counts = _counts(runtime.db, sid)
    assert counts["turns"] == 1  # only the root
    assert counts["outputs"] == 0
    assert counts["submissions"] == 0  # submission record rolled back
    assert counts["head"]["h"] == session_binding["expectedParentId"]
    assert counts["head"]["v"] == 0
    # 待处理任务：root 状态里没有任何 _memory_pending_tasks / _memory_controller
    assert "_memory_pending_tasks" not in counts["root_state"]
    assert "_memory_controller" not in counts["root_state"]
    # 共享缓存：post-commit 通知从未发生，工作副本被丢弃
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
    good_action = "询问管理员夜班名单\n\n[行动判定] 调查检定 1d20 ≥ 12，骰面 14/20，成功。"
    ok = _commit(runtime, binding["sessionId"], _request(
        binding, "req-2", playerAction=good_action, selectedOptionIndex=1, roll={"result": 14},
    ))
    assert ok.timelineNodeId > 0

    # Same shape but the text claims 7/大成功 while the roll says 14 → reject.
    bad_action = "询问管理员夜班名单\n\n[行动判定] 调查检定 1d20 ≥ 12，骰面 7/20，大成功。"
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

    action = "询问管理员夜班名单\n\n[行动判定] 调查检定 1d20 ≥ 12，骰面 14/20，成功。"
    original = _request(binding, "req-2", playerAction=action, selectedOptionIndex=1, roll={"result": 14})
    _commit(runtime, binding["sessionId"], original)

    changed = _request(binding, "req-2", playerAction=action, selectedOptionIndex=1, roll={"result": 5})
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

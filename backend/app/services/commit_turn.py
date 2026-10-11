"""commit-turn — the plan-b submission entry (fixed-candidate implementation).

Implements design/component-io-and-commit-turn.md §3/§4/§6 with fixed
candidates: no model calls — the candidate arrives in the request and this
flow only validates, merges and commits. Everything of one submission runs
on ONE SQLite connection (``Database.write_transaction``, BEGIN IMMEDIATE):
idempotency lookup, binding checks, state read, all writes and the
idempotency result save, so a mid-flow failure rolls back together (§4) and
concurrent same-requestId submissions serialize on the database lock.

Ordering invariant (v3 correction): the write transaction opens FIRST and
the idempotency lookup runs BEFORE binding validation — a successful resend
carries the OLD expectedVersion (the head already moved), so binding checks
must never run ahead of the replay short-circuit or resends would 409.
"""

import hashlib
import json
import re
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError

from app.database import Database
from app.exceptions import ConcurrentModificationError
from app.schemas import StoryOutput


class CommitTurnError(Exception):
    """Submission failure mapped to an HTTP status by the router."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class RollReport(BaseModel):
    result: int


class CommitTurnRequest(BaseModel):
    requestId: str
    expectedParentId: int
    expectedVersion: int
    slotName: str = "default"
    playerAction: str
    candidate: dict[str, Any]
    # Top-level since v3: with the index hidden inside roll, omitting the roll
    # made it impossible to tell whether the player skipped a required check.
    selectedOptionIndex: int | None = None
    roll: RollReport | None = None
    audit: dict[str, Any] = Field(default_factory=dict)


class CommitTurnResponse(BaseModel):
    requestId: str
    replayed: bool = False
    timelineNodeId: int
    parentTimelineNodeId: int
    version: int
    output: dict[str, Any]
    state: dict[str, Any]


# ── Digest (§3.1): six dimensions, selectedOptionIndex INDEPENDENT of roll ──

def submission_digest(request: CommitTurnRequest) -> str:
    payload = {
        "playerAction": request.playerAction,
        "slotName": request.slotName,
        "candidate": request.candidate,
        # Independent dimension: a no-check selection has no roll object, so
        # folding the index into roll would drop the selection from the digest.
        "selectedOptionIndex": request.selectedOptionIndex,
        "roll": request.roll.model_dump() if request.roll else None,
        "expectedParentId": request.expectedParentId,
        "expectedVersion": request.expectedVersion,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Selection + roll validation (§3.3): parent's SAVED options only ──

_ACTION_JUDGMENT_RE = re.compile(
    r"\[行动判定\].*?骰面 (\d+)/20，(大成功|成功|失败|大失败)。", re.DOTALL
)


def _outcome_for(roll: int, target: int) -> tuple[str, str]:
    # Same four classes as frontend/src/lib/dice/rules.ts getOutcome.
    if roll == 20:
        return "critical", "大成功"
    if roll == 1:
        return "fumble", "大失败"
    if roll < target:
        return "failure", "失败"
    return "success", "成功"


def validate_selection(parent_output: dict[str, Any], request: CommitTurnRequest) -> dict[str, Any] | None:
    """Validate selectedOptionIndex/roll against the PARENT turn's saved options.

    The candidate's options are NEXT turn's — never used here. option_checks
    entries may be None (the schema allows it): None means no check required.
    Returns the re-derived roll record for the audit, or None when no check.
    """
    from app.schemas.game.story_output import DIFFICULTY_TARGETS

    options = parent_output.get("options") or []
    checks = parent_output.get("option_checks") or []
    idx = request.selectedOptionIndex

    if idx is None:
        if request.roll is not None:
            raise CommitTurnError(422, "自由输入（selectedOptionIndex=null）不得携带 roll")
        return None

    if isinstance(idx, bool) or not isinstance(idx, int) or idx < 0 or idx >= len(options):
        raise CommitTurnError(422, f"selectedOptionIndex {idx} 不在父节点 options 范围内")

    option_text = str(options[idx])
    if request.playerAction != option_text and not request.playerAction.startswith(option_text):
        raise CommitTurnError(422, "playerAction 与所选父节点选项不对应")

    # option_checks[i] is OptionCheck | None: null = 确定性行动，无需检定。
    check = checks[idx] if idx < len(checks) else None
    if check is None or not check.get("requires_check", True):
        if request.roll is not None:
            reason = "option_checks 为 null" if check is None else "requires_check=false"
            raise CommitTurnError(422, f"该选项无需检定（{reason}），禁止携带 roll")
        return None

    if request.roll is None:
        raise CommitTurnError(422, "所选选项要求检定（requires_check=true），但未提交 roll")
    result = request.roll.result
    if isinstance(result, bool) or not isinstance(result, int) or not 1 <= result <= 20:
        raise CommitTurnError(422, "roll.result 必须是 1 到 20 的整数")

    difficulty = check.get("difficulty", "普通")
    target = DIFFICULTY_TARGETS.get(difficulty, DIFFICULTY_TARGETS["普通"])
    outcome, degree = _outcome_for(result, target)

    # The frontend appends "[行动判定] …，骰面 N/20，<档位>。" to the action
    # (checks.ts formatActionWithCheckResult). If present, it must agree with
    # the dice and the server-recomputed outcome — descriptions that disagree
    # with the roll are rejected.
    match = _ACTION_JUDGMENT_RE.search(request.playerAction)
    if match:
        stated_roll, stated_degree = int(match.group(1)), match.group(2)
        if stated_roll != result or stated_degree != degree:
            raise CommitTurnError(
                422,
                f"行动判定描述与骰点不符：骰面 {stated_roll}/{stated_degree}，"
                f"提交 roll {result}/{degree}（target {target}）",
            )

    return {"optionIndex": idx, "target": target, "result": result, "outcome": outcome, "degree": degree}


# ── Name-grounding check (§6): evidence presence and locatability only ──
# A name appearing in the narration does NOT prove the change happened; the
# check verifies that every change carries a locatable textual basis and that
# item changes don't cite opposite-direction verbs. Passing is NOT legality.

_UPSERT_VERBS = ("获得", "捡起", "拿到", "拾起", "收进", "收下", "接过", "递给", "交给", "发现", "找到", "出现", "拿起", "得到")
_REMOVE_VERBS = ("失去", "消耗", "用掉", "用尽", "丢掉", "丢失", "弄丢", "交出", "卖出", "烧毁", "遗落", "掉落", "折断", "碎")


def _iter_candidate_changes(candidate: dict[str, Any]):
    """Yield (path, name, direction) for every change the candidate declares."""
    for i, item in enumerate(candidate.get("items_gained") or []):
        yield f"items_gained.{i}", (item or {}).get("name", ""), "upsert"
    for i, item in enumerate(candidate.get("items_lost") or []):
        yield f"items_lost.{i}", (item or {}).get("name", ""), "remove"
    updates = candidate.get("memory_updates") or {}
    for i, item in enumerate(updates.get("items_upserted") or []):
        yield f"memory_updates.items_upserted.{i}", (item or {}).get("name", ""), "upsert"
    for i, item in enumerate(updates.get("items_removed") or []):
        yield f"memory_updates.items_removed.{i}", (item or {}).get("name", ""), "remove"
    for i, item in enumerate(updates.get("npcs_upserted") or []):
        yield f"memory_updates.npcs_upserted.{i}", (item or {}).get("name", ""), "upsert"
    for i, item in enumerate(updates.get("quests_upserted") or []):
        yield f"memory_updates.quests_upserted.{i}", (item or {}).get("name", ""), "upsert"
    for i, item in enumerate(updates.get("world_facts_upserted") or []):
        yield f"memory_updates.world_facts_upserted.{i}", (item or {}).get("name", ""), "upsert"


def check_grounding(candidate: dict[str, Any], output: StoryOutput, state: dict[str, Any]) -> list[str]:
    """Return a list of grounding issues; empty means the check passed."""
    def _dialogue_text(line: Any) -> str:
        return line.get("text", "") if isinstance(line, dict) else line.text

    prose = output.narration + "\n" + "\n".join(
        _dialogue_text(line) for line in (output.dialogue or [])
    )
    roster: set[str] = set()
    for key in ("items", "npcs", "quests", "world_facts"):
        for entry in state.get(key) or []:
            if isinstance(entry, dict) and entry.get("name"):
                roster.add(str(entry["name"]))

    bases = {
        entry.get("path"): str(entry.get("basis", ""))
        for entry in (candidate.get("changeBases") or [])
        if isinstance(entry, dict)
    }

    issues: list[str] = []
    for path, name, direction in _iter_candidate_changes(candidate):
        if not name:
            issues.append(f"{path}: 变更缺少实体名")
            continue
        basis = bases.get(path, "")
        if not basis:
            issues.append(f"{path} ({name}): 缺少正文依据")
            continue
        if basis not in prose and name not in roster:
            issues.append(f"{path} ({name}): 正文依据在过检正文与名册中均不可定位")
            continue
        # Direction pairing applies to item changes only (§6 minimal port of
        # the labeler's verb-field pairing); npc/quest/fact entries are
        # presence+base checks only.
        if not path.startswith("items_"):
            continue
        has_upsert_verb = any(verb in basis for verb in _UPSERT_VERBS)
        has_remove_verb = any(verb in basis for verb in _REMOVE_VERBS)
        if direction == "remove" and has_upsert_verb and not has_remove_verb:
            issues.append(f"{path} ({name}): 移除类变更的依据是获得类表述")
        if direction == "upsert" and has_remove_verb and not has_upsert_verb:
            issues.append(f"{path} ({name}): 获得类变更的依据是失去类表述")
    return issues


# ── Working-copy helpers (§4) ──

def merge_npc_relations(
    relations: list[dict[str, Any]], deltas: list[dict[str, Any]] | None, turn: int
) -> list[dict[str, Any]]:
    """Port of post_generation._process_npc_relations_delta, connection-free."""
    by_name: dict[str, dict[str, Any]] = {
        r.get("name"): dict(r) for r in relations if isinstance(r, dict) and r.get("name")
    }
    for delta in deltas or []:
        name = delta.get("name", "")
        if not name:
            continue
        entry = by_name.setdefault(
            name, {"name": name, "affinity": 0, "last_interaction_turn": turn, "note": ""}
        )
        sentiment = delta.get("sentiment", "neutral")
        if sentiment == "positive":
            entry["affinity"] = min(entry.get("affinity", 0) + 1, 10)
        elif sentiment == "negative":
            entry["affinity"] = max(entry.get("affinity", 0) - 1, -10)
        entry["last_interaction_turn"] = turn
        entry["note"] = delta.get("note", "") or entry.get("note", "")
    return list(by_name.values())


def _turn_metrics(output: StoryOutput, state: dict[str, Any]) -> dict[str, int]:
    """Port of CampaignManager.record_turn — pure statistics, no anchor mutation."""
    location_before = state.get("current_location", "")
    location_after = output.current_location or location_before
    return {
        "word_count": len(output.narration),
        "option_count": len(output.options or []),
        "sanity_delta": output.sanity_delta,
        "health_delta": output.health_delta,
        "dialogue_lines": len(output.dialogue or []),
        "location_changed": 1 if location_after != location_before else 0,
        "token_count": 0,
    }


# ── Main flow ──

def commit_turn(
    db: Database,
    state_manager: Any,
    session_id: str,
    request: CommitTurnRequest,
    *,
    model: str,
    source: str,
    memory_controller_factory: Callable[[], Any],
    post_commit: Callable[[CommitTurnResponse], None] | None = None,
    fault_injector: Callable[[str], None] | None = None,
) -> CommitTurnResponse:
    """Validate, merge and commit one fixed-candidate submission.

    ``fault_injector`` is a test-only hook: named steps ("before_merge",
    "after_model_output", "after_story_turn") raise RuntimeError when the
    injector fires, so rollback tests can cut the flow mid-transaction.
    Production callers never pass it.
    """
    def fault(step: str) -> None:
        if fault_injector is not None:
            fault_injector(step)

    digest = submission_digest(request)

    with db.write_transaction() as conn:
        # 1. Idempotency FIRST — before binding (a successful resend carries
        #    the old expectedVersion; §3.1 three-branch semantics).
        row = conn.execute(
            "SELECT content_digest, result_json FROM turn_submissions WHERE session_id = ? AND request_id = ?",
            (session_id, request.requestId),
        ).fetchone()
        if row is not None:
            if row["content_digest"] == digest:
                stored = CommitTurnResponse.model_validate(json.loads(row["result_json"]))
                stored.replayed = True
                return stored
            raise CommitTurnError(409, "requestId 已被不同内容使用（内容摘要不匹配）")

        # 2. Binding: parent + version + slot (all reads on the same connection).
        session = conn.execute(
            "SELECT * FROM game_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session is None:
            raise CommitTurnError(404, "Session not found")
        if (session["active_turn_id"] or 0) != request.expectedParentId:
            raise CommitTurnError(
                409,
                f"会话头已变化：active_turn_id={session['active_turn_id']}，"
                f"expectedParentId={request.expectedParentId}",
            )
        if int(session["version"]) != request.expectedVersion:
            raise CommitTurnError(
                409,
                f"会话版本不匹配：version={session['version']}，expectedVersion={request.expectedVersion}"
                "（推进后回滚的迟到提交在此被拒）",
            )
        if (session["active_slot_name"] or "default") != request.slotName:
            raise CommitTurnError(
                409,
                f"存档不匹配：active_slot_name={session['active_slot_name']}，slotName={request.slotName}",
            )

        parent = conn.execute(
            "SELECT * FROM story_turns WHERE id = ? AND session_id = ?",
            (request.expectedParentId, session_id),
        ).fetchone()
        if parent is None:
            raise CommitTurnError(404, "父节点不存在")
        parent_output = json.loads(parent["output_json"] or "{}")

        # 3. Candidate → StoryOutput; sanitize is an EXPLICIT call — neither
        #    the conversion nor pydantic validation runs replace_em_dashes.
        try:
            output = StoryOutput.model_validate(request.candidate)
        except ValidationError as exc:
            raise CommitTurnError(422, f"候选不符合 StoryOutput 约定：{exc}") from exc
        output.replace_em_dashes()

        roll_record = validate_selection(parent_output, request)

        state = json.loads(session["state_json"])
        issues = check_grounding(request.candidate, output, state)
        if issues:
            raise CommitTurnError(422, "名称出处检查未通过：" + "；".join(issues))

        fault("before_merge")

        # 4. Deterministic merge (pure function on the in-transaction state).
        next_state = state_manager.apply_output(state, request.playerAction, output)

        # 5. Memory working copy: build from the in-transaction snapshot, feed
        #    the turn synchronously, save the updated snapshot WITH the turn —
        #    the saved snapshot must not miss the current turn (§4).
        controller = memory_controller_factory()
        controller.load_state(state.get("_memory_controller") or {})
        controller.on_turn_generated(
            request.playerAction,
            output.narration,
            int(next_state.get("turn", 0)),
            memory_updates=output.memory_updates,
        )
        next_state["_memory_controller"] = controller.export_state()

        # 6. Campaign working row: read in-transaction, mutate the copy only.
        campaign_id = session["campaign_id"]
        progress_payload = None
        if campaign_id:
            progress_row = db.read_campaign_progress(campaign_id, request.slotName, conn=conn)
            if progress_row:
                relations = json.loads(progress_row.get("npc_relations") or "[]")
                relations = merge_npc_relations(relations, output.npc_relations_delta, int(next_state.get("turn", 0)))
                progress_payload = {
                    "campaign_id": campaign_id,
                    "slot_name": request.slotName,
                    "arc_index": int(progress_row["arc_index"]),
                    "session_index": int(progress_row["session_index"]),
                    "turn_in_session": int(progress_row["turn_in_session"]) + 1,
                    "fsm_state": progress_row["fsm_state"],
                    "revealed_anchors": progress_row["revealed_anchors"],
                    "completed_arcs": progress_row["completed_arcs"],
                    "recap_compressed": progress_row["recap_compressed"] or "",
                    "recap_full": progress_row["recap_full"] or "",
                    "npc_relations": json.dumps(relations, ensure_ascii=False),
                }
            else:
                progress_payload = {
                    "campaign_id": campaign_id,
                    "slot_name": request.slotName,
                    "turn_in_session": 1,
                    "npc_relations": json.dumps([], ensure_ascii=False),
                }

        # 7. Writes — every one on the SAME connection (§4).
        metrics = _turn_metrics(output, state)
        output_id = db.add_model_output(
            session_id=session_id,
            model=model,
            input_text=request.playerAction,
            output=output.model_dump(),
            latency_ms=0,
            source=source,
            status="ok",
            raw_output_text=output.model_dump_json(),
            prompt_sections=None,
            prompt_text="",
            conn=conn,
            **metrics,
        )
        fault("after_model_output")

        turn_id = db.commit_story_turn(
            conn=conn,
            session_id=session_id,
            expected_parent_id=request.expectedParentId,
            player_action=request.playerAction,
            output=output.model_dump(),
            state=next_state,
            campaign_progress=progress_payload,
            model=model,
            source=source,
            model_output_id=output_id,
            campaign_session_index=0,
        )
        fault("after_story_turn")

        # 8. Pending maintenance tasks, bound to slot + node, persisted with
        #    the turn so a restart can resume them (§4). The node id only
        #    exists after the insert, hence the in-transaction update.
        next_state["_memory_pending_tasks"] = [
            {"type": "memory_maintain", "slot": request.slotName, "nodeId": turn_id, "turn": int(next_state.get("turn", 0))}
        ]
        state_json = json.dumps(next_state, ensure_ascii=False)
        conn.execute("UPDATE story_turns SET state_json = ? WHERE id = ?", (state_json, turn_id))
        conn.execute("UPDATE game_sessions SET state_json = ? WHERE id = ?", (state_json, session_id))

        # 9. Idempotency result — same connection, before the commit.
        new_version = int(
            conn.execute("SELECT version FROM game_sessions WHERE id = ?", (session_id,)).fetchone()["version"]
        )
        response = CommitTurnResponse(
            requestId=request.requestId,
            replayed=False,
            timelineNodeId=turn_id,
            parentTimelineNodeId=request.expectedParentId,
            version=new_version,
            output=output.model_dump(),
            state=state_manager.sanitize_state(next_state),
        )
        conn.execute(
            "INSERT INTO turn_submissions (session_id, request_id, content_digest, result_json) VALUES (?, ?, ?, ?)",
            (session_id, request.requestId, digest, response.model_dump_json()),
        )

    # Post-commit (outside the transaction): shared-cache swap / pending-task
    # dispatch would hook here; fixed-candidate round only notifies the caller.
    if post_commit is not None:
        post_commit(response)
    return response


def read_turn_context(db: Database, session_id: str) -> dict[str, Any]:
    """One consistent read of everything the component loop binds to (§3.2)."""
    with db.connect() as conn:
        session = conn.execute(
            "SELECT * FROM game_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session is None:
            raise CommitTurnError(404, "Session not found")
        messages = conn.execute(
            "SELECT role, content FROM session_messages WHERE session_id = ? ORDER BY id DESC LIMIT 10",
            (session_id,),
        ).fetchall()

    return {
        "sessionId": session_id,
        "slotName": session["active_slot_name"] or "default",
        "expectedParentId": session["active_turn_id"],
        "expectedVersion": int(session["version"]),
        "state": json.loads(session["state_json"]),
        "recentMessages": [
            {"role": m["role"], "content": m["content"]} for m in reversed(messages)
        ],
    }

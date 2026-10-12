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
from typing import Any, Callable

from pydantic import BaseModel, Field, StrictInt, ValidationError

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
    # StrictInt: lax pydantic coerces bool->int (True becomes 1), which would
    # let a JSON `true` masquerade as a natural 1 (review round 4).
    result: StrictInt


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

# The canonical suffix the frontend appends (checks.ts formatActionWithCheckResult):
# exactly "\n\n[行动判定] {system} 1d20 ≥ {target}，骰面 {roll}/20，{degree}。"
# — rebuilt from the parent's check metadata and compared as a WHOLE string.
def _expected_judgment_suffix(check: dict[str, Any], target: int, result: int, degree: str) -> str:
    """The EXACT suffix the frontend appends (checks.ts formatActionWithCheckResult).

    Rebuilt from the PARENT's saved check metadata + the server-derived
    target so the comparison is over the whole literal string — review
    round 5: the previous regex accepted any system text (`.{+}`) and let
    extra actions ride inside it.
    """
    system = check.get("system", "通用 d20")
    return f"\n\n[行动判定] {system} 1d20 ≥ {target}，骰面 {result}/20，{degree}。"


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
    The action must be EXACTLY the bare option text or the option text plus the
    canonical judgment suffix — startswith-style acceptance let arbitrary
    trailing text ride along (review round 4). Returns the re-derived roll
    record for the audit, or None when no check.
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
    # option_checks[i] is OptionCheck | None: null = 确定性行动，无需检定。
    check = checks[idx] if idx < len(checks) else None
    requires_check = bool(check and check.get("requires_check", True))

    roll_record: dict[str, Any] | None = None
    if requires_check:
        difficulty = check.get("difficulty", "普通")
        target = DIFFICULTY_TARGETS.get(difficulty, DIFFICULTY_TARGETS["普通"])
        if request.roll is None:
            raise CommitTurnError(422, "所选选项要求检定（requires_check=true），但未提交 roll")
        result = request.roll.result
        if not 1 <= result <= 20:
            raise CommitTurnError(422, "roll.result 必须是 1 到 20 的整数")
        outcome, degree = _outcome_for(result, target)
        roll_record = {
            "optionIndex": idx,
            "target": target,
            "result": result,
            "outcome": outcome,
            "degree": degree,
        }
    elif request.roll is not None:
        reason = "option_checks 为 null" if check is None else "requires_check=false"
        raise CommitTurnError(422, f"该选项无需检定（{reason}），禁止携带 roll")

    # Action correspondence: bare option, or option + EXACT canonical suffix
    # rebuilt from the parent's saved check metadata (system/target included).
    if request.playerAction == option_text:
        pass
    elif request.playerAction.startswith(option_text + "\n\n[行动判定] ") and roll_record is not None:
        expected_suffix = _expected_judgment_suffix(
            check, roll_record["target"], roll_record["result"], roll_record["degree"]
        )
        if request.playerAction != option_text + expected_suffix:
            raise CommitTurnError(
                422,
                "行动判定后缀不符：必须是「\\n\\n[行动判定] {检定系统} 1d20 ≥ {重算阈值}，骰面 {提交骰点}/20，{重算档位}。」的逐字符匹配，不得夹带其他文本",
            )
    elif request.playerAction.startswith(option_text + "\n\n[行动判定] ") and roll_record is None:
        raise CommitTurnError(422, "行动判定后缀出现在无需检定的选项上")
    else:
        raise CommitTurnError(
            422,
            "playerAction 与所选父节点选项不对应：只接受裸选项文本，或选项文本加上完整规范的行动判定后缀",
        )

    return roll_record


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
    for i, item in enumerate(candidate.get("npcs_encountered") or []):
        yield f"npcs_encountered.{i}", (item or {}).get("name", ""), "upsert"
    for i, item in enumerate(candidate.get("quests_updated") or []):
        yield f"quests_updated.{i}", (item or {}).get("name", ""), "upsert"
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


def _is_item_path(path: str) -> bool:
    # Covers top-level items_gained/lost AND the nested memory_updates items.
    return ".items_" in f"{path}." or path.startswith("items_")


def check_grounding(candidate: dict[str, Any], output: StoryOutput, state: dict[str, Any]) -> list[str]:
    """Return a list of grounding issues; empty means the check passed.

    Name grounding and basis grounding are checked INDEPENDENTLY (review
    round 4): a real basis no longer rescues a fabricated name, and a roster
    name no longer rescues a nonexistent basis.
    """
    def _dialogue_text(line: Any) -> str:
        return line.get("text", "") if isinstance(line, dict) else line.text

    prose = output.narration + "\n" + "\n".join(
        _dialogue_text(line) for line in (output.dialogue or [])
    )
    roster_names: set[str] = set()
    roster_texts: list[str] = []
    for key in ("items", "npcs", "quests", "world_facts"):
        for entry in state.get(key) or []:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            roster_names.add(str(entry["name"]))
            roster_texts.append(" ".join(str(v) for v in entry.values() if isinstance(v, str)))
    roster_text = "\n".join(roster_texts)

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
        # Check 1 — name grounding: the entity must appear in the passed prose
        # or the roster. Independent of the basis.
        name_ok = name in prose or name in roster_names
        if not name_ok:
            issues.append(f"{path} ({name}): 实体名在过检正文与名册中均无出处")
        # Check 2 — basis grounding: the cited textual basis must itself be
        # locatable in the prose or the roster. Independent of the name.
        basis = bases.get(path, "")
        basis_ok = bool(basis) and (basis in prose or basis in roster_text)
        if not basis_ok:
            issues.append(f"{path} ({name}): 正文依据缺失或不可定位")
        if not (name_ok and basis_ok):
            continue
        # Direction pairing applies to item changes only (§6 minimal port of
        # the labeler's verb-field pairing) — including nested memory_updates
        # items; npc/quest/fact entries are presence+base checks only.
        if not _is_item_path(path):
            continue
        has_upsert_verb = any(verb in basis for verb in _UPSERT_VERBS)
        has_remove_verb = any(verb in basis for verb in _REMOVE_VERBS)
        if direction == "remove" and has_upsert_verb and not has_remove_verb:
            issues.append(f"{path} ({name}): 移除类变更的依据是获得类表述")
        if direction == "upsert" and has_remove_verb and not has_upsert_verb:
            issues.append(f"{path} ({name}): 获得类变更的依据是失去类表述")
    return issues


# ── Working-copy helpers (§4) ──

def _resolve_max_turns(campaign_def: Any, arc_index: int, session_index: int) -> int:
    """Threshold precedence chain, evaluated on STATIC campaign definition.

    The cached manager's progress row may point at an older session (review
    round 5: current-session threshold 2, cached progress returned 30) — the
    threshold must always come from the IN-TRANSACTION row's arc/session
    indexes against the campaign definition: per-session override, then
    campaign-level default, then option_config.json, then 30.
    """
    import logging
    from pathlib import Path

    logger = logging.getLogger(__name__)
    if campaign_def is not None:
        try:
            session = campaign_def.arcs[arc_index].sessions[session_index]
            session_max = getattr(session, "max_turns_per_session", None)
            if session_max is not None:
                return int(session_max)
        except (IndexError, AttributeError):
            pass
        campaign_max = getattr(campaign_def, "max_turns_per_session", None)
        if campaign_max is not None:
            return int(campaign_max)
    try:
        config_path = Path(__file__).resolve().parents[2] / "scripts" / "option_config.json"
        if config_path.exists():
            import json as _json

            config = _json.loads(config_path.read_text(encoding="utf-8"))
            return int(config.get("max_turns_per_session", 30))
    except Exception:
        logger.debug("option_config.json load failed", exc_info=True)
    return 30


def _advance_progress_row(
    progress_row: dict[str, Any],
    campaign_def: Any,
    relations_json: str,
    turn: int,
) -> tuple[dict[str, Any], bool]:
    """Deterministic §4 advancement on the IN-TRANSACTION progress row.

    Mirrors campaign_advancer.advance_turn/advance_session/advance_arc
    (counters and boundary state only; recap GENERATION stays post-commit):
    turn counter +1; at the session threshold the session (or arc) rolls —
    session_index +1 or arc_index +1 with session reset — turn_in_session
    resets to 0 so later commits cannot re-trigger the boundary. Returns
    (row payload, session_rolled).
    """
    arc_index = int(progress_row["arc_index"])
    session_index = int(progress_row["session_index"])
    turn_in_session = int(progress_row["turn_in_session"]) + 1
    completed_arcs = json.loads(progress_row["completed_arcs"] or "[]")
    revealed = progress_row["revealed_anchors"] or "[]"

    max_turns = _resolve_max_turns(campaign_def, arc_index, session_index)
    session_rolled = False
    if max_turns and turn_in_session >= max_turns:
        session_rolled = True
        try:
            arc_sessions = len(campaign_def.arcs[arc_index].sessions) if campaign_def is not None else 0
        except (IndexError, AttributeError):
            arc_sessions = 0
        if campaign_def is None or session_index + 1 >= arc_sessions:
            # Arc boundary: production end_session→arc_transition→begin_arc→
            # session_active; deterministic half = counters + completed list.
            completed_arcs = sorted({*completed_arcs, arc_index})
            arc_index += 1
            session_index = 0
            fsm_state = "active/session_active"
        else:
            # Normal session boundary: end_session→resume_session.
            session_index += 1
            fsm_state = "active/session_active"
        turn_in_session = 0
    else:
        fsm_state = str(progress_row["fsm_state"] or "active/session_active")

    payload = {
        "campaign_id": progress_row["campaign_id"],
        "slot_name": progress_row["slot_name"],
        "arc_index": arc_index,
        "session_index": session_index,
        "turn_in_session": turn_in_session,
        "fsm_state": fsm_state,
        "revealed_anchors": revealed,
        "completed_arcs": json.dumps(completed_arcs, ensure_ascii=False),
        "recap_compressed": progress_row["recap_compressed"] or "",
        "recap_full": progress_row["recap_full"] or "",
        "npc_relations": relations_json,
    }
    return payload, session_rolled


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
    campaign_manager: Any | None = None,
    post_commit: Callable[[CommitTurnResponse], None] | None = None,
    fault_injector: Callable[[str], None] | None = None,
) -> CommitTurnResponse:
    """Validate, merge and commit one fixed-candidate submission.

    ``campaign_manager`` (optional) supplies the campaign-definition side of
    the deterministic advancement: pending anchor triggers and
    resolve_max_turns. Counters and boundary states are still written ONLY
    through the in-transaction progress row — the manager's in-memory
    progress is never trusted (§4).

    ``fault_injector`` is a test-only hook: named steps ("before_merge",
    "after_model_output", "after_story_turn", "after_submission_row") raise
    RuntimeError when the injector fires, so rollback tests can cut the flow
    mid-transaction. Production callers never pass it.
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
        #    Deterministic advancement per §4 — turn counter, pending anchors,
        #    and the session/arc boundary roll all computed from the
        #    IN-TRANSACTION row (the cached manager's progress is stale the
        #    moment another window commits); recap generation stays post-commit.
        campaign_id = session["campaign_id"]
        progress_payload = None
        session_rolled = False
        messages_session_index = 0
        campaign_def = campaign_manager.campaign if campaign_manager is not None else None
        if campaign_id:
            progress_row = db.read_campaign_progress(campaign_id, request.slotName, conn=conn)
            if progress_row:
                relations = json.loads(progress_row.get("npc_relations") or "[]")
                relations = merge_npc_relations(relations, output.npc_relations_delta, int(next_state.get("turn", 0)))
                if campaign_manager is not None:
                    # Pending anchors from THIS turn's direction stage — the
                    # manager's in-memory list is read-only here; merging into
                    # the row keeps the single-connection discipline.
                    current = json.loads(progress_row["revealed_anchors"] or "[]")
                    changed = False
                    for anchor_id, _turn in campaign_manager.pending_anchor_triggers:
                        if anchor_id not in current:
                            current.append(anchor_id)
                            changed = True
                    if changed:
                        progress_row = {
                            **progress_row,
                            "revealed_anchors": json.dumps(current, ensure_ascii=False),
                        }
                messages_session_index = int(progress_row["session_index"])
                progress_payload, session_rolled = _advance_progress_row(
                    progress_row, campaign_def, json.dumps(relations, ensure_ascii=False), int(next_state.get("turn", 0))
                )
            else:
                progress_payload = {
                    "campaign_id": campaign_id,
                    "slot_name": request.slotName,
                    "turn_in_session": 1,
                    "npc_relations": json.dumps([], ensure_ascii=False),
                }

        # 7. Writes — every one on the SAME connection (§4). The audit entry
        #    and the server-recomputed roll record persist with the turn.
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
            audit_json=json.dumps(
                {"audit": request.audit, "roll": roll_record},
                ensure_ascii=False,
            ),
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
            # Messages belong to the session the turn was played IN — the
            # pre-rollover session index, not the head's default (review 4).
            campaign_session_index=messages_session_index,
        )
        fault("after_story_turn")

        # 8. Pending maintenance tasks: carry over the head's unfinished tasks
        #    (overwrite here was losing them every turn — review round 4) and
        #    append this turn's, bound to slot + node. The node id only exists
        #    after the insert, hence the in-transaction backfill.
        carried = list(state.get("_memory_pending_tasks") or [])
        new_tasks = [
            {"type": "memory_maintain", "slot": request.slotName, "nodeId": turn_id, "turn": int(next_state.get("turn", 0))}
        ]
        if progress_payload is not None and session_rolled:
            new_tasks.append(
                {"type": "campaign_recap", "slot": request.slotName, "nodeId": turn_id, "turn": int(next_state.get("turn", 0))}
            )
        next_state["_memory_pending_tasks"] = carried + new_tasks
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
        fault("after_submission_row")

    # Post-commit (outside the transaction): shared-cache swap / pending-task
    # dispatch would hook here; fixed-candidate round only notifies the caller.
    if post_commit is not None:
        post_commit(response)
    return response


def read_turn_context(
    db: Database,
    state_manager: Any,
    session_id: str,
    memory_controller_factory: Callable[[], Any],
    campaign_context_provider: Callable[[dict[str, Any], int], str] | None = None,
) -> dict[str, Any]:
    """One consistent read of everything the component loop binds to (§3.2).

    An explicit read transaction keeps the session row, the ancestor walk and
    the message query on one snapshot. Messages are filtered to the CURRENT
    head's ancestor chain AND the HEAD node's campaign session index — the
    index is taken from the head only (review round 5: walking ancestors and
    overwriting the index each step returned the OLDEST session's messages);
    the ancestor set exists solely to select which message rows belong to
    this playthrough. The state is sanitized before return.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")  # explicit read transaction: one snapshot
        session = conn.execute(
            "SELECT * FROM game_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session is None:
            raise CommitTurnError(404, "Session not found")
        head = conn.execute(
            "SELECT id, parent_turn_id, campaign_progress_json FROM story_turns WHERE id = ? AND session_id = ?",
            (session["active_turn_id"], session_id),
        ).fetchone()
        if head is None:
            raise CommitTurnError(404, "Timeline node not found")
        head_progress = json.loads(head["campaign_progress_json"] or "{}")
        campaign_session_index = int(head_progress.get("session_index", 0))
        ancestors: list[int] = []
        node_id: int | None = int(head["id"])
        while node_id is not None:
            ancestors.append(node_id)
            node = conn.execute(
                "SELECT parent_turn_id FROM story_turns WHERE id = ? AND session_id = ?",
                (node_id, session_id),
            ).fetchone()
            if node is None:
                break
            node_id = node["parent_turn_id"]
        placeholders = ",".join("?" * len(ancestors)) or "NULL"
        messages = conn.execute(
            f"""
            SELECT role, content FROM session_messages
            WHERE session_id = ? AND campaign_session_index = ?
              AND turn_node_id IN ({placeholders})
            ORDER BY id
            """,
            (session_id, campaign_session_index, *ancestors),
        ).fetchall()
        conn.commit()

    state = json.loads(session["state_json"])
    # campaignContext: memory part assembled offline from the in-snapshot
    # controller (no LLM); the campaign part (scene/goal/anchors) comes from
    # the provider — production's campaign_manager.inject_context (review 5:
    # the memory-only render left 当前场景/目标/锚点 out of the context).
    try:
        controller = memory_controller_factory()
        controller.load_state(state.get("_memory_controller") or {})
        campaign_context = controller.assemble_context(state, int(state.get("turn", 0)))
    except Exception:
        campaign_context = ""
    if campaign_context_provider is not None:
        try:
            injected = campaign_context_provider(state, int(state.get("turn", 0)))
            if injected:
                campaign_context = f"{injected}\n\n{campaign_context}" if campaign_context else injected
        except Exception:
            pass

    return {
        "sessionId": session_id,
        "slotName": session["active_slot_name"] or "default",
        "expectedParentId": session["active_turn_id"],
        "expectedVersion": int(session["version"]),
        "state": state_manager.sanitize_state(state),
        "campaignContext": campaign_context,
        "recentMessages": [{"role": m["role"], "content": m["content"]} for m in messages],
    }


def run_pending_tasks(
    db: Database,
    state_manager: Any,
    session_id: str,
    runner: Callable[[dict[str, Any]], None],
) -> list[dict[str, Any]]:
    """Execute the head's pending maintenance tasks; at-most-once per key (§4).

    Review round 5: the maintainer runs OUTSIDE any transaction (a runner
    that writes through its own connection used to deadlock on the write
    lock), and task identity — not queue removal — prevents re-execution:
    each task key is CLAIMED in a short transaction BEFORE the runner fires.
    If the post-run confirmation fails (review round 5's injected fault),
    the claim survives, so a retry re-confirms without re-running. A runner
    that itself failed has its claim cleared and may retry.

    Flow per batch: read head snapshot → claim (short txn) → run (no txn) →
    confirm (short txn: re-check head node/slot/version, remove completed
    tasks from the head snapshot, game_sessions and the head row together).
    """
    with db.connect() as conn:
        session = conn.execute(
            "SELECT active_turn_id, active_slot_name, version, state_json FROM game_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            raise CommitTurnError(404, "Session not found")
        state = json.loads(session["state_json"])
        pending = list(state.get("_memory_pending_tasks") or [])
    if not pending:
        return []

    slot = session["active_slot_name"] or "default"
    binding = (session["active_turn_id"], slot, int(session["version"]))

    def task_key(task: dict[str, Any]) -> str:
        return f"{task.get('slot', slot)}:{task.get('type', 'unknown')}:{task.get('nodeId')}"

    # 1. Claim: INSERT OR IGNORE the keys in a short write transaction. Only
    #    FRESHLY inserted rows authorize execution — a leftover claim from a
    #    previous batch whose confirm failed must NOT re-run the maintainer;
    #    it goes straight to confirmation (review round 5's injected fault).
    fresh_keys: set[str] = set()
    with db.write_transaction() as conn:
        for task in pending:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO memory_task_claims (session_id, task_key) VALUES (?, ?)",
                (session_id, task_key(task)),
            )
            if cursor.rowcount == 1:
                fresh_keys.add(task_key(task))

    # 2. Run OUTSIDE any transaction; only freshly claimed tasks execute —
    #    previously claimed leftovers (confirm failed last round) go straight
    #    to confirmation without re-running the maintainer.
    executed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for task in pending:
        if task_key(task) not in fresh_keys:
            continue
        try:
            runner(task)
            executed.append(task)
        except Exception:
            failed.append(task)

    # 3. Runner failed → clear its claim so a later retry may run it again
    #    (its effect never happened).
    if failed:
        with db.write_transaction() as conn:
            for task in failed:
                conn.execute(
                    "DELETE FROM memory_task_claims WHERE session_id = ? AND task_key = ?",
                    (session_id, task_key(task)),
                )

    # 4. Confirm: short transaction re-checking the binding read in step 0.
    #    Removes from the queue: freshly executed tasks AND leftover-claim
    #    tasks (their effect was applied in an earlier batch — the surviving
    #    claim is the proof; the earlier confirm just failed).
    leftovers = [t for t in pending if task_key(t) not in fresh_keys and t not in failed]
    completed = executed
    if executed or leftovers:
        with db.write_transaction() as conn:
            current = conn.execute(
                "SELECT active_turn_id, active_slot_name, version, state_json FROM game_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            current_binding = (current["active_turn_id"], current["active_slot_name"] or "default", int(current["version"]))
            if current_binding != binding:
                # Head moved between read and confirm: leave everything as is;
                # the next batch re-reads the (new) head's queue.
                return []
            state = json.loads(current["state_json"])
            done_keys = {task_key(t) for t in executed} | {task_key(t) for t in leftovers}
            kept = [t for t in (state.get("_memory_pending_tasks") or []) if task_key(t) not in done_keys]
            state["_memory_pending_tasks"] = kept
            state_json = json.dumps(state, ensure_ascii=False)
            conn.execute("UPDATE game_sessions SET state_json = ? WHERE id = ?", (state_json, session_id))
            conn.execute(
                "UPDATE story_turns SET state_json = ? WHERE id = ? AND session_id = ?",
                (state_json, current["active_turn_id"], session_id),
            )
    return completed


def recover_pending_tasks(
    db: Database,
    state_manager: Any,
    runner: Callable[[dict[str, Any]], None],
) -> dict[str, list[dict[str, Any]]]:
    """Startup recovery entry: execute every session's pending tasks (§4).

    Scans game_sessions for persisted task lists, runs each through the same
    runner, and returns the completions per session. Restart-safe: tasks
    already executed are gone from their snapshot; failed ones stay pending.
    """
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id FROM game_sessions WHERE state_json LIKE '%\"_memory_pending_tasks\"%'"
        ).fetchall()
    completed: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        session_id = row["id"]
        done = run_pending_tasks(db, state_manager, session_id, runner)
        if done:
            completed[session_id] = done
    return completed

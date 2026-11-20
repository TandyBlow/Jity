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

import datetime as _dt
import hashlib
import json
from copy import deepcopy
from typing import Any, Callable
from uuid import uuid4

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
    the deterministic advancement: anchor definitions and turn thresholds.
    Counters and boundary states are still written ONLY
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
        messages_arc_index = 0
        campaign_def = campaign_manager.campaign if campaign_manager is not None else None
        if campaign_id:
            progress_row = db.read_campaign_progress(campaign_id, request.slotName, conn=conn)
            if progress_row:
                relations = json.loads(progress_row.get("npc_relations") or "[]")
                relations = merge_npc_relations(relations, output.npc_relations_delta, int(next_state.get("turn", 0)))
                if campaign_def is not None:
                    from app.schemas.campaign import CampaignProgress
                    from app.services.campaign_anchors import CampaignAnchorEvaluator

                    current = json.loads(progress_row["revealed_anchors"] or "[]")
                    progress_copy = CampaignProgress(
                        campaign_id=campaign_id,
                        arc_index=int(progress_row["arc_index"]),
                        session_index=int(progress_row["session_index"]),
                        turn_in_session=int(progress_row["turn_in_session"]),
                        revealed_anchors=current,
                        completed_arcs=json.loads(progress_row["completed_arcs"] or "[]"),
                    )
                    anchors = CampaignAnchorEvaluator().evaluate_anchors(
                        campaign_def, progress_copy, state, progress_copy.turn_in_session,
                        revealed_anchors=current,
                    )
                    if anchors:
                        current.append(anchors[0].id)
                        progress_row = {
                            **progress_row,
                            "revealed_anchors": json.dumps(current, ensure_ascii=False),
                        }
                messages_session_index = int(progress_row["session_index"])
                messages_arc_index = int(progress_row["arc_index"])
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
            campaign_arc_index=messages_arc_index,
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
    campaign_context_provider: Callable[[dict[str, Any], int, dict[str, Any]], str] | None = None,
) -> dict[str, Any]:
    """One consistent read of everything the component loop binds to (§3.2).

    An explicit read transaction keeps the session row, the ancestor walk and
    the message query on one snapshot. Messages are filtered to the CURRENT
    head's ancestor chain AND the HEAD node's campaign arc+session indexes —
    taken from the head only (review round 5); the ancestor set exists solely
    to select which message rows belong to this playthrough. The campaign
    snapshot the provider renders (slot, progress row) is captured INSIDE the
    same read transaction, and the provider must render on that copy — the
    shared manager is neither trusted nor mutated (review round 6).
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
        head_arc_index = int(head_progress.get("arc_index", 0))
        slot_snapshot = session["active_slot_name"] or "default"
        slot_campaign_id = session["campaign_id"]
        progress_row_snapshot = None
        if slot_campaign_id:
            progress_row_snapshot = db.read_campaign_progress(slot_campaign_id, slot_snapshot, conn=conn)
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
            WHERE session_id = ? AND campaign_session_index = ? AND campaign_arc_index = ?
              AND turn_node_id IN ({placeholders})
            ORDER BY id
            """,
            (session_id, campaign_session_index, head_arc_index, *ancestors),
        ).fetchall()
        conn.commit()

    state = json.loads(session["state_json"])
    # campaignContext: memory part assembled offline from the in-snapshot
    # controller (no LLM); the campaign part (scene/goal/anchors) comes from
    # the provider rendering the CAPTURED snapshot (slot + progress row copy).
    try:
        controller = memory_controller_factory()
        controller.load_state(state.get("_memory_controller") or {})
        campaign_context = controller.assemble_context(state, int(state.get("turn", 0)))
    except Exception:
        campaign_context = ""
    if campaign_context_provider is not None:
        try:
            snapshot = {
                "slotName": slot_snapshot,
                "campaignId": slot_campaign_id,
                "arcIndex": head_arc_index,
                "sessionIndex": campaign_session_index,
                "expectedParentId": session["active_turn_id"],
                "expectedVersion": int(session["version"]),
                "progressRow": progress_row_snapshot,
            }
            injected = campaign_context_provider(state, int(state.get("turn", 0)), snapshot)
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


CLAIM_TIMEOUT_SECONDS = 600
_TASK_EXECUTOR = "commit-turn"


def run_pending_tasks(
    db: Database,
    state_manager: Any,
    session_id: str,
    runner: Callable[[dict[str, Any]], Any],
    executor: str = _TASK_EXECUTOR,
    fault_injector: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Claim, compute and apply each task against the head's bound snapshot.

    ``executor`` is an audit label, never ownership. Every acquisition gets
    a fresh token; release and confirmation require that token AND running
    state. A timed-out worker cannot touch its successor's claim or result.

    The pure runner receives copied ``memory_state`` and ``campaign_progress``.
    memory_maintain returns {"memory_state": <controller export>}; campaign_recap
    returns {"recap_compressed": str, "recap_full": str (optional)}. Invalid
    results remain pending. Tasks run in queue order, reading the result of
    the preceding confirmation, so whole snapshots cannot overwrite one
    another. Fresh claims block later tasks in concurrent callers as well.
    """

    def task_key(task: dict[str, Any]) -> str:
        slot = task.get("slot", "default")
        return f"{slot}:{task.get('type', 'unknown')}:{task.get('nodeId')}"

    with db.connect() as conn:
        session = conn.execute(
            "SELECT active_turn_id, active_slot_name, version, state_json FROM game_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            raise CommitTurnError(404, "Session not found")
        state = json.loads(session["state_json"])
        pending = list(state.get("_memory_pending_tasks") or [])
    slot = session["active_slot_name"] or "default"
    binding = (session["active_turn_id"], slot, int(session["version"]))
    completed: list[dict[str, Any]] = []
    for task in pending:
        key = task_key(task)
        token = uuid4().hex
        if fault_injector is not None:
            fault_injector("before_claim")
        # Capture the runner's inputs and claim in the same short transaction.
        with db.write_transaction() as conn:
            current = conn.execute("SELECT * FROM game_sessions WHERE id = ?", (session_id,)).fetchone()
            if current is None or _task_binding(current) != binding:
                break
            state = json.loads(current["state_json"])
            if not any(task_key(t) == key for t in state.get("_memory_pending_tasks") or []):
                continue
            if task.get("slot", "default") != slot:
                continue
            queued_keys = [task_key(t) for t in state.get("_memory_pending_tasks") or []]
            placeholders = ",".join("?" for _ in queued_keys)
            running = conn.execute(
                f"SELECT task_key, claimed_at FROM memory_task_claims WHERE session_id = ? AND state = 'running' AND task_key IN ({placeholders})",
                (session_id, *queued_keys),
            ).fetchall()
            now = _dt.datetime.now(_dt.timezone.utc)
            if any(not _claim_is_stale(row["claimed_at"], now) for row in running):
                break
            # Whole-memory candidates share one head, so even DIFFERENT tasks
            # must not compute concurrently. Fence any expired queued worker
            # before acquiring this task, including earlier failed work.
            for row in running:
                conn.execute("DELETE FROM memory_task_claims WHERE session_id = ? AND task_key = ?", (session_id, row["task_key"]))
            # A queued task with an old done record can occur after restoring
            # an earlier snapshot. Recompute on that branch; a sibling's
            # completion must not clear work whose effect this snapshot lacks.
            conn.execute(
                """INSERT INTO memory_task_claims
                   (session_id, task_key, state, executor, claim_token)
                   VALUES (?, ?, 'running', ?, ?)
                   ON CONFLICT(session_id, task_key) DO UPDATE SET
                     state = 'running', executor = excluded.executor,
                     claim_token = excluded.claim_token, result_json = '{}',
                     claimed_at = CURRENT_TIMESTAMP""",
                (session_id, key, executor, token),
            )
            progress = db.read_campaign_progress(current["campaign_id"], slot, conn=conn) if current["campaign_id"] else None
            runner_input = deepcopy(task)
            runner_input["memory_state"] = deepcopy(state.get("_memory_controller") or {})
            runner_input["campaign_progress"] = deepcopy(progress)
        if fault_injector is not None:
            fault_injector("after_claim")
        try:
            result = _validate_task_result(db, session_id, task, runner(runner_input))
        except Exception:
            with db.write_transaction() as conn:
                conn.execute(
                    "DELETE FROM memory_task_claims WHERE session_id = ? AND task_key = ? AND state = 'running' AND claim_token = ?",
                    (session_id, key, token),
                )
            continue
        if fault_injector is not None:
            fault_injector("before_confirm")
        with db.write_transaction() as conn:
            current = conn.execute("SELECT * FROM game_sessions WHERE id = ?", (session_id,)).fetchone()
            claim = conn.execute(
                "SELECT state, claim_token FROM memory_task_claims WHERE session_id = ? AND task_key = ?",
                (session_id, key),
            ).fetchone()
            if current is None or _task_binding(current) != binding:
                break
            if claim is None or claim["state"] != "running" or claim["claim_token"] != token:
                break
            state = json.loads(current["state_json"])
            if not any(task_key(t) == key for t in state.get("_memory_pending_tasks") or []):
                break
            if task["type"] == "memory_maintain":
                state["_memory_controller"] = result["memory_state"]
            else:
                progress = db.read_campaign_progress(current["campaign_id"], slot, conn=conn)
                if progress is None or progress["head_turn_id"] != current["active_turn_id"]:
                    raise CommitTurnError(409, "recap 的战役进度不属于当前回合")
                full = result.get("recap_full")
                if full is None:
                    full = "\n\n".join(filter(None, [progress["recap_full"], result["recap_compressed"]]))
                conn.execute(
                    "UPDATE campaign_progress SET recap_compressed = ?, recap_full = ? WHERE campaign_id = ? AND slot_name = ?",
                    (result["recap_compressed"], full, current["campaign_id"], slot),
                )
                head = conn.execute("SELECT campaign_progress_json FROM story_turns WHERE id = ?", (current["active_turn_id"],)).fetchone()
                head_progress = json.loads(head["campaign_progress_json"] or "{}")
                head_progress.update(recap_compressed=result["recap_compressed"], recap_full=full)
                conn.execute(
                    "UPDATE story_turns SET campaign_progress_json = ? WHERE id = ? AND session_id = ?",
                    (json.dumps(head_progress, ensure_ascii=False), current["active_turn_id"], session_id),
                )
            state["_memory_pending_tasks"] = [t for t in state["_memory_pending_tasks"] if task_key(t) != key]
            state_json = json.dumps(state, ensure_ascii=False)
            conn.execute(
                "UPDATE game_sessions SET state_json = ? WHERE id = ?", (state_json, session_id)
            )
            # This hook is INSIDE the transaction, after business writes.
            if fault_injector is not None:
                fault_injector("in_confirm")
            conn.execute(
                "UPDATE story_turns SET state_json = ? WHERE id = ? AND session_id = ?",
                (state_json, current["active_turn_id"], session_id),
            )
            conn.execute(
                """UPDATE memory_task_claims SET state = 'done', result_json = ?
                   WHERE session_id = ? AND task_key = ? AND state = 'running' AND claim_token = ?""",
                (json.dumps({"result": result}, ensure_ascii=False), session_id, key, token),
            )
        completed.append(task)
    return completed


def _task_binding(session: Any) -> tuple[int, str, int]:
    return (session["active_turn_id"], session["active_slot_name"] or "default", int(session["version"]))


def _validate_task_result(db: Database, session_id: str, task: dict[str, Any], result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("维护器必须返回结果对象")
    result = deepcopy(result)
    if task["type"] == "memory_maintain":
        if not isinstance(result.get("memory_state"), dict):
            raise ValueError("memory_maintain 缺少 memory_state")
        from app.services.memory.memory_controller import MemoryController

        controller = MemoryController(None, db, session_id)
        controller.load_state(result["memory_state"])
        result["memory_state"] = controller.export_state()
    elif task["type"] == "campaign_recap":
        if not isinstance(result.get("recap_compressed"), str):
            raise ValueError("campaign_recap 缺少 recap_compressed")
        if "recap_full" in result and not isinstance(result["recap_full"], str):
            raise ValueError("recap_full 必须是字符串")
    else:
        raise ValueError(f"未知维护任务：{task['type']}")
    json.dumps(result, ensure_ascii=False)  # reject unserializable results before confirming
    return result


def _claim_is_stale(claimed_at: str, now: Any) -> bool:
    try:
        stamp = _dt.datetime.fromisoformat(claimed_at)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=_dt.timezone.utc)
        return (now - stamp).total_seconds() > CLAIM_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        return True


def recover_pending_tasks(
    db: Database,
    state_manager: Any,
    runner: Callable[[dict[str, Any]], Any],
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

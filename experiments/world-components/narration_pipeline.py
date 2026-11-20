# N1-N5 runnable narration interfaces (batch 1, world-components commit 1).
# One offline, program-authoritative pipeline that threads the five
# narrative sub-steps through their real contract shapes and failure paths.
# The authority rules are the ones frozen in README (权威锚点) and the
# N3->N4 interface plan:
#
#   input   GetStateData v2 reads only (target point + explicit before
#           record). stateDigest/version/lineage are VALIDATED, never
#           recomputed — the pipeline does not rebuild digests or summaries
#           and does not reconstruct deltas from state differences.
#   N1      program fact extraction over the ORIGINAL entityDeltas (+ time
#           from timeAdvance, + the corpus no_change convention). Facts
#           carry local factIds, source pointers into the read, quotable
#           original text, and BEFORE values from the explicit before
#           read. Commit 1 extends the vocabulary to the changes the task
#           brief demands: position aspects (container AND relativeTo AND
#           slotId, each expressed, never miswritten as a plain move),
#           appearance/personality ADDED/MODIFIED/REMOVED (removals quote
#           the superseded text resolved from the before record), and new
#           subtasks with their parent goal. Duplicate names are flagged
#           on the fact, never silently merged. Changes that cannot be
#           determined or expressed become DIAGNOSTICS that stop the
#           success path — nothing is dropped silently.
#   N2      perspective content selection (commit 1): the real rule in
#           n2_perspective.py classifies every fact as must / may /
#           invisible WITH a recorded visibility ground, wired to the
#           authoritative subject and position from the point state.
#           select-all survives only as the labelled comparison baseline.
#           A must fact without any visibility ground stops the pipeline;
#           illegal fact ids are rejected; the complete fact set stays
#           authoritative for binding and checking.
#   N3      organisation via the B1/B2 program baselines + hard invariants
#           (n3_plan.check_invariants).
#   N4      the N3->N4 interface checks (binding -> coverage -> invariants
#           -> flattened 4-fact range -> 128-stub-token range over the real
#           renderer output) and the shared renderer. Batch 1 wires NO
#           generator: prose authority stays with the model track
#           (composition batch); the selftest uses a clearly-labelled
#           template composer only to give N5 something to judge.
#           Commit 1: the FROZEN r3-direction model vocabulary is still
#           the eight kinds below — selected facts outside it stop with
#           kind-awaiting-model-track BEFORE organisation, so a point
#           holding an not-yet-narratable change never reports ok.
#   N5      the corpus recognizer (corpus_check.check_row) over plan+text:
#           fails stay fails, and REVIEW-class findings are surfaced as
#           semantic_uncertain — never auto-passed, never silently dropped.
#
# Batch-1 regression target: a legal `second` point and a zero-duration
# point used to raise in the shared renderer (UNIT_CN KeyError / num_cn
# ValueError); they now run end-to-end. The frozen corpus space is proven
# byte-identical by n4_units_regression.py.

import copy
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
N2_DIR = HERE / "n2_selection"
N4_DIR = HERE / "n4_corpus"
N4V2_DIR = HERE / "n4_corpus_v2"
for p in (str(N2_DIR), str(N4_DIR), str(N4V2_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from n3_plan import plan_b1, plan_b2, check_invariants  # noqa: E402
from n3_n4_fixture import check_interface, stub_tokens  # noqa: E402
from n4_render import render_input  # noqa: E402
import corpus_check  # noqa: E402
import n2_perspective  # noqa: E402
import n3_organize  # noqa: E402

REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "backend"))
from app.schemas.world.contracts import WorldState  # noqa: E402

MAX_FACTS_PER_RUN = 4  # mirrored from the frozen N3->N4 interface contract

# The fact kinds the FROZEN r3-direction N4 model was trained to narrate
# (the frozen renderer vocabulary). Selected facts outside this set stop
# the pipeline with kind-awaiting-model-track until the commit-2 model
# track is trained and frozen — a point with such a change never reports
# ok on the frozen chain.
FROZEN_MODEL_KINDS = {"moved", "positioned_at", "task_achieved",
                      "personality_changed", "sanity_changed",
                      "appearance_changed", "time", "no_change"}


# ---------- name / container resolution (initial definitions only) ----------

def entity_name(state: dict, eid: str):
    initial = (state or {}).get("initial") or {}
    for group in ("characters", "locations", "items"):
        entry = (initial.get(group) or {}).get(eid)
        if entry is not None:
            return entry.get("name")
    return None


def container_name(state: dict, position) -> str | None:
    if not position:
        return None
    cid = position.get("containerId")
    if cid is None:
        return None
    initial = (state or {}).get("initial") or {}
    for group in ("locations", "items", "characters"):
        entry = (initial.get(group) or {}).get(cid)
        if entry is not None:
            return entry.get("name")
    return None


def enclosing_location(state: dict, position, depth: int = 0) -> str | None:
    """The nearest LOCATION that contains `position`.

    A container may be another character or an item (an item picked up is
    `containerId=<holder>`). Using the direct container name as the fact's
    place produced two defects: (a) N2 read `at=顾北汀` as "not where the
    viewpoint is" and dropped the fact, and (b) the record rendered as
    "灯油瓮 灯寮→顾北汀", which is not narratable. The place of a fact is
    always the enclosing location; the direct container is carried
    separately (`to`).
    """
    if not position or depth > 8:
        return None
    cid = position.get("containerId")
    if cid is None:
        return None
    initial = (state or {}).get("initial") or {}
    locations = initial.get("locations") or {}
    if cid in locations:
        return (locations[cid] or {}).get("name")
    for group in ("characters", "items"):
        if cid in ((initial.get(group) or {})):
            holder = ((state or {}).get(group) or {}).get(cid) or {}
            return enclosing_location(state, holder.get("position"), depth + 1)
    return None


def container_is_holder(state: dict, container_id: str | None) -> bool:
    """True when the container is a character or an item, i.e. the position
    means "carried by", not "standing in"."""
    if container_id is None:
        return False
    initial = (state or {}).get("initial") or {}
    return any(container_id in ((initial.get(g) or {}))
               for g in ("characters", "items"))


def slot_label(state: dict, container_id: str | None, slot_id: str) -> str | None:
    """A slot's display label from the container's registered slots (the
    initial registry is immutable, so before and after lookups agree)."""
    if container_id is None or slot_id is None:
        return None
    initial = (state or {}).get("initial") or {}
    for group in ("locations", "items", "characters"):
        entry = (initial.get(group) or {}).get(container_id)
        if entry is not None:
            for slot in entry.get("slots") or []:
                if slot.get("id") == slot_id:
                    return slot.get("label")
    return None


def name_counts(state: dict) -> dict:
    """How many registered entities carry each display name — the duplicate
    name signal the facts flag (重名人物 is recorded, never merged)."""
    counts = {}
    for group in ("characters", "locations", "items"):
        for entry in (((state or {}).get("initial") or {}).get(group)
                      or {}).values():
            name = entry.get("name")
            if name:
                counts[name] = counts.get(name, 0) + 1
    return counts


def place_name(state: dict, ent) -> str | None:
    """Where a fact happened, in the D2 fact convention: a LOCATION is its
    own place; an item or character sits in its container. (The old
    container_name alone returned None for location entities and would
    have made every location-appearance fact invisible to N2.)"""
    if ent is None:
        return None
    st = (state or {})
    for group in ("locations",):
        if ent.get("id") in (st.get(group) or {}):
            return entity_name(state, ent["id"])
    return container_name(state, ent.get("position"))


def _resolve_superseded(before: dict | None, eid: str, field: str,
                        sup_ids: list) -> list | None:
    """The quoted original texts a DescriptionChange supersedes, resolved
    from the explicit BEFORE record's accumulated change history. None when
    any id is unresolvable — a removal that cannot quote what it removed
    cannot be narrated faithfully."""
    if not before or not sup_ids:
        return None
    st = before.get("state") or {}
    for group in ("characters", "items", "locations"):
        ent = (st.get(group) or {}).get(eid)
        if ent is None:
            continue
        history = {c.get("id"): c for c in ent.get(field) or []}
        texts = []
        for sid in sup_ids:
            change = history.get(sid)
            if change is None or change.get("text") is None:
                return None
            texts.append(change["text"])
        return texts
    return None


# ---------- N1: program fact extraction (original deltas, no diffing) ------

def _before_entity(before: dict, eid: str):
    if not before:
        return None
    st = before.get("state") or {}
    for group in ("characters", "items", "locations"):
        ent = (st.get(group) or {}).get(eid)
        if ent is not None:
            return ent
    return None


def _after_entity(state: dict, eid: str):
    for group in ("characters", "items", "locations"):
        ent = ((state or {}).get(group) or {}).get(eid)
        if ent is not None:
            return ent
    return None


def extract_facts(point: dict, before: dict | None,
                  narrative_outcome: bool = False) -> dict:
    """N1: enumerate fact entries from the ORIGINAL entityDeltas + time.
    Returns {"facts": [...], "diagnostics": [...]} — diagnostics record
    everything that cannot be determined or expressed as a fact, so nothing
    is dropped silently and the success path can be stopped.

    narrative_outcome=True emits the surface `outcome` + `resultText` for a
    completed task instead of the internal `task_achieved` + goal. Missing
    resultText is a blocking `task-outcome-unavailable` diagnostic: the
    N4 narrative path must stop, never fall back to printing the goal. The
    default False keeps the frozen v2 task_achieved contract."""
    state = point.get("state") or {}
    deltas = point.get("entityDeltas") or {}
    facts, diagnostics = [], []
    ambiguous = name_counts(state)

    def location_path(position):
        """Location ids from the container up to the root (see
        n2_perspective.location_path_ids: leaf names are not enough to decide
        "same place", two rooms of one building have different leaves)."""
        out, cid, depth = [], (position or {}).get("containerId"), 0
        locations = ((state or {}).get("initial") or {}).get("locations") or {}
        while cid is not None and depth < 12 and cid in locations:
            out.append(cid)
            cid = (locations[cid] or {}).get("parentLocationId")
            depth += 1
        # a position inside a character/item still belongs to a location
        if not out and position:
            loc = enclosing_location(state, position)
            if loc:
                for lid, ent in locations.items():
                    if (ent or {}).get("name") == loc:
                        out = location_path(ent.get("position")
                                           or {"containerId": lid})
                        break
                else:
                    out = [lid for lid, ent in locations.items()
                           if (ent or {}).get("name") == loc]
        return out

    def add(fact):
        # factId is owned HERE so every constructor site sequences the same
        # way; duplicate names are flagged on the fact, never merged, and
        # the subject's registry group travels with the fact (N2 uses it
        # to separate scenery from other people's facts)
        fact["factId"] = f"f{len(facts)}"
        if fact.get("entityId"):
            fact["entityGroup"] = None
            for group in ("characters", "locations", "items"):
                if fact["entityId"] in (((state.get("initial") or {})
                                         .get(group) or {})):
                    fact["entityGroup"] = group
                    break
        for key in ("name", "targetName", "from", "to", "at"):
            if fact.get(key):
                fact[key + "Ambiguous"] = ambiguous.get(fact[key], 0) > 1
        # every fact carries its location chain so visibility can ask "same
        # building" instead of "same leaf name"
        if fact.get("entityId"):
            ent = _after_entity(state, fact["entityId"])
            fact["atPath"] = location_path((ent or {}).get("position"))
        fact["ref"] = len(facts)
        facts.append(fact)

    def location_of(ent):
        # enclosing LOCATION, not the direct container: an entity held by a
        # character lives at that character's location (see
        # enclosing_location's docstring for the two defects this fixes)
        return (enclosing_location(state, (ent or {}).get("position"))
                if ent else None)

    ta = point.get("timeAdvance")
    for eid, d in deltas.items():
        name = entity_name(state, eid)
        live_after = _after_entity(state, eid)
        live_before = _before_entity(before, eid)
        if name is None:
            diagnostics.append({"code": "entity-unregistered", "entityId": eid})
            continue
        if d.get("positionSet"):
            pos_after = d["positionSet"] or {}
            pos_before = (live_before or {}).get("position") or {}
            same_container = (pos_before.get("containerId")
                              == pos_after.get("containerId"))
            to = container_name(state, pos_after)
            if to is None:
                diagnostics.append({"code": "destination-unresolvable",
                                    "entityId": eid})
                continue
            frm = None
            if not same_container:
                frm = container_name(before.get("state") if before else None,
                                     pos_before)
                if frm is None:
                    diagnostics.append({"code": "origin-unresolvable",
                                        "entityId": eid})
                    continue
            aspects = False
            # relativeTo aspect: expressed as its own fact, never folded
            # into a bare container move (the miswrite the task brief
            # names). A changed relation states the after relation (or
            # quotes the removed one) and keeps the before value.
            rel_b = pos_before.get("relativeTo")
            rel_a = pos_after.get("relativeTo")
            if rel_b != rel_a:
                aspects = True
                a_target = b_target = None
                if rel_a is not None:
                    a_target = entity_name(state, rel_a.get("entityId"))
                    if a_target is None or rel_a.get("relation") not in n2_perspective.RELATION_CN:
                        diagnostics.append({
                            "code": "relative-target-unresolvable",
                            "entityId": eid,
                            "targetId": rel_a.get("entityId"),
                            "relation": rel_a.get("relation")})
                        continue
                if rel_b is not None:
                    b_target = entity_name(state, rel_b.get("entityId"))
                    if b_target is None or rel_b.get("relation") not in n2_perspective.RELATION_CN:
                        diagnostics.append({
                            "code": "relative-target-unresolvable",
                            "entityId": eid,
                            "targetId": rel_b.get("entityId"),
                            "relation": rel_b.get("relation")})
                        continue
                out_rel = rel_a if rel_a is not None else rel_b
                out_target = a_target if rel_a is not None else b_target
                before_rel = None
                if rel_b is not None:
                    before_rel = {"targetName": b_target,
                                  "relation": rel_b["relation"]}
                add({"kind": "position_relative", "entityId": eid,
                     "name": name, "at": to, "targetName": out_target,
                     "targetId": out_rel.get("entityId"),
                     "relation": out_rel["relation"],
                     "op": "changed" if rel_a is not None and rel_b is not None
                     else "added" if rel_a is not None else "removed",
                     "before": before_rel,
                     "source": {"entityId": eid, "field": "positionSet",
                                "aspect": "relativeTo"}})
            # slotId aspect: expressed through the container's registered
            # slot label; an unregistered slot cannot be narrated
            slot_b = pos_before.get("slotId")
            slot_a = pos_after.get("slotId")
            if slot_b != slot_a:
                aspects = True
                if slot_a is not None:
                    label = slot_label(state, pos_after.get("containerId"),
                                       slot_a)
                    if label is None:
                        diagnostics.append({"code": "slot-unresolvable",
                                            "entityId": eid, "slotId": slot_a})
                        continue
                    before_slot = None
                    if slot_b is not None:
                        b_label = slot_label(state, pos_before.get("containerId"),
                                             slot_b)
                        if b_label is None:
                            diagnostics.append({"code": "slot-unresolvable",
                                                "entityId": eid,
                                                "slotId": slot_b})
                            continue
                        before_slot = {"slotId": slot_b, "slotLabel": b_label}
                    add({"kind": "slot_changed", "entityId": eid, "name": name,
                         "at": to, "slotId": slot_a, "slotLabel": label,
                         "op": "added" if slot_b is None else "changed",
                         "before": before_slot,
                         "source": {"entityId": eid, "field": "positionSet",
                                    "aspect": "slotId"}})
                else:
                    b_label = slot_label(state, pos_before.get("containerId"),
                                         slot_b)
                    if b_label is None:
                        diagnostics.append({"code": "slot-unresolvable",
                                            "entityId": eid, "slotId": slot_b})
                        continue
                    add({"kind": "slot_changed", "entityId": eid, "name": name,
                         "at": to, "slotId": None, "slotLabel": b_label,
                         "op": "removed",
                         "before": {"slotId": slot_b, "slotLabel": b_label},
                         "source": {"entityId": eid, "field": "positionSet",
                                    "aspect": "slotId"}})
            if not same_container:
                add({"kind": "moved", "entityId": eid, "name": name,
                     "from": frm, "to": to,
                     "at": (location_of(live_after) or to),
                     "heldBy": (to if container_is_holder(
                         state, (pos_after or {}).get("containerId")) else None),
                     "source": {"entityId": eid, "field": "positionSet"}})
            elif not aspects:
                # positionSet equals the before position and no aspect
                # changed: nothing moved and nothing is lost, but the
                # authority asserted a position change — recorded, and the
                # success path stops rather than guessing what was meant
                diagnostics.append({
                    "code": "no-op-position-change", "entityId": eid,
                    "reason": ("positionSet equals the before position; "
                               "there is no movement to narrate"),
                    "source": {"entityId": eid, "field": "positionSet"}})
                continue
        for ch in d.get("appearanceChanges") or []:
            _emit_description_change("appearanceChanges", "appearance_changed",
                                     "appearance_removed", state, before, eid,
                                     name, ch, live_after, diagnostics, add)
        for ch in d.get("personalityChanges") or []:
            _emit_description_change("personalityChanges",
                                     "personality_changed",
                                     "personality_removed", state, before, eid,
                                     name, ch, live_after, diagnostics, add)
        if d.get("sanitySet") is not None:
            if live_before is None or "sanity" not in live_before:
                diagnostics.append({"code": "sanity-from-unresolvable",
                                    "entityId": eid})
                continue
            add({"kind": "sanity_changed", "entityId": eid, "name": name,
                 "from": live_before["sanity"], "to": d["sanitySet"],
                 "at": location_of(live_after),
                 "source": {"entityId": eid, "field": "sanitySet"}})
        for tid in d.get("tasksAchieved") or []:
            task = ((state.get("characters") or {}).get(eid, {})
                    .get("tasks", {}).get(tid))
            if task is None or task.get("status") != "achieved":
                diagnostics.append({"code": "task-unresolvable",
                                    "entityId": eid, "taskId": tid})
                continue
            if narrative_outcome:
                result_text = task.get("resultText")
                if not isinstance(result_text, str) or not result_text.strip():
                    diagnostics.append({
                        "code": "task-outcome-unavailable",
                        "entityId": eid, "taskId": tid,
                        "reason": "完成的 task 没有 resultText；N4 叙事路径"
                                  "必须停止，不能退回打印 task goal"})
                    continue
                add({"kind": "outcome", "entityId": eid, "name": name,
                     "goal": task["goal"], "resultText": result_text.strip(),
                     "taskId": tid, "at": location_of(live_after),
                     "source": {"entityId": eid, "taskId": tid,
                                "field": "tasksAchieved"}})
            else:
                add({"kind": "task_achieved", "entityId": eid, "name": name,
                     "goal": task["goal"], "at": location_of(live_after),
                     "source": {"entityId": eid, "taskId": tid}})
        for t in d.get("subtasksAdded") or []:
            # new subtasks are now EXPRESSIBLE: the fact quotes the task
            # goal and the parent goal resolved from the state
            parent = ((state.get("characters") or {}).get(eid, {})
                      .get("tasks", {}) or {}).get(t.get("parentTaskId"))
            if t.get("goal") is None or parent is None:
                diagnostics.append({"code": "subtask-parent-unresolvable",
                                    "entityId": eid, "taskId": t.get("id"),
                                    "parentTaskId": t.get("parentTaskId")})
                continue
            add({"kind": "subtask_added", "entityId": eid, "name": name,
                 "goal": t["goal"], "parentGoal": parent.get("goal"),
                 "at": location_of(live_after),
                 "source": {"entityId": eid, "taskId": t.get("id"),
                            "field": "subtasksAdded"}})
    # NO co-presence roster scan. Presence is state, but "who is at the
    # destination" is not a change and co-location is not "was noticed".
    # A move to a crowded place must not manufacture one positioned_at fact
    # per resident (100 NPCs -> 100 facts). positioned_at stays a supported
    # N4 kind only for a future EXPLICIT observation source; N1 does not
    # infer it from state positions.
    if ta is not None:
        dur = ta.get("duration") or {}
        add({"kind": "time",
             "amount": dur.get("amount"), "unit": dur.get("unit"),
             "at": None, "source": {"timeAdvance": True}})
    if not deltas:
        add({"kind": "no_change", "scope": "全局",
             "source": {"noChange": True}})
    # fix round 1c41587 #3: every ORIGINAL delta field must have a handling
    # outcome — a field outside the known EntityDelta vocabulary is recorded
    # as unprocessable, never silently skipped
    for eid, d in deltas.items():
        for key in d:
            if key not in ("entityId", "positionSet", "appearanceChanges",
                           "personalityChanges", "sanitySet", "tasksAchieved",
                           "subtasksAdded"):
                diagnostics.append({"code": "unknown-delta-field",
                                    "entityId": eid, "field": key})
        # a Position's vocabulary is closed (containerId/slotId/relativeTo,
        # and relativeTo carries entityId/relation): an unknown KEY cannot
        # be compared before-vs-after, so the aspect it carries would be
        # silently dropped — recorded as blocking instead (review round on
        # the first commit: the cross-container case used to slip through)
        pos = d.get("positionSet") or {}
        for key in pos:
            if key not in ("containerId", "slotId", "relativeTo"):
                diagnostics.append({"code": "unknown-position-field",
                                    "entityId": eid, "field": key})
        rel = pos.get("relativeTo") or {}
        if isinstance(rel, dict):
            for key in rel:
                if key not in ("entityId", "relation"):
                    diagnostics.append({"code": "unknown-position-field",
                                        "entityId": eid,
                                        "field": f"relativeTo.{key}"})
    return {"facts": facts, "diagnostics": diagnostics}


def _emit_description_change(field: str, add_kind: str, remove_kind: str,
                             state: dict, before: dict | None, eid: str,
                             name: str, ch: dict, live_after,
                             diagnostics: list, add) -> None:
    """One DescriptionChange -> an added/modified fact (the new text is
    what the narration quotes; op records which) or a removed fact that
    QUOTES the superseded originals resolved from the explicit before
    record. Unresolvable shapes record a blocking diagnostic instead of a
    fact — the success path stops, nothing is invented."""
    text = ch.get("text")
    sup = ch.get("supersedes") or []
    at = place_name(state, live_after)
    src = {"entityId": eid, "changeId": ch.get("id"), "field": field}
    if text is None:
        if not sup:
            # the contract forbids pure removal without supersedes; a delta
            # with that shape cannot be interpreted — explicit stop
            diagnostics.append({"code": "supersede-only-change",
                                "entityId": eid, "changeId": ch.get("id")})
            return
        removed = _resolve_superseded(before, eid, field, sup)
        if removed is None:
            diagnostics.append({"code": "superseded-change-unresolvable",
                                "entityId": eid, "changeId": ch.get("id"),
                                "supersedes": sup, "field": field})
            return
        add({"kind": remove_kind, "entityId": eid, "name": name,
             "text": "；".join(removed), "op": "removed",
             "removedIds": list(sup), "at": at, "source": src})
        return
    if sup and _resolve_superseded(before, eid, field, sup) is None:
        # a modification claims to replace prior descriptions; if the
        # before record does not carry them, the claim is unsupported
        diagnostics.append({"code": "superseded-change-unresolvable",
                            "entityId": eid, "changeId": ch.get("id"),
                            "supersedes": sup, "field": field})
        return
    add({"kind": add_kind, "entityId": eid, "name": name, "text": text,
         "op": "modified" if sup else "added", "at": at, "source": src})


# codes whose diagnostics mean an original change CANNOT become narration:
# the pipeline must stop the success path (fix round 1c41587 #3) instead of
# narrating a subset and reporting ok
INCOMPLETE_DIAGNOSTIC_CODES = {
    "unsupported-narration-kind", "supersede-only-change",
    "destination-unresolvable", "sanity-from-unresolvable",
    "task-unresolvable", "entity-unregistered", "unknown-delta-field",
    "no-op-position-change", "unknown-position-field",
    "origin-unresolvable", "relative-target-unresolvable",
    "slot-unresolvable", "superseded-change-unresolvable",
    "subtask-parent-unresolvable", "task-outcome-unavailable",
}


# ---------- authoritative binding, generalised to all N4 fact kinds --------

def bind_point_full(point: dict, before: dict | None, manifest: list) -> list:
    """Same discipline as the frozen n3_n4_fixture.bind_point (keys must
    exist, world identity is state.worldId, names from state.initial.*,
    content checked against the read), extended from task_achieved/time to
    every N4 fact kind. Returns binding-failed reasons (empty = bound)."""
    problems = []
    for field in ("state", "pointId", "version", "stateDigest",
                  "previousPointId", "timeAdvance", "entityDeltas"):
        if field not in point:
            problems.append(f"missing-{field}")
        elif point[field] is None and field in ("state", "pointId", "version",
                                                "stateDigest", "entityDeltas"):
            problems.append(f"missing-{field}")
    if problems:
        return problems
    world = (point["state"] or {}).get("worldId")
    if not world:
        return ["world-missing"]
    is_root = point["version"] == 0
    if is_root:
        if point["previousPointId"] is not None:
            problems.append("root-with-predecessor")
        if point["timeAdvance"] is not None:
            problems.append("root-with-time")
        if point["entityDeltas"]:
            problems.append("root-with-deltas")
        if before is not None:
            problems.append("root-with-before-record")
    else:
        if point["timeAdvance"] is None:
            problems.append("missing-timeAdvance-value")
        if before is None:
            problems.append("missing-before")
        else:
            bstate = before.get("state") or {}
            if not bstate.get("worldId"):
                return problems + ["world-missing"]
            if bstate["worldId"] != world:
                problems.append("world-mismatch")
            if before.get("version") != point["version"] - 1:
                problems.append("version-gap")
            if before.get("pointId") != point["previousPointId"]:
                problems.append("predecessor-identity-mismatch")
    if not isinstance(point["entityDeltas"], dict):
        return problems + ["deltas-not-entity-map"]
    state = point["state"]
    for f in manifest:
        fid, kind = f.get("factId"), f.get("kind")
        if kind not in ("moved", "task_achieved", "personality_changed",
                        "personality_removed", "sanity_changed",
                        "appearance_changed", "appearance_removed",
                        "positioned_at", "subtask_added", "position_relative",
                        "slot_changed", "time", "no_change"):
            problems.append(f"unsupported-fact-kind:{fid}:{kind}")
            continue
        src = f.get("source") or {}
        if kind == "time":
            ta = point["timeAdvance"]
            if not isinstance(ta, dict) \
                    or f.get("amount") != (ta.get("duration") or {}).get("amount") \
                    or f.get("unit") != (ta.get("duration") or {}).get("unit"):
                problems.append(f"source-content-mismatch:{fid}:timeAdvance")
            continue
        if kind == "no_change":
            if point["entityDeltas"]:
                problems.append(f"source-content-mismatch:{fid}:noChange")
            continue
        eid = src.get("entityId")
        if f.get("entityId") != eid:
            problems.append(f"ownership-mismatch:{fid}")
            continue
        registered = entity_name(state, eid)
        if registered is None:
            problems.append(f"entity-unregistered:{fid}")
            continue
        if f.get("name") != registered:
            problems.append(f"name-mismatch:{fid}")
        delta = point["entityDeltas"].get(eid)
        if kind == "positioned_at":
            if not src.get("statePosition"):
                problems.append(f"source-content-mismatch:{fid}:statePosition")
                continue
            live = _after_entity(state, eid)
            at = container_name(state, (live or {}).get("position"))
            if at != f.get("at"):
                problems.append(f"source-content-mismatch:{fid}:position")
            continue
        if delta is None:
            problems.append(f"source-content-mismatch:{fid}:entity")
            continue
        if kind == "moved":
            if src.get("field") != "positionSet" or not delta.get("positionSet"):
                problems.append(f"source-content-mismatch:{fid}:positionSet")
                continue
            to = container_name(state, delta["positionSet"])
            frm = container_name((before or {}).get("state"),
                                 (_before_entity(before, eid) or {}).get("position"))
            if to != f.get("to") or frm != f.get("from"):
                problems.append(f"source-content-mismatch:{fid}:containers")
            continue
        if kind == "position_relative":
            if src.get("field") != "positionSet" \
                    or src.get("aspect") != "relativeTo" \
                    or not delta.get("positionSet"):
                problems.append(f"source-content-mismatch:{fid}:aspect")
                continue
            delta_pos = delta["positionSet"] or {}
            rel_after = delta_pos.get("relativeTo")
            if f.get("at") != container_name(state, delta_pos):
                problems.append(f"source-content-mismatch:{fid}:container")
                continue
            b_pos = (_before_entity(before, eid) or {}).get("position") or {}
            rel_b = b_pos.get("relativeTo")
            if f.get("op") == "removed":
                if rel_after is not None or rel_b is None \
                        or f.get("targetId") != rel_b.get("entityId") \
                        or f.get("relation") != rel_b.get("relation") \
                        or f.get("before") != {"targetName": entity_name(state, rel_b.get("entityId")),
                                               "relation": rel_b.get("relation")}:
                    problems.append(f"source-content-mismatch:{fid}:relativeBefore")
                continue
            if rel_after is None or f.get("targetId") != rel_after.get("entityId") \
                    or f.get("relation") != rel_after.get("relation"):
                problems.append(f"source-content-mismatch:{fid}:relative")
                continue
            want_before = None
            if rel_b is not None:
                want_before = {"targetName": entity_name(state, rel_b.get("entityId")),
                               "relation": rel_b.get("relation")}
            if f.get("before") != want_before:
                problems.append(f"source-content-mismatch:{fid}:relativeBefore")
            continue
        if kind == "slot_changed":
            if src.get("field") != "positionSet" \
                    or src.get("aspect") != "slotId" \
                    or not delta.get("positionSet"):
                problems.append(f"source-content-mismatch:{fid}:aspect")
                continue
            delta_pos = delta["positionSet"] or {}
            if f.get("at") != container_name(state, delta_pos):
                problems.append(f"source-content-mismatch:{fid}:container")
                continue
            slot_after = delta_pos.get("slotId")
            if f.get("op") == "removed":
                b_pos = (_before_entity(before, eid) or {}).get("position") or {}
                slot_b = b_pos.get("slotId")
                if slot_after is not None or f.get("slotId") is not None \
                        or f.get("before", {}).get("slotId") != slot_b \
                        or f.get("slotLabel") != slot_label(state, b_pos.get("containerId"), slot_b):
                    problems.append(f"source-content-mismatch:{fid}:slotBefore")
                continue
            if f.get("slotId") != slot_after \
                    or f.get("slotLabel") != slot_label(state, delta_pos.get("containerId"), slot_after):
                problems.append(f"source-content-mismatch:{fid}:slot")
            continue
        if kind in ("appearance_changed", "personality_changed"):
            field_name = "appearanceChanges" if kind == "appearance_changed" else "personalityChanges"
            change = next((c for c in delta.get(field_name) or []
                           if c.get("id") == src.get("changeId")), None)
            if change is None or change.get("text") != f.get("text"):
                problems.append(f"source-content-mismatch:{fid}:change")
                continue
            want_op = "modified" if (change.get("supersedes") or []) else "added"
            if f.get("op") != want_op:
                problems.append(f"source-content-mismatch:{fid}:op")
            continue
        if kind in ("appearance_removed", "personality_removed"):
            field_name = "appearanceChanges" if kind == "appearance_removed" else "personalityChanges"
            change = next((c for c in delta.get(field_name) or []
                           if c.get("id") == src.get("changeId")), None)
            if change is None or change.get("text") is not None:
                problems.append(f"source-content-mismatch:{fid}:change")
                continue
            resolved = _resolve_superseded(before, eid, field_name,
                                           change.get("supersedes") or [])
            if resolved is None or f.get("text") != "；".join(resolved) \
                    or f.get("op") != "removed":
                problems.append(f"source-content-mismatch:{fid}:removed")
            continue
        if kind == "subtask_added":
            task_new = next((t for t in delta.get("subtasksAdded") or []
                             if t.get("id") == src.get("taskId")), None)
            if task_new is None or task_new.get("goal") != f.get("goal"):
                problems.append(f"source-content-mismatch:{fid}:subtask")
                continue
            parent = (state.get("characters", {}).get(eid, {})
                      .get("tasks", {}) or {}).get(task_new.get("parentTaskId"))
            if parent is None or parent.get("goal") != f.get("parentGoal"):
                problems.append(f"source-content-mismatch:{fid}:subtaskParent")
            continue
        if kind == "sanity_changed":
            if delta.get("sanitySet") != f.get("to") \
                    or f.get("from") != (_before_entity(before, eid) or {}).get("sanity"):
                problems.append(f"source-content-mismatch:{fid}:sanity")
            continue
        if kind == "task_achieved":
            tid = src.get("taskId")
            if tid not in (delta.get("tasksAchieved") or []):
                problems.append(f"source-content-mismatch:{fid}:taskId")
                continue
            task_def = (state.get("characters", {}).get(eid, {})
                        .get("tasks", {}).get(tid))
            if task_def is None or task_def.get("ownerId") != eid \
                    or task_def.get("goal") != f.get("goal") \
                    or task_def.get("status") != "achieved":
                problems.append(f"source-content-mismatch:{fid}:task")
    return problems


# ---------- N2 (perspective rule + baselines) and N3 ------------------------

def select_facts(facts: list, perspective: dict, arm: str = "perspective-rule",
                 may_policy: str = "select", subject_tasks: dict | None = None,
                 selected_ids: list | None = None,
                 visible_other_actions: bool = False) -> dict:
    """N2 interface. The default arm is the REAL perspective rule
    (n2_perspective.classify_facts): every fact is classified must / may /
    invisible with a recorded visibility ground, wired to the authoritative
    subject and position. arm="select-all" survives ONLY as the labelled
    comparison baseline — it is not a content-selection claim.
    arm="manual" validates a caller-supplied selection and REJECTS illegal
    fact ids: no path into N3/N4 accepts an unknown id."""
    valid = {f["factId"] for f in facts}
    if arm == "select-all":
        selected = [f["factId"] for f in facts]
        return {"status": "ok", "arm": arm, "mayPolicy": None,
                "selectedFactIds": selected, "invalidReferences": [],
                "decisions": None,
                "note": ("comparison baseline only: selects everything "
                         "including invisible facts — never shipped as a "
                         "content selection")}
    if arm == "manual":
        if selected_ids is None:
            return {"status": "error", "arm": arm,
                    "reason": "manual-selection-missing",
                    "invalidReferences": []}
        invalid = [x for x in selected_ids if x not in valid]
        if invalid:
            return {"status": "error", "arm": arm,
                    "reason": "invalid-fact-references",
                    "invalidReferences": invalid}
        return {"status": "ok", "arm": arm, "mayPolicy": None,
                "selectedFactIds": list(selected_ids),
                "invalidReferences": [], "decisions": None}
    if arm != "perspective-rule":
        return {"status": "not-implemented", "arm": arm,
                "reason": "unknown selection arm; the pipeline carries the "
                          "perspective rule, the labelled select-all "
                          "baseline and validated manual selections",
                "selectedFactIds": [], "invalidReferences": []}
    result = n2_perspective.classify_facts(
        facts, perspective, subject_tasks=subject_tasks,
        may_policy=may_policy,
        visible_other_actions=visible_other_actions)
    result["arm"] = arm
    result["invalidReferences"] = [x for x in result.get("selectedFactIds", [])
                                   if x not in valid]
    return result


def organize(selected_facts: list, baseline: str = "B1") -> dict:
    """N3 via the program baselines; narrow shape + hard invariants."""
    names = {f["entityId"]: f["name"] for f in selected_facts if f.get("entityId")}
    planner = plan_b1 if baseline == "B1" else plan_b2
    plan = planner(selected_facts, names)
    violations = check_invariants(plan, selected_facts, names)
    if violations:
        return {"status": "error", "reason": "plan-invariant-violation",
                "violations": violations}
    plan["itemId"] = "pipeline"
    return {"status": "ok", "plan": plan}


# ---------- N4 (interface checks + renderer) and N5 (judge) ----------------

def interface_check(plan: dict, manifest: list, binding_problems: list) -> dict:
    """The frozen N3->N4 interface contract (coverage -> invariants ->
    flattened range -> stub-token range over the real renderer output)."""
    return check_interface(plan, manifest, binding_problems)


def generate_reference_text(plan_facts: list) -> str:
    """SELFTEST-ONLY template composer in the frontend narration-split v0
    style. This is NOT a product renderer and NOT a model output: it exists
    so the N5 stage has text to judge in the offline selftest. Prose
    authority in the real chain stays with the N4 model track."""
    parts = []
    for e in plan_facts:
        k = e["kind"]
        if k == "moved":
            parts.append(f"{e['name']}从{e['from']}来到了{e['to']}。" if e.get("from")
                         else f"{e['name']}来到了{e['to']}。")
        elif k == "task_achieved":
            parts.append(f"{e['name']}完成了任务「{e['goal']}」。")
        elif k == "personality_changed":
            parts.append(f"{e['name']}{e['text']}。")
        elif k == "sanity_changed":
            parts.append(f"{e['name']}的精神值从{e['from']}{'升' if e['to'] > e['from'] else '降'}到了{e['to']}。")
        elif k == "appearance_changed":
            parts.append(f"{e['name']}的外观变了:{e['text']}。")
        elif k == "positioned_at":
            parts.append(f"{e['name']}已在{e['at']}。")
        elif k == "time":
            from n4_render import num_cn, UNIT_CN
            parts.append(f"前后大约{num_cn(e['amount'])}{UNIT_CN[e['unit']]}。")
        elif k == "no_change":
            parts.append("一切如旧。")
    return "".join(parts)


def verify_text(plan_facts: list, text: str) -> dict:
    """N5: the program recognizer core (corpus_check.check_narration) over
    plan+text. fails stay fails; reviews are surfaced as semantic_uncertain
    and are NEVER auto-passed (the page gate stays B-side; this module only
    reports)."""
    plan = copy.deepcopy(plan_facts)
    sentences = [s for s in text.split("。") if s.strip()]
    all_refs = [e["ref"] for e in plan]
    fails, reviews = corpus_check.check_narration(
        plan, text, [all_refs for _ in sentences], list(all_refs))
    return {"status": "checked",
            "fails": fails,
            "semanticUncertain": reviews,
            "autoPassed": False,
            "note": "review-class findings are listed for human/model "
                    "review; this module does not gate the page"}


def hashlib_plan(plan: list) -> str:
    import hashlib
    return hashlib.sha256(corpus_check.canon(plan).encode("utf-8")).hexdigest()


# ---------- the v2 chain (commit 2): grouped interface + trained vocabulary

# The vocabulary the v2 model track is TRAINED on (the frozen eight plus
# the five kinds commit 1 extracts). The gate evidence is the v2 freeze
# record (train report + holdout eval); until that record exists the v2
# chain refuses to narrate.
V2_MODEL_KINDS = FROZEN_MODEL_KINDS | {"subtask_added", "personality_removed",
                                       "appearance_removed",
                                       "position_relative", "slot_changed"}

V2_TOKEN_LIMIT = 128  # the standing product gate over REAL tokens


def run_pipeline_v2(point: dict, before: dict | None, perspective,
                    may_policy: str = "omit",
                    gender_hints: dict | None = None,
                    cross_group_guard: bool = True,
                    real_tok=None,
                    visible_other_actions: bool = False) -> dict:
    """The v2 chain: N1 -> N2 (perspective rule) -> N3 (plan_v3: groups,
    appellations, time attribution) -> N4v2 (render_v2 + the REAL-token
    gate). The MODEL call itself stays with the composition runner; this
    function produces everything the model needs and stops at every
    structured boundary the v1 chain stops at.

    may_policy defaults to "omit": only must facts are selected. The old
    "select every visible may fact" behavior is an explicit comparison arm
    (may_policy="select"), never the product default: visibility is not
    salience.

    gender_hints is an EXPERIMENTAL caller-supplied
    {entityId: male|female|unknown} map, NOT part of the state contract.
    None/{} keeps every name (the safe fallback); a pronoun is licensed only
    when an explicit hint exists. Do not source this from inferred UI state.

    cross_group_guard defaults to True: a pronoun is not licensed when the
    previous group contains a different entity with the same pronoun. Set it
    to False only to reproduce the legacy v2 plans; the product path keeps
    it on."""
    from render_v2 import render_input_v2
    out = {"pointId": point.get("pointId"), "version": point.get("version"),
           "chain": "v2"}
    resolved = n2_perspective.resolve_perspective(
        point.get("state") or {}, (perspective or {}).get("entityId"),
        (perspective or {}).get("type", "protagonist"))
    if resolved["problems"]:
        out["status"] = "incomplete"
        out["reason"] = "perspective-unresolvable"
        out["problems"] = resolved["problems"]
        return out
    persp = resolved["perspective"]
    out["perspective"] = persp
    n1 = extract_facts(point, before)
    out["n1"] = {"factCount": len(n1["facts"]),
                 "diagnostics": n1["diagnostics"]}
    blocking = [d for d in n1["diagnostics"]
                if d["code"] in INCOMPLETE_DIAGNOSTIC_CODES]
    if blocking:
        out["n1"]["blocking"] = blocking
        out["status"] = "incomplete"
        out["reason"] = "n1-cannot-express"
        return out
    subject_tasks = None
    if persp.get("entityId"):
        subject_tasks = ((point.get("state") or {}).get("characters")
                         or {}).get(persp["entityId"], {}).get("tasks")
    n2 = select_facts(n1["facts"], persp, may_policy=may_policy,
                      subject_tasks=subject_tasks,
                      visible_other_actions=visible_other_actions)
    out["n2"] = {"arm": n2.get("arm"), "status": n2["status"],
                 "mayPolicy": n2.get("mayPolicy"),
                 "summary": n2.get("summary"),
                 "decisions": n2.get("decisions"),
                 "selectedCount": len(n2.get("selectedFactIds", []))}
    if n2["status"] == "stopped":
        out["status"] = "incomplete"
        out["reason"] = "n2-must-without-visibility-ground"
        out["n2"]["stops"] = n2.get("stops")
        return out
    if n2["status"] != "ok" or n2.get("invalidReferences") or n2.get("refusals"):
        out["status"] = "stopped-at-n2"
        out["n2"]["reason"] = n2.get("reason")
        out["n2"]["invalidReferences"] = n2.get("invalidReferences")
        return out
    selected = [f for f in n1["facts"]
                if f["factId"] in set(n2["selectedFactIds"])]
    if n1["facts"] and not selected:
        out["status"] = "incomplete"
        out["reason"] = "n2-empty-selection"
        return out
    new_kinds = sorted({f["kind"] for f in selected} - V2_MODEL_KINDS)
    if new_kinds:
        out["status"] = "unsupported"
        out["reason"] = "kind-awaiting-model-track"
        out["kinds"] = new_kinds
        return out
    names = {f["entityId"]: f["name"] for f in selected if f.get("entityId")}
    plan = n3_organize.plan_v3(
        selected, names, gender_hints,
        cross_group_guard=cross_group_guard)
    if "refusal" in plan:
        out["status"] = "stopped-at-n3"
        out["n3"] = {"planner": "plan_v3", "refusal": plan["refusal"]}
        return out
    problems = n3_organize.check_plan_v3(
        plan, selected, names, gender_hints,
        cross_group_guard=cross_group_guard)
    if problems:
        out["status"] = "stopped-at-n3"
        out["n3"] = {"planner": "plan_v3", "violations": problems}
        return out
    out["n3"] = {"planner": "plan_v3", "status": "ok",
                 "groups": len(plan["sentences"]),
                 "grants": sum(1 for s in plan["sentences"]
                               for g in s["coreference"])}
    out["plan"] = plan
    out["selectedFacts"] = selected
    render_text = render_input_v2(plan, selected)
    out["n4"] = {"renderer": "render_v2", "status": "rendered"}
    if real_tok is None:
        out["status"] = "stopped-at-token-gate"
        out["reason"] = ("no real tokenizer available to count the rendered "
                         "input; refusing the model call")
        return out
    n_tokens = real_tok.count(render_text)
    out["n4"]["inputTokensReal"] = n_tokens
    if n_tokens > V2_TOKEN_LIMIT:
        out["status"] = "unsupported"
        out["unsupportedReason"] = "input-too-long-real"
        return out
    out["n4"]["renderText"] = render_text
    out["status"] = "ready-for-model"
    return out


# ---------- the pipeline ----------------------------------------------------

def run_pipeline(point: dict, before: dict | None, perspective,
                 baseline: str = "B1", may_policy: str = "select") -> dict:
    """N1 -> N2 -> N3 -> N4 (program path). Any step can stop the pipeline;
    every stop is a structured status, never a silent pass.

    perspective is RESOLVED against the authoritative point state
    (n2_perspective.resolve_perspective; the subject defaults to the state's
    protagonist, the location to the subject's position) — a caller cannot
    inject a viewpoint the record does not support, and an unresolvable one
    stops as incomplete.

    Stop semantics (commit 1):
    - N1 diagnostics that mean an original change cannot become a fact
      stop with status `incomplete` (fix round 1c41587 #3);
    - a MUST fact without any visibility ground (e.g. a tracked task
      completed where the viewpoint cannot perceive it) stops as
      `incomplete` / n2-must-without-visibility-ground;
    - a selection that ends up empty while facts exist stops as
      `incomplete` / n2-empty-selection (narrating nothing is not success);
    - selected facts outside the FROZEN N4 model vocabulary stop as
      `unsupported` / kind-awaiting-model-track BEFORE organisation —
      nothing is narrated past a change the frozen chain cannot express."""
    out = {"pointId": point.get("pointId"), "version": point.get("version")}
    resolved = n2_perspective.resolve_perspective(
        point.get("state") or {}, (perspective or {}).get("entityId"),
        (perspective or {}).get("type", "protagonist"))
    if resolved["problems"]:
        out["status"] = "incomplete"
        out["reason"] = "perspective-unresolvable"
        out["problems"] = resolved["problems"]
        return out
    persp = resolved["perspective"]
    out["perspective"] = persp
    n1 = extract_facts(point, before)
    out["n1"] = {"factCount": len(n1["facts"]), "diagnostics": n1["diagnostics"]}
    blocking = [d for d in n1["diagnostics"]
                if d["code"] in INCOMPLETE_DIAGNOSTIC_CODES]
    if blocking:
        out["n1"]["blocking"] = blocking
        out["status"] = "incomplete"
        out["reason"] = ("N1 cannot express every original change as a "
                         "fact; the success path stops here (fix round "
                         "1c41587 #3)")
        return out
    subject_tasks = None
    if persp.get("entityId"):
        subject_tasks = ((point.get("state") or {}).get("characters")
                         or {}).get(persp["entityId"], {}).get("tasks")
    n2 = select_facts(n1["facts"], persp, may_policy=may_policy,
                      subject_tasks=subject_tasks)
    out["n2"] = {"arm": n2.get("arm"), "status": n2["status"],
                 "mayPolicy": n2.get("mayPolicy"),
                 "summary": n2.get("summary"),
                 "decisions": n2.get("decisions"),
                 "selectedCount": len(n2.get("selectedFactIds", []))}
    if n2["status"] == "stopped":
        out["status"] = "incomplete"
        out["reason"] = "n2-must-without-visibility-ground"
        out["n2"]["stops"] = n2.get("stops")
        return out
    if n2["status"] != "ok" or n2.get("invalidReferences") \
            or n2.get("refusals"):
        out["status"] = "stopped-at-n2"
        out["n2"]["reason"] = n2.get("reason")
        out["n2"]["invalidReferences"] = n2.get("invalidReferences")
        out["n2"]["refusals"] = n2.get("refusals")
        return out
    selected = [f for f in n1["facts"]
                if f["factId"] in set(n2["selectedFactIds"])]
    if n1["facts"] and not selected:
        # every visible change was a legal omission under the policy:
        # emitting no narration would be silent, so stop explicitly
        out["status"] = "incomplete"
        out["reason"] = "n2-empty-selection"
        return out
    # the frozen N4 model track narrates FROZEN_MODEL_KINDS only; selected
    # facts outside that set stop BEFORE organisation
    new_kinds = sorted({f["kind"] for f in selected} - FROZEN_MODEL_KINDS)
    if new_kinds:
        out["status"] = "unsupported"
        out["reason"] = "kind-awaiting-model-track"
        out["kinds"] = new_kinds
        out["kindFacts"] = [f["factId"] for f in selected
                            if f["kind"] not in FROZEN_MODEL_KINDS]
        return out
    n3 = organize(selected, baseline)
    out["n3"] = {"baseline": baseline, "status": n3["status"]}
    if n3["status"] != "ok":
        out["status"] = "stopped-at-n3"
        out["n3"]["violations"] = n3.get("violations")
        return out
    manifest = n1["facts"]
    binding = bind_point_full(point, before, manifest)
    # the interface coverage check runs against the SELECTED set — the full
    # manifest is authoritative for BINDING, while N3/N4 consume the
    # selection (the complete set is never silently re-admitted here)
    verdict = interface_check(n3["plan"], selected, binding)
    out["n4"] = {"status": verdict["status"]}
    if verdict["status"] == "accepted":
        out["n4"]["renderText"] = verdict["renderText"]
        out["n4"]["inputTokensStub"] = verdict["inputTokensStub"]
        out["n4"]["renderInput"] = verdict["renderInput"]
    elif "reason" in verdict:
        out["n4"]["reason"] = verdict["reason"]
    elif "reasons" in verdict:
        out["n4"]["reasons"] = verdict["reasons"]
    out["status"] = {"accepted": "ok", "unsupported": "unsupported",
                     "error": "stopped-at-n4",
                     "binding-failed": "stopped-at-binding"}[verdict["status"]]
    return out


# ---------- selftest ---------------------------------------------------------

def _task_def(tid, owner, goal, status="pending"):
    return {"id": tid, "ownerId": owner, "parentTaskId": None,
            "goal": goal, "status": status}


def make_pipeline_state(world="w_pipe", second_loc=True):
    locations = {"loc_1": {"id": "loc_1", "name": "管线镇", "parentLocationId": None,
                           "initialAppearance": "安静",
                           "slots": [{"id": "slot_a", "label": "上层格位"},
                                     {"id": "slot_b", "label": "下层格位"}]}}
    if second_loc:
        locations["loc_2"] = {"id": "loc_2", "name": "钟楼", "parentLocationId": None,
                              "initialAppearance": "旧", "slots": []}
    ws = WorldState.model_validate({
        "engineVersion": "world-engine-v1", "schemaVersion": 1,
        "worldId": world, "protagonistId": "char_pa",
        "time": {"calendar": "gregorian", "dateTime": "2026-11-01T00:00:00",
                 "instantOrdinal": 2},
        "initial": {
            "engineVersion": "world-engine-v1", "schemaVersion": 1,
            "worldId": world, "protagonistId": "char_pa",
            "initialTime": {"calendar": "gregorian",
                            "dateTime": "2026-11-01T00:00:00", "instantOrdinal": 1},
            "locations": locations, "items": {},
            "characters": {
                "char_pa": {"id": "char_pa", "name": "管线甲",
                            "initialPosition": {"containerId": "loc_1",
                                                "slotId": None, "relativeTo": None},
                            "initialAppearance": "常态",
                            "initialPersonality": "沉稳", "initialSanity": 10,
                            "tasks": {"task_1": _task_def("task_1", "char_pa", "把铜铃挂回钟楼"),
                                      "task_2": _task_def("task_2", "char_pa", "晒网")}},
                "char_pb": {"id": "char_pb", "name": "管线乙",
                            "initialPosition": {"containerId": "loc_1",
                                                "slotId": None, "relativeTo": None},
                            "initialAppearance": "常态",
                            "initialPersonality": "急躁", "initialSanity": 11,
                            "tasks": {"task_3": _task_def("task_3", "char_pb", "补网")}},
            },
        },
        "locations": {k: {"id": k, "appearanceChanges": []} for k in locations},
        "items": {},
        "characters": {
            "char_pa": {"id": "char_pa", "position": {"containerId": "loc_1",
                                                      "slotId": None, "relativeTo": None},
                        "personalityChanges": [], "sanity": 10,
                        "tasks": {"task_1": _task_def("task_1", "char_pa", "把铜铃挂回钟楼"),
                                  "task_2": _task_def("task_2", "char_pa", "晒网")}},
            "char_pb": {"id": "char_pb", "position": {"containerId": "loc_1",
                                                      "slotId": None, "relativeTo": None},
                        "personalityChanges": [], "sanity": 11,
                        "tasks": {"task_3": _task_def("task_3", "char_pb", "补网")}},
        },
    })
    return ws.model_dump(mode="json")


def make_point(version, deltas, time_advance, world="w_pipe", state=None,
               prev=None):
    return {"pointId": f"pt-{version}", "version": version,
            "state": state if state is not None else make_pipeline_state(world),
            "stateDigest": "d" * 8, "previousPointId": prev,
            "timeAdvance": time_advance, "entityDeltas": deltas}


def moved_delta(eid, to_container):
    return {"entityId": eid, "positionSet": {"containerId": to_container,
                                             "slotId": None, "relativeTo": None},
            "appearanceChanges": [], "personalityChanges": [],
            "subtasksAdded": [], "tasksAchieved": [], "sanitySet": None}


def selftest() -> int:
    failures = []

    def check(cond, label):
        if not cond:
            failures.append(label)

    state = make_pipeline_state()
    before_state = make_pipeline_state()
    before = make_point(1, {}, None, state=before_state, prev=None)
    # fix lineage: before is version 1, point is version 2
    before = {**before, "pointId": "pt-1", "version": 1}

    def point(deltas, amount, unit="minute", version=2, st=None):
        ta = None if amount is None else {"boundary": "elapsed",
                                          "duration": {"amount": amount, "unit": unit}}
        return make_point(version, deltas, ta, state=st or copy.deepcopy(state),
                          prev="pt-1")

    PERS = {"type": "protagonist"}

    # S1: legal `second` point — used to KeyError in the shared renderer
    deltas = {"char_pa": {**moved_delta("char_pa", "loc_2"),
                          "tasksAchieved": ["task_1"]}}
    st = copy.deepcopy(state)
    st["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                               "slotId": None, "relativeTo": None}
    st["characters"]["char_pa"]["tasks"]["task_1"]["status"] = "achieved"
    r = run_pipeline(point(deltas, 40, "second", st=st), before, PERS)
    check(r["status"] == "ok", f"S1 second pipeline: {r['status']}")
    check("四十秒" in (r.get("n4", {}).get("renderText") or ""), "S1 second rendering")
    # commit 1: N2 records a per-fact decision with a ground for EVERY fact
    n1s1 = extract_facts(point(deltas, 40, "second", st=st), before)
    dec1 = [d for d in (r.get("n2", {}).get("decisions") or []) if d.get("factId")]
    check(len(dec1) == len(n1s1["facts"])
          and all(d.get("ground") and d.get("class") in ("must", "may",
                                                         "invisible")
                  for d in dec1),
          f"S1 n2 decisions with grounds: {dec1}")

    # S1b: N5 judges the selftest template text for the same point
    n1 = extract_facts(point(deltas, 40, "second", st=st), before)
    text = generate_reference_text(n1["facts"])
    v = verify_text(n1["facts"], text)
    check(v["status"] == "checked" and not v["fails"] and not v["semanticUncertain"],
          f"S1b n5 clean: {json.dumps(v, ensure_ascii=False)[:200]}")

    # S2: zero-duration point — used to ValueError in num_cn
    r = run_pipeline(point({}, 0, "minute"), before, PERS)
    check(r["status"] == "ok", f"S2 zero pipeline: {r['status']}")
    check("零分钟" in (r.get("n4", {}).get("renderText") or ""), "S2 zero rendering")

    # S3: root point binds and renders 无变化 (the perspective resolves
    # against the FULL root state — a bare worldId stub cannot host a view)
    root = {"pointId": "pt-0", "version": 0,
            "state": make_pipeline_state(), "stateDigest": "d" * 8,
            "previousPointId": None, "timeAdvance": None, "entityDeltas": {}}
    r = run_pipeline(root, None, PERS)
    check(r["status"] == "ok", f"S3 root: {r['status']}")
    check(any(f["kind"] == "no_change" for f in extract_facts(root, None)["facts"]),
          "S3 no_change fact")

    # S4 (corrected): co-location does NOT create facts. char_pb is already
    # at loc_2 in the before state; char_pa moves there. N1 must emit only
    # the delta facts + time, never a positioned_at entry for the resident.
    st1 = make_pipeline_state()
    st1["characters"]["char_pb"]["position"] = {"containerId": "loc_2",
                                                "slotId": None, "relativeTo": None}
    before4 = make_point(1, {}, None, state=st1, prev=None)
    before4 = {**before4, "pointId": "pt-1", "version": 1}
    st2 = copy.deepcopy(st1)
    st2["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                                "slotId": None, "relativeTo": None}
    st2["characters"]["char_pa"]["sanity"] = 13
    deltas = {"char_pa": {**moved_delta("char_pa", "loc_2"), "sanitySet": 13}}
    n1 = extract_facts(point(deltas, 5, st=st2), before4)
    kinds = sorted(f["kind"] for f in n1["facts"])
    check(kinds == ["moved", "sanity_changed", "time"],
          f"S4 co-location adds no fact: {kinds}")
    check(all(f["kind"] != "positioned_at" for f in n1["facts"]),
          "S4 no positioned_at roster scan")

    # S4b (regression, review round): a destination with 100 co-located NPCs
    # still produces ONLY the mover's delta facts. The old roster scan would
    # have emitted 100 positioned_at facts and blown the 1-4 fact budget.
    st_many = make_pipeline_state()
    for i in range(100):
        eid, nm = f"npc_{i}", f"居民{i}"
        st_many["initial"]["characters"][eid] = {
            "id": eid, "name": nm,
            "initialPosition": {"containerId": "loc_2", "slotId": None,
                                "relativeTo": None},
            "initialAppearance": "常态", "initialPersonality": "沉默",
            "initialSanity": 9, "tasks": {}}
        st_many["characters"][eid] = {
            "id": eid,
            "position": {"containerId": "loc_2", "slotId": None,
                         "relativeTo": None},
            "appearanceChanges": [], "personalityChanges": [],
            "sanity": 9, "tasks": {}}
    st_many["characters"]["char_pa"]["position"] = {
        "containerId": "loc_2", "slotId": None, "relativeTo": None}
    n_many = extract_facts(
        point({"char_pa": moved_delta("char_pa", "loc_2")}, 5, st=st_many),
        before)
    check(len(n_many["facts"]) == 2
          and [f["kind"] for f in n_many["facts"]] == ["moved", "time"],
          f"S4b 100-NPC destination: {len(n_many['facts'])} facts")

    # S5: five SELECTED self facts -> unsupported/plan-too-long through the
    # REAL interface. Under the perspective rule the binding count is the
    # SELECTED set: other entities' facts are invisible, so the over-limit
    # case is built from the subject's own five (plus global time)
    deltas5 = {"char_pa": {**moved_delta("char_pa", "loc_2"),
                           "tasksAchieved": ["task_1", "task_2"],
                           "sanitySet": 15,
                           "appearanceChanges": [{"id": "ch_a1",
                                                  "text": "外袍被雨浸透",
                                                  "supersedes": []}]}}
    st5 = copy.deepcopy(state)
    st5["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                                "slotId": None, "relativeTo": None}
    st5["characters"]["char_pa"]["sanity"] = 15
    st5["characters"]["char_pa"]["tasks"]["task_1"]["status"] = "achieved"
    st5["characters"]["char_pa"]["tasks"]["task_2"]["status"] = "achieved"
    st5["characters"]["char_pa"]["appearanceChanges"] = [
        {"id": "ch_a1", "text": "外袍被雨浸透", "supersedes": []}]
    r = run_pipeline(point(deltas5, 5, st=st5), before, PERS)
    check(r["status"] == "unsupported" and r["n4"]["reason"] == "plan-too-long",
          f"S5 five facts: {r['status']}/{r.get('n4', {}).get('reason')}")

    # S6: new subtasks are EXTRACTED as subtask_added facts quoting the
    # parent goal; the frozen N4 model vocabulary stops them BEFORE
    # organisation (kind-awaiting-model-track), so the frozen chain never
    # narrates past a change it cannot express
    deltas_sub = {"char_pa": {**moved_delta("char_pa", "loc_2"),
                              "subtasksAdded": [{"id": "task_9",
                                                 "ownerId": "char_pa",
                                                 "parentTaskId": "task_1",
                                                 "goal": "找梯子",
                                                 "status": "pending"}]}}
    r_sub = run_pipeline(point(deltas_sub, 5), before, PERS)
    check(r_sub["status"] == "unsupported"
          and r_sub["reason"] == "kind-awaiting-model-track"
          and "subtask_added" in (r_sub.get("kinds") or []),
          f"S6 subtask kind gate: {r_sub['status']}/{r_sub.get('reason')}")
    n1 = extract_facts(point(deltas_sub, 5), before)
    sub = next((f for f in n1["facts"] if f["kind"] == "subtask_added"), None)
    check(sub is not None and sub["goal"] == "找梯子"
          and sub["parentGoal"] == "把铜铃挂回钟楼",
          f"S6 subtask fact expressed: {sub}")
    # an unresolvable parent goal stops incomplete, never invents one
    deltas_sub2 = {"char_pa": {**moved_delta("char_pa", "loc_2"),
                               "subtasksAdded": [{"id": "task_x",
                                                  "ownerId": "char_pa",
                                                  "parentTaskId": "task_ghost",
                                                  "goal": "爬梯子",
                                                  "status": "pending"}]}}
    r_sub2 = run_pipeline(point(deltas_sub2, 5), before, PERS)
    check(r_sub2["status"] == "incomplete"
          and any(d["code"] == "subtask-parent-unresolvable"
                  for d in r_sub2["n1"]["diagnostics"]),
          f"S6 subtask parent unresolvable: {r_sub2['status']}")

    # S6b: an unknown delta field is unprocessable -> incomplete
    deltas_unk = {"char_pa": {**moved_delta("char_pa", "loc_2"),
                              "someFutureField": 1}}
    r_unk = run_pipeline(point(deltas_unk, 5), before, PERS)
    check(r_unk["status"] == "incomplete"
          and any(d["code"] == "unknown-delta-field"
                  for d in r_unk["n1"]["diagnostics"]),
          f"S6b unknown field: {r_unk['status']}")

    # S6d (review round, first commit): an unknown POSITION key (schema
    # extension like "mood") cannot be compared before-vs-after — even
    # alongside a legal cross-container move it must stop, not slip through
    # as a bare move
    d_unk_pos = {"char_pa": {"entityId": "char_pa",
                             "positionSet": {"containerId": "loc_2",
                                             "slotId": None,
                                             "relativeTo": None,
                                             "mood": "sneaky"},
                             "appearanceChanges": [], "personalityChanges": [],
                             "subtasksAdded": [], "tasksAchieved": [],
                             "sanitySet": None}}
    st_unk = copy.deepcopy(state)
    st_unk["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                                   "slotId": None,
                                                   "relativeTo": None}
    r_unk_pos = run_pipeline(point(d_unk_pos, 5, st=st_unk), before, PERS)
    check(r_unk_pos["status"] == "incomplete"
          and any(d["code"] == "unknown-position-field"
                  for d in r_unk_pos["n1"]["diagnostics"]),
          f"S6d unknown position key: {r_unk_pos['status']}")

    # S6c (commit 1): the reviewer's position-aspect matrix, now EXPRESSED —
    # slot/relative changes become position_relative / slot_changed facts
    # with sources and clean bindings, and stop at the frozen-model kind
    # gate; they are never rendered as a bare container move. Plain moves
    # and carried-along relations stay ok.
    def pos_case(name, before_pos, after_pos, expect_status, expect_kind=None):
        st_p = copy.deepcopy(state)
        st_p["characters"]["char_pa"]["position"] = copy.deepcopy(after_pos)
        d_p = {"char_pa": {"entityId": "char_pa",
                           "positionSet": copy.deepcopy(after_pos),
                           "appearanceChanges": [], "personalityChanges": [],
                           "subtasksAdded": [], "tasksAchieved": [],
                           "sanitySet": None}}
        b_p = {**point({}, 5, st=copy.deepcopy(state), version=1),
               "pointId": "pt-1", "version": 1}
        if before_pos is not None:
            b_p["state"]["characters"]["char_pa"]["position"] = copy.deepcopy(before_pos)
        r_p = run_pipeline(point(d_p, 5, st=st_p), b_p, PERS)
        got_kinds = r_p.get("kinds") or []
        check(r_p["status"] == expect_status
              and (expect_kind is None or expect_kind in got_kinds),
              f"S6c {name}: {r_p['status']}/{r_p.get('reason')}/{got_kinds}")
        if expect_kind is not None:
            n1p = extract_facts(point(d_p, 5, st=st_p), b_p)
            fact = next((f for f in n1p["facts"] if f["kind"] == expect_kind),
                        None)
            check(fact is not None
                  and fact.get("source", {}).get("aspect")
                  in ("relativeTo", "slotId"),
                  f"S6c {name}: {expect_kind} fact with aspect source")
            problems = bind_point_full(point(d_p, 5, st=st_p), b_p,
                                       n1p["facts"])
            check(not problems, f"S6c {name}: binding clean ({problems})")

    plain = {"containerId": "loc_1", "slotId": None, "relativeTo": None}
    beside = {"containerId": "loc_1", "slotId": None,
              "relativeTo": {"entityId": "char_pb", "relation": "beside"}}
    behind = {"containerId": "loc_1", "slotId": None,
              "relativeTo": {"entityId": "char_pb", "relation": "behind"}}
    in_slot = {"containerId": "loc_1", "slotId": "slot_a", "relativeTo": None}
    pos_case("relativeTo-added", plain, beside, "unsupported",
             "position_relative")
    pos_case("relativeTo-changed", beside, behind, "unsupported",
             "position_relative")
    pos_case("relativeTo-cleared", beside, plain, "unsupported",
             "position_relative")
    pos_case("slot-added", plain, in_slot, "unsupported", "slot_changed")
    pos_case("slot-changed",
             in_slot, {"containerId": "loc_1", "slotId": "slot_b",
                       "relativeTo": None},
             "unsupported", "slot_changed")
    pos_case("slot-cleared", in_slot, plain, "unsupported", "slot_changed")
    # container-only change (slot/relative absent or unchanged) is NOT
    # blocked: the plain move and a carried-along beside relation stay ok
    pos_case("plain-move-ok", plain,
             {"containerId": "loc_2", "slotId": None, "relativeTo": None},
             "ok")
    pos_case("moved-with-unchanged-beside-ok", beside,
             {"containerId": "loc_2", "slotId": None,
              "relativeTo": {"entityId": "char_pb", "relation": "beside"}},
             "ok")

    # S7: version gap stops at binding
    r = run_pipeline(point({}, 5, version=3), before, PERS)
    check(r["status"] == "stopped-at-binding", f"S7 version gap: {r['status']}")

    # S8: N5 mismatch text -> semantic_uncertain, never auto-passed
    n1 = extract_facts(point(deltas, 40, "second", st=st), before)
    bad_text = "管线甲从管线镇来到了钟楼。前后零秒。"  # wrong duration value
    v = verify_text(n1["facts"], bad_text)
    check(v["semanticUncertain"] and v["autoPassed"] is False,
          f"S8 review not auto-passed: {json.dumps(v, ensure_ascii=False)[:160]}")

    # S9: the selection interface rejects illegal ids and unknown arms
    bad_sel = select_facts(n1["facts"], PERS, arm="manual",
                           selected_ids=["f1", "f404"])
    check(bad_sel["status"] == "error"
          and bad_sel["invalidReferences"] == ["f404"],
          f"S9 illegal fact id rejected: {bad_sel}")
    good_sel = select_facts(n1["facts"], PERS, arm="manual",
                            selected_ids=["f1"])
    check(good_sel["status"] == "ok", "S9 manual legal selection")
    n2 = select_facts([], PERS, arm="encoder-head")
    check(n2["status"] == "not-implemented", "S9 unknown arm status")
    all_sel = select_facts(n1["facts"], PERS, arm="select-all")
    check(all_sel["status"] == "ok"
          and len(all_sel["selectedFactIds"]) == len(n1["facts"]),
          "S9 select-all baseline still available")

    # S10: appearance/personality ADDED/MODIFIED/REMOVED, removals quoting
    # the superseded text resolved from the explicit before record
    st10 = copy.deepcopy(state)
    st10["characters"]["char_pa"]["appearanceChanges"] = [
        {"id": "ch_old", "text": "旧披风", "supersedes": []}]
    st10["characters"]["char_pa"]["personalityChanges"] = [
        {"id": "pe_old", "text": "言语简短", "supersedes": []}]
    before10 = {**point({}, 5, st=copy.deepcopy(st10), version=1),
                "pointId": "pt-1", "version": 1}
    d10 = {"char_pa": {"entityId": "char_pa", "positionSet": None,
                       "appearanceChanges": [
                           {"id": "ch_new", "text": "披风破了个洞",
                            "supersedes": []},
                           {"id": "ch_rem", "text": None,
                            "supersedes": ["ch_old"]}],
                       "personalityChanges": [
                           {"id": "pe_mod", "text": "变得多言",
                            "supersedes": ["pe_old"]}],
                       "subtasksAdded": [], "tasksAchieved": [],
                       "sanitySet": None}}
    n1 = extract_facts(point(d10, 5, st=st10), before10)
    kinds10 = sorted(f["kind"] for f in n1["facts"])
    check(kinds10 == ["appearance_changed", "appearance_removed",
                      "personality_changed", "time"], f"S10 kinds: {kinds10}")
    ap_rm = next(f for f in n1["facts"] if f["kind"] == "appearance_removed")
    ap_new = next(f for f in n1["facts"] if f["kind"] == "appearance_changed")
    pe_mod = next(f for f in n1["facts"] if f["kind"] == "personality_changed")
    check(ap_rm["text"] == "旧披风" and ap_rm["op"] == "removed"
          and ap_new["op"] == "added" and pe_mod["op"] == "modified",
          f"S10 ops/texts: {ap_rm} {ap_new} {pe_mod}")
    problems = bind_point_full(point(d10, 5, st=st10), before10, n1["facts"])
    check(not problems, f"S10 binding clean: {problems}")
    # an unresolvable superseded id stops the success path
    d10_bad = {"char_pa": {"entityId": "char_pa", "positionSet": None,
                           "appearanceChanges": [{"id": "ch_bad", "text": None,
                                                  "supersedes": ["ch_ghost"]}],
                           "personalityChanges": [], "subtasksAdded": [],
                           "tasksAchieved": [], "sanitySet": None}}
    r10 = run_pipeline(point(d10_bad, 5, st=copy.deepcopy(state)), before, PERS)
    check(r10["status"] == "incomplete"
          and any(d["code"] == "superseded-change-unresolvable"
                  for d in r10["n1"]["diagnostics"]),
          f"S10 unresolvable removal: {r10['status']}")
    # added appearance facts are within the frozen vocabulary and flow
    # through the whole program chain
    d10_ok = {"char_pa": {"entityId": "char_pa", "positionSet": None,
                          "appearanceChanges": [{"id": "ch_new2",
                                                 "text": "外袍被雨浸透",
                                                 "supersedes": []}],
                          "personalityChanges": [], "subtasksAdded": [],
                          "tasksAchieved": [], "sanitySet": None}}
    st10b = copy.deepcopy(state)
    st10b["characters"]["char_pa"]["appearanceChanges"] = [
        {"id": "ch_new2", "text": "外袍被雨浸透", "supersedes": []}]
    r10b = run_pipeline(point(d10_ok, 5, st=st10b),
                        {**point({}, 5, st=copy.deepcopy(state), version=1),
                         "pointId": "pt-1", "version": 1}, PERS)
    check(r10b["status"] == "ok"
          and "外袍被雨浸透" in (r10b.get("n4", {}).get("renderText") or ""),
          f"S10 appearance add end-to-end: {r10b['status']}")

    # S11: duplicate names are flagged on facts, never merged; the fact
    # keeps the mover's entity id
    st11 = make_pipeline_state()
    st11["initial"]["characters"]["char_pc"] = {
        "id": "char_pc", "name": "管线乙",
        "initialPosition": {"containerId": "loc_2", "slotId": None,
                            "relativeTo": None},
        "initialAppearance": "常态", "initialPersonality": "沉默",
        "initialSanity": 9, "tasks": {}}
    st11["characters"]["char_pc"] = {
        "id": "char_pc", "position": {"containerId": "loc_2", "slotId": None,
                                      "relativeTo": None},
        "appearanceChanges": [], "personalityChanges": [], "sanity": 9,
        "tasks": {}}
    before11 = {**point({}, 5, st=copy.deepcopy(st11), version=1),
                "pointId": "pt-1", "version": 1}
    d11 = {"char_pc": moved_delta("char_pc", "loc_1")}
    n1 = extract_facts(point(d11, 5, st=st11), before11)
    mv = next(f for f in n1["facts"] if f["kind"] == "moved")
    check(mv["name"] == "管线乙" and mv.get("nameAmbiguous") is True
          and mv["entityId"] == "char_pc",
          f"S11 duplicate name flagged: {mv}")

    # S12: the perspective rule classifies with grounds (unit level)
    facts12 = [
        {"factId": "f1", "kind": "moved", "entityId": "s1", "name": "甲",
         "at": "此地"},
        {"factId": "f2", "kind": "task_achieved", "entityId": "s1",
         "name": "甲", "goal": "修桥", "at": "此地"},
        {"factId": "f3", "kind": "task_achieved", "entityId": "s2",
         "name": "乙", "goal": "补网", "at": "此地"},
        {"factId": "f4", "kind": "personality_changed", "entityId": "s2",
         "name": "乙", "text": "变得急躁", "at": "此地"},
        {"factId": "f5", "kind": "sanity_changed", "entityId": "s2",
         "name": "乙", "from": 5, "to": 3, "at": "此地"},
        {"factId": "f6", "kind": "task_achieved", "entityId": "s3",
         "name": "丙", "goal": "修桥", "at": "彼处"},
        {"factId": "f7", "kind": "appearance_changed", "entityId": "l1",
         "name": "此地", "text": "招牌歪了", "at": "此地"},
        {"factId": "f8", "kind": "time", "amount": 3, "unit": "minute",
         "at": None},
    ]
    persp12 = {"type": "protagonist", "entityId": "s1", "at": "此地"}
    tasks12 = {"t1": {"goal": "修桥", "status": "pending"}}
    res12 = n2_perspective.classify_facts(facts12, persp12,
                                          subject_tasks=tasks12)
    dec = {d["factId"]: d for d in res12["decisions"] if d.get("factId")}
    check(dec["f1"]["class"] == "must"
          and dec["f1"]["ground"] == "self-position",
          f"S12 self move: {dec['f1']}")
    check(dec["f3"]["class"] == "invisible"
          and dec["f3"]["ground"] == "only-others",
          f"S12 other same-place task: {dec['f3']}")
    check(dec["f4"]["class"] == "invisible"
          and dec["f4"]["ground"] == "inner-state-private",
          f"S12 other inner state not visible despite co-location: {dec['f4']}")
    check(dec["f5"]["class"] == "invisible"
          and dec["f5"]["ground"] == "inner-state-private",
          f"S12 other sanity invisible: {dec['f5']}")
    check(dec["f6"]["class"] == "must"
          and dec["f6"]["ground"] == "tracked-task"
          and res12["status"] == "stopped"
          and res12["stops"][0]["code"] == "must-without-visibility-ground",
          f"S12 tracked task hidden -> stop: {dec['f6']}/{res12['status']}")
    check(dec["f7"]["class"] == "may" and dec["f7"]["selected"] is True,
          f"S12 co-located scenery may-selected: {dec['f7']}")
    check(dec["f8"]["class"] == "may", f"S12 time may: {dec['f8']}")
    # the SAME tracked task, visible at the subject's place, is a clean must
    res12b = n2_perspective.classify_facts(
        [dict(facts12[5], at="此地")], persp12, subject_tasks=tasks12)
    check(res12b["status"] == "ok"
          and res12b["decisions"][0]["class"] == "must"
          and res12b["decisions"][0]["ground"] == "tracked-task",
          f"S12 tracked task visible: {res12b['decisions'][0]}")
    # the conservative omit policy selects no may facts
    res12c = n2_perspective.classify_facts(facts12, persp12,
                                           may_policy="omit")
    check(all(not d["selected"] for d in res12c["decisions"]
              if d["class"] == "may"),
          "S12 omit policy selects no may facts")
    # omniscient: focus = position-fact entities; their position facts must,
    # their other facts may, non-focus entities invisible
    res12d = n2_perspective.classify_facts(
        [{"factId": "g1", "kind": "moved", "entityId": "s1", "name": "甲",
          "at": "旧钟铺"},
         {"factId": "g2", "kind": "personality_changed", "entityId": "s1",
          "name": "甲", "text": "变得谨慎", "at": "旧钟铺"},
         {"factId": "g3", "kind": "personality_changed", "entityId": "s2",
          "name": "乙", "text": "变得急躁", "at": "旧钟铺"}],
        {"type": "omniscient", "entityId": None, "at": "全局"})
    dd = {d["factId"]: d for d in res12d["decisions"] if d.get("factId")}
    check(dd["g1"]["class"] == "must"
          and dd["g1"]["ground"] == "omniscient-focus-position"
          and dd["g2"]["class"] == "may" and dd["g3"]["class"] == "invisible",
          f"S12 omniscient focus: {dd}")

    # S13: an empty selection under the omit policy stops explicitly; the
    # default select policy narrates the same scenery
    d13 = {"loc_1": {"entityId": "loc_1", "positionSet": None,
                     "appearanceChanges": [{"id": "ch_l1",
                                            "text": "镇口的招牌歪了",
                                            "supersedes": []}],
                     "personalityChanges": [], "subtasksAdded": [],
                     "tasksAchieved": [], "sanitySet": None}}
    st13 = copy.deepcopy(state)
    st13["locations"]["loc_1"]["appearanceChanges"] = [
        {"id": "ch_l1", "text": "镇口的招牌歪了", "supersedes": []}]
    before13 = {**point({}, 5, st=copy.deepcopy(state), version=1),
                "pointId": "pt-1", "version": 1}
    r13 = run_pipeline(point(d13, 5, st=st13), before13, PERS,
                       may_policy="omit")
    check(r13["status"] == "incomplete"
          and r13["reason"] == "n2-empty-selection",
          f"S13 empty selection stop: {r13['status']}/{r13.get('reason')}")
    r13b = run_pipeline(point(d13, 5, st=copy.deepcopy(st13)), before13, PERS)
    check(r13b["status"] == "ok"
          and "镇口的招牌歪了" in (r13b.get("n4", {}).get("renderText") or ""),
          f"S13 select policy narrates scenery: {r13b['status']}")

    # S14: a must fact without any visibility ground stops END-TO-END —
    # 乙 completes a task with the same goal as 甲's pending 晒网, at a
    # place 甲 is not and cannot perceive
    st14 = make_pipeline_state()
    st14["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                                 "slotId": None,
                                                 "relativeTo": None}
    st14["characters"]["char_pb"]["tasks"]["task_3"]["goal"] = "晒网"
    st14["characters"]["char_pb"]["tasks"]["task_3"]["status"] = "achieved"
    before14 = {**point({}, 5, st=make_pipeline_state(), version=1),
                "pointId": "pt-1", "version": 1}
    d14 = {"char_pb": {"entityId": "char_pb", "positionSet": None,
                       "appearanceChanges": [], "personalityChanges": [],
                       "subtasksAdded": [], "tasksAchieved": ["task_3"],
                       "sanitySet": None}}
    r14 = run_pipeline(point(d14, 5, st=st14), before14, PERS)
    check(r14["status"] == "incomplete"
          and r14["reason"] == "n2-must-without-visibility-ground",
          f"S14 must-without-ground stop: {r14['status']}/{r14.get('reason')}")

    # S15: perspective resolution is authoritative
    r15 = run_pipeline(point({}, 5), before,
                       {"type": "protagonist", "entityId": "char_ghost"})
    check(r15["status"] == "incomplete"
          and r15["reason"] == "perspective-unresolvable",
          f"S15 unregistered subject: {r15['status']}/{r15.get('reason')}")
    r15b = run_pipeline(point({}, 5), before, {"type": "omniscient"})
    check(r15b["status"] == "ok"
          and r15b["perspective"]["type"] == "omniscient",
          f"S15 omniscient resolved: {r15b['status']}")

    # S16: extended renderer entries render; frozen kinds unchanged; the
    # renderer's relation table must equal the classifier's (they are kept
    # as separate copies because n4_corpus cannot import n2_selection)
    from n4_render import render_entry, RELATION_CN as RENDER_RELATIONS
    check(RENDER_RELATIONS == n2_perspective.RELATION_CN,
          "S16 relation tables equal")
    check(render_entry({"kind": "position_relative", "name": "甲",
                        "targetName": "乙", "relation": "beside",
                        "op": "changed"}) == "相对位置：甲 现在在乙旁边",
          "S16 relative render")
    check(render_entry({"kind": "position_relative", "name": "甲",
                        "targetName": "乙", "relation": "beside",
                        "op": "removed"}) == "相对位置：甲 不再在乙旁边",
          "S16 relative removal render")
    check(render_entry({"kind": "slot_changed", "name": "甲", "at": "木箱",
                        "slotLabel": "上层格位", "op": "added"})
          == "槽位：甲 现在位于木箱的上层格位", "S16 slot render")
    check(render_entry({"kind": "moved", "name": "甲", "from": "A",
                        "to": "B"}) == "位置：甲 从A到B",
          "S16 frozen moved render unchanged")
    check(render_entry({"kind": "subtask_added", "name": "甲", "goal": "找梯子",
                        "parentGoal": "修阁楼"})
          == "新任务：甲 接到「找梯子」（隶属「修阁楼」）",
          "S16 subtask render")

    # S17 (commit 2): the v2 chain renders the GROUPED interface with an
    # appellation grant and reaches ready-for-model; new kinds flow
    st17 = copy.deepcopy(state)
    st17["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                                 "slotId": None,
                                                 "relativeTo": None}
    st17["characters"]["char_pa"]["sanity"] = 14
    st17["characters"]["char_pa"]["tasks"]["task_1"]["status"] = "achieved"
    d17 = {"char_pa": {**moved_delta("char_pa", "loc_2"), "sanitySet": 14,
                       "tasksAchieved": ["task_1"],
                       "subtasksAdded": [{"id": "task_x", "ownerId": "char_pa",
                                          "parentTaskId": "task_1",
                                          "goal": "找梯子",
                                          "status": "pending"}]}}
    pt17 = point(d17, 5, st=st17)

    class _Tok:
        def count(self, text):
            return 100

    r17 = run_pipeline_v2(pt17, before, PERS,
                          gender_hints={"char_pa": "male",
                                        "char_pb": "male"},
                          real_tok=_Tok())
    check(r17["status"] == "ready-for-model"
          and r17["n3"]["groups"] == 1
          and r17["n3"]["grants"] == 1
          and "称谓：管线甲=他" in r17["n4"]["renderText"]
          and "新任务：管线甲" in r17["n4"]["renderText"],
          f"S17 v2 chain: {r17['status']}/{r17.get('reason')}")
    # the grants are data, not decoration: empty hints strip the 称谓 line
    r17b = run_pipeline_v2(pt17, before, PERS, gender_hints=None,
                           real_tok=_Tok())
    check(r17b["status"] == "ready-for-model"
          and "称谓" not in r17b["n4"]["renderText"],
          "S17 v2 ablated render (no grants)")

    # S17c (review round): the v2 default is omit, not select-all-visible.
    # Time is a may fact; it is not narrated unless the select arm is asked
    # for explicitly. The must facts (move/sanity/task/subtask) still flow.
    r17c = run_pipeline_v2(pt17, before, PERS,
                           gender_hints={"char_pa": "male"}, real_tok=_Tok())
    check(r17c["status"] == "ready-for-model"
          and r17c["n2"]["summary"]["mayPolicy"] == "omit"
          and "时间推进" not in r17c["n4"]["renderText"]
          and "新任务：管线甲" in r17c["n4"]["renderText"],
          f"S17c v2 default omit: {r17c['status']}/"
          f"{r17c['n2']['summary']['mayPolicy']}")
    # the explicit select arm keeps the old comparison behavior
    r17d = run_pipeline_v2(pt17, before, PERS, may_policy="select",
                           gender_hints={"char_pa": "male"}, real_tok=_Tok())
    check(r17d["status"] == "ready-for-model"
          and r17d["n2"]["summary"]["mayPolicy"] == "select"
          and "约五分钟" in r17d["n4"]["renderText"],
          f"S17d v2 select arm: {r17d['status']}/"
          f"{r17d['n2']['summary']['mayPolicy']}")

    # S17e (review round): the cross-group pronoun guard reaches the real
    # v2 chain. A (male) and B (male) are in separate groups; A's tracked
    # task is completed by B at the same place. The guard licenses only A's
    # pronoun; B keeps its name, so the input never contains 管线乙=他.
    st17e = copy.deepcopy(state)
    st17e["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                                 "slotId": None,
                                                 "relativeTo": None}
    st17e["characters"]["char_pa"]["sanity"] = 14
    st17e["characters"]["char_pa"]["tasks"]["task_2"]["goal"] = "晒网"
    st17e["characters"]["char_pb"]["position"] = {"containerId": "loc_2",
                                                 "slotId": None,
                                                 "relativeTo": None}
    st17e["characters"]["char_pb"]["tasks"]["task_3"]["goal"] = "晒网"
    st17e["characters"]["char_pb"]["tasks"]["task_3"]["status"] = "achieved"
    d17e = {"char_pa": {**moved_delta("char_pa", "loc_2"), "sanitySet": 14},
            "char_pb": {"entityId": "char_pb", "positionSet": None,
                        "appearanceChanges": [], "personalityChanges": [],
                        "subtasksAdded": [], "tasksAchieved": ["task_3"],
                        "sanitySet": None}}
    r17e = run_pipeline_v2(point(d17e, 8, st=st17e), before, PERS,
                           gender_hints={"char_pa": "male",
                                         "char_pb": "male"},
                           real_tok=_Tok())
    check(r17e["status"] == "ready-for-model"
          and r17e["n3"]["groups"] == 2
          and r17e["n3"]["grants"] == 1
          and "称谓：管线甲=他" in r17e["n4"]["renderText"]
          and "管线乙=他" not in r17e["n4"]["renderText"],
          f"S17e cross-group guard: {r17e['status']}/"
          f"{r17e.get('n3')}")

    # S18: over the 128 real-token limit the v2 chain refuses BEFORE any
    # model call
    class _Big:
        def count(self, text):
            return 129

    r18 = run_pipeline_v2(pt17, before, PERS, gender_hints={"char_pa": "male"},
                          real_tok=_Big())
    check(r18["status"] == "unsupported"
          and r18.get("unsupportedReason") == "input-too-long-real",
          f"S18 v2 over-limit: {r18['status']}")

    # S19: no real tokenizer -> stopped-at-token-gate, never a guess
    r19 = run_pipeline_v2(pt17, before, PERS, gender_hints={"char_pa": "male"},
                          real_tok=None)
    check(r19["status"] == "stopped-at-token-gate",
          f"S19 v2 no-counter: {r19['status']}")

    for f in failures:
        print("SELFTEST FAIL:", f)
    print("narration-pipeline selftest:",
          "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    if args.selftest:
        rc = selftest()
        if args.out:
            pathlib.Path(args.out).write_text(json.dumps(
                {"module": "narration_pipeline", "selftest": "PASS" if rc == 0 else "FAIL"},
                ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        return rc
    parser.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())

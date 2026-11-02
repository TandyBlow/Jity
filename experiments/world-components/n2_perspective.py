# N2 perspective content selection (commit 1 of the three-commit narrative
# completion): the real classification rule that replaces the pipeline's
# select-all placeholder. Semantics follow the frozen D2 annotation rubric
# (design/world-engine-reports/components/n2-annotation-rubric.md v1) with
# the strengthening the C task brief demands: visibility must have a GROUND,
# and co-location alone never reveals another entity's inner state (a
# secret stays secret even in the same room).
#
# Inputs are read-only:
#   facts        the FULL N1 fact set (ids, kinds, entityId, at, ...) — the
#                complete set stays authoritative for binding and checking;
#                only the selected subset is handed to N3/N4
#   perspective  {"type": "protagonist"|"location-limited"|"omniscient",
#                 "entityId": <subject id or None>, "at": <resolved place>}
#                — resolved from the AUTHORITATIVE point state by
#                resolve_perspective, never from caller prose
#   subject_tasks  optional {taskId: {"goal", "status"}} of the subject (the
#                point state's own record). The tracked-task must rule
#                (rubric §2.3d) needs it; without it the rule cannot fire.
#
# Per-fact decisions record class (must / may / invisible), the visibility
# ground code and a Chinese reason — every selection AND every omission is
# accounted for. Three explicit non-success outcomes exist: a must fact
# without any visibility ground (tracked task completed elsewhere the
# viewpoint cannot perceive) STOPS the pipeline; an unknown fact kind is
# REFUSED (never silently classified); a selection that ends up empty while
# facts exist is the caller's stop (empty narrations are not success).
#
# This module is pure: no imports from the pipeline, no I/O, no labels — it
# never reads answer keys or gold files.
#
# N4 narrative arm (opt-in, visible_other_actions=True): another entity's
# co-located moved/outcome/appearance change is a `may` fact (selectable),
# because the viewpoint can see the action. Task goal/status and inner
# states remain invisible. The old v2 arm keeps the flag False, so its
# only-others behaviour is unchanged; `outcome` is the surface action result
# and is deliberately distinct from the internal `task_achieved`.

RELATION_CN = {"under": "下方", "above": "上方", "beside": "旁边",
               "in_front_of": "前方", "behind": "后方"}

PERSPECTIVE_TYPES = {"protagonist", "location-limited", "omniscient"}

# kinds an ordinary co-located observer can perceive happening
OBSERVABLE_KINDS = {"moved", "positioned_at", "task_achieved", "subtask_added",
                    "outcome", "appearance_changed", "appearance_removed",
                    "position_relative", "slot_changed"}
# `outcome` is the SURFACE action result (resultText); `task_achieved` is the
# internal task status/goal. They are deliberately distinct: another
# character's visible action result is narratable, while another character's
# task goal/status is not (the task-goal leak this branch is fixing).
# inner states of OTHERS: never observable, whatever the location — the
# anti-secret rule (co-location is not a visibility ground for these)
INNER_KINDS = {"personality_changed", "personality_removed", "sanity_changed"}
# the subject's own position facts are must-say (rubric §2.3c 位置)
MUST_POSITION_KINDS = {"moved", "positioned_at", "position_relative",
                       "slot_changed"}

MAY_POLICIES = {"omit", "select"}

# N4 narrative selection arm: visible actions/changes of OTHER characters are
# narratable when co-located. This is opt-in because the frozen v2 arm keeps
# its only-others policy. Internal task status/goals remain excluded.
VISIBLE_OTHER_ACTION_KINDS = {
    "moved", "positioned_at", "position_relative", "slot_changed",
    "outcome", "appearance_changed", "appearance_removed",
}


def resolve_perspective(state: dict, subject_id: str | None = None,
                        ptype: str = "protagonist") -> dict:
    """Resolve and validate the perspective against the AUTHORITATIVE point
    state. The subject defaults to the state's protagonistId; the location
    is always the subject's position resolved through the state — a caller
    cannot inject a location the record does not support. Returns
    {"perspective": {...}, "problems": [...]} — problems non-empty means
    the caller must stop, not narrate with a guessed viewpoint."""
    problems = []
    if ptype not in PERSPECTIVE_TYPES:
        return {"perspective": None,
                "problems": [f"unknown-perspective-type:{ptype}"]}
    if ptype == "omniscient":
        return {"perspective": {"type": "omniscient", "entityId": None,
                                "at": "全局"}, "problems": []}
    subject = subject_id or (state or {}).get("protagonistId")
    if not subject:
        return {"perspective": None, "problems": ["perspective-subject-missing"]}
    characters = (state or {}).get("characters") or {}
    entry = characters.get(subject)
    if entry is None:
        return {"perspective": None,
                "problems": [f"perspective-subject-unregistered:{subject}"]}
    at = _container_name_of_state(state, (entry or {}).get("position"))
    if at is None:
        return {"perspective": None,
                "problems": [f"perspective-position-unresolvable:{subject}"]}
    return {"perspective": {"type": ptype, "entityId": subject, "at": at},
            "problems": []}


def _container_name_of_state(state: dict, position) -> str | None:
    """Container display name from the LIVE state's initial registry (the
    same authority the pipeline's entity_name uses)."""
    if not position:
        return None
    cid = position.get("containerId")
    if cid is None:
        return None
    for group in ("locations", "items", "characters"):
        entry = (((state or {}).get("initial") or {}).get(group) or {}).get(cid)
        if entry is not None:
            return entry.get("name")
    return None


def subject_task_goals(subject_tasks: dict | None) -> set:
    """Goals of the subject's tasks that are still in progress — the
    tracked-task must rule only follows tasks the subject is chasing."""
    out = set()
    for task in (subject_tasks or {}).values():
        if isinstance(task, dict) and task.get("status") == "pending" \
                and task.get("goal"):
            out.add(task["goal"])
    return out


def _visibility_ground(fact: dict, perspective: dict) -> tuple[bool, str]:
    """(visible, ground) per the rubric §3 order, with the anti-secret
    strengthening: co-location never makes another entity's inner state
    visible."""
    if perspective["type"] == "omniscient":
        return True, "omniscient"
    if fact.get("entityId") is not None \
            and fact["entityId"] == perspective.get("entityId"):
        return True, "self-state"
    kind = fact.get("kind")
    if kind == "time":
        return True, "global-time"
    if kind == "no_change":
        scope = fact.get("scope")
        if scope == "全局":
            return True, "global-scope"
        if scope is not None and scope == perspective.get("at"):
            return True, "co-location"
        return False, "other-location"
    if fact.get("at") is not None and fact["at"] == perspective.get("at"):
        if kind in INNER_KINDS:
            return False, "inner-state-private"
        if kind in OBSERVABLE_KINDS:
            return True, "co-location"
        return False, f"unknown-kind-observability:{kind}"
    return False, "other-location"


def _omniscient_focus(facts: list) -> tuple[set, str]:
    """Rubric §4: the focus is the set of characters that changed position;
    with no position facts at all, the entity carrying the most facts
    (first-appearance tie-break) becomes the focus, and that fallback is
    recorded so it is never silent."""
    position_entities, counts, order = set(), {}, []
    for fact in facts:
        eid = fact.get("entityId")
        if not eid:
            continue
        counts[eid] = counts.get(eid, 0) + 1
        if eid not in order:
            order.append(eid)
        if fact.get("kind") in ("moved", "positioned_at"):
            position_entities.add(eid)
    if position_entities:
        return position_entities, "omniscient-focus:position-facts"
    if order:
        best = max(order, key=lambda e: (counts[e], -order.index(e)))
        return {best}, "omniscient-focus:most-facts-fallback"
    return set(), "omniscient-focus:none"


def classify_facts(facts: list, perspective: dict,
                   subject_tasks: dict | None = None,
                   may_policy: str = "select",
                   visible_other_actions: bool = False) -> dict:
    """Classify every fact and apply the selection policy. Returns
    {"status": "ok"|"stopped", "stops", "refusals", "decisions",
     "selectedFactIds", "summary"}.

    may_policy: "select" (the frozen P1-rule comparison arm — every VISIBLE
    may fact is written, while invisible facts are excluded with their
    grounds) or "omit" (only must facts are selected, may facts are omitted
    with a recorded reason). The v2 product pipeline passes "omit" by
    default; "select" must be requested explicitly and is never evidence of
    narrative salience. Invisible facts are never selected under either
    policy.
    visible_other_actions: opt-in N4 narrative arm. When True, another
    entity's co-located moved/outcome/appearance change is `may`; task
    goal/status and inner states stay invisible. Default False preserves
    the frozen v2 arm."""
    if may_policy not in MAY_POLICIES:
        return {"status": "stopped",
                "stops": [{"code": "unknown-may-policy", "policy": may_policy}],
                "refusals": [], "decisions": [], "selectedFactIds": [],
                "summary": {}}
    valid_ids = {f["factId"] for f in facts}
    goals = subject_task_goals(subject_tasks)
    decisions, stops, refusals, selected = [], [], [], []
    focus, focus_note = ((set(), "") if perspective["type"] != "omniscient"
                         else _omniscient_focus(facts))
    if focus_note:
        decisions.append({"factId": None, "kind": None, "class": "note",
                          "ground": focus_note, "selected": False,
                          "reason": "全知视角焦点判定：" + focus_note})
    for fact in facts:
        fid, kind = fact.get("factId"), fact.get("kind")
        if fid not in valid_ids or kind is None:
            refusals.append({"factId": fid,
                             "code": "malformed-fact",
                             "reason": "事实缺少合法 factId 或 kind，拒绝分类"})
            continue
        visible, ground = _visibility_ground(fact, perspective)
        eid = fact.get("entityId")
        if visible and kind not in OBSERVABLE_KINDS and kind not in INNER_KINDS \
                and kind not in ("time", "no_change"):
            refusals.append({"factId": fid, "code": "unknown-kind",
                             "reason": f"未知事实种类 {kind}，拒绝分类（不猜测可见性）"})
            continue
        cls, sel_ground, reason = _classify_one(
            fact, perspective, focus, goals, visible, ground,
            visible_other_actions=visible_other_actions)
        if cls == "stop":
            stops.append({"factId": fid, "code": "must-without-visibility-ground",
                          "ground": ground, "reason": reason})
            decisions.append({"factId": fid, "kind": kind, "class": "must",
                              "ground": "tracked-task", "selected": False,
                              "reason": reason})
            continue
        is_selected = cls == "must" or (cls == "may" and may_policy == "select")
        if is_selected:
            selected.append(fid)
        decisions.append({"factId": fid, "kind": kind, "class": cls,
                          "ground": sel_ground, "selected": is_selected,
                          "reason": reason})
    unknown = [d["factId"] for d in decisions if d["factId"] is not None
               and d["factId"] not in valid_ids]
    summary = {"must": sum(1 for d in decisions if d["class"] == "must"),
               "may": sum(1 for d in decisions if d["class"] == "may"),
               "invisible": sum(1 for d in decisions if d["class"] == "invisible"),
               "selected": len(selected),
               "mayPolicy": may_policy}
    status = "stopped" if stops else "ok"
    return {"status": status, "stops": stops, "refusals": refusals,
            "decisions": decisions, "selectedFactIds": selected,
            "invalidReferences": unknown, "summary": summary}


def _classify_one(fact: dict, perspective: dict, focus: set,
                  goals: set, visible: bool, ground: str,
                  visible_other_actions: bool = False) -> tuple:
    """One fact's class + recorded ground + Chinese reason. Returns
    ("stop", ground, reason) when a must fact has no visibility ground."""
    fid, kind = fact.get("factId"), fact.get("kind")
    eid = fact.get("entityId")
    is_self = eid is not None and perspective.get("entityId") is not None \
        and eid == perspective["entityId"]
    if perspective["type"] == "omniscient":
        if eid is None:
            return "may", ground, "全知视角的全局事实（时间/无变化），可写可省"
        if eid in focus:
            if kind in MUST_POSITION_KINDS:
                return "must", "omniscient-focus-position", \
                    "全知视角焦点人物的位置变化，必述"
            if kind in ("task_achieved", "subtask_added"):
                return "must", "omniscient-focus-goal", \
                    "全知视角焦点人物的目标/在追任务，必述（rubric §4）"
            if kind == "sanity_changed":
                return "must", "omniscient-focus-safety", \
                    "全知视角焦点人物的理智变化（安全），必述（rubric §4）"
            return "may", "omniscient-focus", \
                "全知视角焦点人物的其余可见事实，可写可省"
        return "invisible", "only-others-nonfocus", \
            "全知视角下非焦点人物的事实，省略"
    if is_self:
        if kind == "outcome":
            return "must", "self-outcome", "视角人物自己的可见行动结果，必述"
        if kind == "task_achieved":
            return "must", "self-task", "视角人物自己的任务达成，必述"
        if kind == "subtask_added":
            return "must", "self-task", "视角人物自己接到的新任务，必述"
        if kind == "sanity_changed":
            return "must", "self-safety", "视角人物自己的理智变化（安全），必述"
        if kind in MUST_POSITION_KINDS:
            return "must", "self-position", "视角人物自己的位置变化，必述"
        if kind in ("appearance_changed", "appearance_removed",
                    "personality_changed", "personality_removed"):
            return "may", ground, "视角人物自己的描述类变化，可见但可省"
        if kind == "time":
            return "may", ground, "时间推进对视角人物可见，可写可省"
        if kind == "no_change":
            return "may", ground, "无变化事实可见，可写可省"
        return "invisible", ground, "视角人物的事实种类无法归类，省略"
    # another entity's fact
    if kind == "task_achieved" and fact.get("goal") in goals:
        if not visible:
            return "stop", ground, (
                "在追任务由他人在视角人物无法感知之处完成：必述与可见性冲突，"
                "明确停止而不是盲目写入或静默丢弃")
        return "must", "tracked-task", "视角人物在追的任务由他人完成，必述"
    if not visible:
        if ground == "inner-state-private":
            return "invisible", ground, \
                "他人的内心状态不因同处一地而可见，不泄露"
        if ground == "other-location":
            return "invisible", ground, "发生在视角人物感知范围之外，省略"
        return "invisible", ground, "视角人物不可见，省略"
    if visible_other_actions and kind in VISIBLE_OTHER_ACTION_KINDS:
        return "may", ground, "他人在同地的可见动作/变化，可写可省（N4 叙事选择臂）"
    if eid is None:
        # global facts (time / no_change) belong to no one
        return "may", ground, "全局事实，可写可省"
    group = fact.get("entityGroup")
    if group in ("locations", "items"):
        return "may", ground, "同处一地的场景/物件细节，可写可省"
    if group is None and kind == "appearance_changed":
        # group-less facts (the hand-built D2 dev-set shape): their
        # co-located appearance facts are location scenery — a documented
        # fallback; pipeline facts always carry entityGroup
        return "may", ground, \
            "同处一地的场景细节（事实未带主体分组，按场景处理），可写可省"
    return "invisible", "only-others", \
        "仅涉及他人且非在追任务，即使同处一地也省略"

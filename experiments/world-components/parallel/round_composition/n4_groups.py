"""N4.1 grouped input renderer (program-only, deterministic, no model).

Only the N4.0 arrangement changes against the v3 packer: facts are rendered
inside the sentence group that must carry them, movement gets explicit
起点/终点 lines, and each group carries its own writing rules. The scene,
character and perspective blocks and the prohibition text are copied from the
v3 packer so the comparison keeps them fixed.

Same-name actors: the descriptor comes from the authoritative character state
(current personality, else initial personality), is bound to the entityId, and
is written into that entity's fact block. If no descriptor exists, the fact is
blocked rather than invented.

Blocked facts: the rest of the row is still rendered for diagnosis, but the row
is marked `productQualified = False`, so a partial passage can never be counted
as a qualified product and a blocked fact is never mistaken for a model
omission.

Usage:
    from n4_groups import pack_grouped_input
    out = pack_grouped_input(case, plan, world, selected_fact_ids)
    out["status"] in {"ok", "blocked", "error"}
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent.parent
for p in (str(WC), str(WC / "n4_input_renderer"),
          str(WC / "n4_input_renderer" / "..")):
    if p not in sys.path:
        sys.path.insert(0, p)

from n4_input_renderer.packer import (  # noqa: E402
    KIND_LABEL,
    _fact_payload,
    _selected_time_facts,
    _validate_plan,
    _validate_scene,
)
from n4_input_renderer.renderer import (  # noqa: E402
    N4RenderError,
    _loc_name,
    _pov_name,
)
import character_identity  # noqa: E402

VERSION = "n4-groups-v0.2"

# The requirement line the v3 batch ACTUALLY sent, taken from the registration.
# The packer default is not enough: v3 replaced the line as a whole, so the A
# arm and this renderer must carry the same replacement text, or the comparison
# changes the writing constraints as well.
REGISTRATION = HERE / "fixtures" / "batch-v3.json"
DEFAULT_REQUIREMENT_LINE = ("要求：写场景、行动与视角人物心理；不写任务标题、"
                            "数值面板、具体时长、字段名；不新增未列出的具名人物/"
                            "物品/地点；他人只写可见动作。")


def registered_requirement_line(path=REGISTRATION):
    doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    line = ((doc.get("intervention") or {}).get("replacementLine")
            or "").strip()
    if not line.startswith("要求："):
        raise N4RenderError("requirement-line-missing", str(path))
    return line
GROUP_RULES = ("写作要求：在正文里完整表达本组事实；"
               "移动需要交代起点、终点和人物。")

# which fact kinds get an explicit person line and a value line
PERSON_LINE = {"moved", "outcome", "task_achieved", "subtask_added",
               "sanity_changed", "appearance_changed", "appearance_removed",
               "personality_changed", "personality_removed",
               "position_relative", "slot_changed"}


def _initial(state, eid):
    return ((state.get("initial") or {}).get("characters") or {}).get(eid) or {}


def _current(state, eid):
    return ((state.get("characters") or {}).get(eid)) or {}


def _last_change(state, eid, field):
    changes = _current(state, eid).get(field) or []
    for ch in reversed(changes):
        if isinstance(ch, dict) and ch.get("text"):
            return ch["text"]
    return None


def descriptor(state, eid, identities=None):
    """Authoritative descriptor, read from the shared identity record."""
    ids = identities if identities is not None else \
        character_identity.build_identities(state)
    return character_identity.descriptor_for(ids, eid)


def _same_name_entities(facts):
    by_name = {}
    for f in facts:
        if f.get("entityGroup") == "characters" and f.get("name") \
                and f.get("entityId"):
            by_name.setdefault(f["name"], set()).add(f["entityId"])
    return {n: sorted(e) for n, e in by_name.items() if len(e) >= 2}


def _block(fact, state, same_names, seen_eids, identities=None):
    """Render one fact as a block; return (lines|None, blocked|None)."""
    kind = fact.get("kind")
    name = fact.get("name")
    eid = fact.get("entityId")
    fid = fact.get("factId")
    label = KIND_LABEL.get(kind)
    if label is None:
        raise N4RenderError("unsupported-fact-kind", kind)
    head = f"{fid}｜{label}"
    if kind == "time":
        return [head, "时间经过"], None
    if kind == "no_change":
        return [head, "无变化"], None
    if kind == "moved" and (not fact.get("from") or not fact.get("to")):
        return None, {"factId": fid, "reason": "missing-field",
                      "detail": "moved needs from/to"}
    person = name
    if name in same_names:
        ids = identities if identities is not None else             character_identity.build_identities(state)
        got, reason = character_identity.same_name_descriptors(
            ids, name, same_names[name])
        if got is None:
            return None, {"factId": fid,
                          "reason": reason or "same-name-indistinguishable",
                          "detail": f"{name}: {reason}"}
        field = (ids.get("sameNameField") or {}).get(name) or             (ids.get("entries", {}).get(eid) or {}).get("field") or "性格"
        person = f"{name}（{field}={got[eid]}）"
    lines = [head]
    if kind in PERSON_LINE:
        lines.append(f"人物：{person}")
    if kind == "moved":
        lines += [f"起点：{fact['from']}", f"终点：{fact['to']}"]
    elif kind == "outcome":
        result = fact.get("resultText")
        if not result or not str(result).strip():
            return None, {"factId": fid, "reason": "missing-field",
                          "detail": "outcome needs resultText"}
        lines.append(f"结果：{result}")
    elif kind == "subtask_added":
        lines.append(f"新任务：{fact.get('goal')}")
        if fact.get("parentGoal"):
            lines.append(f"属于：{fact['parentGoal']}")
    elif kind == "task_achieved":
        lines.append(f"任务：{fact.get('goal')}")
    elif kind == "sanity_changed":
        direction = "上升" if fact.get("to", 0) > fact.get("from", 0) else "下降"
        lines.append(f"变化：{direction}")
    elif kind == "appearance_changed":
        lines.append(f"外貌：{fact.get('text')}")
    elif kind == "appearance_removed":
        lines.append(f"外貌消失：{fact.get('text')}")
    elif kind == "personality_changed":
        lines.append(f"行为倾向：{fact.get('text')}")
    elif kind == "personality_removed":
        lines.append(f"行为倾向消失：{fact.get('text')}")
    elif kind == "position_relative":
        lines.append(f"相对位置：{fact.get('targetName')}的"
                     f"{ {'under': '下方', 'above': '上方', 'beside': '旁边', 'in_front_of': '前方', 'behind': '后方'}.get(fact.get('relation'), fact.get('relation')) }")
    elif kind == "slot_changed":
        lines.append(f"所在格位：{fact.get('at')}的{fact.get('slotLabel')}")
    else:
        lines.append(_fact_payload(fact, None))
    if eid:
        seen_eids.append(eid)
    return lines, None


def _header(case, plan, world, facts, selected_fact_ids):
    by_id = _validate_plan(plan, facts, selected_fact_ids)
    ss, path, appearance, characters, visible = _validate_scene(case, world)
    path_names = [_loc_name(world, lid) for lid in path]
    appearance_parts = [appearance]
    for key in ("weather", "time", "wind", "light", "atmosphere"):
        value = ss.get(key)
        if value:
            appearance_parts.append(value)
    lines = ["叙事任务。", "场景：",
             f"地点={'>'.join(path_names)}",
             f"地点外貌={'；'.join(appearance_parts)}"]
    siblings = [v["name"] for lid, v in (world.get("locations") or {}).items()
                if lid not in path and (world.get("parents") or {}).get(lid)
                and (world.get("parents") or {}).get(lid) ==
                (world.get("parents") or {}).get(path[-1])]
    if siblings:
        lines.append(f"同栋={'、'.join(siblings)}")
    lines.append("人物：")
    for name, personality, char_appearance, inv in characters:
        lines.append(f"{name}｜性格={personality}｜外貌={char_appearance}"
                     f"｜随身={inv}")
    lines.append("可见：")
    if visible:
        for name, item_appearance in visible:
            lines.append(f"{name}={item_appearance}")
    else:
        lines.append("无")
    lines.append("")
    return lines, by_id


def pack_grouped_input(case, plan, world, selected_fact_ids=None,
                       scene_diagnostics=None, state=None,
                       requirement_line=None):
    out = {"version": VERSION,
           "diagnostics": list(scene_diagnostics or []),
           "productQualified": False, "blocked": []}
    try:
        facts = case.get("facts") or []
        header, by_id = _header(case, plan, world, facts,
                                selected_fact_ids)
        if state is None:
            state = case.get("state") or {}
        included = {fid for s in plan["sentences"] for fid in s["factIds"]}
        selected = [f for f in facts if f.get("factId") in included]
        same_names = _same_name_entities(selected)
        identities = character_identity.build_identities(state)
        pov = _pov_name(case, world, strict=True)
        plan_ids = {fid for s in plan["sentences"] for fid in s["factIds"]}
        extra_time = _selected_time_facts(facts, plan_ids)
        has_group_time = any(s.get("time") for s in plan["sentences"])

        lines = list(header)
        # global invariants: identical to the v3 packer, so the A/B arms only
        # differ in the fact arrangement below
        lines.append(f"视角：{pov}；第三人称限知；只写{pov}的内心，"
                     f"他人只写可见动作。")
        lines.append(requirement_line or registered_requirement_line())
        lines.append("")
        for sentence in plan["sentences"]:
            idx = sentence["index"] + 1
            suffix = "｜组后时间=过去了一会儿" if sentence.get("time") else ""
            lines.append(f"句组 G{idx}{suffix}")
            lines.append(f"叙述视角：{pov}，第三人称限知")
            for fid in sentence["factIds"]:
                fact = next((f for f in facts if f["factId"] == fid), None)
                if fact is None:
                    raise N4RenderError("plan-unknown-fact", fid)
                block, blocked = _block(fact, state, same_names, [],
                                        identities)
                if blocked:
                    out["blocked"].append(blocked)
                    lines.append(f"{fid}｜阻断：{blocked['reason']}")
                    continue
                lines.extend(block)
            lines.append("")
            lines.append(GROUP_RULES)
            lines.append("")
        if not has_group_time and extra_time:
            lines.append("全局时间=过去了一会儿")
            lines.append("")
        lines.append("正文：")

        out["input"] = "\n".join(lines)
        out["sameName"] = same_names
        out["status"] = "blocked" if out["blocked"] else "ok"
        out["productQualified"] = not out["blocked"]
    except N4RenderError as exc:
        out.update(status="error", code=exc.code, detail=exc.detail)
        return out
    return out

# N4.0 narrative input packing (program-only, deterministic).
#
# The N4 generation model reads STRUCTURED records, not pre-written fact
# sentences. This module is the program sub-step that packs:
#   scene context + N1 facts + N3 groups + perspective + constraints
# into a compact, byte-stable record text. It does not choose facts, group
# them, write prose, or call a model.
#
# Numbering: N4 = narrative generation (model); N4.0 = this input packer;
# N5 = verification. The legacy sentence-row renderer remains in renderer.py
# for the frozen v2/v3 models and byte regression, but it is not the new
# N4 input contract.

from .renderer import (  # noqa: F401
    N4RenderError,
    _find_location,
    _item_appearance,
    _item_name,
    _loc_appearance,
    _loc_name,
    _number,
    _pov_name,
    _text,
    _validate_plan,
)

N4_INPUT_VERSION = "n4-input-pack-v0.1"

# Every N1 fact kind this packer can express. Deliberately NOT
# renderer.SUPPORTED_KINDS: that set belongs to the frozen legacy sentence
# renderer (v2/v3 checkpoints) and must keep its byte behaviour. The
# narrative packer reads structured records, so it can carry the kinds the
# legacy renderer refuses (relative position, slot, subtask, removals).
PACK_KINDS = {
    "moved", "outcome", "sanity_changed", "appearance_changed",
    "appearance_removed", "personality_changed", "personality_removed",
    "position_relative", "slot_changed", "subtask_added",
    "task_achieved", "no_change", "time",
}

KIND_LABEL = {
    "moved": "移动",
    "outcome": "结果",
    "task_achieved": "任务达成",
    "subtask_added": "新任务",
    "sanity_changed": "理智",
    "appearance_changed": "外貌",
    "appearance_removed": "外貌消失",
    "personality_changed": "行为倾向",
    "personality_removed": "行为倾向消失",
    "position_relative": "相对位置",
    "slot_changed": "所在格位",
    "no_change": "无变化",
    "time": "时间",
}

RELATION_CN = {"under": "下方", "above": "上方", "beside": "旁边",
               "in_front_of": "前方", "behind": "后方"}


def _fact_payload(fact, pov_entity=None):
    kind = fact.get("kind")
    if kind not in PACK_KINDS:
        raise N4RenderError("unsupported-fact-kind", kind)
    if kind == "time":
        return "时间经过"
    if kind == "no_change":
        return "—"
    name = _text(fact, "name")
    if kind == "moved":
        # an item inside a character reads as "picked up", not as a walk
        if fact.get("heldBy"):
            return f"{name}｜被{fact['heldBy']}拿起"
        return f"{name}｜{_text(fact, 'from')}→{_text(fact, 'to')}"
    if kind == "outcome":
        return f"{name}｜{_text(fact, 'resultText', 'outcome-result-missing')}"
    if kind == "task_achieved":
        return f"{name}｜{_text(fact, 'goal')}"
    if kind == "subtask_added":
        return f"{name}｜{_text(fact, 'goal')}（属于：{_text(fact, 'parentGoal')}）"
    if kind == "sanity_changed":
        before = _number(fact, "from")
        after = _number(fact, "to")
        direction = "上升" if after > before else "下降" if after < before else "不变"
        return f"{name}｜{direction}"
    if kind in ("appearance_changed", "appearance_removed"):
        return f"{name}｜{_text(fact, 'text')}"
    if kind in ("personality_changed", "personality_removed"):
        # 他人的性情看不见，只能从行为上"觉出来"。标记成观察，免得模型
        # 直接把它当成已知的内心事实写出来。
        if pov_entity and fact.get("entityId") and fact["entityId"] != pov_entity:
            return f"{name}｜（从行为看）{_text(fact, 'text')}"
        return f"{name}｜{_text(fact, 'text')}"
    if kind == "position_relative":
        rel = RELATION_CN.get(fact.get("relation"), fact.get("relation"))
        target = _text(fact, "targetName")
        op = fact.get("op")
        if op == "removed":
            return f"{name}｜不再在{target}的{rel}"
        return f"{name}｜在{target}的{rel}"
    if kind == "slot_changed":
        label = _text(fact, "slotLabel")
        if fact.get("op") == "removed":
            return f"{name}｜离开{_text(fact, 'at')}的{label}"
        return f"{name}｜在{_text(fact, 'at')}的{label}"
    raise N4RenderError("unsupported-fact-kind", f"{kind}:{fact.get('factId')}")


def _validate_scene(case, world):
    ss = case.get("sceneState")
    if not isinstance(ss, dict):
        raise N4RenderError("scene-state-invalid", None)
    path = ss.get("locationPath")
    if not isinstance(path, list) or not path:
        raise N4RenderError("scene-location-path-missing", None)
    for lid in path:
        _loc_name(world, lid)
    deepest = path[-1]
    appearance = _loc_appearance(world, deepest)
    character_context = case.get("characterContext")
    if not isinstance(character_context, list):
        raise N4RenderError("scene-character-context-invalid", None)
    characters = []
    for cc in character_context:
        name = _text(cc, "name", "character-name-missing")
        personality = _text(cc, "personality", "character-personality-missing")
        char_appearance = _text(cc, "appearance", "character-appearance-missing")
        inventory = cc.get("inventory") or []
        if not isinstance(inventory, list):
            raise N4RenderError("character-inventory-invalid", cc.get("entityId"))
        inv = "、".join(_item_name(world, x) for x in inventory) or "无"
        characters.append((name, personality, char_appearance, inv))
    visible = []
    for iid in ss.get("visibleItems") or []:
        visible.append((_item_name(world, iid), _item_appearance(world, iid)))
    return ss, path, appearance, characters, visible


def _selected_time_facts(facts, plan_ids):
    return [f["factId"] for f in facts
            if f.get("kind") == "time" and f.get("factId") not in plan_ids]


def pack_narrative_input(case, plan, world, selected_fact_ids=None,
                         scene_diagnostics=None):
    """Formal N4.0 entry -> {status, input|code, diagnostics, version}.

    The output is structured record text: scene/person fields, fact records
    with ids and kind labels, N3 group membership, perspective and rules.
    It contains no pre-written fact sentences and no task goal.
    """
    out = {"version": N4_INPUT_VERSION,
           "diagnostics": list(scene_diagnostics or [])}
    try:
        facts = case.get("facts") or []
        by_id = _validate_plan(plan, facts, selected_fact_ids)
        ss, path, appearance, characters, visible = _validate_scene(case, world)

        path_names = [_loc_name(world, lid) for lid in path]
        # The scene conditions belong to the location appearance, not to a
        # separate environment layer: fold them into one 地点外貌 value.
        appearance_parts = [appearance]
        for key in ("weather", "time", "wind", "light", "atmosphere"):
            value = ss.get(key)
            if value:
                appearance_parts.append(value)
        lines = ["叙事任务。", "场景：",
                 f"地点={'>'.join(path_names)}",
                 f"地点外貌={'；'.join(appearance_parts)}"]

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

        pov_entity = (case.get("perspective") or {}).get("entityId")
        plan_ids = {fid for s in plan["sentences"] for fid in s["factIds"]}
        extra_time = _selected_time_facts(facts, plan_ids)
        included = plan_ids | set(extra_time)
        lines.append("事实：")
        for f in facts:
            fid = f.get("factId")
            if fid not in included:
                continue
            label = KIND_LABEL.get(f.get("kind"))
            if label is None:
                raise N4RenderError("unsupported-fact-kind", f.get("kind"))
            lines.append(f"{fid}｜{label}｜{_fact_payload(f, pov_entity)}")

        lines.append("分组：")
        has_group_time = False
        for s in plan["sentences"]:
            suffix = ""
            if s.get("time"):
                has_group_time = True
                suffix = "｜组后时间=过去了一会儿"
            lines.append(f"G{s['index'] + 1}｜{' '.join(s['factIds'])}{suffix}")
        if not has_group_time and any(
                f.get("kind") == "time" and f.get("factId") in included
                for f in facts):
            lines.append("全局时间=过去了一会儿")

        pov = _pov_name(case, world, strict=True)
        lines.append(f"视角：{pov}；第三人称限知；只写{pov}的内心，"
                     f"他人只写可见动作。")
        lines.append("要求：写场景、行动与视角人物心理；不写任务标题、"
                     "数值面板、具体时长、字段名；不新增未列出的具名人物/"
                     "物品/地点；他人只写可见动作。")
        if any(f.get("kind") in ("personality_changed", "personality_removed")
               and f.get("entityId") and f["entityId"] != case.get(
                   "perspective", {}).get("entityId")
               for f in facts if f.get("factId") in included):
            lines.append("他人的性情变化只能写成看得见的行为或说话方式，"
                         "或者视角人物心里的一句猜测；全篇最多点一次，不要反复提。")
        lines.append("正文：")
        out["input"] = "\n".join(lines)
    except N4RenderError as exc:
        out.update(status="error", code=exc.code, detail=exc.detail)
        return out
    out["status"] = "ok"
    return out

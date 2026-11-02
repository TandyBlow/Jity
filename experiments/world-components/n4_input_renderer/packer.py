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
    SUPPORTED_KINDS,
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

KIND_LABEL = {
    "moved": "移动",
    "outcome": "结果",
    "sanity_changed": "理智",
    "appearance_changed": "外貌",
    "personality_changed": "行为倾向",
    "no_change": "无变化",
    "time": "时间",
}


def _fact_payload(fact):
    kind = fact.get("kind")
    if kind not in SUPPORTED_KINDS:
        raise N4RenderError("unsupported-fact-kind", kind)
    if kind == "time":
        return "时间经过"
    if kind == "no_change":
        return "—"
    name = _text(fact, "name")
    if kind == "moved":
        return f"{name}｜{_text(fact, 'from')}→{_text(fact, 'to')}"
    if kind == "outcome":
        return f"{name}｜{_text(fact, 'resultText', 'outcome-result-missing')}"
    if kind == "sanity_changed":
        before = _number(fact, "from")
        after = _number(fact, "to")
        direction = "上升" if after > before else "下降" if after < before else "不变"
        return f"{name}｜{direction}"
    if kind == "appearance_changed":
        return f"{name}｜{_text(fact, 'text')}"
    if kind == "personality_changed":
        return f"{name}｜{_text(fact, 'text')}"
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
        lines = ["叙事任务。", "场景：",
                 f"地点={'>'.join(path_names)}",
                 f"地点外貌={appearance}"]
        for key, label in (("weather", "天气"), ("time", "时段"),
                           ("wind", "风"), ("light", "光"),
                           ("atmosphere", "氛围")):
            value = ss.get(key)
            if value:
                lines.append(f"{label}={value}")

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
            lines.append(f"{fid}｜{label}｜{_fact_payload(f)}")

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
        lines.append("正文：")
        out["input"] = "\n".join(lines)
    except N4RenderError as exc:
        out.update(status="error", code=exc.code, detail=exc.detail)
        return out
    out["status"] = "ok"
    return out

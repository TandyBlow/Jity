# N4 formal component: narrative input renderer (program-only, deterministic).
#
# New numbering (2026-11-02):
#   N1 fact extraction -> N2 selection -> N3 organization plan
#   -> N4 narrative input rendering (this module)
#   -> N5 narrative generation (old N4)
#   -> N6 verification (old N5)
#
# N4 owns the model-facing input contract. It does NOT choose facts, group
# facts, write prose, call a model, or touch state. It only turns the N1
# facts + N3 plan + N4.1 scene context into one byte-stable prompt for N5.
#
# Fail-closed rules:
#   - every plan factId must exist exactly once; duplicates/unknown ids fail;
#   - when selectedFactIds is supplied, the plan must cover exactly that set;
#   - every supported kind carries its required fields; unknown kinds fail
#     (no JSON dump fallback);
#   - `outcome` requires resultText; the task goal is never rendered;
#   - time amount/unit is never rendered, only "过去了一会儿";
#   - missing scene/character/world fields fail instead of printing None;
#   - environment fields that are absent are omitted (N4.1 records a
#     diagnostic); N4 never invents weather/light.

import json

N4_VERSION = "n4-input-renderer-v0.1"

SUPPORTED_KINDS = {
    "moved",
    "outcome",
    "sanity_changed",
    "appearance_changed",
    "personality_changed",
    "no_change",
    "time",
}

# The only time surface allowed into N5 input. Amount/unit stay internal.
TIME_LINE = "过去了一会儿（不写具体时长）"


class N4RenderError(ValueError):
    """Structured N4 failure. `code` is stable for tests/evidence."""

    def __init__(self, code, detail=None):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _text(mapping, key, code="missing-field"):
    value = mapping.get(key)
    if not isinstance(value, str) or value == "":
        raise N4RenderError(code, key)
    return value


def _number(mapping, key):
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N4RenderError("missing-field", key)
    return value


def _find_location(world, lid):
    locations = world.get("locations") or {}
    if lid in locations:
        return locations[lid]
    for loc in locations.values():
        for sub in loc.get("sublocations") or []:
            if sub.get("id") == lid:
                return sub
    return None


def _loc_name(world, lid):
    loc = _find_location(world, lid)
    if not isinstance(loc, dict) or not isinstance(loc.get("name"), str):
        raise N4RenderError("world-location-missing", lid)
    return loc["name"]


def _loc_appearance(world, lid):
    loc = _find_location(world, lid)
    if not isinstance(loc, dict):
        raise N4RenderError("world-location-missing", lid)
    appearance = loc.get("appearance")
    if not isinstance(appearance, str):
        raise N4RenderError("world-location-appearance-missing", lid)
    return appearance


def _item_name(world, iid):
    item = (world.get("items") or {}).get(iid)
    if not isinstance(item, dict) or not isinstance(item.get("name"), str):
        raise N4RenderError("world-item-missing", iid)
    return item["name"]


def _item_appearance(world, iid):
    item = (world.get("items") or {}).get(iid)
    if not isinstance(item, dict):
        raise N4RenderError("world-item-missing", iid)
    appearance = item.get("appearance")
    if not isinstance(appearance, str):
        raise N4RenderError("world-item-appearance-missing", iid)
    return appearance


def _char_name(world, eid):
    char = (world.get("characters") or {}).get(eid)
    if not isinstance(char, dict) or not isinstance(char.get("name"), str):
        raise N4RenderError("world-character-missing", eid)
    return char["name"]


def render_fact_line(fact):
    """One N1 fact -> one numbered line body. `time` -> None (rendered as
    the group/global time line instead). Every other kind fails closed."""
    kind = fact.get("kind")
    if kind not in SUPPORTED_KINDS:
        raise N4RenderError("unsupported-fact-kind", kind)
    if kind == "time":
        return None

    fact_id = fact.get("factId")
    if kind == "no_change":
        return "这一拍没有新的变化。"

    name = _text(fact, "name")
    if kind == "moved":
        return f"{name}从{_text(fact, 'from')}来到{_text(fact, 'to')}。"
    if kind == "outcome":
        # resultText is the only surface; the goal never enters N5 input.
        return f"{name}{_text(fact, 'resultText', 'outcome-result-missing')}。"
    if kind == "sanity_changed":
        before = _number(fact, "from")
        after = _number(fact, "to")
        if after > before:
            return f"{name}的呼吸比刚才顺了一些。"
        if after < before:
            return f"{name}的呼吸有些发紧。"
        return f"{name}的呼吸没有变化。"
    if kind == "appearance_changed":
        return f"{name}的{_text(fact, 'text')}。"
    if kind == "personality_changed":
        return f"{name}的行为倾向：{_text(fact, 'text')}。"
    raise N4RenderError("unsupported-fact-kind", f"{kind}:{fact_id}")


def _context_lines(case, world, strict=False):
    ss = case.get("sceneState") or {}
    if strict and not isinstance(ss, dict):
        raise N4RenderError("scene-state-invalid", None)
    path = ss.get("locationPath") or []
    if not isinstance(path, list) or not path:
        if strict:
            raise N4RenderError("scene-location-path-missing", None)
        path = []
    names = [_loc_name(world, x) for x in path]
    deepest = path[-1] if path else None
    appearance = _loc_appearance(world, deepest) if deepest else ""
    lines = ["叙事任务。"]
    scene = f"场景：{' → '.join(names)}。{appearance}。"
    if ss.get("weather"):
        scene += f"天气：{ss['weather']}。"
    if ss.get("time"):
        scene += f"时间：{ss['time']}。"
    lines.append(scene)

    character_context = case.get("characterContext") or []
    if strict and not isinstance(character_context, list):
        raise N4RenderError("scene-character-context-invalid", None)
    for cc in character_context:
        name = _text(cc, "name", "character-name-missing")
        personality = _text(cc, "personality", "character-personality-missing")
        char_appearance = _text(cc, "appearance", "character-appearance-missing")
        inventory = cc.get("inventory") or []
        if strict and not isinstance(inventory, list):
            raise N4RenderError("character-inventory-invalid", cc.get("entityId"))
        inv = "、".join(_item_name(world, x) for x in inventory) or "无"
        lines.append(f"{name}（性格：{personality}；"
                     f"外貌：{char_appearance}；随身：{inv}）")

    items = []
    for iid in ss.get("visibleItems") or []:
        items.append(f"{_item_name(world, iid)}（{_item_appearance(world, iid)}）")
    if items:
        lines.append("可见物：" + "；".join(items) + "。")
    return lines


def _pov_name(case, world, strict=False):
    eid = (case.get("perspective") or {}).get("entityId")
    if not eid and case.get("characterContext"):
        eid = case["characterContext"][0].get("entityId")
    if eid:
        return _char_name(world, eid)
    if strict:
        raise N4RenderError("perspective-unresolved", None)
    # Compatibility only (dev preview); the formal path is strict.
    return "沈砚"


def _tail_lines(pov):
    return [
        f"视角：{pov}（第三人称限知）；只写{pov}的内心，他人只写可见动作。",
        "要求：不要写任务标题、数值面板、具体时长、"
        "‘性格/外貌’字段名；不要新增未列出的具名人物/物品/地点。",
        "正文：",
    ]


def _validate_plan(plan, facts, selected_fact_ids):
    if not isinstance(plan, dict) or not isinstance(plan.get("sentences"), list):
        raise N4RenderError("plan-shape-invalid", None)
    if not isinstance(facts, list):
        raise N4RenderError("facts-shape-invalid", None)
    by_id = {}
    for f in facts:
        if not isinstance(f, dict):
            raise N4RenderError("facts-shape-invalid", f)
        fid = f.get("factId")
        if fid in by_id:
            raise N4RenderError("duplicate-fact", fid)
        by_id[fid] = f
    seen = []
    for sentence in plan["sentences"]:
        if not isinstance(sentence, dict) or not isinstance(sentence.get("factIds"), list):
            raise N4RenderError("plan-shape-invalid", sentence)
        if isinstance(sentence.get("index"), bool) or not isinstance(sentence.get("index"), int):
            raise N4RenderError("plan-shape-invalid", "index")
        for fid in sentence["factIds"]:
            if fid not in by_id:
                raise N4RenderError("plan-unknown-fact", fid)
            seen.append(fid)
    if len(seen) != len(set(seen)):
        raise N4RenderError("duplicate-fact", "plan")
    if selected_fact_ids is not None:
        for fid in selected_fact_ids:
            if fid not in by_id:
                raise N4RenderError("selected-unknown-fact", fid)
        # Time may stay out of the plan and be rendered by the global
        # fallback line, so coverage is checked on non-time facts.
        plan_non_time = {fid for fid in seen if by_id[fid]["kind"] != "time"}
        selected_non_time = {fid for fid in selected_fact_ids
                             if by_id[fid]["kind"] != "time"}
        if plan_non_time != selected_non_time:
            raise N4RenderError("plan-coverage-mismatch", {
                "plan": sorted(plan_non_time),
                "selected": sorted(selected_non_time),
            })
    return by_id


def render_plan_input(case, plan, world, strict=False, selected_fact_ids=None):
    """N4.2: N3 grouped plan -> the N5 input text.

    `strict=True` is the formal component path: fail closed on unknown ids,
    duplicates, incomplete context and unsupported kinds. `strict=False`
    keeps the dev-corpus preview behaviour byte-identical.
    """
    if not isinstance(plan, dict):
        raise N4RenderError("plan-shape-invalid", None)
    if "refusal" in plan:
        if strict:
            raise N4RenderError("plan-refusal", plan["refusal"])
        return "PLAN REFUSAL: " + json.dumps(
            plan["refusal"], ensure_ascii=False)
    if strict:
        by_id = _validate_plan(plan, case.get("facts") or [], selected_fact_ids)
    else:
        by_id = {f["factId"]: f for f in case.get("facts") or []}

    lines = _context_lines(case, world, strict=strict)
    lines.append("这一拍（按叙述分组）：")
    has_group_time = False
    for s in plan["sentences"]:
        lines.append(f"第 {s['index'] + 1} 组：")
        n = 0
        for fid in s["factIds"]:
            f = by_id[fid]
            if f["kind"] == "time":
                continue
            line = render_fact_line(f)
            if line:
                n += 1
                lines.append(f"{n}. {line}")
        if s.get("time"):
            has_group_time = True
            lines.append(f"这一组之后，{TIME_LINE}。")
    if not has_group_time and any(f["kind"] == "time"
                                  for f in (case.get("facts") or [])):
        lines.append(f"时间：{TIME_LINE}。")
    lines.extend(_tail_lines(_pov_name(case, world, strict=strict)))
    return "\n".join(lines)


def render_input(case, world, strict=False):
    """Flat dev-preview renderer (all facts, no N3 groups). Not the N5
    production contract; retained for the approved corpus preview."""
    lines = _context_lines(case, world, strict=strict)
    lines.append("这一拍：")
    n = 0
    has_time = False
    for f in case.get("facts") or []:
        if f["kind"] == "time":
            has_time = True
            continue
        line = render_fact_line(f)
        if line:
            n += 1
            lines.append(f"{n}. {line}")
    if has_time:
        lines.append(f"时间：{TIME_LINE}。")
    lines.extend(_tail_lines(_pov_name(case, world, strict=strict)))
    return "\n".join(lines)


def render_narrative_input(case, plan, world, selected_fact_ids=None,
                           scene_diagnostics=None):
    """Formal N4 entry -> {status, input|code, diagnostics, version}.

    `case` carries facts + sceneState + characterContext + perspective;
    `world` is the world view that resolves every referenced id.
    """
    out = {"version": N4_VERSION,
           "diagnostics": list(scene_diagnostics or [])}
    try:
        out["input"] = render_plan_input(
            case, plan, world, strict=True,
            selected_fact_ids=selected_fact_ids)
    except N4RenderError as exc:
        out.update(status="error", code=exc.code, detail=exc.detail)
        return out
    out["status"] = "ok"
    return out

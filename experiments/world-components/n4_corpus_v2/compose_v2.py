# Target composer for the N4 v2 grouped-interface corpus (commit 2).
#
# Deterministic, program-composed prose: per sentence group, one sentence
# per fact (plus the group's time sentence), with the subject rendered
# through the group's APPELLATION GRANT — a licensed pronoun when the plan
# grants one, the bare name otherwise (the safe fallback the task brief
# allows). Surface templates reuse the recognizer-proven patterns from the
# frozen flat corpus (rewrites.jsonl), so every target stays checkable by
# the same content-alignment machinery; the pronoun capability is added by
# SUBJECT SUBSTITUTION, not by new claim shapes.
#
# Same-name entities never share a group (the N3 rule); the composer never
# emits a qualified mention, so targets stay pattern-checkable.

from n4_render import num_cn, UNIT_CN  # noqa: E402  (same numeric vocabulary)

PRONOUN = {"male": "他", "female": "她", "unknown": "TA"}

_MOVED = ["{s}从{frm}来到了{to}。",
          "{s}离开了{frm}，抵达了{to}。",
          "{s}从{frm}进入了{to}。"]
_TASK = ["{s}完成了任务「{g}」。",
         "{s}办妥了任务「{g}」。",
         "{s}已达成任务「{g}」。"]
_SANITY_UP = ["{s}的精神值从{lo}升到了{hi}。", "{s}的精神值从{lo}涨到了{hi}。"]
_SANITY_DOWN = ["{s}的精神值从{lo}降到了{hi}。", "{s}的精神值从{lo}跌到了{hi}。"]
_PERSONALITY = ["{s}变得{text}。", "{s}的性子变了：{text}。"]
_APPEARANCE = ["{name}的外观变了：{text}。", "{name}的外貌变了：{text}。"]
_APPEARANCE_REM = ["{name}不再保有旧样貌「{text}」。"]
_PERSONALITY_REM = ["{name}不再保有旧性子「{text}」。"]
_POSITIONED = ["{s}已在{at}。", "{s}已经在{at}了。"]
_RELATIVE = ["{s}现在在{t}{r}。", "{s}如今在{t}{r}。"]
_RELATIVE_REM = ["{s}不再在{t}{r}。"]
_SLOT = ["{s}现在位于{at}的{slot}。"]
_SLOT_REM = ["{s}不再位于{at}的{slot}。"]
_SUBTASK = ["{s}接到了新任务「{g}」（隶属「{p}」）。", "{s}接到了新任务「{g}」，隶属「{p}」。"]
_TIME_LEAD = ["{t}过去了，"]
_TIME = ["前后大约{t}。", "整整{t}过去了。", "约{t}过去了。"]
_NO_CHANGE = ["一切如旧。", "平静如常。", "没有动静。"]

RELATION_CN = {"under": "下方", "above": "上方", "beside": "旁边",
               "in_front_of": "前方", "behind": "后方"}


def _pick(table, variant):
    return table[variant % len(table)]


def compose_group_sentences(group: dict, facts_by_id: dict,
                            variant: int, mentioned: set) -> list:
    """The group's fact sentences, in factIds order. The subject surface
    follows global discourse: the FIRST mention of an entity in the text
    is its name; later mentions use the group's granted pronoun (the
    antecedent discipline — a grant is a licence, the name is the
    fallback)."""
    out = []
    for fid in group["factIds"]:
        fact = facts_by_id[fid]
        kind = fact["kind"]
        if kind == "time":
            continue  # the group's time renders via compose_target's
            # group-level attribution, not as a fact sentence
        grant = next((g["pronoun"] for g in group.get("coreference") or []
                      if g.get("refersTo") == fact.get("entityId")), None)
        if grant and fact.get("entityId") in mentioned:
            s, used = grant, True
        else:
            s, used = fact.get("name") or "", False
        if fact.get("entityId"):
            mentioned.add(fact["entityId"])
        if kind == "moved":
            out.append(_pick(_MOVED, variant + len(out)).format(
                s=s, frm=fact["from"], to=fact["to"]))
        elif kind == "task_achieved":
            out.append(_pick(_TASK, variant + len(out)).format(s=s, g=fact["goal"]))
        elif kind == "sanity_changed":
            table = _SANITY_UP if fact["to"] > fact["from"] else _SANITY_DOWN
            out.append(_pick(table, variant + len(out)).format(
                s=s, lo=fact["from"], hi=fact["to"]))
        elif kind == "personality_changed":
            out.append(_pick(_PERSONALITY, variant + len(out)).format(
                s=s, text=fact["text"]))
        elif kind == "personality_removed":
            out.append(_pick(_PERSONALITY_REM, variant).format(
                name=fact["name"], text=fact["text"]))
        elif kind == "appearance_changed":
            out.append(_pick(_APPEARANCE, variant + len(out)).format(
                name=fact["name"], text=fact["text"]))
        elif kind == "appearance_removed":
            out.append(_pick(_APPEARANCE_REM, variant).format(
                name=fact["name"], text=fact["text"]))
        elif kind == "positioned_at":
            out.append(_pick(_POSITIONED, variant + len(out)).format(
                s=s, at=fact["at"]))
        elif kind == "position_relative":
            rel = RELATION_CN[fact["relation"]]
            if fact.get("op") == "removed":
                out.append(_pick(_RELATIVE_REM, variant).format(
                    s=s, t=fact["targetName"], r=rel))
            else:
                out.append(_pick(_RELATIVE, variant + len(out)).format(
                    s=s, t=fact["targetName"], r=rel))
        elif kind == "slot_changed":
            if fact.get("op") == "removed":
                out.append(_pick(_SLOT_REM, variant).format(
                    s=s, at=fact["at"], slot=fact["slotLabel"]))
            else:
                out.append(_pick(_SLOT, variant).format(
                    s=s, at=fact["at"], slot=fact["slotLabel"]))
        elif kind == "subtask_added":
            out.append(_pick(_SUBTASK, variant).format(
                s=s, g=fact["goal"], p=fact["parentGoal"]))
        elif kind == "no_change":
            out.append(_pick(_NO_CHANGE, variant + len(out)))
        else:
            raise ValueError(f"composer has no template for kind {kind}")
    return out


def compose_target(plan: dict, facts: list, variant: int = 0) -> str:
    """-> text. Per group: one sentence per fact, then the time sentence
    (or a leading-time prefix on the group's first sentence when the time
    fact leads that group). The eval recomputes this expected structure
    from the plan — the composer carries no side-channel metadata."""
    facts_by_id = {f["factId"]: f for f in facts}
    sentences = []
    mentioned = set()
    for group in plan["sentences"]:
        pieces = compose_group_sentences(group, facts_by_id, variant,
                                         mentioned)
        t = group.get("time")
        if t and t.get("amount") is not None:
            ts = num_cn(t["amount"]) + UNIT_CN.get(t["unit"], t["unit"])
            first_kind = (facts_by_id[group["factIds"][0]]["kind"]
                          if group["factIds"] else None)
            if first_kind == "time":
                # leading time: standalone sentence first, then the facts
                pieces.insert(0, _pick(_TIME, variant).format(t=ts))
            else:
                lead = _pick(_TIME_LEAD, variant).format(t=ts)
                pieces[0] = lead + pieces[0]
        sentences.extend(pieces)
    return "".join(sentences)

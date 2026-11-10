# -*- coding: utf-8 -*-
"""Read-only port of the narration fact rules used by the product checker.

The authoritative checker is TypeScript
(`frontend/src/lib/world-engine/runtime/narration-alignment.ts` plus the
narration-generation ledger/verify). This module mirrors the parts that decide
whether a *settled change* is expressed in prose, so the training data can be
audited and generated rows can be filtered **before** a candidate reaches the
browser. It never writes product state and is not part of runtime.

Rules ported: fact construction for moved / task_achieved /
personality_changed / sanity_changed / at / sanity; `binds`, `signature`,
`hasArrival`, `reversedArrival`, `scopeFor`; time duration matching; number
matching; the event-verb list; the hard-violation classes (wrong time,
direction reversed, actor swap, task claimed without fact, movement/stance
without fact, added event, wrong sanity number).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

CN_DIGITS = "零一二三四五六七八九"

MOVE_VERB = r"(?:走到|走向|来到|走进|进入|赶到|赶往|前往|抵达|走|跑|迈|移|去|到)"
STANCE = r"(?:在|位于|站在|待在|停在)"
FROM_MARK = r"(?:从|离开|自)"
COMPLETION = re.compile(r"(完成|达成|做完|搞定|结束|成功|办完|了结)")
CHANGE_VERB = re.compile(r"(变|升|降|掉|减|增|恢复|回落|涨)")
TERMINAL = re.compile(r"[\u3002\uff01\uff1f!?\u2026\u201d\u300d\u300f.~～)\uff09]$")
SENTENCE_SPLIT = re.compile(r"[。！？\n]+")
CLAUSE_SPLIT = re.compile(r"[，,；;]")

EVENT_VERBS = [
    "推开", "踢开", "踹开", "冲进", "冲出", "奔跑", "跑向", "攻击", "开枪", "拔出",
    "举起", "捡起", "拾起", "递给", "塞进", "敲门", "打开", "关上", "锁上", "躲到",
    "藏在", "翻过", "爬上", "跳下", "喊住", "大叫", "大喊", "呼喊", "点燃", "砸碎", "撕开",
]
PAST_MARKERS = ["小时候", "童年", "儿时", "当年", "十年前", "从前", "曾经", "很久以前", "那一年"]
PROMISE_VERBS = ["答应", "承诺", "保证", "发誓", "许诺", "约好", "说好"]

UNIT_WORDS = {
    "second": ["秒", "秒后"],
    "minute": ["分钟"],
    "hour": ["小时", "个钟头"],
    "day": ["天", "日"],
    "month": ["个月", "月"],
    "year": ["年"],
}
UNIT_CN = {"second": "秒", "minute": "分钟", "hour": "小时",
           "day": "天", "month": "个月", "year": "年"}


def cn_number(value: int) -> Optional[str]:
    if not isinstance(value, int) or value < 0 or value > 99:
        return None
    if value < 10:
        return CN_DIGITS[value]
    tens, ones = divmod(value, 10)
    return f"{'' if tens == 1 else CN_DIGITS[tens]}十{'' if ones == 0 else CN_DIGITS[ones]}"


def escape(value: str) -> str:
    return re.sub(r"([.*+?^${}()|\[\]\\])", r"\\\1", value)


def bare_of(text: str) -> str:
    return re.sub(r"「[^」]*」", "「」", text)


def mentions_number(sentence: str, value: int) -> bool:
    if re.search(rf"(?<![0-9]){value}(?![0-9])", sentence):
        return True
    reading = cn_number(value)
    if reading is not None and reading in sentence:
        return True
    return value == 2 and "两" in sentence


def ordinal_span(words: Sequence[str]) -> re.Pattern:
    body = "|".join(escape(word) for word in words)
    return re.compile(rf"第\s*[0-9零一二两三四五六七八九十百]{{1,3}}\s*(?:个)?\s*(?:{body})")


def durations_in(sentence: str, unit: str) -> List[int]:
    words = UNIT_WORDS[unit]
    scanned = ordinal_span(words).sub("§", sentence)
    found: Set[int] = set()
    for word in words:
        for match in re.finditer(rf"([0-9]+)\s*(?:个)?\s*{escape(word)}", scanned):
            found.add(int(match.group(1)))
        for value in range(1, 100):
            reading = cn_number(value)
            if reading and re.search(rf"{reading}\s*(?:个)?\s*{escape(word)}", scanned):
                found.add(value)
            for alias in (["两"] if value == 2 else []):
                if re.search(rf"{alias}\s*(?:个)?\s*{escape(word)}", scanned):
                    found.add(value)
    return sorted(found)


def mentions_time(sentence: str, amount: int, unit: str) -> bool:
    return amount in durations_in(sentence, unit)


def sentences(text: str) -> List[str]:
    return [part.strip() for part in SENTENCE_SPLIT.split(text) if part.strip()]


def has_arrival(sentence: str, origin: str, target: str) -> bool:
    forward = re.search(
        rf"{FROM_MARK}[^。！？]{{0,6}}{escape(origin)}[^。！？]{{0,14}}"
        rf"{MOVE_VERB}[^。！？]{{0,6}}{escape(target)}", sentence)
    reversed_ = re.search(
        rf"{FROM_MARK}[^。！？]{{0,6}}{escape(target)}[^。！？]{{0,14}}"
        rf"{MOVE_VERB}[^。！？]{{0,6}}{escape(origin)}", sentence)
    if forward:
        return True
    if reversed_:
        return False
    from_at = sentence.find(origin)
    to_at = sentence.find(target)
    if from_at >= 0 and to_at > from_at:
        between = sentence[from_at + len(origin):to_at]
        return re.search(MOVE_VERB, between) is not None
    return False


def reversed_arrival(sentence: str, origin: str, target: str) -> bool:
    return re.search(
        rf"{FROM_MARK}[^。！？]{{0,6}}{escape(target)}[^。！？]{{0,14}}"
        rf"{MOVE_VERB}[^。！？]{{0,6}}{escape(origin)}", sentence) is not None


def clauses_of(sentence: str) -> List[str]:
    return [part for part in CLAUSE_SPLIT.split(sentence) if part]


def _clause_start(clauses: List[str], name: str) -> int:
    for index, part in enumerate(clauses):
        if name in part:
            return index
    return -1


def _other_name(text: str, names: Iterable[str], exclude: str) -> Optional[str]:
    plain = bare_of(text)
    for name in names:
        if name != exclude and name in plain:
            return name
    return None


def _scopes(fact: Dict[str, Any], sentence: str, names: Sequence[str]) -> List[str]:
    clauses = clauses_of(sentence)
    start = _clause_start(clauses, fact["name"])
    scopes: List[str] = []
    if start >= 0:
        scope = clauses[start]
        scopes.append(scope)
        for index in range(start + 1, min(start + 3, len(clauses))):
            if _other_name(clauses[index], names, fact["name"]):
                break
            scope = scope + "，" + clauses[index]
            scopes.append(scope)
    else:
        scopes.append(sentence)
    return scopes


def _scope_for(fact: Dict[str, Any], sentence: str, names: Sequence[str]) -> str:
    clauses = clauses_of(sentence)
    start = _clause_start(clauses, fact["name"])
    if start < 0:
        return sentence
    scope = clauses[start]
    if fact["kind"] == "moved" and start + 1 < len(clauses):
        nxt = clauses[start + 1]
        if not _other_name(nxt, names, fact["name"]):
            scope = scope + "，" + nxt
    return scope


def _loose_phrase(text: str) -> re.Pattern:
    degree = "(?:十分|非常|特别|格外|相当|颇为|极为|极其|更加|越发|有些|很|挺)"
    return re.compile(degree.join(escape(ch) for ch in text))


def _binds_in(scope: str, fact: Dict[str, Any], named: bool, names: Sequence[str]) -> bool:
    kind = fact["kind"]
    if kind == "at":
        return named and fact["location"] in scope
    if kind == "moved":
        target = fact["to"]
        origin = fact["from"]
        if named and has_arrival(scope, origin, target):
            return True
        return (named and origin not in scope and target in scope
                and (re.search(MOVE_VERB, scope) is not None
                     or re.search(STANCE, scope) is not None))
    if kind == "sanity":
        return named and mentions_number(scope, fact["value"])
    if kind == "sanity_changed":
        return (named and CHANGE_VERB.search(scope) is not None
                and (mentions_number(scope, fact["from"]) or mentions_number(scope, fact["to"])))
    if kind == "task_achieved":
        return named and fact["goal"] in scope and COMPLETION.search(scope) is not None
    if kind == "personality_changed":
        return named and (fact["text"] in scope or _loose_phrase(fact["text"]).search(scope) is not None)
    return False


def binds(fact: Dict[str, Any], sentence: str, names: Sequence[str]) -> bool:
    named = fact["name"] in sentence
    if any(_binds_in(scope, fact, named, names) for scope in _scopes(fact, sentence, names)):
        return True
    if fact["kind"] == "moved" and named:
        clause = _scope_for(fact, sentence, names)
        return _binds_in(clause, fact, named, names)
    return False


def signature(fact: Dict[str, Any], sentence: str) -> bool:
    kind = fact["kind"]
    if kind == "at":
        return fact["location"] in sentence and re.search(MOVE_VERB, sentence) is None
    if kind == "moved":
        return has_arrival(sentence, fact["from"], fact["to"])
    if kind == "sanity":
        return mentions_number(sentence, fact["value"])
    if kind == "sanity_changed":
        return mentions_number(sentence, fact["from"]) and mentions_number(sentence, fact["to"])
    if kind == "task_achieved":
        return fact["goal"] in sentence
    if kind == "personality_changed":
        return fact["text"] in sentence
    return False


# ------------------------------------------------------------ fact building

def _position(state: Dict[str, Any], name: str) -> Optional[str]:
    person = (state.get("人物") or {}).get(name)
    if person:
        return person.get("位置")
    item = (state.get("物品") or {}).get(name)
    if item:
        return item.get("位置")
    place = (state.get("地点") or {}).get(name)
    if place:
        return place.get("位于")
    return None


def build_facts(x: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Approximate the runtime packet for a training row.

    Training rows predate the browser `entityDeltas` schema, so the mapping is
    explicit: delta 位置 → moved, 完成任务 → task_achieved, 新增个性 →
    personality_changed, 精神值 → sanity_changed. Characters that did not move
    get an optional `at`; every character gets an optional static `sanity`.
    """
    before = x.get("上回合状态") or {}
    delta = (x.get("本回合变化") or {}).get("变化") or {}
    people = before.get("人物") or {}
    facts: List[Dict[str, Any]] = []
    moved: Set[str] = set()
    for name, ops in delta.items():
        person = people.get(name)
        if not person:
            continue
        if "位置" in ops:
            origin = person.get("位置")
            if origin and origin != ops["位置"]:
                facts.append({"id": f"{name}:position", "kind": "moved", "name": name,
                              "from": origin, "to": ops["位置"]})
                moved.add(name)
        for goal in ops.get("完成任务") or []:
            facts.append({"id": f"{name}:task:{goal}", "kind": "task_achieved",
                          "name": name, "goal": goal})
        for text in ops.get("新增个性") or []:
            facts.append({"id": f"{name}:personality:{text}", "kind": "personality_changed",
                          "name": name, "text": text})
        if "精神值" in ops:
            facts.append({"id": f"{name}:sanity", "kind": "sanity_changed", "name": name,
                          "from": person.get("精神值"), "to": ops["精神值"]})
    for name, person in people.items():
        if name not in moved:
            facts.append({"id": f"{name}:position", "kind": "at", "name": name,
                          "location": person.get("位置")})
        if name not in delta or "精神值" not in (delta.get(name) or {}):
            facts.append({"id": f"{name}:sanity", "kind": "sanity", "name": name,
                          "value": person.get("精神值")})
    return facts


MANDATORY = {"moved", "task_achieved", "personality_changed", "sanity_changed"}


def parse_time(value: Any) -> Optional[Tuple[int, str]]:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*([0-9]+)\s*(秒|分钟|小时|天|个月|年)\s*", value)
    if not match:
        return None
    amount = int(match.group(1))
    unit = {"秒": "second", "分钟": "minute", "小时": "hour", "天": "day",
            "个月": "month", "年": "year"}[match.group(2)]
    return amount, unit


# ---------------------------------------------------------------- checking

def check_row(x: Dict[str, Any], text: str, allowed_verbs: Sequence[str] = (),
              past_context: str = "") -> Dict[str, Any]:
    """Grade one narration against a training row's settled facts.

    Returns the same shape that matters for data work: mandatory coverage,
    time coverage, and hard violations with their sentence.
    """
    facts = build_facts(x)
    names = [fact["name"] for fact in facts if fact["name"]]
    names = sorted(set(names), key=len, reverse=True)
    roster = [fact["name"] for fact in facts if fact["name"]]
    roster = sorted(set(roster), key=len, reverse=True)
    mandatory = [fact for fact in facts if fact["kind"] in MANDATORY]
    sentences_ = sentences(text)
    coverage = {fact["id"]: False for fact in facts}
    violations: List[Dict[str, str]] = []
    unverified: List[str] = []
    time = parse_time((x.get("本回合变化") or {}).get("时间推进"))
    time_expressed: Optional[bool] = False if time else None
    source_text = json_text(x) + "\n" + past_context
    licensed_past = [marker for marker in PAST_MARKERS if marker in source_text]
    licensed_promises = [verb for verb in PROMISE_VERBS if verb in source_text]

    for sentence in sentences_:
        if time and time_expressed is False and mentions_time(sentence, time[0], time[1]):
            time_expressed = True
        bound = [fact for fact in facts if binds(fact, sentence, roster)]
        for fact in bound:
            coverage[fact["id"]] = True

        if time:
            declared = []
            for unit in UNIT_WORDS:
                declared.extend((amount, unit) for amount in durations_in(sentence, unit))
            wrong = [(amount, unit) for amount, unit in declared
                     if unit != time[1] or amount != time[0]]
            if wrong:
                violations.append({"kind": "wrong_time", "sentence": sentence,
                                   "detail": f"{wrong[0][0]} {wrong[0][1]} vs {time[0]} {time[1]}"})
                continue

        clauses = clauses_of(sentence)
        weak = {"at"}
        swapped_out = False
        for fact in facts:
            if fact in bound and fact["kind"] in weak:
                continue
            swapped = None
            for clause in clauses:
                if not signature(fact, clause):
                    continue
                other = _other_name(clause, roster, fact["name"])
                if other:
                    swapped = other
                    break
            if swapped:
                violations.append({"kind": "actor_swap", "sentence": sentence,
                                   "detail": f"{fact['id']} attributed to {swapped}"})
                swapped_out = True
                break
        if swapped_out:
            continue

        for fact in facts:
            if fact["kind"] == "moved" and reversed_arrival(sentence, fact["from"], fact["to"]):
                violations.append({"kind": "direction_reversed", "sentence": sentence,
                                   "detail": f"{fact['name']}: {fact['from']}->{fact['to']}"})
        # Added events: event verbs with no committed fact behind them.
        if not bound:
            for verb in EVENT_VERBS:
                if verb in sentence and verb not in allowed_verbs:
                    if re.search(rf"(?:没有|没|未|不曾|并未|未曾|并不)\s*{escape(verb)}", sentence):
                        continue
                    violations.append({"kind": "added_event", "sentence": sentence,
                                       "detail": f"event verb {verb}"})
                    break
        # Task goals claimed without a fact.
        for fact in facts:
            if fact["kind"] != "task_achieved":
                continue
            if fact["goal"] in sentence and COMPLETION.search(sentence) and not binds(fact, sentence, roster):
                violations.append({"kind": "task_claimed_without_fact", "sentence": sentence,
                                   "detail": fact["goal"]})
        # Sanity numbers that contradict the fact while the name is present.
        for fact in facts:
            if fact["kind"] not in ("sanity", "sanity_changed") or fact["name"] not in sentence:
                continue
            if not re.search(r"(精神|理智|清醒|值|变|升|降|掉|减|增|恢复|回落|涨)", sentence):
                continue
            allowed = ([fact["value"]] if fact["kind"] == "sanity"
                       else [fact["from"], fact["to"]])
            numbers = value_positions(sentence)
            wrong = [value for value in numbers if value not in allowed]
            if wrong:
                violations.append({"kind": "wrong_number", "sentence": sentence,
                                   "detail": f"{fact['name']}: {wrong[0]} not in {allowed}"})
                break
        for verb in PROMISE_VERBS:
            if verb in sentence and verb not in licensed_promises:
                violations.append({"kind": "promise_without_fact", "sentence": sentence,
                                   "detail": f"promise verb {verb}"})
        for marker in PAST_MARKERS:
            if marker in sentence and marker not in licensed_past:
                violations.append({"kind": "past_without_fact", "sentence": sentence,
                                   "detail": f"past marker {marker}"})

    omitted = [fact for fact in mandatory if not coverage[fact["id"]]]
    return {
        "mandatory": len(mandatory),
        "covered": len(mandatory) - len(omitted),
        "omitted": [fact["id"] for fact in omitted],
        "time": None if not time else {"amount": time[0], "unit": time[1],
                                       "expressed": bool(time_expressed)},
        "violations": violations,
        "unverified": unverified,
        "ok": not omitted and not violations and (time_expressed is not False),
    }


def value_positions(sentence: str) -> List[int]:
    all_units = sorted({word for words in UNIT_WORDS.values() for word in words}, key=len, reverse=True)
    masked = ordinal_span(all_units).sub("§", sentence)
    masked = re.sub(
        rf"(?:[0-9]+|[零一二两三四五六七八九十]{{1,3}})\s*(?:个)?\s*(?:{'|'.join(escape(word) for word in all_units)})",
        "§", masked)
    found: Set[int] = set()
    for match in re.finditer(r"(?<![0-9])([0-9]+)(?![0-9])", masked):
        found.add(int(match.group(1)))
    for value in range(1, 100):
        reading = cn_number(value)
        for source in ([reading] if reading else []) + (["两"] if value == 2 else []):
            if re.search(rf"(?<![0-9]){source}(?![0-9])", masked) and _after_value_marker(masked, source):
                found.add(value)
    return sorted(found)


def _after_value_marker(text: str, token: str) -> bool:
    return re.search(rf"(?:从|到|为|是|至)\s*{escape(token)}", text) is not None


def json_text(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

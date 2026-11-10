# N5 v3: the adjudicated successor to the frozen v2 aligner.
#
# Decisions implemented here (owner rulings, 2026-11-08):
#   D1 = C  task completion is narrated from `outcome` + `resultText`; the
#           result text must come from the authoritative fact. A fact without
#           resultText BLOCKS the judgement (`outcome-result-missing`) and the
#           task goal is never used as a substitute.
#   D2 = A  a vague time expression may cover the time fact; if the text
#           states a DURATION VALUE it must match the authoritative time fact
#           numerically (value+unit), so a fabricated duration fails. The
#           reason is not "the model could not see the number" — a model can
#           invent one, and that invention is exactly what is checked.
#   D5      G4/G5 are DATA-triggered, not `rowId`-triggered. The judge does not
#           read the rowId at all, so renaming a case cannot change a verdict.
#   N6      this module only produces hard-gate results. Semantic review is a
#           separate layer: `quality()` returns pending/undetermined unless an
#           executed N6 result is supplied, and never "pass" by default.
#
# Frozen v2 stays untouched (`eval_n4_v2.judge_row`) and keeps producing the
# old archives. Existing fact frames are REUSED from that module so the new
# version cannot silently diverge on kinds it did not change.

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent.parent
for p in (str(WC), str(WC / "n4_corpus"), str(WC / "n4_corpus_v2")):
    if p not in sys.path:
        sys.path.insert(0, p)

from eval_n4_v2 import (  # noqa: E402
    CN_NUM,
    UNIT_EN,
    UNIT_RE,
    fact_patterns,
    grants_by_entity,
)
from corpus_check import cn_to_int, esc  # noqa: E402

VERSION = "n5-v3"

# Vague temporal expressions that may cover a time fact when no duration value
# is stated. Deliberately bounded: "很久很久" / "不知过了多久" carry no usable
# time claim and are NOT in the list; a text that omits time entirely does not
# cover the fact.
VAGUE_TIME = (
    "过了一会儿", "过了片刻", "过了不久", "过了半晌", "过了一会儿",
    "不一会儿", "没过多久", "不久之后", "片刻之后", "稍后", "随后",
    "一会儿", "片刻", "半晌", "一阵子", "一段时间", "过了一阵",
)

# Duration scanning must see the WHOLE numeric expression. The first version
# matched only a trailing numeral and therefore let "8.8分钟", "负八分钟" and
# "八分半钟" through (the reviewers' counter-examples). Now the scanner takes a
# sign, a decimal or Chinese numeral (or 半/几/数) and a unit, and any match it
# cannot convert to (value, unit) is an EXPLICIT duration that cannot be
# checked -> hard failure, never a fallback to the vague expression.
# Number grammar covers Arabic decimals, Chinese decimals (八点八) and Chinese
# numerals up to 千; the unit alternatives are longest-first so 分半钟 beats
# 分钟. A trailing 半 (八分钟半) is captured separately. Whatever the scanner
# matches must be the WHOLE expression: a match that is preceded or followed by
# more numeric material (点/半/零/digit/numeral) is a fragment and becomes
# unparseable instead of being read as its legal-looking prefix.
#
# The number is REQUIRED. A bare unit is ambiguous with ordinary words ("天色",
# "月色", "年度"), and treating it as a duration without a value rejected
# ordinary prose as unparseable. A bare unit is now simply not a duration
# mention; "几分钟" still matches (num=几) and stays unparseable.
CN_CHARS = "零一二两三四五六七八九十百千"
DURATION_RE = re.compile(
    r"(?P<neg>负|－|-|−)?\s*"
    r"(?P<num>\d+(?:\.\d+)?"
    r"|[零一二两三四五六七八九十百千]+点[零一二三四五六七八九]+"
    r"|[零一二两三四五六七八九十百千]+|半|几|数)\s*"
    r"(?P<unit>个半小时|个半月|个小时|个钟头|个月|分钟|分半钟|分半"
    r"|小时|钟头|秒钟|秒|天|日|年|月|时辰)"
    r"(?P<tailhalf>半)?")

CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNIT = {"十": 10, "百": 100, "千": 1000}


def _cn_number(text):
    """Chinese numeral -> int, or None. Covers 十/百/千 and 零 separators
    (一百零五). The frozen `corpus_check.cn_to_int` returns None above 99 and
    the first version then crashed on float(None); this parser replaces it for
    durations and never raises."""
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total, section, num, seen = 0, 0, 0, False
    for ch in text:
        if ch in CN_DIGIT:
            num = CN_DIGIT[ch]
            seen = True
        elif ch in CN_UNIT:
            unit = CN_UNIT[ch]
            section += (num or 1) * unit
            num = 0
            seen = True
        else:
            return None
    if not seen:
        return None
    return total + section + num


def _cn_decimal(text):
    """八点八 -> 8.8; 零点五 -> 0.5; None when not a clean decimal."""
    if "点" not in text:
        return None
    whole, frac = text.split("点", 1)
    if not whole or not frac:
        return None
    if any(ch not in CN_DIGIT for ch in frac):
        return None
    w = _cn_number(whole)
    if w is None:
        return None
    return w + int("".join(str(CN_DIGIT[ch]) for ch in frac)) / (10 ** len(frac))

UNIT_MAP = {"秒钟": "second", "秒": "second", "分钟": "minute",
            "分半钟": "minute", "分半": "minute", "小时": "hour",
            "个小时": "hour", "钟头": "hour", "个钟头": "hour",
            "个半小时": "hour", "天": "day", "日": "day",
            "个月": "month", "个半月": "month", "半月": "month",
            "月": "month", "年": "year"}

# Exact-length units can be compared across units (90 minutes == 1.5 hours).
# Months and years have no fixed length, so those are compared unit-for-unit.
SECONDS_PER = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def _same_duration(value, unit, amount, auth_unit) -> bool:
    if unit == auth_unit:
        return abs(float(value) - float(amount)) < 1e-9
    if unit in SECONDS_PER and auth_unit in SECONDS_PER:
        return abs(float(value) * SECONDS_PER[unit]
                   - float(amount) * SECONDS_PER[auth_unit]) < 1e-6
    return False
HALF_UNITS = {"分半钟", "分半", "个半小时", "个半月"}


def _parse_duration(num, unit_cn, neg, tail_half=False):
    """-> (value, unit) or None when the expression is an explicit duration we
    cannot convert exactly. None is a hard failure, not a vague pass. Never
    raises: any conversion problem is an unparseable duration."""
    try:
        if unit_cn == "时辰":   # archaic unit, no exact minute mapping
            return None
        unit = UNIT_MAP.get(unit_cn)
        if unit is None:
            return None
        extra = 0.5 if (unit_cn in HALF_UNITS or tail_half) else 0.0
        if num is None:
            return None
        if num == "半":
            value = 0.5
        elif num in ("几", "数"):
            return None
        elif re.fullmatch(r"\d+(?:\.\d+)?", num):
            value = float(num)
        elif _cn_decimal(num) is not None:
            value = float(_cn_decimal(num))
        elif re.fullmatch(rf"[{CN_CHARS}]+", num):
            whole = _cn_number(num)
            if whole is None:
                return None
            value = float(whole)
        else:
            return None
        value += extra
        if neg:
            value = -value
        return value, unit
    except Exception:            # conversion failure is a verdict, not a crash
        return None

BLOCKING_CODES = {"outcome-result-missing", "unsupported-kind"}


class JudgeBlocked(Exception):
    """The row cannot be judged at all: a mandatory authoritative field is
    missing. This is NOT a text failure and must never be turned into one."""

    def __init__(self, code, detail=None):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _outcome_patterns(fact, pronoun=None):
    name = esc(fact.get("name") or "")
    result = fact.get("resultText")
    if not isinstance(result, str) or not result.strip():
        raise JudgeBlocked("outcome-result-missing", fact.get("factId"))
    # The result appears with the acting subject in one sentence; the exact
    # result wording is required (it is the authoritative surface text), while
    # up to 8 characters of connective prose may sit between subject and text.
    subj = f"(?:{name}|{esc(pronoun)})" if pronoun else name
    return [rf"{subj}[^。]{{0,8}}?{esc(result.strip())}"]


def _patterns_for(fact, pronoun=None):
    """Frames for one fact. `pronoun` is the plan's appellation grant for the
    fact's entity (Regression: the first version always passed None and so
    rejected every legal 他/她 grant that v2 accepts)."""
    kind = fact.get("kind")
    if kind == "outcome":
        return _outcome_patterns(fact, pronoun)
    try:
        return fact_patterns(fact, pronoun)
    except ValueError:
        raise JudgeBlocked("unsupported-kind", kind)


NUMERIC_CONTEXT = set(CN_CHARS) | set("点0123456789")


def _is_fragment(text, start, end, other_starts):
    """A match that sits inside a larger numeric expression is not a duration:
    '八点八分钟' fragments must not be read as their legal-looking prefix.

    Two things are NOT fragments:
      - an empty boundary (start/end of text): the first version wrote
        `before in (CN_CHARS + "点...")`, and with before="" Python's substring
        rule made that True, so a text STARTING with a duration was rejected;
      - the start of the NEXT duration in a compound ("一小时六十分钟"): the
        following digit begins a new duration token, not a continuation. Only
        numeric material that does NOT start another duration nearby counts as
        a fragment."""
    before = text[start - 1] if start > 0 else None
    after = text[end] if end < len(text) else None
    if before is not None and before in NUMERIC_CONTEXT:
        return True
    if after is None:
        return False
    if after in NUMERIC_CONTEXT or after == "半":
        # allow a following duration token ("六十分钟" after "一小时")
        nearby = [s for s in other_starts if end <= s <= end + 2]
        return not nearby
    return False


def _duration_mentions(text):
    """-> (parsed, unparseable). `parsed` holds (value, unit) expressions we
    can compare; `unparseable` holds explicit duration claims we cannot
    convert OR fragments of a larger expression. Unparseable is a hard
    failure; it never falls back to a vague expression."""
    parsed, unparseable = [], []
    matches = list(DURATION_RE.finditer(text))
    other_starts = {m.start() for m in matches}
    for m in matches:
        raw = m.group(0)
        entry = {"raw": raw, "start": m.start(), "end": m.end()}
        if m.group("num") is None:
            # a bare unit ("分钟过去了") states a duration without a value
            unparseable.append(entry)
            continue
        if _is_fragment(text, m.start(), m.end(), other_starts - {m.start()}):
            unparseable.append(entry)
            continue
        got = _parse_duration(m.group("num"), m.group("unit"),
                              bool(m.group("neg")),
                              bool(m.group("tailhalf")))
        if got is None:
            unparseable.append(entry)
        else:
            entry["amount"], entry["unit"] = got
            parsed.append(entry)
    return parsed, unparseable


SENTENCE_END = "。！？!?；;" + chr(10)


def _sentence_index(text, pos):
    return sum(1 for ch in text[:pos] if ch in SENTENCE_END)


def _compound_groups(mentions, text):
    """Mentions that share a sentence form a compound duration
    ("一小时六十分钟"). The declared rule is that compounds are NOT summed, so
    they are rejected; per-component matching would otherwise accept a
    component that happens to equal the authoritative value while the total
    differs."""
    by_sentence = {}
    for m in mentions:
        by_sentence.setdefault(_sentence_index(text, m["start"]), []).append(m)
    return {k: v for k, v in by_sentence.items() if len(v) > 1}


def _time_gate(facts, must, text):
    """D2: a vague expression may cover the time fact ONLY when the text states
    no duration at all. Every stated duration is compared numerically with the
    authoritative time fact; an explicit duration that cannot be parsed is a
    hard failure, not a vague pass."""
    time_facts = [f for f in facts if f.get("kind") == "time"
                  and f.get("factId") in must]
    parsed, unparseable = _duration_mentions(text)
    authorized = {(f.get("amount"), f.get("unit")) for f in time_facts}
    info = {"triggered": bool(time_facts), "parsed": parsed,
            "unparseable": [u["raw"] for u in unparseable],
            "authorized": sorted(map(list, authorized))}
    problems = []
    compounds = _compound_groups(parsed + unparseable, text)
    if compounds:
        info["compound"] = [["".join(m["raw"] for m in group)]
                            for group in compounds.values()]
        for group in compounds.values():
            problems.append(
                "time-compound-unsupported:"
                + "+".join(m["raw"] for m in group)
                + " (compound durations are not summed)")
    if unparseable:
        # cannot check -> reject; never fall back to a vague expression
        problems.extend(f"time-value-unparseable:{u['raw']}"
                        for u in unparseable)
    if parsed and not compounds:
        if not time_facts:
            problems.extend(f"time-value-without-fact:{m['raw']}"
                            for m in parsed)
        else:
            for m in parsed:
                if not any(_same_duration(m["amount"], m["unit"], a, u)
                           for a, u in authorized):
                    problems.append(
                        f"time-value-mismatch:{m['raw']}="
                        f"{m['amount']}{m['unit']} not in "
                        f"{sorted(authorized)}")
    if not parsed and not unparseable and not compounds:
        vague_hit = next((v for v in VAGUE_TIME if v in text), None)
        info["vague"] = vague_hit
        if time_facts and vague_hit is None:
            problems.append(
                "uncovered:time (no vague expression and no value)")
    return not problems, problems, info


def _same_name_groups(facts):
    """display name -> distinct entity ids, only for character facts."""
    by_name = {}
    for f in facts:
        if f.get("entityGroup") != "characters":
            continue
        name, eid = f.get("name"), f.get("entityId")
        if name and eid:
            by_name.setdefault(name, set()).add(eid)
    return {n: ids for n, ids in by_name.items() if len(ids) >= 2}


def judge(facts, must_express, plan, text, finish_reason="eos"):
    """Hard gates only. Raises JudgeBlocked when the row cannot be judged.

    Returns {status: "judged"|"blocked", hardPass, gates, triggers, problems,
             covered, time, version}. Quality is NOT decided here.
    """
    must = list(must_express or [])
    facts_by_id = {f["factId"]: f for f in facts}
    missing = [m for m in must if m not in facts_by_id]
    if missing:
        raise JudgeBlocked("must-express-unknown", missing)

    # plan grants (entityId -> pronoun) are honoured in fact matching; G5 uses
    # the same map to reject grants on same-name entities
    grants = (grants_by_entity({"plan": plan, "facts": facts})
              if plan else {})

    # every must fact must be expressible by SOME frame, checked up front so a
    # missing authoritative field blocks instead of silently shrinking the row
    for fid in must:
        _patterns_for(facts_by_id[fid],
                      grants.get(facts_by_id[fid].get("entityId")))

    covered, problems, spans, claimed = [], [], [], []
    for fid in must:
        fact = facts_by_id[fid]
        if fact.get("kind") == "time":
            continue  # handled by G3
        patterns = _patterns_for(fact, grants.get(fact.get("entityId")))
        pool = []
        for pat in patterns:
            for m in re.finditer(pat, text):
                if any(m.start() < ce and m.end() > cs for cs, ce in claimed):
                    continue
                pool.append((m.start(), -(m.end() - m.start()), m))
        # NOTE (v3, D5): there is deliberately NO fallback to an already
        # claimed span. The frozen v2 aligner fell back to a repeated match so
        # that two identical-shape facts could both "match" one occurrence;
        # for two same-name actors that is exactly the conflation G4 exists to
        # catch, so v3 requires a second, unclaimed occurrence.
        if not pool:
            problems.append(f"uncovered:{fid}:{fact.get('kind')}")
            continue
        m = min(pool, key=lambda c: c[:2])[2]
        covered.append(fid)
        spans.append((m.start(), m.end()))
        claimed.append((m.start(), m.end()))

    # G1: every must fact except time must be covered
    must_non_time = [f for f in must if facts_by_id[f].get("kind") != "time"]
    g1 = all(f in covered for f in must_non_time)

    # G3: time coverage + value fidelity
    time_ok, time_problems, time_info = _time_gate(facts, must, text)
    problems.extend(time_problems)
    g3 = time_ok

    # G2: registered names and task goals must not survive outside matches
    masked = bytearray(b"\x00" * len(text))
    for s, e in spans:
        for i in range(s, e):
            masked[i] = 1
    residue = "".join(ch for i, ch in enumerate(text) if not masked[i])
    for f in facts:
        if f.get("entityGroup") == "characters" and f.get("name") \
                and f["name"] in residue:
            problems.append(f"residue-name:{f['name']}")
        if f.get("goal") and f["goal"] in residue:
            problems.append(f"residue-goal:{f['goal']}")
    g2 = not [p for p in problems
              if p.startswith("residue-")]

    # G4: data-triggered (>=2 distinct entities sharing a display name, both
    # must-express). Different names never trigger it.
    groups = _same_name_groups([facts_by_id[f] for f in must])
    g4_trigger = bool(groups)
    g4 = True
    if g4_trigger:
        for name, ids in groups.items():
            if text.count(name) < len(ids):
                g4 = False
                problems.append(
                    f"same-name-actors-not-all-named:{name} "
                    f"needs {len(ids)} mentions")

    # G5: data-triggered (a grant exists for an entity whose name is shared)
    same_name_entities = {eid for ids in groups.values() for eid in ids}
    g5_trigger = bool(set(grants) & same_name_entities)
    g5 = not g5_trigger
    if g5_trigger:
        problems.append(
            f"same-name-pronoun-grant:{sorted(set(grants) & same_name_entities)}")

    # G6: completed sentence + the generator did not stop on the length cap
    g6 = text.rstrip().endswith(("。", "！", "？")) \
        and finish_reason != "length"
    if not g6:
        problems.append("truncated-or-unfinished")

    gates = {"G1_alignment": g1, "G2_residue": g2, "G3_time": g3,
             "G6_no_truncation": g6}
    if g4_trigger:
        gates["G4_conflict_names"] = g4
    if g5_trigger:
        gates["G5_same_name_discipline"] = g5
    return {
        "version": VERSION,
        "status": "judged",
        "hardPass": all(gates.values()),
        "gates": gates,
        "triggers": {"G4": g4_trigger, "G5": g5_trigger},
        "problems": problems,
        "covered": sorted(covered),
        "residue": residue,
        "time": time_info,
    }


def quality(n6=None):
    """D3: N6 is a separate layer. Never 'pass' without an executed result."""
    if not isinstance(n6, dict):
        return "pending"
    status = n6.get("status")
    if status in (None, "not-run"):
        return "pending"
    if status == "executed":
        result = n6.get("result")
        if result in ("pass", "fail"):
            return result
        return "undetermined"
    return "undetermined"


def unregistered_names(annotations):
    """D4: human labels for a text. `count is None` means NOT CHECKED; a
    checked text with nothing found is 0. Never inferred, never guessed."""
    if annotations is None:
        return {"checked": False, "count": None, "items": []}
    items = []
    for a in annotations:
        if not isinstance(a, dict) or not a.get("snippet"):
            raise JudgeBlocked("annotation-shape-invalid", a)
        items.append({
            "snippet": a["snippet"],
            "position": a.get("position"),
            "source": a.get("source", "human"),
            "reviewStatus": a.get("reviewStatus", "pending-independent-review"),
            "isError": a.get("isError", True),
        })
    return {"checked": True, "count": len(items), "items": items}

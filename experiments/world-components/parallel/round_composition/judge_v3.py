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

DURATION_RE = (rf"(?P<num>{CN_NUM})\s*"
               rf"(?P<unit>秒钟|秒|分钟|小时|天|个月|年)")

BLOCKING_CODES = {"outcome-result-missing", "unsupported-kind"}


class JudgeBlocked(Exception):
    """The row cannot be judged at all: a mandatory authoritative field is
    missing. This is NOT a text failure and must never be turned into one."""

    def __init__(self, code, detail=None):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _outcome_patterns(fact):
    name = esc(fact.get("name") or "")
    result = fact.get("resultText")
    if not isinstance(result, str) or not result.strip():
        raise JudgeBlocked("outcome-result-missing", fact.get("factId"))
    # The result appears with the acting subject in one sentence; the exact
    # result wording is required (it is the authoritative surface text), while
    # up to 8 characters of connective prose may sit between subject and text.
    return [rf"{name}[^。]{{0,8}}?{esc(result.strip())}"]


def _patterns_for(fact):
    kind = fact.get("kind")
    if kind == "outcome":
        return _outcome_patterns(fact)
    try:
        return fact_patterns(fact, None)
    except ValueError:
        raise JudgeBlocked("unsupported-kind", kind)


def _duration_mentions(text):
    out = []
    for m in re.finditer(DURATION_RE, text):
        unit_cn = m.group("unit")
        unit = UNIT_EN.get(unit_cn if unit_cn != "秒钟" else "秒")
        out.append({"raw": m.group(0), "amount": cn_to_int(m.group("num")),
                    "unit": unit, "start": m.start(), "end": m.end()})
    return out


def _time_gate(facts, must, text):
    """D2: vague coverage allowed; any stated duration must match the
    authoritative time fact numerically."""
    time_facts = [f for f in facts if f.get("kind") == "time"
                  and f.get("factId") in must]
    if not time_facts:
        # a duration in a row with no time fact is an invented claim
        mentions = _duration_mentions(text)
        if mentions:
            return False, [f"time-value-without-fact:{m['raw']}"
                           for m in mentions], {"triggered": bool(mentions)}
        return True, [], {"triggered": False}
    authorized = {(f.get("amount"), f.get("unit")) for f in time_facts}
    mentions = _duration_mentions(text)
    vague_hit = next((v for v in VAGUE_TIME if v in text), None)
    problems = []
    if mentions:
        for m in mentions:
            if (m["amount"], m["unit"]) not in authorized:
                problems.append(
                    f"time-value-mismatch:{m['raw']} not in "
                    f"{sorted(authorized)}")
    elif vague_hit is None:
        problems.append("uncovered:time (no vague expression and no value)")
    return not problems, problems, {"triggered": True, "vague": vague_hit,
                                    "mentions": [m["raw"] for m in mentions],
                                    "authorized": sorted(map(list, authorized))}


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

    # every must fact must be expressible by SOME frame, checked up front so a
    # missing authoritative field blocks instead of silently shrinking the row
    for fid in must:
        _patterns_for(facts_by_id[fid])

    covered, problems, spans, claimed = [], [], [], []
    for fid in must:
        fact = facts_by_id[fid]
        if fact.get("kind") == "time":
            continue  # handled by G3
        patterns = _patterns_for(fact)
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
    grants = grants_by_entity({"plan": plan, "facts": facts}) if plan else {}
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

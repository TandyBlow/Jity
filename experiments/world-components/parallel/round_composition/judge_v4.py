"""N5 v4: the owner's 2026-11-09 rulings on the four gate defects.

What changed against the frozen v3 (v3 and its archives stay untouched):

G2  A registered character's name appearing again outside the matched fact
    span is a DIAGNOSTIC, not a rejection. `residue-goal` stays a hard check.
    Names that are not registered at all remain outside the hard gates by
    design: D4/N6 must look at them, so their absence from the registry can no
    longer hide an invented actor.

G1  Three outcomes instead of two: covered / rejected / needs-semantic-review.
    Explicit negation, irrealis ("差点", "如果"), rhetorical questions and
    quoted speech that carry the result text are REJECTED. Cases the program
    cannot decide (an observer verb in front of the subject, a result with no
    subject in its clause) are marked `needs-semantic-review`, which is NOT a
    pass. Only an unmarked clause with the subject bound to the result counts
    as covered.

G4  The name count is gone. Two same-name actors are separated only when each
    actor's own fact payload matches its own, disjoint text evidence. If the
    authoritative facts cannot tell the two apart (identical payloads), the
    result is `undetermined`, never a pass.

G6  `finish_reason` must be explicit. `stop`/`eos` = normal, `length` =
    truncated, `load` = not a success, a missing or unknown reason BLOCKS the
    judgement instead of defaulting to `eos`.

Everything else (time gate, fact frames for the unchanged kinds, plan grants,
JudgeBlocked codes) is imported from the frozen v3 so the new version cannot
silently diverge on what it did not change.

Usage:
    j = judge_v4.judge(facts, must, plan, text, finish_reason="stop")
    j["status"] in {"judged", "needs-semantic-review", "undetermined"}
    j["hardPass"] is True only for "judged" with every gate true.
"""

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent.parent
for p in (HERE, str(WC), str(WC / "n4_corpus"), str(WC / "n4_corpus_v2")):
    if p not in sys.path:
        sys.path.insert(0, p)

import judge_v3 as v3  # frozen; helpers only, its judge() is not called
from judge_v3 import JudgeBlocked, _patterns_for, _time_gate, _same_name_groups

VERSION = "n5-v4"

BOUNDARY = "。！？!?；;\n"

# Explicit negation. Multi-character cues only: a bare 不/没 would reject
# legitimate prose such as "不由自主地把铜铃挂回了钟楼".
NEGATION = ("并未", "并没有", "没有", "没能", "未能", "尚未", "未曾", "不曾",
            "不再", "无法", "难以", "差点", "几乎", "险些", "差一点", "未把",
            "没把", "并没有把", "并未能")
# Irrealis / conditional / hypothetical: the result is described but not done.
IRREALIS = ("如果", "假如", "假使", "要是", "若是", "万一", "一旦", "倘若",
            "即使", "哪怕", "就算", "若不是", "要是没有")
# Rhetorical questions that quote the result without asserting it.
RHETORICAL = ("难道", "岂", "何曾", "怎么可能", "怎么会", "哪有", "几时")
# Reported or quoted speech: the result appears inside someone's words.
QUOTE_MARKS = ("「", "」", "“", "”", "『", "』")
QUOTE_VERBS = ("说", "说道", "问", "问道", "喊", "喊道", "告诉", "转述",
               "听说", "据说", "声称", "念叨", "嘟囔")
# Attribution cannot be decided by the program: an observer is in front of the
# named subject, so the result belongs to someone else's report.
OBSERVER = ("看见", "看到", "看着", "听见", "听到", "望着", "盯着", "目送",
            "注意到", "发现")


def _clause_start(text, pos):
    cut = max(text.rfind(ch, 0, pos) for ch in BOUNDARY)
    return cut + 1


def _clause(text, pos):
    return text[_clause_start(text, pos):pos]


def classify_clause(text, subject_pos, match_end):
    """Inspect the clause that carries a fact match.

    Returns (verdict, code) with verdict in {"ok", "reject", "review"}.
    """
    clause = _clause(text, match_end)
    prefix = text[_clause_start(text, subject_pos):subject_pos]
    for cue in RHETORICAL:
        if cue in clause:
            return "reject", f"rhetorical:{cue}"
    if any(q in clause for q in QUOTE_MARKS):
        return "reject", "quoted-speech"
    for cue in QUOTE_VERBS:
        if cue in prefix:
            return "reject", f"reported-speech:{cue}"
    for cue in IRREALIS:
        if cue in clause:
            return "reject", f"irrealis:{cue}"
    for cue in NEGATION:
        if cue in clause:
            return "reject", f"negation:{cue}"
    for cue in OBSERVER:
        if cue in prefix:
            return "review", f"observer:{cue}"
    return "ok", None


def _outcome_status(fact, pronoun, text):
    """Locate the authoritative result text and say what its clause does."""
    result = fact.get("resultText")
    if not isinstance(result, str) or not result.strip():
        raise JudgeBlocked("outcome-result-missing", fact.get("factId"))
    result = result.strip()
    name = fact.get("name") or ""
    subjects = [s for s in (name, pronoun) if s]
    if not subjects:
        raise JudgeBlocked("outcome-subject-missing", fact.get("factId"))
    seen = []
    for m in re.finditer(re.escape(result), text):
        start = m.start()
        clause = text[_clause_start(text, start):m.end()]
        subj = next((s for s in subjects if s in clause), None)
        if subj is None:
            seen.append(("review", "result-without-subject"))
            continue
        subj_pos = _clause_start(text, start) + clause.find(subj)
        verdict, code = classify_clause(text, subj_pos, m.end())
        seen.append((verdict, code, (subj_pos, m.end())))
    return _pick(seen), seen


def _pick(seen):
    for verdict in ("ok", "reject", "review"):
        for item in seen:
            if item[0] == verdict:
                return verdict, (item[1] if len(item) > 1 else None), \
                    (item[2] if len(item) > 2 else None)
    return "missing", None, None


def _frame_status(fact, pronoun, text):
    """Same tri-state for the non-outcome kinds, using the frozen v3 frames."""
    pats = _patterns_for(fact, pronoun)
    seen = []
    for pat in pats:
        for m in re.finditer(pat, text):
            verdict, code = classify_clause(text, m.start(), m.end())
            seen.append((verdict, code, (m.start(), m.end())))
    return _pick(seen), seen


def _finish_gate(finish_reason):
    if finish_reason is None or finish_reason == "":
        raise JudgeBlocked("finish-reason-missing",
                           "the call cannot be classified as complete")
    if finish_reason not in ("stop", "eos", "length", "load"):
        raise JudgeBlocked("finish-reason-unknown", finish_reason)
    if finish_reason in ("length", "load"):
        return False, f"finish-{finish_reason}"
    return True, None


def _same_name_undetermined(facts, must, text):
    """Two actors share a display name: the program can only separate them when
    each actor carries its OWN identifying descriptor and that descriptor is in
    the text. Two mentions of the name are not evidence, and a distinct action
    payload does not say WHICH 管线乙 moved, so either case is `undetermined`.
    """
    group_facts = [f for f in facts if f["factId"] in must]
    groups = _same_name_groups(group_facts)
    for name, eids in groups.items():
        for eid in sorted(eids):
            own = [f for f in group_facts if f.get("entityId") == eid]
            descr = {f[k] for f in own
                     for k in ("text", "appearance", "role", "descriptor")
                     if isinstance(f.get(k), str) and f[k].strip()}
            if not descr or not any(d in text for d in descr):
                return name, sorted(eids)
    return None


def judge(facts, must_express, plan, text, finish_reason):
    must = list(must_express or [])
    facts_by_id = {f["factId"]: f for f in facts}
    missing = [m for m in must if m not in facts_by_id]
    if missing:
        raise JudgeBlocked("must-express-unknown", missing)

    grants = (v3.grants_by_entity({"plan": plan, "facts": facts})
              if plan else {})

    problems, statuses = [], {}
    claimed = []

    for fid in must:
        fact = facts_by_id[fid]
        pronoun = grants.get(fact.get("entityId"))
        if fact.get("kind") != "time":
            _patterns_for(fact, pronoun)  # blocks unsupported/missing fields
            if fact.get("kind") == "outcome":
                (verdict, code, span), seen = _outcome_status(fact, pronoun, text)
            else:
                (verdict, code, span), seen = _frame_status(fact, pronoun, text)
            if verdict == "ok" and span and \
                    any(span[0] < ce and span[1] > cs for cs, ce in claimed):
                # a second fact may not reuse another fact's evidence
                verdict, code = "review", "overlapping-evidence"
            statuses[fid] = {"status": verdict, "code": code,
                             "occurrences": len(seen)}
            if verdict == "ok":
                claimed.append(span)
                continue
            if verdict == "reject":
                problems.append(f"fact-rejected:{fid}:{code}")
            elif verdict == "review":
                problems.append(f"fact-needs-review:{fid}:{code}")
            else:
                problems.append(f"uncovered:{fid}:{fact.get('kind')}")
        else:
            statuses[fid] = {"status": "time", "code": None, "occurrences": None}

    time_ok, time_problems, time_info = _time_gate(facts, must, text)
    problems.extend(time_problems)

    # G2: names are diagnostics now; goals stay hard
    matched = claimed
    masked = bytearray(b"\x00" * len(text))
    for s, e in matched:
        for i in range(s, e):
            masked[i] = 1
    residue = "".join(ch for i, ch in enumerate(text) if not masked[i])
    name_hits = {}
    for f in facts:
        if f.get("entityGroup") == "characters" and f.get("name")                 and f["name"] in residue:
            name_hits[f["name"]] = name_hits.get(f["name"], 0) + 1
        if f.get("goal") and f["goal"] in residue:
            problems.append(f"residue-goal:{f['goal']}")
    goal_ok = not [p for p in problems if p.startswith("residue-goal")]

    # G4: identical payloads are undetermined; otherwise the per-fact disjoint
    # evidence already separates the actors (no count is used anywhere)
    undetermined = _same_name_undetermined(facts, must, text)
    groups = _same_name_groups([facts_by_id[f] for f in must])
    g4_trigger = bool(groups)
    if undetermined:
        g4 = "undetermined"
        problems.append(f"same-name-indistinguishable:{undetermined[0]} "
                        f"{undetermined[1]}")
    else:
        same_name_eids = {eid for ids in groups.values() for eid in ids}
        g4 = all(statuses.get(f["factId"], {}).get("status") == "ok"
                 for f in facts_by_id.values()
                 if f.get("entityId") in same_name_eids
                 and f["factId"] in must)

    g5_trigger = bool(set(grants) & {eid for ids in groups.values()
                                     for eid in ids})
    if g5_trigger:
        problems.append(
            f"same-name-pronoun-grant:{sorted(set(grants) & {eid for ids in groups.values() for eid in ids})}")

    g6, g6_code = _finish_gate(finish_reason)
    if not g6:
        problems.append(g6_code)
    if text and not text.rstrip().endswith(("。", "！", "？", "」", "”")):
        g6 = False
        problems.append("truncated-or-unfinished")

    rejected = [f for f, s in statuses.items() if s["status"] == "reject"]
    review = [f for f, s in statuses.items() if s["status"] == "review"]
    uncovered = [f for f, s in statuses.items() if s["status"] == "missing"]
    g1 = not rejected and not review and not uncovered

    gates = {"G1_alignment": g1, "G2_goal_residue": goal_ok,
             "G3_time": time_ok, "G6_completion": g6}
    if g4_trigger:
        gates["G4_conflict_names"] = g4
    if g5_trigger:
        gates["G5_same_name_discipline"] = False

    if undetermined:
        status = "undetermined"
        # the per-fact "overlap" review is the same finding as "indistinguishable"
        problems = [p for p in problems
                    if not p.startswith("fact-needs-review")]
    elif review:
        status = "needs-semantic-review"
    else:
        status = "judged"
    hard = status == "judged" and all(v is True for v in gates.values())
    return {
        "version": VERSION,
        "status": status,
        "hardPass": hard,
        "gates": gates,
        "triggers": {"G4": g4_trigger, "G5": g5_trigger},
        "problems": problems,
        "diagnostics": [{"code": "residue-name", "name": n, "count": c}
                        for n, c in name_hits.items()],
        "facts": statuses,
        "residue": residue,
        "time": time_info,
    }


def quality(n6=None):
    return v3.quality(n6)

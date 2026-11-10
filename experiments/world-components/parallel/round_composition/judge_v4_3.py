"""N5 v4.3: v4.2 plus separate reporting of confirmed failures and identity doubt.

Owner review 2026-11-09: when a passage is truncated AND the two same-name
actors cannot be told apart, the old code reported the whole row as
`undetermined`, which hides a confirmed error behind "cannot decide". v4.3:

- keeps the per-fact statuses (covered / reject / review / uncovered);
- collects `failureKinds` (finish-length, finish-load, uncovered/fact ids,
  fact-rejected codes);
- reports status `undetermined` ONLY when nothing else is confirmed wrong;
  when a confirmed failure exists the status is `judged` (or
  `needs-semantic-review`), the G4 gate stays "undetermined", and both kinds are
  listed separately so a report cannot count a confirmed error as a mere
  cannot-decide.

Everything else is v4.2:

The judge no longer reads descriptors from the fact objects when an identity
record is supplied: `judge(..., identities=...)` receives the same
`character_identity.build_identities(state)` object the N4 renderer reads, so the
two components cannot disagree about who is 急躁 and who is 沉默. Identical
descriptors are refused as evidence (`descriptors-identical`), not silently
accepted. Without an identity record the old fact fields are still honoured for
backwards compatibility; the pipeline always passes the record.

Everything else is v4.1:

Fixed here (v4 and its archive out/archive-rejudge-v4.json are kept unchanged):

A  Attribution when the named subject only WATCHES someone else act
   ("管线甲站在旁边，看着王五把铜铃挂回了钟楼"). v4 searched the whole sentence
   for the subject and only looked for an observer verb BEFORE it, so the
   observer was credited with the result. v4.1 requires the subject to sit in
   the same comma-delimited segment as the result; an observer verb plus another
   actor in between is a rejection (`attribution-other-actor`).

B  Same-name descriptors must MODIFY the right person. v4 checked that the
   descriptor appears somewhere in the text. v4.1 checks that each entity's own
   matched segment carries ITS descriptor and not the other entity's, so two
   passages with the names and descriptors swapped are `undetermined`.

C  Negation was searched in the whole sentence, so "他先没挂上，后来挂回去了"
   was falsely rejected. v4.1 scopes negation/irrealis to the clause segment
   that carries the match, while quoted speech is still checked on the whole
   sentence.

The rulings recorded in v4 (G2 diagnostics, G1 tri-state, G4 no counting, G6
strict finish) are unchanged.


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

import character_identity as _identity  # noqa: E402
import judge_v3 as v3  # frozen; helpers only, its judge() is not called
from judge_v3 import JudgeBlocked, _patterns_for, _time_gate, _same_name_groups

VERSION = "n5-v4.3"

BOUNDARY = "。！？!?；;\n"
SEGMENT = "。！？!?；;\n，,、：:"

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

# A result may follow the subject across a comma only when nothing but a plain
# connector sits in between ("他先没挂上，后来又挂回去了"). A segment holding a
# person-like token is not a connector, so the bind is refused and the fact goes
# to review instead of being credited.
CONNECTORS = {"", "后来", "又", "于是", "随后", "接着", "终于", "然后", "才",
              "便", "最后", "随即", "当即", "之后", "紧接着"}


def _clause_start(text, pos):
    cut = max(text.rfind(ch, 0, pos) for ch in BOUNDARY)
    return cut + 1


def _clause(text, pos):
    """Sentence-level text before `pos` (used for quotes and report verbs)."""
    return text[_clause_start(text, pos):pos]


def _segment_start(text, pos):
    cut = max(text.rfind(ch, 0, pos) for ch in SEGMENT)
    return cut + 1


def _segment(text, pos):
    """Comma-delimited segment before `pos` (used for negation/irrealis)."""
    return text[_segment_start(text, pos):pos]


def _segment_with(text, pos):
    """The whole comma-delimited segment around `pos`."""
    start = _segment_start(text, pos)
    end = len(text)
    for i in range(pos, len(text)):
        if text[i] in SEGMENT:
            end = i
            break
    return text[start:end]


def classify_clause(text, subject_pos, match_end):
    """Inspect the segment that carries a fact match.

    v4.1 scopes negation/irrealis to the comma-delimited segment (a failure
    earlier in the sentence no longer rejects a later success) while keeping
    quoted speech and report verbs at sentence level.

    Returns (verdict, code) with verdict in {"ok", "reject", "review"}.
    """
    segment = _segment(text, match_end)
    prefix = text[_segment_start(text, subject_pos):subject_pos]
    sentence = _clause(text, match_end)
    for cue in RHETORICAL:
        if cue in segment or cue in sentence:
            return "reject", f"rhetorical:{cue}"
    if any(q in sentence for q in QUOTE_MARKS):
        return "reject", "quoted-speech"
    for cue in QUOTE_VERBS:
        if cue in prefix:
            return "reject", f"reported-speech:{cue}"
    for cue in IRREALIS:
        if cue in segment:
            return "reject", f"irrealis:{cue}"
    for cue in NEGATION:
        if cue in segment:
            return "reject", f"negation:{cue}"
    for cue in OBSERVER:
        if cue in prefix:
            return "review", f"observer:{cue}"
    return "ok", None


def _observer_cue(text):
    for cue in OBSERVER:
        if cue in text:
            return cue
    return None


def _other_actor_before_result(text):
    """An observer verb followed by 'X把...' means someone else acted."""
    return bool(re.search(r"[^\s，,、。；;：:]{2,6}把", text))


def _outcome_status(fact, pronoun, text):
    """Locate the authoritative result text and say what its segment does.

    v4.1: the subject must sit in the SAME comma-delimited segment as the
    result. If it does not, an observer construction with another actor before
    the result is a rejection (the observer watched someone else do it); any
    other case is a review, never a pass.
    """
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
        result_pos, end = m.start(), m.end()
        seg_start = _segment_start(text, result_pos)
        seg = text[seg_start:result_pos]
        subj = next((x for x in subjects if x in seg), None)
        if subj is None:
            sent = text[_clause_start(text, result_pos):result_pos]
            if _observer_cue(sent) and                     _other_actor_before_result(sent + result[:1]):
                seen.append(("reject", "attribution-other-actor"))
                continue
            loose = next((x for x in subjects if x in sent), None)
            connector = seg.strip()
            if loose and connector in CONNECTORS:
                subj_pos = _clause_start(text, result_pos) + sent.find(loose)
                verdict, code = classify_clause(text, subj_pos, end)
                seen.append((verdict, code, (subj_pos, end)))
                continue
            seen.append(("review", "result-without-subject"))
            continue
        subj_pos = seg_start + seg.find(subj)
        after = text[subj_pos:end]
        if _observer_cue(after) and _other_actor_before_result(after):
            seen.append(("reject", "attribution-other-actor"))
            continue
        verdict, code = classify_clause(text, subj_pos, end)
        seen.append((verdict, code, (subj_pos, end)))
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


def _descriptors(facts):
    out = set()
    for f in facts:
        for k in ("text", "appearance", "role", "descriptor"):
            v = f.get(k)
            if isinstance(v, str) and v.strip():
                out.add(v.strip())
    return out


def _same_name_undetermined(facts, must, text, statuses, identities=None):
    """Two actors share a display name. v4 only asked whether a descriptor
    appeared anywhere. v4.1 requires each actor's OWN descriptor to sit next to
    that actor's own matched evidence, and the other actor's descriptor not to
    sit there, so swapped identities cannot pass.
    """
    group_facts = [f for f in facts if f["factId"] in must]
    groups = _same_name_groups(group_facts)
    for name, eids in groups.items():
        if identities is not None:
            got, reason = _identity.same_name_descriptors(
                identities, name, sorted(eids))
            if got is None:
                return name, sorted(eids), reason
            descr_by_eid = {eid: {got[eid]} for eid in eids}
        else:
            descr_by_eid = {eid: _descriptors([f for f in group_facts
                                               if f.get("entityId") == eid])
                            for eid in eids}
            if any(not d for d in descr_by_eid.values()):
                return name, sorted(eids), "descriptor-missing"
            values = [next(iter(d)) for d in descr_by_eid.values()]
            if len(set(values)) < len(values):
                return name, sorted(eids), "descriptors-identical"
        for eid in sorted(eids):
            own = [f for f in group_facts if f.get("entityId") == eid]
            descr = descr_by_eid[eid]
            others = set().union(*[d for o, d in descr_by_eid.items()
                                   if o != eid])
            for f in own:
                st = statuses.get(f["factId"]) or {}
                span = st.get("span")
                if not span:
                    # no evidence for this actor: the two identities cannot be
                    # shown apart, so the verdict is undetermined, not "pass"
                    return name, sorted(eids), "evidence-missing"
                ctx = text[max(0, span[0] - 8):span[1]]
                if not any(d in ctx for d in descr):
                    return name, sorted(eids), "descriptor-not-next-to-actor"
                if any(d in ctx for d in others):
                    return name, sorted(eids), "descriptor-swapped"
    return None


def judge(facts, must_express, plan, text, finish_reason, identities=None):
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
                             "occurrences": len(seen), "span": span}
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
    undetermined = _same_name_undetermined(facts, must, text, statuses,
                                           identities)
    groups = _same_name_groups([facts_by_id[f] for f in must])
    g4_trigger = bool(groups)
    if undetermined:
        g4 = "undetermined"
        reason = undetermined[2] if len(undetermined) > 2 else "indistinguishable"
        problems.append(f"same-name-{reason}:{undetermined[0]} "
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

    failure_kinds = []
    if not g6:
        failure_kinds.append(g6_code or "finish-unknown")
    failure_kinds += [f"uncovered:{f}" for f in uncovered]
    failure_kinds += [p.split(":", 2)[0] + ":" + p.split(":", 2)[1]
                      for p in problems if p.startswith("fact-rejected:")]
    if undetermined:
        failure_kinds.append("same-name-undetermined")
        # the per-fact "overlap" review is the same finding as "indistinguishable"
        problems = [p for p in problems
                    if not p.startswith("fact-needs-review")]
    confirmed = bool([k for k in failure_kinds
                      if not k.startswith("same-name-")])
    if undetermined and not confirmed:
        status = "undetermined"
    elif undetermined or review:
        # a confirmed error wins: the row is a failure, and the identity doubt
        # is reported next to it instead of replacing it
        status = "judged" if confirmed else "needs-semantic-review"
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
        "failureKinds": failure_kinds,
        "diagnostics": [{"code": "residue-name", "name": n, "count": c}
                        for n, c in name_hits.items()],
        "facts": statuses,
        "residue": residue,
        "time": time_info,
    }


def quality(n6=None):
    return v3.quality(n6)

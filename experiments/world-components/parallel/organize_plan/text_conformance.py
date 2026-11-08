# -*- coding: utf-8 -*-
"""Text-level plan conformance checker — v2.

v1 (runs/r1) answered only "are the facts there and are the groups separated".
Three read-only tamper probes showed it accepted clearly wrong text:

    T01  reverse every sentence            -> passed (only "different sentence" was checked)
    T02  add 随后 at an unauthorised spot   -> passed (only "a required edge exists somewhere")
    T03  append 并拿走了一把刀              -> passed (no check for content the plan never carried)

v2 adds three families of checks and splits every finding into two severities:

    hard   = the text cannot be a correct realisation of THIS plan; decided
             by position/structure alone (order, relation scope, connectors,
             fact coverage, refs, group layout). No human override.
    review = suspicious but not decidable mechanically (content that no
             selected fact carries). Every review item must get a human
             verdict before the item is accepted; "no automatic hard finding"
             is NOT acceptance.

New checks in v2
----------------
ORDER (T01, T04)
  * group-out-of-order      : groups must appear in plan order in the text
                              (sentence index of group i < group i+1)
  * within-group-order      : inside one group, the facts must appear in
                              plan order (character offset must increase)

RELATION SCOPE (T02, T05)
  * sequence-wording-outside-scope : a connector word ("随后") sits in a
                              sentence that is NOT a required-edge target group
  * sequence-wording-after-fact    : the connector appears after the target
                              fact inside its sentence
  * sequence-wording-excess        : more connector occurrences than required edges
  * sequence-wording-missing       : a required edge has no connector (v1 code kept)

ADDED CONTENT (T03)
  * added-content-outside-scope : after removing names, fact texts, licensed
                              connectors, punctuation and function characters,
                              a residual content character appears nowhere in
                              the selected facts, the entity names, or the
                              scene's visible list -> the text asserts
                              something the plan never carried
  * added-content-in-visible-scope : residual content is covered by the scene
                              visible list only -> cannot decide automatically;
                              queued for manual review (e.g. "打开了潮汐簿")
  * added-sentence          : more sentences than groups (extra narration block)

The residual computation is deliberately mechanical and is documented in
`residual_content()` so a reviewer can recompute it by hand.

Usage:
    python -X utf8 text_conformance.py --texts runs/r1/reference-output.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CONTRACT_VERSION = "c3-text-conformance-v2"

# Connectors that claim something the plan may not carry.
SIMULTANEITY = ("同时", "与此同时")
CAUSALITY = ("因为", "所以", "因此", "导致", "于是")
SEQUENCE_LICENSED = "随后"          # only licensed on a required-edge target group
SEQUENCE_OTHER = ("然后", "接着", "之后", "之前")
PRONOUNS = ("他", "她")

# Function characters that carry no world content. Everything else that is not
# covered by a fact / name / visible item is treated as new content.
FUNCTION_CHARS = set(
    "的了着过把被在从到向与和及也又就都还只更再很并且而或如若则因所其之"
    "一个两三十将让使对为是有无未不没这那如此"
)

PUNCT = "，。、；：！？“”‘’（）《》…—,.;:!?\"'() \n\t"


def sent_split(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=[。！？])", text) if p.strip()]


def grams(s: str, n: int = 3) -> set[str]:
    s = re.sub(r"\s", "", s)
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))} or {s}


def recall(a: str, b: str) -> float:
    ga = grams(a)
    return len(ga & grams(b)) / len(ga) if ga else 0.0


def _sent_of_offset(sents: list[str], pos: int) -> int:
    acc = 0
    for i, s in enumerate(sents):
        acc += len(s)
        if pos < acc:
            return i
    return max(0, len(sents) - 1)


def fact_span(fact: dict, sents: list[str]) -> tuple[bool, int, float, int]:
    """-> (supported, sentenceIndex, score, charOffsetWithinSentence)."""
    kind = fact.get("kind")
    if kind in ("appearance_changed", "outcome", "personality_changed", "position_relative"):
        needle = fact.get("text", "")
        best, bi = 0.0, 0
        for i, s in enumerate(sents):
            r = recall(needle, s)
            if r > best:
                best, bi = r, i
        pos = sents[bi].find(needle) if bi < len(sents) else -1
        return best >= 0.5, bi, best, max(0, pos)
    if kind == "moved":
        joined = "".join(sents)
        i, j = joined.find(fact["from"]), joined.find(fact["to"])
        ok = i >= 0 and j > i
        pos = j if j >= 0 else 0
        si = _sent_of_offset(sents, pos)
        inner = pos - sum(len(s) for s in sents[:si])
        return ok, si, 1.0 if ok else 0.0, max(0, inner)
    if kind == "positioned_at":
        joined = "".join(sents)
        pos = joined.find(fact["at"])
        si = _sent_of_offset(sents, max(0, pos))
        inner = max(0, pos) - sum(len(s) for s in sents[:si])
        return pos >= 0, si, 1.0 if pos >= 0 else 0.0, max(0, inner)
    if kind == "task_achieved":
        best, bi = 0.0, 0
        for i, s in enumerate(sents):
            r = recall(fact.get("goal", ""), s)
            if r > best:
                best, bi = r, i
        needle = fact.get("goal", "")
        pos = sents[bi].find(needle) if bi < len(sents) else -1
        return best >= 0.5, bi, best, max(0, pos)
    raise ValueError(f"no conformance span for kind {kind!r}")


def licensed_vocabulary(facts: list[dict], visible: str | None) -> set[str]:
    chars: set[str] = set()
    for f in facts:
        for key in ("text", "name", "goal", "from", "to", "at"):
            value = f.get(key)
            if isinstance(value, str):
                chars.update(value)
    if visible:
        for item in re.split(r"[、,，]", visible):
            chars.update(item.strip())
    return chars


def residual_content(text: str, facts: list[dict], visible: str | None) -> list[dict]:
    """Remove everything the plan licenses, return the leftover content runs.

    Removed: punctuation, entity names, every selected fact text, the licensed
    connectors ("随后", "同时", ...), and FUNCTION_CHARS.
    Left over is split into maximal runs of non-function characters.
    """
    residue = text
    for f in facts:
        for key in ("text", "goal"):
            value = f.get(key)
            if isinstance(value, str) and value:
                residue = residue.replace(value, "")
        name = f.get("name")
        if isinstance(name, str) and name:
            residue = residue.replace(name, "")
    for word in (SEQUENCE_LICENSED,) + SIMULTANEITY + CAUSALITY + SEQUENCE_OTHER:
        residue = residue.replace(word, "")
    for ch in PUNCT:
        residue = residue.replace(ch, "")

    runs, current = [], []
    for ch in residue:
        if ch in FUNCTION_CHARS:
            if current:
                runs.append("".join(current))
                current = []
            continue
        current.append(ch)
    if current:
        runs.append("".join(current))

    vocab = licensed_vocabulary(facts, visible)
    out = []
    for run in runs:
        outside = [ch for ch in run if ch not in vocab]
        out.append({
            "run": run,
            "outsideVocabulary": "".join(outside),
            "scope": "outside" if outside else "visible-only",
        })
    return out


def check_text(
    facts: list[dict],
    authorized_edges: list[dict],
    plan: dict,
    text: str,
    *,
    context: dict | None = None,
) -> dict:
    """Validate one text against one plan.

    Returns {"ok", "hard", "warnings", "violations", "checks"}.
    `ok` is True only when there are no hard findings.
    """
    sentences = sent_split(text)
    violations: list[dict] = []

    def v(severity: str, code: str, detail: str, **extra) -> None:
        item = {"severity": severity, "code": code, "detail": detail}
        item.update(extra)
        violations.append(item)

    hard = lambda *a, **k: v("hard", *a, **k)      # noqa: E731

    # ---------------------------------------------------------------- facts
    info: dict[str, dict] = {}
    for f in facts:
        ok, si, score, inner = fact_span(f, sentences)
        info[f["factId"]] = {
            "supported": bool(ok),
            "sentenceIndex": int(si),
            "charOffset": int(inner),
            "score": round(float(score), 3),
            "sentence": sentences[si] if sentences else "",
        }
        if not ok:
            hard("fact-omitted", f"{f['factId']} is not recognisable in any sentence", factId=f["factId"])
        if f.get("text"):
            hits = [i for i, s in enumerate(sentences) if recall(f["text"], s) >= 0.5]
            if len(hits) > 1:
                hard("fact-repeated", f"{f['factId']} is recognisable in {len(hits)} sentences",
                     factId=f["factId"])

    groups = plan.get("groups", [])

    # ------------------------------------------------------- group layout
    merged = []
    for gi, g in enumerate(groups):
        if len(g.get("facts", [])) < 2:
            continue
        sids = [info[fid]["sentenceIndex"] for fid in g["facts"] if fid in info]
        same = len(set(sids)) == 1
        merged.append({"group": g["facts"], "sameSentence": same, "sentences": sids})
        if not same:
            hard("group-split", f"group {gi} {g['facts']} spans sentences {sids}", group=gi)
        # ORDER: inside a group the facts must keep plan order
        offsets = [info[fid]["charOffset"] for fid in g["facts"] if fid in info]
        if same and offsets != sorted(offsets):
            hard("within-group-order",
                 f"group {gi} facts {g['facts']} appear at offsets {offsets}, not plan order", group=gi)

    separated = []
    for gi in range(len(groups) - 1):
        a = groups[gi]["facts"][-1]
        b = groups[gi + 1]["facts"][0]
        different = info[a]["sentenceIndex"] != info[b]["sentenceIndex"]
        separated.append({"pair": [a, b], "differentSentence": different,
                          "sentences": [info[a]["sentenceIndex"], info[b]["sentenceIndex"]]})
        if not different:
            hard("groups-merged", f"groups {gi}/{gi + 1} share a sentence at {a}/{b}", pair=[a, b])

    # ORDER: groups must appear in plan order
    group_order = []
    for gi, g in enumerate(groups):
        first = g["facts"][0] if g.get("facts") else None
        if first in info:
            group_order.append((gi, info[first]["sentenceIndex"]))
    for (gi, si), (gj, sj) in zip(group_order, group_order[1:]):
        if si >= sj:
            hard("group-out-of-order",
                 f"group {gi} starts at sentence {si} but group {gj} starts at {sj}", groups=[gi, gj])

    if sentences and len(sentences) > len(groups):
        hard("added-sentence", f"{len(sentences)} sentences for {len(groups)} groups",
             sentences=len(sentences), groups=len(groups))
    elif sentences and len(sentences) < len(groups):
        hard("sentence-count-mismatch", f"{len(sentences)} sentences for {len(groups)} groups",
             sentences=len(sentences), groups=len(groups))

    # ---------------------------------------------------------------- refs
    refs = plan.get("refs", {})
    ref_rows = []
    seen_entities: set[str] = set()
    for g in groups:
        last_named = None
        for fid in g["facts"]:
            f = next(x for x in facts if x["factId"] == fid)
            ref = refs.get(fid)
            sent = info[fid]["sentence"]
            name = f.get("name")
            eid = f.get("entityId")
            ref_rows.append({"factId": fid, "ref": ref, "name": name, "sentence": sent})
            if ref == "name":
                if name and name not in sent:
                    hard("ref-name-missing", f"{fid} ref=name but {name!r} is absent from its sentence", factId=fid)
                last_named = eid
                seen_entities.add(eid)
            elif ref == "omit":
                if eid not in seen_entities:
                    hard("ref-first-mention-omit", f"{fid} omits a first mention", factId=fid)
                if not name or name not in sent:
                    hard("ref-missing-antecedent", f"{fid} ref=omit but its sentence has no {name!r}", factId=fid)
                pos = sent.find(f.get("text", ""))
                if pos > 0 and name and name in sent[max(0, pos - 4):pos]:
                    hard("ref-not-omitted", f"{fid} is still written with {name!r}", factId=fid)
                if last_named is not None and last_named != eid:
                    hard("ref-ambiguous-omit",
                         f"{fid} omits {eid} but the nearest named entity is {last_named}", factId=fid)

    # --------------------------------------------------------------- edges
    edge_rows = []
    required = [e for e in plan.get("edges", []) if e.get("mode") == "required"]
    required_targets = {e["to"] for e in required}
    licensed_sentences = {
        info[e["to"]]["sentenceIndex"] for e in required if e["to"] in info
    }
    for e in plan.get("edges", []):
        src, dst = e["from"], e["to"]
        different = info[src]["sentenceIndex"] != info[dst]["sentenceIndex"]
        target_sent = info[dst]["sentence"]
        has_wording = SEQUENCE_LICENSED in target_sent
        edge_rows.append({"edge": [src, dst], "mode": e.get("mode"), "differentSentence": different,
                          "targetHasWording": has_wording})
        if not different:
            hard("edge-endpoints-share-sentence", f"edge {src}->{dst} endpoints share a sentence",
                 edge=[src, dst])
        if e.get("mode") == "required" and not has_wording:
            hard("sequence-wording-missing",
                 f"required edge {src}->{dst} has no 随后 in its target sentence", edge=[src, dst])

    # RELATION SCOPE: every connector must sit in a required-edge target sentence
    for si, s in enumerate(sentences):
        if SEQUENCE_LICENSED in s:
            if not required_targets:
                hard("invented-sequence", "随后 appears but the plan carries no required edge")
            elif si not in licensed_sentences:
                hard("sequence-wording-outside-scope",
                     f"随后 is in sentence {si} but the required edge targets sentence(s) "
                     f"{sorted(licensed_sentences)}", sentenceIndex=si)
            else:
                # the connector must come before the target fact
                target_ids = [e["to"] for e in required if info.get(e["to"]) and info[e["to"]]["sentenceIndex"] == si]
                if target_ids:
                    tid = target_ids[0]
                    fact_text = next((x.get("text", "") for x in facts if x["factId"] == tid), "")
                    pos_word = s.find(SEQUENCE_LICENSED)
                    pos_fact = s.find(fact_text) if fact_text else -1
                    if pos_fact >= 0 and pos_word > pos_fact:
                        hard("sequence-wording-after-fact",
                             f"随后 is placed after the target fact {tid} inside its sentence", factId=tid)

    occurrences = text.count(SEQUENCE_LICENSED)
    if occurrences > len(required):
        hard("sequence-wording-excess",
             f"{occurrences} occurrence(s) of 随后 for {len(required)} required edge(s)")

    for word in SIMULTANEITY:
        if word in text:
            hard("invented-simultaneity", f"{word!r} claims simultaneity; parallel is expression-only")
    for word in CAUSALITY:
        if word in text:
            hard("invented-causality", f"{word!r} claims a causal link the plan does not carry")
    for word in SEQUENCE_OTHER:
        if word in text:
            hard("invented-sequence", f"{word!r} adds an unauthorised temporal order")
    for word in PRONOUNS:
        if word in text:
            hard("invented-pronoun", f"{word!r} is a pronoun; refs only license name/omit")

    # ------------------------------------------------------- added content
    residues = residual_content(text, facts, (context or {}).get("visible"))
    added_rows = []
    for r in residues:
        added_rows.append(r)
        if r["scope"] == "outside":
            v("review", "added-content-outside-vocabulary",
              f"content {r['run']!r} uses characters that appear in no selected fact, name or "
              f"visible item ({r['outsideVocabulary']!r})", run=r["run"],
              outsideVocabulary=r["outsideVocabulary"])
        else:
            v("review", "added-content-visible-only",
                 f"content {r['run']!r} only reuses scene-visible vocabulary; needs manual review",
                 run=r["run"])

    hard_rows = [x for x in violations if x["severity"] == "hard"]
    review_rows = [x for x in violations if x["severity"] == "review"]
    return {
        "contractVersion": CONTRACT_VERSION,
        "ok": not hard_rows,
        "accepted": (not hard_rows) and (not review_rows),
        "needsManualReview": bool(review_rows),
        "hard": hard_rows,
        "review": review_rows,
        "warnings": review_rows,
        "violations": violations,
        "checks": {
            "sentenceCount": len(sentences),
            "groupCount": len(groups),
            "facts": info,
            "merged": merged,
            "separated": separated,
            "groupOrder": group_order,
            "refs": ref_rows,
            "edges": edge_rows,
            "residual": added_rows,
            "factSupported": sum(1 for r in info.values() if r["supported"]),
            "factTotal": len(info),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--texts", required=True)
    ap.add_argument("--sources", default="freeze/sources.json")
    ap.add_argument("--plans", default="freeze/plans-v1.jsonl")
    ap.add_argument("--contexts", default="freeze/contexts.json")
    args = ap.parse_args()
    here = Path(__file__).resolve().parent
    sources = {s["sourceId"]: s for s in json.loads((here / args.sources).read_text(encoding="utf-8"))["sources"]}
    contexts = json.loads((here / args.contexts).read_text(encoding="utf-8"))["contexts"]
    plans = [json.loads(l) for l in (here / args.plans).read_text(encoding="utf-8").splitlines()]
    texts = [json.loads(l) for l in (here / args.texts).read_text(encoding="utf-8").splitlines()]
    by_key = {(t["sourceId"], t["planId"]): t for t in texts}
    for p in plans:
        t = by_key[(p["sourceId"], p["planId"])]
        src = sources[p["sourceId"]]
        facts = [f for f in src["facts"] if f["factId"] in p["factsUsed"]]
        r = check_text(facts, p["authorizedEdges"], p["plan"], t["text"],
                       context=contexts.get(p["sourceId"]))
        codes = [x["code"] for x in r["hard"]]
        print(p["sourceId"], p["planId"], "OK" if r["accepted"] else ("FAIL" if codes else "REVIEW"),
              codes[:5], [x["code"] for x in r["review"]][:3])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

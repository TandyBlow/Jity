# -*- coding: utf-8 -*-
"""Text-level plan conformance checker (independent of any model).

Question it answers: given (selected facts, authorization, plan, text), did the
text organise the facts the way the plan says? It is the second half of the
c3 split: plan legality is checked by plan_contract.py; this file checks
execution. It runs on the deterministic reference text now, and on a model
output in the pre-registered next round.

The sentence/fact alignment helpers are re-implemented from the previous
controllability checker (experiments/world-components/organize_wording/
train_ab.py: sent_split / grams / recall / fact_span, 3-gram recall >= 0.5) so
the numbers stay comparable. The plan-conformance rules here are stricter:
refs (name/omit), required-edge wording, group count, repetition and
unauthorised temporal/causal connectives are checked too.

Usage:
    python -X utf8 text_conformance.py --texts runs/r1/reference-output.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SIMULTANEITY = ("同时", "与此同时")
SEQUENCE = ("随后", "然后", "接着", "之后", "之前")
CAUSALITY = ("因为", "所以", "因此", "导致", "于是")
PRONOUNS = ("他", "她")


def sent_split(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=[。！？])", text) if p.strip()]


def grams(s: str, n: int = 3) -> set[str]:
    s = re.sub(r"\s", "", s)
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))} or {s}


def recall(a: str, b: str) -> float:
    ga = grams(a)
    return len(ga & grams(b)) / len(ga) if ga else 0.0


def fact_span(fact: dict, sents: list[str]) -> tuple[bool, int, float]:
    kind = fact.get("kind")
    if kind in ("appearance_changed", "outcome", "personality_changed", "position_relative"):
        needle = fact.get("text", "")
        best, bi = 0.0, 0
        for i, s in enumerate(sents):
            r = recall(needle, s)
            if r > best:
                best, bi = r, i
        return best >= 0.5, bi, best
    if kind == "moved":
        joined = "".join(sents)
        i, j = joined.find(fact["from"]), joined.find(fact["to"])
        ok = i >= 0 and j > i
        pos = j if j >= 0 else 0
        acc = 0
        for k, s in enumerate(sents):
            acc += len(s)
            if pos < acc:
                return ok, k, 1.0 if ok else 0.0
        return ok, max(0, len(sents) - 1), 1.0 if ok else 0.0
    if kind == "positioned_at":
        joined = "".join(sents)
        pos = joined.find(fact["at"])
        ok = pos >= 0
        acc = 0
        for k, s in enumerate(sents):
            acc += len(s)
            if pos < acc:
                return ok, k, 1.0 if ok else 0.0
        return ok, max(0, len(sents) - 1), 1.0 if ok else 0.0
    if kind == "task_achieved":
        best, bi = 0.0, 0
        for i, s in enumerate(sents):
            r = recall(fact.get("goal", ""), s)
            if r > best:
                best, bi = r, i
        return best >= 0.5, bi, best
    raise ValueError(f"no conformance span for kind {kind!r}")


def check_text(facts: list[dict], authorized_edges: list[dict], plan: dict, text: str) -> dict:
    sentences = sent_split(text)
    violations: list[dict] = []

    def v(code: str, detail: str, **extra) -> None:
        item = {"code": code, "detail": detail}
        item.update(extra)
        violations.append(item)

    info: dict[str, dict] = {}
    for f in facts:
        ok, si, score = fact_span(f, sentences)
        info[f["factId"]] = {
            "supported": bool(ok),
            "sentenceIndex": int(si),
            "score": round(float(score), 3),
            "sentence": sentences[si] if sentences else "",
        }
        if not ok:
            v("fact-omitted", f"{f['factId']} is not recognisable in any sentence", factId=f["factId"])
        hits = [i for i, s in enumerate(sentences) if recall(f.get("text", ""), s) >= 0.5] if f.get("text") else []
        if len(hits) > 1:
            v("fact-repeated", f"{f['factId']} is recognisable in {len(hits)} sentences", factId=f["factId"])

    groups = plan.get("groups", [])
    merged = []
    for gi, g in enumerate(groups):
        if len(g.get("facts", [])) < 2:
            continue
        sids = [info[fid]["sentenceIndex"] for fid in g["facts"] if fid in info]
        same = len(set(sids)) == 1
        merged.append({"group": g["facts"], "sameSentence": same, "sentences": sids})
        if not same:
            v("group-split", f"group {gi} {g['facts']} spans sentences {sids}", group=gi)

    separated = []
    for gi in range(len(groups) - 1):
        a = groups[gi]["facts"][-1]
        b = groups[gi + 1]["facts"][0]
        different = info[a]["sentenceIndex"] != info[b]["sentenceIndex"]
        separated.append({"pair": [a, b], "differentSentence": different,
                          "sentences": [info[a]["sentenceIndex"], info[b]["sentenceIndex"]]})
        if not different:
            v("groups-merged", f"groups {gi}/{gi + 1} share a sentence at {a}/{b}", pair=[a, b])

    if sentences and len(sentences) != len(groups):
        v("sentence-count-mismatch", f"{len(sentences)} sentences for {len(groups)} groups",
          sentences=len(sentences), groups=len(groups))

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
            row = {"factId": fid, "ref": ref, "name": name, "sentence": sent}
            if ref == "name":
                if name and name not in sent:
                    v("ref-name-missing", f"{fid} ref=name but {name!r} is absent from its sentence", factId=fid)
                last_named = eid
                seen_entities.add(eid)
            elif ref == "omit":
                if eid not in seen_entities:
                    v("ref-first-mention-omit", f"{fid} omits a first mention", factId=fid)
                if not name or name not in sent:
                    v("ref-missing-antecedent", f"{fid} ref=omit but its sentence has no {name!r}", factId=fid)
                pos = sent.find(f.get("text", ""))
                if pos > 0 and name and name in sent[max(0, pos - 4):pos]:
                    v("ref-not-omitted", f"{fid} is still written with {name!r}", factId=fid)
                if last_named is not None and last_named != eid:
                    v("ref-ambiguous-omit", f"{fid} omits {eid} but the nearest named entity is {last_named}", factId=fid)
            ref_rows.append(row)

    edge_rows = []
    required_targets = {e["to"] for e in plan.get("edges", []) if e.get("mode") == "required"}
    for e in plan.get("edges", []):
        src, dst = e["from"], e["to"]
        different = info[src]["sentenceIndex"] != info[dst]["sentenceIndex"]
        target_sent = info[dst]["sentence"]
        has_wording = "随后" in target_sent
        row = {"edge": [src, dst], "mode": e.get("mode"), "differentSentence": different,
               "targetHasWording": has_wording}
        edge_rows.append(row)
        if not different:
            v("edge-endpoints-share-sentence", f"edge {src}->{dst} endpoints share a sentence", edge=[src, dst])
        if e.get("mode") == "required" and not has_wording:
            v("edge-wording-missing", f"required edge {src}->{dst} has no 随后 in its target sentence", edge=[src, dst])
        if e.get("mode") == "optional" and "随后" in text and not has_wording:
            v("edge-wording-misplaced", f"optional edge {src}->{dst} wording is outside the target sentence", edge=[src, dst])

    for word in SIMULTANEITY:
        if word in text:
            v("invented-simultaneity", f"{word!r} claims simultaneity; parallel is expression-only")
    for word in CAUSALITY:
        if word in text:
            v("invented-causality", f"{word!r} claims a causal link that the plan does not carry")
    for word in SEQUENCE:
        if word not in text:
            continue
        if word == "随后":
            if not required_targets:
                v("invented-sequence", "'随后' appears but no authorized edge exists")
            continue
        v("invented-sequence", f"{word!r} adds an unauthorised temporal order")
    for word in PRONOUNS:
        if word in text:
            v("invented-pronoun", f"{word!r} is a pronoun; refs only license name/omit")

    return {
        "ok": not violations,
        "violations": violations,
        "checks": {
            "sentenceCount": len(sentences),
            "groupCount": len(groups),
            "facts": info,
            "merged": merged,
            "separated": separated,
            "refs": ref_rows,
            "edges": edge_rows,
            "factSupported": sum(1 for r in info.values() if r["supported"]),
            "factTotal": len(info),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--texts", required=True)
    ap.add_argument("--sources", default="freeze/sources.json")
    ap.add_argument("--plans", default="freeze/plans-v1.jsonl")
    args = ap.parse_args()
    here = Path(__file__).resolve().parent
    sources = {s["sourceId"]: s for s in json.loads((here / args.sources).read_text(encoding="utf-8"))["sources"]}
    plans = [json.loads(l) for l in (here / args.plans).read_text(encoding="utf-8").splitlines()]
    texts = [json.loads(l) for l in (here / args.texts).read_text(encoding="utf-8").splitlines()]
    by_key = {(t["sourceId"], t["planId"]): t for t in texts}
    for p in plans:
        t = by_key[(p["sourceId"], p["planId"])]
        src = sources[p["sourceId"]]
        facts = [f for f in src["facts"] if f["factId"] in p["factsUsed"]]
        r = check_text(facts, p["authorizedEdges"], p["plan"], t["text"])
        print(p["sourceId"], p["planId"], "OK" if r["ok"] else "FAIL",
              [x["code"] for x in r["violations"]][:5])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

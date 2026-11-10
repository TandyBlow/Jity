# -*- coding: utf-8 -*-
"""Deterministic plan-faithful composer — a CONTROL, not a product renderer.

It turns (facts, plan) into one Chinese paragraph using only the plan's
groups/refs/edges. Its purpose is to prove that a legal plan is sufficient to
determine a text and that the two plans of one source are distinguishable by
the text-level conformance checker. It is not the N4 model and its wording is
not a quality claim.

Rules (fixed before the run):
- one group -> one sentence; within a group facts are joined by "，";
- groups are joined by "。" and the paragraph ends with "。";
- ref=name writes the display name; ref=omit writes the fact text without it;
- a `required` edge prefixes its target group with "随后，";
- no other connective, no background, no new entity.

Usage:
    python -X utf8 reference_compose.py --plan-file freeze/plans-v1.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


class UnsupportedFact(Exception):
    pass


def fact_phrase(fact: dict, ref: str) -> str:
    kind = fact.get("kind")
    name = fact.get("name")
    text = fact.get("text", "")
    if kind == "appearance_changed":
        body = text
        if ref != "name" or not name:
            return body
        # A few frozen fact texts are verb phrases (被雨打湿半幅); a possessive
        # would be ungrammatical. Keep the reference text readable; wording
        # quality is not what this control measures.
        return f"{name}{body}" if body.startswith("被") else f"{name}的{body}"
    if kind == "outcome":
        if ref == "name" and name:
            return f"{name}{text}" if text.startswith(("把", "将", "用", "从", "向")) else f"{name}的{text}"
        return text
    if kind == "moved":
        return f"{name}从{fact['from']}走到{fact['to']}" if ref == "name" and name else f"从{fact['from']}走到{fact['to']}"
    if kind == "positioned_at":
        return f"{name}在{fact['at']}" if ref == "name" and name else f"在{fact['at']}"
    if kind == "task_achieved":
        return f"{name}完成了任务「{fact['goal']}」" if ref == "name" and name else f"完成了任务「{fact['goal']}」"
    if kind == "personality_changed":
        body = text if text.startswith("变得") else f"变得{text}"
        return f"{name}{body}" if ref == "name" and name else body
    if kind == "sanity_changed":
        return f"{name}的理智值从{fact['from']}变为{fact['to']}" if ref == "name" and name else f"理智值从{fact['from']}变为{fact['to']}"
    raise UnsupportedFact(f"kind {kind!r} has no reference phrase template")


def compose(facts: list[dict], plan: dict) -> str:
    by_id = {f["factId"]: f for f in facts}
    refs = plan.get("refs", {})
    required_targets = {
        e["to"] for e in plan.get("edges", [])
        if e.get("type") == "before" and e.get("mode") == "required"
    }
    sentences: list[str] = []
    for group in plan.get("groups", []):
        clauses = [fact_phrase(by_id[fid], refs[fid]) for fid in group["facts"]]
        sentence = "，".join(clauses)
        if any(fid in required_targets for fid in group["facts"]):
            sentence = "随后，" + sentence
        sentences.append(sentence)
    return "。".join(sentences) + "。"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-file", default="freeze/plans-v1.jsonl")
    ap.add_argument("--sources", default="freeze/sources.json")
    ap.add_argument("--out", default="-")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    sources = json.loads((here / args.sources).read_text(encoding="utf-8"))
    by_source = {s["sourceId"]: s for s in sources["sources"]}
    rows = []
    for line in (here / args.plan_file).read_text(encoding="utf-8").splitlines():
        p = json.loads(line)
        src = by_source[p["sourceId"]]
        facts = [f for f in src["facts"] if f["factId"] in p["factsUsed"]]
        text = compose(facts, p["plan"])
        rows.append({"sourceId": p["sourceId"], "planId": p["planId"], "shape": p["shape"], "text": text})
    out = json.dumps(rows, ensure_ascii=False, indent=1) + "\n"
    if args.out == "-":
        print(out)
    else:
        (here / args.out).write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

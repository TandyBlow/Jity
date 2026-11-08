#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic organizer for the split arm (per-fact sentences -> group text).

Rules (v1, frozen by sha256 in freeze-v1.json):
- Within a plan group, facts are joined in plan order with "，".
- If the next fact has the same entity as the previous one (entityId when both
  rows carry it, otherwise identical name), a leading occurrence of that name
  is removed from its sentence so the clause continues the same subject.
- Different entities keep their own leading name.
- Groups are joined with "。"; a group containing an edge target gets "随后，".
- No word is added other than punctuation and the "随后，" marker.
"""
import re


def clean(text):
    t = text.strip()
    t = re.sub(r"^随后，", "", t)
    t = t.rstrip("。").strip()
    return t


def _entity_key(fact):
    return fact.get("entityId") or fact.get("name") or ""


def join_group(facts, sentences):
    clauses = []
    prev = None
    for f in facts:
        t = clean(sentences[f["factId"]])
        if prev is not None and _entity_key(prev) == _entity_key(f):
            name = f.get("name") or ""
            if name and t.startswith(name):
                t = t[len(name):]
                if t.startswith("的"):
                    t = t[1:]
                t = t.lstrip("，,")
        clauses.append(t)
        prev = f
    return "，".join(clauses)


def organize(row, fact_sentences):
    """fact_sentences: factId -> generated sentence for every fact in the row."""
    facts = {f["factId"]: f for f in row["facts"]}
    groups = row["plan"]["groups"]
    edges = row["plan"].get("edges", [])
    parts = []
    for g in groups:
        text = join_group([facts[fid] for fid in g["facts"]], fact_sentences)
        if any(e["to"] in g["facts"] for e in edges):
            text = "随后，" + text
        parts.append(text)
    return "。".join(parts) + "。"


def group_span(row, sample_facts, fact_sentences):
    """Text of one plan group only (for sample-level audit)."""
    facts = {f["factId"]: f for f in row["facts"]}
    edges = row["plan"].get("edges", [])
    text = join_group([facts[fid] for fid in sample_facts], fact_sentences)
    if any(e["to"] in sample_facts for e in edges):
        text = "随后，" + text
    return text + "。"


if __name__ == "__main__":
    # Self-test with the frozen n4n-109 per-fact reference text (A-large-77).
    row = {
        "facts": [
            {"factId": "f1", "name": "沈砚", "entityId": "char_shen"},
            {"factId": "f2", "name": "沈砚", "entityId": "char_shen"},
        ],
        "plan": {"groups": [{"facts": ["f1", "f2"]}], "edges": []},
    }
    text = organize(row, {"f1": "沈砚从潮渡走到雾堤。", "f2": "沈砚开始愿意先开口。"})
    assert text == "沈砚从潮渡走到雾堤，开始愿意先开口。", text
    print("ok:", text)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit for batch 2 (freeze-b2-v1). Same rules as audit_v1, parameterized paths."""
import json
import re
import sys
from pathlib import Path

EX = Path(__file__).resolve().parent
SYM = ("心里", "脑子", "胸口", "发紧", "发沉", "松快", "清亮", "发慌", "清醒")


def sent_split(text):
    return [p.strip() for p in re.split(r"(?<=[。！？])", text) if p.strip()]


def grams(s, n=3):
    s = re.sub(r"\s", "", s)
    return {s[i:i+n] for i in range(max(0, len(s) - n + 1))} or {s}


def recall(a, b):
    ga, gb = grams(a), grams(b)
    return len(ga & gb) / len(ga) if ga else 0.0


def fact_span(f, sents):
    k = f["kind"]
    if k == "moved":
        text = "".join(sents)
        i, j = text.find(f["from"]), text.find(f["to"])
        ok = i >= 0 and j > i
        pos = j if j >= 0 else 0
    elif k == "no_change":
        text = "".join(sents)
        ok = any(x in text for x in ("没有", "没再", "没发生"))
        pos = text.find("没有")
    elif k == "sanity_changed":
        text = "".join(sents)
        ok = any(x in text for x in SYM) and not re.search(r"\d", text)
        pos = max([text.find(x) for x in SYM] + [0])
    else:
        best, bi = 0.0, -1
        for i, s in enumerate(sents):
            r = recall(f.get("text", ""), s)
            if r > best:
                best, bi = r, i
        return best >= 0.5, bi, best
    acc = 0
    for i, s in enumerate(sents):
        acc += len(s)
        if pos < acc:
            return ok, i, 1.0 if ok else 0.0
    return ok, max(0, len(sents) - 1), 1.0 if ok else 0.0


def clause_split(text):
    return [p.strip() for p in re.split(r"(?<=[。，；！？])", text) if p.strip()]


def best_fact(clause, facts):
    best, bid = 0.0, None
    for f in facts:
        target = f.get("text") or f"{f.get('from','')}{f.get('to','')}"
        r = recall(target, clause)
        if f["kind"] == "moved":
            r = max(r, 1.0 if f["from"] in clause and f["to"] in clause else r)
        if r > best:
            best, bid = r, f["factId"]
    return bid, round(best, 3)


def audit_text(row, fact_ids, text):
    facts = [f for f in row["facts"] if f["factId"] in fact_ids]
    sents = sent_split(text)
    info = {}
    for f in facts:
        ok, si, sc = fact_span(f, sents)
        info[f["factId"]] = {"support": bool(ok), "sentence": sents[si] if sents else "", "score": round(float(sc), 3)}
    clauses = []
    for c in clause_split(text):
        fid, sc = best_fact(c, facts)
        clauses.append({"clause": c, "best_fact": fid, "score": sc})
    names = [f.get("name") for f in facts if f.get("name")]
    repeated = 0
    for n in set(names):
        repeated += max(0, text.count(n) - 1)
    return {
        "text": text, "sentences": sents, "facts": info,
        "omissions": [k for k, v in info.items() if not v["support"]],
        "clauses": clauses, "weak_clauses": [c for c in clauses if c["score"] < 0.35],
        "sentence_count": len(sents), "repeated_names": repeated,
        "contains_digit": bool(re.search(r"\d", text)),
        "contains_pronoun": bool(re.search(r"[他她]", text)),
        "sanity_words": [w for w in SYM if w in text],
    }


def main():
    freeze_path = Path(sys.argv[1]) if len(sys.argv) > 1 else EX / "freeze-b2-v1.json"
    results_path = Path(sys.argv[2]) if len(sys.argv) > 2 else EX / "run-b2-v1/results.json"
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else EX / "audit-b2-v1.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    results = json.loads(results_path.read_text(encoding="utf-8"))
    out = {"source": str(results_path), "freeze": str(freeze_path),
           "determinism_ok": results.get("determinism_ok"), "samples": {},
           "row_checks": {}, "summary": {}}
    for sid, r in results["rows"].items():
        out["row_checks"][sid] = {"J_matches_recorded_784": r["J"]["matches_recorded_784"]}
    j_bad = s_bad = 0
    for s in freeze["samples"]:
        sid = s["sampleId"]
        got = results["samples"][sid]
        row = next(x for x in freeze["rows"] if x["sourceId"] == got["sourceId"])
        j = audit_text(row, s["groupFacts"], got["J_text"])
        sv = audit_text(row, s["groupFacts"], got["S_text"])
        j_bad += len(j["omissions"])
        s_bad += len(sv["omissions"])
        out["samples"][sid] = {"sourceId": s["sourceId"], "role": s["role"], "groupFacts": s["groupFacts"],
                               "J": j, "S": sv}
    out["summary"] = {"J_omissions": j_bad, "S_omissions": s_bad, "samples": len(freeze["samples"])}
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out["summary"], ensure_ascii=False))
    for sid, v in out["samples"].items():
        print(f"\n{sid} [{v['role']}] {v['sourceId']} {v['groupFacts']}")
        print("  J:", v["J"]["text"])
        print("     omissions", v["J"]["omissions"], "weak", [c["clause"] for c in v["J"]["weak_clauses"]])
        print("  S:", v["S"]["text"])
        print("     omissions", v["S"]["omissions"], "weak", [c["clause"] for c in v["S"]["weak_clauses"]])


if __name__ == "__main__":
    main()

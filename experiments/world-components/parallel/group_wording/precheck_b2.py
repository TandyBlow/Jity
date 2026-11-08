#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pre-flight checks for batch 2: freeze integrity, call coverage, archived J
reassembly, and that batch-1 files are untouched. No model calls."""
import hashlib
import json
import re
import sys
from pathlib import Path

EX = Path(__file__).resolve().parent
ROOT = EX.parents[3]
RUN784 = ROOT / "artifacts/world-components/organize-wording/sentence-base-784m-run-v1/results.json"
RUN77 = ROOT / "artifacts/world-components/organize-wording/sentence-scale-run-v1/results.json"
FREEZE_SHA = "34d7be711105a660aa2d4eab29e233f6efd143fe256dd2a6e64f13f74de50f02"
BATCH1_FREEZE_SHA = "0d8db13f0ca079174504d02fece57514b32672ee53bba3d0e3a9959a9e66f0ed"
BATCH1_RESULTS_SHA = "77d7128780c05110a66a994169fea37b6469269a50c33d20f61dbd823bb22aff"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def assemble(calls, outputs, edges):
    parts = []
    for call in calls:
        t = outputs[call["callId"]]["text"].strip()
        t = re.sub(r"^随后，", "", t).rstrip("。").strip()
        if any(e["to"] in call["factIds"] for e in edges):
            t = "随后，" + t
        parts.append(t)
    return "。".join(parts) + "。"


def group_text(row, outputs, group_facts):
    edges = row["plan"].get("edges", [])
    cs = [c for c in row["B_calls"] if set(c["factIds"]) <= set(group_facts)]
    assert cs, (row["sourceId"], group_facts)
    return assemble(cs, outputs, edges)


def main():
    assert sha(EX / "freeze-b2-v1.json") == FREEZE_SHA, sha(EX / "freeze-b2-v1.json")
    assert sha(EX / "freeze-v1.json") == BATCH1_FREEZE_SHA, "batch-1 freeze changed"
    assert sha(EX / "run-v1/results.json") == BATCH1_RESULTS_SHA, "batch-1 results changed"
    freeze = json.loads((EX / "freeze-b2-v1.json").read_text(encoding="utf-8"))
    run784 = json.loads(RUN784.read_text(encoding="utf-8"))
    run77 = json.loads(RUN77.read_text(encoding="utf-8"))
    org = __import__("organizer_v1")

    for row in freeze["rows"]:
        got = [f for c in row["A_calls"] for f in c["factIds"]]
        want = [f["factId"] for f in row["facts"]]
        assert sorted(got) == sorted(want), (row["sourceId"], got, want)
        assert len(got) == len(set(got)), (row["sourceId"], "duplicate fact")

    for row in freeze["rows"]:
        rec = run784[row["split"]][row["sourceId"]]
        text = assemble([{"callId": c["callId"], "factIds": c["factIds"]} for c in row["B_calls"]],
                        rec["calls"], row["plan"].get("edges", []))
        assert text == rec["assembled"], (row["sourceId"], text, rec["assembled"])
        assert text == row["recorded_784_assembled"]

    checked = 0
    for s in freeze["samples"]:
        row = next(r for r in freeze["rows"] if r["sourceId"] == s["sourceId"])
        rec = run784[row["split"]][row["sourceId"]]
        text = group_text(row, rec["calls"], s["groupFacts"])
        hit = [g for g in rec.get("groups", []) if g["facts"] == s["groupFacts"]]
        assert hit, (s["sampleId"], "no recorded group")
        assert text == hit[0]["text"], (s["sampleId"], text, hit[0]["text"])
        checked += 1

    out = {}
    for s in freeze["samples"]:
        row = next(r for r in freeze["rows"] if r["sourceId"] == s["sourceId"])
        a = run77["arms"]["A-large"][row["split"]][row["sourceId"]]["calls"]
        sent = {fid: a[c["callId"]]["text"] for c in row["A_calls"] for fid in c["factIds"]}
        out[s["sampleId"]] = org.group_span(row, s["groupFacts"], sent)

    print("freeze-b2", FREEZE_SHA)
    print("batch-1 freeze/results unchanged")
    print("rows", len(freeze["rows"]), "samples", len(freeze["samples"]), "prompts", len(freeze["prompts"]))
    print("J reassembly matches recorded 784: all rows")
    print("sample group texts matched to recorded groups:", checked)
    for k, v in out.items():
        print(k, v)


if __name__ == "__main__":
    main()

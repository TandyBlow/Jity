# -*- coding: utf-8 -*-
"""Build the frozen tamper-probe set for the v2 text checker.

The probes are derived mechanically from the r1 reference texts (18 texts, all
accepted by the v1 checker) so the mutation is auditable: every probe names the
base (sourceId, planId) and the exact edit, and the resulting literal text is
stored in freeze/tamper-probes.json with a sha256.

Two expectation kinds:
    "fail"   -> at least one hard finding with the listed code
    "review" -> no hard finding, but a review item whose residual run contains
                the listed text (a human must confirm or reject it)

Usage:
    python -X utf8 build_tamper_probes.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN1 = HERE / "runs" / "r1"
OUT = HERE / "freeze" / "tamper-probes.json"


def sentences(text: str) -> list[str]:
    return [p for p in text.split("。") if p]


def join(sents: list[str]) -> str:
    return "。".join(sents) + "。"


def main() -> int:
    texts = {}
    for line in (RUN1 / "reference-output.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        texts[(row["sourceId"], row["planId"])] = row["text"]

    r1p1 = sentences(texts[("fixture-r1", "P1")])
    r1p2 = sentences(texts[("fixture-r1", "P2")])
    t2p1 = sentences(texts[("train-r2", "P1")])

    probes = []

    def add(pid, base, mutation, text, verdict, codes, review_contains=None, note=""):
        probes.append({
            "probeId": pid,
            "baseSourceId": base[0],
            "basePlanId": base[1],
            "mutation": mutation,
            "text": text,
            "textSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "expect": {
                "verdict": verdict,
                "mustIncludeCodes": codes,
                "reviewRunContains": review_contains or [],
            },
            "note": note,
        })

    add("T01-reverse-sentences", ("fixture-r1", "P1"),
        "reverse the order of all four sentences",
        join(list(reversed(r1p1))), "fail", ["group-out-of-order"],
        note="v1 accepted this: it only compared adjacent groups for 'different sentence'.")

    add("T02-sequence-out-of-scope", ("fixture-r1", "P1"),
        "prefix the 周宁 sentence (not the edge target) with 随后",
        join([r1p1[0], "随后，" + r1p1[1], r1p1[2], r1p1[3]]), "fail",
        ["sequence-wording-outside-scope", "sequence-wording-excess"],
        note="v1 accepted this: it only checked that a required edge exists somewhere in the text.")

    add("T03-add-unlicensed-object", ("fixture-r1", "P1"),
        "append ，并拿走了一把刀 to the last sentence",
        join(r1p1[:3] + [r1p1[3] + "，并拿走了一把刀"]), "review",
        ["added-content-outside-vocabulary"], review_contains=["刀"],
        note="v1 accepted this; v2 must flag 刀 as vocabulary outside the selected facts, names and visible list.")

    add("T04-swap-two-groups", ("fixture-r1", "P1"),
        "swap sentence 0 and sentence 1 (group order broken, sentence count unchanged)",
        join([r1p1[1], r1p1[0], r1p1[2], r1p1[3]]), "fail", ["group-out-of-order"])

    add("T05-swap-clauses-in-group", ("fixture-r1", "P1"),
        "swap the two clauses inside group [f0,f1]",
        join([r1p1[0].replace("袖口沾了雨，指节发白", "指节发白，袖口沾了雨")] + r1p1[1:]), "fail",
        ["within-group-order"])

    add("T06-second-sequence-word", ("fixture-r1", "P1"),
        "append ，随后，陈默退了出去 to the last sentence",
        join(r1p1[:3] + [r1p1[3] + "，随后，陈默退了出去"]), "fail",
        ["sequence-wording-outside-scope", "sequence-wording-excess"])

    add("T07-added-sentence", ("fixture-r1", "P1"),
        "insert an extra sentence 潮汐簿被合上了。 in the middle",
        join(r1p1[:2] + ["潮汐簿被合上了"] + r1p1[2:]), "fail", ["added-sentence"],
        review_contains=["合"], note="also produces a review item because 合 is outside the vocabulary")

    add("T08-drop-required-wording", ("fixture-r1", "P2"),
        "delete 随后， from the required-edge target sentence",
        join([s.replace("随后，", "", 1) if "随后" in s else s for s in r1p2]), "fail",
        ["sequence-wording-missing"])

    add("T09-props-only-addition", ("fixture-r1", "P1"),
        "append ，墨和干纸还在 to the last sentence (all characters come from the visible list)",
        join(r1p1[:3] + [r1p1[3] + "，墨和干纸还在"]), "review",
        ["added-content-visible-only"], review_contains=["墨"])

    add("T10-wrong-actor", ("fixture-r1", "P1"),
        "replace the first 林川 with 周宁",
        join([r1p1[0].replace("林川", "周宁", 1)] + r1p1[1:]), "fail", ["ref-name-missing"])

    add("T11-sequence-in-grouping-family", ("train-r2", "P1"),
        "append 随后 to the first sentence; this source carries no authorised edge at all",
        join(["随后，" + t2p1[0]] + t2p1[1:]), "fail", ["invented-sequence"],
        note="the grouping family has edges=[]; any 随后 must be rejected outright")

    doc = {
        "protocol": "c3-tamper-probes-v2",
        "created": datetime.now(timezone.utc).isoformat(),
        "checkerVersion": "c3-text-conformance-v2",
        "baseTexts": "runs/r1/reference-output.jsonl (18 texts, all accepted by the v1 checker)",
        "note": ("Each probe is one mechanical edit of a reference text. 'fail' means at least one hard "
                 "finding with one of the listed codes. 'review' means no hard finding but a review item "
                 "whose residual run contains the listed substring; a human verdict is required before "
                 "the item is accepted."),
        "probes": probes,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(probes)} probes)")
    for p in probes:
        print(f"  {p['probeId']}: {p['expect']['verdict']} {p['expect']['mustIncludeCodes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

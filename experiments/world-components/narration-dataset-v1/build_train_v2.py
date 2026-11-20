# -*- coding: utf-8 -*-
"""Combine two fact-clean target styles into one training file.

Sources
  1. the hand-written narration, after factcheck_yuyan dropped unsupported sentences
  2. the 7B teacher rewrite, after the same filter

Both keep the same prompt (built by build_instruct_rows.build_brief), so the
model sees one input format and two acceptable realisations of it. Quotes are
normalised to 「」 because the training material uses them.
"""
import json
import re

from build_instruct_rows import PROMPT, add_missing, build_brief, filter_paragraphs
from factcheck_yuyan import check


def normalise(text):
    text = text.replace("“", "「").replace("”", "」")
    text = re.sub(r"[ \t\u3000]+", " ", text)
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        line = re.sub(r"^[」』]+", "", line)
        line = re.sub(r"[「『]+$", "", line)
        if re.search(r"[\u4e00-\u9fff]", line):
            lines.append(line)
    return "\n\n".join(lines)


def main():
    rows = {r["id"]: r for r in (json.loads(l) for l in open("yuyan/rows-yuyan.jsonl", encoding="utf-8"))}
    teacher = {}
    for line in open("instruct/teacher-full.jsonl", encoding="utf-8"):
        record = json.loads(line)
        teacher[record["id"]] = record["filtered"]
    out = []
    for rid, row in rows.items():
        brief, view = build_brief(row)
        prompt = PROMPT.format(view=view, brief=brief)
        hand, _ = filter_paragraphs(row, row.get("yPlain", ""))
        hand = add_missing(row, hand, check(row, row.get("yPlain", "")))
        hand = normalise(hand)
        if len(hand) >= 160:
            out.append({"id": rid + "-hand", "prompt": prompt, "target": hand, "source": "hand"})
        rewrite = normalise(teacher.get(rid, ""))
        if len(rewrite) >= 160:
            out.append({"id": rid + "-teacher", "prompt": prompt, "target": rewrite, "source": "teacher"})
    with open("instruct/rows-v2.jsonl", "w", encoding="utf-8") as handle:
        for item in out:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(json.dumps({"pairs": len(out), "hand": sum(1 for i in out if i["source"] == "hand"),
                      "teacher": sum(1 for i in out if i["source"] == "teacher"),
                      "chars": sum(len(i["target"]) for i in out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

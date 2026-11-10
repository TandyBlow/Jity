# -*- coding: utf-8 -*-
"""Convert a 09 product handoff into the sequence-review JSONL.

Usage:
  python -X utf8 convert_09_handoff.py <handoff.json> <out.jsonl>

The handoff schema is `09-quality-handoff`: turns[] with id, input (player
command), text, message, before/after UI summaries, timings, problems.

What can be reviewed from that alone:
  - cross-turn repetition (full text is enough),
  - turn-level provenance (`text` vs `fallbackNote`),
  - per-turn presence/task drift against the UI summaries, as review items only.

What cannot: fact checks against settled state. Those need `settled` per turn
(视角/上回合状态/本回合变化/本回合状态). When it is missing this script writes
the turn with `input: null` so the review reports `undetermined` instead of
pretending to have checked it.
"""
import json
import sys

UI_TO_DATASET = {
    "sanity": "精神值",
    "place": "位置",
}


def turn_record(turn, group_id):
    settled = turn.get("settled") or None
    text = turn.get("text") or ""
    note = turn.get("fallbackNote") or ""
    source = "model"
    if settled and settled.get("textSource"):
        source = settled["textSource"]
    elif note or (turn.get("problems") or []) and "fallback" in " ".join(turn.get("problems") or []):
        source = "program_fallback"
    elif not text:
        source = "unknown"
    record = {
        "groupId": group_id,
        "turn": int(str(turn.get("id", "0")).split("-t")[-1] or 0),
        "input": settled.get("input") if settled else None,
        "text": text,
        "textSource": source,
        "playerCommand": turn.get("input"),
        "uiBefore": turn.get("before"),
        "uiAfter": turn.get("after"),
        "problems": turn.get("problems") or [],
        "timings": turn.get("timings") or {},
    }
    return record


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    handoff = json.loads(open(sys.argv[1], encoding="utf-8").read())
    group_id = (handoff.get("product") or {}).get("head") or handoff.get("at") or "09-handoff"
    turns = handoff.get("turns") or []
    with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as out:
        for index, turn in enumerate(turns, start=1):
            record = turn_record(turn, group_id)
            if not record["turn"]:
                record["turn"] = index
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    missing = sum(1 for turn in turns if not (turn.get("settled") or {}).get("input"))
    print(f"turns={len(turns)} missing_settled_input={missing}")


if __name__ == "__main__":
    main()

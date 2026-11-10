# -*- coding: utf-8 -*-
"""Grade beat-scoped teacher prose and filter it into supervised pairs.

A beat target is kept only when it stays on the fact's subject and carries the
fact itself. The checks are deliberately looser than the product's strict
`signature()` (which demands verbatim goal/personality text and would reject
every human row too); they encode what a reader can verify:

    moved                : subject named, both places named, not reversed
    task_achieved        : subject named, completion verb, goal's distinctive words
    personality_changed  : subject named, trait's distinctive words, no other actor
    sanity_changed       : subject named, direction words or the resulting number
    time                 : a duration with the same amount and unit

Anything else is reported, never silently dropped. Output rows are
`{"id", "split", "prompt", "target", "sourceId", "kind", "checks"}`.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))

DONE = re.compile(r"(查清|找到|找着|查完|问清|完成|做完|搞定|办完|了结|核对完|比对完|确认|合上|放回|收好|对上|交出去|拿到|记下)")
UP = re.compile(r"(回升|上升|恢复|稳住|松开|缓过来|散了些|散开|暖|安定|踏实)")
DOWN = re.compile(r"(下降|降到|落到|掉到|沉下去|发紧|发凉|收紧|压得|闷|散了一层|撑不住|发白)")
MOVE = re.compile(r"(走到|走向|走进|走入|走上|走进来|进来|出去|回到|退到|退回|"
                  r"往.{0,6}走|下楼|上楼|下楼去|转向|挪到|跨进|跨出|退开|"
                  r"离开|移到|移到|过来|过去)")
EXTRA_ACTOR = re.compile(r"[\u4e00-\u9fff]{2,3}(说|问|答|喊|道|看|伸手|抬起|低头)")


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def words(text: str) -> List[str]:
    """Distinctive 2-char pieces of a Chinese phrase, stopwords removed."""
    stop = {"这个", "那个", "一件", "事情", "自己", "已经", "没有", "什么", "一直",
            "一个", "的是", "了的", "里的", "把", "了", "的", "在", "和", "与",
            "上", "下", "里", "个", "这", "那", "他", "她", "它", "们", "就", "也"}
    pieces = [text[i:i + 2] for i in range(len(text) - 1)]
    return [piece for piece in pieces if piece not in stop and not re.search(r"[，。、：；「」（）]", piece)]


def overlap(text: str, phrase: str, need: int = 2) -> int:
    return sum(1 for piece in words(phrase) if piece in text and len(piece) == 2) >= need


def check(beat: Dict[str, Any], text: str) -> Dict[str, Any]:
    fact = beat["fact"]
    kind = fact["kind"]
    others = [name for name in beat["scene"].get("present") or []
              if name != fact.get("name")]
    issues: List[str] = []
    if kind == "moved":
        if fact["name"] not in text:
            issues.append("subject_missing")
        if fact["from"] not in text:
            issues.append("origin_missing")
        if fact["to"] not in text:
            issues.append("target_missing")
        if MOVE.search(text) is None:
            issues.append("no_movement_verb")
    elif kind == "task_achieved":
        if fact["name"] not in text:
            issues.append("subject_missing")
        if DONE.search(text) is None:
            issues.append("no_completion_verb")
        if not overlap(text, fact["goal"]):
            issues.append("goal_not_recognisable")
    elif kind == "personality_changed":
        if fact["name"] not in text:
            issues.append("subject_missing")
        if not overlap(text, fact["text"]):
            issues.append("trait_not_recognisable")
    elif kind == "sanity_changed":
        if fact["name"] not in text:
            issues.append("subject_missing")
        direction = UP if fact["to"] > fact["from"] else DOWN
        if direction.search(text) is None and str(fact["to"]) not in text:
            issues.append("direction_missing")
    elif kind == "time":
        if f"{fact['amount']}" not in text:
            issues.append("amount_missing")
    if len(text) > 120:
        issues.append("too_long")
    if "\n" in text:
        issues.append("multiple_paragraphs")
    for name in others:
        if name in text and re.search(re.escape(name) + r"[^，。]{0,4}(说|问|答|道|伸手|抬手|低头)", text):
            issues.append(f"other_actor:{name}")
            break
    return {"ok": not issues, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--beats", default=os.path.join(V2, "data", "beats-v1.jsonl"))
    parser.add_argument("--raw", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    beats = {beat["id"]: beat for beat in read_jsonl(args.beats)}
    raw = read_jsonl(args.raw)
    kept: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    per_kind: Dict[str, Dict[str, int]] = {}
    for row in raw:
        beat = beats.get(row.get("id") or "")
        if not beat:
            continue
        kind = beat["fact"]["kind"]
        stats = per_kind.setdefault(kind, {"candidates": 0, "kept": 0})
        for text in row.get("candidates") or row.get("samples") or row.get("texts") or []:
            text = str(text).strip()
            if not text:
                continue
            stats["candidates"] += 1
            verdict = check(beat, text)
            if verdict["ok"]:
                stats["kept"] += 1
                kept.append({"id": f"{beat['id']}-{stats['kept']}",
                             "split": beat["split"], "prompt": row.get("prompt")
                             or beat.get("prompt"), "target": text,
                             "sourceId": beat["sourceId"], "kind": kind,
                             "checks": verdict})
                break
            rejected.append({"id": beat["id"], "text": text, "issues": verdict["issues"]})
    with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        for row in kept:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {"kept": len(kept), "beats": len(beats), "perKind": per_kind,
               "rejectedExamples": rejected[:20]}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if args.report:
        with io.open(args.report, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

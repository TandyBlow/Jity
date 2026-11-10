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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import narration_rules as R  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))

DONE = re.compile(r"(查清|查明|找到|找着|查完|问清|完成|做完|搞定|办完|了结|核对|"
                  r"比对|确认|合上|放回|收好|对上|交出去|拿到|记下|守住|接诊|"
                  r"留下|留出|换掉|告诉|说明|发布|安排|报告|解决|放行|登记|"
                  r"撤|交|办成|办妥|答完|数完|理完|整完|翻完|换到|到达|走到|"
                  r"定下来|结束|缓过来|缓了|做实|做完)")
UP = re.compile(r"(回升|上升|恢复|稳住|松开|缓过来|散了些|散开|暖|安定|踏实)")
DOWN = re.compile(r"(下降|降到|落到|掉到|沉下去|发紧|发凉|收紧|压得|闷|散了一层|撑不住|发白)")
MOVE = re.compile(r"(走到|走向|走进|走入|走上|走进来|进来|出去|回到|退到|退回|"
                  r"退进|绕到|穿过|下到|走下|下楼|上楼|转向|挪到|跨进|跨出|"
                  r"退开|离开|移到|过来|过去|进了|出了)")
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


MOOD = re.compile(r"(似乎|仿佛|像是|宛如|好像|承载|岁月|寂寥|故事|秘密|遗弃|细语)")
# Clichés that dominated the first teacher pass; a supervised target built from
# them teaches one opening sentence for every fact instead of prose.
CLICHE = re.compile(r"(微微颤抖|深吸一口气|轻轻|目光扫过|吱嘎|沙沙|泛黄|尘土|寂静|静谧|"
                    r"空气里|回声|脚步声在|心头|心里|某种|一丝|几分|缓缓|慢慢|默默|"
                    r"小心翼翼|仔细|认真|仿佛|似乎|像是|终于)")
CN_NUMBERED = re.compile(r"第[一二三四五六七八九十百千零两]+(页|章|行|年|天|月|日|排|个)")

HARD_VIOLATIONS = {"added_event", "actor_swap", "promise_without_fact",
                   "past_without_fact", "wrong_time", "reversed_arrival",
                   "unlicensed_entity"}


def project_check(row: Optional[Dict[str, Any]], text: str) -> List[str]:
    """Product-rule violations that indicate invented action/past/time."""
    if row is None:
        return []
    result = R.check_row(row["x"], text)
    return [violation["kind"] for violation in result["violations"]
            if violation["kind"] in HARD_VIOLATIONS]


def digits(text: str) -> List[str]:
    return re.findall(r"[0-9]+", text)


def check(beat: Dict[str, Any], text: str,
          row: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        amount = (fact.get("amount") if "amount" in fact
                  else (beat.get("time") or {}).get("amount"))
        unit = (fact.get("unit") if "unit" in fact
                else (beat.get("time") or {}).get("unit"))
        cn = {1: "一", 2: "两", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七",
              8: "八", 9: "九", 10: "十", 15: "十五", 20: "二十", 30: "三十"}
        if amount == 60 and unit == "minute" and "小时" in text:
            pass
        elif amount is None or (str(amount) not in text
                                and cn.get(amount, "") not in text):
            issues.append("amount_missing")
    if MOOD.search(text):
        issues.append("mood_or_interpretation")
    if CLICHE.search(text):
        issues.append("cliche")
    if CN_NUMBERED.search(text) and not CN_NUMBERED.search(beat.get("prompt") or ""):
        issues.append("invented_numbered_thing")
    if len(text) > 90:
        issues.append("too_long")
    if "\n" in text:
        issues.append("multiple_paragraphs")
    for name in others:
        if name in text and re.search(re.escape(name) + r"[^，。]{0,4}(说|问|答|道|伸手|抬手|低头)", text):
            issues.append(f"other_actor:{name}")
            break
    allowed_numbers = set(digits(beat.get("prompt") or ""))
    if beat["fact"]["kind"] == "sanity_changed":
        allowed_numbers.update({str(beat["fact"]["from"]), str(beat["fact"]["to"])})
    invented = [number for number in digits(text) if number not in allowed_numbers]
    if invented:
        issues.append("invented_number:" + ",".join(invented[:2]))
    for kind in project_check(row, text):
        issues.append("product_rule:" + kind)
    return {"ok": not issues, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--beats", default=os.path.join(V2, "data", "beats-v1.jsonl"))
    parser.add_argument("--raw", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default="")
    parser.add_argument("--rows", default=os.path.join(V2, "data", "rows-v2.jsonl"),
                        help="frozen rows, for product-rule checks on library beats")
    args = parser.parse_args()

    beats = {beat["id"]: beat for beat in read_jsonl(args.beats)}
    rows = {}
    if args.rows and os.path.exists(args.rows):
        rows = {row["id"]: row for row in read_jsonl(args.rows)}
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
            verdict = check(beat, text, rows.get(beat.get("sourceId") or ""))
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

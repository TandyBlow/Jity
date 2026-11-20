# -*- coding: utf-8 -*-
"""12-character overlap between supervision targets: generic phrasing vs
content-specific reproduction.

10-training reported that v1/v3 "memorise" training lines, measured as shared
12-character windows. A 12-character window can be ordinary syntax ("她把钥匙
从锁孔里取出来") or a content-specific phrase (a name plus an event). This
script separates the two so the report can say which kind is duplicated.

Usage:
    python -X utf8 experiments/narration-quality/review/overlap12.py \
        <train.jsonl> <out.json>
"""
import itertools
import json
import io
import sys
from collections import Counter, defaultdict

TRAIN = sys.argv[1] if len(sys.argv) > 1 else (
    "D:/others/Jity/.local/parallel-local-game/worktrees/10-training/"
    "experiments/narration-runtime-v2/data/train-page-v3.jsonl")
OUT = sys.argv[2] if len(sys.argv) > 2 else (
    "D:/others/Jity/.local/parallel-local-game/results/quality/overlap12-01.json")
TEXTS = sys.argv[3] if len(sys.argv) > 3 else None

# Names and event nouns that make a shared window content-specific.
CONTENT_MARKERS = [
    "路明非", "诺诺", "芬格尔", "楚子航", "凯撒", "苏茜", "林亦舟", "唐骁", "周映",
    "秦越", "顾岚", "沈澄", "富山雅史", "曼施坦因", "黎含章", "沈砚", "罗平",
    "阿茂", "陈漪", "温执", "黎知微", "周宁", "林川", "顾望舒",
    "潮位计", "水尺", "浮标", "救生衣", "档案", "还书处", "装订间", "值班室",
    "服务巷", "护目镜", "演习背心", "短枪", "规则牌", "路线图", "盒子",
]
# Task/event verbs: a window with these says what happened, not just how.
EVENT_MARKERS = [
    "走到", "走进", "走到", "离开", "递给", "接过", "放下", "拿起", "打开", "合上",
    "完成", "答应", "拒绝", "告诉", "问道", "说道", "回答", "看见", "听见",
    "扶住", "蹲下", "退了", "摇了摇头", "点了点头",
]

MIN = 12


def windows(text):
    clean = "".join(ch for ch in text if ch not in " \t\r\n")
    return {clean[i:i + MIN] for i in range(0, max(0, len(clean) - MIN + 1))}


def classify(window):
    if any(marker in window for marker in CONTENT_MARKERS):
        return "content"
    if any(marker in window for marker in EVENT_MARKERS):
        return "event"
    return "generic"


def main():
    rows = [json.loads(line) for line in io.open(TRAIN, encoding="utf-8") if line.strip()]
    index = defaultdict(list)
    for row in rows:
        for window in windows(row["target"]):
            index[window].append(row["id"])
    shared = {window: ids for window, ids in index.items() if len({*ids}) > 1}
    kinds = Counter(classify(window) for window in shared)
    # Per row: how many of its windows are shared, and of which kind.
    per_row = {}
    for row in rows:
        mine = windows(row["target"])
        hits = [window for window in mine if window in shared]
        per_row[row["id"]] = {
            "shared": len(hits),
            "content": sum(1 for w in hits if classify(w) == "content"),
            "event": sum(1 for w in hits if classify(w) == "event"),
            "generic": sum(1 for w in hits if classify(w) == "generic"),
            "examples": sorted(hits, key=classify)[:4],
        }
    texts = []
    if TEXTS:
        target_windows = defaultdict(set)
        for row in rows:
            for window in windows(row["target"]):
                target_windows[window].add(row["id"])
        for line in io.open(TEXTS, encoding="utf-8"):
            if not line.strip():
                continue
            item = json.loads(line)
            hits = [w for w in windows(item["text"]) if w in target_windows]
            texts.append({
                "id": item["id"],
                "chars": len(item["text"]),
                "shared": len(hits),
                "content": sorted(w for w in hits if classify(w) == "content"),
                "event": sorted(w for w in hits if classify(w) == "event"),
                "generic": len([w for w in hits if classify(w) == "generic"]),
            })
    payload = {
        "train": TRAIN,
        "rows": len(rows),
        "window": MIN,
        "sharedWindows": len(shared),
        "kinds": dict(kinds),
        "rowsWithShared": sum(1 for v in per_row.values() if v["shared"]),
        "rowsWithContentShared": sum(1 for v in per_row.values() if v["content"]),
        "perRow": per_row,
        "texts": texts,
    }
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: payload[k] for k in
                      ("rows", "sharedWindows", "kinds", "rowsWithShared", "rowsWithContentShared")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()

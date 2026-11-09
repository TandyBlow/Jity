# -*- coding: utf-8 -*-
"""Turn the reviewed 104 rows into the shape YuYan-700M can actually eat.

Three differences from the original rows, all forced by that model:

1. No spaces anywhere. The character-level vocabulary (13,668 chars) has no
   space token; a prompt containing one makes the tokenizer throw
   `invalid unordered_map<K, T> key`. Every row's X contains spaces, both from
   json.dumps separators and from the data itself ("3 分钟").
2. No newlines. The vocabulary has no newline either, so a paragraph break is
   written as the marker "※" (one character, in the vocabulary, unused by any
   row) and turned back into a blank line when the text is shown.
3. The JSON is gone. Feeding this model raw JSON makes it loop on the brackets
   themselves, so the same facts are written as labelled lines. No new facts are
   introduced; every string comes from the row.

Output is one record per row:

  id       the row id
  xJson    the original X, spaces removed, compact JSON (kept for comparison)
  xProse   the labelled-line version, ends with the 正文 header
  yMarked  the narrative with "※" standing in for the blank line between paragraphs
  yPlain   the narrative as written, for reference
"""

import io
import json
import os
import re

MARK = "※"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rows-yuyan.jsonl")
SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rows-xy.jsonl")


def squash(text):
    """Spaces are not in the vocabulary; digits keep their meaning without them."""
    return re.sub(r"[ \t\u3000]+", "", text)


def join_items(items):
    """Items are records, not sentences; a trailing full stop would double up."""
    clean = [squash(item).rstrip("。；，") for item in items]
    return "、".join(item for item in clean if item)


def task_line(tasks):
    parts = []
    big = tasks.get("大任务")
    if big:
        parts.append(f"{squash(big['目标'])}（{big['状态']}）")
    for small in tasks.get("小任务", []):
        parts.append(f"{squash(small['目标'])}（{small['状态']}）")
    return "；".join(parts)


def person_line(name, entry, fields=None):
    pieces = []
    if fields is None or "位置" in fields:
        where = entry.get("位置")
        if where:
            pieces.append(f"在{where}")
    if fields is None or "精神值" in fields:
        if "精神值" in entry:
            pieces.append(f"精神值{entry['精神值']}")
    if fields is None or "外貌" in fields:
        if entry.get("外貌"):
            pieces.append("外貌" + join_items(entry["外貌"]))
    if fields is None or "个性" in fields:
        if entry.get("个性"):
            pieces.append("个性" + join_items(entry["个性"]))
    if fields is None or "任务" in fields:
        if entry.get("任务"):
            pieces.append("任务" + task_line(entry["任务"]))
    return f"{name}：" + "，".join(pieces) + "。"


def place_line(name, entry):
    looks = join_items(entry.get("外貌", []))
    parent = entry.get("位于")
    body = f"{name}"
    if parent:
        body += f"（在{parent}里）"
    if looks:
        body += f"：{looks}"
    return body + "。"


def render_state(state):
    lines = []
    places = state.get("地点", {})
    if places:
        lines.append("【地点】" + "".join(place_line(name, entry)
                                        for name, entry in sorted(places.items())))
    people = state.get("人物", {})
    if people:
        lines.append("【人物】" + "".join(person_line(name, entry)
                                        for name, entry in sorted(people.items())))
    things = state.get("物品", {})
    if things:
        lines.append("【物品】" + "".join(place_line(name, entry)
                                        for name, entry in sorted(things.items())))
    return "".join(lines)


def describe_change(entity, ops, state):
    """One sentence per changed entity, written from the ops that were declared."""
    pieces = []
    if "位置" in ops:
        pieces.append(f"移动到{ops['位置']}")
    if "精神值" in ops:
        pieces.append(f"精神值变成{ops['精神值']}")
    if ops.get("解除外貌"):
        pieces.append("去掉外貌" + join_items(ops["解除外貌"]))
    if ops.get("新增外貌"):
        pieces.append("多出外貌" + join_items(ops["新增外貌"]))
    if ops.get("解除个性"):
        pieces.append("去掉个性" + join_items(ops["解除个性"]))
    if ops.get("新增个性"):
        pieces.append("多出个性" + join_items(ops["新增个性"]))
    if ops.get("完成任务"):
        pieces.append("完成" + join_items(ops["完成任务"]))
    if ops.get("新增小任务"):
        pieces.append("新任务" + join_items([task["目标"] for task in ops["新增小任务"]]))
    if not pieces:
        return ""
    kind = "地点" if entity in state.get("地点", {}) else (
        "物品" if entity in state.get("物品", {}) else "人物")
    return f"{entity}（{kind}）：" + "，".join(pieces) + "。"


def render_delta(delta, before, after):
    time_line = f"时间推进{squash(delta.get('时间推进', ''))}。"
    changes = delta.get("变化", {})
    if not changes:
        return "【变化】" + time_line + "这一回合没有结算出变化。"
    body = "".join(describe_change(name, ops, {**before, **after})
                   for name, ops in sorted(changes.items()))
    return "【变化】" + time_line + body


def render_row(row):
    data = json.loads(row["xText"])
    before = data.get("上回合状态", {})
    delta = data.get("本回合变化", {})
    after = data.get("本回合状态", {})
    viewpoint = squash(data.get("视角", "")).split("；")[0]
    parts = [
        "【视角】" + viewpoint,
        render_state(before),
        render_delta(delta, before, after),
        render_state(after),
        "【正文】",
    ]
    return "".join(part for part in parts if part)


def main():
    rows = [json.loads(line) for line in io.open(SOURCE, encoding="utf-8")]
    out = []
    for row in rows:
        data = json.loads(row["xText"])
        prose = render_row(row)
        paragraphs = [p.strip() for p in row["y"].split("\n\n") if p.strip()]
        record = {
            "id": row["id"],
            "xJson": squash(json.dumps(data, ensure_ascii=False, separators=(",", ":"))),
            "xProse": prose,
            "xProseChars": len(prose),
            "yMarked": MARK.join(paragraphs),
            "yPlain": row["y"],
            "paragraphs": len(paragraphs),
            "targetChars": len(row["y"]),
        }
        out.append(record)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        for record in out:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"{OUT}: {len(out)} rows")
    print(f"xProse 字符数 {min(r['xProseChars'] for r in out)}-"
          f"{max(r['xProseChars'] for r in out)}，平均 "
          f"{round(sum(r['xProseChars'] for r in out) / len(out))}")
    print("xProse 含空格:", any(" " in r["xProse"] for r in out))
    print("yMarked 含空格:", any(" " in r["yMarked"] for r in out))
    print("yMarked 含换行:", any("\n" in r["yMarked"] for r in out))


if __name__ == "__main__":
    main()

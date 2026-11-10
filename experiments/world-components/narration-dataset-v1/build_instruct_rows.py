# -*- coding: utf-8 -*-
"""Build the browser training pairs: compact settled facts -> fact-clean prose.

The prompt mirrors `instructNarrationInput` in
frontend/src/lib/world-engine/local/prompt.ts so that what the browser sends at
inference is exactly what the model saw in training. The target is the
hand-written narration after `factcheck_yuyan` removed sentences whose claims
the row's state does not support.
"""
import json
import re
import sys

from factcheck_yuyan import check, parse

UNIT = {"second": "秒", "minute": "分钟", "hour": "小时", "day": "天", "month": "个月", "year": "年"}


def squash(text):
    text = re.sub(r"[ \t\u3000]+", " ", text or "").strip()
    return re.sub(r"[。；，]+$", "", text)


def appearances(value):
    out = []
    look = value.get("外貌")
    if isinstance(look, list):
        out.extend(look)
    elif look:
        out.append(str(look))
    return out


def build_brief(row):
    x, before, change, after_part, chars, items, locs, after, item_after, delta, view = parse(row)
    name = view
    room = after[view].get("位置") or chars[view].get("位置") or ""
    sentences = []
    move = change.get("时间推进") or ""
    m = re.match(r"\s*(\d+)\s*(\S+)", move)
    if m:
        sentences.append(f"时间过去了{m.group(1)}{m.group(2)}。")
    own = delta.get(view) or {}
    if own.get("位置"):
        previous = chars[view].get("位置") or ""
        sentences.append(f"{name}{'从' + previous if previous else ''}走到了{own['位置']}。")
    look = squash("，".join(appearances(after[view])))[:60]
    sentences.append(f"{name}现在在{room}{'，' + look if look else ''}。")
    others = [n for n in chars if n != view and (after[n].get("位置") or chars[n].get("位置")) == room]
    for other in others[:3]:
        look = squash("，".join(appearances(after[other])))[:50]
        sentences.append(f"{other}也在{room}{'，' + look if look else ''}。")
    for other, value in delta.items():
        if other == view or not isinstance(value, dict):
            continue
        if value.get("位置"):
            sentences.append(f"{other}去了{value['位置']}。")
        for goal in value.get("完成任务") or []:
            sentences.append(f"{other}完成了「{goal}」。")
        if value.get("精神值") is not None:
            sentences.append(f"{other}的精神值变成{value['精神值']}。")
    if not others:
        sentences.append("房间里没有别人。")
    return "".join(sentences), view


def filter_paragraphs(row, text):
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text.replace("※", "\n\n")) if p.strip()]
    kept = []
    dropped = 0
    for paragraph in paragraphs:
        result = check(row, paragraph)
        kept_text = "".join(result["kept"]).strip()
        if not re.search(r"[一-鿿]", kept_text):
            continue
        kept_text = re.sub(r"^[」』）】]+", "", kept_text).strip()
        dropped += len(result["violations"])
        if kept_text:
            kept.append(kept_text)
    return "\n\n".join(kept), dropped


def add_missing(row, text, check_result):
    _, _, _, _, chars, _, _, after, _, delta, view = parse(row)
    extra = []
    for item in check_result.get("missing", []):
        if item.startswith("position:"):
            name, loc = item.split(":", 1)[1].split("->", 1)
            old = (chars.get(name) or {}).get("位置") or ""
            extra.append(f"{name}从{old}走到{loc}。" if old else f"{name}走到{loc}。")
        elif item.startswith("task:"):
            goal = item.split(":", 1)[1]
            owner = next((n for n, v in delta.items() if isinstance(v, dict) and goal in (v.get("完成任务") or [])), view)
            extra.append(f"{owner}完成了「{goal}」。")
    return text + ("\n\n" + "".join(extra) if extra else "")


PROMPT = (
    "你是中文小说作者。下面是这一回合已经结算的事实，请写成 {view} 视角的小说正文，250 到 350 字。\n"
    "要求：只写事实里有的人和事；不要复述这份清单；不要写时间、地点、人物之类的标题；不要用 Markdown；"
    "不要加人物、地点、物品、事件或数字；短句，对白用「」，分 3 到 5 段。\n"
    "事实：\n{brief}\n正文："
)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "yuyan/rows-yuyan.jsonl"
    out = sys.argv[2] if len(sys.argv) > 2 else "instruct/rows-instruct.jsonl"
    rows = [json.loads(line) for line in open(src, encoding="utf-8")]
    kept_rows = []
    stats = {"rows": 0, "kept": 0, "chars": 0, "droppedSentences": 0}
    for row in rows:
        brief, view = build_brief(row)
        body, dropped = filter_paragraphs(row, row.get("yPlain", ""))
        full = check(row, row.get("yPlain", ""))
        body = add_missing(row, body, full)
        chars = len(body.replace("\n", ""))
        stats["rows"] += 1
        stats["droppedSentences"] += dropped
        if chars < 160:
            continue
        stats["kept"] += 1
        stats["chars"] += chars
        kept_rows.append({
            "id": row["id"],
            "prompt": PROMPT.format(view=view, brief=brief),
            "target": body,
            "chars": chars,
        })
    import os
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        for item in kept_rows:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(json.dumps(stats, ensure_ascii=False))
    if kept_rows:
        print(json.dumps(kept_rows[0], ensure_ascii=False)[:900])


if __name__ == "__main__":
    main()

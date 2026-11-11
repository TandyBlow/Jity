# -*- coding: utf-8 -*-
"""Sentence-level fact gate for the yuyan rows.

This is deliberately conservative: it keeps a sentence only when every named
character/location, every number and every hard event can be traced to the
row's before state or this turn's delta.  It is a data filter, not the browser
grader; the browser keeps its own TypeScript alignment check.
"""
import json
import re

HARD_EVENTS = [
    "推开", "推门", "打开", "关上", "拿起", "放下", "递给", "接过", "开枪",
    "枪响", "枪声", "敲门", "脚步声", "摔倒", "晕倒", "醒来", "发现", "找到",
    "撕下", "撕掉", "掏出", "摸出", "点亮", "熄灭", "爆炸", "破裂", "冲进",
    "冲出", "跑进", "跑出", "离开", "走进", "走出", "回到", "来到", "跳下",
    "爬上", "抱住", "抓住", "打翻", "砸", "踢", "喊", "叫", "哭", "响",
]
MOVE_WORDS = ["走进", "走出", "离开", "回到", "来到", "走向", "走到", "进入", "回到"]
SAFE_NUM_UNITS = ["个人", "人", "分钟", "秒", "小时", "岁", "年", "排", "张", "只", "本", "份", "次", "步"]


def parse(row):
    x = json.loads(row["xJson"]) if isinstance(row["xJson"], str) else row["xJson"]
    before = x.get("上回合状态", {})
    change = x.get("本回合变化", {})
    after_part = x.get("本回合状态", {})
    chars = before.get("人物", {})
    items = before.get("物品", {})
    locs = before.get("地点", {})
    after = {}
    for name, value in chars.items():
        merged = dict(value)
        if name in after_part:
            merged.update(after_part[name])
        after[name] = merged
    item_after = {}
    for name, value in items.items():
        merged = dict(value)
        if name in after_part:
            merged.update(after_part[name])
        item_after[name] = merged
    delta = change.get("变化", {})
    view = ""
    m = re.search(r"主角视角[（(]([^）)]+)[）)]", x.get("视角", ""))
    if m:
        view = m.group(1)
    if not view and chars:
        view = next(iter(chars))
    return x, before, change, after_part, chars, items, locs, after, item_after, delta, view


def ancestors(name, locs):
    out = []
    seen = set()
    while name and name not in seen:
        out.append(name)
        seen.add(name)
        name = (locs.get(name, {}) or {}).get("位于")
    return out


def related_locations(names, locs, after_pos):
    out = set()
    for name in names:
        out.update(ancestors(after_pos.get(name), locs))
    return out


def split_sentences(text):
    text = text.replace("※", "\n")
    parts = re.split(r"(?<=[。！？!?])|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def check(row, text):
    x, before, change, after_part, chars, items, locs, after, item_after, delta, view = parse(row)
    names = sorted(chars.keys(), key=len, reverse=True)
    item_names = sorted(items.keys(), key=len, reverse=True)
    all_locs = set(locs.keys())
    before_pos = {n: (chars[n].get("位置") or "") for n in chars}
    after_pos = {n: (after[n].get("位置") or before_pos[n]) for n in chars}
    changed_pos = {n: v.get("位置") for n, v in delta.items() if isinstance(v, dict) and v.get("位置")}
    visible = {n for n in chars if after_pos.get(n) == after_pos.get(view)}
    allowed_chars = visible | set(changed_pos) | {view}
    allowed_locs = related_locations(allowed_chars, locs, after_pos)
    # Items in the protagonist's room or on a changed character.
    allowed_items = {n for n in items if item_after.get(n, {}).get("位置") == after_pos.get(view)}
    completed = set()
    for n, v in delta.items():
        if isinstance(v, dict):
            completed.update(v.get("完成任务") or [])
    all_goals = set()
    for c in chars.values():
        t = c.get("任务", {})
        big = t.get("大任务")
        if big and big.get("目标"):
            all_goals.add(big["目标"])
        for small in t.get("小任务", []) or []:
            if small.get("目标"):
                all_goals.add(small["目标"])
    x_text = json.dumps(x, ensure_ascii=False)
    # Numbers that are literally present in the row.
    number_facts = set(re.findall(r"[0-9]+", x_text))
    number_facts.update(re.findall(r"[一二三四五六七八九十百千万两]+(?:个人|人|分钟|秒|小时|岁|年|排|张|只|本|份|次|步)?", x_text))
    violations = []
    kept = []
    covered_pos = set()
    covered_task = set()
    for sent in split_sentences(text):
        local = []
        # Characters: a name outside the visible/changed set is a new actor.
        mentioned = [n for n in names if n in sent]
        outside = [n for n in mentioned if n not in allowed_chars]
        if outside:
            local.append(f"unprojected_character:{','.join(outside)}")
        # Location mentions: only the protagonist's/visible room and changed destinations.
        loc_hits = [l for l in sorted(all_locs, key=len, reverse=True) if l in sent]
        for loc in loc_hits:
            if loc not in allowed_locs:
                # A location used only as a movement destination is checked below.
                move_here = any(w in sent and loc in sent.split(w, 1)[-1][:8] for w in MOVE_WORDS)
                if not move_here:
                    local.append(f"unprojected_location:{loc}")
        # Position assertions for named characters.
        for name in mentioned:
            for loc in loc_hits:
                if re.search(rf"{re.escape(name)}[^。！？]{{0,8}}(?:在|位于|站在|坐在|靠在|走到|走进|走向|回到|来到|进入|离开){re.escape(loc)}", sent):
                    ok = loc in ancestors(after_pos.get(name, ""), locs) or loc in ancestors(before_pos.get(name, ""), locs)
                    if not ok:
                        local.append(f"wrong_position:{name}->{loc}")
                    elif after_pos.get(name) != before_pos.get(name) and loc in ancestors(after_pos.get(name, ""), locs):
                        covered_pos.add(name)
        # Task completion claims.
        for goal in sorted(all_goals, key=len, reverse=True):
            if goal and goal in sent and "完成" in sent and goal not in completed:
                local.append(f"task_not_completed:{goal}")
            if goal and goal in sent and goal in completed:
                covered_task.add(goal)
        # Hard events must be supported by a change or a mundane item action.
        for event in HARD_EVENTS:
            if event not in sent:
                continue
            if event in ("响", "喊", "叫", "哭", "枪响", "枪声", "敲门", "脚步声"):
                local.append(f"added_event:{event}")
                continue
            if event in MOVE_WORDS:
                if not any(n in sent and after_pos.get(n) != before_pos.get(n) for n in changed_pos):
                    local.append(f"movement_without_fact:{event}")
                continue
            obj_ok = any(item in sent for item in allowed_items)
            if obj_ok and event in ("拿起", "放下", "递给", "接过"):
                continue
            if any(goal in sent for goal in completed) and event in ("发现", "找到", "完成"):
                continue
            if any(goal in sent for goal in completed) and event in ("撕下", "撕掉", "掏出", "摸出"):
                continue
            if event in ("打开", "关上", "推开", "推门") and any(n in sent for n in changed_pos):
                continue
            local.append(f"added_event:{event}")
        # Numbers.
        for num in re.findall(r"[0-9]+", sent):
            if num not in number_facts and num not in {str(6), str(2), str(1)}:
                local.append(f"unverified_number:{num}")
        for phrase in re.findall(r"[一二三四五六七八九十百千万两]+(?:个人|人|分钟|秒|小时|岁|年|排|张|只|本|份|次|步)", sent):
            if phrase not in number_facts and phrase not in {"一个人", "两个人", "三个人", "四个人"}:
                local.append(f"unverified_number:{phrase}")
        # Backstory is allowed only when the exact word is in the state.
        for marker in ("十年前", "当年", "父亲", "母亲", "小时候", "以前"):
            if marker in sent and marker not in x_text and marker not in {"以前"}:
                local.append(f"unprojected_backstory:{marker}")
        if local:
            violations.append({"sentence": sent, "reasons": sorted(set(local))})
        else:
            kept.append(sent)
    # Coverage of changed positions and completed tasks.
    missing = []
    for name, loc in changed_pos.items():
        if name not in covered_pos and not any(name in s and (loc in s or (before_pos.get(name) and before_pos[name] in s)) for s in kept):
            missing.append(f"position:{name}->{loc}")
    for goal in completed:
        if goal not in covered_task and not any(goal in s for s in kept):
            missing.append(f"task:{goal}")
    return {
        "ok": not violations and not missing,
        "violations": violations,
        "missing": missing,
        "kept": kept,
        "filtered": "".join(s for s in kept),
        "changed_pos": changed_pos,
        "completed": list(completed),
        "before_pos": {n: before_pos[n] for n in changed_pos},
    }


if __name__ == "__main__":
    import sys
    path = sys.argv[1]
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    stats = {"rows": 0, "ok": 0, "sent": 0, "kept": 0, "chars": 0, "kept_chars": 0}
    examples = []
    for row in rows:
        r = check(row, row.get("yPlain", ""))
        stats["rows"] += 1
        stats["ok"] += int(r["ok"])
        sents = len(split_sentences(row.get("yPlain", "")))
        stats["sent"] += sents
        stats["kept"] += len(r["kept"])
        stats["chars"] += len(row.get("yPlain", ""))
        stats["kept_chars"] += len(r["filtered"])
        if len(examples) < 3 and r["violations"]:
            examples.append({"id": row["id"], "v": r["violations"][:5], "missing": r["missing"][:5]})
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    print(json.dumps(examples, ensure_ascii=False, indent=1))

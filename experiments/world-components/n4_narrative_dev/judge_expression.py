"""Mechanical per-unit judge for the routed-expression arms.

Four metrics are computed and reported SEPARATELY (never netted off):
  mustExpress   -- the fact's own content is expressed
  binding       -- subject name kept, fact object tokens kept, no other name
  repetition    -- literal duplicate span, or the same state said twice
  addition      -- action / object / state content not present in the fact

It is a vocabulary-driven mechanical judge, not a semantic gold standard.
Every flagged item is written out so it can be read back by hand.
"""
from __future__ import annotations

import re
import sys
import pathlib

PUNCT = re.compile(r"[\s，,。．.；;：:！!？?、…—－\-\"'“”‘’（）()《》「」]")

# body parts and scene objects that the material actually uses
OBJECT_TOKENS = [
    "袖口", "指节", "斗篷下摆", "衣领", "肩头", "帽檐", "鞋底", "鞋跟", "裤脚",
    "膝盖", "手背", "掌心", "指尖", "指缝", "鬓发", "鬓角", "脚踝", "背上",
    "腰侧", "前襟", "胸口", "下颌", "手肘", "发梢", "耳后", "下摆", "衣角",
    "围巾", "脸色", "额头", "手腕", "手", "脚",
    "灯罩", "铜灯", "潮汐簿", "钟绳", "警示灯", "渡船", "船灯", "鱼筐",
    "案板", "抹布", "干纸", "银鳞鱼", "油纸伞", "纸灯笼", "木板", "门槛",
    "长桌", "窗纸", "水缸", "墨", "鱼鳞", "盐沫", "水沫", "铜油", "盐霜",
    "灰", "泥",
]

EXTRA_ACTIONS = [
    "蹲", "站住", "停住", "抬头", "抬起头", "抱起", "松开手", "走过去",
    "低头", "叹气", "点头", "拽", "踩", "跨", "转过身", "回头",
]


def tokenize(text, vocab):
    """Longest match, left to right, no overlap: 铜灯罩 must not yield 灯罩+铜灯."""
    pairs = sorted(vocab, key=len, reverse=True)
    out, i = [], 0
    while i < len(text):
        hit = None
        for v in pairs:
            if text.startswith(v, i):
                hit = v
                break
        if hit:
            out.append(hit)
            i += len(hit)
        else:
            i += 1
    return out

EXTRA_STATES = [
    "绷直", "不再", "发暗", "扑到", "打滑", "紧绷",
]

# documented allowances (u240-clean-rate-retraction.md): psychological-state
# wording for a sanity fact and the standard no-change phrasing are legal.
SANITY_ALLOWED_BODY = ["呼吸", "手指", "胸口", "气", "手"]
NOCHANGE_ALLOWED = ["还亮着", "灯还亮着", "什么也没有再发生", "四下安静"]

ALIAS = {"潮汐档案馆": ["档案馆"], "潮渡": ["渡口", "栈桥"], "旧灯塔": ["灯塔"],
         "雾堤": ["堤面", "堤上"], "潮生巷": ["巷子"], "早市": ["集市"],
         "河心": ["河"], "灯寮": ["灯"]}

CHAR_NAMES = ["沈砚", "叶知微", "阿棠", "韩渡", "顾行舟", "林川", "周宁", "陈默"]


def n(s):
    return PUNCT.sub("", s or "")


def bigrams(s):
    s = n(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def coverage(key, text):
    b = bigrams(key)
    if not b:
        return 1.0
    return len(b & bigrams(text)) / len(b)


def fact_core(fact):
    kind = fact.get("kind")
    if kind == "moved":
        return f"{fact.get('from')}→{fact.get('to')}"
    if kind == "no_change":
        return ""
    if kind == "sanity_changed" and "to" in fact and "from" in fact:
        return f"{fact['from']}→{fact['to']}"
    return fact.get("resultText") or fact.get("text") or ""


def visible_of(input_text):
    m = re.search(r"地点可见=([^\n]+)", input_text or "")
    if not m:
        return []
    return [x for x in m.group(1).split("、") if x]


def seen_place(place, text):
    if not place:
        return False
    return place in text or any(x in text for x in ALIAS.get(place, []))


def judge_unit(fact, input_text, text):
    kind = fact.get("kind")
    core = fact_core(fact)
    name = fact.get("name") or ""
    vis = visible_of(input_text)
    t = text or ""

    # ---- mustExpress
    if kind == "no_change":
        ok = bool(re.search(r"(没有新的变化|没有新的事情|什么也没有再发生|没有别的动静"
                            r"|没有动静|没有动|四下安静)", t))
        must_note = "" if ok else "no-change cue missing"
    elif kind == "moved":
        a, b = fact.get("from"), fact.get("to")
        ok = seen_place(a, t) and seen_place(b, t)
        must_note = "" if ok else f"from={seen_place(a, t)} to={seen_place(b, t)}"
    elif kind == "sanity_changed" and "to" in fact and "from" in fact:
        up = fact["to"] > fact["from"]
        up_cues = ["松", "落回", "缓", "稳", "轻", "匀", "散"]
        down_cues = ["紧", "闷", "重", "抖", "冷", "屏"]
        ok = any(w in t for w in (up_cues if up else down_cues))
        must_note = "" if ok else "no direction cue"
    else:
        cov = coverage(core, t)
        ok = cov >= 0.5 and (not name or name in t)
        must_note = f"cov={cov:.2f}" + ("" if name in t else " name missing")

    # ---- binding
    obj_tokens = tokenize(core, OBJECT_TOKENS)
    missing_obj = [o for o in obj_tokens if o not in t]
    other_names = [c for c in CHAR_NAMES if c in t and c != name]
    binding_ok = (not name or name in t) and not missing_obj and not other_names
    binding_note = []
    if name and name not in t:
        binding_note.append(f"subject missing({name})")
    if missing_obj:
        binding_note.append("object replaced/missing(" + ",".join(missing_obj) + ")")
    if other_names:
        binding_note.append("other subject(" + ",".join(other_names) + ")")

    # ---- repetition (within this unit)
    literal = None
    spans = [s for s in re.split(r"[，,。．.；;]", t) if len(n(s)) >= 4]
    seen = {}
    for s in spans:
        key = n(s)
        if key in seen:
            literal = s
            break
        seen[key] = s
    semantic = None
    for o in obj_tokens:
        if n(t).count(n(o)) >= 2:
            semantic = o
            break
    if semantic is None and core:
        # same state head twice (e.g. 擦得透亮 / 透亮起来)
        heads = [core[i:i + 2] for i in range(max(0, len(core) - 1))]
        for h in heads:
            if len(h) == 2 and n(t).count(h) >= 2 and h not in ("了", "的"):
                semantic = h
                break
    repetition = bool(literal or semantic)

    # ---- addition
    extra_act = [v for v in EXTRA_ACTIONS if v in t and v not in core]
    allowed_objects = set(obj_tokens) | set(vis)
    extra_obj = [o for o in tokenize(t, OBJECT_TOKENS)
                 if o not in obj_tokens and o not in vis]
    if kind == "sanity_changed":
        extra_obj = [o for o in extra_obj
                     if not any(a in o or o in a for a in SANITY_ALLOWED_BODY)]
    if kind == "no_change":
        extra_obj = [o for o in extra_obj if o not in ("灯",)]
    extra_state = [w for w in EXTRA_STATES if w in t and w not in core]
    if kind == "no_change":
        extra_state = [w for w in extra_state
                       if not any(a in t for a in NOCHANGE_ALLOWED)]
    addition = bool(extra_act or extra_obj or extra_state)

    return {
        "mustExpress": bool(ok), "mustNote": must_note,
        "binding": bool(binding_ok), "bindingNote": "; ".join(binding_note),
        "repetition": repetition, "literalRepeat": literal, "semanticRepeat": semantic,
        "addition": addition, "extraAction": extra_act, "extraObject": extra_obj,
        "extraState": extra_state,
        "allowedObjects": sorted(allowed_objects),
    }


def judge_unit_row(row, text):
    """row: {'kind','fact','input'} — the frozen contract units."""
    return judge_unit(row["fact"], row.get("input", ""), text)


def judge_round_unit(unit, text, header_visible):
    fact = {"kind": unit["kind"], "name": unit["name"], "text": unit.get("text")}
    if unit["kind"] == "moved":
        fact.update({"from": unit.get("from") or unit.get("text"),
                     "to": unit.get("to") or unit.get("text")})
    inp = "地点可见=" + "、".join(header_visible)
    return judge_unit(fact, inp, text)


def summarize(results):
    total = len(results)
    return {
        "units": total,
        "mustExpress": sum(r["mustExpress"] for r in results),
        "binding": sum(r["binding"] for r in results),
        "repetition": sum(r["repetition"] for r in results),
        "addition": sum(r["addition"] for r in results),
        "extraAction": sum(1 for r in results if r["extraAction"]),
        "extraObject": sum(1 for r in results if r["extraObject"]),
        "extraState": sum(1 for r in results if r["extraState"]),
        "clean": sum(1 for r in results
                     if r["mustExpress"] and r["binding"]
                     and not r["repetition"] and not r["addition"]),
    }


def main():
    import json
    path = pathlib.Path(sys.argv[1])
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for arm, sets in doc.items():
        out[arm] = {}
        for setname, rows in sets.items():
            res = [judge_unit_row(r, r["text"]) for r in rows]
            out[arm][setname] = {"summary": summarize(res), "rows": res}
    print(json.dumps({a: {s: v["summary"] for s, v in sets.items()}
                      for a, sets in out.items()}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

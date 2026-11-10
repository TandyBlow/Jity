# -*- coding: utf-8 -*-
"""Freeze the shared public development package for lanes 11/12.

Inputs are copied verbatim from material that already exists and is already
public inside this project:

  * 01's short-scene corpus (01-authored, development only),
  * the frozen 199-row library corpus (train material, development only),
  * 05's tide-watch continuity scenes (05-authored, development only).

Nothing here is an independent final set. Every case records its source file,
row id and content hash so a reviewer can trace it. Texts are never rewritten;
05's older delta field shapes are normalized to the canonical
`视角/上回合状态/本回合变化/本回合状态` form without changing names, numbers or
events.
"""
import hashlib
import io
import json
import os

ROOT = "D:/others/Jity/.local/parallel-local-game"
WT = ROOT + "/worktrees/01-input"
OUT = WT + "/experiments/narration-quality/dev-package-v1"
SHORT = WT + "/experiments/narration-quality/corpus-short/rows.jsonl"
FROZEN = "D:/others/Jity/.local/world-components-worktree/experiments/world-components/narration-dataset-v1/rows-xy.jsonl"
TIDE = ROOT + "/worktrees/05-kernel/experiments/narration-quality/corpus-scenes/generated/rows.jsonl"


def sha256_file(path):
    digest = hashlib.sha256()
    with io.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


short_rows = {json.loads(line)["id"]: json.loads(line) for line in io.open(SHORT, encoding="utf-8")}
frozen_rows = {json.loads(line)["id"]: json.loads(line) for line in io.open(FROZEN, encoding="utf-8")}
tide_rows = {json.loads(line)["id"]: json.loads(line) for line in io.open(TIDE, encoding="utf-8")}


def normalize_required(facts):
    """Normalize 01's checklist into a consumer-checkable expression list."""
    out = []
    for fact in facts:
        kind = fact.get("kind")
        if kind == "time_advance":
            minutes = parse_minutes(fact.get("text", ""))
            out.append({"kind": "time_advance", "minutes": minutes, "summary": f"时间推进 {fact.get('text')}",
                        "expression": "state the settled elapsed time"})
        elif kind == "movement":
            out.append({"kind": "movement", "actor": fact.get("actor") or fact.get("entity"),
                        "from": fact.get("from"), "to": fact.get("to"),
                        "summary": f"{fact.get('actor') or fact.get('entity')}: {fact.get('from')} → {fact.get('to')}",
                        "expression": "actor reaches the settled destination; direction must not reverse"})
        elif kind in ("task_complete", "task_completed"):
            out.append({"kind": "task_complete", "owner": fact.get("owner"), "goal": fact.get("goal") or fact.get("task"),
                        "summary": f"{fact.get('owner')} 完成：{fact.get('goal') or fact.get('task')}",
                        "expression": "goal quoted, or its result described with a completion verb"})
        elif kind in ("sanity_change", "sanity"):
            out.append({"kind": "sanity_change", "owner": fact.get("owner") or fact.get("entity"),
                        "from": fact.get("from"), "to": fact.get("to"),
                        "summary": f"{fact.get('owner') or fact.get('entity')} 精神值 {fact.get('from')} → {fact.get('to')}",
                        "expression": "both numbers, or a direction-consistent reaction (needs review)"})
        elif kind in ("personality_change", "personality_added"):
            out.append({"kind": "personality_change", "owner": fact.get("owner"), "add": fact.get("add"),
                        "remove": fact.get("remove"),
                        "summary": f"{fact.get('owner')} 个性 +{fact.get('add')} -{fact.get('remove')}",
                        "expression": "trait text, or behaviour that shows it (needs review)"})
        elif kind == "item_state":
            out.append({"kind": "item_state", "item": fact.get("item"), "add": fact.get("add"), "remove": fact.get("remove"),
                        "summary": f"物品 {fact.get('item')} 状态变化",
                        "expression": "the object's new state; no extra object movement"})
        elif kind == "appearance_state":
            out.append({"kind": "appearance", "entity": fact.get("entity"), "add": fact.get("add"),
                        "summary": f"{fact.get('entity')} 外貌变化",
                        "expression": "optional; if stated it must match"})
        elif kind == "location_change":
            out.append({"kind": "place_change", "entity": fact.get("entity"), "add": fact.get("add"),
                        "summary": f"{fact.get('entity')} 环境变化",
                        "expression": "optional; if stated it must match"})
        elif kind == "task_added":
            out.append({"kind": "task_added", "owner": fact.get("owner"), "goal": fact.get("goal"),
                        "summary": f"{fact.get('owner')} 新增任务：{fact.get('goal')}",
                        "expression": "optional; must not be invented if absent"})
        elif kind == "separation":
            out.append({"kind": "separation", "summary": "人物分开", "expression": "optional"})
        else:
            out.append(dict(fact, expression=fact.get("expression", "review")))
    return out


CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def parse_minutes(text):
    text = (text or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return int(digits)
    value = 0
    current = 0
    for ch in text:
        if ch == "十":
            value += (current or 1) * 10
            current = 0
        elif ch in CN:
            current = CN[ch]
    return value + current or None


def licensed_entities(input_block):
    state = input_block.get("上回合状态", {})
    names = list((state.get("人物") or {}).keys()) + list((state.get("地点") or {}).keys()) + list((state.get("物品") or {}).keys())
    viewpoint = input_block.get("视角", "")
    if "（" in viewpoint:
        names.append(viewpoint.split("（")[1].split("）")[0])
    seen = []
    for name in sorted(set(names), key=len, reverse=True):
        if name not in seen:
            seen.append(name)
    return seen


def case_from_short(row_id, category, notes):
    row = short_rows[row_id]
    required = normalize_required(row.get("requiredFacts") or [])
    return {
        "caseId": row_id,
        "category": category,
        "worldFamily": row["worldFamily"],
        "source": {
            "kind": "01-authored-short-scene",
            "file": "worktrees/01-input/experiments/narration-quality/corpus-short/rows.jsonl",
            "rowId": row_id,
            "rowSha256": sha256_text(json.dumps(row["input"], ensure_ascii=False, sort_keys=True)),
            "author": "01-input",
            "independence": "development_only",
        },
        "viewpoint": row["input"].get("视角"),
        "input": row["input"],
        "requiredFacts": required,
        "licensedEntities": licensed_entities(row["input"]),
        "priorTexts": [],
        "reference": {
            "text": row["targetText"],
            "author": "01-input",
            "status": "development_reference",
            "reviewRecord": "experiments/narration-quality/corpus-short/review.md",
        },
        "notes": notes,
    }


cases = [
    case_from_short("dr-0021-no-change-three-people", "no_change",
                    "Settled point with no change except time: three people keep their places. Any move, posture or event is an addition."),
    case_from_short("short2-0034-carved-line-worn", "move_direction",
                    "One person moves 天台 → 天台楼梯间; the direction must not reverse and the viewpoint stays put."),
    case_from_short("dr-0003-task-goggles", "task_time",
                    "Task completion plus a settled item check; the elapsed time must be stated."),
    case_from_short("short2-0102-three-copies-collated", "multi_person_reference",
                    "Three named people in one scene; each clause must keep its own actor."),
    case_from_short("dr-0019-tomiyama-shen-symptom", "sanity",
                    "Sanity 41 → 46 shown through a conversation; the viewpoint cannot read the other person's mind."),
    case_from_short("short2-0031-binding-glue-and-tape", "appearance_item",
                    "Appearance change on a person and an object; no story event is settled."),
    case_from_short("dr-0018-fingel-tells-hatch", "dialogue",
                    "A task completed by telling someone a fact; the stated content is settled, further claims are not."),
    case_from_short("short2-0056-duty-name-and-copy", "gender_pronoun",
                    "Two people with similar names; the pronoun and the actor must stay with the right person."),
    case_from_short("short-0008-two-minute-no-change", "time_only_derived",
                    "Time-only contrast row derived from row-0008; only the elapsed time differs from the base row."),
    case_from_short("short2-0129-film-version-and-fear", "task_sanity",
                    "Task completion plus a sanity drop in the same short scene."),
]

# ---------------------------------------------------------------- frozen row
frozen = frozen_rows["row-0012"]
cases.append({
    "caseId": "frozen-row-0012",
    "category": "long_text",
    "worldFamily": "library-frozen-train",
    "source": {
        "kind": "frozen-199-train-row",
        "file": "world-components-worktree/experiments/world-components/narration-dataset-v1/rows-xy.jsonl",
        "rowId": "row-0012",
        "rowSha256": sha256_text(json.dumps(frozen["x"], ensure_ascii=False, sort_keys=True)),
        "author": "world-components dataset (pre-01)",
        "independence": "development_only_train_material",
    },
    "viewpoint": frozen["x"].get("视角"),
    "input": frozen["x"],
    "requiredFacts": [
        {"kind": "time_advance", "minutes": parse_minutes(frozen["x"]["本回合变化"]["时间推进"]),
         "summary": "时间推进 " + frozen["x"]["本回合变化"]["时间推进"], "expression": "state the settled elapsed time"},
        {"kind": "movement", "actor": "温执", "from": "借阅台", "to": "还书处",
         "summary": "温执: 借阅台 → 还书处", "expression": "actor reaches the settled destination"},
        {"kind": "personality_change", "owner": "黎知微", "add": "答应替温执留一只没登记过的旧箱",
         "summary": "黎知微 新增个性", "expression": "trait text or behaviour (needs review)"},
        {"kind": "item_state", "item": "铁皮还书箱", "add": "箱底垫了一块木板", "remove": "箱底锈穿了一个洞",
         "summary": "铁皮还书箱 箱底变化", "expression": "the object's new state"},
    ],
    "licensedEntities": licensed_entities(frozen["x"]),
    "priorTexts": [],
    "reference": {
        "text": frozen["y"],
        "author": "world-components dataset",
        "status": "development_reference_only",
        "warning": "Known supervision gaps: the old text never states the elapsed time and adds unfounded footsteps.",
    },
    "notes": "Long dialogue-heavy library scene. Used for length/dialogue behaviour, not as a time-expression or move-coverage reference.",
    "knownIssues": ["The reference text never states the elapsed time (198/199 frozen rows share this gap).", "The reference adds footsteps with no settled move."],
})


# ------------------------------------------------------------ 05 continuity
def normalize_tide_delta(input_block):
    """05's older delta shape -> canonical arrays/status, content unchanged."""
    block = json.loads(json.dumps(input_block))
    delta = block["本回合变化"]
    changes = delta.get("变化") or {}
    for name, change in list(changes.items()):
        if isinstance(change.get("新增个性"), str):
            change["新增个性"] = [change["新增个性"]]
        if isinstance(change.get("解除个性"), str):
            change["解除个性"] = [change["解除个性"]]
        completed = change.pop("完成任务", None)
        if completed:
            before = block["上回合状态"].get("人物", {}).get(name, {})
            tasks = before.get("任务") or {}
            big = tasks.get("大任务")
            small = tasks.get("小任务") or []
            goals = set(completed if isinstance(completed, list) else [completed])
            new_tasks = {"小任务": [
                {"目标": task["目标"], "状态": "已完成" if task["目标"] in goals else task.get("状态", "未完成")}
                for task in small
            ]}
            if big:
                new_tasks["大任务"] = big
            change["任务"] = new_tasks
    if "时间推进" in changes:
        delta["时间推进"] = changes.pop("时间推进")
    return block


tide_prior = []
for turn in ("tide-duty-t1", "tide-duty-t2", "tide-duty-t3"):
    row = tide_rows[turn]
    normalized = normalize_tide_delta(row["input"])
    cases.append({
        "caseId": "tide-continuity-" + turn,
        "category": "continuity",
        "worldFamily": "tide-watch-1998",
        "source": {
            "kind": "05-authored-continuity",
            "file": "worktrees/05-kernel/experiments/narration-quality/corpus-scenes/generated/rows.jsonl",
            "rowId": turn,
            "rowSha256": sha256_text(json.dumps(row["input"], ensure_ascii=False, sort_keys=True)),
            "author": "05-kernel",
            "independence": "development_only",
            "normalization": "05 delta shape (新增个性 string / 完成任务 list / 时间推进 inside 变化) normalized to canonical arrays and task statuses; names, numbers and events unchanged",
        },
        "viewpoint": row["input"].get("视角"),
        "input": normalized,
        "requiredFacts": normalize_required([
            {"kind": "time_advance", "text": (row["input"]["本回合变化"].get("变化") or {}).get("时间推进")
             or row["input"]["本回合变化"].get("时间推进") or ""}]),
        "licensedEntities": licensed_entities(normalized),
        "priorTexts": list(tide_prior),
        "reference": {
            "text": row["targetText"],
            "author": "05-kernel",
            "status": "development_reference",
        },
        "notes": "Turn %s of a three-turn sequence; priorTexts is what the same model wrote earlier, used for cross-turn repetition and continuity checks." % turn[-1],
        "knownIssues": () if turn != "tide-duty-t1" else ["The reference has an unbound footstep sound (一串脚步声) although nobody moved this point; reported to 05."],
    })
    tide_prior.append(row["targetText"])

# ------------------------------------------------------- item transfer case
transfer = case_from_short("dr-0003-task-goggles", "item_transfer_fixture",
                           "Placeholder replaced below.")
transfer["caseId"] = "fixture-goggles-transfer"
transfer["source"] = {
    "kind": "01-authored-fixture",
    "file": "frontend/public/worlds/dragon-raja-free-day.world.json",
    "worldSha256": sha256_file(WT + "/frontend/public/worlds/dragon-raja-free-day.world.json"),
    "author": "01-input",
    "independence": "development_only",
}
transfer["input"] = {
    "视角": "主角视角（路明非）；只表达已结算的世界事实",
    "上回合状态": {
        "地点": {"西侧服务巷": {"位于": None, "外貌": ["巷口的黄黑绳已放下，右墙贴着赛区图。"]}},
        "人物": {
            "路明非": {"位置": "西侧服务巷", "精神值": 43, "外貌": ["护目镜挂在胸前，右手还空着"], "个性": ["习惯先用一句玩笑替自己解围"],
                       "任务": {"大任务": {"目标": "在自由一日结束前作出自己的参赛选择", "状态": "未完成"}, "小任务": []}},
            "诺诺": {"位置": "西侧服务巷", "精神值": 58, "外貌": ["红发用发圈束在脑后，红色识别带缠在左臂，手里没有东西"], "个性": ["看人时比听解释更有耐心"],
                     "任务": {"大任务": {"目标": "让红方的旗台行动有可执行的掩护", "状态": "未完成"}, "小任务": []}},
        },
        "物品": {"路明非的护目镜": {"位置": "路明非", "外貌": ["镜片无裂纹，镜带松着"]}},
    },
    "本回合变化": {
        "时间推进": "1 分钟",
        "变化": {
            "路明非的护目镜": {"位置": "诺诺"},
            "路明非": {"外貌": ["右手空着"]},
            "诺诺": {"外貌": ["护目镜拿在手里"]},
        },
    },
    "本回合状态": {
        "路明非的护目镜": {"位置": "诺诺"},
        "路明非": {"外貌": ["护目镜挂在胸前，右手还空着", "右手空着"]},
        "诺诺": {"外貌": ["红发用发圈束在脑后，红色识别带缠在左臂，手里没有东西", "护目镜拿在手里"]},
    },
}
transfer["requiredFacts"] = [
    {"kind": "time_advance", "minutes": 1, "summary": "时间推进 1 分钟", "expression": "state the settled elapsed time"},
    {"kind": "item_transfer", "item": "路明非的护目镜", "from": "路明非", "to": "诺诺",
     "summary": "护目镜 路明非 → 诺诺", "expression": "the object ends up with 诺诺, not with anyone else"},
]
transfer["licensedEntities"] = licensed_entities(transfer["input"])
transfer["reference"] = {
    "text": "一分钟过去，路明非把护目镜从胸前摘下来，递到诺诺手里。镜带还松着，镜片没有裂纹。诺诺接过去，顺手把镜带绕在手腕上，红色识别带还缠在左臂。",
    "author": "01-input",
    "status": "development_reference",
}
transfer["notes"] = "The only settled change is an item moving from 路明非 to 诺诺. Writing it as 诺诺 handing it to him, or as a scene object floating in the lane, is a contradiction."
cases.append(transfer)

os.makedirs(OUT, exist_ok=True)
with io.open(OUT + "/cases.jsonl", "w", encoding="utf-8", newline="\n") as handle:
    for case in cases:
        handle.write(json.dumps(case, ensure_ascii=False) + "\n")

manifest = {
    "package": "narration-dev-package-v1",
    "frozenAt": "2026-11-10",
    "owner": "01-input",
    "status": "public_development_regression_not_final",
    "purpose": "One shared settled-input package for lanes 11/12 (and any candidate comparison) so results are comparable without building another platform.",
    "caseCount": len(cases),
    "categories": sorted({case["category"] for case in cases}),
    "inputs": {
        "shortCorpus": {"path": "worktrees/01-input/experiments/narration-quality/corpus-short/rows.jsonl", "sha256": sha256_file(SHORT)},
        "frozen199": {"path": FROZEN, "sha256": sha256_file(FROZEN)},
        "tideScenes": {"path": TIDE, "sha256": sha256_file(TIDE)},
        "world": {"path": "worktrees/01-input/frontend/public/worlds/dragon-raja-free-day.world.json",
                  "sha256": sha256_file(WT + "/frontend/public/worlds/dragon-raja-free-day.world.json")},
    },
    "cases": [
        {"caseId": case["caseId"], "category": case["category"], "worldFamily": case["worldFamily"],
         "knownIssues": case.get("knownIssues", []),
         "inputSha256": sha256_text(json.dumps(case["input"], ensure_ascii=False, sort_keys=True)),
         "referenceSha256": sha256_text(case["reference"]["text"]),
         "priorTextCount": len(case["priorTexts"])}
        for case in cases
    ],
    "files": {
        "cases.jsonl": sha256_file(OUT + "/cases.jsonl"),
    },
    "rubric": "RUBRIC.md",
    "checkerReference": "frontend/src/lib/world-engine/local/narration-quality/ (reviewNarration) and its batch harness",
    "independence": {
        "finalSet": False,
        "reason": "All cases are public development material: 01/05 authored scenes, frozen train rows, or a 01-authored fixture. They can never become the independent final set, and changing the reviewer does not change that.",
        "authors": ["01-input", "05-kernel", "world-components dataset"],
    },
}
with io.open(OUT + "/manifest.json", "w", encoding="utf-8", newline="\n") as handle:
    json.dump(manifest, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print("cases", len(cases), "sha", manifest["files"]["cases.jsonl"][:16])

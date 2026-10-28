# N4 corpus seed builder: program-enumerated fact plans + template-seed rows.
#
# Protocol: experiments/world-components/n4_corpus/corpus_protocol.md
# - plans are constructed INDEPENDENTLY (program enumeration, not state
#   differencing); construction/validation records ride on every row
# - vocabulary is brand new (asserted zero overlap with B cast words)
# - empty-point template deliberately avoids B's 「没有新的变化」 phrase
#   (smoke-probe lesson) and B's mechanical clause pattern stays inside
#   template-seed rows only (registered as template method, not derivation)
#
# Usage: python experiments/world-components/n4_corpus/build_seeds.py
# Output: experiments/world-components/n4_corpus/corpus.seeds.jsonl (seeds only;
# rewrite rows live in rewrites.jsonl so reruns never clobber them)

import hashlib
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "corpus.seeds.jsonl"

NAMES = ["陈舟", "苏晚", "周砚", "林望", "沈青"]
LOCS = ["东门", "水房", "钟楼", "侧院", "柴房", "石桥", "碑亭"]
ITEMS = ["铜铃", "木匣", "青瓷碗", "油纸伞"]
GOALS = ["把铜铃挂回钟楼", "整理柴房", "修缮石桥栏杆", "清点碑亭石刻"]
DURATIONS = [(3, "minute", "三分钟"), (8, "minute", "八分钟"),
             (12, "minute", "十二分钟"), (25, "minute", "二十五分钟"),
             (40, "minute", "四十分钟"), (1, "hour", "一小时")]
APPEARANCES = ["门柱上的漆皮剥落了大半", "石阶缝里长出了青苔"]
PERSONALITIES = ["变得沉稳", "话多了起来"]

# B cast words that must not appear in the new vocabulary (names/locations
# from narration-eval samples, validation samples and b3 world).
B_CAST = {"学生A", "学生B", "学生C", "学生D", "主角", "老师", "走廊", "大厅",
          "门厅", "教室", "食堂", "操场", "宿舍", "图书馆", "钥匙", "柜子",
          "书架", "暗门", "雕像", "铜钥匙", "校徽", "旧笔记", "二楼档案室"}

SANITY_PAIRS = [(11, 13), (9, 14), (15, 12)]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def plan_hash(plan: list) -> str:
    return hashlib.sha256(
        json.dumps(plan, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def row(group: str, origin: str, rewriter: str, split: str, plan: list,
        text: str, plan_refs: list, must: list, may: list, no_add: str,
        purpose: str) -> dict:
    return {
        "sourceGroupId": group,
        "rowOrigin": origin,
        "rewriter": rewriter,
        "task": "n4-sentence",
        "split": split,
        "plan": plan,
        "planConstruction": {"method": "program-enum-v1",
                             "note": "程序枚举独立构造，非状态差分反推"},
        "planValidation": {
            "authority": "validate_plan_authority.py -> authority-report.json",
            "note": "行内字段仅为构造声明；权威校验由独立脚本把 plan 映射为 backend "
                    "v2 EntityDelta/TimeAdvance 并经 pydantic 逐行执行，结果落 "
                    "authority-report.json（含 contracts.py 源哈希与草稿键映射）"},
        "text": text,
        "planRefs": plan_refs,
        "mustExpress": must,
        "mayMention": may,
        "mustNotAdd": no_add,
        "hashes": {"plan": plan_hash(plan), "text": sha(text)},
        "purpose": purpose,
    }


def moved(name, frm, to):
    return {"kind": "moved", "entityId": f"c_{name}", "name": name,
            "from": frm, "to": to}


def time_f(i):
    amount, unit, cn = DURATIONS[i % len(DURATIONS)]
    return {"kind": "time", "amount": amount, "unit": unit, "rendered": cn}


NO_ADD_STD = "不得新增：其他实体的动作、对话、评价、未登记实体"

rows = []
g = 0

# --- family 1: movement + time (6 groups, train) ---
for i in range(6):
    g += 1
    name = NAMES[i % len(NAMES)]
    frm, to = LOCS[i % len(LOCS)], LOCS[(i + 2) % len(LOCS)]
    plan = [{"ref": 0, **moved(name, frm, to)}, {"ref": 1, **time_f(i)}]
    text = f"{name}从{frm}来到{to}。前后大约{DURATIONS[i % len(DURATIONS)][2]}。"
    rows.append(row(f"n4-loc-{g:03d}", "template-seed", "program", "train", plan,
                    text, [[0], [1]], [0, 1], [], NO_ADD_STD,
                    "N4 成句微调：位置事实＋时间句"))

# --- family 2: empty point + time (4 groups, train) ---
# v2: 空点行不再对具体地点作"一切如旧"主张（无计划支持）——plan 补 no_change
# 全局条目，正文去掉具体地点名，校验器禁 no_change 句出现实体名。
for i in range(4):
    g += 1
    dur = DURATIONS[(i + 1) % len(DURATIONS)]
    plan = [{"ref": 0, **time_f(i + 1)},
            {"ref": 1, "kind": "no_change", "scope": "全局"}]
    text = f"大约{dur[2]}过去了，一切如旧。"
    rows.append(row(f"n4-empty-{g:03d}", "template-seed", "program", "train", plan,
                    text, [[0, 1]], [0, 1], [], NO_ADD_STD,
                    "N4 成句微调：空点＋时间（无实体主张；句式避开 B 空点模板短语）"))

# --- family 3: task achieved + time (5 groups, train) ---
for i in range(5):
    g += 1
    name = NAMES[(i + 1) % len(NAMES)]
    goal = GOALS[i % len(GOALS)]
    plan = [{"ref": 0, "kind": "task_achieved", "entityId": f"c_{name}",
             "name": name, "goal": goal},
            {"ref": 1, **time_f(i + 2)}]
    text = f"{name}完成了任务「{goal}」。前后大约{DURATIONS[(i + 2) % len(DURATIONS)][2]}。"
    rows.append(row(f"n4-task-{g:03d}", "template-seed", "program", "train", plan,
                    text, [[0], [1]], [0, 1], [], NO_ADD_STD,
                    "N4 成句微调：任务达成＋引语逐字保留"))

# --- family 4: task -> personality -> sanity chain (3 groups, train) ---
for i in range(3):
    g += 1
    name = NAMES[(i + 2) % len(NAMES)]
    goal = GOALS[(i + 1) % len(GOALS)]
    lo, hi = SANITY_PAIRS[i]
    pers = PERSONALITIES[i % len(PERSONALITIES)]
    # v2: 方向动词按数据渲染（15→12 是下降，写"升到了"是错误监督）
    sanity_verb = "升到了" if hi > lo else "降到了"
    plan = [
        {"ref": 0, "kind": "task_achieved", "entityId": f"c_{name}", "name": name, "goal": goal},
        {"ref": 1, "kind": "personality_changed", "entityId": f"c_{name}", "name": name, "text": pers},
        {"ref": 2, "kind": "sanity_changed", "entityId": f"c_{name}", "name": name,
         "from": lo, "to": hi},
        {"ref": 3, **time_f(i + 3)},
    ]
    text = (f"{name}完成了任务「{goal}」，{pers}，"
            f"精神值从{lo}{sanity_verb}{hi}。前后大约{DURATIONS[(i + 3) % len(DURATIONS)][2]}。")
    rows.append(row(f"n4-chain-{g:03d}", "template-seed", "program", "train", plan,
                    text, [[0, 1, 2], [3]], [0, 1, 2, 3], [], NO_ADD_STD,
                    "N4 成句微调：任务→人格→理智联动一文体"))

# --- family 5: appearance + time (3 groups, train) ---
for i in range(3):
    g += 1
    loc = LOCS[(i + 5) % len(LOCS)]
    desc = APPEARANCES[i % len(APPEARANCES)]
    plan = [{"ref": 0, "kind": "appearance_changed", "entityId": f"l_{loc}",
             "name": loc, "text": desc},
            {"ref": 1, **time_f(i + 4)}]
    text = f"{loc}的外观变了：{desc}。前后大约{DURATIONS[(i + 4) % len(DURATIONS)][2]}。"
    rows.append(row(f"n4-appear-{g:03d}", "template-seed", "program", "train", plan,
                    text, [[0], [1]], [0, 1], [], NO_ADD_STD,
                    "N4 成句微调：地点外貌（B 投影不支持面，接口表待办）"))

# --- family 6: two entities one sentence (3 groups, train) ---
for i in range(3):
    g += 1
    n1, n2 = NAMES[i % len(NAMES)], NAMES[(i + 3) % len(NAMES)]
    frm, to = LOCS[(i + 1) % len(LOCS)], LOCS[(i + 4) % len(LOCS)]
    plan = [{"ref": 0, **moved(n1, frm, to)},
            {"ref": 1, "kind": "positioned_at", "entityId": f"c_{n2}",
             "name": n2, "at": to},
            {"ref": 2, **time_f(i)}]
    text = (f"{n1}从{frm}来到{to}时，{n2}已经在{to}了。"
            f"前后大约{DURATIONS[i % len(DURATIONS)][2]}。")
    rows.append(row(f"n4-multi-{g:03d}", "template-seed", "program", "train", plan,
                    text, [[0, 1], [2]], [0, 1, 2], [], NO_ADD_STD,
                    "N4 成句微调：同点多人物＋现状陈述"))

# --- 2 dev groups (held out from the start, same families 1 and 3) ---
g += 1
name, frm, to = NAMES[4], LOCS[6], LOCS[0]
plan = [{"ref": 0, **moved(name, frm, to)}, {"ref": 1, **time_f(5)}]
text = f"{name}从{frm}来到{to}。前后大约{DURATIONS[5][2]}。"
rows.append(row(f"n4-loc-{g:03d}", "template-seed", "program", "dev", plan,
                text, [[0], [1]], [0, 1], [], NO_ADD_STD,
                "N4 开发验收（组级隔离，构造起即 dev）"))
g += 1
name, goal = NAMES[3], GOALS[3]
plan = [{"ref": 0, "kind": "task_achieved", "entityId": f"c_{name}",
         "name": name, "goal": goal},
        {"ref": 1, **time_f(0)}]
text = f"{name}完成了任务「{goal}」。前后大约{DURATIONS[0][2]}。"
rows.append(row(f"n4-task-{g:03d}", "template-seed", "program", "dev", plan,
                text, [[0], [1]], [0, 1], [], NO_ADD_STD,
                "N4 开发验收（组级隔离，构造起即 dev）"))

# vocabulary guard: assert new-vocab rows never touch B cast words
for r in rows:
    for word in B_CAST:
        if word in r["text"]:
            raise SystemExit(f"CAST CROSSING: {word} in {r['sourceGroupId']}: {r['text']}")

OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
               encoding="utf-8")
print(f"wrote {len(rows)} seed rows -> {OUT}")
for prefix in ["n4-loc", "n4-empty", "n4-task", "n4-chain", "n4-appear", "n4-multi"]:
    n = sum(1 for r in rows if r["sourceGroupId"].startswith(prefix))
    print(f"  {prefix}: {n}")

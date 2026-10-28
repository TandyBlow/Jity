# N4 corpus seed builder v3: program-enumerated worlds + raw deltas + plans.
#
# v3 (2026-10-29 review): plans are no longer the primary artifact. Each row
# now carries INDEPENDENTLY CONSTRUCTED before-state registry (`world`) and
# raw delta (`rawDelta`); `plan` is a PROJECTION of the delta produced by the
# same generator, so plan and delta are same-source by construction and the
# delta is the authoritative input for apply-based validation.
#
# Protocol: corpus_protocol.md. Vocabulary stays brand new; the empty-point
# template still avoids B's phrase; rows are grouped by sourceGroupId with
# group-level split.
#
# Usage: python experiments/world-components/n4_corpus/build_seeds.py
# Output: experiments/world-components/n4_corpus/corpus.seeds.jsonl

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "corpus.seeds.jsonl"

# Structured world registry (draft ids are program-assigned, v2 Id is ASCII).
LOCS = [("loc_001", "东门"), ("loc_002", "水房"), ("loc_003", "钟楼"),
        ("loc_004", "侧院"), ("loc_005", "柴房"), ("loc_006", "石桥"),
        ("loc_007", "碑亭")]
LOC_NAME = {lid: name for lid, name in LOCS}
LOC_ID = {name: lid for lid, name in LOCS}
# char: id, name, home loc, initial sanity, personality, tasks [(id, goal)]
CHARS = [
    ("char_001", "陈舟", "loc_001", 10, "谨慎", [("task_001", "把铜铃挂回钟楼")]),
    ("char_002", "苏晚", "loc_002", 10, "外向", [("task_002", "整理柴房")]),
    ("char_003", "周砚", "loc_003", 12, "沉默", [("task_003", "修缮石桥栏杆")]),
    ("char_004", "林望", "loc_004", 11, "急躁", [("task_004", "清点碑亭石刻")]),
    ("char_005", "沈青", "loc_005", 9, "细心", []),
]
CHAR_BY_NAME = {name: (cid, home, sanity, pers, tasks)
                for cid, name, home, sanity, pers, tasks in CHARS}
GOAL_TO_TASK = {goal: tid for *_x, tasks in CHARS for tid, goal in tasks}
TASK_OF = {}
for _cid, _n, _h, _s, _p, _t in CHARS:
    if _t:
        TASK_OF[_n] = _t[0][1]
TASK_OWNERS = list(TASK_OF)  # 陈舟/苏晚/周砚/林望（沈青无任务）

DURATIONS = [(3, "minute", "三分钟"), (8, "minute", "八分钟"),
             (12, "minute", "十二分钟"), (25, "minute", "二十五分钟"),
             (40, "minute", "四十分钟"), (1, "hour", "一小时")]

B_CAST = {"学生A", "学生B", "学生C", "学生D", "主角", "老师", "走廊", "大厅",
          "门厅", "教室", "食堂", "操场", "宿舍", "图书馆", "钥匙", "柜子",
          "书架", "暗门", "雕像", "铜钥匙", "校徽", "旧笔记", "二楼档案室"}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def make_world(char_names: list, loc_names: list) -> dict:
    """Minimal before-state registry: only entities this row needs. The v2
    initial-state contract requires >=1 location and the protagonist on the
    roster, so an empty location list falls back to the first character's
    home."""
    if not loc_names and char_names:
        loc_names = [LOC_NAME[CHAR_BY_NAME[char_names[0]][1]]]
    # every character's home must be on the registry too (before state
    # positions reference it; the initial-state validator rejects unknown
    # containers)
    for n in char_names:
        home = LOC_NAME[CHAR_BY_NAME[n][1]]
        if home not in loc_names:
            loc_names = [*loc_names, home]
    locs = [{"id": LOC_ID[n], "name": n} for n in loc_names]
    chars = []
    for n in char_names:
        cid, home, sanity, pers, tasks = CHAR_BY_NAME[n]
        chars.append({
            "id": cid, "name": n, "homeLocId": home, "initialSanity": sanity,
            "initialPersonality": pers,
            "tasks": [{"id": tid, "goal": g, "ownerId": cid} for tid, g in tasks],
        })
    protagonist = CHAR_BY_NAME[char_names[0]][0] if char_names else "char_001"
    return {"protagonistId": protagonist, "locations": locs, "characters": chars}


def moved_delta(cid, to_loc):
    return {"entityId": cid, "positionSet": {"containerId": LOC_ID[to_loc]}}


def task_delta(cid, goal):
    return {"entityId": cid, "tasksAchieved": [GOAL_TO_TASK[goal]]}


def sanity_delta(cid, to):
    return {"entityId": cid, "sanitySet": to}


def personality_delta(cid, chg_id, text):
    return {"entityId": cid,
            "personalityChanges": [{"id": chg_id, "text": text, "supersedes": []}]}


def appearance_delta(loc_name, chg_id, text):
    return {"entityId": LOC_ID[loc_name],
            "appearanceChanges": [{"id": chg_id, "text": text, "supersedes": []}]}


def project_plan(deltas: list, time_entry: dict | None,
                 claims: list | None = None) -> list:
    """Plan is a projection of the raw delta (same-source by construction)."""
    plan = []
    ref = 0
    for d in deltas:
        eid, cid, name = d["entityId"], d["entityId"], None
        if "positionSet" in d:
            to = LOC_NAME[d["positionSet"]["containerId"]]
            name = next(n for n, (c, *_rest) in
                        ((cn, CHAR_BY_NAME[cn]) for cn in CHAR_BY_NAME)
                        if c == eid)
            frm = CHAR_BY_NAME[name][1]
            plan.append({"ref": ref, "kind": "moved", "entityId": eid, "name": name,
                         "from": LOC_NAME[frm], "to": to})
            ref += 1
        elif "tasksAchieved" in d:
            goal = next(g for g, t in GOAL_TO_TASK.items() if t == d["tasksAchieved"][0])
            name = next(n for n in CHAR_BY_NAME
                        if CHAR_BY_NAME[n][0] == eid)
            plan.append({"ref": ref, "kind": "task_achieved", "entityId": eid,
                         "name": name, "goal": goal})
            ref += 1
        elif "sanitySet" in d:
            name = next(n for n in CHAR_BY_NAME if CHAR_BY_NAME[n][0] == eid)
            before = CHAR_BY_NAME[name][2]
            plan.append({"ref": ref, "kind": "sanity_changed", "entityId": eid,
                         "name": name, "from": before, "to": d["sanitySet"]})
            ref += 1
        elif "personalityChanges" in d:
            name = next(n for n in CHAR_BY_NAME if CHAR_BY_NAME[n][0] == eid)
            plan.append({"ref": ref, "kind": "personality_changed", "entityId": eid,
                         "name": name, "text": d["personalityChanges"][0]["text"]})
            ref += 1
        elif "appearanceChanges" in d:
            name = LOC_NAME[d["entityId"]]
            plan.append({"ref": ref, "kind": "appearance_changed",
                         "entityId": d["entityId"], "name": name,
                         "text": d["appearanceChanges"][0]["text"]})
            ref += 1
    for p in [c for c in (claims or []) if c["kind"] == "positioned_at"]:
        plan.append({"ref": ref, "kind": "positioned_at", "entityId": p["entityId"],
                     "name": p["name"], "at": p["at"]})
        ref += 1
    if time_entry is not None:
        plan.append({"ref": ref, "kind": "time", **time_entry})
        ref += 1
    for c in [c for c in (claims or []) if c["kind"] == "no_change"]:
        plan.append({"ref": ref, "kind": "no_change", **{k: v for k, v in c.items() if k != "kind"}})
        ref += 1
    return plan


NO_ADD_STD = "不得新增：其他实体的动作、对话、评价、未登记实体"

rows = []
g = 0


def row(group, origin, rewriter, split, world, deltas, time_entry, text,
        refs, must, may, no_add, purpose, claims=None):
    plan = project_plan(deltas, time_entry, claims)
    return {
        "sourceGroupId": group,
        "rowOrigin": origin,
        "rewriter": rewriter,
        "task": "n4-sentence",
        "split": split,
        "world": world,
        "rawDelta": {"entityDeltas": deltas, "time": time_entry},
        "plan": plan,
        "planOnlyClaims": claims or [],
        "planConstruction": {"method": "program-enum-v3",
                             "note": "world 与 rawDelta 独立构造；plan 为同一生成器对 rawDelta 的投影"},
        "planValidation": {
            "authority": "validate_plan_authority.py -> authority-report.json",
            "note": "权威校验=A 侧 kernel apply_point 把 rawDelta 应用到 world 构造的 before 状态，"
                    "并核对起点/旧值/任务归属/现状/空增量与 after 值；报告含 server 树 HEAD 与 kernel 哈希"},
        "text": text,
        "planRefs": refs,
        "mustExpress": must,
        "mayMention": may,
        "mustNotAdd": no_add,
        "hashes": {
            "plan": hashlib.sha256(canon(plan).encode("utf-8")).hexdigest(),
            "world": hashlib.sha256(canon(world).encode("utf-8")).hexdigest(),
            "rawDelta": hashlib.sha256(canon({"entityDeltas": deltas, "time": time_entry}).encode("utf-8")).hexdigest(),
            "text": sha(text),
        },
        "purpose": purpose,
    }


# --- family 1: movement + time (6 groups, train) ---
for i in range(6):
    g += 1
    name = list(CHAR_BY_NAME)[i % 5]
    cid = CHAR_BY_NAME[name][0]
    frm_name = LOC_NAME[CHAR_BY_NAME[name][1]]
    to_name = LOCS[(i + 2) % 7][1]
    dur = DURATIONS[i % 6]
    world = make_world([name], [frm_name, to_name])
    deltas = [moved_delta(cid, to_name)]
    time_entry = {"amount": dur[0], "unit": dur[1], "rendered": dur[2]}
    text = f"{name}从{frm_name}来到{to_name}。前后大约{dur[2]}。"
    rows.append(row(f"n4-loc-{g:03d}", "template-seed", "program", "train",
                    world, deltas, time_entry, text, [[0], [1]], [0, 1], [],
                    NO_ADD_STD, "N4 成句微调：位置事实＋时间句"))

# --- family 2: empty point + time (4 groups, train) ---
# v3: before world must be a legal minimal world (one location + protagonist)
# so the Python authority can build a before state; the delta stays empty.
for i in range(4):
    g += 1
    dur = DURATIONS[(i + 1) % 6]
    world = make_world(["陈舟"], ["东门"])
    deltas = []
    time_entry = {"amount": dur[0], "unit": dur[1], "rendered": dur[2]}
    text = f"大约{dur[2]}过去了，一切如旧。"
    rows.append(row(f"n4-empty-{g:03d}", "template-seed", "program", "train",
                    world, deltas, time_entry, text, [[0, 1]], [0, 1], [],
                    NO_ADD_STD,
                    "N4 成句微调：空点＋时间（无实体主张；句式避开 B 空点模板短语）",
                    claims=[{"kind": "no_change", "scope": "全局"}]))

# --- family 3: task achieved + time (5 groups, train) ---
# v3: the goal must be the mover's OWN registered task (provenance check
# caught the v2 generator assigning other people's tasks).
for i in range(5):
    g += 1
    name = TASK_OWNERS[i % len(TASK_OWNERS)]
    cid = CHAR_BY_NAME[name][0]
    goal = TASK_OF[name]
    dur = DURATIONS[(i + 2) % 6]
    world = make_world([name], [])
    deltas = [task_delta(cid, goal)]
    time_entry = {"amount": dur[0], "unit": dur[1], "rendered": dur[2]}
    text = f"{name}完成了任务「{goal}」。前后大约{dur[2]}。"
    rows.append(row(f"n4-task-{g:03d}", "template-seed", "program", "train",
                    world, deltas, time_entry, text, [[0], [1]], [0, 1], [],
                    NO_ADD_STD, "N4 成句微调：任务达成＋引语逐字保留"))

# --- family 4: task -> personality -> sanity chain (3 groups, train) ---
# v3: sanity from-value comes from the world registry (before is the
# authority); CHAIN_SANITY only declares the target value.
CHAIN_SANITY = [13, 14, 12]
PERSONALITIES = ["变得沉稳", "话多了起来", "变得内敛"]  # 内敛: hv-task-pers-1 uses 变得沉默 (dedup hit)
for i in range(3):
    g += 1
    name = TASK_OWNERS[(i + 1) % len(TASK_OWNERS)]  # chain rows need an owned task
    cid = CHAR_BY_NAME[name][0]
    goal = TASK_OF[name]
    lo = CHAR_BY_NAME[name][2]   # before sanity from the world registry
    hi = CHAIN_SANITY[i]
    dur = DURATIONS[(i + 3) % 6]
    world = make_world([name], [])
    deltas = [task_delta(cid, goal),
              personality_delta(cid, f"chg_{i + 1:03d}", PERSONALITIES[i]),
              sanity_delta(cid, hi)]
    time_entry = {"amount": dur[0], "unit": dur[1], "rendered": dur[2]}
    verb = "升到了" if hi > lo else "降到了"
    text = (f"{name}完成了任务「{goal}」，{PERSONALITIES[i]}，"
            f"精神值从{lo}{verb}{hi}。前后大约{dur[2]}。")
    rows.append(row(f"n4-chain-{g:03d}", "template-seed", "program", "train",
                    world, deltas, time_entry, text, [[0, 1, 2], [3]],
                    [0, 1, 2, 3], [], NO_ADD_STD,
                    "N4 成句微调：任务→人格→理智联动（sanity 动词按数据方向渲染）"))

# --- family 5: appearance + time (3 groups, train) ---
APPEARANCES = ["门柱上的漆皮剥落了大半", "石阶缝里长出了青苔", "栏杆的漆色褪成了灰白"]
for i in range(3):
    g += 1
    loc_name = LOCS[(i + 5) % 7][1]
    desc = APPEARANCES[i % 3]
    dur = DURATIONS[(i + 4) % 6]
    world = make_world(["陈舟"], [loc_name])
    deltas = [appearance_delta(loc_name, f"chg_a{i + 1:03d}", desc)]
    time_entry = {"amount": dur[0], "unit": dur[1], "rendered": dur[2]}
    text = f"{loc_name}的外观变了：{desc}。前后大约{dur[2]}。"
    rows.append(row(f"n4-appear-{g:03d}", "template-seed", "program", "train",
                    world, deltas, time_entry, text, [[0], [1]], [0, 1], [],
                    NO_ADD_STD, "N4 成句微调：地点外貌（B 投影不支持面，接口表待办）"))

# --- family 6: two entities, one mover + one positioned (3 groups, train) ---
for i in range(3):
    g += 1
    n1 = list(CHAR_BY_NAME)[i % 5]
    n2 = list(CHAR_BY_NAME)[(i + 3) % 5]
    c1 = CHAR_BY_NAME[n1][0]
    frm_name = LOC_NAME[CHAR_BY_NAME[n1][1]]
    to_name = LOCS[(i + 4) % 7][1]
    dur = DURATIONS[i % 6]
    world = make_world([n1, n2], [frm_name, to_name])
    deltas = [moved_delta(c1, to_name)]
    time_entry = {"amount": dur[0], "unit": dur[1], "rendered": dur[2]}
    # positioned claim: n2's home IS to_name for these rows (current state)
    c2, home2 = CHAR_BY_NAME[n2][0], CHAR_BY_NAME[n2][1]
    if home2 != to_name:
        # move n2's registry home (loc ID, not the Chinese name) so the
        # positioned claim has before support
        world = make_world([n1, n2], [frm_name, to_name])
        for c in world["characters"]:
            if c["id"] == c2:
                c["homeLocId"] = LOC_ID[to_name]
    text = (f"{n1}从{frm_name}来到{to_name}时，{n2}已经在{to_name}了。"
            f"前后大约{dur[2]}。")
    rows.append(row(f"n4-multi-{g:03d}", "template-seed", "program", "train",
                    world, deltas, time_entry, text, [[0, 1], [2]], [0, 1, 2],
                    [], NO_ADD_STD,
                    "N4 成句微调：同点多人物＋现状陈述（现状=before 位置，不进 Δ）",
                    claims=[{"kind": "positioned_at", "entityId": c2,
                             "name": n2, "at": to_name}]))

# --- 2 dev groups ---
g += 1
name = "沈青"
cid = CHAR_BY_NAME[name][0]
frm_name = LOC_NAME[CHAR_BY_NAME[name][1]]
to_name = "东门"
dur = DURATIONS[5]
world = make_world([name], [frm_name, to_name])
deltas = [moved_delta(cid, to_name)]
time_entry = {"amount": dur[0], "unit": dur[1], "rendered": dur[2]}
text = f"{name}从{frm_name}来到{to_name}。前后大约{dur[2]}。"
rows.append(row(f"n4-loc-{g:03d}", "template-seed", "program", "dev",
                world, deltas, time_entry, text, [[0], [1]], [0, 1], [],
                NO_ADD_STD, "N4 开发验收（组级隔离，构造起即 dev）"))
g += 1
name = "林望"
cid = CHAR_BY_NAME[name][0]
goal = "清点碑亭石刻"
dur = DURATIONS[0]
world = make_world([name], [])
deltas = [task_delta(cid, goal)]
time_entry = {"amount": dur[0], "unit": dur[1], "rendered": dur[2]}
text = f"{name}完成了任务「{goal}」。前后大约{dur[2]}。"
rows.append(row(f"n4-task-{g:03d}", "template-seed", "program", "dev",
                world, deltas, time_entry, text, [[0], [1]], [0, 1], [],
                NO_ADD_STD, "N4 开发验收（组级隔离，构造起即 dev）"))

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

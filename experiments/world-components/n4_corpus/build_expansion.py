# N4 expansion builder v8 (review round 9 phase 2, approved design).
#
# Time-choice boundary: every row carries `fullPlan` (the COMPLETE fact
# table INCLUDING the original time advance; rawDelta always keeps the
# advance) and `plan` (the EXPRESSION plan: fullPlan, or fullPlan minus the
# time entry). mustExpress/planRefs index into `plan`; source reconciliation
# runs on fullPlan; text checks run on plan — omitting time never deletes
# the delta.
#
# Scale (approved table):
#   small tier: 60 train sources (24 existing + 36 new)
#   large tier: 120 train sources (small + 60 large-only; containment)
#   fixed dev:   30 sources (6 existing + 24 new)
# Every source group yields TWO plans — expressed-time and omitted-time —
# each a seed+rewrite pair (4 rows/group, 600 rows total). A plan pair is
# ONE independent source.
#
# Rewrite texts: the pattern bank below is authored by ZCode (style-teacher
# role); slot assignment is a deterministic rotation. Existing groups'
# omitted-time siblings are hand-listed verbatim. Assembly is mechanical.
#
# Run AFTER build_seeds.py; NOT idempotent (aborts on existing expansion
# rows). Usage:
#   python experiments/world-components/n4_corpus/build_expansion.py

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SEEDS = HERE / "corpus.seeds.jsonl"
REWRITES = HERE / "rewrites.jsonl"

FAMILIES = ["loc", "empty", "task", "chain", "appear", "multi"]

# ---- expanded vocabulary (new slots only; B cast is guarded by the checker)
NEW_NAMES = ["顾一帆", "白桦", "祁霖", "温以宁", "阮秋", "岑野", "宋知远",
             "贺清言", "洛之衡", "薛映"]
NEW_LOCS = ["灰墙巷", "洗砚池", "南渡口", "旧灯房", "竹径", "断碑崖"]
NEW_TASKS = ["把信笺送去洗砚池", "更换旧灯房的灯油", "修补灰墙巷的路面",
             "抄录断碑崖的铭文", "给竹径立一块木牌", "打捞洗砚池的木匣"]
NEW_APPEARANCES = ["桥栏的麻绳磨断了", "灯罩积了厚厚的灰", "墙根的苔痕连成了一片",
                   "碑座裂了一道细缝", "木牌上的字迹晕开了", "池面的浮叶堆到了一角"]
NEW_PERSONALITIES = ["变得爽朗", "变得寡言", "变得急切", "变得耐心", "变得细心"]
DUR_SLOTS = [(2, "minute", "两分钟"), (6, "minute", "六分钟"),
             (15, "minute", "十五分钟"), (20, "minute", "二十分钟"),
             (30, "minute", "三十分钟"), (45, "minute", "四十五分钟"),
             (90, "minute", "九十分钟"), (2, "hour", "两小时")]
CN = {1: "一", 2: "二", 6: "六", 3: "三", 5: "五", 8: "八", 12: "十二", 15: "十五",
      20: "二十", 25: "二十五", 30: "三十", 40: "四十", 45: "四十五",
      60: "六十", 90: "九十"}
UNIT_CN = {"minute": "分钟", "hour": "小时"}


def num_cn(amount):
    if amount in CN:
        return CN[amount]
    if 10 < amount < 20:
        return "十" + CN[amount - 10]
    if amount % 10 == 0 and amount // 10 in CN:
        return CN[amount // 10] + "十"
    raise ValueError(f"no numeral mapping for {amount}")

# existing registry (mirrors build_seeds; expansion never mutates reviewed rows)
CHARS = {
    "陈舟": ("char_001", "loc_001", 10, [("task_001", "把铜铃挂回钟楼"),
                                         ("task_101", "修补灰墙巷的路面")]),
    "苏晚": ("char_002", "loc_002", 10, [("task_002", "整理柴房"),
                                         ("task_102", "把信笺送去洗砚池")]),
    "周砚": ("char_003", "loc_003", 12, [("task_003", "修缮石桥栏杆"),
                                         ("task_103", "更换旧灯房的灯油")]),
    "林望": ("char_004", "loc_004", 11, [("task_004", "清点碑亭石刻"),
                                         ("task_104", "抄录断碑崖的铭文")]),
    "沈青": ("char_005", "loc_005", 9, [("task_105", "给竹径立一块木牌")]),
}
LOCS = {"loc_001": "东门", "loc_002": "水房", "loc_003": "钟楼", "loc_004": "侧院",
        "loc_005": "柴房", "loc_006": "石桥", "loc_007": "碑亭",
        "loc_008": "灰墙巷", "loc_009": "洗砚池", "loc_010": "南渡口",
        "loc_011": "旧灯房", "loc_012": "竹径", "loc_013": "断碑崖"}
LOC_ID = {v: k for k, v in LOCS.items()}
NEW_CHARS = {}
for i, n in enumerate(NEW_NAMES):
    cid = f"char_{200 + i:03d}"
    home = f"loc_{200 + i:03d}" if False else None  # home assigned per group
    t1, t2 = NEW_TASKS[i % 6], NEW_TASKS[(i + 3) % 6]
    NEW_CHARS[n] = (cid, 10 + (i % 6),
                    [(f"task_{200 + i:03d}", t1), (f"task_{200 + i + 20:03d}", t2)])
ALL_CHAR_NAMES = list(CHARS) + list(NEW_CHARS)
ALL_LOCS = list(LOC_ID)


def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True)


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def strip_time(entry_list):
    """fullPlan -> expression plan (drop the time entry)."""
    return [dict(e, ref=i) for i, e in enumerate(
        e for e in entry_list if e["kind"] != "time")]


# ---- hand-listed omitted-time siblings for the 30 existing groups
EXISTING_SIBLINGS = {
    "n4-loc-001": ("陈舟从东门来到钟楼。", "陈舟从东门一路走到了钟楼。"),
    "n4-loc-002": ("苏晚从水房来到侧院。", "苏晚从水房进入了侧院。"),
    "n4-loc-003": ("周砚从钟楼来到柴房。", "周砚离开了钟楼一路走到了柴房。"),
    "n4-loc-004": ("林望从侧院来到石桥。", "林望从侧院抵达石桥。"),
    "n4-loc-005": ("沈青从柴房来到碑亭。", "沈青由柴房进入碑亭。"),
    "n4-loc-006": ("陈舟从东门来到水房。", "陈舟从东门一路走到了水房。"),
    "n4-empty-007": ("风平浪静。", "风平浪静。"),
    "n4-empty-008": ("平静如常。", "平静如常。"),
    "n4-empty-009": ("没有动静。", "没有动静。"),
    "n4-empty-010": ("一切照旧。", "一切照旧。"),
    "n4-task-011": ("陈舟完成了任务「把铜铃挂回钟楼」。",
                    "陈舟已达成任务「把铜铃挂回钟楼」。"),
    "n4-task-012": ("苏晚完成了任务「整理柴房」。", "苏晚办妥了任务「整理柴房」。"),
    "n4-task-013": ("周砚完成了任务「修缮石桥栏杆」。",
                    "约四十分钟过去了，周砚已达成任务「修缮石桥栏杆」。".replace(
                        "约四十分钟过去了，", "")),
    "n4-task-014": ("林望完成了任务「清点碑亭石刻」。", "林望办妥了任务「清点碑亭石刻」。"),
    "n4-task-015": ("陈舟完成了任务「把铜铃挂回钟楼」。", "陈舟已办妥任务「把铜铃挂回钟楼」。"),
    "n4-chain-016": ("苏晚完成了任务「整理柴房」，变得沉稳，精神值从10升到了13。",
                     "苏晚办妥了任务「整理柴房」，变得沉稳，精神值从10提升至13。"),
    "n4-chain-017": ("周砚完成了任务「修缮石桥栏杆」，话多了起来，精神值从12升到了14。",
                     "周砚完成了任务「修缮石桥栏杆」，话多了起来，精神值从12涨到了14。"),
    "n4-chain-018": ("林望完成了任务「清点碑亭石刻」，变得内敛，精神值从11升到了12。",
                     "林望达成了任务「清点碑亭石刻」，变得内敛，精神值从11升到了12。"),
    "n4-appear-019": ("石桥的外观变了：门柱上的漆皮剥落了大半。",
                      "石桥的外观变了：门柱上的漆皮剥落了大半。"),
    "n4-appear-020": ("碑亭的外观变了：石阶缝里长出了青苔。",
                      "碑亭的外观变了：石阶缝里长出了青苔。"),
    "n4-appear-021": ("东门的外观变了：栏杆的漆色褪成了灰白。",
                      "东门的外观变了：栏杆的漆色褪成了灰白。"),
    "n4-multi-022": ("陈舟从东门来到柴房时，林望已经在柴房了。",
                     "陈舟一路从东门来到了柴房，林望已经在柴房了。"),
    "n4-multi-023": ("苏晚从水房来到石桥时，沈青已经在石桥了。",
                     "苏晚从水房抵达石桥时，沈青已经在石桥了。"),
    "n4-multi-024": ("周砚从钟楼来到碑亭时，陈舟已经在碑亭了。",
                     "周砚从钟楼进入碑亭，陈舟已经在碑亭了。"),
    "n4-loc-025": ("沈青从柴房来到东门。", "整整一小时过去了，沈青由柴房抵达东门。".replace(
        "整整一小时过去了，", "")),
    "n4-task-026": ("林望完成了任务「清点碑亭石刻」。", "林望已办妥任务「清点碑亭石刻」。"),
    "n4-empty-027": ("没有动静。", "风平浪静。"),
    "n4-chain-028": ("陈舟达成了任务「把铜铃挂回钟楼」，变得大胆，精神值从10降到了8。",
                     "陈舟已办妥任务「把铜铃挂回钟楼」，变得大胆，精神值从10降至8。"),
    "n4-appear-029": ("水房的外观变了：墙角的青砖泛了潮。",
                      "水房的外观变了：墙角的青砖泛了潮。"),
    "n4-multi-030": ("三分钟过去了，沈青从柴房来到水房，苏晚已经在水房了。".replace(
        "三分钟过去了，", ""), "沈青由柴房进入了水房，苏晚已经在水房了。"),
}

# ---- rewrite pattern bank for NEW groups (style-teacher authored)
BANK = {
    "loc": ["{n}从{f}一路走到了{t}。", "{n}由{f}进入了{t}。", "{n}离开了{f}，抵达了{t}。"],
    "empty": ["风平浪静。", "平静如常。", "没有动静。", "一切如旧。"],
    "task": ["{n}已达成任务「{g}」。", "{n}办妥了任务「{g}」。", "{n}完成了任务「{g}」。"],
    "chain": ["{n}完成了任务「{g}」，{p}，精神值从{a}{v}到了{b}。",
              "{n}已办妥任务「{g}」，{p}，精神值从{a}{v2}{b}。"],
    "appear": ["{l}的外观变了：{d}。", "{l}的外貌变了:{d}。"],
    "multi": ["{n1}从{f}来到了{t}，{n2}已经在{t}了。", "{n1}由{f}进入了{t}，{n2}已在{t}。"],
}


def make_row(group, origin, rewriter, split, tier, world, raw_delta, full_plan,
             plan, scope, text, refs, must, claims, purpose):
    return {
        "sourceGroupId": group, "rowOrigin": origin, "rewriter": rewriter,
        "task": "n4-sentence", "split": split, "tier": tier,
        "world": world, "rawDelta": raw_delta,
        "fullPlan": full_plan, "plan": plan, "timeScope": scope,
        "planOnlyClaims": claims,
        "planConstruction": {"method": "program-enum-v8",
                             "note": "world/rawDelta/fullPlan 独立构造；plan=fullPlan 的时间表达子集"},
        "planValidation": {
            "authority": "validate_plan_authority.py -> authority-report.json",
            "note": "来源核对与 Δ 对账跑在 fullPlan 上；正文只对 plan 负责；"
                    "plan⊆fullPlan 双向核对见 corpus_check"},
        "text": text, "planRefs": refs,
        "mustExpress": must, "mayMention": [], "mustNotAdd":
            "不得新增：其他实体的动作、对话、评价、未登记实体",
        "hashes": {"plan": sha(canon(plan)), "fullPlan": sha(canon(full_plan)),
                   "world": sha(canon(world)),
                   "rawDelta": sha(canon(raw_delta)), "text": sha(text)},
        "purpose": purpose,
    }


def refs_for(text, plan):
    """Mechanical refs: split sentences on 。; assign each plan entry to the
    sentence whose recognized core it matches (time/no_change by kind)."""
    sentences = [s for s in text.split("。") if s.strip()]
    out = [[] for _ in sentences]
    for e in plan:
        k = e["kind"]
        placed = False
        for si, s in enumerate(sentences):
            hit = False
            if k == "moved" and e["name"] in s and e["to"] in s:
                hit = True
            elif k == "task_achieved" and e["goal"] in s:
                hit = True
            elif k == "personality_changed" and e["text"] in s:
                hit = True
            elif k == "sanity_changed" and (str(e["from"]) in s and str(e["to"]) in s):
                hit = True
            elif k == "appearance_changed" and e["text"] in s:
                hit = True
            elif k == "positioned_at" and (e["at"] in s and e["name"] in s):
                hit = True
            elif k == "time" and UNIT_CN[e["unit"]] in s and (
                    e.get("rendered") in s or str(e["amount"]) in s):
                hit = True
            elif k == "no_change" and any(w in s for w in
                                          ("如旧", "照旧", "没有动静", "平静如常", "风平浪静")):
                hit = True
            if hit:
                out[si].append(e["ref"])
                placed = True
                break
        assert placed, f"unplaceable plan entry {e} in {text!r}"
    return out


def build_new_group(idx, family, split, tier):
    """One new source group = two plans (expressed/omitted) x (seed+rewrite)."""
    gid = f"n4x-{split[:1]}{idx:03d}-{family}"
    di = idx * 3
    dur_a, dur_u, dur_cn = DUR_SLOTS[di % 8]
    name1 = ALL_CHAR_NAMES[idx % 15]
    name2 = ALL_CHAR_NAMES[(idx + 7) % 15]
    loc_f = ALL_LOCS[(idx * 2) % 13]
    loc_t = ALL_LOCS[(idx * 2 + 5) % 13]
    if loc_t == loc_f:
        loc_t = ALL_LOCS[(idx * 2 + 6) % 13]
    reg1 = CHARS.get(name1) or NEW_CHARS[name1]
    tasks1 = reg1[-1] if name1 in CHARS else NEW_CHARS[name1][2]
    goal = tasks1[idx % len(tasks1)][1]
    desc = NEW_APPEARANCES[idx % 6]
    pers = NEW_PERSONALITIES[idx % 5]

    if name1 in CHARS:
        cid1, home1, sanity1, tasks = CHARS[name1]
        goal = tasks[idx % len(tasks)][1]
        task_id = tasks[idx % len(tasks)][0]
    else:
        cid1 = NEW_CHARS[name1][0]
        sanity1 = NEW_CHARS[name1][1]
        tasks = NEW_CHARS[name1][2]
        goal = tasks[idx % len(tasks)][1]
        task_id = tasks[idx % len(tasks)][0]
        home1 = f"home_{cid1}"
    cid2 = (CHARS.get(name2) or NEW_CHARS[name2])[0]

    if name2 in CHARS:
        home2 = CHARS[name2][1]
    else:
        home2 = LOC_ID[ALL_LOCS[(idx * 2 + 5) % 13]]

    world = {"protagonistId": cid1, "locations": [], "characters": []}
    seen = set()
    for loc_name in (loc_f, loc_t):
        if loc_name not in seen:
            world["locations"].append({"id": LOC_ID[loc_name], "name": loc_name})
            seen.add(loc_name)
    for n, home in ((name1, home1), (name2, home2)):
        if home and LOC_ID.get(LOCS.get(home, home if home.startswith("loc_") else None)):
            pass
    # registry locations: every referenced container + both homes
    home_ids = {home1, home2} - {None}
    for hid in home_ids:
        if hid in LOCS and hid not in seen:
            world["locations"].append({"id": hid, "name": LOCS[hid]})
            seen.add(hid)
    for n, home in ((name1, home1), (name2, home2)):
        if n in CHARS:
            c = CHARS[n]
            world["characters"].append({
                "id": c[0], "name": n, "homeLocId": c[1],
                "initialSanity": c[2],
                "tasks": [{"id": t[0], "goal": t[1], "ownerId": c[0]} for t in c[3]]})
        else:
            c = NEW_CHARS[n]
            world["characters"].append({
                "id": c[0], "name": n, "homeLocId": home2 if n == name2 else None,
                "initialSanity": c[1],
                "tasks": [{"id": t[0], "goal": t[1], "ownerId": c[0]} for t in c[2]]})
    if not world["locations"]:
        world["locations"].append({"id": "loc_001", "name": "东门"})
    for ch in world["characters"]:
        if ch["homeLocId"] is None:
            ch["homeLocId"] = world["locations"][0]["id"]
    known = {l["id"] for l in world["locations"]}
    for ch in world["characters"]:
        assert ch["homeLocId"] in known, f"{gid}: home not registered"

    time_entry = {"kind": "time", "amount": dur_a, "unit": dur_u,
                  "rendered": dur_cn}
    time_raw = {"amount": dur_a, "unit": dur_u, "rendered": dur_cn}

    if family == "loc":
        deltas = [{"entityId": cid1, "positionSet": {"containerId": LOC_ID[loc_t]}}]
        main_s, main_r = (f"{name1}从{loc_f}来到{loc_t}。",
                          BANK["loc"][idx % 3].format(n=name1, f=loc_f, t=loc_t))
        full = [{"kind": "moved", "entityId": cid1, "name": name1,
                 "from": loc_f, "to": loc_t}]
        claims = []
    elif family == "empty":
        deltas = []
        main_s, main_r = "一切如旧。", BANK["empty"][idx % 4]
        full = [{"kind": "no_change", "scope": "全局"}]
        claims = [{"kind": "no_change", "scope": "全局"}]
    elif family == "task":
        deltas = [{"entityId": cid1, "tasksAchieved": [task_id]}]
        main_s = f"{name1}完成了任务「{goal}」。"
        main_r = BANK["task"][idx % 3].format(n=name1, g=goal)
        full = [{"kind": "task_achieved", "entityId": cid1, "name": name1, "goal": goal}]
        claims = []
    elif family == "chain":
        down = idx % 2 == 1
        hi = max(sanity1 - 3, 1) if down else min(sanity1 + 3, 20)
        deltas = [{"entityId": cid1, "tasksAchieved": [task_id]},
                  {"entityId": cid1,
                   "personalityChanges": [{"id": f"chg_{gid}", "text": pers,
                                           "supersedes": []}]},
                  {"entityId": cid1, "sanitySet": hi}]
        verb = "升" if hi > sanity1 else "降"
        main_s = (f"{name1}完成了任务「{goal}」，{pers}，"
                  f"精神值从{sanity1}{verb}到了{hi}。")
        main_r = BANK["chain"][idx % 2].format(
            n=name1, g=goal, p=pers, a=sanity1, b=hi,
            v=verb, v2=("提升至" if hi > sanity1 else "降至"))
        full = [{"kind": "task_achieved", "entityId": cid1, "name": name1, "goal": goal},
                {"kind": "personality_changed", "entityId": cid1, "name": name1,
                 "text": pers},
                {"kind": "sanity_changed", "entityId": cid1, "name": name1,
                 "from": sanity1, "to": hi}]
        claims = []
    elif family == "appear":
        deltas = [{"entityId": LOC_ID[loc_t],
                   "appearanceChanges": [{"id": f"chg_{gid}", "text": desc,
                                          "supersedes": []}]}]
        main_s, main_r = (f"{loc_t}的外观变了：{desc}。",
                          BANK["appear"][idx % 2].format(l=loc_t, d=desc))
        full = [{"kind": "appearance_changed", "entityId": LOC_ID[loc_t],
                 "name": loc_t, "text": desc}]
        claims = []
    else:  # multi
        # mover n1 leaves home; n2's registry home IS the target (current state)
        world = json.loads(json.dumps(world))
        if name2 in CHARS:
            home2 = CHARS[name2][1]
            if home2 != LOC_ID[loc_t]:
                home2 = LOC_ID[loc_t]
                for ch in world["characters"]:
                    if ch["name"] == name2:
                        ch["homeLocId"] = home2
        else:
            home2 = LOC_ID[loc_t]
            for ch in world["characters"]:
                if ch["name"] == name2:
                    ch["homeLocId"] = home2
        deltas = [{"entityId": cid1, "positionSet": {"containerId": LOC_ID[loc_t]}}]
        main_s = f"{name1}从{loc_f}来到{loc_t}时，{name2}已经在{loc_t}了。"
        main_r = BANK["multi"][idx % 2].format(n1=name1, f=loc_f, t=loc_t, n2=name2)
        full = [{"kind": "moved", "entityId": cid1, "name": name1,
                 "from": loc_f, "to": loc_t},
                {"kind": "positioned_at", "entityId": cid2, "name": name2,
                 "at": loc_t}]
        claims = [{"kind": "positioned_at", "entityId": cid2, "name": name2,
                   "at": loc_t}]

    time_full = dict(time_entry, ref=len(full))
    full_plan = [dict(e, ref=i) for i, e in enumerate(full)] + [time_full]
    raw_delta = {"entityDeltas": deltas, "time": time_raw}

    rows = []
    for scope, seed_text, rw_text in (
            ("expressed",
             main_s + (f"前后大约{dur_cn}。" if family != "empty" else
                       f"大约{dur_cn}过去了。"),
             main_r + (f"前后大约{dur_cn}。" if family != "empty" else
                       f"{dur_cn}过去了。")),
            ("omitted", main_s, main_r)):
        plan = full_plan if scope == "expressed" else strip_time(full_plan)
        must = [e["ref"] for e in plan]
        refs = refs_for(seed_text, plan)
        rows.append(("template-seed", make_row(gid, "template-seed", "program", split, tier,
                                      world, raw_delta, full_plan, plan, scope,
                                      seed_text, refs, must, claims,
                                      f"N4 扩批 {family}/{scope} 种子行")))
        refs_r = refs_for(rw_text, plan)
        rows.append(("rewrite", make_row(gid, "rewrite", "zcode-model", split, tier,
                                         world, raw_delta, full_plan, plan, scope,
                                         rw_text, refs_r, must, claims,
                                         f"N4 扩批 {family}/{scope} 改写行")))
    return rows


def main() -> None:
    seed_lines = [json.loads(l) for l in SEEDS.read_text(encoding="utf-8").splitlines()
                  if l.strip()]
    rw_lines = [json.loads(l) for l in REWRITES.read_text(encoding="utf-8").splitlines()
                if l.strip()]
    existing_ids = {r["sourceGroupId"] for r in seed_lines}
    if any(g.startswith("n4x-") for g in existing_ids):
        raise SystemExit("expansion rows already present — not idempotent")

    # ---- migrate existing rows: fullPlan/timeScope/tier + fullPlan hash
    for r in seed_lines + rw_lines:
        if "fullPlan" in r:
            continue
        r["fullPlan"] = r["plan"]           # existing rows all express time
        r["timeScope"] = "expressed"
        r["tier"] = "small" if r["split"] == "train" else "fixed-dev"
        r["hashes"]["fullPlan"] = sha(canon(r["fullPlan"]))

    # ---- existing groups: omitted-time sibling rows (hand-listed texts)
    seed_by_group = {r["sourceGroupId"]: r for r in seed_lines}
    new_seeds, new_rewrites = [], []
    for gid, (sib_seed, sib_rw) in EXISTING_SIBLINGS.items():
        base = seed_by_group[gid]
        full_plan = base["fullPlan"]
        plan = strip_time(full_plan)
        must = [e["ref"] for e in plan]
        tier = base["tier"]
        rows = []
        for origin, text in (("template-seed", sib_seed), ("rewrite", sib_rw)):
            rows.append((origin, text))
        for origin, text in rows:
            refs = refs_for(text, plan)
            row = make_row(gid, origin,
                           "program" if origin == "template-seed" else "zcode-model",
                           base["split"], tier, base["world"], base["rawDelta"],
                           full_plan, plan, "omitted", text, refs, must,
                           base.get("planOnlyClaims", []),
                           f"N4 扩批 {gid.split('-', 1)[1]}/omitted（既有组 sibling）")
            (new_seeds if origin == "template-seed" else new_rewrites).append(row)

    # ---- new groups: 96 train (36 small + 60 large) + 24 dev
    plan_of_family = []
    for i in range(96):
        family = FAMILIES[i % 6]
        tier = "small" if i < 36 else "large"
        split = "train"
        plan_of_family.append((i, family, split, tier))
    for i in range(24):
        family = FAMILIES[i % 6]
        plan_of_family.append((100 + i, family, "dev", "fixed-dev"))

    for idx, family, split, tier in plan_of_family:
        for origin, row in build_new_group(idx, family, split, tier):
            (new_seeds if origin == "template-seed" else new_rewrites).append(row)

    SEEDS.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in seed_lines + new_seeds)
        + "\n", encoding="utf-8")
    REWRITES.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rw_lines + new_rewrites)
        + "\n", encoding="utf-8")
    tiers = {}
    for r in new_seeds:
        key = (r["split"], r["tier"])
        tiers[key] = tiers.get(key, 0) + 1
    print(f"existing rows migrated: {len(seed_lines) + len(rw_lines)}")
    print(f"new rows: seeds {len(new_seeds)} + rewrites {len(new_rewrites)}")
    print(f"new-group tier census (seeds): {tiers}")
    total_groups = len({r['sourceGroupId'] for r in seed_lines + new_seeds})
    total_rows = len(seed_lines + new_seeds) + len(rw_lines + new_rewrites)
    print(f"total groups: {total_groups}  total rows: {total_rows}")


if __name__ == "__main__":
    main()

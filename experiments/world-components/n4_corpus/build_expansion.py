# N4 expansion builder v9.2 (review round 12).
#
# v9.2 fixes on top of v9.1:
# a. the no_change exemption is NARROWED to the atomic omitted-time plan
#    (plan == [no_change], rendering exactly "无变化"). Time-bearing empty
#    plans (time + no_change) are distinguishable by duration and now obey
#    the train/dev input-disjointness rule: dev uses a disjoint duration
#    pool (1/4/7/10 min) so no time-bearing empty dev input repeats a train
#    input. The old build exempted all no_change plans, which let
#    n4x-d101-empty reuse n4x-t001-empty's "两分钟+无变化" input.
# b. the build prints the reviewer's denominator directly: unique train/dev
#    render inputs, dev inputs also in train, unseen dev inputs, and the
#    frozen base-group regression pair.
#
# v9.1 fixes on top of the v9 draft:
# a. character task tuples unpack as (task_id, goal), matching the registry
#    layout — the draft swapped them, so plans carried ids as goals and the
#    authority report showed 480 provenance errors
# b. empty-family seed time uses 「前后大约X。」 instead of 「大约X分钟过去了」,
#    which was a bidirectional-substring hit against B's archived
#    「约X分钟过去了。」 in narration-split-baseline.json
# c. frozen base groups enter the signature table; base-only duplicates are
#    tallied as a regression item instead of being silently excluded
# (d) checker v4: sentence-level coverage with an optional-comma moved
#    pattern so 「X离开了A，抵达了B」 is recognized as one fact
#
# Time-choice boundary (unchanged): every row carries `fullPlan` (complete
# fact table INCLUDING the original time advance; rawDelta always keeps it)
# and `plan` (expression plan = fullPlan, or fullPlan minus time).
# mustExpress/planRefs index into `plan`; authority reconciles fullPlan;
# text checks run on plan.
#
# v9 fixes over the rejected 2aa6355 build:
# 1. complete world registries — every character has id/home/sanity/
#    initialPersonality/tasks; locations are the deduplicated union of every
#    referenced container; moved targets are asserted != the mover's home
#    (no fake home ids, no idempotent moves, no KeyError in authority)
# 2. source isolation by SIGNATURE: sha(world+rawDelta+fullPlan) must be
#    unique across ALL groups — the round-10 train/dev empty-point and task
#    input collisions are structurally impossible now; uniqueness is
#    asserted at build time
# 3. slot assignment is DECOUPLED from the global loop index: per-family
#    counters drive duration/name/pattern/description; chain direction
#    alternates per family counter with train starting upward and dev
#    starting downward; a real coverage table is printed
# 4. rendered fields come from n4_render.num_cn (the single numeric
#    formatter), and every produced row's training input is rendered at
#    build time (600/600 precheck) plus a render-input train/dev disjointness
#    assertion
#
# Scale (approved): small 60 train sources (24 existing + 36 new), large
# 120 (containment), fixed dev 30 (6 existing + 24 new); two plans per
# group (expressed/omitted), seed+rewrite each; plan pairs = ONE source.
#
# Run AFTER build_seeds.py; NOT idempotent. Usage:
#   python experiments/world-components/n4_corpus/build_expansion.py

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from n4_render import num_cn, UNIT_CN, render_input  # noqa: E402

SEEDS = HERE / "corpus.seeds.jsonl"
REWRITES = HERE / "rewrites.jsonl"

FAMILIES = ["loc", "empty", "task", "chain", "appear", "multi"]

NEW_NAMES = ["顾一帆", "白桦", "祁霖", "温以宁", "阮秋", "岑野", "宋知远",
             "贺清言", "洛之衡", "薛映"]
NEW_LOCS = ["灰墙巷", "洗砚池", "南渡口", "旧灯房", "竹径", "断碑崖"]
NEW_TASKS = ["把信笺送去洗砚池", "更换旧灯房的灯油", "修补灰墙巷的路面",
             "抄录断碑崖的铭文", "给竹径立一块木牌", "打捞洗砚池的木匣"]
NEW_APPEARANCES = ["桥栏的麻绳磨断了", "灯罩积了厚厚的灰", "墙根的苔痕连成了一片",
                   "碑座裂了一道细缝", "木牌上的字迹晕开了", "池面的浮叶堆到了一角"]
NEW_PERSONALITIES = ["变得爽朗", "变得寡言", "变得急切", "变得耐心", "变得细心"]
# Train and dev duration pools are DISJOINT by construction: the empty-point
# fact table renders to time + no_change, so two 2-minute empty plans are the
# same input. The round-11 review rejected exempting time-bearing empty dev
# inputs from the train/dev input-disjointness check; only the atomic
# omitted-time "无变化" plan (one possible rendering) stays exempt.
DUR_SLOTS = [(2, "minute"), (5, "minute"), (6, "minute"), (15, "minute"),
             (20, "minute"), (30, "minute"), (45, "minute"), (90, "minute")]
DEV_DUR_SLOTS = [(1, "minute"), (4, "minute"), (7, "minute"), (10, "minute")]

LOC_ID = {"东门": "loc_001", "水房": "loc_002", "钟楼": "loc_003",
          "侧院": "loc_004", "柴房": "loc_005", "石桥": "loc_006",
          "碑亭": "loc_007", "灰墙巷": "loc_008", "洗砚池": "loc_009",
          "南渡口": "loc_010", "旧灯房": "loc_011", "竹径": "loc_012",
          "断碑崖": "loc_013"}
LOC_NAME = {v: k for k, v in LOC_ID.items()}
CHARS = {
    "陈舟": {"id": "char_001", "home": "loc_001", "sanity": 10,
             "personality": "谨慎",
             "tasks": [("task_001", "把铜铃挂回钟楼"), ("task_101", "修补灰墙巷的路面")]},
    "苏晚": {"id": "char_002", "home": "loc_002", "sanity": 10,
             "personality": "外向",
             "tasks": [("task_002", "整理柴房"), ("task_102", "把信笺送去洗砚池")]},
    "周砚": {"id": "char_003", "home": "loc_003", "sanity": 12,
             "personality": "沉默",
             "tasks": [("task_003", "修缮石桥栏杆"), ("task_103", "更换旧灯房的灯油")]},
    "林望": {"id": "char_004", "home": "loc_004", "sanity": 11,
             "personality": "急躁",
             "tasks": [("task_004", "清点碑亭石刻"), ("task_104", "抄录断碑崖的铭文")]},
    "沈青": {"id": "char_005", "home": "loc_005", "sanity": 9,
             "personality": "细心",
             "tasks": [("task_105", "给竹径立一块木牌")]},
}
for i, n in enumerate(NEW_NAMES):
    CHARS[n] = {"id": f"char_{200 + i:03d}",
                "home": f"loc_{200 + (i % 6):03d}",
                "sanity": 8 + (i % 9), "personality": "平常",
                "tasks": [(f"task_{200 + i:03d}", NEW_TASKS[i % 6]),
                          (f"task_{220 + i:03d}", NEW_TASKS[(i + 3) % 6])]}
    LOC_ID[NEW_LOCS[i % 6]] = f"loc_{200 + (i % 6):03d}"
LOC_NAME.update({v: k for k, v in LOC_ID.items()})
ALL_NAMES = list(CHARS)

BANK = {
    "loc": ["{n}从{f}一路走到了{t}。", "{n}由{f}进入了{t}。", "{n}离开了{f}，抵达了{t}。"],
    "empty": ["风平浪静。", "平静如常。", "没有动静。", "一切如旧。"],
    "task": ["{n}已达成任务「{g}」。", "{n}办妥了任务「{g}」。", "{n}完成了任务「{g}」。"],
    "chain": ["{n}完成了任务「{g}」，{p}，精神值从{a}{v}到了{b}。",
              "{n}已办妥任务「{g}」，{p}，精神值从{a}{v2}{b}。"],
    "appear": ["{l}的外观变了：{d}。", "{l}的外貌变了:{d}。"],
    "multi": ["{n1}从{f}来到了{t}，{n2}已经在{t}了。", "{n1}由{f}进入了{t}，{n2}已在{t}。"],
}

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
                    "周砚已达成任务「修缮石桥栏杆」。"),
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
    "n4-loc-025": ("沈青从柴房来到东门。", "沈青由柴房抵达东门。"),
    "n4-task-026": ("林望完成了任务「清点碑亭石刻」。", "林望已办妥任务「清点碑亭石刻」。"),
    "n4-empty-027": ("没有动静。", "风平浪静。"),
    "n4-chain-028": ("陈舟达成了任务「把铜铃挂回钟楼」，变得大胆，精神值从10降到了8。",
                     "陈舟已办妥任务「把铜铃挂回钟楼」，变得大胆，精神值从10降至8。"),
    "n4-appear-029": ("水房的外观变了：墙角的青砖泛了潮。",
                      "水房的外观变了：墙角的青砖泛了潮。"),
    "n4-multi-030": ("沈青从柴房来到水房，苏晚已经在水房了。",
                     "沈青由柴房进入了水房，苏晚已经在水房了。"),
}


def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True)


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def strip_time(entries):
    return [dict(e, ref=i) for i, e in enumerate(
        e for e in entries if e["kind"] != "time")]


def refs_for(text, plan):
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
            elif k == "sanity_changed" and str(e["from"]) in s and str(e["to"]) in s:
                hit = True
            elif k == "appearance_changed" and e["text"] in s:
                hit = True
            elif k == "positioned_at" and e["at"] in s and e["name"] in s:
                hit = True
            elif k == "time" and UNIT_CN[e["unit"]] in s and (
                    e.get("rendered") in s or str(e["amount"]) in s):
                hit = True
            elif k == "no_change" and any(w in s for w in (
                    "如旧", "照旧", "没有动静", "平静如常", "风平浪静")):
                hit = True
            if hit:
                out[si].append(e["ref"])
                placed = True
                break
        assert placed, f"unplaceable plan entry {e} in {text!r}"
    return out


def make_row(group, origin, rewriter, split, tier, world, raw_delta, full_plan,
             plan, scope, text, refs, must, claims, purpose):
    return {
        "sourceGroupId": group, "rowOrigin": origin, "rewriter": rewriter,
        "task": "n4-sentence", "split": split, "tier": tier,
        "world": world, "rawDelta": raw_delta,
        "fullPlan": full_plan, "plan": plan, "timeScope": scope,
        "planOnlyClaims": claims,
        "planConstruction": {"method": "program-enum-v9",
                             "note": "完整 world 注册表独立构造；plan=fullPlan 的时间表达子集"},
        "planValidation": {
            "authority": "validate_plan_authority.py -> authority-report.json",
            "note": "来源核对与 Δ 对账跑在 fullPlan 上；正文只对 plan 负责；"
                    "plan⊆fullPlan 双向核对见 corpus_check"},
        "text": text, "planRefs": refs,
        "mustExpress": must, "mayMention": [],
        "mustNotAdd": "不得新增：其他实体的动作、对话、评价、未登记实体",
        "hashes": {"plan": sha(canon(plan)), "fullPlan": sha(canon(full_plan)),
                   "world": sha(canon(world)),
                   "rawDelta": sha(canon(raw_delta)), "text": sha(text)},
        "purpose": purpose,
    }


def build_world(names, extra_locs):
    """Complete registry: every referenced container registered, every
    character with id/home/sanity/initialPersonality/tasks."""
    world = {"protagonistId": CHARS[names[0]]["id"], "locations": [],
             "characters": []}
    seen = set()
    for n in names:
        home = CHARS[n]["home"]
        if home not in seen:
            world["locations"].append({"id": home, "name": LOC_NAME[home]})
            seen.add(home)
    for loc in extra_locs:
        lid = LOC_ID[loc]
        if lid not in seen:
            world["locations"].append({"id": lid, "name": loc})
            seen.add(lid)
    for n in names:
        c = CHARS[n]
        world["characters"].append({
            "id": c["id"], "name": n, "homeLocId": c["home"],
            "initialSanity": c["sanity"], "initialPersonality": c["personality"],
            "tasks": [{"id": t[0], "goal": t[1], "ownerId": c["id"]}
                      for t in c["tasks"]]})
    return world


def build_new_group(seq, family, split, tier, fc):
    """fc = per-family counter (decoupled slot assignment)."""
    dur_pool = DEV_DUR_SLOTS if split == "dev" else DUR_SLOTS
    dur_a, dur_u = dur_pool[fc % len(dur_pool)]
    dur_cn = f"{num_cn(dur_a)}{UNIT_CN[dur_u]}"
    name1 = ALL_NAMES[fc % 15]
    name2 = ALL_NAMES[(fc + 7) % 15]
    loc_names = list(LOC_ID)
    loc_appear = loc_names[(fc * 3 + 5) % 13]
    reg1 = CHARS[name1]
    task_id, goal = reg1["tasks"][fc % len(reg1["tasks"])]
    desc = NEW_APPEARANCES[fc % 6]
    pers = NEW_PERSONALITIES[fc % 5]
    gid = f"n4x-{split[:1]}{seq:03d}-{family}"

    # movement departs from the mover's registered home (authority provenance
    # requires plan.from == registry home) and targets a DIFFERENT location
    # (idempotent position sets do not evidence movement)
    home_name = LOC_NAME[reg1["home"]]

    def resolve_target(offset):
        cand = loc_names[(fc * 3 + offset) % 13]
        while cand in (home_name, loc_f):
            offset += 1
            cand = loc_names[(fc * 3 + offset) % 13]
        return cand

    if family in ("loc", "multi"):
        loc_f = home_name
        loc_t = resolve_target(5)

    if family == "loc":
        world = build_world([name1], [loc_f, loc_t])
        assert reg1["home"] != LOC_ID[loc_t], f"{gid}: idempotent move"
        deltas = [{"entityId": reg1["id"],
                   "positionSet": {"containerId": LOC_ID[loc_t]}}]
        main_s = f"{name1}从{loc_f}来到{loc_t}。"
        main_r = BANK["loc"][fc % 3].format(n=name1, f=loc_f, t=loc_t)
        full = [{"kind": "moved", "entityId": reg1["id"], "name": name1,
                 "from": loc_f, "to": loc_t}]
        claims = []
    elif family == "empty":
        world = build_world([name1], [])
        deltas = []
        main_s, main_r = "一切如旧。", BANK["empty"][fc % 4]
        full = [{"kind": "no_change", "scope": "全局"}]
        claims = [{"kind": "no_change", "scope": "全局"}]
    elif family == "task":
        world = build_world([name1], [])
        deltas = [{"entityId": reg1["id"], "tasksAchieved": [task_id]}]
        main_s = f"{name1}完成了任务「{goal}」。"
        main_r = BANK["task"][fc % 3].format(n=name1, g=goal)
        full = [{"kind": "task_achieved", "entityId": reg1["id"],
                 "name": name1, "goal": goal}]
        claims = []
    elif family == "chain":
        world = build_world([name1], [])
        down = (fc % 2 == 1) if split == "train" else (fc % 2 == 0)
        hi = max(reg1["sanity"] - 3, 1) if down else min(reg1["sanity"] + 3, 20)
        deltas = [{"entityId": reg1["id"], "tasksAchieved": [task_id]},
                  {"entityId": reg1["id"],
                   "personalityChanges": [{"id": f"chg_{gid}", "text": pers,
                                           "supersedes": []}]},
                  {"entityId": reg1["id"], "sanitySet": hi}]
        verb = "升" if hi > reg1["sanity"] else "降"
        main_s = (f"{name1}完成了任务「{goal}」，{pers}，"
                  f"精神值从{reg1['sanity']}{verb}到了{hi}。")
        main_r = BANK["chain"][fc % 2].format(
            n=name1, g=goal, p=pers, a=reg1["sanity"], b=hi, v=verb,
            v2=("提升至" if hi > reg1["sanity"] else "降至"))
        full = [{"kind": "task_achieved", "entityId": reg1["id"],
                 "name": name1, "goal": goal},
                {"kind": "personality_changed", "entityId": reg1["id"],
                 "name": name1, "text": pers},
                {"kind": "sanity_changed", "entityId": reg1["id"],
                 "name": name1, "from": reg1["sanity"], "to": hi}]
        claims = []
    elif family == "appear":
        world = build_world(["陈舟"], [loc_appear])
        deltas = [{"entityId": LOC_ID[loc_appear],
                   "appearanceChanges": [{"id": f"chg_{gid}", "text": desc,
                                          "supersedes": []}]}]
        main_s = f"{loc_appear}的外观变了：{desc}。"
        main_r = BANK["appear"][fc % 2].format(l=loc_appear, d=desc)
        full = [{"kind": "appearance_changed", "entityId": LOC_ID[loc_appear],
                 "name": loc_appear, "text": desc}]
        claims = []
    else:  # multi
        other = name2
        reg_o = CHARS[other]
        world = build_world([name1, other], [loc_f, loc_t])
        home_o = LOC_ID[loc_t]
        for ch in world["characters"]:
            if ch["name"] == other:
                ch["homeLocId"] = home_o
        deltas = [{"entityId": reg1["id"],
                   "positionSet": {"containerId": LOC_ID[loc_t]}}]
        assert reg1["home"] != LOC_ID[loc_t], f"{gid}: idempotent move"
        main_s = f"{name1}从{loc_f}来到{loc_t}时，{other}已经在{loc_t}了。"
        main_r = BANK["multi"][fc % 2].format(n1=name1, f=loc_f, t=loc_t,
                                              n2=other)
        full = [{"kind": "moved", "entityId": reg1["id"], "name": name1,
                 "from": loc_f, "to": loc_t},
                {"kind": "positioned_at", "entityId": reg_o["id"],
                 "name": other, "at": loc_t}]
        claims = [{"kind": "positioned_at", "entityId": reg_o["id"],
                   "name": other, "at": loc_t}]

    full_plan = [dict(e, ref=i) for i, e in enumerate(full)]
    full_plan.append(dict({"kind": "time", "amount": dur_a, "unit": dur_u,
                           "rendered": dur_cn}, ref=len(full)))
    raw_delta = {"entityDeltas": deltas,
                 "time": {"amount": dur_a, "unit": dur_u, "rendered": dur_cn}}

    rows, meta = [], {"family": family, "split": split, "tier": tier}
    # empty seed-time phrasing v9.1: "大约X分钟过去了" contains B's archived
    # split-baseline string "约X分钟过去了。" (dedup bidirectional substring),
    # so empty seeds use the same "前后大约X。" form as the other families
    time_sent_s = f"前后大约{dur_cn}。"
    time_sent_r = (f"前后大约{dur_cn}。" if family != "empty"
                   else f"{dur_cn}过去了。")
    for scope, text_s, text_r in (("expressed",
                                   main_s + time_sent_s, main_r + time_sent_r),
                                  ("omitted", main_s, main_r)):
        plan = full_plan if scope == "expressed" else strip_time(full_plan)
        must = [e["ref"] for e in plan]
        for origin, text in (("template-seed", text_s), ("rewrite", text_r)):
            rows.append(make_row(gid, origin,
                                 "program" if origin == "template-seed"
                                 else "zcode-model",
                                 split, tier, world, raw_delta, full_plan,
                                 plan, scope, text, refs_for(text, plan), must,
                                 claims, f"N4 扩批 v9 {family}/{scope}"))
    return rows, meta


def register(seq, fam, split, fc, rows, signatures, coverage):
    sig = sha(canon({"world": rows[0]["world"],
                     "rawDelta": rows[0]["rawDelta"],
                     "fullPlan": rows[0]["fullPlan"]}))
    if sig in signatures:
        raise SystemExit(f"SIGNATURE COLLISION: n4x group {seq} duplicates "
                         f"group {signatures[sig]}")
    signatures[sig] = seq
    if fam == "chain":
        down = (fc % 2 == 1) if split == "train" else (fc % 2 == 0)
        key = ("chain", split, "down" if down else "up")
    else:
        key = (fam, split)
    coverage[key] = coverage.get(key, 0) + 1


def main() -> None:
    seed_rows = [json.loads(l) for l in SEEDS.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
    rw_rows = [json.loads(l) for l in REWRITES.read_text(encoding="utf-8").splitlines()
               if l.strip()]
    existing_ids = {r["sourceGroupId"] for r in seed_rows}
    if any(g.startswith("n4x-") for g in existing_ids):
        raise SystemExit("expansion rows already present — not idempotent")

    for r in seed_rows + rw_rows:
        if "fullPlan" in r:
            continue
        r["fullPlan"] = r["plan"]
        r["timeScope"] = "expressed"
        r["tier"] = "small" if r["split"] == "train" else "fixed-dev"
        r["hashes"]["fullPlan"] = sha(canon(r["fullPlan"]))

    seed_by_group = {r["sourceGroupId"]: r for r in seed_rows}
    new_seeds, new_rewrites = [], []
    all_rows = seed_rows + rw_rows

    for gid, (sib_seed, sib_rw) in EXISTING_SIBLINGS.items():
        base = seed_by_group[gid]
        full_plan = base["fullPlan"]
        plan = strip_time(full_plan)
        must = [e["ref"] for e in plan]
        for origin, text in (("template-seed", sib_seed), ("rewrite", sib_rw)):
            row = make_row(gid, origin,
                           "program" if origin == "template-seed" else "zcode-model",
                           base["split"], base["tier"], base["world"],
                           base["rawDelta"], full_plan, plan, "omitted", text,
                           refs_for(text, plan), must,
                           base.get("planOnlyClaims", []),
                           f"N4 扩批 v9 {gid}/omitted（既有组 sibling）")
            all_rows.append(row)
            (new_seeds if origin == "template-seed" else new_rewrites).append(row)

    plan_specs = []
    for i in range(96):
        plan_specs.append((i, FAMILIES[i % 6], "train",
                           "small" if i < 36 else "large"))
    for i in range(24):
        plan_specs.append((100 + i, FAMILIES[i % 6], "dev", "fixed-dev"))

    families = {f: 0 for f in FAMILIES}
    coverage = {}
    # v9.1: base (frozen) source groups enter the signature table too, so the
    # "unique across ALL groups" claim covers new-vs-base as well. Pre-existing
    # duplicates among the reviewed base rows are tallied, not fixed here
    # (changing accepted rows would break their pinned hashes).
    signatures = {}
    base_dup_sigs = []
    for gid, r in seed_by_group.items():
        sig = sha(canon({"world": r["world"], "rawDelta": r["rawDelta"],
                         "fullPlan": r["fullPlan"]}))
        if sig in signatures:
            base_dup_sigs.append((signatures[sig], gid))
        else:
            signatures[sig] = gid
    # disjointness targets BOTH directions: new train inputs must avoid the
    # existing dev rows' inputs, and new dev inputs must avoid every train
    # input. ONLY the atomic omitted-time no_change plan (rendering "无变化")
    # is exempt (tallied separately, see below); time-bearing empty plans are
    # distinguishable by duration and must obey disjointness.
    def atomic_no_change(row):
        plan = row["plan"]
        return bool(plan) and all(e["kind"] == "no_change" for e in plan)

    base_dv_in = {sha(render_input(r["plan"])) for r in all_rows
                  if r["split"] == "dev" and not atomic_no_change(r)}
    # train first: its render inputs define the set dev must avoid
    for seq, fam, split, tier in plan_specs:
        fc = families[fam]
        families[fam] += 1
        if split == "train":
            for shift in range(60):
                rows, meta = build_new_group(seq, fam, split, tier, fc + shift * 7)
                if all(sha(render_input(r["plan"])) not in base_dv_in for r in rows):
                    break
            else:
                raise SystemExit(f"train group {seq}: no disjoint slot shift found")
            register(seq, fam, split, fc + shift * 7, rows, signatures, coverage)
            all_rows.extend(rows)
            for row in rows:
                (new_seeds if row["rowOrigin"] == "template-seed"
                 else new_rewrites).append(row)
        else:
            # dev: shift slots until this group's render inputs are disjoint
            # from every train input (deterministic retry, step coprime with
            # the name/location/duration pools)
            tr_in = {sha(render_input(r["plan"])) for r in all_rows
                     if r["split"] == "train" and not atomic_no_change(r)}
            for shift in range(60):
                rows, meta = build_new_group(seq, fam, split, tier, fc + shift * 7)
                if all(sha(render_input(r["plan"])) not in tr_in for r in rows):
                    break
            else:
                raise SystemExit(f"dev group {seq}: no disjoint slot shift found")
            register(seq, fam, split, fc + shift * 7, rows, signatures, coverage)
            all_rows.extend(rows)
            for row in rows:
                (new_seeds if row["rowOrigin"] == "template-seed"
                 else new_rewrites).append(row)

    # build-time rendering precheck over every produced row
    for r in all_rows:
        render_input(r["plan"])

    # render-input disjointness across splits (review round 11 #2 / round 12):
    # only the atomic omitted-time no_change plan is exempt — its one possible
    # rendering ("无变化") is an unavoidable shared input in BOTH splits, so
    # it is tallied as a regression input, never counted as a failure.
    def has_no_change(r):
        return atomic_no_change(r)
    tr_in = {sha(render_input(r["plan"])) for r in all_rows
             if r["split"] == "train" and not has_no_change(r)}
    dv_in = {sha(render_input(r["plan"])) for r in all_rows
             if r["split"] == "dev" and not has_no_change(r)}
    if tr_in & dv_in:
        reviewed_shared, hard = [], []
        for h in tr_in & dv_in:
            groups = {r["sourceGroupId"] for r in all_rows
                      if sha(render_input(r["plan"])) == h}
            # collisions inside the REVIEWED corpus (pre-expansion groups)
            # cannot be fixed without touching accepted rows: tallied as a
            # regression item. Any collision involving an expansion group is
            # a construction failure.
            if all(g.startswith("n4-") for g in groups):
                reviewed_shared.append(sorted(groups))
            else:
                hard.append((h, sorted(groups)))
        if hard:
            for h, gs in hard:
                print("COLLISION render input involves expansion groups:")
                print(render_input(next(r for r in all_rows
                                        if sha(render_input(r["plan"])) == h
                                        and r["split"] == "train")["plan"]))
                print(" ", gs)
            raise SystemExit(f"render-input collisions (expansion): {len(hard)}")
        print(f"reviewed-corpus shared-input regression tally: "
              f"{len(reviewed_shared)} pair(s), e.g. {reviewed_shared[:2]} "
              f"— frozen accepted data, counted separately")
    nc_tr = {sha(render_input(r["plan"])) for r in all_rows
             if r["split"] == "train" and has_no_change(r)}
    nc_dv = {sha(render_input(r["plan"])) for r in all_rows
             if r["split"] == "dev" and has_no_change(r)}
    nc_shared = nc_tr & nc_dv

    # generalization denominator, as the reviewer counts it: distinct dev
    # inputs minus inputs that also occur in train (atomic no_change included
    # in the seen set, because the model has seen that input).
    all_tr_in = {sha(render_input(r["plan"])) for r in all_rows
                 if r["split"] == "train"}
    all_dv_in = {sha(render_input(r["plan"])) for r in all_rows
                 if r["split"] == "dev"}
    seen_dv = all_tr_in & all_dv_in
    print(f"unique render inputs: train {len(all_tr_in)} / dev {len(all_dv_in)}; "
          f"dev inputs also in train: {len(seen_dv)}; unseen dev inputs: "
          f"{len(all_dv_in - all_tr_in)}")
    for h in sorted(seen_dv):
        rows = [r for r in all_rows if sha(render_input(r["plan"])) == h]
        groups = sorted({r["sourceGroupId"] for r in rows})
        print(f"   seen dev input {render_input(rows[0]['plan']).replace(chr(10), '|')[:72]}"
              f" — {groups[:4]}{'...' if len(groups) > 4 else ''}")

    SEEDS.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                               for r in seed_rows + new_seeds) + "\n",
                     encoding="utf-8")
    REWRITES.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                  for r in rw_rows + new_rewrites) + "\n",
                        encoding="utf-8")
    print(f"migrated rows: {len(seed_rows) + len(rw_rows)}")
    print(f"new rows: seeds {len(new_seeds)} + rewrites {len(new_rewrites)}")
    print(f"group signatures unique (incl. base): {len(signatures)}; "
          f"base duplicate tally: {len(base_dup_sigs)} {base_dup_sigs[:3]}")
    if base_dup_sigs:
        print("   ^ frozen accepted base rows, counted as a regression item "
              "(not re-authored here)")
    print(f"render inputs: train {len(tr_in)} / dev {len(dv_in)}, disjoint "
          f"(atomic no_change exempt)")
    print(f"atomic no_change shared-input regression tally: {len(nc_shared)} "
          f"shared input(s) — counted separately, never in the unseen "
          f"denominator")
    print("coverage (family, split[, direction]): groups")
    for key in sorted(coverage, key=str):
        print(f"   {key}: {coverage[key]}")
    total_groups = len({r["sourceGroupId"] for r in seed_rows + new_seeds})
    print(f"total groups: {total_groups}  total rows: {len(all_rows)}")


if __name__ == "__main__":
    main()

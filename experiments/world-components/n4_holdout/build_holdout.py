# N4 independent holdout builder (round 14, post-r3 acceptance).
#
# Purpose: build fact plans that participated in NOTHING — not training, not
# the r2/r3 development selection, not recognizer/rule revisions. The r3
# direction result (53/53 dev inputs) is development evidence; the quality
# gate needs a sample the model has never seen under a FROZEN renderer,
# checkpoint and judge.
#
# Isolation rules:
# - new cast / locations / tasks / appearances / personalities / durations
#   (disjoint from both the training corpus vocabulary and every duration
#   used by the 600-row corpus: 1-8,10,12,15,20,25,30,40,45,60,90 minutes;
#   this file uses 9/11/13/18/22/35/50/75)
# - every rendered input must be absent from all 600 corpus rows (asserted
#   at build time), so no holdout prompt was seen during training or selection
# - no rewrite targets are authored here: rows carry a program template text
#   for schema/checker validation only; acceptance judges the MODEL output
#   against the plan, never against this reference text
# - the holdout is built ONCE, then frozen by freeze_r3.py before the single
#   acceptance run. Do not edit or regenerate after seeing model outputs.
#
# Usage: python experiments/world-components/n4_holdout/build_holdout.py
# Output: experiments/world-components/n4_holdout/holdout.jsonl

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
CORPUS_DIR = HERE.parent / "n4_corpus"
sys.path.insert(0, str(CORPUS_DIR))
from n4_render import num_cn, UNIT_CN, render_input  # noqa: E402

OUT = HERE / "holdout.jsonl"

FAMILIES = ["loc", "empty", "task", "chain", "appear", "multi"]
GROUPS_PER_FAMILY = 4

NAMES = ["陆知微", "江砚白", "顾青梧", "秦照野", "温屿",
         "苏砚", "白露生", "沈星回", "程望舒", "柳含烟"]
LOCS = ["柳堤", "药圃", "旧书阁", "望江亭", "白矾巷",
        "南屏桥", "梅坞", "半山亭", "听雨轩", "落霞渡"]
TASKS = ["把风灯挂上檐角", "整理旧书阁", "修补药圃的篱笆",
         "把药篓送到柳堤", "修好南屏桥的栏杆", "给望江亭换一块匾",
         "把柴担挑到半山亭", "收起听雨轩的竹帘"]
APPEARANCES = ["檐下水痕洇成了深色", "门轴的响声变得尖了",
               "石阶上落了厚厚一层松针", "窗棂的漆色暗了下去",
               "井沿的砖缝透出湿气", "墙头的草叶枯了大半",
               "廊下的灯笼歪向一边", "池边的木栏松了一根"]
PERSONALITIES = ["变得从容", "变得温和", "变得沉静", "变得利落",
                 "变得随和", "变得热络", "变得爽快", "变得安静"]
DURATIONS = [(9, "minute"), (11, "minute"), (13, "minute"), (18, "minute"),
             (22, "minute"), (35, "minute"), (50, "minute"), (75, "minute")]

LOC_ID = {name: f"loc_{300 + i:03d}" for i, name in enumerate(LOCS)}
LOC_NAME = {v: k for k, v in LOC_ID.items()}
CHARS = {}
for i, name in enumerate(NAMES):
    home = LOCS[i % len(LOCS)]
    tasks = [(f"task_{300 + i * 2 + j:03d}", TASKS[(i * 2 + j) % len(TASKS)])
             for j in range(2)]
    CHARS[name] = {"id": f"char_{300 + i:03d}", "home": LOC_ID[home],
                   "sanity": 9 + (i % 8), "personality": "平常",
                   "tasks": tasks}


def canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def make_row(gid, world, raw_delta, full_plan, plan, scope, text, claims,
             purpose):
    return {
        "sourceGroupId": gid, "rowOrigin": "template-seed", "rewriter": "program",
        "task": "n4-sentence", "split": "holdout", "tier": "holdout",
        "world": world, "rawDelta": raw_delta,
        "fullPlan": full_plan, "plan": plan, "timeScope": scope,
        "planOnlyClaims": claims,
        "planConstruction": {"method": "program-enum-holdout-v1",
                             "note": "独立留出：新词表、新时长；未参与训练/调参/规则修订"},
        "planValidation": {
            "authority": "validate_plan_authority.py --rows holdout.jsonl -> holdout-authority-report.json",
            "note": "来源核对与 Δ 对账跑在 fullPlan 上；正文只对 plan 负责"},
        "text": text, "planRefs": refs_for(text, plan),
        "mustExpress": [e["ref"] for e in plan], "mayMention": [],
        "mustNotAdd": "不得新增：其他实体的动作、对话、评价、未登记实体",
        "hashes": {"plan": sha(canon(plan)), "fullPlan": sha(canon(full_plan)),
                   "world": sha(canon(world)),
                   "rawDelta": sha(canon(raw_delta)), "text": sha(text)},
        "purpose": purpose,
    }


def build_world(names, extra_locs):
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


def build_group(family, idx):
    dur_a, dur_u = DURATIONS[idx % len(DURATIONS)]
    dur_cn = f"{num_cn(dur_a)}{UNIT_CN[dur_u]}"
    name1 = NAMES[idx % len(NAMES)]
    reg1 = CHARS[name1]
    home_name = LOC_NAME[reg1["home"]]
    task_id, goal = reg1["tasks"][idx % len(reg1["tasks"])]
    desc = APPEARANCES[idx % len(APPEARANCES)]
    pers = PERSONALITIES[idx % len(PERSONALITIES)]
    gid = f"n4h-{family}-{idx + 1:02d}"

    target = None
    for off in range(1, len(LOCS)):
        cand = LOCS[(idx * 3 + off) % len(LOCS)]
        if cand != home_name:
            target = cand
            break
    assert target is not None and target != home_name

    if family == "loc":
        world = build_world([name1], [home_name, target])
        deltas = [{"entityId": reg1["id"],
                   "positionSet": {"containerId": LOC_ID[target]}}]
        main_s = f"{name1}从{home_name}来到{target}。"
        facts = [{"kind": "moved", "entityId": reg1["id"], "name": name1,
                  "from": home_name, "to": target}]
        claims = []
    elif family == "empty":
        world = build_world([name1], [])
        deltas = []
        main_s = "一切如旧。"
        facts = [{"kind": "no_change", "scope": "全局"}]
        claims = [{"kind": "no_change", "scope": "全局"}]
    elif family == "task":
        world = build_world([name1], [])
        deltas = [{"entityId": reg1["id"], "tasksAchieved": [task_id]}]
        main_s = f"{name1}完成了任务「{goal}」。"
        facts = [{"kind": "task_achieved", "entityId": reg1["id"],
                  "name": name1, "goal": goal}]
        claims = []
    elif family == "chain":
        world = build_world([name1], [])
        up = idx % 2 == 0
        to = min(reg1["sanity"] + 3, 20) if up else max(reg1["sanity"] - 3, 1)
        deltas = [{"entityId": reg1["id"], "tasksAchieved": [task_id]},
                  {"entityId": reg1["id"],
                   "personalityChanges": [{"id": f"chg_{gid}", "text": pers,
                                           "supersedes": []}]},
                  {"entityId": reg1["id"], "sanitySet": to}]
        verb = "升" if to > reg1["sanity"] else "降"
        main_s = (f"{name1}完成了任务「{goal}」，{pers}，"
                  f"精神值从{reg1['sanity']}{verb}到了{to}。")
        facts = [{"kind": "task_achieved", "entityId": reg1["id"],
                  "name": name1, "goal": goal},
                 {"kind": "personality_changed", "entityId": reg1["id"],
                  "name": name1, "text": pers},
                 {"kind": "sanity_changed", "entityId": reg1["id"],
                  "name": name1, "from": reg1["sanity"], "to": to}]
        claims = []
    elif family == "appear":
        world = build_world([name1], [home_name, target])
        deltas = [{"entityId": LOC_ID[home_name],
                   "appearanceChanges": [{"id": f"chg_{gid}", "text": desc,
                                          "supersedes": []}]}]
        main_s = f"{home_name}的外观变了：{desc}。"
        facts = [{"kind": "appearance_changed", "entityId": LOC_ID[home_name],
                  "name": home_name, "text": desc}]
        claims = []
    else:  # multi
        other = NAMES[(idx + 5) % len(NAMES)]
        reg_o = CHARS[other]
        world = build_world([name1, other], [home_name, target])
        for ch in world["characters"]:
            if ch["name"] == other:
                ch["homeLocId"] = LOC_ID[target]
        deltas = [{"entityId": reg1["id"],
                   "positionSet": {"containerId": LOC_ID[target]}}]
        main_s = f"{name1}从{home_name}来到{target}时，{other}已经在{target}了。"
        facts = [{"kind": "moved", "entityId": reg1["id"], "name": name1,
                  "from": home_name, "to": target},
                 {"kind": "positioned_at", "entityId": reg_o["id"],
                  "name": other, "at": target}]
        claims = [{"kind": "positioned_at", "entityId": reg_o["id"],
                   "name": other, "at": target}]

    full_plan = [dict(e, ref=i) for i, e in enumerate(facts)]
    full_plan.append({"kind": "time", "amount": dur_a, "unit": dur_u,
                      "rendered": dur_cn, "ref": len(facts)})
    raw_delta = {"entityDeltas": deltas,
                 "time": {"amount": dur_a, "unit": dur_u, "rendered": dur_cn}}
    rows = []
    for scope in ("expressed", "omitted"):
        plan = full_plan if scope == "expressed" else strip_time(full_plan)
        text = (main_s + f"前后大约{dur_cn}。" if scope == "expressed"
                else main_s)
        rows.append(make_row(gid, world, raw_delta, full_plan, plan, scope,
                             text, claims,
                             f"N4 独立留出验收 {family}/{scope}（未参与训练/调参）"))

    # expressed and omitted plans must share every non-time fact (round-13
    # review check, asserted here as well)
    def non_time(p):
        return [{k: v for k, v in e.items() if k != "ref"}
                for e in p if e["kind"] != "time"]
    assert non_time(rows[0]["plan"]) == non_time(rows[1]["plan"]), gid
    return rows


def atomic_no_change(r) -> bool:
    return bool(r["plan"]) and all(e["kind"] == "no_change" for e in r["plan"])


def corpus_inputs() -> set:
    out = set()
    for name in ("corpus.seeds.jsonl", "rewrites.jsonl"):
        p = CORPUS_DIR / name
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.add(sha(render_input(json.loads(line)["plan"])))
    return out


def main() -> None:
    rows = []
    for family in FAMILIES:
        for i in range(GROUPS_PER_FAMILY):
            rows.extend(build_group(family, i))

    train_inputs = corpus_inputs()
    if train_inputs:
        overlap = [r for r in rows if sha(render_input(r["plan"])) in train_inputs]
        hard = [r for r in overlap if not atomic_no_change(r)]
        shared = [r for r in overlap if atomic_no_change(r)]
        if hard:
            for r in hard:
                print("INPUT OVERLAP with corpus:", r["sourceGroupId"],
                      r["timeScope"])
            raise SystemExit(f"holdout inputs overlap the corpus: {len(hard)}")
        # The atomic omitted-time no_change plan has exactly one rendering
        # ("无变化"), which necessarily exists in the corpus. It is a SHARED
        # regression input: reported separately and never counted in the
        # unseen acceptance denominator (review rule, round 12/14).
        shared_inputs = {sha(render_input(r["plan"])) for r in shared}
        print(f"holdout rows: {len(rows)}; shared atomic no_change input(s): "
              f"{len(shared_inputs)} ({len(shared)} rows) — regression, "
              f"excluded from the unseen denominator")
        print(f"corpus inputs: {len(train_inputs)} (no other overlap)")
    else:
        print(f"holdout rows: {len(rows)}; corpus not found, overlap check skipped")

    # every non-atomic row must have its own input; the atomic no_change rows
    # legitimately collapse to one shared input (handled as regression)
    non_atomic = [r for r in rows if not atomic_no_change(r)]
    non_atomic_inputs = {sha(render_input(r["plan"])) for r in non_atomic}
    if len(non_atomic_inputs) != len(non_atomic):
        raise SystemExit("holdout non-atomic render inputs are not unique")
    inputs = non_atomic_inputs | {sha(render_input(r["plan"]))
                                  for r in rows if atomic_no_change(r)}
    print(f"distinct holdout inputs: {len(inputs)} = {len(non_atomic_inputs)} "
          f"unseen + {len(inputs) - len(non_atomic_inputs)} shared regression")
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                             for r in rows) + "\n", encoding="utf-8")
    print(f"groups: {len({r['sourceGroupId'] for r in rows})}  "
          f"inputs: {len(inputs)}  -> {OUT}")


if __name__ == "__main__":
    main()

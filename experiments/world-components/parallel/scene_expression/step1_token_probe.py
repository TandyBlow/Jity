"""Step 1 补充：旧模板输入长度余量，以及样本事实能否落进旧模板。

只读：u240 训练用的三个单元池、冻结样本导出 JSON。
只写：step1/step1-token-probe.json。

用法（仓库根）：
  /d/software/Anaconda/envs/nndl_proj/python.exe -X utf8 \
    experiments/world-components/parallel/scene_expression/step1_token_probe.py
"""
import json
import pathlib
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DEV = ROOT / "experiments/world-components/n4_narrative_dev"
OUT = HERE / "step1"
EXPORT = OUT / "narration-split-samples.export.json"
TARGETS = ["ns-appear-1", "ns-loc-appear-1", "ns-task-1", "ns-task-time-1",
           "ns-pers-1", "ns-multi-1", "ns-empty-1", "ns-cont-1", "ns-cont-2",
           "ns-cont-3"]
MODEL_DIR = pathlib.Path(r"D:\others\Jity\.local\models")

# 与 fact_contract.build_unit_input 末尾逐字相同的固定要求行（仅用于长度对比：
# 契约检查会拒收含拉丁字母的名字，量长度时仍保留完整尾部）
REQ_TAIL = ("\n要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；"
            "只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；"
            "不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。\n短句：\n")


def tokenizer():
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    return T5Tokenizer.from_pretrained(str(MODEL_DIR), legacy=False,
                                       local_files_only=True)


def n_tokens(tok, text):
    return len(tok(text)["input_ids"])


def dist(tok, texts):
    vals = sorted(n_tokens(tok, t) for t in texts)
    return {"count": len(vals), "min": vals[0],
            "p50": statistics.median(vals),
            "p95": vals[int(round(0.95 * (len(vals) - 1)))], "max": vals[-1]}


def training_pools():
    """u240 训练实际使用的三个单元池（train_routed_arms.py 顶部常量）。"""
    pools = {
        "verbalizerPairs": DEV / "verbalizer_pairs.jsonl",
        "expand78": ROOT / "artifacts/world-components/n4-expand78-unified.jsonl",
        "objects40": ROOT / "artifacts/world-components/n4-object-train40-clean.jsonl",
    }
    out = {}
    for name, path in pools.items():
        rows = [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]
        out[name] = {"path": str(path.relative_to(ROOT)), "units": len(rows),
                     "inputs": [r["input"] for r in rows]}
    return out


def scene_materials(state):
    """从已提交状态取可见素材；每项带 entityId 与 fieldPath 来源。"""
    initial = state["initial"]
    proto = state["protagonistId"]
    place = state["characters"][proto]["position"]["containerId"]
    loc_name = initial["locations"][place]["name"]

    loc = state["locations"].get(place, {})
    loc_initial = initial["locations"][place].get("initialAppearance") or ""
    loc_changes = [c["text"] for c in loc.get("appearanceChanges", [])
                   if c.get("active", True)]

    visible = []
    for iid, item in state["items"].items():
        if (item.get("position") or {}).get("containerId") != place:
            continue
        base = initial["items"][iid]
        texts = [base.get("initialAppearance") or ""]
        texts += [c["text"] for c in item.get("appearanceChanges", [])
                  if c.get("active", True)]
        visible.append({"entityId": iid, "name": base["name"],
                        "fieldPath": f"items.{iid}.initialAppearance+appearanceChanges",
                        "appearance": "；".join(t for t in texts if t)})

    people = []
    for cid, ch in state["characters"].items():
        if (ch.get("position") or {}).get("containerId") != place:
            continue
        base = initial["characters"][cid]
        pers = base.get("initialPersonality") or ""
        pers += "".join(c["text"] for c in ch.get("personalityChanges", [])
                        if c.get("active", True))
        goals = [t["goal"] for t in ch.get("tasks", {}).values()
                 if t.get("status") != "achieved"]
        people.append({"entityId": cid, "name": base["name"],
                       "fieldPath": f"characters.{cid}.initialPersonality/"
                                    "personalityChanges/tasks",
                       "personality": pers, "tasks": goals})

    return {"place": place, "locName": loc_name,
            "locAppearance": "；".join(t for t in [loc_initial] + loc_changes if t),
            "locFieldPath": f"locations.{place}.initialAppearance+appearanceChanges",
            "visible": visible, "people": people,
            "hour": state["time"]["dateTime"][11:16]}


def headers(mat):
    """A / B / C 三档场景头。只加素材字段，不加指导语。"""
    vis = "、".join(v["name"] for v in mat["visible"]) or "无"
    a = [f"地点={mat['locName']}", f"地点可见={vis}",
         f"场景={mat['hour']}", "视角=主角；第三人称"]
    b = a + [f"地点外貌={mat['locAppearance'] or '未登记'}"]
    b += [f"{v['name']}外貌={v['appearance']}" for v in mat["visible"] if v["appearance"]]
    c = b + [f"{p['name']}｜性格={p['personality'] or '未登记'}"
             f"｜任务={'、'.join(p['tasks']) or '无'}" for p in mat["people"]]
    return {"A": "\n".join(a) + "\n", "B": "\n".join(b) + "\n",
            "C": "\n".join(c) + "\n"}


def fact_spec(rf, before, names):
    """样本 requiredFact → 旧契约事实；不能表达的返回 (None, 原因)。"""
    kind = rf["kind"]
    name = names.get(rf.get("entityId"), rf.get("entityId"))
    if kind == "position":
        return {"kind": "moved", "name": name,
                "from": rf["fromName"], "to": rf["toName"]}, None
    if kind == "appearanceText":
        return {"kind": "appearance_changed", "name": name, "text": rf["text"]}, None
    if kind == "personalityText":
        return {"kind": "personality_changed", "name": name, "text": rf["text"]}, None
    if kind == "sanityValue":
        old = before["characters"][rf["entityId"]]["sanity"]
        return {"kind": "sanity_changed", "name": name,
                "from": old, "to": rf["value"]}, None
    if kind == "taskGoal":
        return None, "taskGoal 只能作为结果内容进入 结果，但契约禁止把 goal 当 resultText"
    if kind in ("timePassage", "timeReached"):
        return None, f"{kind} 在旧契约里没有对应事实行"
    return None, f"未知种类 {kind}"


def name_map(state):
    initial = state["initial"]
    out = {}
    for group in ("characters", "items", "locations"):
        for eid, ent in initial[group].items():
            out[eid] = ent["name"] if "name" in ent else eid
    return out


def main():
    sys.path.insert(0, str(DEV))
    from fact_contract import build_unit_input

    tok = tokenizer()
    doc = {"step": "1b"}

    pools = training_pools()
    doc["trainingInputs"] = {
        name: {**{k: v for k, v in p.items() if k != "inputs"},
               "tokens": dist(tok, p["inputs"])}
        for name, p in pools.items()}

    samples = json.loads(EXPORT.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in samples["samples"]}
    doc["samplesSource"] = {"file": str(EXPORT.relative_to(ROOT)),
                            "sourceSha256": samples["sourceSha256"]}

    rows = []
    for sid in TARGETS:
        s = by_id[sid]
        mat = scene_materials(s["after"])
        hdrs = headers(mat)
        names = name_map(s["after"])

        facts, gaps = [], []
        for rf in s["requiredFacts"]:
            spec, why = fact_spec(rf, s["before"], names)
            if spec is None:
                gaps.append({"kind": rf["kind"], "why": why})
            else:
                facts.append(spec)

        per_fact = []
        for spec in facts:
            counts, contract = {}, {}
            for arm, hdr in hdrs.items():
                try:
                    text = build_unit_input(hdr, spec)
                    contract[arm] = "ok"
                except Exception as exc:  # 契约拒收：名字含拉丁字母等
                    from fact_contract import serialize_fact
                    line = serialize_fact(spec)
                    text = hdr + f"事实={line}" + REQ_TAIL
                    contract[arm] = f"{type(exc).__name__}: {exc}"
                counts[arm] = n_tokens(tok, text)
            per_fact.append({"kind": spec["kind"], "name": spec["name"],
                             "contract": contract, **counts})
        worst = max((c[arm] for c in per_fact for arm in "ABC"), default=0)
        rows.append({"sampleId": sid, "place": mat["place"],
                     "locName": mat["locName"],
                     "requiredKinds": [rf["kind"] for rf in s["requiredFacts"]],
                     "expressibleFacts": len(facts), "templateGaps": gaps,
                     "visibleItems": len(mat["visible"]),
                     "peopleAtPlace": len(mat["people"]),
                     "headerChars": {k: len(v) for k, v in hdrs.items()},
                     "unitTokens": per_fact, "maxUnitTokens": worst})

    doc["perSample"] = rows
    gaps = {}
    for r in rows:
        for g in r["templateGaps"]:
            gaps[g["kind"]] = gaps.get(g["kind"], 0) + 1
    doc["templateGapTotals"] = gaps
    doc["contractRejected"] = sum(
        1 for r in rows for f in r["unitTokens"]
        for v in f["contract"].values() if v != "ok")
    doc["trainingMaxInputTokens"] = max(
        doc["trainingInputs"][k]["tokens"]["max"] for k in doc["trainingInputs"])

    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "step1-token-probe.json"
    dst.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    print(json.dumps(doc["trainingInputs"], ensure_ascii=False, indent=1))
    print("training max input tokens:", doc["trainingMaxInputTokens"])
    print("template gaps:", json.dumps(gaps, ensure_ascii=False))
    for r in rows:
        print(f"{r['sampleId']:18s} facts={r['expressibleFacts']} "
              f"gaps={[g['kind'] for g in r['templateGaps']]} "
              f"items={r['visibleItems']} people={r['peopleAtPlace']} "
              f"maxUnitTokens={r['maxUnitTokens']}")
    print("保存:", dst)


if __name__ == "__main__":
    main()

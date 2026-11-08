"""冻结三臂输入：素材来源表 + 每条可表达事实的模型输入 + 程序句。

只读：step1/narration-split-samples.export.json（TS 样本的导出）。
只写：frozen/materials.json、frozen/inputs.json、frozen/manifest.json。

规则全部写在 freeze-protocol.md；本脚本是它的可执行副本。改动脚本等于改协议，
必须重跑并更新 manifest。

用法（仓库根）：
  /d/software/Anaconda/envs/nndl_proj/python.exe -X utf8 \
    experiments/world-components/parallel/scene_expression/build_inputs.py
"""
import hashlib
import json
import pathlib
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
EXPORT = HERE / "step1/narration-split-samples.export.json"
FROZEN = HERE / "frozen"

TARGETS = ["ns-appear-1", "ns-loc-appear-1", "ns-task-1", "ns-task-time-1",
           "ns-pers-1", "ns-multi-1", "ns-empty-1", "ns-cont-1", "ns-cont-2",
           "ns-cont-3"]
DEV_ONLY = ["ns-pos-1"]

# 与 fact_contract.build_unit_input 逐字相同的尾部；包装器只跳过 check_line 的
# 姓名正则（样本名字含拉丁字母），不新增、不改写任何事实行。
REQ_TAIL = ("\n要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；"
            "只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；"
            "不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。\n短句：\n")

UNIT_CN = {"second": "秒", "minute": "分钟", "hour": "小时", "day": "天",
           "month": "个月", "year": "年"}
CN_SMALL = {0: "零", 1: "一", 2: "两", 3: "三", 4: "四", 5: "五", 6: "六",
            7: "七", 8: "八", 9: "九", 10: "十"}


def cn_num(n):
    return CN_SMALL[n] if isinstance(n, int) and 0 <= n <= 10 else str(n)


def hour_word(hh):
    hour = int(str(hh).split(":")[0])
    if hour < 11:
        return "上午"
    if hour < 13:
        return "中午"
    if hour < 18:
        return "下午"
    if hour < 22:
        return "傍晚"
    return "晚上"


def join_texts(texts):
    """拼接素材时去掉每段末尾的句末标点，避免「。；」。素材原文不变。"""
    return "；".join(t.rstrip("。；，") for t in texts if t)


def active_changes(entity):
    return [c for c in entity.get("appearanceChanges", [])
            if c.get("active", True)]


def material_pool(sample):
    """按协议取素材：当前有效、主角视角可见。每项都有来源路径。"""
    st = sample["after"]
    ini = st["initial"]
    proto = st["protagonistId"]
    place = st["characters"][proto]["position"]["containerId"]
    loc_name = ini["locations"][place]["name"]

    pool = {"location": [], "items": [], "characters": [], "previousNarration": []}

    base = ini["locations"][place]
    if base.get("initialAppearance"):
        pool["location"].append({
            "sourceId": f"loc:{place}:initialAppearance",
            "entityId": place, "fieldPath": f"initial.locations.{place}.initialAppearance",
            "text": base["initialAppearance"], "visibleToPerspective": True,
            "effectiveAtPoint": "state-initial",
        })
    for chg in active_changes(st["locations"].get(place, {})):
        pool["location"].append({
            "sourceId": f"loc:{place}:change:{chg['id']}",
            "entityId": place,
            "fieldPath": f"after.locations.{place}.appearanceChanges[{chg['id']}].text",
            "text": chg["text"], "visibleToPerspective": True,
            "effectiveAtPoint": sample["after"]["time"]["dateTime"],
        })

    for iid, item in st["items"].items():
        if (item.get("position") or {}).get("containerId") != place:
            continue
        ibase = ini["items"][iid]
        if ibase.get("initialAppearance"):
            pool["items"].append({
                "sourceId": f"item:{iid}:initialAppearance",
                "entityId": iid, "name": ibase["name"],
                "fieldPath": f"initial.items.{iid}.initialAppearance",
                "text": ibase["initialAppearance"], "visibleToPerspective": True,
                "effectiveAtPoint": "state-initial",
            })
        for chg in active_changes(item):
            pool["items"].append({
                "sourceId": f"item:{iid}:change:{chg['id']}",
                "entityId": iid, "name": ibase["name"],
                "fieldPath": f"after.items.{iid}.appearanceChanges[{chg['id']}].text",
                "text": chg["text"], "visibleToPerspective": True,
                "effectiveAtPoint": sample["after"]["time"]["dateTime"],
            })

    for cid, person in st["characters"].items():
        if (person.get("position") or {}).get("containerId") != place:
            continue
        cbase = ini["characters"][cid]
        if cbase.get("initialPersonality"):
            pool["characters"].append({
                "sourceId": f"char:{cid}:initialPersonality",
                "entityId": cid, "name": cbase["name"], "kind": "personality",
                "fieldPath": f"initial.characters.{cid}.initialPersonality",
                "text": cbase["initialPersonality"], "visibleToPerspective": True,
                "effectiveAtPoint": "state-initial",
            })
        for chg in person.get("personalityChanges", []):
            if not chg.get("active", True):
                continue
            pool["characters"].append({
                "sourceId": f"char:{cid}:personalityChange:{chg['id']}",
                "entityId": cid, "name": cbase["name"], "kind": "personality",
                "fieldPath": f"after.characters.{cid}.personalityChanges[{chg['id']}].text",
                "text": chg["text"], "visibleToPerspective": True,
                "effectiveAtPoint": sample["after"]["time"]["dateTime"],
            })
        for tid, task in person.get("tasks", {}).items():
            if task.get("status") == "achieved":
                continue
            pool["characters"].append({
                "sourceId": f"char:{cid}:task:{tid}:goal",
                "entityId": cid, "name": cbase["name"], "kind": "taskGoal",
                "fieldPath": f"after.characters.{cid}.tasks.{tid}.goal",
                "text": task["goal"], "visibleToPerspective": True,
                "effectiveAtPoint": sample["after"]["time"]["dateTime"],
            })

    # 数据集没有“上一段叙事”字段；C 臂的该类别记为缺失，不补造。
    pool["previousNarrationNote"] = "样本无上一段叙事字段；C 臂不含前文，缺口如实登记"
    pool["place"] = place
    pool["placeName"] = loc_name
    pool["pendingHour"] = st["time"]["dateTime"][11:16]
    return pool


def headers(pool):
    """三臂场景头；只加素材行，不加指导语。"""
    vis = [m["name"] for m in pool["items"] if m["sourceId"].endswith("initialAppearance")]
    scene = hour_word(pool["pendingHour"])
    base = [f"地点={pool['placeName']}",
            f"地点可见={'、'.join(vis) if vis else '无'}",
            f"场景={scene}",
            "视角=主角；第三人称"]
    b = list(base)
    loc_texts = [m["text"] for m in pool["location"]]
    if loc_texts:
        b.append(f"地点外貌={join_texts(loc_texts)}")
    for name in dict.fromkeys(m["name"] for m in pool["items"]):
        texts = [m["text"] for m in pool["items"] if m["name"] == name]
        if texts:
            b.append(f"{name}外貌={join_texts(texts)}")
    c = list(b)
    for cid in dict.fromkeys(m["entityId"] for m in pool["characters"]):
        pers = [m["text"] for m in pool["characters"]
                if m["entityId"] == cid and m["kind"] == "personality"]
        goals = [m["text"] for m in pool["characters"]
                 if m["entityId"] == cid and m["kind"] == "taskGoal"]
        name = next(m["name"] for m in pool["characters"] if m["entityId"] == cid)
        line = f"{name}｜"
        if pers:
            line += f"性格={join_texts(pers)}｜"
        if goals:
            line += f"任务={'、'.join(goals)}｜"
        c.append(line.rstrip("｜"))
    return {"A": "\n".join(base) + "\n", "B": "\n".join(b) + "\n",
            "C": "\n".join(c) + "\n"}


def model_fact(rf, sample, names):
    """requiredFact → 旧契约事实（只接受能表达的四种）。"""
    kind = rf["kind"]
    name = names.get(rf.get("entityId"), rf.get("entityId"))
    if kind == "position":
        return {"kind": "moved", "name": name, "from": rf["fromName"],
                "to": rf["toName"], "direction": "平"}
    if kind == "appearanceText":
        return {"kind": "appearance_changed", "name": name, "text": rf["text"]}
    if kind == "personalityText":
        return {"kind": "personality_changed", "name": name, "text": rf["text"]}
    if kind == "sanityValue":
        old = sample["before"]["characters"][rf["entityId"]]["sanity"]
        if rf["value"] == old:
            return None
        return {"kind": "sanity_changed", "name": name, "from": old,
                "to": rf["value"]}
    return None


def fact_line(fact):
    """与 fact_contract.serialize_fact 相同的写法。"""
    kind = fact["kind"]
    if kind == "moved":
        return f'{fact["name"]}｜移动｜{fact["from"]}→{fact["to"]}'
    if kind == "appearance_changed":
        return f'{fact["name"]}｜外貌变化｜{fact["text"]}'
    if kind == "personality_changed":
        return f'{fact["name"]}｜性格变化｜{fact["text"]}'
    if kind == "sanity_changed":
        up = fact["to"] > fact["from"]
        return f'{fact["name"]}｜状态变化｜{"放松" if up else "发紧"}'
    raise ValueError(kind)


def program_sentence(rf, sample, names):
    """程序句：沿用历史 composeSentences 模板；timeReached 用固定新句。"""
    kind = rf["kind"]
    name = names.get(rf.get("entityId"), rf.get("entityId"))
    if kind == "timePassage":
        return f'约{cn_num(rf["amount"])}{UNIT_CN[rf["unit"]]}过去了。'
    if kind == "timeReached":
        return "时间已到中午。" if rf["hour"] == 12 else f'时间已到{rf["hour"]}点。'
    if kind == "taskGoal":
        return f'{name}完成了任务「{rf["goal"]}」。'
    if kind == "sanityValue":
        old = sample["before"]["characters"][rf["entityId"]]["sanity"]
        word = "升为" if rf["value"] > old else "降为"
        return f'{name}的理智值{word}{rf["value"]}。'
    raise ValueError(kind)


def sanity_direction_fact(rf, sample, names):
    """理智方向交给模型：旧契约只有 放松/发紧，数值由程序句负责。"""
    old = sample["before"]["characters"][rf["entityId"]]["sanity"]
    if rf["value"] == old:
        return None
    return {"kind": "sanity_changed",
            "name": names.get(rf["entityId"], rf["entityId"]),
            "from": old, "to": rf["value"]}


def name_map(state):
    ini = state["initial"]
    out = {}
    for group in ("characters", "items", "locations"):
        for eid, ent in ini[group].items():
            out[eid] = ent.get("name", eid)
    return out


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head():
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()


def main():
    doc = json.loads(EXPORT.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in doc["samples"]}

    materials, inputs = {}, {}
    for sid in TARGETS + DEV_ONLY:
        s = by_id[sid]
        pool = material_pool(s)
        pool["pendingHour"] = s["after"]["time"]["dateTime"][11:16]
        hdrs = headers(pool)
        names = name_map(s["after"])

        slots = []
        for rf in s["requiredFacts"]:
            if rf["kind"] == "sanityValue":
                # 固定顺序：先模型方向句，后程序数值句。
                direction = sanity_direction_fact(rf, s, names)
                if direction is not None:
                    line = fact_line(direction)
                    slots.append({"owner": "model", "kind": "sanity_changed",
                                  "phrase": f'{names.get(rf["entityId"])}理智方向',
                                  "factLine": line,
                                  "prompts": {arm: hdrs[arm] + f"事实={line}" + REQ_TAIL
                                              for arm in "ABC"}})
                slots.append({"owner": "program", "kind": rf["kind"],
                              "phrase": rf["phrase"],
                              "programText": program_sentence(rf, s, names)})
                continue
            fact = model_fact(rf, s, names)
            if fact is None:
                slots.append({"owner": "program", "kind": rf["kind"],
                              "phrase": rf["phrase"],
                              "programText": program_sentence(rf, s, names)})
                continue
            line = fact_line(fact)
            calls = {arm: hdrs[arm] + f"事实={line}" + REQ_TAIL for arm in "ABC"}
            slots.append({"owner": "model", "kind": rf["kind"],
                          "phrase": rf["phrase"], "factLine": line,
                          "prompts": calls})

        materials[sid] = {"place": pool["place"], "placeName": pool["placeName"],
                          "location": pool["location"], "items": pool["items"],
                          "characters": pool["characters"],
                          "previousNarration": pool["previousNarration"],
                          "previousNarrationNote": pool["previousNarrationNote"],
                          "headers": hdrs}
        inputs[sid] = {"sampleId": sid, "slots": slots,
                       "modelCallCount": sum(1 for x in slots if x["owner"] == "model")}

    FROZEN.mkdir(parents=True, exist_ok=True)
    m_path, i_path = FROZEN / "materials.json", FROZEN / "inputs.json"
    m_path.write_text(json.dumps(materials, ensure_ascii=False, indent=1), encoding="utf-8")
    i_path.write_text(json.dumps(inputs, ensure_ascii=False, indent=1), encoding="utf-8")

    docs = {}
    for name in ("freeze-protocol.md", "README.md", "frozen/prompt-tokens.json",
                 "step1/step1-verify.json", "step1/step1-token-probe.json"):
        path = HERE / name
        if path.exists():
            docs[name] = sha256(path)

    manifest = {
        "parentCommit": git_head(),
        "note": "提交本清单的提交即冻结提交；清单不记录自身提交号以免自指。",
        "samplesExport": {"path": str(EXPORT.relative_to(ROOT)),
                          "sha256": sha256(EXPORT),
                          "sourceSha256": doc["sourceSha256"]},
        "materials": {"path": str(m_path.relative_to(ROOT)), "sha256": sha256(m_path)},
        "inputs": {"path": str(i_path.relative_to(ROOT)), "sha256": sha256(i_path)},
        "targets": TARGETS, "devOnly": DEV_ONLY,
        "modelCallCounts": {sid: inputs[sid]["modelCallCount"] for sid in TARGETS},
        "builder": {"path": str(pathlib.Path(__file__).relative_to(ROOT)),
                    "sha256": sha256(pathlib.Path(__file__))},
        "docs": docs,
    }
    (FROZEN / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    for sid in TARGETS:
        n = inputs[sid]["modelCallCount"]
        print(f"{sid:17s} modelCalls={n}")
    print(json.dumps({k: v for k, v in manifest.items() if k not in ("targets", "docs")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

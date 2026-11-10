"""Build the independent acceptance set registration (no inference, no u240 output).

Every unit is assembled from fields that exist in the N4 world file
(`experiments/world-components/n4_narrative_dev/world.json`) or, where the value is
authored, marked `authored` with the world field it is derived from. The rendered
input uses the same template as cf24 so the two sets stay comparable.

The script also checks signature overlap against:
  * the three pinned u240 training pools (229 + 80 + 40)
  * cf24 (85), final24 (76), moved24 (24)

and writes:
  freeze/acceptance-registration-v2.json
  results/acceptance-registration-v2.md

v2 (2026-11-09) fixes provenance after review:
  * ac01 uses task_lamp.resultText, not the goal sentence (goal != outcome)
  * su01 is authored: the subject was swapped from the task owner to 韩渡
  * moved units are marked `derived` from location levels; world.json has no action log
  * sa01/sa02 hide the sanity number, so the criterion is "no number may appear",
    not numeric fidelity
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve()
EXPERIMENT = HERE.parents[1]
TREE = HERE.parents[5]
NEXT = Path(os.environ.get("JITY_REPO", "<repo>") + "/.local/world-components-next-worktree")

WORLD = TREE / "experiments/world-components/n4_narrative_dev/world.json"
POOLS = [
    ("verbalizer", TREE / "experiments/world-components/n4_narrative_dev/verbalizer_pairs.jsonl"),
    ("expand-train80", NEXT / "artifacts/next-inputs/world-components/n4-expand-train80.jsonl"),
    ("object-train40", NEXT / "artifacts/next-inputs/world-components/n4-object-train40.jsonl"),
]
OTHER_SETS = [
    ("cf24", TREE / "artifacts/world-components/n4-cf24-contract.jsonl"),
    ("final24", NEXT / "artifacts/next-inputs/world-components/n4-final24-contract.jsonl"),
    ("moved24", NEXT / "artifacts/next-inputs/world-components/n4-moved24-contract.jsonl"),
]

TEMPLATE = (
    "短句任务。\n"
    "地点={place}\n"
    "地点可见={visible}\n"
    "场景={scene}\n"
    "视角={viewer}；第三人称\n"
    "事实={fact_line}\n"
    "{direction_line}"
    "要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；"
    "只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；"
    "不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。\n"
    "短句：\n"
)

KIND_LABEL = {
    "outcome": "结果",
    "appearance_changed": "外貌变化",
    "moved": "移动",
    "sanity_changed": "状态变化",
}

# visible lists come from the world sublocations; extra items named by the fact are
# appended (same handling cf24 used for e.g. 鱼筐), so the fact never contradicts
# the visible list on purpose.
UNITS = [
    # --- extra_action_state: the fact is plain, so any tail clause is an addition ---
    dict(id="ac01", kind="outcome", subject="韩渡", value="换好了塔顶的灯芯",
         place=("旧灯塔", "塔顶"), visible=["铜框信号灯", "玻璃罩", "火苗", "海风直吹", "备用灯芯"],
         scene="夜；夜雾，海风；铜灯已点亮", viewer="沈砚",
         source="world.json#tasks.task_lamp.resultText（主语由沈砚换成韩渡）", authored=True,
         provenance="authored", basis="subject swapped from the task owner; the sentence is verbatim resultText",
         focus="新增动作/状态",
         note="取 resultText 而非 goal（goal 是“把备用灯芯送到塔顶”，不是结果）；主语是人工换的"),
    dict(id="ac02", kind="moved", subject="顾行舟", frm="雾堤", to="潮渡", direction="平",
         place=("潮渡", "栈桥"), visible=["木桩", "缆绳", "船灯", "水面"],
         scene="傍晚；雾；船灯", viewer="顾行舟",
         source="world.json#locations.loc_seawall, loc_ferry（同为 level1）", authored=False,
         provenance="derived", basis="location level comparison; world.json has no action log",
         focus="新增动作/状态", note="平向移动，无抵达后内容；该主体+起终点组合未在任何旧集出现"),
    dict(id="ac03", kind="appearance_changed", subject="油布包", value="边角磨出了线头",
         place=("潮生巷", "巷子"), visible=["湿石板", "纸灯笼", "排水沟", "墙根", "水洼", "油布包"],
         scene="雨停；入夜；纸灯笼", viewer="沈砚",
         source="world.json#items.item_oilcloth.appearance（边角磨白）+ authored 变化", authored=True,
         focus="新增动作/状态", note="外貌变化，只应有一处变化"),

    # --- position: two legitimate positions that must survive, one over-claim trap ---
    dict(id="po01", kind="outcome", subject="沈砚", value="把系泊绳拖回栈桥",
         place=("潮渡", "栈桥"), visible=["木桩", "缆绳", "船灯", "水面", "系泊绳"],
         scene="清晨；薄雾；船灯", viewer="沈砚",
         source="world.json#items.item_rope.afterPosition=loc_ferry_pier", authored=True,
         provenance="authored",
         basis="afterPosition only says the rope is at the pier; 沈砚 dragging it back is not recorded",
         focus="位置（合法位置不得删减）", note="终点位置来自 afterPosition；拖绳动作是人工补的"),
    dict(id="po02", kind="outcome", subject="阿棠", value="把鱼筐放在摊棚边",
         place=("早市", "摊棚"), visible=["帆布棚", "鱼筐", "案板", "石板", "银鳞鱼", "白汽"],
         scene="清晨；薄雾；棚下散光", viewer="阿棠",
         source="world.json#items.item_fishbasket.afterPosition=loc_market_stalls", authored=False,
         provenance="derived",
         basis="afterPosition says the basket is at the stalls; 阿棠 placing it there is inferred, not recorded",
         focus="位置（合法位置不得删减）", note="位置来自 afterPosition；放筐的人与动作是推导的；摊棚在可见清单里"),
    dict(id="po03", kind="moved", subject="顾行舟", frm="潮生巷", to="潮汐档案馆", direction="平",
         place=("潮汐档案馆", "长桌"), visible=["潮汐簿", "墨", "干纸", "铜灯", "笔", "长桌"],
         scene="午后；阴；铜灯", viewer="顾行舟",
         source="world.json#locations.loc_archive, loc_alley", authored=False,
         provenance="derived", basis="location level comparison; world.json has no action log",
         focus="位置（过度断言风险）", note="可见清单有长桌，只授权存在；“在长桌边坐下”属过度断言"),

    # --- direction: 上 / 下 / 平 ---
    dict(id="di01", kind="moved", subject="韩渡", frm="潮渡", to="旧灯塔", direction="上",
         place=("旧灯塔", "塔顶"), visible=["铜框信号灯", "玻璃罩", "火苗", "海风直吹"],
         scene="夜；夜雾，海风", viewer="沈砚",
         source="world.json#locations.loc_ferry(level1) -> loc_lighthouse(level3)", authored=False,
         provenance="derived", basis="location level comparison; world.json has no action log",
         focus="方向", note="由低到高，方向=上"),
    dict(id="di02", kind="moved", subject="韩渡", frm="旧灯塔", to="潮渡", direction="下",
         place=("潮渡", "栈桥"), visible=["木桩", "缆绳", "船灯", "水面"],
         scene="清晨；薄雾；船灯", viewer="沈砚",
         source="world.json#locations.loc_lighthouse(level3) -> loc_ferry(level1)", authored=False,
         provenance="derived", basis="location level comparison; world.json has no action log",
         focus="方向", note="由高到低，方向=下"),
    dict(id="di03", kind="moved", subject="韩渡", frm="潮生巷", to="早市", direction="平",
         place=("早市", "摊棚"), visible=["帆布棚", "鱼筐", "案板", "石板", "银鳞鱼", "白汽"],
         scene="清晨；薄雾；棚下散光", viewer="韩渡",
         source="world.json#locations.loc_alley -> loc_market（同为 level1）", authored=False,
         provenance="derived", basis="location level comparison; world.json has no action log",
         focus="方向", note="同层移动，方向=平；不许出现高低措辞"),

    # --- subject ---
    dict(id="su01", kind="outcome", subject="韩渡", value="把被风吹歪的警示灯扶正",
         place=("雾堤", "堤面"), visible=["石壁", "钟架", "钟绳", "警示灯", "铁皮", "白沫"],
         scene="夜；浓雾；警示灯", viewer="韩渡",
         source="world.json#tasks.task_warnlamp.resultText，改用韩渡为主语", authored=True,
         provenance="authored", basis="subject swapped from the task owner (沈砚) to 韩渡",
         focus="主体归属", note="主体是人工换的，不是世界记录；不得把主体写成沈砚"),
    dict(id="su02", kind="appearance_changed", subject="阿棠", value="围裙上刮破了口子",
         place=("早市", "摊棚"), visible=["帆布棚", "鱼筐", "案板", "石板", "银鳞鱼", "白汽"],
         scene="清晨；薄雾；棚下散光", viewer="阿棠",
         source="world.json#characters.char_atang.appearance（围裙上有鱼鳞）+ authored 变化", authored=True,
         focus="主体归属", note="变化在围裙上，主体必须是阿棠"),

    # --- sanity_value ---
    dict(id="sa01", kind="sanity_changed", subject="沈砚", frm=12, to=7, descriptor="胸口发闷",
         place=("潮生巷", "巷子"), visible=["湿石板", "纸灯笼", "排水沟", "墙根", "水洼"],
         scene="雨后；雨停；纸灯笼", viewer="沈砚",
         source="authored（cf24 只有 12→9；此处换数值）", authored=True,
         provenance="authored", basis="new numbers; the number is deliberately absent from the input",
         focus="理智描述（输入不含数值）",
         criterion="不得出现具体数值；只要求写出“胸口发闷”这类描述；数值保真不在本单元验收范围",
         note="输入不含数字，判定只看是否编造数值"),
    dict(id="sa02", kind="sanity_changed", subject="韩渡", frm=15, to=11, descriptor="手抖",
         place=("雾堤", "堤面"), visible=["石壁", "钟架", "钟绳", "警示灯", "铁皮", "白沫"],
         scene="夜；浓雾；警示灯", viewer="韩渡",
         source="authored（新主体与新数值）", authored=True,
         provenance="authored", basis="new subject and numbers; the number is absent from the input",
         focus="理智描述（输入不含数值）",
         criterion="不得出现具体数值；只要求写出“手抖”这类描述；数值保真不在本单元验收范围",
         note="同上"),

    # --- repetition / language ---
    dict(id="rp01", kind="appearance_changed", subject="铜灯罩", value="玻璃上蒙了一层水汽",
         place=("旧灯塔", "塔顶"), visible=["铜框信号灯", "玻璃罩", "火苗", "海风直吹", "铜灯罩"],
         scene="夜；夜雾，海风", viewer="叶知微",
         source="world.json#items.item_lamp_cover.appearance + authored 变化", authored=True,
         focus="复述", note="“蒙了水汽”容易被同义重说一遍"),
    dict(id="rp02", kind="outcome", subject="叶知微", value="把灯罩擦到能照见人影",
         place=("旧灯塔", "塔顶"), visible=["铜框信号灯", "玻璃罩", "火苗", "海风直吹", "抹布"],
         scene="夜；夜雾，海风；铜灯已点亮", viewer="叶知微",
         source="world.json#tasks.task_wipe.goal 改写 + authored 结果", authored=True,
         focus="复述", note="“照见人影”容易被再次改写复述"),
    dict(id="lg01", kind="appearance_changed", subject="排水沟", value="沟底积了泥",
         place=("潮生巷", "巷子"), visible=["湿石板", "纸灯笼", "排水沟", "墙根", "水洼"],
         scene="雨后；雨停；纸灯笼", viewer="沈砚",
         source="world.json#items（潮生巷排水沟现象）+ authored 变化", authored=True,
         focus="语病", note="“排水沟的沟底”属所有格错位风险"),
    dict(id="lg02", kind="appearance_changed", subject="铁链", value="链环之间的缝里卡了沙",
         place=("旧灯塔", "塔顶"), visible=["铜框信号灯", "玻璃罩", "火苗", "海风直吹", "铁链"],
         scene="夜；夜雾，海风", viewer="叶知微",
         source="world.json#locations.loc_lighthouse_top（铁链）+ authored 变化", authored=True,
         focus="语病", note="多重“的”结构风险"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fact_line(unit: dict) -> str:
    if unit["kind"] == "moved":
        return f'{unit["subject"]}｜移动｜{unit["frm"]}→{unit["to"]}'
    if unit["kind"] == "sanity_changed":
        return f'{unit["subject"]}｜状态变化｜{unit["descriptor"]}'
    return f'{unit["subject"]}｜{KIND_LABEL[unit["kind"]]}｜{unit["value"]}'


def render(unit: dict) -> str:
    direction = f'方向={unit["direction"]}\n' if unit["kind"] == "moved" else ""
    return TEMPLATE.format(place=f'{unit["place"][0]}>{unit["place"][1]}',
                           visible="、".join(unit["visible"]),
                           scene=unit["scene"], viewer=unit["viewer"],
                           fact_line=fact_line(unit), direction_line=direction)


def signature(unit: dict):
    if unit["kind"] == "moved":
        return ("moved", unit["subject"], unit["frm"], unit["to"])
    if unit["kind"] == "sanity_changed":
        return ("sanity_changed", unit["subject"], unit["frm"], unit["to"])
    return (unit["kind"], unit["subject"], unit["value"])


def parse_signature_from_input(text: str, kind: str | None = None):
    m = re.search(r"事实=([^\n]+)", text)
    if not m:
        return None
    parts = [p.strip() for p in m.group(1).split("｜")]
    if len(parts) < 2:
        return None
    label = parts[1]
    if label == "移动" and len(parts) >= 3:
        frm, _, to = parts[2].partition("→")
        return ("moved", parts[0], frm.strip(), to.strip())
    if label == "状态变化":
        return ("sanity_changed", parts[0], None, None)
    value = "｜".join(parts[2:])
    kind_map = {"结果": "outcome", "外貌变化": "appearance_changed"}
    return (kind_map.get(label, label), parts[0], value)


def main() -> int:
    world = json.loads(WORLD.read_text(encoding="utf-8"))

    # collect signatures of everything the model has already seen
    seen = {}
    for name, path in POOLS + OTHER_SETS:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        sigs, inputs = set(), set()
        for row in rows:
            if "input" in row:
                inputs.add(row["input"])
                sig = parse_signature_from_input(row["input"])
                if sig:
                    sigs.add(sig)
            elif "fact" in row:  # contract rows carry structured facts
                f = row["fact"]
                if f["kind"] == "moved":
                    sigs.add(("moved", f["name"], f["from"], f["to"]))
                elif f["kind"] == "sanity_changed":
                    sigs.add(("sanity_changed", f["name"], f["from"], f["to"]))
                elif f["kind"] == "no_change":
                    sigs.add(("no_change", f["name"]))
                else:
                    sigs.add((f["kind"], f["name"], f.get("resultText") or f.get("text")))
        seen[name] = dict(signatures=sigs, inputs=inputs, units=len(rows))

    units_out = []
    problems = []
    for unit in UNITS:
        text = render(unit)
        sig = signature(unit)
        hits = sorted(name for name, data in seen.items() if sig in data["signatures"])
        input_hits = sorted(name for name, data in seen.items() if text in data["inputs"])
        if hits:
            problems.append(dict(unit=unit["id"], kind="signature", hit=hits, sig=sig))
        if input_hits:
            problems.append(dict(unit=unit["id"], kind="input", hit=input_hits))
        units_out.append(dict(
            unitId=unit["id"],
            source=dict(
                spec=unit["source"], authored=unit["authored"],
                provenance=unit.get("provenance", "verbatim"),
                basis=unit.get("basis"),
                worldFile="experiments/world-components/n4_narrative_dev/world.json",
                worldSha256=sha256(WORLD),
            ),
            fact=dict(kind=unit["kind"], name=unit["subject"],
                      value=unit.get("value"),
                      **({"from": unit["frm"], "to": unit["to"]} if unit["kind"] in ("moved", "sanity_changed") else {}),
                      **({"direction": unit["direction"]} if unit["kind"] == "moved" else {})),
            entityId=("characters.char_" + {"沈砚": "shen", "顾行舟": "gu", "叶知微": "ye", "阿棠": "atang", "韩渡": "han"}.get(unit["subject"], "unknown")
                      if unit["kind"] in ("outcome", "moved", "sanity_changed") else "items/item (see source)"),
            fieldPath=unit["source"].split("#")[-1],
            input=text,
            inputSha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            overlap=dict(signatureHits=hits, inputHits=input_hits,
                         independent=not hits and not input_hits),
            focus=unit["focus"], note=unit["note"], criterion=unit.get("criterion"),
        ))

    registration = dict(
        protocol="c4-acceptance-registration-v2",
        status="v1 superseded by v2 (provenance/criteria fixes); still registered, not run",
        createdAt="2026-11-08",
        unitCount=len(units_out),
        world=dict(path="experiments/world-components/n4_narrative_dev/world.json", sha256=sha256(WORLD),
                   id=world["worldId"], family=world["family"]),
        inputTemplate=dict(text=TEMPLATE, source="same template as cf24 (v3 diagnostic)"),
        judgingStandard=dict(
            protocol="comparison-protocol-v3.md §4",
            taxonomy="freeze/failure-taxonomy-v1.json (seven categories)",
            notes=["U is never a pass", "categories may overlap and are never summed",
                   "an object named by the fact is authorised by the fact itself",
                   "position needs the fact or the visible list; mere existence is not authorisation"],
        ),
        overlapRule=dict(
            signature="kind + subject + value, or kind + subject + from + to",
            input="rendered input must not equal any pool or earlier-set input",
            pools=[dict(name=n, sha256=sha256(p), units=seen[n]["units"]) for n, p in POOLS],
            otherSets=[dict(name=n, sha256=sha256(p), units=seen[n]["units"]) for n, p in OTHER_SETS],
        ),
        units=units_out,
        problems=problems,
        limitations=[
            "same N4 world as training; independence is signature/input level, not a new world",
            "authored values are declared per unit and are not world-authoritative records",
            "world.json has no committed action log: all moved units are derived from location levels",
            "v1 registration (freeze/acceptance-registration-v1.json) is kept as the reviewed-before-fix record",
            "no u240 output exists for this set yet; registration only",
            "judging will again be assistant-only unless a human reviewer is added",
        ],
    )
    (EXPERIMENT / "freeze/acceptance-registration-v2.json").write_text(
        json.dumps(registration, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = [
        "# 独立验收集登记 v2（已登记，未运行）",
        "",
        "> 状态：登记完成，**没有运行任何模型**，也没有生成或查看 u240 在这些单元上的输出。",
        f"> 单元数：{len(units_out)}；其中事实值由人工撰写（authored）的 {sum(1 for u in units_out if u['source']['authored'])} 条，其余直接取自世界字段。",
        f"> 世界文件：`experiments/world-components/n4_narrative_dev/world.json`（`worldId={world['worldId']}`，sha256 `{sha256(WORLD)[:16]}…`）",
        "> 判定标准：`comparison-protocol-v3.md` §4 + `freeze/failure-taxonomy-v1.json` 七类；U 不算通过；类别可重叠、不相加。",
        "",
        "| 单元 | 类别 | 事实 | 来源 | authored | 输入 sha256 | 重叠 | 重点 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for u in units_out:
        f = u["fact"]
        if f["kind"] == "moved":
            fact = f'{f["name"]} 移动 {f["from"]}→{f["to"]} dir={f["direction"]}'
        elif f["kind"] == "sanity_changed":
            fact = f'{f["name"]} 状态 {f["from"]}→{f["to"]}'
        else:
            fact = f'{f["name"]} {f["kind"]} {f.get("value")}'
        lines.append(f'| {u["unitId"]} | {u["fact"]["kind"]} | {fact} | `{u["source"]["spec"]}` | '
                     f'{"是" if u["source"]["authored"] else "否"} | `{u["inputSha256"][:16]}…` | '
                     f'{"独立" if u["overlap"]["independent"] else "冲突"} | {u["focus"]} |')
    lines += ["", "## 输入渲染示例（ac01）", "", "```", units_out[0]["input"].rstrip(), "```", "",
              "## 限制", ""] + [f"- {x}" for x in registration["limitations"]]
    (EXPERIMENT / "results/acceptance-registration-v2.md").write_text(chr(10).join(lines) + chr(10), encoding="utf-8")

    if problems:
        print("OVERLAP PROBLEMS:", json.dumps(problems, ensure_ascii=False, indent=1))
    print(f"registered {len(units_out)} units, authored={sum(1 for u in units_out if u['source']['authored'])}")
    for u in units_out:
        print(f"  {u['unitId']} {u['fact']['kind']:<19} independent={u['overlap']['independent']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

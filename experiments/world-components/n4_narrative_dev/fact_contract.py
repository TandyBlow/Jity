"""单一事实序列化函数（训练 / 评估 / 推理共用）。

训练语料 `verbalizer_pairs.jsonl` 的事实行格式是：

    <名字>｜<标签>｜<取值>

    moved             沈砚｜移动｜潮渡→雾堤
    outcome           沈砚｜结果｜把灯罩擦得透亮
    appearance_changed 沈砚｜外貌变化｜袖口沾了铜油
    personality_changed 沈砚｜性格变化｜开始愿意先开口
    sanity_changed    沈砚｜状态变化｜放松        （升）/ 发紧（降）
    no_change         场景｜无变化

注意顺序：**名字在前、标签在中、取值在后**。实验脚本里手拼的
`标签｜名字｜取值`、`外观`、`无变化｜`、`理智｜…｜下降` 都与这个格式不符，
本模块是唯一允许的写法，并在生成前做格式校验。
"""
import json
import pathlib
import re
import sys

LABEL = {
    "moved": "移动",
    "outcome": "结果",
    "appearance_changed": "外貌变化",
    "personality_changed": "性格变化",
    "sanity_changed": "状态变化",
    "no_change": "无变化",
}

# 每种事实的取值规则；sanity 只有升/降两个取值词
SANITY_UP, SANITY_DOWN = "放松", "发紧"

NAME_RE = r"[一-鿿]{1,6}"   # 墨(1) … 潮汐档案馆(5)
LINE_RE = {
    "moved": re.compile(rf"^{NAME_RE}｜移动｜{NAME_RE}→{NAME_RE}$"),
    "outcome": re.compile(rf"^{NAME_RE}｜结果｜\S+$"),
    "appearance_changed": re.compile(rf"^{NAME_RE}｜外貌变化｜\S+$"),
    "personality_changed": re.compile(rf"^{NAME_RE}｜性格变化｜\S+$"),
    "sanity_changed": re.compile(rf"^{NAME_RE}｜状态变化｜(放松|发紧)$"),
    "no_change": re.compile(r"^场景｜无变化$"),
}


class ContractError(ValueError):
    pass


def serialize_fact(fact):
    """事实 → 事实行的取值部分（不含 `事实=` 前缀）。"""
    kind = fact["kind"]
    if kind == "no_change":
        return "场景｜无变化"
    name = fact.get("name")
    if not name:
        raise ContractError(f"{kind} 缺少主体")
    if kind == "moved":
        return f'{name}｜移动｜{fact["from"]}→{fact["to"]}'
    if kind == "outcome":
        # 训练语料用 resultText，生成材料用 text，两者都是“结果内容”
        return f'{name}｜结果｜{fact.get("resultText") or fact.get("text")}'
    if kind == "appearance_changed":
        return f'{name}｜外貌变化｜{fact.get("text") or fact.get("resultText")}'
    if kind == "personality_changed":
        return f'{name}｜性格变化｜{fact.get("text") or fact.get("resultText")}'
    if kind == "sanity_changed":
        up = fact["to"] > fact["from"]
        return f'{name}｜状态变化｜{SANITY_UP if up else SANITY_DOWN}'
    raise ContractError(f"未知事实种类 {kind}")


def check_line(kind, line):
    """检查一行（`事实=` 之后的部分）是否符合该种类的格式。"""
    rx = LINE_RE.get(kind)
    if rx is None:
        raise ContractError(f"未知事实种类 {kind}")
    if not rx.match(line):
        raise ContractError(f"{kind} 格式不符：{line!r}，期望 {rx.pattern}")
    return True


def build_unit_input(scene_header, fact):
    """拼一条短句任务输入：场景头 + 视角 + 事实 + 要求。"""
    line = serialize_fact(fact)
    check_line(fact["kind"], line)
    out = scene_header.rstrip("\n") + "\n" + f"事实={line}"
    if fact["kind"] == "moved":
        out += f'\n方向={fact.get("direction", "平")}'
    out += ("\n要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；"
            "只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；"
            "不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。\n短句：\n")
    return out


def unit_fact_line(unit_input):
    for ln in unit_input.splitlines():
        if ln.startswith("事实="):
            return ln[len("事实="):]
    raise ContractError("单元输入里没有 事实= 行")


def check_units(units, strict=True):
    """校验一批单元；返回问题列表。strict 时抛错。"""
    problems = []
    for u in units:
        kind = u.get("kind")
        if kind is None:
            problems.append((u.get("unitId"), "缺少 kind，无法校验格式"))
            continue
        try:
            check_line(kind, unit_fact_line(u["input"]))
        except ContractError as exc:
            problems.append((u.get("unitId"), str(exc)))
    if strict and problems:
        head = "\n  ".join(f"{u}: {m}" for u, m in problems[:8])
        raise ContractError(f"{len(problems)} 个单元的事实行格式不符：\n  {head}")
    return problems


# ---- 固定样例：升 / 降各一条，逐字符比对实际送入模型的字符串
SAMPLES = {
    "sanity_up": ({"kind": "sanity_changed", "name": "沈砚", "from": 9, "to": 12},
                  "沈砚｜状态变化｜放松"),
    "sanity_down": ({"kind": "sanity_changed", "name": "沈砚", "from": 12, "to": 9},
                    "沈砚｜状态变化｜发紧"),
    "moved": ({"kind": "moved", "name": "沈砚", "from": "潮渡", "to": "雾堤"},
              "沈砚｜移动｜潮渡→雾堤"),
    "appearance": ({"kind": "appearance_changed", "name": "沈砚",
                    "text": "袖口沾了铜油"}, "沈砚｜外貌变化｜袖口沾了铜油"),
    "no_change": ({"kind": "no_change"}, "场景｜无变化"),
}


def run_self_check():
    for tag, (fact, want) in SAMPLES.items():
        got = serialize_fact(fact)
        if got != want:
            raise ContractError(f"样例 {tag} 不符：得到 {got!r}，应为 {want!r}")
        check_line(fact["kind"], got)
    # 反例必须被拒绝
    for bad in ("状态变化｜沈砚｜发紧", "理智｜沈砚｜下降", "外观｜沈砚｜袖口沾了油",
                "无变化｜", "移动｜沈砚｜潮渡→雾堤"):
        kind = {"状态变化": "sanity_changed", "理智": "sanity_changed",
                "外观": "appearance_changed", "无变化": "no_change",
                "移动": "moved"}[bad.split("｜")[0]]
        try:
            check_line(kind, bad)
        except ContractError:
            continue
        raise ContractError(f"反例未被拒绝：{bad!r}")
    print(f"契约自检通过：{len(SAMPLES)} 个正向样例、5 个反例")


def main(argv):
    if not argv or argv[0] == "--self-check":
        run_self_check()
        return 0
    if argv[0] == "--check":
        bad_total = 0
        for path in argv[1:]:
            rows = [json.loads(l) for l in
                    pathlib.Path(path).read_text(encoding="utf-8").splitlines()
                    if l.strip()]
            problems = check_units(rows, strict=False)
            bad_total += len(problems)
            print(f"{pathlib.Path(path).name}: {len(rows)} 单元，"
                  f"{len(problems)} 个格式不符")
            for u, m in problems[:5]:
                print("   ", u, m)
        return 1 if bad_total else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

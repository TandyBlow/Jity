"""Hard pre-training checks for single-fact data.

Four checks, all mechanical:
  1. entity    — every name in a fact exists in world.json
  2. visibility— every item named by a fact is in that unit's 地点可见 list,
                 or is carried by the viewpoint character
  3. authorisation — a fact's subject is a character, an item, or a listed
                 location feature; a no_change fact has no subject
  4. whole/part — a part may only be named if world.json documents it, and the
                 whole it belongs to must be visible

Matching is longest-first so that 铜灯 does not match inside 铜灯罩.
"""
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
WORLD = json.loads((HERE / "world.json").read_text(encoding="utf-8"))

ITEMS = {v["name"] for v in WORLD["items"].values()}
CHARS = {v["name"] for v in WORLD["characters"].values()}
FEATURES = set()
for L in WORLD["locations"].values():
    FEATURES |= set(L.get("features") or [])
    for s in L.get("sublocations") or []:
        FEATURES |= set((s.get("appearance") or "").replace("、", " ").split())
LOCS = set()
for L in WORLD["locations"].values():
    LOCS.add(L["name"])
    LOCS |= {s["name"] for s in L.get("sublocations") or []}
CARRIED = {}
for c in WORLD["characters"].values():
    CARRIED[c["name"]] = {WORLD["items"][i]["name"] for i in c.get("inventory") or []}

# 整体 → 已登记的部件。只查这张表里有的整体；地点名后面的“的”当方位短语，跳过。
PARTS_OF = {
    "油布包": {"内层", "外层", "夹层"},
    "铜灯罩": {"灯罩", "玻璃罩"},
    "警示灯": {"玻璃罩", "灯罩"},
    "铜灯": {"灯罩"},
    "铁链": {"链环"},
    "潮汐簿": {"扉页", "封面", "缺页"},
    "外袍": {"下摆", "袖口"},
    "渡船": {"船板"},
    "油纸伞": {"伞骨"},
    "船灯": {"罩子"},
    "纸灯笼": {"骨架"},
    "抹布": {"边角"},
    "鱼筐": {"边沿"},
    "案板": {"边沿"},
    "缆绳": {"末端"},
    "系泊绳": {"末端"},
    "擦铜油": {"罐口"},
    "银鳞鱼": {"鳞片"},
    "钟绳": {"末端"},
    "钟架": {"横木"},
}
CHAR_PARTS = {"袖口", "下摆", "辫梢", "鞋底", "手背", "指尖", "眉毛"}
PARTS = {p for v in PARTS_OF.values() for p in v} | CHAR_PARTS
_ORDERED_ITEMS = sorted(ITEMS, key=len, reverse=True)


def items_in(text):
    """Longest-first item mentions; 铜灯 does not match inside 铜灯罩."""
    found, rest = set(), text or ""
    for name in _ORDERED_ITEMS:
        if name in rest:
            found.add(name)
            rest = rest.replace(name, "\u0000")
    return found


def parts_in(text):
    """只报“整体在表里、部件不在它名下”的组合；地点名后面的“的”跳过。"""
    out = []
    text = text or ""
    for m in re.finditer(r"([一-鿿]{2,5})的", text):
        head = m.group(1)
        tail = text[m.end():]
        whole = next((w for w in sorted(PARTS_OF, key=len, reverse=True)
                      if head.endswith(w)), None)
        if whole is None:
            continue
        part = next((p for p in sorted(PARTS, key=len, reverse=True)
                     if tail.startswith(p)), tail[:2])
        if part not in PARTS_OF[whole]:
            out.append((whole, part))
    return out


def visible_of(input_text):
    line = input_text.split("地点可见=")[1].splitlines()[0]
    return {x for x in line.split("、") if x}


def pov_of(input_text):
    return input_text.split("视角=")[1].splitlines()[0].split("；")[0]


def parse_fact(input_text):
    line = input_text.split("事实=")[1].splitlines()[0]
    parts = line.split("｜")
    kind = {"移动": "moved", "结果": "outcome", "外观": "appearance_changed",
            "无变化": "no_change"}.get(parts[0], parts[0])
    return {"kind": kind,
            "name": parts[1] if len(parts) > 1 else "",
            "text": parts[2] if len(parts) > 2 else ""}


def check_unit(unit):
    """unit: dict with unitId, input, optionally fact.  Returns list of problems."""
    inp = unit["input"]
    fact = unit.get("fact") or parse_fact(inp)
    vis = visible_of(inp)
    pov = pov_of(inp)
    carried = CARRIED.get(pov, set())
    problems = []
    kind, name = fact["kind"], fact.get("name") or ""

    # 1 entity
    if kind != "no_change":
        if name not in CHARS | ITEMS | FEATURES:
            problems.append(f"entity: 主体 {name} 不在世界表")
        if kind == "moved":
            for k in ("from", "to"):
                v = fact.get(k)
                if v and v not in LOCS:
                    problems.append(f"entity: {k}={v} 不是地名")

    # 2 visibility
    body = fact.get("text") or ""
    if kind == "moved":
        body = str(fact.get("to") or "")
    for it in items_in(body):
        if it not in vis and it not in carried:
            problems.append(f"visibility: 引用物件 {it} 不在可见列表")
    if name in ITEMS and name not in vis and name not in carried:
        problems.append(f"visibility: 主体物件 {name} 不在可见列表")

    # 3 authorisation
    if kind == "no_change" and name:
        problems.append("authorisation: 无变化事实不应有主体")
    if name and name in FEATURES and name not in ITEMS and name not in CHARS \
            and name not in vis:
        problems.append(f"authorisation: 场景特征 {name} 未在该地点列出")

    # 4 whole/part
    for whole, part in parts_in(body):
        if part not in PARTS:
            problems.append(f"part: 部件 {part} 未登记（整体 {whole}）")
        for it in items_in(whole):
            if it not in vis and it not in carried:
                problems.append(f"part: 整体 {it} 不可见，部件 {part} 无从谈起")
    return problems


def audit_file(path):
    out = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        u = json.loads(line)
        pr = check_unit(u)
        out.append({"unitId": u["unitId"], "problems": pr})
    return out


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        res = audit_file(p)
        bad = [r for r in res if r["problems"]]
        print(f"{pathlib.Path(p).name}: {len(res)} units, {len(bad)} with problems")
        for b in bad:
            print("  ", b["unitId"], b["problems"])

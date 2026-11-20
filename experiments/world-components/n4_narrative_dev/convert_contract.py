"""把已有固定诊断集的事实行改写为契约格式（只改事实行，其余一字不动）。

用法：
  python convert_contract.py            # 生成 *-contract.jsonl 并逐条校验
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fact_contract as FC  # noqa: E402

ART = HERE.parents[2] / "artifacts" / "world-components"

SETS = [
    ("object18", ART / "n4-object-confirm18-units.jsonl"),
    ("expand36", ART / "n4-expand-confirm36-units.jsonl"),
    ("final24", ART / "n4-final24.jsonl"),
]


def rewrite(unit):
    """把一条单元的 事实= 行换成契约格式，返回新输入。"""
    fact = unit.get("fact")
    if fact is None:
        raise SystemExit(f'{unit.get("unitId")}: 缺少 fact 字段，无法改写')
    want = FC.serialize_fact(fact)
    out, done = [], False
    for ln in unit["input"].splitlines():
        if ln.startswith("事实="):
            out.append("事实=" + want)
            done = True
        else:
            out.append(ln)
    if not done:
        raise SystemExit(f'{unit.get("unitId")}: 输入里没有 事实= 行')
    return "\n".join(out) + "\n"


def cf24_units():
    mat = json.loads((ART / "n4-cf24-materials-v2.json").read_text(encoding="utf-8"))
    out = []
    for s in mat["sources"]:
        for f in s["facts"]:
            out.append({"unitId": f'{s["id"]}:{f["factId"]}', "sourceId": s["id"],
                        "kind": f["kind"], "fact": f,
                        "input": s["unitInputs"][f["factId"]]})
    return out


def main():
    total, bad = 0, 0
    for name, path in SETS:
        units = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        fixed = []
        for u in units:
            u = dict(u, input=rewrite(u))
            fixed.append({k: u[k] for k in
                          ("unitId", "sourceId", "kind", "fact", "input") if k in u})
        problems = FC.check_units(fixed, strict=False)
        bad += len(problems)
        total += len(fixed)
        out = ART / f"n4-{name}-contract.jsonl"
        out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in fixed) + "\n",
                       encoding="utf-8")
        print(f"{name}: {len(fixed)} 单元，格式问题 {len(problems)} → {out.name}")
    units = cf24_units()
    fixed = [{**{k: u[k] for k in ("unitId", "sourceId", "kind", "fact")},
              "input": rewrite(u)} for u in units]
    problems = FC.check_units(fixed, strict=False)
    bad += len(problems)
    total += len(fixed)
    out = ART / "n4-cf24-contract.jsonl"
    out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in fixed) + "\n",
                   encoding="utf-8")
    print(f"cf24: {len(fixed)} 单元，格式问题 {len(problems)} → {out.name}")
    print(f"合计 {total} 单元，格式问题 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

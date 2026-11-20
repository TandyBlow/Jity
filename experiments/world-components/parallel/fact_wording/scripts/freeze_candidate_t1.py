"""Freeze candidate T1 (one requirement sentence change) without running a model.

For every cf24 unit, replace exactly the first clause of the requirement sentence and
verify that nothing else changed. Writes freeze/candidate-t1-v1.json with the two
sentences, the per-unit input hashes and the count of changed units.
"""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve()
TREE = HERE.parents[5]
UNIT_FILE = TREE / "artifacts/world-components/n4-cf24-contract.jsonl"
OUT = HERE.parents[1] / "freeze/candidate-t1-v1.json"

OLD = ("要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；"
       "只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；"
       "不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。")
NEW = ("要求：只写事实本身，写成一句陈述；句中出现事实主体的名字；"
       "只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；"
       "不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    units = [json.loads(line) for line in UNIT_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows, changed, unchanged = [], 0, []
    for unit in units:
        old_input = unit["input"]
        occurrences = old_input.count(OLD)
        new_input = old_input.replace(OLD, NEW)
        if occurrences != 1:
            unchanged.append(dict(unitId=unit["unitId"], occurrences=occurrences))
        else:
            changed += 1
        rows.append(dict(unitId=unit["unitId"],
                         oldInputSha256=sha(old_input), newInputSha256=sha(new_input),
                         replaced=occurrences == 1))
    payload = dict(
        protocol="c4-candidate-t1-v1",
        purpose="one requirement-sentence change for extra_action_state; not run",
        oldRequirement=OLD, newRequirement=NEW,
        oldRequirementSha256=sha(OLD), newRequirementSha256=sha(NEW),
        unitFile=str(UNIT_FILE.relative_to(TREE)).replace(chr(92), "/"),
        unitFileSha256=hasattr(hashlib, "sha256") and hashlib.sha256(UNIT_FILE.read_bytes()).hexdigest(),
        units=len(units), changedUnits=changed, anomalies=unchanged,
        rows=rows,
        note="only the first clause changed; facts, visible lists, scenes and directions untouched",
    )
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"units={len(units)} changed={changed} anomalies={len(unchanged)}")
    print("old sentence sha256:", sha(OLD)[:16], "new:", sha(NEW)[:16])
    print("manifest:", OUT)
    return 0 if changed == len(units) else 1


if __name__ == "__main__":
    raise SystemExit(main())

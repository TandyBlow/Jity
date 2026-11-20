# -*- coding: utf-8 -*-
"""Direct audit of the three frozen v1 rule modules.

`legacy_compat` already verifies the source hashes and the legacy `xProse`
bytes.  This script additionally executes the two modules the v2 builder does
not call directly:

  * `split_xy.build_x` / `build_text` must reproduce the stored `x` / `xText`
    for every one of the 199 rows;
  * `rows_common.result_view` must reproduce the v2 result for person fields
    when given the reconstructed full after entity, and the known item-position
    gap must be visible rather than silently ignored.

It writes `data/legacy-rule-audit.json`; no training data is modified.
"""

from __future__ import annotations

import io
import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import legacy_compat as legacy


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "data", "legacy-rule-audit.json")


def multiset(value: Any) -> Any:
    if isinstance(value, list):
        return sorted(value)
    return value


def merge_tasks(before: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild the full task tree expected by rows_common.result_view.

    The result block carries only changed tasks; rows_common expects the full
    after tree so it can look up each completed/added goal.
    """
    big = dict(before["大任务"])
    small = [dict(task) for task in before.get("小任务", [])]
    result_big = result.get("大任务")
    if result_big:
        if big["目标"] == result_big["目标"]:
            big["状态"] = result_big["状态"]
    for changed in result.get("小任务", []):
        found = False
        for task in small:
            if task["目标"] == changed["目标"]:
                task["状态"] = changed["状态"]
                found = True
                break
        if not found:
            small.append(dict(changed))
    return {"大任务": big, "小任务": small}


def main() -> int:
    split = legacy.load_split_xy()
    common = legacy.load_rows_common()
    rows = legacy.legacy_rows()
    problems: List[str] = []
    split_x_ok = 0
    split_text_ok = 0
    person_fields_checked = 0
    person_fields_ok = 0
    for row in rows:
        # rows-xy.jsonl stores the four fields under x; split_xy expects the
        # original row shape (fields at top level plus the narrative).
        raw_row = dict(row["x"])
        raw_row["叙事"] = row["y"]
        x = split.build_x(raw_row)
        text = split.build_text(x)
        if x != row["x"]:
            problems.append(f"{row['id']}: split_xy.build_x differs")
        else:
            split_x_ok += 1
        if text != row["xText"]:
            problems.append(f"{row['id']}: split_xy.build_text differs")
        else:
            split_text_ok += 1

        before = row["x"]["上回合状态"]
        changes = row["x"]["本回合变化"]["变化"]
        result = row["x"]["本回合状态"]
        for entity, ops in changes.items():
            if entity not in before.get("人物", {}):
                continue
            full = dict(before["人物"][entity])
            full.update(result.get(entity, {}))
            if "任务" in result.get(entity, {}):
                full["任务"] = merge_tasks(before["人物"][entity]["任务"],
                                           result[entity]["任务"])
            legacy_view = common.result_view(full, ops, True)
            for field_name, value in legacy_view.items():
                person_fields_checked += 1
                actual = result.get(entity, {}).get(field_name)
                if multiset(value) != multiset(actual):
                    problems.append(
                        f"{row['id']}:{entity}.{field_name}: rows_common "
                        f"{value!r} != v2 {actual!r}")
                else:
                    person_fields_ok += 1

    # Explicit item-position gap: rows_common.build_result's item branch copies
    # appearance only, while v2 must carry the settled item position.
    gap_after = {"人物": {}, "地点": {}, "物品": {
        "铜钥匙": {"位置": "木箱", "外貌": ["多了一道刻痕"]}}}
    gap_changes = {"铜钥匙": {"位置": "木箱", "新增外貌": ["多了一道刻痕"]}}
    legacy_item_result = common.build_result(gap_after, gap_changes)
    item_position_gap = "位置" not in legacy_item_result.get("铜钥匙", {})

    audit = {
        "schema": "jity-narration-legacy-rule-audit",
        "rows": len(rows),
        "sourceHashes": legacy.verify_sources(),
        "splitXy": {
            "buildXOk": split_x_ok,
            "buildTextOk": split_text_ok,
            "rows": len(rows),
            "matches": split_x_ok == len(rows) and split_text_ok == len(rows),
        },
        "rowsCommon": {
            "personFieldsChecked": person_fields_checked,
            "personFieldsOk": person_fields_ok,
            "matches": person_fields_checked == person_fields_ok and not problems,
            "itemPositionGap": item_position_gap,
            "itemPositionSyntheticLegacyResult": legacy_item_result,
            "itemPositionFix": "v2 build_result/place line copies item 位置 and renders 物品（位于<位置>）",
        },
        "problems": problems,
        "ok": not problems and split_x_ok == len(rows) and split_text_ok == len(rows)
              and person_fields_checked == person_fields_ok and item_position_gap,
    }
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: audit[key] for key in
                      ("rows", "splitXy", "rowsCommon", "problems", "ok")},
                     ensure_ascii=False, indent=1))
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""Build the public golden vectors for the v2 narration projection.

The vectors are the contract between this lane and lane 01 (browser input
adapter).  Each vector carries:

  * the structured projection (already normalized and result-filled),
  * the normalization ledger for the vector,
  * the exact UTF-8 text, its SHA-256 and hex bytes,
  * field-level segments (block/entity/field -> code-point range),
  * expected success or a stable error code and stage.

The real cases come from the frozen 199 rows.  Synthetic cases cover shapes the
199 rows do not contain: item movement, zero sanity, empty appearance/personality,
task hierarchy, non-BMP name ordering, whitespace and OOV refusal.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import legacy_compat as legacy
import projection_v2 as projection
import v2_render as v2
from tokenizer_profile import load_tokenizer_profile, public_profile, validate_tokenizer_text


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DATA = os.path.join(ROOT, "data")
GOLDEN = os.path.join(ROOT, "golden")
TOKENIZER = os.path.join(ROOT, "tokenizers", "yuyan-v1", "dict.txt")

REAL_CASES = [
    # id, why this row is in the set
    ("row-0002", "max input length; item appearance; person move; task complete/add"),
    ("row-0003", "item appearance; task complete; new task"),
    ("row-0004", "sanity change; person appearance; place appearance"),
    ("row-0005", "person move; appearance; place appearance"),
    ("row-0006", "known historical failure row; personality changes"),
    ("row-0007", "task complete; item appearance"),
    ("row-0008", "no-change round; no result block"),
    ("row-0009", "new task; item appearance"),
    ("row-0010", "new task; place appearance"),
    ("row-0011", "person move; item appearance"),
    ("row-0012", "person move; item appearance"),
    ("row-0016", "person move; appearance"),
    ("row-0017", "dev split; person move"),
    ("row-0018", "test split; new task"),
    ("row-0022", "dev split; place appearance"),
    ("row-0028", "test split; sanity change"),
    ("row-0033", "test split; big task complete; personality"),
    ("row-0053", "test split; two small task completions"),
    ("row-0095", "empty appearance list in result"),
    ("row-0132", "empty item appearance list in result"),
]


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def atomic_write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_jsonl(path: str, records: List[Dict[str, Any]]) -> None:
    payload = "".join(json.dumps(record, ensure_ascii=False) + "\n"
                      for record in records).encode("utf-8")
    atomic_write(path, payload)


def expected_ok(serialized: v2.Serialized, fills: List[Dict[str, Any]],
                extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = serialized.text.encode("utf-8")
    payload = {
        "status": "ok",
        "text": serialized.text,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytesUtf8Hex": data.hex(),
        "segments": [segment.as_dict() for segment in serialized.segments],
        "resultFills": fills,
    }
    if extra:
        payload.update(extra)
    return payload


def expected_error(stage: str, code: str, message: str, path: str = "") -> Dict[str, Any]:
    return {"status": "error", "stage": stage, "errorCode": code,
            "errorMessage": message, "errorPath": path}


def base_world() -> Dict[str, Any]:
    return {
        "地点": {
            "旧屋": {"位于": None, "外貌": ["墙皮剥落。"]},
            "里间": {"位于": "旧屋", "外貌": ["一盏灯泡坏了。"]},
        },
        "人物": {
            "阿青": {
                "位置": "里间", "精神值": 12,
                "外貌": ["短发"], "个性": ["谨慎"],
                "任务": {
                    "大任务": {"目标": "找到钥匙", "状态": "未完成"},
                    "小任务": [
                        {"目标": "翻找抽屉", "状态": "未完成"},
                        {"目标": "问老周", "状态": "未完成"},
                    ],
                },
            },
            "老周": {
                "位置": "旧屋", "精神值": 40,
                "外貌": ["戴旧帽"], "个性": ["寡言"],
                "任务": {
                    "大任务": {"目标": "守住旧屋", "状态": "未完成"},
                    "小任务": [],
                },
            },
        },
        "物品": {
            "铜钥匙": {"位置": "里间", "外貌": ["齿口磨平了。"]},
            "木箱": {"位置": "旧屋", "外貌": []},
        },
    }


def projection_for(changes: Dict[str, Any], *,
                   before: Optional[Dict[str, Any]] = None,
                   result: Optional[Dict[str, Any]] = None,
                   time: str = "3分钟",
                   viewpoint: str = "主角视角（阿青）；只表达已结算的世界事实") -> Dict[str, Any]:
    return {
        "视角": viewpoint,
        "上回合状态": before if before is not None else base_world(),
        "本回合变化": {"时间推进": time, "变化": changes},
        "本回合状态": result if result is not None else {},
    }


def make_case(case_id: str, kind: str, raw: Dict[str, Any], *,
              source: Optional[Dict[str, Any]] = None,
              tokenizer: Optional[Dict[str, Any]] = None,
              tokenizer_check: bool = False,
              skip_build: bool = False,
              note: str = "") -> Dict[str, Any]:
    """Normalize, build the result block, serialize, and capture the outcome."""
    record: Dict[str, Any] = {
        "caseId": case_id,
        "rawProjection": raw,
        "kind": kind,
        "note": note,
        "versions": {
            "projectionVersion": v2.PROJECTION_VERSION,
            "serializerVersion": v2.SERIALIZER_VERSION,
            "legacySerializerVersion": v2.LEGACY_SERIALIZER_VERSION,
            "modelTemplateVersion": v2.MODEL_TEMPLATE_VERSION,
            "tokenizerHash": tokenizer["sha256"] if tokenizer else None,
            "tokenizerStatus": "bound" if tokenizer else "pending",
        },
    }
    if source:
        record["source"] = source
    try:
        normalized, ledger = projection.normalize_projection(raw)
    except v2.NarrationSerializeError as error:
        record["projection"] = None
        record["normalization"] = []
        record["expected"] = expected_error("normalize", error.code, error.message, error.path)
        return record
    record["normalization"] = ledger
    try:
        if skip_build:
            fills = []
        else:
            result, fills = v2.build_result(normalized["上回合状态"],
                                            normalized["本回合变化"],
                                            normalized["本回合状态"])
            normalized["本回合状态"] = result
        serialized = v2.serialize(normalized)
    except v2.NarrationSerializeError as error:
        record["projection"] = normalized
        stage = "serialize" if skip_build else "build"
        record["expected"] = expected_error(stage, error.code,
                                            error.message, error.path)
        return record
    record["projection"] = normalized
    if tokenizer_check and tokenizer is not None:
        try:
            validate_tokenizer_text(serialized.text, tokenizer)
        except v2.NarrationSerializeError as error:
            record["expected"] = expected_error("tokenizer", error.code,
                                                error.message, error.path)
            return record
    record["expected"] = expected_ok(serialized, fills)
    return record


def real_cases(rows: Dict[str, Dict[str, Any]], tokenizer: Dict[str, Any]) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    for row_id, note in REAL_CASES:
        row = rows[row_id]
        serialized = v2.serialize(row["x"])
        cases.append({
            "caseId": f"real-{row_id}",
            "kind": "real",
            "note": note,
            "source": {"rowId": row_id, "sourceRowSha256": row["sourceRowSha256"],
                       "split": "train" if row_id in set(legacy.legacy_split()["train"])
                       else ("dev" if row_id in set(legacy.legacy_split()["dev"]) else "test")},
            "versions": {
                "projectionVersion": v2.PROJECTION_VERSION,
                "serializerVersion": v2.SERIALIZER_VERSION,
                "legacySerializerVersion": v2.LEGACY_SERIALIZER_VERSION,
                "modelTemplateVersion": v2.MODEL_TEMPLATE_VERSION,
                "tokenizerHash": tokenizer["sha256"],
                "tokenizerStatus": "bound",
            },
            "projection": row["x"],
            "normalization": row.get("normalizations", []),
            "expected": expected_ok(serialized, row.get("resultFills", [])),
        })
    return cases


def synthetic_cases(tokenizer: Dict[str, Any]) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []

    # 1. Item movement, result missing -> filled from the declaration.
    cases.append(make_case(
        "synthetic-item-move", "synthetic",
        projection_for({"铜钥匙": {"位置": "木箱"}}), tokenizer=tokenizer,
        tokenizer_check=True,
        note="item position result is filled; state item line uses 位于; result uses 位置"))

    # 2. Item movement + appearance in one result line.
    cases.append(make_case(
        "synthetic-item-move-appearance", "synthetic",
        projection_for({"铜钥匙": {"位置": "木箱", "新增外貌": ["多了一道刻痕"]}}),
        tokenizer=tokenizer, tokenizer_check=True,
        note="two item fields, fixed field order"))

    # 3. Zero sanity.
    cases.append(make_case(
        "synthetic-sanity-zero", "synthetic",
        projection_for({"阿青": {"精神值": 0}}), tokenizer=tokenizer,
        tokenizer_check=True,
        note="0 must be rendered, not dropped by a truthiness check"))

    # 4. Empty appearance list.
    cases.append(make_case(
        "synthetic-empty-appearance", "synthetic",
        projection_for({"阿青": {"解除外貌": ["短发"]}}), tokenizer=tokenizer,
        tokenizer_check=True,
        note="empty list result is explicit 外貌（空）"))

    # 5. Empty personality list.
    cases.append(make_case(
        "synthetic-empty-personality", "synthetic",
        projection_for({"阿青": {"解除个性": ["谨慎"]}}), tokenizer=tokenizer,
        tokenizer_check=True,
        note="empty list result is explicit 个性（空）"))

    # 6. Empty item appearance.
    cases.append(make_case(
        "synthetic-empty-item-appearance", "synthetic",
        projection_for({"铜钥匙": {"解除外貌": ["齿口磨平了。"]}}), tokenizer=tokenizer,
        tokenizer_check=True,
        note="item empty list result"))

    # 7. Empty place appearance.
    cases.append(make_case(
        "synthetic-empty-place-appearance", "synthetic",
        projection_for({"旧屋": {"解除外貌": ["墙皮剥落。"]}}), tokenizer=tokenizer,
        tokenizer_check=True,
        note="place empty list result"))

    # 8. Big task completed only.
    cases.append(make_case(
        "synthetic-task-big-complete", "synthetic",
        projection_for({"阿青": {"完成任务": ["找到钥匙"]}}), tokenizer=tokenizer,
        tokenizer_check=True,
        note="big task result without a small-task list"))

    # 9. Small task completed + new small task.
    cases.append(make_case(
        "synthetic-task-small-and-new", "synthetic",
        projection_for({"阿青": {"完成任务": ["翻找抽屉"],
                                 "新增小任务": [{"目标": "核对钥匙齿口",
                                                  "属于大任务": "找到钥匙",
                                                  "状态": "未完成"}]}}),
        tokenizer=tokenizer, tokenizer_check=True,
        note="task hierarchy: completed small task plus added small task"))

    # 10. Type order: place, person, item.
    cases.append(make_case(
        "synthetic-type-order", "synthetic",
        projection_for({
            "铜钥匙": {"新增外貌": ["多了一道刻痕"]},
            "阿青": {"精神值": 9},
            "旧屋": {"新增外貌": ["窗纸破了"]},
        }), tokenizer=tokenizer, tokenizer_check=True,
        note="result block groups 地点, then 人物, then 物品"))

    # 11. Non-BMP name sorting.  Python sorts by code point; JS default sorts
    # by UTF-16 code unit, which would put 𠀀 before ！.  The golden must catch it.
    non_bmp = {
        "地点": {
            "！": {"位于": None, "外貌": ["感叹号地点。"]},
            "阿": {"位于": None, "外貌": ["阿地点。"]},
            "𠀀": {"位于": None, "外貌": ["非BMP地点。"]},
        },
        "人物": {
            "！人": {"位置": "！", "精神值": 1, "外貌": [], "个性": [],
                     "任务": {"大任务": {"目标": "守", "状态": "未完成"}, "小任务": []}},
            "阿人": {"位置": "阿", "精神值": 2, "外貌": [], "个性": [],
                     "任务": {"大任务": {"目标": "守", "状态": "未完成"}, "小任务": []}},
            "𠀀人": {"位置": "𠀀", "精神值": 3, "外貌": [], "个性": [],
                      "任务": {"大任务": {"目标": "守", "状态": "未完成"}, "小任务": []}},
        },
        "物品": {
            "！物": {"位置": "！", "外貌": []},
            "阿物": {"位置": "阿", "外貌": []},
            "𠀀物": {"位置": "𠀀", "外貌": []},
        },
    }
    cases.append(make_case(
        "synthetic-non-bmp-sort", "synthetic",
        projection_for({
            "！": {"新增外貌": ["一"]},
            "阿": {"新增外貌": ["二"]},
            "𠀀": {"新增外貌": ["三"]},
        }, before=non_bmp), tokenizer=tokenizer, tokenizer_check=False,
        note="Python code-point order: 阿 < ！ < 𠀀; a JS UTF-16 sort would put 𠀀 first. "
             "The non-BMP name is intentionally outside the YuYan vocabulary; this vector "
             "tests ordering, not tokenizer acceptance."))

    # 12. No-change round.
    cases.append(make_case(
        "synthetic-no-change", "synthetic",
        projection_for({}), tokenizer=tokenizer, tokenizer_check=True,
        note="no result block; the fixed no-change sentence is present"))

    # 13. Ordinary space normalization in free text.
    cases.append(make_case(
        "synthetic-space-normalization", "synthetic",
        projection_for({"阿青": {"新增外貌": ["袖口沾了 灰"]}}, time="2 分钟"),
        tokenizer=tokenizer, tokenizer_check=True,
        note="ordinary spaces are removed and recorded in the ledger"))

    # 14. Tab normalization.
    cases.append(make_case(
        "synthetic-tab-normalization", "synthetic",
        projection_for({"阿青": {"新增外貌": ["袖口沾了\t灰"]}}, time="2\t分钟"),
        tokenizer=tokenizer, tokenizer_check=True,
        note="tab is removed and recorded"))

    # 15. Full-width space normalization.
    cases.append(make_case(
        "synthetic-fullwidth-space-normalization", "synthetic",
        projection_for({"阿青": {"新增外貌": ["袖口沾了\u3000灰"]}}, time="2\u3000分钟"),
        tokenizer=tokenizer, tokenizer_check=True,
        note="U+3000 is removed and recorded"))

    # 16. Long input above 1000 characters.
    long_appearance = [f"第{index}道划痕从门框一直延伸到墙根，像是有人反复搬过什么东西留下的。"
                       for index in range(1, 31)]
    long_world = base_world()
    long_world["地点"]["旧屋"]["外貌"] = long_appearance
    cases.append(make_case(
        "synthetic-long-input", "synthetic",
        projection_for({"旧屋": {"新增外貌": ["门框上多了一道新划痕"]}},
                       before=long_world), tokenizer=tokenizer, tokenizer_check=True,
        note="long input: render length is above the training median and the v1 maximum"))

    # Negative cases -------------------------------------------------------
    cases.append(make_case(
        "negative-unknown-entity", "negative",
        projection_for({"不存在的人": {"精神值": 3}}), tokenizer=tokenizer,
        note="an entity that is not in the before state is refused"))

    ambiguous_world = base_world()
    ambiguous_world["地点"]["阿青"] = {"位于": None, "外貌": ["重名地点。"]}
    cases.append(make_case(
        "negative-ambiguous-entity", "negative",
        projection_for({"阿青": {"精神值": 3}}, before=ambiguous_world),
        tokenizer=tokenizer,
        note="the same name in two entity tables is ambiguous"))

    cases.append(make_case(
        "negative-newline", "negative",
        projection_for({"阿青": {"精神值": 3}}, viewpoint="主角视角（阿青）\n只表达已结算事实"),
        tokenizer=tokenizer,
        note="CR/LF is refused, not silently removed"))

    cases.append(make_case(
        "negative-nbsp", "negative",
        projection_for({"阿青": {"新增外貌": ["袖口\u00a0沾灰"]}}), tokenizer=tokenizer,
        note="non-breaking space is unsupported whitespace, not silently removed"))

    cases.append(make_case(
        "negative-oov-emoji", "negative",
        projection_for({"阿青": {"新增外貌": ["袖口😀沾灰"]}}), tokenizer=tokenizer,
        tokenizer_check=True,
        note="serializer succeeds, tokenizer check refuses the OOV character"))

    cases.append(make_case(
        "negative-empty-viewpoint", "negative",
        projection_for({"阿青": {"精神值": 3}}, viewpoint=""),
        tokenizer=tokenizer,
        note="empty viewpoint is refused"))

    cases.append(make_case(
        "negative-unknown-result-field", "negative",
        projection_for({"阿青": {"精神值": 3}}, result={"阿青": {"眼睛": "红"}}),
        tokenizer=tokenizer,
        note="unknown result field is refused"))

    cases.append(make_case(
        "negative-unchanged-result-field", "negative",
        projection_for({"阿青": {"精神值": 3}}, result={"阿青": {"外貌": ["短发"]}}),
        tokenizer=tokenizer,
        note="a result field that no operation changed is refused"))

    cases.append(make_case(
        "negative-result-conflict", "negative",
        projection_for({"阿青": {"精神值": 3}}, result={"阿青": {"精神值": 4}}),
        tokenizer=tokenizer,
        note="the settled result and the declaration disagree"))

    cases.append(make_case(
        "negative-empty-result-entity", "negative",
        projection_for({"阿青": {"精神值": 3}}, result={"阿青": {}}),
        tokenizer=tokenizer, skip_build=True,
        note="a changed entity with an empty result view is refused"))

    cases.append(make_case(
        "negative-bool-sanity", "negative",
        projection_for({"阿青": {"精神值": True}}), tokenizer=tokenizer,
        note="bool is not an integer sanity value"))

    cases.append(make_case(
        "negative-unknown-change-field", "negative",
        projection_for({"阿青": {"飞行": "屋顶"}}), tokenizer=tokenizer,
        note="unknown delta operation is refused"))

    unknown_state = base_world()
    unknown_state["人物"]["阿青"]["年龄"] = 20
    cases.append(make_case(
        "negative-unknown-state-field", "negative",
        projection_for({"阿青": {"精神值": 3}}, before=unknown_state),
        tokenizer=tokenizer,
        note="unknown state field is refused"))

    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=DATA)
    parser.add_argument("--out", default=GOLDEN)
    parser.add_argument("--tokenizer", default=TOKENIZER)
    args = parser.parse_args()

    with io.open(os.path.join(args.data, "manifest.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    rows = {row["id"]: row for row in
            (json.loads(line) for line in
             io.open(os.path.join(args.data, "rows-v2.jsonl"), encoding="utf-8"))}
    tokenizer = load_tokenizer_profile(args.tokenizer)

    cases = real_cases(rows, tokenizer) + synthetic_cases(tokenizer)
    case_ids = [case["caseId"] for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise SystemExit("duplicate case ids")
    if len(cases) < 30:
        raise SystemExit(f"only {len(cases)} cases; the design asks for about 30")

    by_kind: Dict[str, int] = {}
    by_stage: Dict[str, int] = {}
    coverage: Dict[str, int] = {}
    for case in cases:
        by_kind[case["kind"]] = by_kind.get(case["kind"], 0) + 1
        expected = case["expected"]
        stage = expected.get("stage", "ok")
        by_stage[stage] = by_stage.get(stage, 0) + 1

    def has(case_id: str, needle: str) -> bool:
        case = next(item for item in cases if item["caseId"] == case_id)
        return needle in case["expected"].get("text", "")

    coverage["item_position"] = int(any("（位于" in case["expected"].get("text", "")
                                       for case in cases if "item-move" in case["caseId"]))
    coverage["empty_result"] = int(has("synthetic-empty-appearance", "外貌（空）")
                                   and has("synthetic-empty-personality", "个性（空）")
                                   and has("synthetic-empty-item-appearance", "外貌（空）")
                                   and has("synthetic-empty-place-appearance", "外貌（空）"))
    coverage["zero_sanity"] = int(has("synthetic-sanity-zero", "精神值0"))
    coverage["no_change"] = int(has("synthetic-no-change", "这一回合没有结算出变化。")
                                and not has("synthetic-no-change", "【本回合状态】"))
    coverage["task_hierarchy"] = int(has("synthetic-task-big-complete", "找到钥匙（已完成）")
                                     and has("synthetic-task-small-and-new", "核对钥匙齿口（未完成）"))
    non_bmp_case = next(item for item in cases if item["caseId"] == "synthetic-non-bmp-sort")
    non_bmp_text = non_bmp_case["expected"].get("text", "")
    coverage["non_bmp_sort"] = int(
        "阿（地点）" in non_bmp_text and "！（地点）" in non_bmp_text
        and "𠀀（地点）" in non_bmp_text
        and non_bmp_text.index("阿（地点）") < non_bmp_text.index("！（地点）") <
        non_bmp_text.index("𠀀（地点）"))
    coverage["whitespace_removed"] = int(has("synthetic-space-normalization", "袖口沾了灰")
                                         and has("synthetic-tab-normalization", "袖口沾了灰")
                                         and has("synthetic-fullwidth-space-normalization", "袖口沾了灰"))
    coverage["whitespace_refused"] = int(
        next(item for item in cases if item["caseId"] == "negative-newline")["expected"]["errorCode"]
        == "newline_not_allowed"
        and next(item for item in cases if item["caseId"] == "negative-nbsp")["expected"]["errorCode"]
        == "unsupported_whitespace")
    coverage["oov_refused"] = int(
        next(item for item in cases if item["caseId"] == "negative-oov-emoji")["expected"]["stage"]
        == "tokenizer")
    coverage["unknown_entity_refused"] = int(
        next(item for item in cases if item["caseId"] == "negative-unknown-entity")["expected"]["errorCode"]
        == "unknown_entity")
    coverage["long_input"] = int(max(len(case["expected"].get("text", "")) for case in cases) > 1000)

    golden_path = os.path.join(args.out, "vectors.jsonl")
    write_jsonl(golden_path, cases)
    golden_manifest = {
        "schema": "jity-narration-golden-v2",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "dataManifest": os.path.relpath(os.path.join(args.data, "manifest.json"), ROOT),
        "dataManifestSha256": hashlib.sha256(
            io.open(os.path.join(args.data, "manifest.json"), "rb").read()).hexdigest(),
        "versions": manifest["versions"],
        "tokenizer": public_profile(tokenizer),
        "cases": len(cases),
        "byKind": by_kind,
        "byExpectedStage": by_stage,
        "coverage": coverage,
        "sourceRows": [row_id for row_id, _ in REAL_CASES],
        "files": {
            "vectors.jsonl": {
                "bytes": os.path.getsize(golden_path),
                "sha256": hashlib.sha256(io.open(golden_path, "rb").read()).hexdigest(),
                "cases": len(cases),
            }
        },
        "howToUse": [
            "Read vectors.jsonl one JSON object per line.",
            "For expected.status == 'ok', feed projection to the browser serializer and compare "
            "the UTF-8 bytes with expected.bytesUtf8Hex / expected.sha256.",
            "Compare segments by charStart/charEnd (Unicode code points, not UTF-16 units).",
            "For expected.status == 'error', return the same errorCode at the same stage; do not "
            "fall back to a partial text.",
            "The target narrative is deliberately absent from every vector; do not look for it.",
        ],
    }
    manifest_path = os.path.join(args.out, "manifest.json")
    atomic_write(manifest_path, (json.dumps(golden_manifest, ensure_ascii=False,
                                            indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"cases": len(cases), "byKind": by_kind,
                      "byStage": by_stage, "coverage": coverage,
                      "vectors": golden_path, "manifest": manifest_path},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Diagnostic: what the 18/3/3/1 literal short format erased, and what a fix costs.

This is NOT the pairing serializer. The only official serializer is 04's
`experiments/action-next-step/pairwise_serialize.py`; lane 13 imports it and
never ships a second one. This script only measures, on the frozen 300 rows:

1. the 12 compressed-context collisions the coordinator reported, and whether
   the full X actually differs anywhere the short format cannot show;
2. whether adding the time (which lives inside the 地点 slot of the full X) and
   a second `刚才` line restores the lost distinction;
3. how often the 18-character goal clip removes the verb that the label names;
4. token length of the literal format and of the two candidate fixes, with the
   real MiniRBT tokenizer and special tokens.

Output goes to the shared results directory as JSON + a short markdown note.
Nothing here writes rows, labels, or a frozen artifact.
"""

from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import re
from pathlib import Path

SOURCE_SHA256 = "cb4676b3eb74945331f73ee8855be300455c9e11db261c288d7534c7b02ef188"
SNAPSHOT = Path("D:/others/Jity/artifacts/benchmark/minirbt-h256-snapshot")

GROUP_ORDER = [
    "感知", "移动", "战斗", "援助", "请求", "胁迫", "言语", "算计", "情绪", "物品", "身体", "立场",
]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def context_of(text: str) -> str:
    return text.rsplit("动作：", 1)[0]


def short_x(row: dict, *, goals: int = 18, with_time: bool = False, recent_lines: int = 1) -> str:
    """Assemble a candidate short X for measurement only."""
    x = row["x"]
    goals_text = "|".join(goal.split("：", 1)[-1][:goals] for goal in x["goals"])
    place = x["place"].split("（")[0]
    time_match = re.search(r"时间=([0-9T:\-]+)", x["place"])
    if with_time and time_match:
        place = f"{place}；时间={time_match.group(1)[11:16]}"
    present = "、".join(entry["name"] for entry in x["present"][:3]) or "无"
    items = "、".join(entry["name"] for entry in x["items"][:3]) or "无"
    recent = "；".join(line[:30] for line in x["recent"][-recent_lines:]) if x["recent"] and recent_lines else "无"
    return (
        f"任务：{goals_text}\n"
        f"所见：{place}；{present}；{items}\n"
        f"刚见：{recent}\n"
    )


def without_time(x: dict) -> str:
    stripped = copy.deepcopy(x)
    stripped["place"] = re.sub(r"；时间=[^；]*", "", stripped["place"])
    return json.dumps(stripped, ensure_ascii=False, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", required=True)
    parser.add_argument("--literal-pairs", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--tokenizer-dir", default=str(SNAPSHOT))
    args = parser.parse_args()

    rows = read_jsonl(Path(args.rows))
    digest = hashlib.sha256(Path(args.rows).read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise SystemExit(f"rows digest {digest} is not the frozen 300-row file")
    by_id = {row["rowId"]: row for row in rows}
    literal = read_jsonl(Path(args.literal_pairs))

    # 1. collisions in the literal format
    contexts: dict[str, set[str]] = collections.defaultdict(set)
    for pair in literal:
        contexts[context_of(pair["text"])].add(pair["rowId"])
    collisions = {text: sorted(ids) for text, ids in contexts.items() if len(ids) > 1}

    inventory = []
    for text, ids in collisions.items():
        labels = {row_id: by_id[row_id]["yGroup"] for row_id in ids}
        identical_without_time = {
            json.dumps(without_time(by_id[row_id]["x"]), ensure_ascii=False) for row_id in ids
        }
        inventory.append(
            {
                "rowIds": ids,
                "labels": labels,
                "distinctLabels": sorted(set(labels.values())),
                "identicalExceptTime": len(identical_without_time) == 1,
                "recentCounts": {row_id: len(by_id[row_id]["x"]["recent"]) for row_id in ids},
                "recent": {row_id: by_id[row_id]["x"]["recent"] for row_id in ids},
                "time": {
                    row_id: (re.search(r"时间=([0-9T:\-]+)", by_id[row_id]["x"]["place"]) or [None, None])[1]
                    for row_id in ids
                },
            }
        )

    # 2. does the fix restore distinctness?
    def distinct(collision: dict, *, with_time: bool, recent_lines: int) -> bool:
        texts = {
            short_x(by_id[row_id], with_time=with_time, recent_lines=recent_lines)
            for row_id in collision["rowIds"]
        }
        return len(texts) == len(collision["rowIds"])

    resolution = {
        "literal": sum(1 for item in inventory if not distinct(item, with_time=False, recent_lines=1)),
        "time": sum(1 for item in inventory if not distinct(item, with_time=True, recent_lines=1)),
        "time+2recent": sum(1 for item in inventory if not distinct(item, with_time=True, recent_lines=2)),
    }

    # 3. does the 18-char goal clip hide the object the label names?
    def candidate_name(row: dict, object_id: str | None) -> str | None:
        if not object_id:
            return None
        for entry in row["x"]["candidates"]:
            if entry["id"] == object_id:
                return entry["name"]
        return None

    clip_rows = []
    for row in rows:
        steps = row["y"]["steps"]
        if not steps:
            continue
        name = candidate_name(row, steps[0]["object"])
        if not name:
            continue
        goal_texts = [goal.split("：", 1)[-1] for goal in row["x"]["goals"]]
        in_head = any(name in goal[:18] for goal in goal_texts)
        in_tail = any(name in goal[18:] for goal in goal_texts)
        if not in_head:
            clip_rows.append({"rowId": row["rowId"], "object": name, "inTail": in_tail})
    goal_counts = collections.Counter(len(row["x"]["goals"]) for row in rows)

    # 4. token length of the variants
    from transformers import BertTokenizer  # local import so the report explains itself

    tokenizer = BertTokenizer.from_pretrained(args.tokenizer_dir)
    variants = {
        "literal": dict(with_time=False, recent_lines=1, goals=18),
        "time": dict(with_time=True, recent_lines=1, goals=18),
        "time+2recent": dict(with_time=True, recent_lines=2, goals=18),
        "time+2recent+goals24": dict(with_time=True, recent_lines=2, goals=24),
    }
    lengths = {}
    for name, options in variants.items():
        texts = [short_x(row, **options) for row in rows]
        chars = sorted(len(text) for text in texts)
        tokens = sorted(len(tokenizer.encode(text, add_special_tokens=True)) for text in texts)
        lengths[name] = {
            "chars": {"min": chars[0], "p50": chars[len(chars) // 2], "p95": chars[int(len(chars) * 0.95)], "max": chars[-1]},
            "tokens": {"min": tokens[0], "p50": tokens[len(tokens) // 2], "p95": tokens[int(len(tokens) * 0.95)], "max": tokens[-1]},
            "over512": sum(1 for value in tokens if value > 512),
            "ceil32": ((tokens[-1] + 31) // 32) * 32,
        }

    report = {
        "kind": "lane-13-diagnostic-not-serializer-not-training-data",
        "sourceSha256": digest,
        "rows": len(rows),
        "literalPairs": len(literal),
        "collisions": len(inventory),
        "collisionInventory": sorted(inventory, key=lambda item: item["rowIds"]),
        "stillCollidingAfterFix": resolution,
        "conflictingLabels": [item for item in inventory if len(item["distinctLabels"]) > 1],
        "identicalExceptTime": sum(1 for item in inventory if item["identicalExceptTime"]),
        "goalCounts": dict(sorted(goal_counts.items())),
        "rowsWhoseObjectNameIsNotInAnyGoalHead": clip_rows,
        "lengths": lengths,
        "tokenizerDir": args.tokenizer_dir,
        "notes": [
            "the literal 所见 line drops the time that the full X keeps inside 地点",
            "the literal 刚见 line keeps only the last perceivable event",
            "the four conflicting-label groups are identical in the full X except the timestamp; "
            "no compression change can make their labels consistent",
            "candidate ids are metadata; printing them is a separate length variant owned by 04",
        ],
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("collisions", "stillCollidingAfterFix", "identicalExceptTime")}, ensure_ascii=False))
    print(json.dumps(lengths, ensure_ascii=False))
    print("label-verb-only-after-18:", len(clip_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

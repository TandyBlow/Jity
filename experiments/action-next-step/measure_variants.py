# Measure how long the delivered X really is, and what a documented projection
# would cost, before anyone sets maxLen.
#
# The frozen rule (freeze.json: maxLenRule) refuses rows longer than 384 tokens
# instead of truncating them. lane-13's batch1 rows render to 455-1460 chars, so
# no row fits today. This script measures variants side by side; it does NOT
# define a serializer and does not change what training reads. If a variant is
# chosen, the serializer changes in its own commit and the freeze is renewed.
#
# Usage: python measure_variants.py --rows <13 rows jsonl> [--out variant-report.json]

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dataset import read_rows  # noqa: E402
from serialize import _entity, _list_slot, _text, render_x, row_x  # noqa: E402

NEWLINE = chr(10)
MAXLEN_CAP = 384


def goal_short(goal: str, words: int = 24) -> str:
    return goal if len(goal) <= words else goal[:words] + "…"


def joined(parts) -> str:
    return NEWLINE.join(parts)


def recent_text(recent) -> str:
    items = recent if isinstance(recent, list) else [recent]
    return "；".join(_text(item) for item in items) if items else "（无）"


def variant_a(row: dict) -> str:
    """Every slot, but goals cut to the first two and personality to 120 chars."""
    x = row_x(row)
    goals = x["goals"][:2]
    personality = x["personality"]
    if len(personality) > 120:
        personality = personality[:120] + "…"
    return joined([
        f"角色：{_entity(x['character'], with_holds=True)}",
        f"目标：{'；'.join(goals) if goals else '（无）'}",
        f"地点：{x['place'] or '（无）'}",
        f"在场：{_list_slot(x['present'])}",
        f"物品：{_list_slot(x['items'], with_place=True)}",
        f"刚才：{recent_text(x['recent'])}",
        f"精神：{_text(x['sanity']) or '（无）'}",
        f"个性：{personality or '（无）'}",
        f"候选：{_list_slot(x['candidates'], with_place=True)}",
    ])


def variant_b(row: dict) -> str:
    """A, with the two shortest goals, shorter personality, and candidate/item
    labels without container text."""
    x = row_x(row)
    goals = sorted(x["goals"], key=len)[:2]
    personality = x["personality"]
    if len(personality) > 80:
        personality = personality[:80] + "…"
    return joined([
        f"角色：{_entity(x['character'])}",
        f"目标：{'；'.join(goal_short(item, 30) for item in goals) if goals else '（无）'}",
        f"地点：{x['place'] or '（无）'}",
        f"在场：{_list_slot(x['present'])}",
        f"物品：{_list_slot(x['items'])}",
        f"刚才：{recent_text(x['recent'])}",
        f"精神：{_text(x['sanity']) or '（无）'}",
        f"个性：{personality or '（无）'}",
        f"候选：{_list_slot(x['candidates'])}",
    ])


def variant_c(row: dict) -> str:
    """The shape that can fit a 512-token encoder at all: every goal kept (so
    the model, not the builder, chooses which one to serve) but clipped to 24
    chars, personality to 80, and counted list limits on present/items/candidates."""
    x = row_x(row)
    personality = x["personality"]
    if len(personality) > 80:
        personality = personality[:80] + "…"
    return joined([
        f"角色：{_entity(x['character'])}",
        f"目标：{'；'.join(goal_short(item, 24) for item in x['goals']) if x['goals'] else '（无）'}",
        f"地点：{x['place'] or '（无）'}",
        f"在场：{_list_slot(x['present'], limit=6)}",
        f"物品：{_list_slot(x['items'], limit=6)}",
        f"刚才：{recent_text(x['recent'])}",
        f"精神：{_text(x['sanity']) or '（无）'}",
        f"个性：{personality or '（无）'}",
        f"候选：{_list_slot(x['candidates'], limit=8)}",
    ])


def stats(values):
    ordered = sorted(values)
    if not ordered:
        return {}

    def pick(q: float) -> int:
        return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]

    return {
        "min": ordered[0], "p50": pick(0.5), "p90": pick(0.9), "p100": ordered[-1],
        "mean": round(sum(ordered) / len(ordered), 1),
        "overCap": sum(1 for value in ordered if value > MAXLEN_CAP),
        "maxLenIfRule": min(512, ((ordered[-1] + 31) // 32) * 32),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", nargs="+", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    rows = []
    for path in args.rows:
        rows.extend(read_rows(path))
    # Offline proxy: one character counts as one token. BertTokenizer for Chinese
    # is character-based, so this is the closest bound available without the
    # weights; the real tokenizer confirms it on the HPC before training.
    measure = lambda text: len(text) + 2  # noqa: E731
    report = {
        "rows": len(rows),
        "tokensAre": "characters + 2 (offline proxy; the real BertTokenizer must confirm on HPC)",
        "cap": MAXLEN_CAP,
        "variants": {
            "frozen-x1": stats([measure(render_x(row)) for row in rows]),
            "variant-a-goals2-personality120": stats([measure(variant_a(row)) for row in rows]),
            "variant-b-goals2-short-no-places": stats([measure(variant_b(row)) for row in rows]),
            "variant-c-all-goals-24-personality80-lists-6-8": stats([measure(variant_c(row)) for row in rows]),
        },
    }
    text = json.dumps(report, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

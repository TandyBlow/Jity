# -*- coding: utf-8 -*-
"""Score a passage on the style features measured from the hand-written rows.

The features come from narratives/style-notes.md: paragraph count, median
paragraph length, share of one-sentence paragraphs, share of paragraphs that
open with a line of dialogue, mean sentence length, comma-to-period ratio,
exclamation marks, ellipses.

  python score_style.py file1.txt file2.txt ...
  python score_style.py --json runs/report.json --field samples[*].output
"""

import argparse
import io
import json
import statistics
import sys


def strip_quotes(line):
    return line.strip().strip("「」")


def features(text):
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return None
    para_lens = [len(p) for p in paragraphs]
    single = sum(1 for p in paragraphs if p.count("。") + p.count("」") <= 1)
    dialogue = sum(1 for p in paragraphs if p.startswith("「"))
    # a sentence ends at 。 or 」; count both so dialogue lines are not zero-length
    sentences = [s for s in text.replace("」", "」。").split("。") if s.strip()]
    sent_lens = [len(s) for s in sentences]
    body = len(text)
    return {
        "段落数": len(paragraphs),
        "段落长度中位数": statistics.median(para_lens),
        "单句段落占比": round(single / len(paragraphs), 2),
        "对白段落占比": round(dialogue / len(paragraphs), 2),
        "平均句长": round(statistics.mean(sent_lens), 1) if sent_lens else 0,
        "逗号句号比": round(text.count("，") / max(text.count("。"), 1), 2),
        "感叹号": text.count("！") + text.count("!"),
        "省略号": text.count("…"),
        "字数": body,
    }


def collect(args):
    items = []
    if args.json:
        payload = json.load(io.open(args.json, encoding="utf-8"))
        for path in args.field:
            node = payload
            for part in path.split("."):
                if part.endswith("[*]"):
                    node = [item[part[:-3]] for item in node]
                    break
                node = node[part]
            for index, text in enumerate(node):
                items.append((f"{path}[{index}]", text))
        return items
    for path in args.files:
        items.append((path, io.open(path, encoding="utf-8").read()))
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*")
    parser.add_argument("--json")
    parser.add_argument("--field", action="append", default=[])
    args = parser.parse_args()
    rows = []
    for name, text in collect(args):
        stats = features(text)
        if stats:
            rows.append((name, stats))
    keys = list(rows[0][1]) if rows else []
    print("| 来源 | " + " | ".join(keys) + " |")
    print("|" + "---|" * (len(keys) + 1))
    for name, stats in rows:
        print(f"| {name} | " + " | ".join(str(stats[k]) for k in keys) + " |")
    if len(rows) > 1:
        mean = {k: round(statistics.mean(s[k] for _, s in rows), 1) for k in keys
                if isinstance(rows[0][1][k], (int, float))}
        print(f"| **均值（{len(rows)} 段）** | " + " | ".join(str(mean[k]) for k in keys) + " |")


if __name__ == "__main__":
    main()

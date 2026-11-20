"""Make a fixed, stratified train/dev/test split and freeze it on disk.

Why: picking the epoch on the same rows we then report means the reported number
is optimistic, and a 2-row or 10-row holdout is too noisy to rank epochs. This
script writes one split file that every later run must reuse, so numbers stay
comparable.

Stratification key = the set of change kinds in the row (完成任务+新增外貌+精神值
and so on). Rows are dealt out round-robin inside each stratum, so every change
shape appears in dev and test in roughly the same proportion as in train.

Usage:
  python -X utf8 make_split.py --dev 0.20 --test 0.10 --out splits/v1.json
"""
import argparse
import collections
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def signature(row):
    change = row["x"]["本回合变化"]["变化"]
    kinds = collections.Counter()
    for spec in change.values():
        for key in spec:
            kinds[key] += 1
    return "+".join(sorted(kinds)) or "none"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default=os.path.join(HERE, "rows-xy.jsonl"))
    ap.add_argument("--dev", type=float, default=0.20)
    ap.add_argument("--test", type=float, default=0.10)
    ap.add_argument("--out", default=os.path.join(HERE, "splits", "v1.json"))
    args = ap.parse_args()

    rows = [json.loads(line) for line in io.open(args.rows, encoding="utf-8")]
    total = len(rows)
    want_test = max(1, round(total * args.test))
    want_dev = max(1, round(total * args.dev))

    strata = collections.defaultdict(list)
    for row in rows:
        strata[signature(row)].append(row["id"])
    for ids in strata.values():
        ids.sort()

    # Interleave the strata (biggest first) so that adjacent rows come from
    # different change shapes. Systematic sampling over that interleaved list
    # then covers every shape, instead of spending dev/test on the two most
    # common shapes the way a naive first-come allocation does.
    order = sorted(strata.items(), key=lambda item: (-len(item[1]), item[0]))
    interleaved, depth = [], 0
    while True:
        added = False
        for _, ids in order:
            if depth < len(ids):
                interleaved.append(ids[depth])
                added = True
        if not added:
            break
        depth += 1

    def systematic(count):
        return {min(total - 1, int((j + 0.5) * total / count))
                for j in range(count)}

    test_pos = systematic(want_test)
    dev_pos = systematic(want_dev) - test_pos
    test = [interleaved[p] for p in sorted(test_pos)]
    dev = [interleaved[p] for p in sorted(dev_pos)]

    dev = sorted(set(dev))
    test = sorted(set(test))
    train = sorted(set(r["id"] for r in rows) - set(dev) - set(test))

    by_id = {r["id"]: r for r in rows}
    split = {"dev": dev, "test": test, "train": train,
             "fractions": {"dev": args.dev, "test": args.test}}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(split, handle, ensure_ascii=False, indent=1)

    def describe(label, ids):
        chars = [len(by_id[i]["y"]) for i in ids]
        shapes = collections.Counter(signature(by_id[i]) for i in ids)
        print(f"{label}: {len(ids)} 行 ({len(ids)/total:.0%}) "
              f"平均 {sum(chars)//max(len(chars),1)} 字 "
              f"变化形状 {len(shapes)} 种 最常见 {shapes.most_common(1)}")

    describe("train", train)
    describe("dev  ", dev)
    describe("test ", test)
    print(f"写入 {args.out}")


if __name__ == "__main__":
    main()

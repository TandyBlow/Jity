"""Inventory the group-arm material and build what already exists.

Group targets must be aligned to fact ids by a human, not cut at punctuation.
The only such material on disk is the `annotations` field of the n4n corpus:
each entry carries `text` plus `covers: [factId]`. This script counts how far
that reaches and emits the groups it can vouch for.
"""
import json, pathlib, re
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "artifacts" / "world-components" / "n4-group-material-r1.json"
EXCLUDE = {"n4n-03", "n4n-15"}


def rows(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8")
            .splitlines() if l.strip()]


def fact_line(f):
    k = f["kind"]
    if k == "moved":
        return f'{f["factId"]}｜移动｜{f["name"]}｜{f.get("from")}→{f.get("to")}'
    if k == "outcome":
        return f'{f["factId"]}｜结果｜{f["name"]}｜{f.get("resultText")}'
    if k == "appearance_changed":
        return f'{f["factId"]}｜外观｜{f["name"]}｜{f.get("text")}'
    if k == "appearance_removed":
        return f'{f["factId"]}｜外观消失｜{f["name"]}｜{f.get("text", "")}'
    if k == "personality_changed":
        return f'{f["factId"]}｜性情｜{f["name"]}｜{f.get("text")}'
    if k == "sanity_changed":
        d = "上升" if f.get("to", 0) >= f.get("from", 0) else "下降"
        return f'{f["factId"]}｜理智｜{f["name"]}｜{d}'
    if k == "no_change":
        return f'{f["factId"]}｜无变化｜'
    if k == "time":
        return f'{f["factId"]}｜时间｜时间经过'
    return None


def build_group_input(para_input, group_ids, facts):
    head = para_input.split("事实：")[0]
    lines = [fact_line(f) for f in facts if f["factId"] in group_ids]
    lines = [x for x in lines if x]
    return (head + "事实：\n" + "\n".join(lines) + "\n分组：\n"
            f"G1｜{' '.join(group_ids)}｜组后时间=过去了一会儿\n"
            + "视角：" + para_input.split("视角：", 1)[1])


def main():
    corpus = rows(HERE / "corpus_v1.jsonl") + rows(HERE / "corpus.jsonl") + \
        rows(HERE / "corpus_v2.jsonl")
    para = {r["sourceId"]: r for r in rows(HERE / "formal_pairs.jsonl")}
    shared = [r for r in corpus if r["id"] in para and r["id"] not in EXCLUDE]

    inventory = {
        "sources": len(shared),
        "factsPerSource": dict(Counter(len([f for f in r["facts"] if f["kind"] != "time"])
                                       for r in shared)),
        "sourcesWithTwoPlusFacts": sum(
            1 for r in shared if len([f for f in r["facts"] if f["kind"] != "time"]) >= 2),
        "sourcesWithAnnotations": sum(1 for r in shared if r.get("annotations")),
        "bySplit": dict(Counter(para[r["id"]]["split"] for r in shared)),
    }

    groups, problems, annotated = [], [], []
    for r in shared:
        ann = [a for a in (r.get("annotations") or []) if a.get("covers")]
        if not ann:
            continue
        annotated.append(r["id"])
        required = [f["factId"] for f in r["facts"] if f["kind"] != "time"]
        seen = [fid for a in ann for fid in a["covers"]]
        if sorted(seen) != sorted(required):
            problems.append({"sourceId": r["id"], "kind": "coverage-mismatch",
                             "required": required, "covered": sorted(seen)})
            continue
        if len(seen) != len(set(seen)):
            problems.append({"sourceId": r["id"], "kind": "fact-in-two-groups",
                             "covered": seen})
            continue
        for i, a in enumerate(ann, 1):
            gid = f'{r["id"]}:g{i}'
            groups.append({
                "groupId": gid, "sourceId": r["id"],
                "split": para[r["id"]]["split"],
                "factIds": list(a["covers"]),
                "input": build_group_input(para[r["id"]]["input"],
                                           a["covers"], r["facts"]),
                "target": a["text"],
                "elaboration": a.get("elaboration") or [],
            })

    # 机械信号：目标里出现阿拉伯数字，或目标没有覆盖到组内事实的实词
    for g in groups:
        if re.search(r"[0-9]", g["target"]):
            problems.append({"groupId": g["groupId"], "kind": "digit-in-target"})

    rec = {
        "purpose": "group-arm material inventory and what exists on disk",
        "excluded": sorted(EXCLUDE),
        "inventory": inventory,
        "annotatedSources": annotated,
        "groups": groups,
        "problems": problems,
        "gap": {
            "sourcesWithoutGroupTargets": inventory["sources"] - len(annotated),
            "note": "group targets need fact-id alignment; punctuation splitting is "
                    "not accepted, so the rest has to be written or aligned by hand",
        },
    }
    OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(inventory, ensure_ascii=False))
    print("annotated sources:", len(annotated), annotated)
    print("groups built:", len(groups), "| problems:", len(problems))
    for p in problems[:5]:
        print("  !", p)
    from collections import Counter as C2
    print("groups by split:", dict(C2(g["split"] for g in groups)))
    print("->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

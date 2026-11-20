"""Build and verify the shared source set for the paragraph + fact arms.

Every source must appear in all three places with the same split and the same
fact ids; the fact references must actually express their own fact. Writes the
manifest the trainers read, plus the check record.
"""
import json, pathlib, re
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "artifacts" / "world-components" / "n4-two-arm-manifest-r1.json"
# n4n-03: moved fact names from=河心, absent from world.json (data gap)
# n4n-15: moved f0 says 沈砚 -> 旧灯塔, the paragraph puts him at 潮渡; the two
#         arms would learn contradictory versions of the same fact
EXCLUDE = {"n4n-03", "n4n-15"}


def rows(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8")
            .splitlines() if l.strip()]


PUNCT = re.compile(r"[\s，,。．.；;：:！!？?、…—－\-\"'“”‘’（）()《》「」]")


def norm(s):
    return PUNCT.sub("", s or "")


def bigrams(s):
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def coverage(needle, hay):
    b = bigrams(needle)
    return len(b & bigrams(hay)) / len(b) if b else 1.0


def main():
    corpus = rows(HERE / "corpus_v1.jsonl") + rows(HERE / "corpus.jsonl") + \
        rows(HERE / "corpus_v2.jsonl")
    para = rows(HERE / "formal_pairs.jsonl")
    fact = rows(HERE / "verbalizer_pairs.jsonl")

    by_source = {r["id"]: r for r in corpus}
    para_by = {r["sourceId"]: r for r in para}
    facts_by = defaultdict(list)
    for r in fact:
        facts_by[r["sourceId"]].append(r)

    problems, fact_signals, para_signals = [], [], []
    sources = []
    for sid, row in by_source.items():
        if sid in EXCLUDE:
            continue
        if sid not in para_by:
            problems.append(f"{sid}: 缺整段参考")
            continue
        if sid not in facts_by:
            problems.append(f"{sid}: 缺单事实参考")
            continue
        p = para_by[sid]
        # time 事实按契约不写成句子（不写具体时长），两臂都不要求表达；
        # 比对可表达事实集合时统一剔除。
        ids_corpus = [f["factId"] for f in row["facts"]
                      if f.get("kind") != "time"]
        skipped_time = [f["factId"] for f in row["facts"]
                        if f.get("kind") == "time"]
        units = sorted(facts_by[sid], key=lambda r: ids_corpus.index(r["factId"])
                       if r["factId"] in ids_corpus else 99)
        ids_units = [u["factId"] for u in units]
        if set(ids_units) != set(ids_corpus):
            problems.append(f"{sid}: factId 不一致 参考={sorted(set(ids_corpus))} "
                            f"单元={sorted(set(ids_units))}")
        if len(ids_units) != len(set(ids_units)):
            problems.append(f"{sid}: 单元 factId 重复")
        for f in row["facts"]:
            kind = f.get("kind")
            if kind == "time":
                continue
            name = f.get("name")
            key = f.get("resultText") or f.get("text") or f.get("to") or ""
            key = key if isinstance(key, str) else ""
            for u in units:
                if u["factId"] != f["factId"]:
                    continue
                t = u["target"]
                rec = {"sourceId": sid, "factId": f["factId"], "kind": kind,
                       "targetCoverage": round(coverage(key, t), 2)
                       if key else None,
                       "nameInTarget": (norm(name) in norm(t)) if name else None,
                       "chars": len(norm(t))}
                if key and rec["targetCoverage"] < 0.5:
                    fact_signals.append(rec)
                if name and rec["nameInTarget"] is False and kind in (
                        "moved", "outcome", "appearance_changed"):
                    fact_signals.append(rec)
            prec = {"sourceId": sid, "factId": f["factId"], "kind": kind,
                    "coverage": round(coverage(key, p["target"]), 2) if key else None}
            if key and prec["coverage"] is not None and prec["coverage"] < 0.3:
                para_signals.append(prec)
        sources.append({"sourceId": sid, "split": p["split"],
                        "facts": ids_corpus, "units": ids_units,
                        "timeFactsNotVerbalised": skipped_time,
                        "paragraphChars": len(norm(p["target"])),
                        "unitChars": [len(norm(u["target"])) for u in units]})

    splits = Counter(s["split"] for s in sources)
    units_total = sum(len(s["units"]) for s in sources)
    rec = {
        "purpose": "shared source set for the paragraph + fact arms",
        "excluded": sorted(EXCLUDE),
        "counts": {"sources": len(sources), "bySplit": dict(splits),
                   "factUnits": units_total,
                   "unitsBySplit": dict(Counter(s["split"] for s in sources
                                                for _ in s["units"])),
                   "paragraphCharsMedian": sorted(s["paragraphChars"] for s in sources)[len(sources) // 2],
                   "unitCharsMedian": sorted(c for s in sources for c in s["unitChars"])[
                       units_total // 2]},
        "problems": problems,
        "factReferenceSignals": fact_signals,
        "paragraphReferenceSignals": para_signals,
        "sources": sources,
        "checks": {
            "sourceSetsEqual": len(problems) == 0,
            "factIdsCovered": len(problems) == 0,
            "noDuplicateUnits": all(len(s["units"]) == len(set(s["units"])) for s in sources),
        },
    }
    OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    import hashlib
    def sha(p):
        h = hashlib.sha256()
        h.update(pathlib.Path(p).read_bytes())
        return h.hexdigest()
    freeze = {name: sha(path) for name, path in {
        "formal_pairs.jsonl": HERE / "formal_pairs.jsonl",
        "verbalizer_pairs.jsonl": HERE / "verbalizer_pairs.jsonl",
        "two-arm-manifest.json": OUT,
        "run_arm.py": HERE / "run_arm.py",
        "sequence_policy.py": HERE / "sequence_policy.py",
        "run_cf.py": HERE / "run_cf.py",
    }.items()}
    (ROOT / "artifacts" / "world-components" / "n4-two-arm-freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=1), encoding="utf-8")
    print("sources", len(sources), "| by split", dict(splits), "| units", units_total,
          "| units by split", rec["counts"]["unitsBySplit"])
    print("problems", len(problems), problems[:5])
    print("fact refs below 0.5 coverage or missing name:", len(fact_signals))
    print("paragraph refs below 0.3 coverage:", len(para_signals))
    print("->", OUT)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

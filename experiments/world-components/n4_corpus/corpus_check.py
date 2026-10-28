# N4 corpus row checker: per-row faithfulness checks + group consistency +
# rewrite overlap signal + distribution report. Negative self-test built in
# (two bad rows MUST be caught, else the report is void).
#
# Protocol: corpus_protocol.md §1/§4/§5.
#
# Usage: python experiments/world-components/n4_corpus/corpus_check.py [corpus.jsonl]

import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent


def corpus_files() -> list:
    if len(sys.argv) > 1:
        return [pathlib.Path(p) for p in sys.argv[1:]]
    files = [HERE / "corpus.seeds.jsonl"]
    rewrites = HERE / "rewrites.jsonl"
    if rewrites.exists():
        files.append(rewrites)
    return files

REQUIRED = ["sourceGroupId", "rowOrigin", "rewriter", "task", "split", "plan",
            "planConstruction", "planValidation", "text", "planRefs",
            "mustExpress", "mayMention", "mustNotAdd", "hashes", "purpose"]

CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def cn_to_int(s: str):
    """Parse simple Chinese numerals up to 99; None if not a number."""
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + CN_DIGITS[s[1]] if len(s) == 2 else None
    if "十" in s:
        tens = CN_DIGITS.get(s[0])
        if tens is None or tens < 2:
            return None
        ones = CN_DIGITS.get(s[2], 0) if len(s) == 3 else 0
        return tens * 10 + ones
    return CN_DIGITS.get(s)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_row(r: dict, idx: int):
    problems = []
    gid = r.get("sourceGroupId", f"<row{idx}>")

    for k in REQUIRED:
        if k not in r:
            problems.append(f"missing field {k}")
    if problems:
        return problems

    text, plan, refs = r["text"], r["plan"], r["planRefs"]
    sentences = [s for s in text.split("。") if s.strip()]
    if len(sentences) != len(refs):
        problems.append(f"planRefs has {len(refs)} entries for {len(sentences)} sentences")

    # ref index validity + referenced-by-sentence checks
    n = len(plan)
    cited = set()
    for si, srefs in enumerate(refs):
        sent = sentences[si] if si < len(sentences) else ""
        for ref in srefs:
            if not isinstance(ref, int) or not (0 <= ref < n):
                problems.append(f"sentence {si}: plan ref {ref} out of range (plan has {n})")
                continue
            cited.add(ref)
            entry = plan[ref]
            kind = entry.get("kind")
            if kind == "time":
                amount, unit = entry["amount"], entry["unit"]
                unit_word = "分钟" if unit == "minute" else "小时"
                if unit_word not in sent:
                    problems.append(f"sentence {si}: time unit {unit_word} not asserted")
                else:
                    before = sent.split(unit_word)[0]
                    num = re.findall(r"[\d]+|[零一二两三四五六七八九十]+", before)
                    nums = [cn_to_int(x) for x in num]
                    nums = [x for x in nums if x is not None]
                    if amount not in nums:
                        problems.append(
                            f"sentence {si}: time amount {amount} not asserted (found {nums} before {unit_word})")
            else:
                name = entry.get("name", "")
                if name and name not in sent:
                    problems.append(f"sentence {si}: entity {name} not in cited sentence")
                if kind == "moved":
                    if entry["from"] not in sent or entry["to"] not in sent:
                        problems.append(
                            f"sentence {si}: moved {entry['from']}->{entry['to']} not both asserted")
                elif kind == "task_achieved":
                    if entry["goal"] not in sent:
                        problems.append(f"sentence {si}: task goal quote not verbatim")
                elif kind == "personality_changed":
                    if entry["text"] not in sent:
                        problems.append(f"sentence {si}: personality text not asserted")
                elif kind == "sanity_changed":
                    lo, hi = str(entry["from"]), str(entry["to"])
                    if lo not in sent or hi not in sent:
                        problems.append(f"sentence {si}: sanity {lo}->{hi} not asserted")
                elif kind == "appearance_changed":
                    if entry["text"] not in sent:
                        problems.append(f"sentence {si}: appearance text not asserted")
                elif kind == "positioned_at":
                    if entry["at"] not in sent:
                        problems.append(f"sentence {si}: position {entry['at']} not asserted")

    must = set(r["mustExpress"])
    if not must <= cited:
        problems.append(f"mustExpress {sorted(must - cited)} not covered by planRefs")

    if r["rowOrigin"] == "rewrite":
        if r.get("rewriter") != "zcode-model":
            problems.append("rewrite row must register rewriter zcode-model")
        if "overlap" not in r or "ratio" not in r.get("overlap", {}):
            problems.append("rewrite row missing overlap.ratio")
    elif r.get("rewriter") != "program":
        problems.append("template-seed row must have rewriter=program")

    if r["hashes"]["text"] != sha(text):
        problems.append("text hash mismatch")
    plan_canon = json.dumps(plan, ensure_ascii=False, sort_keys=True)
    if r["hashes"]["plan"] != hashlib.sha256(plan_canon.encode("utf-8")).hexdigest():
        problems.append("plan hash mismatch")

    return problems


def masked_bigrams(text: str, names: set, goals: set) -> set:
    """§4: mask names/values+units/quotes before bigram overlap."""
    t = text
    for name in sorted(names, key=len, reverse=True):
        t = t.replace(name, "⟨N⟩")
    for goal in sorted(goals, key=len, reverse=True):
        t = t.replace(goal, "⟨Q⟩")
    t = re.sub(r"[零一二两三四五六七八九十\d]+(分钟|小时)", "⟨V⟩", t)
    t = re.sub(r"精神值从\d+升到\d+|精神值由\d+降至\d+", "⟨V⟩", t)
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else set()


def main() -> None:
    inputs = corpus_files()
    rows = []
    for cf in inputs:
        rows += [json.loads(line) for line in
                 cf.read_text(encoding="utf-8").splitlines() if line.strip()]

    # ---- negative self-test: two bad rows MUST fail, else report is void ----
    good = dict(rows[0])
    bad_idx = dict(good)
    bad_idx["planRefs"] = [[7]]
    bad_must = dict(good)
    bad_must["mustExpress"] = [5]
    bad_must["planRefs"] = [[0, 1]]
    neg = []
    if not check_row(bad_idx, -1):
        neg.append("self-test: out-of-range ref NOT caught")
    if not check_row(bad_must, -1):
        neg.append("self-test: uncovered mustExpress NOT caught")
    if neg:
        print("REPORT VOID — checker self-test failed:")
        for x in neg:
            print(" ", x)
        sys.exit(2)

    # ---- group consistency (plan/split/mustExpress are group-level; purpose is per-row) ----
    groups = {}
    for r in rows:
        groups.setdefault(r["sourceGroupId"], []).append(r)
    gfail = 0
    for gid, members in groups.items():
        for key in ["split", "plan", "mustExpress"]:
            vals = {json.dumps(m.get(key), ensure_ascii=False, sort_keys=True)
                    for m in members}
            if len(vals) > 1:
                gfail += 1
                print(f"GROUP FAIL {gid}: inconsistent {key}")
    print(f"group checks: {len(groups) - gfail}/{len(groups)} groups consistent")

    # ---- rewrite overlap signal (computed BEFORE row checks: check_row
    # requires overlap.ratio on rewrite rows) ----
    by_group_seeds = {gid: [m for m in ms if m["rowOrigin"] == "template-seed"]
                      for gid, ms in groups.items()}
    rewrites = [r for r in rows if r["rowOrigin"] == "rewrite"]
    for r in rewrites:
        seeds = by_group_seeds.get(r["sourceGroupId"], [])
        if not seeds:
            continue
        names = {e["name"] for e in r["plan"] if "name" in e}
        goals = {e["goal"] for e in r["plan"] if e["kind"] == "task_achieved"}
        rb = masked_bigrams(r["text"], names, goals)
        ratios = []
        for s in seeds:
            sb = masked_bigrams(s["text"], names, goals)
            if sb:
                ratios.append(len(rb & sb) / len(rb))
        r["overlap"] = {"ratio": round(max(ratios), 3) if ratios else None,
                        "method": "masked-bigram-jaccard-vs-seed (protocol §4)"}
        flag = " REVIEW-FLAG" if (r["overlap"]["ratio"] or 0) > 0.6 else ""
        print(f"overlap {r['sourceGroupId']} ({r['rewriter']}): "
              f"ratio={r['overlap']['ratio']}{flag}")

    # ---- per-row checks ----
    failures = 0
    for i, r in enumerate(rows):
        problems = check_row(r, i)
        if problems:
            failures += 1
            print(f"FAIL {r['sourceGroupId']} ({r['rowOrigin']}):")
            for p in problems:
                print(f"   - {p}")
    print(f"row checks: {len(rows) - failures}/{len(rows)} pass")

    # ---- distribution report ----
    print("\ndistribution:")
    for key in ["rowOrigin", "rewriter", "split"]:
        counts = {}
        for r in rows:
            counts[r[key]] = counts.get(r[key], 0) + 1
        print(f"  {key}: {counts}")
    fam = {}
    for r in rows:
        famname = r["sourceGroupId"].rsplit("-", 1)[0]
        fam[famname] = fam.get(famname, 0) + 1
    print(f"  families: {fam}")
    time_rows = sum(1 for r in rows if any(e["kind"] == "time" for e in r["plan"]))
    empty = sum(1 for r in rows if r["sourceGroupId"].startswith("n4-empty"))
    multi = sum(1 for r in rows if r["sourceGroupId"].startswith("n4-multi"))
    quote = sum(1 for r in rows if any(e["kind"] == "task_achieved" for e in r["plan"]))
    print(f"  time-statement rows: {time_rows}/{len(rows)}, empty-point: {empty}, "
          f"multi-entity: {multi}, task-quote: {quote}")

    if failures or gfail:
        sys.exit(1)


if __name__ == "__main__":
    main()

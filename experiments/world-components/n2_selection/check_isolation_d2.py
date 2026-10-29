# D2 isolation scan: the 8 capability items vs B's frozen corpus.
#
# Reuses the frozen exclusion pool builder and matcher from
# check_isolation.py (pinned B commit, same source lists) and scans the
# content strings of d2_capability_items.jsonl with the same field
# extraction rules used for the 16-item set. Zero hits within the listed
# scope means no verbatim reuse of B's narration corpus. The scan never
# mutates the pinned pool or the pinned commit.

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_isolation as ci  # noqa: E402

OUT = HERE.parent.parent.parent / "artifacts" / "world-components" / "n2-isolation-d2.json"


def d2_strings() -> dict:
    items = [json.loads(line) for line in
             (HERE / "d2_capability_items.jsonl").read_text(
                 encoding="utf-8").splitlines() if line.strip()]
    out = {}
    for it in items:
        strings = [it["viewpoint"].get("name"), it["viewpoint"].get("rule")]
        for f in it["facts"]:
            for k in ("name", "from", "to", "goal", "text", "at", "scope"):
                strings.append(f.get(k))
        for s in strings:
            if isinstance(s, str) and len(s) >= 2:
                out.setdefault(s, set()).add(it["itemId"])
    return out


def selftest() -> list:
    problems = []
    pool = {"潮音渡口的风"}
    hits = ci.match_hits(pool, {"潮音渡口的风": {"n3cap-selftest"}})
    if "潮音渡口的风" not in hits:
        problems.append("selftest: planted string not matched")
    hits2 = ci.match_hits(pool, {"潮音渡": {"n3cap-selftest"}})
    if "潮音渡" not in hits2:
        problems.append("selftest: substring containment not caught")
    return problems


def main() -> int:
    problems = selftest()
    if problems:
        for p in problems:
            print("SELFTEST FAIL:", p)
        return 1
    print("selftest PASS: planted string caught; exact matching pinned")
    pool, manifest, missing, details = ci.collect_frozen(ci.PINNED_MAIN_COMMIT)
    strings = d2_strings()
    hits = ci.match_hits(pool, strings)
    record = {
        "purpose": "D2 capability items isolation vs B frozen corpus",
        "decision": "D2",
        "pinnedMainCommit": ci.PINNED_MAIN_COMMIT,
        "poolDigest": ci.pool_digest(pool),
        "poolStrings": len(pool),
        "sources": [{"label": d.get("label"), "kind": d.get("kind"),
                     "sha256": d.get("sha256"), "listSha256": d.get("listSha256")}
                    for d in details],
        "manifest": manifest,
        "missingSources": missing,
        "scannedStrings": len(strings),
        "scannedItems": len({i for ids in strings.values() for i in ids}),
        "verdict": "ZERO_HIT" if not hits else "HIT",
        "hits": hits,
        "stringList": sorted(strings),
        "tool": "check_isolation_d2.py (reuses check_isolation.collect_frozen/match_hits)",
    }
    OUT.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"frozen pool: {len(pool)} strings, digest {ci.pool_digest(pool)[:16]}…")
    print(f"scanned d2 strings: {len(strings)} across "
          f"{len({i for ids in strings.values() for i in ids})} items")
    print(f"verdict: {record['verdict']} -> {OUT.name}")
    return 0 if not hits else 1


if __name__ == "__main__":
    sys.exit(main())

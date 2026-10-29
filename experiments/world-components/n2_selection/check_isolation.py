# N2 dev-set isolation check (round 18).
#
# The N2 items use a THIRD vocabulary (裴行舟/沈拾/... and 石阶码头/旧钟铺/...),
# disjoint from the N4 corpus cast and from the frozen N4 holdout cast. This
# script verifies it against the same B-line exclusion sources dedup_check.py
# uses, with the same rule: strings >= 4 chars are checked as bidirectional
# substrings; shorter cast words are reported, not failed.
#
# Verdict wording stays limited, as in dedup_check: "zero hits within the
# listed scope and rules". Renaming/derivation beyond substring matching is
# not provable here.
#
# Usage: python experiments/world-components/n2_selection/check_isolation.py
# Output: prints a verdict; exit 1 on any hit

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
CWT = REPO
MAIN = pathlib.Path("D:/others/Jity")

SOURCES = [
    ("frontend/src/lib/world-engine/runtime/narration-eval-samples.ts", CWT, "nv-*"),
    ("frontend/src/lib/world-engine/runtime/narration-eval-validation.ts", CWT, "hv-*"),
    ("frontend/src/lib/world-engine/runtime/narration-split-samples.ts", CWT, "ns-*"),
    ("frontend/src/lib/world-engine/runtime/b3-samples.ts", CWT, "b3-*"),
    ("artifacts/narration-eval-recheck/run.json", CWT, "archived run"),
    ("artifacts/narration-split-baseline.json", CWT, "split baseline"),
    ("artifacts/narration-http-review.json", CWT, "http review"),
]
GLOBS = [("artifacts/world-page/*.json", CWT, "page archive"),
         ("artifacts/world-chain/*.json", MAIN, "chain archive")]


def strings_of(obj, out):
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            strings_of(v, out)
    elif isinstance(obj, list):
        for v in obj:
            strings_of(v, out)


def collect() -> tuple:
    pool, manifest = set(), []
    for rel, base, label in SOURCES:
        p = base / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        strs = set()
        if p.suffix == ".json":
            out = []
            try:
                strings_of(json.loads(text), out)
            except Exception:
                out = []
            strs = {s for s in out if len(s) >= 4}
        else:
            import re
            strs = {s for s in re.findall(r'[^"\'`\n\r]{4,}', text)}
        pool |= strs
        manifest.append((label, str(p), len(strs)))
    for pattern, base, label in GLOBS:
        for p in sorted(base.glob(pattern)):
            out = []
            try:
                strings_of(json.loads(p.read_text(encoding="utf-8")), out)
            except Exception:
                continue
            strs = {s for s in out if len(s) >= 4}
            pool |= strs
            manifest.append((label, p.name, len(strs)))
    return pool, manifest


def n2_strings() -> dict:
    items = [json.loads(l) for l in (HERE / "items.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    out = {}
    for it in items:
        for f in it["facts"]:
            for k in ("name", "from", "to", "goal", "text", "at", "scope"):
                if isinstance(f.get(k), str):
                    out.setdefault(f[k], set()).add(it["itemId"])
        if isinstance(it["viewpoint"].get("name"), str):
            out.setdefault(it["viewpoint"]["name"], set()).add(it["itemId"])
    return out


def main() -> None:
    pool, manifest = collect()
    n2 = n2_strings()
    long_hits, cast_hits = {}, {}
    for s, ids in n2.items():
        if len(s) >= 4:
            hits = [p for p in pool if s in p or p in s]
            if hits:
                long_hits[s] = (sorted(ids)[:3], hits[:2])
        else:
            hits = [p for p in pool if s in p]
            if hits:
                cast_hits[s] = (sorted(ids)[:3], hits[:1])
    print(f"exclusion pool: {len(pool)} strings from {len(manifest)} sources")
    print(f"N2 vocabulary: {len(n2)} strings "
          f"({sum(1 for s in n2 if len(s) >= 4)} >=4 chars, "
          f"{sum(1 for s in n2 if len(s) < 4)} short cast/location words)")
    for s, (ids, hits) in long_hits.items():
        print(f"HIT(long) {s!r} items={ids} vs {hits}")
    for s, (ids, hits) in cast_hits.items():
        print(f"hit(cast) {s!r} items={ids} vs {hits}")
    print(f"verdict: {len(long_hits)} long-string hit(s), {len(cast_hits)} cast hit(s) "
          f"— zero-hit within the listed scope and rules means no verbatim reuse "
          f"of the archived material")
    print("known limits: substring only; renaming/derivation not provable; "
          "B's runtime TS code is not scanned")
    sys.exit(1 if (long_hits or cast_hits) else 0)


if __name__ == "__main__":
    main()

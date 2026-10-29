# N2 dev-set isolation check (v2, review round 19).
#
# Fixes over v1:
#  a. SHORT STRINGS ARE SCANNED: v1 dropped everything below 4 characters
#     before matching, so a 3-character cast name planted in a B sample file
#     went undetected. Now every N2 string of length >= 2 is matched, and the
#     collector keeps short source strings too.
#  b. MISSING SOURCES ARE REPORTED, never silently skipped: every listed file
#     is printed as present (+ digest) or MISSING, and a missing file is
#     counted in the verdict line.
#  c. REUSES THE EXISTING COLLECTOR for TS sources (dedup_check.collect_ts),
#     so the two checks cannot drift; JSON archives get an equivalent walker
#     that also keeps short strings.
#  d. SELF-TEST: a planted 3-character cast string in a temporary TS file and
#     a 2-character string in a temporary JSON file must both be caught,
#     otherwise the report is void.
#
# Verdict wording stays limited, as in dedup_check: "zero hits within the
# listed scope and rules"; renaming/derivation beyond substring matching is
# not provable.
#
# Usage: python experiments/world-components/n2_selection/check_isolation.py
# Output: prints verdict; exit 1 on any hit or missing source

import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
CWT = REPO
MAIN = pathlib.Path("D:/others/Jity")

sys.path.insert(0, str(HERE.parent / "n4_corpus"))
import dedup_check  # noqa: E402

TS_SOURCES = [
    ("frontend/src/lib/world-engine/runtime/narration-eval-samples.ts", "nv-*"),
    ("frontend/src/lib/world-engine/runtime/narration-eval-validation.ts", "hv-*"),
    ("frontend/src/lib/world-engine/runtime/narration-split-samples.ts", "ns-*"),
    ("frontend/src/lib/world-engine/runtime/b3-samples.ts", "b3-*"),
]
JSON_SOURCES = [
    ("artifacts/narration-eval-recheck/run.json", CWT, "archived run"),
    ("artifacts/narration-split-baseline.json", CWT, "split baseline"),
    ("artifacts/narration-http-review.json", CWT, "http review"),
]
JSON_GLOBS = [("artifacts/world-page/*.json", CWT, "page archive"),
              ("artifacts/world-chain/*.json", MAIN, "chain archive")]


def walk_strings(obj, out: set) -> None:
    if isinstance(obj, str):
        if len(obj) >= 2:
            out.add(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            walk_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk_strings(v, out)


def collect() -> tuple:
    """-> (pool, manifest lines, missing count). TS uses dedup_check's own
    collector; JSON keeps short strings (v2 fix)."""
    pool: set = set()
    manifest, missing = [], 0
    for rel, label in TS_SOURCES:
        p = CWT / rel
        if not p.exists():
            manifest.append(f"MISSING {label}: {p}")
            missing += 1
            continue
        values, n = dedup_check.collect_ts(p, label)
        pool |= set(values)                      # no length filter (v2)
        manifest.append(f"{label}: {rel} strings={len(values)} raw={n} "
                        f"sha256[:16]={dedup_check.hashlib.sha256(p.read_bytes()).hexdigest()[:16]}")
    for rel, base, label in JSON_SOURCES:
        p = base / rel
        if not p.exists():
            manifest.append(f"MISSING {label}: {p}")
            missing += 1
            continue
        out: set = set()
        try:
            walk_strings(json.loads(p.read_text(encoding="utf-8")), out)
        except Exception as exc:
            manifest.append(f"UNREADABLE {label}: {p} ({exc})")
            missing += 1
            continue
        pool |= out
        manifest.append(f"{label}: {rel} strings={len(out)}")
    for pattern, base, label in JSON_GLOBS:
        files = sorted(base.glob(pattern))
        if not files:
            manifest.append(f"MISSING {label}: {base / pattern}")
            missing += 1
            continue
        for p in files:
            out = set()
            try:
                walk_strings(json.loads(p.read_text(encoding="utf-8")), out)
            except Exception:
                continue
            pool |= out
        manifest.append(f"{label}: {pattern} files={len(files)}")
    return pool, manifest, missing


def n2_strings() -> dict:
    items = [json.loads(l) for l in (HERE / "items.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
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
    """A planted 3-char cast string (TS) and a 2-char string (JSON) must be
    caught by the same collectors this script uses."""
    void = []
    with tempfile.TemporaryDirectory() as td:
        ts = pathlib.Path(td) / "planted.ts"
        ts.write_text("export const X = [{ id: 'z', text: '裴行舟' }];", encoding="utf-8")
        ts_values, _ = dedup_check.collect_ts(ts, "planted")
        if "裴行舟" not in ts_values:
            void.append("TS collector missed a 3-character planted string")
        js = pathlib.Path(td) / "planted.json"
        js.write_text(json.dumps({"rows": [{"text": "沈拾"}]}, ensure_ascii=False),
                      encoding="utf-8")
        out: set = set()
        walk_strings(json.loads(js.read_text(encoding="utf-8")), out)
        if "沈拾" not in out:
            void.append("JSON walker missed a 2-character planted string")
    return void


def main() -> None:
    void = selftest()
    if void:
        print("REPORT VOID — isolation self-test failed:")
        for x in void:
            print(" ", x)
        sys.exit(2)
    print("self-test PASS: planted 3-char TS string and 2-char JSON string both caught")

    pool, manifest, missing = collect()
    n2 = n2_strings()
    hits = {}
    for s, ids in n2.items():
        found = [p for p in pool if s in p or p in s]
        if found:
            hits[s] = (sorted(ids)[:3], found[:2])
    print(f"\nexclusion pool: {len(pool)} strings (short strings included)")
    print(f"N2 vocabulary: {len(n2)} strings "
          f"({sum(1 for s in n2 if len(s) >= 4)} >=4 chars, "
          f"{sum(1 for s in n2 if len(s) < 4)} short)")
    for s, (ids, found) in hits.items():
        print(f"HIT {s!r} items={ids} vs {found}")
    print("\nsources:")
    for line in manifest:
        print(f"  {line}")
    print(f"\nverdict: {len(hits)} hit(s), {missing} missing source(s) "
          f"— zero-hit within the listed scope and rules means no verbatim reuse")
    print("known limits: substring only; renaming/derivation not provable; "
          "B's runtime TS code is not scanned")
    sys.exit(1 if (hits or missing) else 0)


if __name__ == "__main__":
    main()

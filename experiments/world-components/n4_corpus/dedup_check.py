# N4 corpus dedup checker against B-line corpora (protocol §2).
#
# Scans the exclusion list (nv-*/hv-*/ns-* sample files, b3-samples, archived
# run/baseline JSONs), extracts all designated string fields, and checks every
# corpus row's text+plan against that set (bidirectional substring for sources
# >= 4 chars; shorter cast words are REGISTERED, not failed - new vocab is
# designed for zero cast hits, any hit means go back and rename).
#
# Forbid-string note-stripping variants: for every source containing （…）,
# the core string without the parenthetical is added to the source set too -
# direct regression for the smoke-probe lesson (narration-freeform was
# nv-cont-1's forbidden core with the note stripped).
#
# Verdict wording is LIMITED by design: "zero hits within the listed scope
# and rules" - renaming/direction-flip derivations beyond substring matching
# are NOT provable here and stay with human review (protocol §2).
#
# Self-test: the smoke probe sentence (known derivation) MUST hit
# nv-cont-1's forbidden core; otherwise the report is void.
#
# Usage: python experiments/world-components/n4_corpus/dedup_check.py <corpus.jsonl>...

import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent  # n4_corpus -> world-components -> experiments -> worktree root

# (label, path-or-glob, kind) - kind: ts / json / glob-json
SOURCES = [
    ("narration-eval-samples.ts (nv-*)",
     "frontend/src/lib/world-engine/runtime/narration-eval-samples.ts", "ts"),
    ("narration-eval-validation.ts (hv-*)",
     "frontend/src/lib/world-engine/runtime/narration-eval-validation.ts", "ts"),
    ("narration-split-samples.ts (ns-*)",
     "frontend/src/lib/world-engine/runtime/narration-split-samples.ts", "ts"),
    ("b3-samples.ts",
     "frontend/src/lib/world-engine/runtime/b3-samples.ts", "ts"),
    ("artifacts/narration-eval-recheck/run.json",
     "artifacts/narration-eval-recheck/run.json", "json"),
    ("artifacts/narration-split-baseline.json",
     "artifacts/narration-split-baseline.json", "json"),
]

# v3 (review round 3): full-chain live-run archives are part of the required
# exclusion scope. They are untracked in the B main tree and absent from the
# C worktree, so resolution order is: C worktree -> B main tree; unresolved
# entries are reported as missing, never silently skipped.
EXTRA_SOURCES = [
    ("artifacts/world-page/*.json (整链页面归档)",
     "artifacts/world-page", "glob-json"),
    ("artifacts/world-chain/*.json (整链运行归档)",
     "artifacts/world-chain", "glob-json"),
    ("artifacts/narration-http-review.json (真实 HTTP 叙事复核)",
     "artifacts/narration-http-review.json", "json"),
]
MAIN_TREE = pathlib.Path("D:/others/Jity")

TS_SINGLE = re.compile(r"\b(mechanical|reference|goal|note|text|phrase|desc|appearance|initialAppearance|name|from|to)\s*:\s*'([^']+)'")
TS_ARRAY = re.compile(r"\b(?:forbidden|mayMention|mustNotFabricate)\s*:\s*\[([^\]]*)\]")
TS_STR = re.compile(r"'([^']+)'")

# Schema enum values / field names that legitimately appear in both corpora:
# shared protocol vocabulary, not narrative content. Excluded from JSON
# recursive collection (documented in the manifest, per protocol §2).
GENERIC_TOKENS = {
    "moved", "positioned_at", "task_achieved", "personality_changed",
    "sanity_changed", "appearance_changed", "position", "appearance",
    "personality", "sanity", "task", "time", "movement", "multi_character",
    "continuity", "empty_delta", "task_personality_sanity", "root", "commit",
}

KNOWN_MISSES = [
    "TS 类型代码与注释不扫",
    "整链归档的 narration-*.md 等 Markdown 产物不扫（json 产物已全部纳入）",
    "模板句式拼接代码以短语人工核对补（「没有新的变化」教训，种子句式已避开）",
]

# Corpus fields that carry NARRATIVE CONTENT and are substring-scanned.
# Structural fields (kind/unit/ref/amount/entityId/rendered/scope) are
# excluded: they are protocol vocabulary, and short values like kind="time"
# produce false direction hits against long meta-strings ("time" ⊂
# "timePassage…") — review finding on v1 per-field matching.
CONTENT_FIELDS = {"name", "from", "to", "at", "goal", "text"}


def strip_notes(s: str) -> list:
    """Forbid-string note-stripping variants: （…） suffix/prefix removed."""
    out = []
    m = re.search(r"（[^）]*）", s)
    if m:
        core = (s[:m.start()] + s[m.end():]).strip()
        if len(core) >= 4:
            out.append(core)
    return out


def collect_ts(path: pathlib.Path, label: str):
    """value -> set of origins. Key is the VALUE (v1 keyed by field NAME and
    silently dropped same-named later fields — review-found bug)."""
    text = path.read_text(encoding="utf-8")
    fields = {}
    n = 0
    for m in TS_SINGLE.finditer(text):
        fields.setdefault(m.group(2), set()).add(f"{label}:{m.group(1)}")
        n += 1
    for m in TS_ARRAY.finditer(text):
        for s in TS_STR.findall(m.group(1)):
            fields.setdefault(s, set()).add(f"{label}:{m.group(1)}-array")
            n += 1
    return fields, n


def collect_json(path: pathlib.Path, label: str):
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}

    def walk(o):
        if isinstance(o, str):
            if len(o) >= 4 and o not in GENERIC_TOKENS:
                out.setdefault(o, set()).add(f"{label}:json")
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return out, len(out)


def main() -> None:
    corpus_files = [pathlib.Path(p) for p in sys.argv[1:]]
    rows = []
    for cf in corpus_files:
        rows += [json.loads(line) for line in
                 cf.read_text(encoding="utf-8").splitlines() if line.strip()]

    source_set = {}   # >=4 chars: value -> origins
    cast_set = {}     # <4 chars: value -> origins
    manifest = []

    def resolve(rel: str):
        for base in (REPO, MAIN_TREE):
            p = base / rel
            if p.exists():
                return p, str(base.name)
        return None, None

    def ingest(path: pathlib.Path, label: str, kind: str):
        if kind == "ts":
            fields, n = collect_ts(path, label)
        else:
            fields, n = collect_json(path, label)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        for s, origins in fields.items():
            if len(s) >= 4:
                source_set.setdefault(s, set()).update(origins)
                for core in strip_notes(s):
                    source_set.setdefault(core, set()).update(
                        o + "+note-stripped" for o in origins)
            else:
                cast_set.setdefault(s, set()).update(origins)
        manifest.append({"source": label, "file": str(path.relative_to(path.anchor))
                         if False else str(path), "sha256_16": digest,
                         "extractedStrings": n})

    for label, rel, kind in SOURCES:
        path, base = resolve(rel)
        if path is None:
            manifest.append({"source": label, "file": rel, "status": "MISSING"})
            continue
        ingest(path, f"{label} [{base}]", kind)
    for label, rel, kind in EXTRA_SOURCES:
        target, base = resolve(rel)
        if target is None:
            manifest.append({"source": label, "file": rel, "status": "MISSING"})
            continue
        if kind == "glob-json":
            files = sorted(target.glob("*.json"))
            if not files:
                manifest.append({"source": label, "file": rel, "status": "MISSING(no json)"})
                continue
            total = 0
            for f in files:
                _f, n = collect_json(f, label)
                total += n
                digest = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
                for s, origins in collect_json(f, f"{label} [{base}]")[0].items():
                    if len(s) >= 4:
                        source_set.setdefault(s, set()).update(origins)
                        for core in strip_notes(s):
                            source_set.setdefault(core, set()).update(
                                o + "+note-stripped" for o in origins)
                    else:
                        cast_set.setdefault(s, set()).update(origins)
                manifest.append({"source": f"{label} [{base}]", "file": str(f),
                                 "sha256_16": digest, "extractedStrings": n})
            continue
        ingest(target, f"{label} [{base}]", kind)

    print(f"source set: {len(source_set)} strings (>=4 chars, substring-checked), "
          f"{len(cast_set)} cast words (<4 chars, registered)")

    # self-test: the known derivation MUST be caught
    probe = "用一句中文叙述以下变化：学生A从大厅走到了走廊。时间过去了约三十分钟。"
    hits = [s for s in source_set if s in probe or probe in s]
    if not any("方向反转" in s or "学生A从大厅走到了走廊" in s for s in hits):
        print("REPORT VOID — self-test failed: smoke probe derivation not caught")
        print("  hits:", hits)
        sys.exit(2)
    print(f"self-test PASS: probe derivation caught via {hits}")

    # scan corpus: PER-FIELD bidirectional matching over CONTENT fields only
    # (text + plan semantic values; structural keys excluded, see
    # CONTENT_FIELDS note).
    corpus_fields = []
    for r in rows:
        fields = [("text", r["text"])]
        for e in r.get("plan", []):
            for k, v in e.items():
                if k in CONTENT_FIELDS and isinstance(v, str):
                    fields.append((f"plan.{k}", v))
        for fname, field in fields:
            if field:
                corpus_fields.append((r["sourceGroupId"], fname, field))

    failures = 0
    cast_hits = {}
    for gid, fname, field in corpus_fields:
        hits = [(s, o) for s, o in source_set.items() if s in field or field in s]
        if hits:
            failures += 1
            print(f"HIT {gid} [{fname}]:")
            for s, origins in hits:
                print(f"   - {s!r}  (from {sorted(origins)[0]})")
        for w, origins in cast_set.items():
            if w in field:
                cast_hits.setdefault(w, set()).add(gid)

    print(f"\nsubstring scan: {len(rows) - failures}/{len(rows)} rows zero-hit "
          f"(within the listed scope and rules)")
    if cast_hits:
        print("cast-word hits (registered, design goal = zero; rename required):")
        for w, gids in cast_hits.items():
            print(f"   - {w!r}: {gids}")
        failures += len(cast_hits)
    else:
        print("cast-word hits: none (new vocabulary is disjoint from B cast)")

    print("\nknown misses (NOT covered by this scan):")
    for x in KNOWN_MISSES:
        print(f"   - {x}")
    print("\nsource manifest:")
    for m in manifest:
        print(f"   - {m['source']}: sha256[:16]={m['sha256_16']}, "
              f"{m['extractedStrings']} strings")

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

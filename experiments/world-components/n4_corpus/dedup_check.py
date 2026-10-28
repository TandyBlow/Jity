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

# (label, path, kind) - kind: ts-field extraction or json-recursive
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
    "world-page/、world-chain/ 等整链归档的真机输入原文未扫",
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
    for label, rel, kind in SOURCES:
        path = REPO / rel
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
        manifest.append({"source": label, "file": rel, "sha256_16": digest,
                         "extractedStrings": n})

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

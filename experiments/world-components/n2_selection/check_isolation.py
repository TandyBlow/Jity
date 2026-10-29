# N2 dev-set isolation check (v3, review round 22).
#
# Fixes over v2:
#  a. THE CANONICAL POOL IS FROZEN: v2 scanned B's live main worktree, so
#     poolStrings moved every time B wrote another run archive (4023 -> 4041
#     -> 4042 -> 4048 in one afternoon). v3 reads B's TRACKED corpus at
#     PINNED_MAIN_COMMIT via `git show`, so the archived number is
#     reproducible from the commit alone.
#  b. THE LIVE DIAGNOSTIC IS STILL RUN AND ARCHIVED: `liveDiagnostic` scans
#     the current working tree (including untracked run archives) and
#     `excludedWorkingFiles` lists the files present on disk but absent at
#     the pinned commit, so a live/canonical difference is attributable.
#  c. EVERY FILE IS HASHED WITH THE SAME BYTES THAT ARE PARSED, and the
#     archive carries poolDigest (sorted strings), sourceDigest (per-file
#     hashes) and the pinned commit. A cited number is only meaningful
#     together with those digests.
#  d. v2 fixes kept: short strings are scanned; missing sources are
#     reported; the TS collector is shared with dedup_check; the planted
#     3-char/2-char self-test voids the report on failure.
#
# Verdict wording stays limited, as in dedup_check: "zero hits within the
# listed scope and rules"; renaming/derivation beyond substring matching is
# not provable.
#
# Usage: python experiments/world-components/n2_selection/check_isolation.py [--archive]
# Output: prints the frozen verdict (canonical) and the live diagnostic;
#         exit 1 on any hit or missing source in either.
#         With --archive writes artifacts/world-components/n2-isolation-r2.json.

import datetime
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
CWT = REPO
MAIN = pathlib.Path("D:/others/Jity")

# B / world-browser HEAD when this round's pool was frozen. Bump only with a
# reviewable reason; the archive names it so a number cannot silently drift.
PINNED_MAIN_COMMIT = "8878e970278a9d311ea1ff669527eebb078458da"

sys.path.insert(0, str(HERE.parent / "n4_corpus"))
import dedup_check  # noqa: E402

TS_SOURCES = [
    ("frontend/src/lib/world-engine/runtime/narration-eval-samples.ts", "nv-*"),
    ("frontend/src/lib/world-engine/runtime/narration-eval-validation.ts", "hv-*"),
    ("frontend/src/lib/world-engine/runtime/narration-split-samples.ts", "ns-*"),
    ("frontend/src/lib/world-engine/runtime/b3-samples.ts", "b3-*"),
]
JSON_SOURCES = [
    ("artifacts/narration-eval-recheck/run.json", "archived run"),
    ("artifacts/narration-split-baseline.json", "split baseline"),
    ("artifacts/narration-http-review.json", "http review"),
]
JSON_GLOBS = [("artifacts/world-page", "page archive"),
              ("artifacts/world-chain", "chain archive")]


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


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pool_digest(pool: set) -> str:
    h = hashlib.sha256()
    for s in sorted(pool):
        h.update(s.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def source_digest(details: list) -> str:
    return hashlib.sha256(json.dumps(
        details, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def git_bytes(commit: str, rel: str):
    r = subprocess.run(["git", "-C", str(MAIN), "show", f"{commit}:{rel}"],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def git_json_files(commit: str, dirpath: str) -> list:
    r = subprocess.run(["git", "-C", str(MAIN), "ls-tree", "-r", "--name-only",
                        commit, "--", dirpath], capture_output=True, text=True)
    if r.returncode != 0:
        return []
    return [line for line in r.stdout.splitlines() if line.endswith(".json")]


def parse_ts(data: bytes, label: str):
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "source.ts"
        p.write_bytes(data)
        return dedup_check.collect_ts(p, label)


def match_hits(pool: set, n2: dict) -> dict:
    hits = {}
    for s, ids in n2.items():
        found = [p for p in pool if s in p or p in s]
        if found:
            hits[s] = {"items": sorted(ids)[:3], "matched": found[:2]}
    return hits


def collect_frozen(commit: str) -> tuple:
    """B's tracked corpus at `commit`: pool, manifest, missing, details."""
    pool: set = set()
    manifest, missing, details = [], 0, []
    for rel, label in TS_SOURCES:
        data = git_bytes(commit, rel)
        if data is None:
            manifest.append(f"MISSING {label}: {rel} @ {commit[:8]}")
            missing += 1
            continue
        values, n = parse_ts(data, label)
        pool |= set(values)                      # no length filter (v2)
        digest = sha_bytes(data)
        manifest.append(f"{label}: {rel} strings={len(values)} raw={n} "
                        f"sha256[:16]={digest[:16]}")
        details.append({"label": label, "kind": "ts", "path": rel,
                        "sha256": digest, "strings": len(values)})
    for rel, label in JSON_SOURCES:
        data = git_bytes(commit, rel)
        if data is None:
            manifest.append(f"MISSING {label}: {rel} @ {commit[:8]}")
            missing += 1
            continue
        out: set = set()
        try:
            walk_strings(json.loads(data), out)
        except Exception as exc:
            manifest.append(f"UNREADABLE {label}: {rel} ({exc})")
            missing += 1
            continue
        pool |= out
        digest = sha_bytes(data)
        manifest.append(f"{label}: {rel} strings={len(out)} sha256[:16]={digest[:16]}")
        details.append({"label": label, "kind": "json", "path": rel,
                        "sha256": digest, "strings": len(out)})
    for dirpath, label in JSON_GLOBS:
        files = git_json_files(commit, dirpath)
        if not files:
            manifest.append(f"MISSING {label}: {dirpath}/*.json @ {commit[:8]}")
            missing += 1
            continue
        files_detail = []
        for rel in files:
            data = git_bytes(commit, rel)
            if data is None:
                continue
            out = set()
            try:
                walk_strings(json.loads(data), out)
            except Exception:
                continue
            pool |= out
            files_detail.append({"path": pathlib.PurePosixPath(rel).name,
                                 "sha256": sha_bytes(data), "strings": len(out)})
        list_sha = sha_bytes("".join(f["sha256"] for f in files_detail).encode("ascii"))
        manifest.append(f"{label}: {dirpath}/*.json files={len(files)} "
                        f"listSha256[:16]={list_sha[:16]}")
        details.append({"label": label, "kind": "json_glob",
                        "base": f"B@{commit[:8]}", "dir": dirpath,
                        "listSha256": list_sha, "files": files_detail})
    return pool, manifest, missing, details


def collect_live() -> tuple:
    """Current main-worktree corpus, including untracked files (diagnostic
    only: this is the moving number v2 cited by mistake)."""
    pool: set = set()
    manifest, missing, details = [], 0, []
    for rel, label in TS_SOURCES:
        p = MAIN / rel
        if not p.exists():
            manifest.append(f"MISSING {label}: {p}")
            missing += 1
            continue
        data = p.read_bytes()
        values, n = parse_ts(data, label)
        pool |= set(values)
        digest = sha_bytes(data)
        manifest.append(f"{label}: {rel} strings={len(values)} raw={n} "
                        f"sha256[:16]={digest[:16]}")
        details.append({"label": label, "kind": "ts", "path": rel,
                        "sha256": digest, "strings": len(values)})
    for rel, label in JSON_SOURCES:
        p = MAIN / rel
        if not p.exists():
            manifest.append(f"MISSING {label}: {p}")
            missing += 1
            continue
        data = p.read_bytes()
        out: set = set()
        try:
            walk_strings(json.loads(data), out)
        except Exception as exc:
            manifest.append(f"UNREADABLE {label}: {p} ({exc})")
            missing += 1
            continue
        pool |= out
        digest = sha_bytes(data)
        manifest.append(f"{label}: {rel} strings={len(out)} sha256[:16]={digest[:16]}")
        details.append({"label": label, "kind": "json", "path": rel,
                        "sha256": digest, "strings": len(out)})
    for dirpath, label in JSON_GLOBS:
        files = sorted((MAIN / dirpath).glob("*.json"))
        if not files:
            manifest.append(f"MISSING {label}: {MAIN / dirpath}/*.json")
            missing += 1
            continue
        files_detail = []
        for p in files:
            data = p.read_bytes()
            out = set()
            try:
                walk_strings(json.loads(data), out)
            except Exception:
                continue
            pool |= out
            files_detail.append({"path": p.name, "sha256": sha_bytes(data),
                                 "strings": len(out)})
        list_sha = sha_bytes("".join(f["sha256"] for f in files_detail).encode("ascii"))
        manifest.append(f"{label}: {dirpath}/*.json files={len(files)} "
                        f"listSha256[:16]={list_sha[:16]}")
        details.append({"label": label, "kind": "json_glob", "base": "MAIN",
                        "dir": dirpath, "listSha256": list_sha,
                        "files": files_detail})
    return pool, manifest, missing, details


def excluded_working_files() -> list:
    """Files on disk under the globbed dirs but absent at the pinned commit.
    They explain why the live diagnostic differs from the frozen pool."""
    out = []
    for dirpath, label in JSON_GLOBS:
        pinned = {pathlib.PurePosixPath(r).name
                  for r in git_json_files(PINNED_MAIN_COMMIT, dirpath)}
        for p in sorted((MAIN / dirpath).glob("*.json")):
            if p.name not in pinned:
                out.append({"dir": dirpath, "path": p.name,
                            "sha256": sha_bytes(p.read_bytes()),
                            "reason": "not tracked at the pinned commit"})
    return out


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


def print_report(tag: str, pool: set, manifest: list, missing: int, hits: dict) -> None:
    print(f"\n[{tag}] exclusion pool: {len(pool)} strings (short strings included)")
    for s, found in hits.items():
        print(f"HIT {s!r} items={found['items']} vs {found['matched']}")
    print(f"[{tag}] sources:")
    for line in manifest:
        print(f"  {line}")
    print(f"[{tag}] verdict: {len(hits)} hit(s), {missing} missing source(s) "
          f"— zero-hit within the listed scope and rules means no verbatim reuse")


def main() -> None:
    archive = "--archive" in sys.argv
    void = selftest()
    if void:
        print("REPORT VOID — isolation self-test failed:")
        for x in void:
            print(" ", x)
        sys.exit(2)
    print("self-test PASS: planted 3-char TS string and 2-char JSON string both caught")

    n2 = n2_strings()
    pool, manifest, missing, details = collect_frozen(PINNED_MAIN_COMMIT)
    hits = match_hits(pool, n2)
    print(f"\nfrozen corpus: B@{PINNED_MAIN_COMMIT[:8]} (tracked files; canonical)")
    print(f"N2 vocabulary: {len(n2)} strings "
          f"({sum(1 for s in n2 if len(s) >= 4)} >=4 chars, "
          f"{sum(1 for s in n2 if len(s) < 4)} short)")
    print_report("frozen", pool, manifest, missing, hits)
    excluded = excluded_working_files()
    if excluded:
        print(f"\non-canonical working files (absent at {PINNED_MAIN_COMMIT[:8]}): "
              + ", ".join(e["path"] for e in excluded))

    live_pool, live_manifest, live_missing, live_details = collect_live()
    live_hits = match_hits(live_pool, n2)
    try:
        main_commit = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                              cwd=MAIN, text=True).strip()
        main_dirty = subprocess.check_output(["git", "status", "--porcelain"],
                                             cwd=MAIN, text=True).strip().splitlines()
    except Exception:
        main_commit, main_dirty = "unknown", []
    print(f"\nlive diagnostic: main worktree @ {main_commit[:8]} (not the canonical number)")
    print_report("live", live_pool, live_manifest, live_missing, live_hits)

    print("\nknown limits: substring only; renaming/derivation not provable; "
          "B's runtime TS code is not scanned")

    if archive:
        try:
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                             cwd=REPO, text=True).strip()
        except Exception:
            commit = "unknown"
        out = {
            "purpose": ("N2 dev-set isolation check v3: canonical pool from B's tracked "
                        "corpus at a pinned commit, plus a live working-tree diagnostic"),
            "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "generatedFromCommit": commit,
            "pinnedMainCommit": PINNED_MAIN_COMMIT,
            "pinPolicy": ("bump only when B commits new calibration corpus; the pin keeps "
                          "the cited pool reproducible instead of following B's live writes"),
            "hashBasis": ("git blob bytes at the pinned commit (LF); a working-tree "
                          "checkout may hash differently under core.autocrlf"),
            "selftest": "PASS: planted 3-char TS string and 2-char JSON string both caught",
            "poolStrings": len(pool),
            "poolDigest": pool_digest(pool),
            "sourceDigest": source_digest(details),
            "sourceGroups": len(manifest),
            "n2VocabularyStrings": len(n2),
            "n2VocabularyShortStrings": sum(1 for s in n2 if len(s) < 4),
            "sources": manifest,
            "sourceFiles": details,
            "missingSources": missing,
            "hits": hits,
            "verdict": ("pass" if not hits and not missing else "fail"),
            "excludedWorkingFiles": excluded,
            "liveDiagnostic": {
                "note": ("working tree snapshot; moves whenever B writes a run archive. "
                         "Not the canonical number; compare with poolDigest, not with "
                         "poolStrings alone. Working-tree hashes here may also differ "
                         "from the frozen blob hashes by CRLF conversion."),
                "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "mainWorktree": {"path": str(MAIN), "commit": main_commit,
                                 "dirty": main_dirty},
                "poolStrings": len(live_pool),
                "poolDigest": pool_digest(live_pool),
                "sourceDigest": source_digest(live_details),
                "sources": live_manifest,
                "sourceFiles": live_details,
                "missingSources": live_missing,
                "hits": live_hits,
                "verdict": ("pass" if not live_hits and not live_missing else "fail"),
            },
            "knownLimits": ["substring only", "renaming/derivation not provable",
                            "B's runtime TS code is not scanned",
                            "untracked working files are excluded from the canonical "
                            "pool and listed in excludedWorkingFiles; the live "
                            "diagnostic includes them",
                            "frozen file hashes are git blob bytes; working-tree "
                            "hashes may differ by CRLF without changing strings"],
        }
        path = REPO / "artifacts" / "world-components" / "n2-isolation-r2.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\narchive -> {path}")

    failed = bool(hits or missing or live_hits or live_missing)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

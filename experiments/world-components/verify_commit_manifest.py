# Commit-manifest verifier (commit 1). The fix-round manifest carried ONE
# sha256 per file — the working-tree byte hash — and hashed ITSELF, which
# cannot stay true: `git add` of the manifest changes its own bytes (the
# self-hash goes stale by construction), and under core.autocrlf=true a
# clean checkout materialises CRLF bytes whose hashes can never match the
# LF-normalised blob content. The corrected discipline, implemented here:
#
#   - the manifest records, per file, BOTH hashes:
#       sha256Bytes  sha256 of the exact working-tree bytes at manifest
#                    time (environment-bound: CRLF on an autocrlf=true
#                    checkout);
#       blobSha256   the git blob hash `git hash-object --path` produces —
#                    newline-conversion independent, what ANY autocrlf
#                    setting commits, and what a clean checkout must
#                    reproduce;
#   - the manifest carries NO self-hash: its identity is the committed
#     blob of its own path (`git ls-files -s` recites it);
#   - verification modes:
#       --mode bytes : compare working-tree byte hashes (only meaningful
#                      in the same checkout state as manifest time);
#       --mode blob  : compare the STAGED/committed blob hashes via
#                      `git ls-files -s` — the check to run right before
#                      committing AND inside a clean checkout;
#     --eol-normalised additionally accepts a byte-hash match after
#     newline normalisation (a checkout under a different autocrlf setting
#     changes bytes, not content).
#
# Usage:
#   python verify_commit_manifest.py --manifest <path> --mode blob
#   python verify_commit_manifest.py --manifest <path> --mode bytes
#   python verify_commit_manifest.py --scan <file> [<file> ...]   # entries

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path) -> str:
    return sha_bytes(pathlib.Path(path).read_bytes())


def git(args: list, cwd) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True)


def blob_sha(path: pathlib.Path, cwd) -> str:
    """The blob hash git would store for this path under the active
    filters (autocrlf clean conversion included) — newline-independent.
    The path is passed POSIX-style: a backslash form would make git miss
    the attribute/autocrlf lookup and hash unconverted bytes."""
    posix = path.as_posix()
    out = git(["hash-object", "--path", posix, "--", posix], cwd)
    return out.strip()


def staged_blob_sha(path: pathlib.Path, cwd) -> str | None:
    """The blob hash actually staged/committed for this path, or None when
    the path is not in the index."""
    out = git(["ls-files", "-s", "--", str(path)], cwd)
    line = out.strip()
    if not line:
        return None
    return line.split()[1]


def normalised_sha(path: pathlib.Path) -> str:
    data = pathlib.Path(path).read_bytes()
    return sha_bytes(data.replace(b"\r\n", b"\n"))


def load_manifest(path) -> dict:
    manifest = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    entries = []
    for section in ("modifiedTracked", "untrackedNormalAdd",
                    "untrackedForceAdd"):
        entries.extend(manifest.get(section) or [])
    if not entries:
        raise SystemExit("manifest carries no entries")
    return manifest, entries


def check(manifest_path, mode, eol_normalised: bool) -> int:
    manifest_path = pathlib.Path(manifest_path)
    cwd = manifest_path.resolve().parent.parent.parent.parent
    manifest, entries = load_manifest(manifest_path)
    self_named = [e for e in entries
                  if pathlib.Path(e["file"]).name
                  == pathlib.Path(manifest_path).name]
    if self_named:
        print(f"FAIL: manifest hashes itself ({self_named[0]['file']}) — "
              "the self-hash must be removed; the manifest's identity is "
              "its committed blob")
        return 1
    failures = []
    for entry in entries:
        rel = entry["file"]
        path = cwd / rel
        if not path.exists():
            failures.append(f"{rel}: missing from the working tree")
            continue
        if mode == "bytes":
            got = sha_file(path)
            want = entry.get("sha256Bytes")
            if got != want:
                if eol_normalised and want and \
                        normalised_sha(path) == want:
                    failures.append(
                        f"{rel}: byte hash differs but matches after "
                        "newline normalisation (EOL conversion)")
                else:
                    failures.append(f"{rel}: bytes {got} != manifest {want}")
        else:
            staged = staged_blob_sha(path, cwd)
            want = entry.get("blobSha256")
            if staged is None:
                failures.append(f"{rel}: NOT in the git index — the commit "
                                "would silently drop it (force-add?)")
            elif staged != want:
                failures.append(f"{rel}: staged blob {staged} != manifest "
                                f"{want} (restage after the last edit)")
    for f in failures:
        print("FAIL:", f)
    print(f"manifest {manifest_path.name}: mode={mode} "
          f"entries={len(entries)} failures={len(failures)}")
    return 1 if failures else 0


def scan(paths) -> int:
    cwd = pathlib.Path.cwd()
    out = []
    for p in paths:
        path = pathlib.Path(p)
        out.append({"file": path.as_posix(),
                    "sha256Bytes": sha_file(path),
                    "blobSha256": blob_sha(path, cwd)})
    print(json.dumps(out, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--mode", choices=["bytes", "blob"], default="blob")
    parser.add_argument("--eol-normalised", action="store_true")
    parser.add_argument("--scan", nargs="+", metavar="FILE")
    args = parser.parse_args()
    if args.scan:
        return scan(args.scan)
    if not args.manifest:
        parser.error("--manifest is required without --scan")
    return check(args.manifest, args.mode, args.eol_normalised)


if __name__ == "__main__":
    sys.exit(main())

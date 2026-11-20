"""Copy the four cf24 scripts read-only into this task's directory and record provenance.

Original files stay untouched. Any later local modification must be a new file with
its own hash, never an overwrite of the copies recorded here.
"""

import hashlib
import json
import os
import pathlib
import shutil
import subprocess

SRC = pathlib.Path(os.environ.get("JITY_REPO", "<repo>") + "/.local/world-components-next-worktree/experiments/world-components")
DST = pathlib.Path(__file__).resolve().parent / "upstream"
NAMES = ["run_cf24_baseline.py", "score_cf24_baseline.py",
         "review_cf24_baseline.py", "check_cf24_overlap.py"]


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in NAMES:
        source = SRC / name
        if not source.exists():
            rows.append(dict(name=name, exists=False))
            continue
        target = DST / name
        shutil.copy2(source, target)
        rows.append(dict(
            name=name, exists=True,
            source=str(source).replace(chr(92), "/"),
            sourceSha256=sha256(source),
            copySha256=sha256(target),
            byteIdentical=sha256(source) == sha256(target),
            sourceBytes=source.stat().st_size,
        ))

    try:
        commit = subprocess.run(
            ["git", "-c", "safe.directory=*", "-C", str(SRC.parents[1]), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        commit = None

    try:
        status = subprocess.run(
            ["git", "-c", "safe.directory=*", "-C", str(SRC.parents[1]), "status", "--porcelain",
             "--", *[f"experiments/world-components/{n}" for n in NAMES]],
            capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        status = None

    manifest = dict(
        protocol="c4-upstream-scripts-v1",
        copiedFilesDirtyVsHead=bool(status),
        gitStatusForCopiedFiles=status,
        note="read-only copy; originals untouched. Any local change must be a new file with its own hash.",
        upstreamTree=os.environ.get("JITY_REPO", "<repo>") + "/.local/world-components-next-worktree",
        upstreamCommit=commit,
        scripts=rows,
    )
    (DST / "provenance.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

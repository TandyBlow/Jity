# Privacy scan (repo hygiene, batch 1): tracked files must not embed local
# environment information — absolute local disk paths are the pattern this
# project has repeatedly had to repair after the fact (local paths were
# committed inside archived JSON artifacts by earlier rounds). This scanner
# finds ABSOLUTE PATH-LOOKING strings in the working tree of C-owned
# directories so they can be rewritten to repo-relative references before
# commit; it records only the PATTERN, never any concrete value.
#
# Scope: experiments/world-components + design/world-engine-reports/
# components + artifacts/world-components (C's paths per README 文件职责).
# Hits are printed with file:line:column so each one can be judged by hand
# (some may be false positives, e.g. a documentation example).

import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent

# Windows drive paths and rooted unix paths inside string fields. Drive
# letter is the load-bearing part: repo-relative text never matches. The
# lookbehind keeps "https://" and friends (letter before the colon) out;
# an http(s) URL is NOT a local path. A `.local/` reference is ALSO
# environment structure (worktree layout) and is flagged even when not
# drive-rooted.
PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[/\\][^\s\"'<>|\*?]{2,}")
LOCAL_DIR = re.compile(r"(?<![A-Za-z0-9])\.local[/\\]")


def tracked_files() -> list:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files",
         "experiments/world-components", "design/world-engine-reports/components",
         "artifacts/world-components"],
        capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line.strip()]


def main() -> int:
    hits = []
    for rel in tracked_files():
        path = REPO / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for m in PATTERN.finditer(line):
                # redacted context: only the matched shape, not neighbors
                hits.append(f"{rel}:{i}:{m.group(0)[:60]}")
            if LOCAL_DIR.search(line):
                hits.append(f"{rel}:{i}:<.local reference>")
    for h in hits:
        print("PATH-LEAK:", h)
    print(f"scan: {len(hits)} hit(s) in tracked C paths")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())

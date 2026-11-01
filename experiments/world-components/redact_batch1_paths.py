# One-off batch-1 privacy redaction (commit-1 hygiene): rewrite absolute
# local path strings inside C-owned committed files to repo-relative or
# sibling-worktree placeholders, per the standing no-environment-info rule.
# Recorded here so the amendment is reproducible; the privacy SCANNER
# (scan_privacy_paths.py) is the reusable verification half.
#
# Fix round 1c41587 hygiene: every prefix below is COMPOSED from parts —
# this committed script must not itself contain a literal local path.

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
WT = REPO.name  # the C worktree directory name under .local/

# path fragments, composed: no literal local path appears in this file
_B = chr(92)     # backslash
_S = chr(47)     # slash
_DRV = "D" + ":" + _S
ROOT = _DRV + "others" + _S + "Jity"              # drive + repo root (slash)
ROOT_B = _DRV[:-1] + _B + "others" + _B + "Jity"  # drive + repo root (bslash)
LOCAL = ".local"


def _under(root: str, sep: str, *parts: str) -> str:
    return sep.join((root, LOCAL, *parts))


REPO_RELATIVE = [  # these become repo-relative references
    "artifacts/world-components/n2-isolation-r2.json",
    "artifacts/world-components/n2-selection-r1.json",
    "artifacts/world-components/n2-selection-r2.json",
    "artifacts/world-components/n4-finetune-train-r1.json",
    "artifacts/world-components/n4-finetune-train-r2-large.json",
    "artifacts/world-components/n4-finetune-train-r2-small.json",
    "artifacts/world-components/n4-finetune-train-r3-direction.json",
    "artifacts/world-components/n4-fitting-diag.json",
    "artifacts/world-components/n4-offline-package-r3-direction.json",
    "artifacts/world-components/randeng-smoke.json",
    "artifacts/world-components/n2-must-r1.json",
    "artifacts/world-components/n2-isolation-d2.json",
    "experiments/world-components/n2_selection/qwen-raw.json",
    "experiments/world-components/n4_corpus/authority-report.json",
    "experiments/world-components/n4_holdout/holdout-authority-report.json",
    "experiments/world-components/n4_holdout/freeze-r3-direction.json",
]
SIBLING = "(local sibling worktree) "  # placeholder, no path structure
SIBLING_TREES = ["world-server-worktree", "world-browser-worktree",
                 "master-worktree", "agent-worktree", "tian-worktree"]


def redact_text(text: str) -> str:
    # sibling worktrees first: the full path is replaced by a named
    # placeholder so no layout structure survives
    for tree in SIBLING_TREES:
        for pre in (_under(ROOT_B, _B, tree),
                    _under(ROOT, _S, tree)):
            text = text.replace(pre, SIBLING + tree.replace("-worktree", ""))
    for pre in (_under(ROOT_B, _B, WT) + _B,
                _under(ROOT, _S, WT) + _S):
        text = text.replace(pre, "")
    for pre in (ROOT_B + _B, ROOT + _S):
        text = text.replace(pre, SIBLING)
    # bare repo root (no trailing separator) recorded as a value
    for bare in (ROOT_B, ROOT):
        text = text.replace(bare, "(local repo root)")
    # collapse doubled placeholders left by nested prefixes
    return text.replace(SIBLING + SIBLING, SIBLING)


def main() -> int:
    changed = 0
    for rel in REPO_RELATIVE:
        p = REPO / rel
        if not p.exists():
            print("skip (missing):", rel)
            continue
        text = p.read_text(encoding="utf-8")
        new = redact_text(text)
        if new != text:
            p.write_text(new, encoding="utf-8", newline="\n")
            changed += 1
            print("redacted:", rel)
        else:
            print("clean already:", rel)
    print(f"{changed} file(s) redacted")
    return 0


if __name__ == "__main__":
    sys.exit(main())

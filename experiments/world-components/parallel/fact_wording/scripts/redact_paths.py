"""Redact local absolute paths in the c4 deliverables before publishing.

Replaces the local repository root (absolute Windows/msys forms) with the literal
placeholder `<repo>`. Path constants in three scripts fall back to the JITY_REPO
environment variable so the scripts stay runnable:

    JITY_REPO=/path/to/Jity python -X utf8 scripts/build_acceptance_set.py

Idempotent: running it again changes nothing.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREFIX = re.compile(r"D:[\\/]+others[\\/]+Jity|/d/[a-z]+/Jity", re.IGNORECASE)

TEXT_FILES = [
    "freeze/comparison-inputs-v1.json",
    "freeze/comparison-inputs-v2.json",
    "freeze/comparison-inputs-v3.json",
    "freeze/u240-identity-v1.json",
    "scripts/upstream/provenance.json",
    "scripts/analyze_candidate.py",
    "scripts/build_acceptance_set.py",
    "scripts/build_comparison_manifest.py",
    "scripts/copy_upstream.py",
    "scripts/inventory_u240.py",
    "artifacts/fact-wording/preflight/env.json",
    "artifacts/fact-wording/preflight/preflight.json",
]

# after prefix replacement these constants still hold "<repo>/..."; make them env-overridable
CONSTANT_EDITS = [
    ("scripts/analyze_candidate.py",
     'NEXT = Path("<repo>/.local/world-components-next-worktree")',
     'NEXT = Path(os.environ.get("JITY_REPO", "<repo>") + "/.local/world-components-next-worktree")'),
    ("scripts/build_acceptance_set.py",
     'NEXT = Path("<repo>/.local/world-components-next-worktree")',
     'NEXT = Path(os.environ.get("JITY_REPO", "<repo>") + "/.local/world-components-next-worktree")'),
    ("scripts/copy_upstream.py",
     'SRC = pathlib.Path("<repo>/.local/world-components-next-worktree/experiments/world-components")',
     'SRC = pathlib.Path(os.environ.get("JITY_REPO", "<repo>") + "/.local/world-components-next-worktree/experiments/world-components")'),
    ("scripts/copy_upstream.py",
     'upstreamTree="<repo>/.local/world-components-next-worktree",',
     'upstreamTree=os.environ.get("JITY_REPO", "<repo>") + "/.local/world-components-next-worktree",'),
]

NEEDS_OS = [
    "scripts/analyze_candidate.py",
    "scripts/build_acceptance_set.py",
    "scripts/copy_upstream.py",
]


def main() -> int:
    changed = []
    for rel in TEXT_FILES:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        new = PREFIX.sub("<repo>", text)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed.append(rel)

    for rel, old, new in CONSTANT_EDITS:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        if old in text:
            path.write_text(text.replace(old, new), encoding="utf-8")
            if rel not in changed:
                changed.append(rel)

    for rel in NEEDS_OS:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        if "\nimport os\n" not in text and not text.startswith("import os\n"):
            path.write_text(text.replace("import json", "import json\nimport os", 1), encoding="utf-8")
            if rel not in changed:
                changed.append(rel)

    print("changed files:", len(changed))
    for rel in changed:
        print("  ", rel)

    remaining = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or "env" in path.parts:
            continue
        if path.suffix.lower() not in (".json", ".md", ".py", ".txt", ".jsonl"):
            continue
        if PREFIX.search(path.read_text(encoding="utf-8", errors="ignore")):
            remaining.append(str(path.relative_to(ROOT)))
    print("remaining matches:", remaining if remaining else "none")
    return 0 if not remaining else 1


if __name__ == "__main__":
    raise SystemExit(main())

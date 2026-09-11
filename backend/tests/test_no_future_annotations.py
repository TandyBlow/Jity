"""Ensure no code file uses `from __future__ import annotations`.

This import masks forward-reference bugs by deferring annotation evaluation.
The project enforces explicit top-level imports instead.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Jity/
SCAN_DIRS = ["backend", "scripts"]
FORBIDDEN = "from __future__ import annotations"


def _py_files() -> list[Path]:
    """Collect all .py files under the scanned directories."""
    files: list[Path] = []
    for dirname in SCAN_DIRS:
        scan_root = PROJECT_ROOT / dirname
        if not scan_root.exists():
            continue
        for py_file in scan_root.rglob("*.py"):
            # Skip virtual environments and caches
            parts = py_file.parts
            if any(p.startswith(".") or p in ("__pycache__", "venv", ".venv", "node_modules") for p in parts):
                continue
            files.append(py_file)
    return sorted(files)


def test_no_future_annotations_import():
    """Every .py file under backend/ and scripts/ must NOT contain the forbidden import.

    Violating files are listed in the assertion message.
    """
    violators: list[tuple[Path, int]] = []

    for path in _py_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            if line.strip() == FORBIDDEN:
                violators.append((path, lineno))

    assert not violators, (
        f"Found {FORBIDDEN!r} in {len(violators)} file(s) — "
        f"remove it and fix any forward-reference errors by moving imports to the top:\n"
        + "\n".join(f"  {p.relative_to(PROJECT_ROOT)}:{lineno}" for p, lineno in violators)
    )

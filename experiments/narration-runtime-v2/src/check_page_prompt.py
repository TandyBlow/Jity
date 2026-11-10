# -*- coding: utf-8 -*-
"""Check that the Python page-prompt port still equals the page's own output.

`golden/page-prompt/ts-scene.txt` and `ts-repair.txt` were produced by calling
the real `instructNarrationInput` from worktrees/06-recovery with vitest on
2026-11-10 (draft in `draft.txt`, viewpoint 周叙白). If 06 changes prompt.ts,
this check fails and the training data must be regenerated — the model is only
valid for the prompt it was trained on.

    python src/check_page_prompt.py
"""

from __future__ import annotations

import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
GOLD = os.path.join(V2, "golden", "page-prompt")

sys.path.insert(0, HERE)
import build_page_pairs as B  # noqa: E402


def read(name: str) -> str:
    with io.open(os.path.join(GOLD, name), encoding="utf-8", newline="") as handle:
        return handle.read().replace("\r\n", "\n")


def main() -> int:
    draft = read("draft.txt").strip("\n")
    failures = []
    for mode, name in (("scene", "ts-scene.txt"), ("repair", "ts-repair.txt")):
        expected = read(name)
        got = B.page_prompt("周叙白", draft, mode)
        if expected.rstrip("\n") != got.rstrip("\n"):
            failures.append(mode)
            print(f"{mode}: MISMATCH")
            print("expected first line:", expected.splitlines()[0][:80])
            print("got     first line:", got.splitlines()[0][:80])
        else:
            print(f"{mode}: identical ({len(got)} chars)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

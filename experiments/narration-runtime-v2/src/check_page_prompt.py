# -*- coding: utf-8 -*-
"""Check that the Python page-prompt port still equals the page's own output.

`golden/page-prompt/ts-scene.txt` and `ts-repair.txt` are captured from the real
`instructNarrationInput` in worktrees/06-recovery by harness/page-prompts.mjs
(capture.json records the source path, world and viewpoint). The viewpoint name
only appears in the prompt head, so the capture uses the world's own protagonist.
If 06 changes prompt.ts, re-capture and this check tells you whether the Python
port still matches; the model is only valid for the prompt it was trained on.

    python src/check_page_prompt.py
"""

from __future__ import annotations

import io
import json
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
    with io.open(os.path.join(GOLD, "capture.json"), encoding="utf-8") as handle:
        capture = json.load(handle)
    viewpoint = capture.get("viewpointName") or "周叙白"
    failures = []
    for mode, name in (("scene", "ts-scene.txt"), ("repair", "ts-repair.txt")):
        expected = read(name)
        got = B.page_prompt(viewpoint, draft, mode)
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

"""Remove dice-demo CSS rules whose selectors no longer appear in any TSX file.

Conservative by design: a rule is only removed when every class token in every
one of its selectors is an unused dice class, so grouped rules that share a live
selector are always kept. Media queries are dropped only once every rule inside
them is removed.

Usage:
    python scripts/find-dead-dice-css.py           # report
    python scripts/find-dead-dice-css.py --list    # report + class names
    python scripts/find-dead-dice-css.py --apply   # rewrite globals.css
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "src" / "app" / "globals.css"

DICE_TOKEN = re.compile(r"(?:dice-demo|real-dice)-[a-z0-9-]+")
DICE_CLASS_IN_CSS = re.compile(r"\.((?:dice-demo|real-dice)-[a-z0-9-]+)")


def used_classes() -> set[str]:
    """Class tokens referenced from TSX/TS; these have no leading dot."""
    used: set[str] = set()
    sources = list((ROOT / "src").rglob("*.tsx")) + list((ROOT / "src").rglob("*.ts"))
    for path in sources:
        used.update(DICE_TOKEN.findall(path.read_text(encoding="utf-8")))
    return used


def scan(text: str) -> list[dict]:
    """Return every brace block with its selector text, offsets and nesting depth."""
    blocks: list[dict] = []
    stack: list[tuple[int, int, str]] = []
    cursor = 0
    selector_start = 0
    length = len(text)

    while cursor < length:
        char = text[cursor]
        if char == "{":
            stack.append((selector_start, cursor, text[selector_start:cursor]))
            selector_start = cursor + 1
        elif char == "}":
            if stack:
                start, brace, selector = stack.pop()
                blocks.append({
                    "start": start,
                    "brace": brace,
                    "end": cursor + 1,
                    "selector": selector,
                    "depth": len(stack),
                })
            selector_start = cursor + 1
        elif char == ";":
            selector_start = cursor + 1
        cursor += 1
    return blocks


def selector_is_dead(selector: str, dead: set[str]) -> bool:
    parts = [part.strip() for part in selector.split(",") if part.strip()]
    if not parts:
        return False
    for part in parts:
        tokens = DICE_CLASS_IN_CSS.findall(part)
        if not tokens:
            return False
        if any(token not in dead for token in tokens):
            return False
    return True


def main() -> int:
    text = CSS.read_text(encoding="utf-8")
    used = used_classes()
    defined = set(DICE_CLASS_IN_CSS.findall(text))
    dead = defined - used

    blocks = scan(text)
    removals: list[dict] = []
    media_blocks: dict[int, list[dict]] = {}

    for block in blocks:
        selector = block["selector"]
        if block["depth"] == 0 and "@media" in selector:
            media_blocks[block["start"]] = []
            continue
        if selector_is_dead(selector, dead):
            removals.append(block)

    # Associate inner rules with their enclosing media query by offset range.
    for media in [b for b in blocks if b["depth"] == 0 and "@media" in b["selector"]]:
        children = [
            b for b in blocks
            if b["depth"] == 1 and media["brace"] < b["start"] < media["end"]
        ]
        if children and all(any(b is r for r in removals) for b in children):
            removals = [r for r in removals if r not in children]
            removals.append(media)

    removed_lines = 0
    for block in removals:
        removed_lines += text[block["start"]:block["end"]].count("\n") + 1

    print(f"defined dice classes: {len(defined)}")
    print(f"used dice classes:    {len(used & defined)}")
    print(f"unused dice classes:  {len(dead)}")
    print(f"removable rules:      {len(removals)}")
    print(f"removable lines:      {removed_lines}")

    if "--list" in sys.argv:
        for name in sorted(dead):
            print(f"  {name}")

    if "--apply" not in sys.argv:
        return 0

    out = text
    for block in sorted(removals, key=lambda b: b["start"], reverse=True):
        out = out[:block["start"]] + out[block["end"]:]
    # Collapse the blank-line runs the deletions leave behind.
    out = re.sub(r"\n{3,}", "\n\n", out)
    CSS.write_text(out, encoding="utf-8")
    print(f"rewrote {CSS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

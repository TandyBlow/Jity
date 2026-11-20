"""Extract part-anchor texts from the committed fixtures.

An anchor is a piece of committed text that can prove a "part" word belongs to
an entity: an initial appearance clause, an appearance change, or a personality
change. Every anchor records file, 1-based line, change id, sourcePointId and
entity id, so a later resolver can verify "袖口 belongs to 林川" instead of
guessing.

Output: freeze/anchors-v1.json
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
HERE = pathlib.Path(__file__).resolve().parent
FREEZE = HERE / "freeze"

SOURCES = {
    "W1": "frontend/src/lib/world-engine/runtime/narration-split-samples.ts",
    "W2": "frontend/src/lib/world-engine/runtime/b3-short-samples.ts",
}

CONST_RE = re.compile(r"const ([A-Z][A-Z0-9_]*) = '([^']*)'")
CHANGE_RE = re.compile(
    r"(appearanceChanges|personalityChanges): \[\{ id: '([^']+)', text: ([A-Z][A-Z0-9_]*|'[^']*')"
    r"[^\n]*?sourcePointId: '([^']+)'"
)
ENTITY_BEFORE_RE = re.compile(r"'(?:[a-z][a-z0-9_]*)'")
INITIAL_RE = re.compile(r"id: '([^']+)', name: '([^']+)'")
APPEARANCE_RE = re.compile(r"initialAppearance: '([^']*)'")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unquote(token: str, constants: dict[str, str]) -> str:
    if token.startswith("'"):
        return token.strip("'")
    if token in constants:
        return constants[token]
    raise SystemExit(f"unknown text constant {token}")


def build(ref: str, rel: str) -> dict:
    path = ROOT / rel
    lines = path.read_text(encoding="utf-8").splitlines()
    constants: dict[str, str] = {}
    for line in lines:
        hit = CONST_RE.search(line)
        if hit:
            constants[hit.group(1)] = hit.group(2)

    anchors: list[dict] = []
    for number, line in enumerate(lines, start=1):
        initial = INITIAL_RE.search(line)
        appearance = APPEARANCE_RE.search(line)
        if initial and appearance:
            anchors.append(
                {
                    "entityId": initial.group(1),
                    "kind": "initial_appearance",
                    "text": appearance.group(1),
                    "changeId": None,
                    "sourcePointId": None,
                    "line": number,
                }
            )
        for match in CHANGE_RE.finditer(line):
            field, change_id, text_token, point = match.groups()
            head = line[: match.start()]
            entity_ids = ENTITY_BEFORE_RE.findall(head)
            entity_id = entity_ids[-1].strip("'") if entity_ids else None
            if not entity_id:
                raise SystemExit(f"{rel}:{number}: change without entity")
            anchors.append(
                {
                    "entityId": entity_id,
                    "kind": "appearance_change" if field == "appearanceChanges" else "personality_change",
                    "text": unquote(text_token, constants),
                    "changeId": change_id,
                    "sourcePointId": point,
                    "line": number,
                }
            )

    for anchor in anchors:
        if anchor["text"] not in path.read_text(encoding="utf-8"):
            raise SystemExit(f"{rel}:{anchor['line']}: text literal missing")
    return {
        "rosterRef": ref,
        "sourceFile": rel,
        "sourceSha256": sha256(path),
        "anchors": anchors,
    }


def main() -> int:
    FREEZE.mkdir(parents=True, exist_ok=True)
    doc = {
        "protocol": "c1-attention-anchors-v1",
        "note": "锚点文本逐字来自已登记夹具；行号为该夹具当前版本的 1 基行号。用于验证 part 词是否属于该实体，不用于生成叙事。",
        "sources": {ref: build(ref, rel) for ref, rel in SOURCES.items()},
    }
    target = FREEZE / "anchors-v1.json"
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for ref, source in doc["sources"].items():
        counts: dict[str, int] = {}
        for anchor in source["anchors"]:
            counts[anchor["kind"]] = counts.get(anchor["kind"], 0) + 1
        print(f"{ref} {source['sourceFile']} sha={source['sourceSha256'][:12]} {counts}")
    print(f"wrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

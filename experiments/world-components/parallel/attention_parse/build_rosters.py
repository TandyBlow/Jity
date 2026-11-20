"""Build the two rosters used by the c1 attention-parse experiment.

Every object, name, descriptor and task goal is copied VERBATIM out of a
committed fixture file; the builder records the file sha256, the 1-based line
number and the field path. It fails if a literal cannot be located, so a
roster can never drift silently from the fixture.

Output: freeze/rosters.json (also prints per-roster entity counts).
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

SECTION_RE = re.compile(r"^\s*(locations|items|characters): \{")
ENTITY_RE = re.compile(r"id: '([^']+)', name: '([^']+)'")
APPEARANCE_RE = re.compile(r"initialAppearance: '([^']*)'")
TASK_RE = re.compile(
    r"id: '([^']+)', ownerId: '([^']+)', parentTaskId: [^,]+, goal: '([^']+)'"
)
WORLD_RE = re.compile(r"worldId: '([^']+)'")
PROTAG_RE = re.compile(r"protagonistId: '([^']+)'")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse(path: pathlib.Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    section = None
    out: list[dict] = []
    for number, line in enumerate(lines, start=1):
        m = SECTION_RE.match(line)
        if m:
            section = m.group(1)
        if "initialAppearance:" not in line:
            continue
        entity = ENTITY_RE.search(line)
        if not entity:
            raise SystemExit(f"{path}:{number}: entity line without id/name")
        appearance = APPEARANCE_RE.search(line)
        record = {
            "entityId": entity.group(1),
            "kind": {"locations": "location", "items": "item", "characters": "character"}[section],
            "name": entity.group(2),
            "descriptor": appearance.group(1) if appearance else "",
            "nameLine": number,
            "descriptorLine": number if appearance else None,
        }
        out.append(record)
        for task in TASK_RE.finditer(line):
            out.append(
                {
                    "entityId": task.group(1),
                    "kind": "task",
                    "name": task.group(3),
                    "ownerId": task.group(2),
                    "goal": task.group(3),
                    "nameLine": number,
                    "descriptorLine": None,
                }
            )
    return out


def field_path(kind: str, entity_id: str, field: str) -> str:
    bucket = {"location": "locations", "item": "items", "character": "characters"}.get(kind)
    if bucket:
        return f"initial.{bucket}.{entity_id}.{field}"
    return f"initial.characters.{entity_id}.tasks.{entity_id}.{field}"


def build(ref: str, rel: str) -> dict:
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    entities = parse(path)
    if not entities:
        raise SystemExit(f"{rel}: no entities parsed")
    for item in entities:
        if item["name"] not in text or item["entityId"] not in text:
            raise SystemExit(f"{rel}: literal missing for {item['entityId']}")
        if item.get("descriptor") and item["descriptor"] not in text:
            raise SystemExit(f"{rel}: descriptor missing for {item['entityId']}")
    for item in entities:
        item["provenance"] = {
            "file": rel,
            "line": item["nameLine"],
            "nameFieldPath": field_path(item["kind"], item["entityId"], "name" if item["kind"] != "task" else "goal"),
        }
        if item.get("descriptor"):
            item["provenance"]["descriptorFieldPath"] = field_path(
                item["kind"], item["entityId"], "initialAppearance"
            )
            item["provenance"]["descriptorLine"] = item["descriptorLine"]
    world = WORLD_RE.search(text)
    protagonist = PROTAG_RE.search(text)
    return {
        "rosterRef": ref,
        "sourceFile": rel,
        "sourceSha256": sha256(path),
        "worldId": world.group(1) if world else None,
        "protagonistId": protagonist.group(1) if protagonist else None,
        "entities": entities,
    }


def main() -> int:
    FREEZE.mkdir(parents=True, exist_ok=True)
    doc = {
        "protocol": "c1-attention-parse-roster-v1",
        "note": "对象/字段逐字来自已登记夹具；行号为该夹具当前版本中的 1 基行号。",
        "rosters": {ref: build(ref, rel) for ref, rel in SOURCES.items()},
    }
    target = FREEZE / "rosters.json"
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for ref, roster in doc["rosters"].items():
        kinds: dict[str, int] = {}
        for item in roster["entities"]:
            kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
        print(f"{ref} {roster['worldId']} {roster['sourceFile']} sha={roster['sourceSha256'][:12]} {kinds}")
    print(f"wrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

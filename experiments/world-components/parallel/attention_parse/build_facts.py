"""Build the wiring fact bundle from committed requiredFacts.

The six facts are the machine-checkable `requiredFacts` entries of committed
narration-split samples. The extractor copies entityId / text / goal / from /
to / amount verbatim, resolves text constants, records the sample id, the
1-based fixture line and the source file sha256.

Authorization (must / optional / forbidden) is NOT taken from the fixture: it
is authored for this experiment and recorded in AUTHORIZATION below. The
provenance of the fact itself stays committed.

Output: freeze/facts-v1.json
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
SOURCE = "frontend/src/lib/world-engine/runtime/narration-split-samples.ts"

SAMPLE_RE = re.compile(r"^    id: '(ns-[a-z0-9-]+)', category:")
POSITION_RE = re.compile(
    r"\{ kind: 'position', entityId: '([^']+)', fromName: '([^']+)', toName: '([^']+)', phrase: '([^']*)' \}"
)
APPEARANCE_RE = re.compile(
    r"\{ kind: 'appearanceText', entityId: '([^']+)', text: ([A-Z][A-Z0-9_]*|'[^']*'), phrase: '([^']*)' \}"
)
TASK_RE = re.compile(r"\{ kind: 'taskGoal', entityId: '([^']+)', goal: '([^']+)', phrase: '([^']*)' \}")
TIME_RE = re.compile(r"\{ kind: 'timePassage', amount: (\d+), unit: '([^']+)', phrase: '([^']*)' \}")
CONST_RE = re.compile(r"const ([A-Z][A-Z0-9_]*) = '([^']*)'")

# Authored for the wiring experiment (not from the fixture): which of the six
# facts a narrator must tell, which are optional, which are forbidden.
AUTHORIZATION = {
    "ns-task-1#taskGoal": "must",
    "ns-task-1#timePassage": "must",
    "ns-pos-1#position": "optional",
    "ns-appear-1#appearanceText": "optional",
    "ns-loc-appear-1#appearanceText": "optional",
    "ns-cont-2#appearanceText": "forbidden",
}

KIND_MAP = {
    "position": "moved",
    "appearanceText": "appearance_changed",
    "taskGoal": "task_achieved",
    "timePassage": "time",
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unquote(token: str, constants: dict[str, str]) -> str:
    if token.startswith("'"):
        return token.strip("'")
    if token in constants:
        return constants[token]
    raise SystemExit(f"unknown text constant {token}")


def main() -> int:
    FREEZE.mkdir(parents=True, exist_ok=True)
    path = ROOT / SOURCE
    lines = path.read_text(encoding="utf-8").splitlines()
    constants = {hit.group(1): hit.group(2) for line in lines if (hit := CONST_RE.search(line))}

    sample = None
    facts: list[dict] = []
    for number, line in enumerate(lines, start=1):
        hit = SAMPLE_RE.match(line)
        if hit:
            sample = hit.group(1)
            continue
        if sample is None:
            continue
        for regex, kind in (
            (POSITION_RE, "position"),
            (APPEARANCE_RE, "appearanceText"),
            (TASK_RE, "taskGoal"),
            (TIME_RE, "timePassage"),
        ):
            match = regex.search(line)
            if not match:
                continue
            fact_id = f"{sample}#{kind}"
            if fact_id not in AUTHORIZATION:
                break
            if kind == "position":
                fact = {
                    "entityId": match.group(1),
                    "from": match.group(2),
                    "to": match.group(3),
                }
            elif kind == "appearanceText":
                fact = {"entityId": match.group(1), "text": unquote(match.group(2), constants)}
            elif kind == "taskGoal":
                fact = {"entityId": match.group(1), "goal": match.group(2)}
            else:
                fact = {"amount": int(match.group(1)), "unit": match.group(2)}
            facts.append(
                {
                    "factId": fact_id,
                    "sourceSampleId": sample,
                    "sourceKind": kind,
                    "kind": KIND_MAP[kind],
                    "authorization": AUTHORIZATION[fact_id],
                    "sourceFile": SOURCE,
                    "sourceLine": number,
                    **fact,
                }
            )
            break

    missing = set(AUTHORIZATION) - {fact["factId"] for fact in facts}
    if missing:
        raise SystemExit(f"facts not found in fixture: {sorted(missing)}")
    source_text = path.read_text(encoding="utf-8")
    for fact in facts:
        if fact["kind"] != "time" and fact["entityId"] not in source_text:
            raise SystemExit(f"{fact['factId']}: entity literal missing")
        text = fact.get("text") or fact.get("goal") or fact.get("to") or ""
        if text and text not in source_text:
            raise SystemExit(f"{fact['factId']}: text literal missing")

    order = list(AUTHORIZATION)
    facts.sort(key=lambda item: order.index(item["factId"]))
    doc = {
        "protocol": "c1-n2-wiring-facts-v1",
        "note": "事实本身逐字来自提交样本的 requiredFacts；must/optional/forbidden 是本实验作者标注，不是夹具自带，也不是真实 N2 判定。",
        "sourceFile": SOURCE,
        "sourceSha256": sha256(path),
        "facts": facts,
    }
    target = FREEZE / "facts-v1.json"
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for fact in facts:
        print(f"{fact['factId']:<36} {fact['authorization']:<9} {fact['kind']:<18} line {fact['sourceLine']}")
    print(f"wrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

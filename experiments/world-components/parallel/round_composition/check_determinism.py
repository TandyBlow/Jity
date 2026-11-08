# Determinism check for the offline composer(s).
#
# Runs compose.py (v2, frozen gate) and compose_v3.py (adjudicated N5 v3)
# twice each into separate archives, strips ONLY wall-clock fields (runAt,
# per-stage ms, per-attempt ms and the case-level timings block), then
# compares each pair byte-for-byte. Anything else that differs is a
# non-deterministic input, and the check fails loudly.
#
# Both versions are checked because they share the same chain: a change in one
# that silently leaks into the other would show up here.
#
# Usage: python -X utf8 check_determinism.py

import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"
PAIRS = {
    "v2": (HERE / "compose.py",
           OUT / "determinism-a.json", OUT / "determinism-b.json"),
    "v3": (HERE / "compose_v3.py",
           OUT / "determinism-v3-a.json", OUT / "determinism-v3-b.json"),
}
RESULT = OUT / "determinism.json"


def strip(doc: dict) -> dict:
    d = json.loads(json.dumps(doc))
    d.pop("runAt", None)
    for case in d.get("cases") or []:
        case.pop("timings", None)
        for stage in (case.get("stages") or {}).values():
            if not isinstance(stage, dict):
                continue
            stage.pop("ms", None)
            for att in stage.get("attempts") or []:
                att.pop("ms", None)
            for verdict in stage.get("verdicts") or []:
                verdict.pop("ms", None)
    return d


def first_diff(a, b, path="root"):
    if type(a) is not type(b):
        return f"{path}: type {type(a).__name__} vs {type(b).__name__}"
    if isinstance(a, dict):
        ka, kb = sorted(a), sorted(b)
        if ka != kb:
            return f"{path}: keys differ {set(ka) ^ set(kb)}"
        for k in ka:
            d = first_diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} vs {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else f"{path}: {a!r} vs {b!r}"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sections = {}
    for name, (script, a_path, b_path) in PAIRS.items():
        for target in (a_path, b_path):
            subprocess.run([sys.executable, "-X", "utf8", str(script),
                            "--out", str(target)], check=True,
                           capture_output=True)
        a = strip(json.loads(a_path.read_text(encoding="utf-8")))
        b = strip(json.loads(b_path.read_text(encoding="utf-8")))
        diff = first_diff(a, b, "archive")
        sections[name] = {
            "script": script.name,
            "compared": [str(a_path.relative_to(HERE)),
                         str(b_path.relative_to(HERE))],
            "identicalAfterStrip": diff is None,
            "firstDifference": diff,
        }
    result = {
        "version": "round-composition-determinism-v0.2",
        "strippedFields": ["runAt", "timings", "*.stages.*.ms",
                           "*.stages.*.attempts[].ms"],
        "versions": sections,
        "identicalAfterStrip": all(s["identicalAfterStrip"]
                                   for s in sections.values()),
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["identicalAfterStrip"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

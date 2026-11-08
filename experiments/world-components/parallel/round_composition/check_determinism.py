# Determinism check for the offline composer.
#
# Runs compose.py twice into separate archives, strips ONLY wall-clock
# fields (runAt, per-stage ms, per-attempt ms, totalMs, and the retry
# feedback strings that are derived from a previous attempt's wall clock —
# there are none), then compares the rest byte-for-byte. Anything that
# differs is a non-deterministic input, and the check fails loudly.
#
# Usage: python -X utf8 check_determinism.py

import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"
A = OUT / "determinism-a.json"
B = OUT / "determinism-b.json"
RESULT = OUT / "determinism.json"


def strip(doc: dict) -> dict:
    d = json.loads(json.dumps(doc))
    d.pop("runAt", None)
    for case in d["cases"]:
        case.pop("timings", None)
        for stage in case.get("stages", {}).values():
            if not isinstance(stage, dict):
                continue
            stage.pop("ms", None)
            for att in stage.get("attempts") or []:
                att.pop("ms", None)
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
    for target in (A, B):
        subprocess.run([sys.executable, "-X", "utf8",
                        str(HERE / "compose.py"), "--out", str(target)],
                       check=True, capture_output=True)
    a, b = strip(json.loads(A.read_text(encoding="utf-8"))), strip(
        json.loads(B.read_text(encoding="utf-8")))
    diff = first_diff(a, b, "archive")
    # A second difference class must also be reported: our own output file
    # hashes change every run only through the stripped timing fields.
    res = {"version": "round-composition-determinism-v0.1",
           "compared": [str(A.relative_to(HERE)), str(B.relative_to(HERE))],
           "strippedFields": ["runAt", "timings", "*.stages.*.ms",
                              "*.stages.*.attempts[].ms"],
           "identicalAfterStrip": diff is None,
           "firstDifference": diff}
    RESULT.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8", newline="\n")
    print(json.dumps(res, ensure_ascii=False))
    return 0 if diff is None else 1


if __name__ == "__main__":
    raise SystemExit(main())

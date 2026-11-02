# Validate scene-sentence targets.
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/validate_scene_corpus.py

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from scene_check import check  # noqa: E402


def main():
    bad = 0
    for name in ("scene_pairs.jsonl", "scene_holdout.jsonl"):
        rows = [json.loads(l) for l in
                (HERE / name).read_text(encoding="utf-8").splitlines()
                if l.strip()]
        for r in rows:
            c = check(r, r["target"])
            if not c["ok"]:
                bad += 1
                print(name, r["pairId"], c["reasons"], "|", r["target"])
        print(name, len(rows), "rows")
    print("bad:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

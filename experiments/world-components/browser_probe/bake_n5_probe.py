# Bake the N5 browser probe cases (commit 3) from the EXPORTED ONNX archive
# and the FROZEN eval thresholds. No new labels are invented here:
#   - token ids, HF logits and ORT-python logits come from
#     n5-export-report.json (the export's own parity gate already passed)
#   - t_support / t_contradict come from n5-relation-eval.json, which fixed
#     them on the dev split before touching the test split
# The browser probe compares against these baked references byte-for-byte
# (ids) and numerically (logits), then applies the same threshold rule.

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
EXP = HERE.parent
EXPORT = EXP / "n4_corpus_v2" / "onnx-n5" / "n5-export-report.json"
EVAL = EXP.parents[1] / "artifacts" / "world-components" / "n5-relation-eval.json"
OUT = HERE / "n5_probe_cases.json"


def main() -> int:
    exp = json.loads(EXPORT.read_text(encoding="utf-8"))
    ev = json.loads(EVAL.read_text(encoding="utf-8"))
    cases = []
    for b in exp["baked"]:
        cases.append({
            "factText": b["factText"],
            "sentence": b["sentence"],
            "factKind": b["factKind"],
            "label": b["label"],
            "tokenIds": b["tokenIds"],
            "hfLogits": b["hfLogits"],
            "ortLogits": b["ortLogits"],
        })
    out = {
        "purpose": "N5 browser probe inputs (commit 3) - baked from the "
                   "exported ONNX parity archive and the frozen eval "
                   "thresholds; thresholds never fitted in the browser",
        "onnxSha256": exp["onnx"]["sha256"],
        "modelSha256": exp["encoder"]["sha256"],
        "thresholds": {
            "t_support": ev["thresholds"]["t_support"],
            "t_contradict": ev["thresholds"]["t_contradict"],
            "rule": ev["thresholds"]["rule"],
        },
        "cases": cases,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"baked {len(cases)} cases -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Judge the N4 v2 BROWSER texts with the same frozen v2 gates the offline
# holdout eval uses (G1 alignment, G2 fabrication, G3 time, G4/G5 discipline
# rows, G6 truncation). This is the browser-side quality check: token parity
# with ORT-python is necessary, but the text must still pass the gates.
#
# Usage: python judge_v2_browser_texts.py <texts.json>
#   texts.json: {rowId: {text, finishReason}}

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
sys.path.insert(0, str(WC / "n4_corpus_v2"))

from eval_n4_v2 import judge_row  # noqa: E402


def main() -> int:
    texts = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    rows = {json.loads(l)["rowId"]: json.loads(l) for l in
            (WC / "n4_corpus_v2" / "corpus_v2" / "holdout-v2.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()}
    out = {}
    for row_id, rec in texts.items():
        row = rows[row_id]
        verdict = judge_row(row, rec["text"], rec.get("finishReason"))
        out[row_id] = {"verdict": verdict,
                       "text": rec["text"]}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

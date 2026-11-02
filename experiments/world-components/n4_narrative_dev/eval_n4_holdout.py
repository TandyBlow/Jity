# Zero-shot evaluation of the N4 formal checkpoint on the new-world holdout.
# No training. The model was trained on n4n-fog-harbor; this world has
# different names/places/items.
#
# Usage (HPC): python eval_n4_holdout.py --ckpt ~/n4formal_run/ckpt-formal
# Output: holdout-report.json

import argparse
import difflib
import hashlib
import json
import pathlib
import sys

import torch
from transformers.generation.logits_process import LogitsProcessor, LogitsProcessorList
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
PAIRS = HERE / "holdout_pairs.jsonl"
FREEZE = HERE / "holdout-freeze.json"
MAX_INPUT = 512
MAX_OUTPUT = 128

OLD_NAMES = ["沈砚", "顾行舟", "叶知微", "阿棠", "韩渡",
             "潮生巷", "旧灯塔", "潮渡", "潮汐档案馆", "雾堤", "早市"]
NEW_NAMES = ["陆行", "阿洛", "祁婶", "石青",
             "云关驿", "风口岭", "雪溪", "望雪台"]
# Copy constraint: input tokens + punctuation + common function words.
# No general nouns are added, so "冰箱"/"铁盆" cannot be formed unless both
# characters already appear in the input.
ALLOWED_EXTRA = ("，。；：？！、,.!?;: "
                 "“”‘’（）()《》—…"
                 "的了着在把被从到向又也还只就才和与而但是有没一个这那"
                 "他她它们上下里外前后中间时候过来去走站看听说问答声")


class CopyConstraint(LogitsProcessor):
    def __init__(self, allowed_ids):
        self.allowed = sorted(allowed_ids)

    def __call__(self, input_ids, scores):
        mask = torch.full_like(scores, float("-inf"))
        mask[:, self.allowed] = 0.0
        return scores + mask


def norm_punct(text):
    return (text.replace("，", ",").replace("；", ";")
                .replace("：", ":").replace("？", "?").replace("！", "!"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ckpt", default=str(pathlib.Path("ckpt-formal")))
    parser.add_argument("--copy-constraint", action="store_true",
                        help="restrict output tokens to input + punctuation/"
                             "function words")
    args = parser.parse_args()

    rows = [json.loads(line) for line in
            PAIRS.read_text(encoding="utf-8").splitlines() if line.strip()]
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    got = hashlib.sha256(
        "".join(r["input"] for r in rows).encode("utf-8")).hexdigest()
    if got != freeze["inputSha256"]:
        print("REFUSED: holdout input hash differs from the freeze")
        return 2
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = T5Tokenizer.from_pretrained(args.ckpt, legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(
        args.ckpt, torch_dtype=torch.float32).to(device)
    model.eval()

    samples = []
    for r in rows:
        enc = tok(r["input"], return_tensors="pt", truncation=True,
                  max_length=MAX_INPUT).to(device)
        processors = None
        allowed = None
        if args.copy_constraint:
            allowed = set(tok(r["input"], add_special_tokens=False).input_ids)
            allowed |= set(tok(ALLOWED_EXTRA,
                               add_special_tokens=False).input_ids)
            allowed.add(tok.eos_token_id)
            allowed.add(tok.pad_token_id)
            processors = LogitsProcessorList([CopyConstraint(allowed)])
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=MAX_OUTPUT,
                                 num_beams=1, do_sample=False,
                                 logits_processor=processors)
        text = tok.decode(gen[0], skip_special_tokens=True)
        old_hits = [n for n in OLD_NAMES if n in text]
        new_hits = [n for n in NEW_NAMES if n in text]
        out_ids = tok(text, add_special_tokens=False).input_ids
        oov = [i for i in out_ids if allowed is not None and i not in allowed]
        samples.append({
            "rowId": r["rowId"], "sourceId": r["sourceId"],
            "oovTokens": len(oov),
            "exactNormalized": norm_punct(text) == norm_punct(r["target"]),
            "ratio": round(difflib.SequenceMatcher(
                None, text, r["target"]).ratio(), 3),
            "oldNameHits": old_hits,
            "newNameHits": new_hits,
            "output": text,
            "target": r["target"],
        })

    def mean(key):
        return round(sum(s[key] for s in samples) / len(samples), 3)

    report = {
        "purpose": "N4 new-world zero-shot holdout; no training",
        "mode": "copy-constraint" if args.copy_constraint else "free",
        "ckpt": "ckpt-formal (n4n-fog-harbor, 100 train)",
        "data": {"freeze": freeze, "rows": len(rows)},
        "results": {
            "exactNormalized": sum(1 for s in samples
                                   if s["exactNormalized"]),
            "meanRatio": mean("ratio"),
            "rowsWithOldNames": sum(1 for s in samples
                                    if s["oldNameHits"]),
            "rowsWithNewNames": sum(1 for s in samples
                                    if s["newNameHits"]),
            "oovTokens": sum(s["oovTokens"] for s in samples),
        },
        "samples": samples,
    }
    out_name = ("holdout-report-copy.json" if args.copy_constraint
                else "holdout-report.json")
    pathlib.Path(out_name).write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print("results:", json.dumps(report["results"], ensure_ascii=False))
    for s in samples:
        print(s["sourceId"], "old", s["oldNameHits"],
              "new", s["newNameHits"], s["output"][:80])
    return 0


if __name__ == "__main__":
    sys.exit(main())

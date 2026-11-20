# Zero-shot new-world holdout with fact-coverage reranking.
# Generates 8 candidates per case, scores them with input-only signals
# (fact coverage, OOV tokens, repetition), and selects the best. The target
# is used only for post-hoc reporting, never for selection.
#
# Usage (HPC): python eval_n4_holdout_rerank.py --ckpt ~/n4formal_run/ckpt-formal
# Output: holdout-report-rerank.json

import argparse
import collections
import difflib
import hashlib
import json
import pathlib
import sys

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
PAIRS = HERE / "holdout_pairs.jsonl"
FREEZE = HERE / "holdout-freeze.json"
CORPUS = HERE / "holdout_corpus.jsonl"
MAX_INPUT = 512
MAX_OUTPUT = 128
ALLOWED_EXTRA = ("，。；：？！、,.!?;: "
                 "“”‘’（）()《》—…"
                 "的了着在把被从到向又也还只就才和与而但是有没一个这那"
                 "他她它们上下里外前后中间时候过来去走站看听说问答声")


def norm_punct(text):
    return (text.replace("，", ",").replace("；", ";")
                .replace("：", ":").replace("？", "?").replace("！", "!"))


def char_cov(output, phrase):
    chars = [c for c in phrase if "\u4e00" <= c <= "\u9fff"]
    if not chars:
        return 0.0
    return sum(1 for c in chars if c in output) / len(chars)


def coverage(output, facts):
    total = hits = 0
    for f in facts:
        if f["kind"] == "time":
            continue
        total += 1
        name = f.get("name") or ""
        ok = bool(name) and name in output
        if f["kind"] == "moved":
            ok = ok and str(f["to"]) in output
        elif f["kind"] == "outcome":
            ok = ok and char_cov(output, str(f["resultText"])) >= 0.5
        elif f["kind"] in ("appearance_changed", "personality_changed"):
            ok = ok and char_cov(output, str(f["text"])) >= 0.4
        elif f["kind"] == "sanity_changed":
            ok = ok and any(k in output for k in
                            ["呼吸", "胸口", "气", "手", "肩", "手指"])
        elif f["kind"] == "no_change":
            ok = ok and any(k in output for k in
                            ["没有", "什么", "再发生"])
        hits += 1 if ok else 0
    return (hits / total) if total else 0.0


def rep_score(text):
    grams = [text[i:i + 4] for i in range(max(0, len(text) - 3))]
    if not grams:
        return 0
    return max(collections.Counter(grams).values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ckpt", default=str(pathlib.Path("ckpt-formal")))
    parser.add_argument("--samples", type=int, default=8)
    args = parser.parse_args()

    rows = [json.loads(line) for line in
            PAIRS.read_text(encoding="utf-8").splitlines() if line.strip()]
    facts = {r["id"]: r["facts"] for r in
             (json.loads(line) for line in
              CORPUS.read_text(encoding="utf-8").splitlines() if line.strip())}
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
        allowed = set(tok(r["input"], add_special_tokens=False).input_ids)
        allowed |= set(tok(ALLOWED_EXTRA, add_special_tokens=False).input_ids)
        allowed.add(tok.eos_token_id)
        allowed.add(tok.pad_token_id)
        with torch.no_grad():
            gen = model.generate(
                **enc, max_new_tokens=MAX_OUTPUT, num_beams=1,
                do_sample=True, temperature=0.9, top_p=0.95,
                num_return_sequences=args.samples)
        cands = []
        for ids in gen:
            text = tok.decode(ids, skip_special_tokens=True)
            out_ids = tok(text, add_special_tokens=False).input_ids
            oov = sum(1 for i in out_ids if i not in allowed)
            cov = coverage(text, facts[r["sourceId"]])
            rep = rep_score(text)
            score = cov * 10 - oov * 0.5 - rep * 0.5
            cands.append({
                "output": text, "coverage": round(cov, 3),
                "oov": oov, "rep": rep, "score": round(score, 3),
                "ratio": round(difflib.SequenceMatcher(
                    None, text, r["target"]).ratio(), 3),
            })
        best = max(cands, key=lambda c: c["score"])
        samples.append({
            "sourceId": r["sourceId"],
            "selected": best,
            "candidates": cands,
            "target": r["target"],
        })
        print(r["sourceId"], "cov", best["coverage"], "oov", best["oov"],
              "ratio", best["ratio"], best["output"][:90], flush=True)

    def mean(key):
        return round(sum(s["selected"][key] for s in samples) / len(samples), 3)

    report = {
        "purpose": "N4 new-world holdout; fact-coverage reranking, no training",
        "ckpt": "ckpt-formal (n4n-fog-harbor, 100 train)",
        "mode": "coverage-rerank",
        "freeze": freeze,
        "samplesPerCase": args.samples,
        "results": {
            "meanCoverage": mean("coverage"),
            "meanOov": mean("oov"),
            "meanRatio": mean("ratio"),
        },
        "samples": samples,
    }
    pathlib.Path("holdout-report-rerank.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print("results:", json.dumps(report["results"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

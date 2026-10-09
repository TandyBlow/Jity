# Python mirror of run-combo-trial.mjs — predictions only, no timing.
#
# Scores the SAME frozen artifacts with the SAME decode logic so the
# browser combo trial can be checked case-by-case: labeler q8+fp32 via
# train-span-labeler's make_forward_onnx / tags_to_spans / constrained_decode
# (loaded from the file — the filename has a hyphen, so importlib instead of
# a plain import; NOT re-implemented here), classifier q8 written inline
# (plain argmax, same natural-length feed as the classifier trial). The
# category-conditioned rule variant (inspect/move/npc_talk -> ITEM forced
# empty) mirrors the JS enumeration exactly: TGT options only, empty option
# first, strictly-greater wins, ties keep the first enumerated
# (empty > a asc > j asc).
#
# Output: artifacts/benchmark/combo-trial-python-<ts>.json (compare against
# the browser combo-trial-<ts>.json arms[].cases).
#
# Usage: python scripts/eval-combo.py

import importlib.util
import json
import math
import pathlib
import time

import numpy as np

sys_path = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("train_span_labeler", sys_path / "train-span-labeler.py")
tsl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tsl)

FRONTEND_ROOT = sys_path.parent
ARTIFACTS = FRONTEND_ROOT.parent / "artifacts" / "benchmark"
LABELER_DIR = FRONTEND_ROOT / "public" / "models" / "minirbt-h256-span"
CLASSIFIER_DIR = FRONTEND_ROOT / "public" / "models" / "minirbt-h256-action"
LABELS = ["item_use", "npc_talk", "move", "inspect", "other"]


def constrained_decode_suppress_item(offsets, probs):
    """规则变体：ITEM 强制为空，只枚举 TGT 选项（平局取先枚举者）。

    与 run-combo-trial.mjs 的 constrainedDecode(offsets, probs, true) 同序：
    空 > a 升 > j 升，严格大于才替换。
    """
    idx = [i for i, (_, end) in enumerate(offsets) if end != 0]
    n = len(idx)
    if n == 0:
        return None, None, [0] * len(offsets)
    log_p = [[math.log(max(p, 1e-12)) for p in row] for row in probs]
    b, cont, o = (tsl.TAGS.index("B-TGT"), tsl.TAGS.index("I-TGT"), tsl.TAGS.index("O"))
    best_gain, best_a, best_j = 0.0, None, None  # 空选项先行
    for a in range(n):
        gain = log_p[idx[a]][b] - log_p[idx[a]][o]
        for j in range(a, n):
            if j > a:
                gain += log_p[idx[j]][cont] - log_p[idx[j]][o]
            if gain > best_gain:
                best_gain, best_a, best_j = gain, a, j
    assignment = ["O"] * n
    if best_a is not None:
        assignment[best_a] = "B-TGT"
        for t in range(best_a + 1, best_j + 1):
            assignment[t] = "I-TGT"
    ids = [0] * len(offsets)
    for k, t in enumerate(idx):
        ids[t] = tsl.TAGS.index(assignment[k])
    item = None
    target = None if best_a is None else (offsets[idx[best_a]][0], offsets[idx[best_j]][1])
    return item, target, ids


def make_classify(session, tokenizer):
    def classify(text):
        enc = tokenizer(text, truncation=True, max_length=32)
        seq = len(enc["input_ids"])
        feed = {
            "input_ids": np.array([enc["input_ids"]], dtype=np.int64),
            "attention_mask": np.ones((1, seq), dtype=np.int64),
            "token_type_ids": np.zeros((1, seq), dtype=np.int64),
        }
        logits = session.run(None, feed)[0][0]
        best = int(logits.argmax())
        shifted = logits - logits.max()
        exp = np.exp(shifted)
        probs = exp / exp.sum()
        return best, [float(p) for p in probs]

    return classify


def strict_hit(text, expected, predicted):
    if expected is None and predicted is None:
        return True
    if expected is None or predicted is None:
        return False
    return predicted == (text.index(expected), text.index(expected) + len(expected))


def main():
    import onnxruntime as ort
    from transformers.models.bert.tokenization_bert_fast import BertTokenizerFast

    manifest = json.loads((ARTIFACTS / "span-labeler-corpus.json").read_text(encoding="utf-8"))
    categories_doc = json.loads((ARTIFACTS / "span-labeler-dev-categories.json").read_text(encoding="utf-8"))
    suppress = set(categories_doc["suppressCategories"])
    category_by_text = {c["text"]: c["category"] for c in categories_doc["categories"]}

    batches = [
        ("devClassic", manifest["devClassic"]),
        ("devGroups", [row for grp in manifest["devGroups"] for row in grp["sentences"]]),
        ("scored", manifest["scored"]),
    ]

    tokenizer_labeler = BertTokenizerFast.from_pretrained(LABELER_DIR)
    tokenizer_classifier = BertTokenizerFast.from_pretrained(CLASSIFIER_DIR)
    session_classifier = ort.InferenceSession(str(CLASSIFIER_DIR / "onnx" / "model_quantized.onnx"))
    classify = make_classify(session_classifier, tokenizer_classifier)

    arms = []
    for arm_name, model_file in (("q8-t1", "onnx/model_quantized.onnx"), ("fp32-t1", "onnx/model.onnx")):
        session_labeler = ort.InferenceSession(str(LABELER_DIR / model_file))
        forward = tsl.make_forward_onnx(session_labeler, tokenizer_labeler)
        cases = []
        for batch_name, rows in batches:
            for row in rows:
                text = row["text"]
                gold_category = category_by_text[text]
                best, cat_probs = classify(text)
                predicted_category = LABELS[best]
                offsets, greedy_ids, probs = forward(text)

                def spans_str(span):
                    return text[span[0]: span[1]] if span else None

                g_item, g_tgt = tsl.tags_to_spans(text, offsets, greedy_ids)
                c_item, c_tgt, _ = tsl.constrained_decode(offsets, probs)
                gr_item, gr_tgt, _ = (
                    constrained_decode_suppress_item(offsets, probs)
                    if gold_category in suppress
                    else tsl.constrained_decode(offsets, probs)
                )
                pr_item, pr_tgt, _ = (
                    constrained_decode_suppress_item(offsets, probs)
                    if predicted_category in suppress
                    else tsl.constrained_decode(offsets, probs)
                )

                def sub(item_span, target_span):
                    return {
                        "predItem": spans_str(item_span),
                        "predTarget": spans_str(target_span),
                        "itemStrict": strict_hit(text, row["item"], item_span),
                        "targetStrict": strict_hit(text, row["target"], target_span),
                    }

                cases.append({
                    "batch": batch_name,
                    "group": row.get("group"),
                    "text": text,
                    "expectItem": row["item"],
                    "expectTarget": row["target"],
                    "goldCategory": gold_category,
                    "predictedCategory": predicted_category,
                    "categoryCorrect": predicted_category == gold_category,
                    "pPredicted": round(cat_probs[best], 4),
                    "pGold": round(cat_probs[LABELS.index(gold_category)], 4),
                    "decodes": {
                        "greedy": sub(g_item, g_tgt),
                        "constrained": sub(c_item, c_tgt),
                        "goldRule": sub(gr_item, gr_tgt),
                        "predRule": sub(pr_item, pr_tgt),
                    },
                })
        arms.append({"name": arm_name, "file": model_file, "cases": cases})

        def both(variant):
            return sum(1 for c in cases if c["decodes"][variant]["itemStrict"] and c["decodes"][variant]["targetStrict"])

        print(f"{arm_name} merged(53) both-fields: greedy {both('greedy')}/53 constrained {both('constrained')}/53 goldRule {both('goldRule')}/53 predRule {both('predRule')}/53")

    out_path = ARTIFACTS / f"combo-trial-python-{int(time.time() * 1000)}.json"
    out_path.write_text(json.dumps({"suppressCategories": sorted(suppress), "arms": arms}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()

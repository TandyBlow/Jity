# N4 v3 corpus (N4 optimization experiment): derive the v3 rows from the
# committed v2 rows so the facts/worlds stay fixed and only the N3 plan and
# N4 target change.
#
# Changes:
#   1. drop the old N1 co-presence `positioned_at` facts (N1 no longer emits
#      them; they are not part of the current pipeline);
#   2. renumber the remaining facts f0.. and recompute the plan with the
#      current N3 default (cross-group pronoun guard ON);
#   3. recompose the target with compose_v3: same-entity facts in a group
#      merge into one sentence with clause commas; different entities stay
#      separate; appearance/personality/no_change/time keep their sentences.
#
# The v2 corpus files are READ-ONLY here. The family-C test rows are REUSED
# from the v2 frozen holdout: this is a direct N4 A/B comparison on the same
# family, not a new independent holdout. The freeze sha of the new
# holdout-v3.jsonl is written before training.

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
REPO = WC.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(WC))
sys.path.insert(0, str(WC / "n4_corpus"))

import n3_organize  # noqa: E402
from compose_v3 import compose_target_v3  # noqa: E402
from render_v2 import render_input_v2, render_input_v2_ablated  # noqa: E402

V2 = HERE / "corpus_v2"
OUT = HERE / "corpus_v3"
CKPT_V2 = HERE / "ckpt-v2"


def sha_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def renumber(facts):
    out = []
    for i, f in enumerate(facts):
        f = dict(f)
        f["factId"] = f"f{i}"
        f["ref"] = i
        out.append(f)
    return out


def names_of(facts):
    names = {}
    for f in facts:
        if f.get("entityId") and f.get("name"):
            names.setdefault(f["entityId"], f["name"])
    return names


def rebase(row, tok):
    facts = renumber([f for f in row["facts"]
                      if f["kind"] != "positioned_at"])
    names, hints = names_of(facts), row.get("genderHints") or {}
    plan = n3_organize.plan_v3(facts, names, hints,
                              cross_group_guard=True)
    if "refusal" in plan:
        raise SystemExit(f"plan refusal on {row['rowId']}: {plan}")
    variant = int(row["rowId"].rsplit(":v", 1)[1])
    text = compose_target_v3(plan, facts, variant)
    text_in = render_input_v2(plan, facts)
    n_tok = len(tok(text_in).input_ids)
    out = dict(row)
    out.update({
        "task": "n4-sentence-v3",
        "plan": plan, "facts": facts,
        "input": text_in,
        "inputRealTokens": n_tok,
        "ablatedInput": render_input_v2_ablated(plan, facts),
        "text": text,
        "mustExpress": [f["factId"] for f in facts],
        "pronounElicited": any(g.get("pronoun")
                               for s in plan["sentences"]
                               for g in s["coreference"]),
        "hashes": {"facts": hashlib.sha256(
            json.dumps(facts, ensure_ascii=False, sort_keys=True)
            .encode("utf-8")).hexdigest()},
    })
    return out


def style(rows):
    groups = facts = sents = 0
    for r in rows:
        groups += len(r["plan"]["sentences"])
        facts += len(r["facts"])
        sents += r["text"].count("。")
    return (round(sents / groups, 3) if groups else 0,
            round(facts / sents, 3) if sents else 0,
            sents)


def main() -> int:
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tok = T5Tokenizer.from_pretrained(str(CKPT_V2), legacy=False)
    train_src = [json.loads(l) for l in
                 (V2 / "train-v2.jsonl").read_text(encoding="utf-8")
                 .splitlines() if l.strip()]
    test_src = [json.loads(l) for l in
                (V2 / "holdout-v2.jsonl").read_text(encoding="utf-8")
                .splitlines() if l.strip()]
    if any(r["familyId"] == "v2-c-salt" for r in train_src):
        raise SystemExit("family C leaked into the v2 training source")
    train = [rebase(r, tok) for r in train_src]
    test = [rebase(r, tok) for r in test_src]
    OUT.mkdir(parents=True, exist_ok=True)
    train_path, test_path = OUT / "train-v3.jsonl", OUT / "holdout-v3.jsonl"
    train_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                  for r in train), encoding="utf-8",
                          newline="\n")
    test_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                 for r in test), encoding="utf-8",
                         newline="\n")
    test_sha = sha_file(test_path)
    freeze = {
        "freeze": "n4-v3-holdout (N4 optimization experiment) -- family-C "
                  "rows REUSED from the v2 frozen holdout with N3 guard-on "
                  "plans and the merged-target composer; frozen before any "
                  "v3 training run. This is a direct A/B comparison, not a "
                  "new independent holdout.",
        "file": "holdout-v3.jsonl", "rows": len(test),
        "familyId": "v2-c-salt", "sha256": test_sha,
        "source": "experiments/world-components/n4_corpus_v2/corpus_v2/"
                  "holdout-v2.jsonl",
        "sourceSha256": sha_file(V2 / "holdout-v2.jsonl"),
        "criteria": "same G1/G2/G3/G4/G5/G6 and P1/P2 machinery as "
                    "eval_n4_v2.py; reused test family",
    }
    (OUT / "holdout-v3-freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")

    v2_style = style(test_src)
    v3_style = style(test)
    before_rows = sum(1 for a, b in zip(train_src, train)
                      if a["text"].count("。") > b["text"].count("。"))
    report = {
        "purpose": "N4 v3 corpus: same v2 facts/worlds, current N3 guard-on "
                   "plans, merged same-entity targets",
        "scope": "derived corpus for the N4 optimization experiment; family-C "
                 "rows are reused from v2 and are not a new independent "
                 "holdout",
        "source": {
            "train": "n4_corpus_v2/corpus_v2/train-v2.jsonl",
            "holdout": "n4_corpus_v2/corpus_v2/holdout-v2.jsonl",
            "trainSha256": sha_file(V2 / "train-v2.jsonl"),
            "holdoutSha256": sha_file(V2 / "holdout-v2.jsonl"),
        },
        "counts": {"trainDev": len(train), "test": len(test),
                   "droppedPositionedAt": sum(
                       1 for r in train_src + test_src for f in r["facts"]
                       if f["kind"] == "positioned_at")},
        "targetStyle": {
            "v2": {"meanSentencesPerGroup": v2_style[0],
                   "meanFactsPerSentence": v2_style[1],
                   "sentences": v2_style[2]},
            "v3": {"meanSentencesPerGroup": v3_style[0],
                   "meanFactsPerSentence": v3_style[1],
                   "sentences": v3_style[2]},
            "trainRowsWithFewerSentences": before_rows,
        },
        "freeze": freeze,
    }
    out = REPO / "artifacts" / "world-components" / "n4-v3-corpus-report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps(report["counts"], ensure_ascii=False))
    print(json.dumps(report["targetStyle"], ensure_ascii=False))
    print("holdout sha", test_sha[:16], "->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

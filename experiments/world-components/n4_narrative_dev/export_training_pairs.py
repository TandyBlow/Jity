# Export N4.0 training pairs from the approved 12-case corpus.
#
# This is the overfit-check corpus only: 9 train / 3 check, deterministic by
# case order. It is NOT a formal train/dev/holdout split and must not be used
# for generalization claims. Targets are the approved narratives.
#
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/export_training_pairs.py

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
REPO = WC.parent.parent
sys.path.insert(0, str(WC))
sys.path.insert(0, str(HERE))

import n2_perspective as n2  # noqa: E402
import n3_organize as n3  # noqa: E402
import n4_input_renderer as n4r  # noqa: E402

OUT = HERE / "training_pairs.jsonl"
TRAIN_N = 9


def main() -> int:
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tok = T5Tokenizer.from_pretrained(
        str(WC / "n4_corpus_v2" / "ckpt-v2"), legacy=False)
    world = json.loads((HERE / "world.json").read_text(encoding="utf-8"))
    cases = [json.loads(line) for line in
             (HERE / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    assert len(cases) == 12, len(cases)
    names = {cid: ch["name"] for cid, ch in world["characters"].items()}
    rows = []
    for i, c in enumerate(cases):
        facts = [dict(f) for f in c["facts"]]
        for f in facts:
            if f.get("entityId") in world["characters"]:
                f["entityGroup"] = "characters"
        res = n2.classify_facts(
            facts, c["perspective"], may_policy="select",
            visible_other_actions=True)
        selected_ids = set(res["selectedFactIds"])
        selected = [f for f in facts if f["factId"] in selected_ids]
        plan = n3.plan_v3(selected, names, cross_group_guard=True)
        assert "refusal" not in plan, (c["id"], plan)
        problems = n3.check_plan_v3(plan, selected, names)
        assert not problems, (c["id"], problems)
        packed = n4r.pack_narrative_input(
            c, plan, world, selected_fact_ids=res["selectedFactIds"])
        assert packed["status"] == "ok", (c["id"], packed)
        input_tokens = len(tok(packed["input"]).input_ids)
        target_tokens = len(tok(c["narrative"]).input_ids)
        rows.append({
            "rowId": f"n4n-overfit:{c['id']}",
            "sourceId": c["id"],
            "split": "overfit-train" if i < TRAIN_N else "overfit-check",
            "inputVersion": packed["version"],
            "input": packed["input"],
            "target": c["narrative"],
            "inputTokens": input_tokens,
            "targetTokens": target_tokens,
        })
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                             for r in rows) + "\n",
                   encoding="utf-8", newline="\n")
    train = sum(1 for r in rows if r["split"] == "overfit-train")
    check = len(rows) - train
    print(f"training pairs: {len(rows)} ({train} train / {check} check); "
          f"input {min(r['inputTokens'] for r in rows)}-"
          f"{max(r['inputTokens'] for r in rows)}; "
          f"target {min(r['targetTokens'] for r in rows)}-"
          f"{max(r['targetTokens'] for r in rows)}; -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

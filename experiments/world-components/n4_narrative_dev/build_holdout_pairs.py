# Build the new-world holdout pairs for zero-shot evaluation.
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/build_holdout_pairs.py

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(WC))

import n2_perspective as n2  # noqa: E402
import n3_organize as n3  # noqa: E402
import n4_input_renderer as n4r  # noqa: E402

OUT = HERE / "holdout_pairs.jsonl"
FREEZE = HERE / "holdout-freeze.json"


def main():
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tok = T5Tokenizer.from_pretrained(
        str(WC / "n4_corpus_v2" / "ckpt-v2"), legacy=False)
    world = json.loads((HERE / "holdout_world.json").read_text(encoding="utf-8"))
    names = {cid: ch["name"] for cid, ch in world["characters"].items()}
    cases = [json.loads(line) for line in
             (HERE / "holdout_corpus.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    assert len(cases) == 12, len(cases)
    rows = []
    for c in cases:
        facts = [dict(f) for f in c["facts"]]
        for f in facts:
            if f.get("entityId") in world["characters"]:
                f["entityGroup"] = "characters"
        res = n2.classify_facts(
            facts, c["perspective"], may_policy="select",
            visible_other_actions=True)
        selected = [f for f in facts
                    if f["factId"] in set(res["selectedFactIds"])]
        plan = n3.plan_v3(selected, names, cross_group_guard=True)
        assert "refusal" not in plan, (c["id"], plan)
        problems = n3.check_plan_v3(plan, selected, names)
        assert not problems, (c["id"], problems)
        packed = n4r.pack_narrative_input(
            c, plan, world, selected_fact_ids=res["selectedFactIds"])
        assert packed["status"] == "ok", (c["id"], packed)
        in_tok = len(tok(packed["input"]).input_ids)
        out_tok = len(tok(c["narrative"]).input_ids)
        assert in_tok <= 512 and out_tok <= 128, (c["id"], in_tok, out_tok)
        rows.append({
            "rowId": f"n4-holdout:{c['id']}", "sourceId": c["id"],
            "inputVersion": packed["version"],
            "input": packed["input"], "target": c["narrative"],
            "inputTokens": in_tok, "targetTokens": out_tok,
        })
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                             for r in rows) + "\n",
                   encoding="utf-8", newline="\n")
    freeze = {
        "scope": "N4 new-world zero-shot holdout; not used for training",
        "date": "2026-11-02",
        "ids": [r["sourceId"] for r in rows],
        "inputSha256": hashlib.sha256(
            "".join(r["input"] for r in rows).encode("utf-8")).hexdigest(),
        "targetSha256": hashlib.sha256(
            "".join(r["target"] for r in rows).encode("utf-8")).hexdigest(),
        "rows": len(rows),
    }
    FREEZE.write_text(json.dumps(freeze, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8", newline="\n")
    print("holdout pairs:", len(rows))
    print("input", min(r["inputTokens"] for r in rows),
          "-", max(r["inputTokens"] for r in rows),
          "target", min(r["targetTokens"] for r in rows),
          "-", max(r["targetTokens"] for r in rows))
    print("freeze:", FREEZE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

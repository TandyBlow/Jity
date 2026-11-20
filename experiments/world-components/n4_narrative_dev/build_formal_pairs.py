# Build the 120-case N4 formal pairs (100 train / 8 dev / 12 frozen holdout).
#
# All 12 v0 + 20 v1 + 88 v2 cases are approved. The holdout is a stratified
# same-world slice across the 8 patterns; this is a scaling/quality run, not
# a final new-world generalization claim.
#
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/build_formal_pairs.py

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

OUT = HERE / "formal_pairs.jsonl"
FREEZE = HERE / "formal-freeze.json"
DEV_IDS = {"n4n-41", "n4n-52", "n4n-63", "n4n-73",
           "n4n-86", "n4n-97", "n4n-108", "n4n-119"}
HOLDOUT_IDS = {"n4n-40", "n4n-43", "n4n-53", "n4n-54", "n4n-64", "n4n-65",
               "n4n-74", "n4n-75", "n4n-87", "n4n-98", "n4n-109",
               "n4n-120"}


def load_cases():
    out = []
    for name in ("corpus.jsonl", "corpus_v1.jsonl", "corpus_v2.jsonl"):
        rows = [json.loads(line) for line in
                (HERE / name).read_text(encoding="utf-8").splitlines()
                if line.strip()]
        out.extend(rows)
    return out


def sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tok = T5Tokenizer.from_pretrained(
        str(WC / "n4_corpus_v2" / "ckpt-v2"), legacy=False)
    world = json.loads((HERE / "world.json").read_text(encoding="utf-8"))
    names = {cid: ch["name"] for cid, ch in world["characters"].items()}
    cases = load_cases()
    assert len(cases) == 120, len(cases)
    assert len({c["id"] for c in cases}) == 120
    assert all(c.get("reviewStatus") == "approved" for c in cases)
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
        cid = c["id"]
        if cid in HOLDOUT_IDS:
            split = "formal-holdout"
        elif cid in DEV_IDS:
            split = "formal-dev"
        else:
            split = "formal-train"
        in_tok = len(tok(packed["input"]).input_ids)
        out_tok = len(tok(c["narrative"]).input_ids)
        rows.append({
            "rowId": f"n4-formal:{cid}", "sourceId": cid, "split": split,
            "inputVersion": packed["version"],
            "input": packed["input"], "target": c["narrative"],
            "inputTokens": in_tok, "targetTokens": out_tok,
        })
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                             for r in rows) + "\n",
                   encoding="utf-8", newline="\n")
    hold = [r for r in rows if r["split"] == "formal-holdout"]
    freeze = {
        "scope": "N4 120-case same-world formal run; holdout is stratified "
                 "across the 8 patterns, not a new-world set",
        "date": "2026-11-02",
        "holdoutIds": [r["sourceId"] for r in hold],
        "inputSha256": sha_text("".join(r["input"] for r in hold)),
        "targetSha256": sha_text("".join(r["target"] for r in hold)),
        "rows": len(hold),
    }
    FREEZE.write_text(json.dumps(freeze, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8", newline="\n")
    counts = {s: sum(1 for r in rows if r["split"] == s)
              for s in ("formal-train", "formal-dev", "formal-holdout")}
    print("formal pairs:", counts)
    print("input", min(r["inputTokens"] for r in rows),
          "-", max(r["inputTokens"] for r in rows),
          "target", min(r["targetTokens"] for r in rows),
          "-", max(r["targetTokens"] for r in rows))
    print("freeze:", FREEZE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

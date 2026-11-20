# Validate the 20-case v1 review corpus through N2 -> N3 -> N4.0 packing.
#
# Checks: no dropped facts, no plan problems, pack ok, input <= 512,
# target <= 128. Reports token counts; targets above 99 are flagged but
# not auto-edited.

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
sys.path.insert(0, str(WC))
sys.path.insert(0, str(HERE))

import n2_perspective as n2  # noqa: E402
import n3_organize as n3  # noqa: E402
import n4_input_renderer as n4r  # noqa: E402

CORPUS = HERE / "corpus_v1.jsonl"
OUT = HERE / "corpus_v1_validation.json"


def main():
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tok = T5Tokenizer.from_pretrained(
        str(WC / "n4_corpus_v2" / "ckpt-v2"), legacy=False)
    world = json.loads((HERE / "world.json").read_text(encoding="utf-8"))
    names = {cid: ch["name"] for cid, ch in world["characters"].items()}
    cases = [json.loads(line) for line in
             CORPUS.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(cases) == 20, len(cases)
    bad = []
    report = []
    for c in cases:
        facts = [dict(f) for f in c["facts"]]
        for f in facts:
            if f.get("entityId") in world["characters"]:
                f["entityGroup"] = "characters"
        res = n2.classify_facts(
            facts, c["perspective"], may_policy="select",
            visible_other_actions=True)
        selected_ids = set(res["selectedFactIds"])
        selected = [f for f in facts if f["factId"] in selected_ids]
        dropped = [f["factId"] for f in facts
                   if f["factId"] not in selected_ids]
        plan = n3.plan_v3(selected, names, cross_group_guard=True)
        problems = ([] if "refusal" in plan
                    else n3.check_plan_v3(plan, selected, names))
        packed = n4r.pack_narrative_input(
            c, plan, world, selected_fact_ids=res["selectedFactIds"])
        in_tok = (len(tok(packed["input"]).input_ids)
                  if packed["status"] == "ok" else -1)
        out_tok = len(tok(c["narrative"]).input_ids)
        flag = ""
        if (dropped or problems or packed["status"] != "ok"
                or out_tok > 99 or in_tok > 512):
            flag = "  <-- CHECK"
            bad.append(c["id"])
        print(f"{c['id']} {c['title']}: n2={res['status']} "
              f"selected={res['summary']['selected']} dropped={dropped} "
              f"groups={len(plan.get('sentences', []))} problems={problems} "
              f"pack={packed['status']} in={in_tok} out={out_tok}{flag}")
        report.append({
            "id": c["id"], "title": c["title"],
            "n2Status": res["status"], "n2Summary": res["summary"],
            "dropped": dropped, "planProblems": problems,
            "plan": plan, "packStatus": packed["status"],
            "inputVersion": packed.get("version"),
            "inputTokens": in_tok, "targetTokens": out_tok,
            "target": c["narrative"],
        })
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print("bad:", bad if bad else "none")
    print("report ->", OUT)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

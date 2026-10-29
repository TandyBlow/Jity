# N3 baseline runner r1 (review round 20): B1/B2 over the N2 v2 dev items.
#
# Selection input = each item's program-defined `target` (the gold selection;
# these are C-baselines, no model arm is claimed). For every item:
#   - build B1/B2 plans (no prose)
#   - assert the hard invariants (I1 coverage, I2 referent anchoring,
#     I3 B1 canonical order) — a violation voids the report
#   - record group counts / facts per group / mention stats as measurable
#     baseline numbers that model arms must beat, not just match
#
# Consumer-path smoke (clearly separate, no quality claim): each B1 sentence
# group is rendered through the SHARED n4_render and narrated by the FROZEN
# r3-direction checkpoint (offline Python). Stored raw for human review;
# nothing here counts as N4 evidence and the N4 holdout is not used.
#
# Usage: python experiments/world-components/n2_selection/run_n3_baselines.py [--skip-smoke]
# Output: artifacts/world-components/n3-baselines-r1.json

import hashlib
import importlib.machinery
import json
import pathlib
import sys
import time
import types

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
CORPUS_DIR = HERE.parent / "n4_corpus"
ITEMS = HERE / "items.jsonl"
ASSETS = HERE.parent / "assets"
CKPT = ASSETS / "n4-finetune" / "r3-direction"
REPORT = REPO / "artifacts" / "world-components" / "n3-baselines-r1.json"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(CORPUS_DIR))
from n3_plan import plan_b1, plan_b2, check_invariants, PRIORITY  # noqa: E402
from n4_render import render_input, corpus_hashes  # noqa: E402


def sha_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_items() -> list:
    return [json.loads(line) for line in
            ITEMS.read_text(encoding="utf-8").splitlines() if line.strip()]


def names_of(item: dict) -> dict:
    names = {}
    for f in item["facts"]:
        if f.get("entityId") and f.get("name"):
            names.setdefault(f["entityId"], f["name"])
    return names


def stats(plan: dict, selected: list) -> dict:
    facts = {f["factId"]: f for f in selected}
    groups = plan["sentences"]
    multi = [g for g in groups if len(g["factIds"]) > 1]
    actor_groups = [g for g in multi if len({
        (facts[fid].get("entityId") or fid) for fid in g["factIds"]}) == 1]
    return {"groups": len(groups), "factsPerGroupMean": round(
                sum(len(g["factIds"]) for g in groups) / len(groups), 2),
            "multiFactGroups": len(multi),
            "actorCohesiveGroups": len(actor_groups),
            "mentions": sum(len(g["coreference"]) for g in groups),
            "factIds": [fid for g in groups for fid in g["factIds"]]}


def run_smoke(items: list) -> dict:
    """Offline Python, frozen r3-direction checkpoint. Evidence for the
    consumer path ONLY — no N4 quality claim, holdout untouched."""
    try:
        import pyarrow  # noqa: F401
    except Exception:
        stub = types.ModuleType("pyarrow")
        stub.__version__ = "16.1.0"
        stub.__path__ = []
        sys.modules["pyarrow"] = stub
    tf_stub = types.ModuleType("tensorflow")
    tf_stub.__spec__ = importlib.machinery.ModuleSpec("tensorflow", None)
    tf_stub.__path__ = []
    sys.modules.setdefault("tensorflow", tf_stub)

    import torch
    import transformers
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    tokenizer = T5Tokenizer(vocab_file=str(CKPT / "spiece.model"), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(CKPT), torch_dtype=torch.float32)
    model.cuda()
    model.eval()
    smoke = {"groups": [], "disclaimers": ["consumer-path smoke only; not N4 evidence; holdout not used"]}
    for item in items:
        names = names_of(item)
        selected = [f for f in item["facts"] if f["factId"] in set(item["target"])]
        p1 = plan_b1(selected, names)
        for sentence in p1["sentences"]:
            group_facts = [f for f in selected if f["factId"] in set(sentence["factIds"])]
            prompt = render_input(group_facts)
            enc = tokenizer(prompt, return_tensors="pt", truncation=True,
                            max_length=160).to(model.device)
            t0 = time.perf_counter()
            with torch.no_grad():
                out = model.generate(**enc, max_new_tokens=32,
                                     num_beams=1, do_sample=False)
            text = tokenizer.decode(out[0], skip_special_tokens=True)
            smoke["groups"].append({
                "itemId": item["itemId"], "sentenceIndex": sentence["index"],
                "factIds": sentence["factIds"], "prompt": prompt,
                "output": text, "wallSeconds": round(time.perf_counter() - t0, 2)})
    return smoke


def main() -> None:
    skip_smoke = "--skip-smoke" in sys.argv
    items = load_items()
    assert len(items) == 16 and all(r.get("batch") == "v2" for r in items)

    per_item = []
    problems = []
    for item in items:
        names = names_of(item)
        selected = [f for f in item["facts"] if f["factId"] in set(item["target"])]
        entry = {"itemId": item["itemId"], "selectedIds": [f["factId"] for f in selected]}
        for make, label in ((plan_b1, "B1"), (plan_b2, "B2")):
            plan = make(selected, names)
            violations = check_invariants(plan, selected, names)
            problems.extend(f"{item['itemId']} {v}" for v in violations)
            entry[label] = {"plan": plan, "stats": stats(plan, selected),
                            "invariantViolations": violations}
        per_item.append(entry)

    if problems:
        print("REPORT VOID — invariance violations:")
        for x in problems:
            print(" ", x)
        sys.exit(2)
    print("invariance PASS: I1 coverage, I2 referent anchoring, I3 B1 order")

    smoke = None if skip_smoke else run_smoke(items)

    b1_total = sum(e["B1"]["stats"]["groups"] for e in per_item)
    b2_total = sum(e["B2"]["stats"]["groups"] for e in per_item)
    report = {
        "purpose": "N3 structured organisation-plan baselines r1 (B1/B2), determinstic program arms",
        "planShape": "sentences[{index, factIds, coreference[{mention, refersTo}]}]; no prose (prose stays in N4)",
        "provenance": {"items": sha_file(ITEMS),
                       "frozenRenderer": corpus_hashes()["n4_render.py"],
                       "checkpoint": {f.name: sha_file(f)[:16]
                                      for f in sorted(CKPT.iterdir()) if f.is_file()} if not skip_smoke else None},
        "summary": {"items": len(items),
                    "b1GroupsTotal": b1_total, "b2GroupsTotal": b2_total,
                    "b1FactsPerGroupMean": round(sum(e["B1"]["stats"]["factsPerGroupMean"] for e in per_item) / len(items), 2),
                    "invariantViolations": 0},
        "items": per_item,
        "smoke": smoke,
        "disclaimers": [
            "B1/B2 are program baselines: their grouping/order numbers are guarantees, not achievements",
            "model arms for N3 are NOT run yet; the baselines are the numbers they must beat",
            "coreference suggestions are NAMES only; pronoun policy needs the coordinator's decision",
            "significance target definition inherits N2's open question (human confirmation pending)",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"B1 groups {b1_total} / B2 groups {b2_total} over {len(items)} items; "
          f"B1 facts/group mean {report['summary']['b1FactsPerGroupMean']}")
    if smoke:
        walls = [g["wallSeconds"] for g in smoke["groups"]]
        print(f"consumer smoke: {len(walls)} group renders, mean {round(sum(walls) / len(walls), 2)}s")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
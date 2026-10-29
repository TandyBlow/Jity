# N3 baseline runner r2 (repair round 21): B1/B2 over the N2 v2 dev items.
#
# Selection input = each item's program-defined `target` (the gold selection;
# these are C-baselines, no model arm is claimed). For every item:
#   - build B1/B2 plans (no prose)
#   - assert the hard invariants (I1 coverage, I2 referent anchoring,
#     I3 B1 canonical order) — a violation voids the report
#   - record group counts / facts per group / mention stats as measurable
#     baseline numbers that model arms must beat, not just match
#
# I2 anchoring is checked against the sentence group's OWN entityIds only
# (the r1 global `sentence_ids` set is gone). `--tamper` runs the mutation
# probe: a valid plan is deliberately broken in six ways and every
# applicable mutation MUST be caught. The probe result is archived.
#
# Two separate archives:
#   n3-baselines-r1.json      plans, structural stats, optional tamper probe
#   n3-factids-smoke-r1.json  factIds consumer smoke (offline Python, frozen
#                             r3-direction checkpoint, one group at a time)
#
# The smoke is FACTIDS consumption only. n4_render.render_input() takes a
# flat fact list: it has no coreference parameter and no sentence-group
# boundary, so coreference is NOT consumed by N4 and cross-group coherence
# is NOT tested. No N4 quality claim is made and the sealed N4 holdout is
# untouched.
#
# Usage:
#   python experiments/world-components/n2_selection/run_n3_baselines.py \
#       [--skip-smoke] [--smoke-only] [--tamper]
# Output: artifacts/world-components/n3-baselines-r1.json
#         artifacts/world-components/n3-factids-smoke-r1.json

import copy
import datetime
import hashlib
import importlib.machinery
import json
import pathlib
import subprocess
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
SMOKE_REPORT = REPO / "artifacts" / "world-components" / "n3-factids-smoke-r1.json"

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


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO,
                                       text=True).strip()
    except Exception:
        return "unknown"


def load_items() -> list:
    return [json.loads(line) for line in
            ITEMS.read_text(encoding="utf-8").splitlines() if line.strip()]


def names_of(item: dict) -> dict:
    names = {}
    for f in item["facts"]:
        if f.get("entityId") and f.get("name"):
            names.setdefault(f["entityId"], f["name"])
    return names


def selected_of(item: dict) -> list:
    target = set(item["target"])
    return [f for f in item["facts"] if f["factId"] in target]


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


def build_all(items: list) -> tuple:
    """-> (per_item entries, problem strings). Does not write anything."""
    per_item, problems = [], []
    for item in items:
        names = names_of(item)
        selected = selected_of(item)
        entry = {"itemId": item["itemId"], "selectedIds": [f["factId"] for f in selected]}
        for make, label in ((plan_b1, "B1"), (plan_b2, "B2")):
            plan = make(selected, names)
            violations = check_invariants(plan, selected, names)
            problems.extend(f"{item['itemId']} {v}" for v in violations)
            entry[label] = {"plan": plan, "stats": stats(plan, selected),
                            "invariantViolations": violations}
        per_item.append(entry)
    return per_item, problems


# ---- tamper probe ---------------------------------------------------------
def _ref_with_sentence(plan: dict):
    for i, s in enumerate(plan["sentences"]):
        if s["coreference"] and s["factIds"]:
            return i, s
    return None, None


def _other_group(plan: dict, index: int, selected: list, key: str):
    """Pick a different sentence group and return a value under `key`."""
    by_id = {f["factId"]: f for f in selected}
    own = set(plan["sentences"][index]["factIds"])
    for j, s in enumerate(plan["sentences"]):
        if j == index:
            continue
        for fid in s["factIds"]:
            fact = by_id[fid]
            value = fid if key == "factId" else fact.get("entityId")
            if value and value not in own:
                return value
    return None


def run_tamper(items: list) -> dict:
    """Break a valid B1 plan on purpose; every applicable mutation must be
    caught by check_invariants. Controls prove the unmodified plan is clean."""
    cases = {
        "crossGroupEntity": {"applicable": 0, "detected": 0},
        "globalFactId": {"applicable": 0, "detected": 0},
        "unknownEntity": {"applicable": 0, "detected": 0},
        "wrongMention": {"applicable": 0, "detected": 0},
        "droppedFact": {"applicable": 0, "detected": 0},
        "duplicatedFact": {"applicable": 0, "detected": 0},
        "fabricatedFact": {"applicable": 0, "detected": 0},
    }
    controls = {"validPlans": 0, "zeroProblems": 0}
    misses = []
    per_item = []

    def attempt(item, label, mutate):
        names = names_of(item)
        selected = selected_of(item)
        plan = plan_b1(selected, names)
        tampered = copy.deepcopy(plan)
        changed = mutate(tampered)
        if not changed:
            return "na"
        problems = check_invariants(tampered, selected, names)
        cases[label]["applicable"] += 1
        cases[label]["detected"] += 1 if problems else 0
        if not problems:
            misses.append(f"{item['itemId']} {label} NOT caught")
        return "ok"

    for item in items:
        names = names_of(item)
        selected = selected_of(item)
        valid = plan_b1(selected, names)
        controls["validPlans"] += 1
        if not check_invariants(valid, selected, names):
            controls["zeroProblems"] += 1
        else:
            misses.append(f"{item['itemId']} valid control has problems")

        idx, sent = _ref_with_sentence(valid)
        cross_entity = _other_group(valid, idx, selected, "entityId") if sent else None
        global_fid = _other_group(valid, idx, selected, "factId") if sent else None

        def cross_group(p):
            p["sentences"][idx]["coreference"][0]["refersTo"] = cross_entity
            p["sentences"][idx]["coreference"][0]["mention"] = names.get(cross_entity, "某名")
            return True

        def global_fact(p):
            p["sentences"][idx]["coreference"][0]["refersTo"] = global_fid
            return True

        def unknown(p):
            p["sentences"][idx]["coreference"][0]["refersTo"] = "char_999"
            return True

        def wrong_name(p):
            p["sentences"][idx]["coreference"][0]["mention"] = "错名"
            return True

        def dropped(p):
            nonempty = [s for s in p["sentences"] if s["factIds"]]
            victim = nonempty[-1]
            if len(victim["factIds"]) > 1:
                victim["factIds"].pop()
            else:
                p["sentences"].remove(victim)
            return True

        def duplicated(p):
            p["sentences"][0]["factIds"].append(p["sentences"][0]["factIds"][0])
            return True

        def fabricated(p):
            p["sentences"][0]["factIds"].append("f999")
            return True

        for label, mutate in (
                ("crossGroupEntity", cross_group),
                ("globalFactId", global_fact),
                ("unknownEntity", unknown),
                ("wrongMention", wrong_name),
                ("droppedFact", dropped),
                ("duplicatedFact", duplicated),
                ("fabricatedFact", fabricated)):
            if label == "crossGroupEntity" and not cross_entity:
                continue
            if label == "globalFactId" and not global_fid:
                continue
            if label in ("unknownEntity", "wrongMention") and not sent:
                continue
            attempt(item, label, mutate)

        per_item.append({"itemId": item["itemId"],
                         "groups": len(valid["sentences"]),
                         "crossGroupEntityAvailable": bool(cross_entity),
                         "globalFactIdAvailable": bool(global_fid)})

    detected = sum(c["detected"] for c in cases.values())
    applicable = sum(c["applicable"] for c in cases.values())
    return {
        "purpose": "mutation probe for I1/I2: a valid B1 plan is broken on purpose; every applicable mutation must be caught",
        "cases": cases,
        "controls": controls,
        "summary": {"applicable": applicable, "detected": detected,
                    "misses": len(misses)},
        "perItem": per_item,
        "misses": misses,
        "verdict": "PASS" if not misses else "FAIL",
    }


# ---- factIds consumer smoke ----------------------------------------------
def run_factids_smoke(items: list) -> dict:
    """Offline Python, frozen r3-direction checkpoint. EVIDENCE FOR THE
    FACTIDS CONSUMER PATH ONLY. Each sentence group is rendered as a flat
    fact list; coreference and group boundaries are not passed."""
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

    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.manual_seed(0)

    tokenizer = T5Tokenizer(vocab_file=str(CKPT / "spiece.model"), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(CKPT), torch_dtype=torch.float32)
    model.cuda()
    model.eval()
    smoke = {
        "purpose": "N3 factIds consumer smoke (offline Python, frozen r3-direction checkpoint)",
        "inputMode": ("each B1 sentence group is passed to n4_render.render_input() "
                      "as a flat fact list; coreference/group boundaries are NOT "
                      "passed to N4"),
        "notTested": [
            "coreference consumption: render_input() has no coreference parameter",
            "cross-group coherence: groups are rendered independently",
            "N4 quality: this is not N4 evidence; the sealed holdout was not used",
            "browser execution: offline Python only",
        ],
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "cuda": torch.version.cuda,
            "cudnn": torch.backends.cudnn.version(),
            "deviceName": torch.cuda.get_device_name(0),
            "determinism": {
                "cudnn.deterministic": torch.backends.cudnn.deterministic,
                "cudnn.benchmark": torch.backends.cudnn.benchmark,
                "torch.manual_seed": 0,
            },
        },
        "provenance": {
            "items": sha_file(ITEMS),
            "frozenRenderer": corpus_hashes()["n4_render.py"],
            "checkpoint": {f.name: sha_file(f)[:16]
                           for f in sorted(CKPT.iterdir()) if f.is_file()},
            "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "generatedFromCommit": git_commit(),
        },
        "groups": [],
        "disclaimers": [
            "consumer-path smoke ONLY; not N4 evidence; sealed holdout untouched",
            "factIds only: coreference is advisory and has no downstream consumer yet",
            "one group per render; cross-group coherence is untested",
        ],
    }
    for item in items:
        names = names_of(item)
        selected = selected_of(item)
        plan = plan_b1(selected, names)
        for sentence in plan["sentences"]:
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
    walls = [g["wallSeconds"] for g in smoke["groups"]]
    smoke["summary"] = {"groups": len(walls),
                        "meanWall": round(sum(walls) / len(walls), 2) if walls else None,
                        "maxWall": max(walls) if walls else None}
    return smoke


def main() -> None:
    skip_smoke = "--skip-smoke" in sys.argv
    smoke_only = "--smoke-only" in sys.argv
    do_tamper = "--tamper" in sys.argv
    if skip_smoke and smoke_only:
        sys.exit("--skip-smoke and --smoke-only are mutually exclusive")
    items = load_items()
    assert len(items) == 16 and all(r.get("batch") == "v2" for r in items)

    if not smoke_only:
        per_item, problems = build_all(items)
        if problems:
            print("REPORT VOID — invariance violations:")
            for x in problems:
                print(" ", x)
            sys.exit(2)
        print("invariance PASS: I1 coverage, I2 referent anchoring, I3 B1 order")

        tamper = run_tamper(items) if do_tamper else None
        if tamper:
            print(f"tamper probe: {tamper['verdict']} — "
                  f"{tamper['summary']['detected']}/{tamper['summary']['applicable']} "
                  f"applicable mutations caught; valid controls "
                  f"{tamper['controls']['zeroProblems']}/{tamper['controls']['validPlans']} clean")
            if tamper["verdict"] != "PASS":
                sys.exit(2)

        b1_total = sum(e["B1"]["stats"]["groups"] for e in per_item)
        b2_total = sum(e["B2"]["stats"]["groups"] for e in per_item)
        report = {
            "purpose": "N3 structured organisation-plan baselines r1 (B1/B2), deterministic program arms",
            "planShape": "sentences[{index, factIds, coreference[{mention, refersTo}]}]; no prose (prose stays in N4)",
            "selection": {"source": "v2 program target (items.jsonl)",
                          "note": "not an N2 model output",
                          "v3Gate": ("pending D1 annotation; if v3 vs v2 must differs "
                                    "by more than 2/16 items, these 16 inputs are rebuilt")},
            "metricScope": ("structural stats only. H1/H2/G1-G4 are MODEL-ARM metrics "
                            "and are not computed here; the earlier ①–⑤ list is "
                            "superseded by the joint decisions D1/D2. No coreference "
                            "antecedent score and no readability score is claimed."),
            "provenance": {"items": sha_file(ITEMS),
                           "code": {"n3_plan.py": sha_file(HERE / "n3_plan.py"),
                                    "run_n3_baselines.py": sha_file(pathlib.Path(__file__))},
                           "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                           "generatedFromCommit": git_commit()},
            "summary": {"items": len(items),
                        "b1GroupsTotal": b1_total, "b2GroupsTotal": b2_total,
                        "b1FactsPerGroupMean": round(sum(e["B1"]["stats"]["factsPerGroupMean"] for e in per_item) / len(items), 2),
                        "invariantViolations": 0,
                        "tamperVerdict": tamper["verdict"] if tamper else None},
            "items": per_item,
            "tamper": tamper,
            "smoke": {"archive": str(SMOKE_REPORT.relative_to(REPO)),
                      "generatedThisRun": not skip_smoke,
                      "note": "factIds consumer smoke only; see the separate archive"},
            "disclaimers": [
                "B1/B2 are program baselines: their grouping/order numbers are guarantees, not achievements",
                "model arms for N3 are NOT run yet; the baselines are the numbers they must beat",
                "coreference suggestions are NAMES only; no pronoun is generated and N4 does not consume coreference",
                "significance target definition inherits N2's open question (human confirmation pending)",
            ],
        }
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"B1 groups {b1_total} / B2 groups {b2_total} over {len(items)} items; "
              f"B1 facts/group mean {report['summary']['b1FactsPerGroupMean']}")
        print(f"report -> {REPORT}")

    if not skip_smoke:
        smoke = run_factids_smoke(items)
        SMOKE_REPORT.parent.mkdir(parents=True, exist_ok=True)
        SMOKE_REPORT.write_text(json.dumps(smoke, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"factIds consumer smoke: {smoke['summary']['groups']} group renders, "
              f"mean {smoke['summary']['meanWall']}s -> {SMOKE_REPORT}")


if __name__ == "__main__":
    main()

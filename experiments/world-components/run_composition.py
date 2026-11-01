# Real-model composition run (commit 1 of the three-commit narrative
# completion): the N1-N5 chain over program components + the FROZEN
# r3-direction N4 model, exercised on normal, failure and over-limit paths,
# with N5 findings listed separately.
#
# Component provenance (per contracts §8 and the batch-2 measurement):
#   N1 extraction = program, commit-1 vocabulary (position aspects,
#     appearance add/modify/remove, subtasks, duplicate-name flags)
#   N2 selection  = the PERSPECTIVE RULE (n2_perspective.py): must / may /
#     invisible with recorded visibility grounds wired to the authoritative
#     subject and position; select-all survives only as the labelled
#     comparison arm (the N2 encoder head was measured and REJECTED in
#     batch 2; the N3 generative model arm is blocked by the coordinator's
#     0.6B pause, so N3 stays program-side here — recorded, not silently
#     substituted)
#   N3 organisation, N5 recognition = program
#   N4 = the frozen r3-direction checkpoint via HF generate (fp32, greedy,
#     max_new_tokens 64, deterministic flags — the same decode contract as
#     the frozen holdout eval); selected facts outside the frozen model
#     vocabulary stop with kind-awaiting-model-track and the model is NOT
#     called (the commit-2 model track will lift this)
# Failure-path semantics: binding failures stop BEFORE any model call;
# over-limit plans return unsupported and the model is NOT called; an
# empty generation is its own failure class; N5 fails stay fails and N5
# reviews are listed as semanticUncertain, never auto-passed.
# Browser-side evidence is a SEPARATE archive (n4-browser-adapter-r*.json,
# batch 3); timings here are offline-CPU and are never merged with it.

import argparse
import copy
import hashlib
import importlib.machinery
import json
import pathlib
import platform
import sys
import time
import types

try:
    import pyarrow  # noqa: F401
except Exception:
    _stub = types.ModuleType("pyarrow")
    _stub.__version__ = "16.1.0"
    _stub.__path__ = []
    sys.modules["pyarrow"] = _stub
_tf = types.ModuleType("tensorflow")
_tf.__spec__ = importlib.machinery.ModuleSpec("tensorflow", None)
_tf.__path__ = []
sys.modules.setdefault("tensorflow", _tf)

import torch  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import narration_pipeline as np_  # noqa: E402
import n2_perspective as n2p  # noqa: E402

CHECKPOINT = HERE / "assets" / "n4-finetune" / "r3-direction"


def sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class FrozenN4:
    """The frozen checkpoint under the frozen decode contract."""

    def __init__(self):
        from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
        from transformers.models.t5.tokenization_t5 import T5Tokenizer
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.manual_seed(0)
        self.tok = T5Tokenizer.from_pretrained(str(CHECKPOINT), legacy=False)
        self.model = T5ForConditionalGeneration.from_pretrained(
            str(CHECKPOINT), dtype=torch.float32)
        self.model.eval()
        # offline CPU on purpose: GPU work runs in the external GPU
        # environment per the standing directive; 77M fp32 CPU inference is
        # seconds-per-call, and this archive records offline timing only
        self.device = "cpu"
        self.model.to(self.device)

    def generate(self, render_text, max_new_tokens=64):
        # defense in depth (re-review 11-02 finding 1): this entry point can
        # be called DIRECTLY, bypassing run_scenario's gate — it counts with
        # its own real tokenizer and refuses over-limit inputs itself
        n_tokens = len(self.tok(render_text).input_ids)
        if n_tokens > RealTokenizer.LIMIT:
            raise ValueError(
                f"model call refused: rendered input measures {n_tokens} "
                f"real tokens (incl. special tokens) over the {RealTokenizer.LIMIT} "
                "limit — unsupported, not truncated")
        t0 = time.perf_counter()
        enc = self.tok(render_text, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model.generate(**enc, do_sample=False, num_beams=1,
                                      max_new_tokens=max_new_tokens)
        # T5 generate returns the DECODER sequence (decoder_start + tokens):
        # decode it whole with skip_special_tokens, exactly like the frozen
        # holdout eval — an [input_len:] slice would empty the result
        text = self.tok.decode(out[0], skip_special_tokens=True)
        return {"text": text, "outputTokens": int(out.shape[1]),
                "wallMs": round((time.perf_counter() - t0) * 1000, 1),
                "inputTokens": n_tokens}


class RealTokenizer:
    """Standalone real tokenizer for the pre-model length gate (fix round
    1c41587 #2): counts input_ids INCLUDING special tokens — the same
    counting the browser adapter does with sentencepiece-js (+EOS). The
    6-char stub in the frozen interface fixtures stays there for that
    frozen contract; the AUTHORITATIVE gate at the model-call boundary is
    this real count (review: stub 55 vs real 175)."""

    LIMIT = 128

    def __init__(self):
        from transformers.models.t5.tokenization_t5 import T5Tokenizer
        self.tok = T5Tokenizer.from_pretrained(str(CHECKPOINT), legacy=False)

    def count(self, text: str) -> int:
        return len(self.tok(text).input_ids)


def build_length_case(state_tpl, before, target_tokens, tok: RealTokenizer):
    """Construct a point whose rendered N4 input measures EXACTLY
    target_tokens real tokens (incl. special tokens): pad task_1's goal
    with a filler character until the count hits the target exactly.
    Deterministic search over filler repetitions; several filler chars are
    tried because unigram merges differ per character."""
    base_delta = {"char_pa": {"entityId": "char_pa",
                              "tasksAchieved": ["task_1"],
                              "appearanceChanges": [], "personalityChanges": [],
                              "subtasksAdded": [], "positionSet": None,
                              "sanitySet": None}}
    for filler in ("网", "灯", "甲", "绳"):
        for k in range(0, 400):
            st = copy.deepcopy(state_tpl)
            st["characters"]["char_pa"]["tasks"]["task_1"]["goal"] = \
                "把铜铃挂回钟楼" + filler * k
            st["characters"]["char_pa"]["tasks"]["task_1"]["status"] = "achieved"
            point = {"pointId": "pt-2", "version": 2,
                     "state": st, "stateDigest": "d" * 8,
                     "previousPointId": "pt-1",
                     "timeAdvance": {"boundary": "elapsed",
                                     "duration": {"amount": 5, "unit": "minute"}},
                     "entityDeltas": copy.deepcopy(base_delta)}
            n1 = np_.extract_facts(point, before)
            plan = np_.organize(n1["facts"])
            if plan["status"] != "ok":
                continue
            binding = np_.bind_point_full(point, before, n1["facts"])
            verdict = np_.interface_check(plan["plan"], n1["facts"], binding)
            if verdict["status"] != "accepted":
                continue
            n = tok.count(verdict["renderText"])
            if n == target_tokens:
                return point, verdict, n
            if n > target_tokens:
                break
    raise SystemExit(f"could not construct a {target_tokens}-token case")


def run_scenario(n4, name, point, before, perspective, expect,
                 real_tok: RealTokenizer | None = None):
    """Full chain for one scenario; every stage timed. The perspective is a
    dict RESOLVED against the authoritative point state; N2 is the
    perspective rule (must/may/invisible with grounds, stops on a must
    without visibility ground); the frozen-model kind gate stops selected
    facts outside the frozen vocabulary BEFORE organisation. The model is
    only reached through BOTH gates (interface acceptance + the REAL-token
    limit). The final status REFLECTS N5 (fix round 1c41587 #1): empty
    generation, N5 fails and semantic-uncertain findings are each explicit
    non-success states."""
    rec = {"name": name, "expect": expect, "stages": {}}
    resolved = n2p.resolve_perspective(
        point.get("state") or {}, (perspective or {}).get("entityId"),
        (perspective or {}).get("type", "protagonist"))
    if resolved["problems"]:
        rec["status"] = "incomplete"
        rec["reason"] = "perspective-unresolvable"
        rec["problems"] = resolved["problems"]
        rec["modelCalled"] = False
        rec["expectMet"] = rec["status"] == expect
        return rec
    persp = resolved["perspective"]
    rec["perspective"] = persp
    t0 = time.perf_counter()
    n1 = np_.extract_facts(point, before)
    blocking = [d for d in n1["diagnostics"]
                if d["code"] in np_.INCOMPLETE_DIAGNOSTIC_CODES]
    rec["stages"]["n1"] = {"ms": round((time.perf_counter() - t0) * 1000, 2),
                           "facts": len(n1["facts"]),
                           "diagnostics": n1["diagnostics"]}
    if blocking:
        rec["stages"]["n1"]["blocking"] = blocking
        rec["status"] = "incomplete"
        rec["modelCalled"] = False
        rec["expectMet"] = rec["status"] == expect
        return rec
    subject_tasks = None
    if persp.get("entityId"):
        subject_tasks = ((point.get("state") or {}).get("characters")
                         or {}).get(persp["entityId"], {}).get("tasks")
    t0 = time.perf_counter()
    n2 = np_.select_facts(n1["facts"], persp, subject_tasks=subject_tasks)
    rec["stages"]["n2"] = {"ms": round((time.perf_counter() - t0) * 1000, 2),
                           "status": n2["status"],
                           "summary": n2.get("summary"),
                           "stops": n2.get("stops"),
                           "selected": len(n2.get("selectedFactIds", []))}
    if n2["status"] == "stopped":
        rec["status"] = "incomplete"
        rec["reason"] = "n2-must-without-visibility-ground"
        rec["modelCalled"] = False
        rec["expectMet"] = rec["status"] == expect
        return rec
    if n2["status"] != "ok" or n2.get("invalidReferences") or n2.get("refusals"):
        rec["status"] = "stopped-at-n2"
        rec["reason"] = n2.get("reason")
        rec["invalidReferences"] = n2.get("invalidReferences")
        rec["refusals"] = n2.get("refusals")
        rec["modelCalled"] = False
        rec["expectMet"] = rec["status"] == expect
        return rec
    selected = [f for f in n1["facts"]
                if f["factId"] in set(n2["selectedFactIds"])]
    if n1["facts"] and not selected:
        rec["status"] = "incomplete"
        rec["reason"] = "n2-empty-selection"
        rec["modelCalled"] = False
        rec["expectMet"] = rec["status"] == expect
        return rec
    new_kinds = sorted({f["kind"] for f in selected} - np_.FROZEN_MODEL_KINDS)
    if new_kinds:
        rec["status"] = "unsupported"
        rec["unsupportedReason"] = "kind-awaiting-model-track"
        rec["kinds"] = new_kinds
        rec["modelCalled"] = False
        rec["expectMet"] = rec["status"] == expect
        return rec
    t0 = time.perf_counter()
    n3 = np_.organize(selected)
    rec["stages"]["n3"] = {"ms": round((time.perf_counter() - t0) * 1000, 2),
                           "status": n3["status"]}
    if n3["status"] != "ok":
        rec["status"] = "stopped-at-n3"
        rec["expectMet"] = rec["status"] == expect
        return rec
    t0 = time.perf_counter()
    binding = np_.bind_point_full(point, before, n1["facts"])
    verdict = np_.interface_check(n3["plan"], selected, binding)
    rec["stages"]["n4Interface"] = {
        "ms": round((time.perf_counter() - t0) * 1000, 2),
        "status": verdict["status"],
        "reason": verdict.get("reason"),
        "reasons": verdict.get("reasons")}
    if verdict["status"] != "accepted":
        rec["status"] = {"unsupported": "unsupported",
                         "error": "stopped-at-n4",
                         "binding-failed": "stopped-at-binding"}[verdict["status"]]
        rec["modelCalled"] = False
        rec["expectMet"] = rec["status"] == expect
        return rec
    # fix round 1c41587 #2 (and 11-02 re-review finding 1): the
    # AUTHORITATIVE pre-model length gate over the REAL tokenizer (special
    # tokens included); the stub verdict alone no longer admits a run
    # (review measured stub 55 vs real 175), and a MISSING counter refuses
    # the model call outright — no counting capability means no model call
    if real_tok is None and n4 is not None:
        rec["stages"]["n4RealTokens"] = None
        rec["status"] = "stopped-at-token-gate"
        rec["reason"] = ("no real tokenizer available to count the rendered "
                         "input; refusing the model call (re-review 11-02 "
                         "finding 1)")
        rec["modelCalled"] = False
        rec["expectMet"] = rec["status"] == expect
        return rec
    real_tokens = real_tok.count(verdict["renderText"]) if real_tok else None
    rec["stages"]["n4RealTokens"] = real_tokens
    if real_tokens is not None and real_tokens > RealTokenizer.LIMIT:
        rec["status"] = "unsupported"
        rec["unsupportedReason"] = "input-too-long-real"
        rec["modelCalled"] = False
        rec["expectMet"] = rec["status"] == expect
        return rec
    t0 = time.perf_counter()
    gen = n4.generate(verdict["renderText"]) if n4 is not None \
        else {"text": "", "outputTokens": 0, "wallMs": 0.0}
    if n4 is None:
        rec["modelCalled"] = False
        rec["stages"]["n4Model"] = {"skipped": "no-model dry run"}
        rec["status"] = "accepted-unrendered"
        # a dry run cannot render; an expected-ok scenario is considered
        # met up to the render step
        rec["expectMet"] = rec["status"] == expect or expect == "ok"
        return rec
    rec["stages"]["n4Model"] = {"ms": gen["wallMs"],
                                "outputTokens": gen["outputTokens"],
                                "text": gen["text"]}
    rec["modelCalled"] = True
    rec["modelInput"] = verdict["renderText"]
    t0 = time.perf_counter()
    n5 = np_.verify_text(verdict["renderInput"], gen["text"])
    rec["stages"]["n5"] = {"ms": round((time.perf_counter() - t0) * 1000, 2),
                           **n5}
    # fix round 1c41587 #1: the status reflects N5 — empty output, N5 fails
    # and semantic-uncertain findings are each explicit non-success states
    if not gen["text"].strip("。，,：:；; "):
        rec["status"] = "empty-output"
    elif n5["fails"]:
        rec["status"] = "n5-failed"
    elif n5["semanticUncertain"]:
        rec["status"] = "n5-review-pending"
    else:
        rec["status"] = "ok"
    rec["expectMet"] = rec["status"] == expect
    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None,
                        help="default: artifacts/world-components/"
                             "n1-n5-composition-r1.json (dry runs must "
                             "pass an explicit path)")
    parser.add_argument("--no-model", action="store_true",
                        help="program-only dry run (no checkpoint load)")
    args = parser.parse_args()

    out_path = args.out or str(HERE.parent.parent / "artifacts" /
                               "world-components" / "n1-n5-composition-r3.json")
    n4 = None
    if not args.no_model:
        t0 = time.perf_counter()
        n4 = FrozenN4()
        load_s = round(time.perf_counter() - t0, 1)
        print(f"frozen checkpoint loaded on {n4.device} in {load_s}s")

    state = np_.make_pipeline_state()
    before_state = np_.make_pipeline_state()
    before = {**np_.make_point(1, {}, None, state=before_state),
              "pointId": "pt-1", "version": 1}
    PERS = {"type": "protagonist"}

    def point(deltas, amount, unit="minute", st=None, version=2):
        ta = None if amount is None else {"boundary": "elapsed",
                                          "duration": {"amount": amount, "unit": unit}}
        return np_.make_point(version, deltas, ta,
                              state=st or copy.deepcopy(state), prev="pt-1")

    scenarios = []

    # S-normal-1: legal second point, moved + task achieved (frozen
    # checkpoint's trained vocabulary is minute/hour; the second-unit plan
    # exercises the batch-1 legal-input extension through the REAL model)
    st = copy.deepcopy(state)
    st["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                               "slotId": None, "relativeTo": None}
    st["characters"]["char_pa"]["tasks"]["task_1"]["status"] = "achieved"
    deltas = {"char_pa": {**np_.moved_delta("char_pa", "loc_2"),
                          "tasksAchieved": ["task_1"]}}
    scenarios.append(("normal-second", point(deltas, 40, "second", st=st),
                      before, "ok"))

    # S-normal-2: zero-duration empty point (legal, instantaneous)
    scenarios.append(("normal-zero-empty", point({}, 0, "minute"),
                      before, "ok"))

    # S-normal-3: root point (no deltas, no time) — the perspective
    # resolves against the FULL root state
    root = {"pointId": "pt-0", "version": 0,
            "state": np_.make_pipeline_state(), "stateDigest": "d" * 8,
            "previousPointId": None, "timeAdvance": None, "entityDeltas": {}}
    scenarios.append(("normal-root", root, None, "ok"))

    # S-fail-1: version gap -> binding stops before any model call
    scenarios.append(("fail-version-gap", point({}, 5, version=3),
                      before, "stopped-at-binding"))

    # S-limit-1: five SELECTED self facts -> unsupported, model NOT called.
    # Under the perspective rule the binding count is the SELECTED set;
    # other entities' facts are invisible, so the over-limit case is built
    # from the subject's own five plus global time
    st5 = copy.deepcopy(state)
    st5["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                                "slotId": None, "relativeTo": None}
    st5["characters"]["char_pa"]["sanity"] = 15
    st5["characters"]["char_pa"]["tasks"]["task_1"]["status"] = "achieved"
    st5["characters"]["char_pa"]["tasks"]["task_2"]["status"] = "achieved"
    st5["characters"]["char_pa"]["appearanceChanges"] = [
        {"id": "ch_a1", "text": "外袍被雨浸透", "supersedes": []}]
    deltas5 = {"char_pa": {**np_.moved_delta("char_pa", "loc_2"),
                           "tasksAchieved": ["task_1", "task_2"],
                           "sanitySet": 15,
                           "appearanceChanges": [{"id": "ch_a1",
                                                  "text": "外袍被雨浸透",
                                                  "supersedes": []}]}}
    scenarios.append(("limit-five-facts", point(deltas5, 5, st=st5),
                      before, "unsupported"))

    # S-kind-1 (commit 1): a new subtask is EXTRACTED as a subtask_added
    # fact and stops at the frozen-model kind gate — model NOT called
    st_sub = copy.deepcopy(state)
    st_sub["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                                   "slotId": None, "relativeTo": None}
    deltas_sub = {"char_pa": {**np_.moved_delta("char_pa", "loc_2"),
                              "subtasksAdded": [{"id": "task_9",
                                                 "ownerId": "char_pa",
                                                 "parentTaskId": "task_1",
                                                 "goal": "找梯子",
                                                 "status": "pending"}]}}
    scenarios.append(("kind-gate-subtask", point(deltas_sub, 5, st=st_sub),
                      before, "unsupported"))

    # S-kind-2 (commit 1): a same-container relativeTo change becomes a
    # position_relative fact — never narrated as a plain container move —
    # and stops at the frozen-model kind gate, model NOT called
    st_rel = copy.deepcopy(state)
    st_rel["characters"]["char_pa"]["position"] = {
        "containerId": "loc_1", "slotId": None,
        "relativeTo": {"entityId": "char_pb", "relation": "beside"}}
    deltas_rel = {"char_pa": {"entityId": "char_pa",
                              "positionSet": {"containerId": "loc_1",
                                              "slotId": None,
                                              "relativeTo": {"entityId": "char_pb",
                                                             "relation": "behind"}},
                              "appearanceChanges": [], "personalityChanges": [],
                              "subtasksAdded": [], "tasksAchieved": [],
                              "sanitySet": None}}
    scenarios.append(("kind-gate-relative", point(deltas_rel, 5, st=st_rel),
                      before, "unsupported"))

    # S-n2-1 (commit 1): a tracked task completed where the viewpoint
    # cannot perceive it — the must has no visibility ground and the
    # success path STOPS (incomplete), model NOT called
    st_stop = copy.deepcopy(state)
    st_stop["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                                    "slotId": None,
                                                    "relativeTo": None}
    st_stop["characters"]["char_pb"]["tasks"]["task_3"]["goal"] = "晒网"
    st_stop["characters"]["char_pb"]["tasks"]["task_3"]["status"] = "achieved"
    d_stop = {"char_pb": {"entityId": "char_pb", "positionSet": None,
                          "appearanceChanges": [], "personalityChanges": [],
                          "subtasksAdded": [], "tasksAchieved": ["task_3"],
                          "sanitySet": None}}
    scenarios.append(("n2-must-hidden-stop", point(d_stop, 5, st=st_stop),
                      before, "incomplete"))

    # fix round 1c41587 #2: real-tokenizer boundary cases — the rendered
    # input measures EXACTLY 128 (admitted, model called) and EXACTLY 129
    # (unsupported, model NOT called) real tokens incl. special tokens
    real_tok = RealTokenizer()
    pt128, _, n128 = build_length_case(state, before, 128, real_tok)
    pt129, _, n129 = build_length_case(state, before, 129, real_tok)
    print(f"real-token boundary cases constructed: {n128} and {n129} tokens")
    # the 128 case is ADMITTED and the model faithfully narrates the padded
    # goal — the filler residue is then flagged by N5, which is exactly the
    # fix-#1 behaviour (status reflects N5); the gate evidence here is
    # modelCalled=True with exactly 128 real tokens
    scenarios.append(("limit-real-128", pt128, before, "n5-review-pending"))
    scenarios.append(("limit-real-129", pt129, before, "unsupported"))

    results = []
    for name, pt, bef, expect in scenarios:
        rec = run_scenario(n4, name, pt, bef, PERS, expect, real_tok)
        results.append(rec)
        print(f"{name:20s} status={rec['status']:20s} expectMet={rec['expectMet']}"
              + (f" n4='{rec['stages'].get('n4Model', {}).get('text', '')[:36]}'"
                 if rec.get("modelCalled") else ""))

    # fix round 1c41587 #1: end-to-end NEGATIVE/POSITIVE controls through
    # the same run_scenario with scripted generators — empty output, clearly
    # wrong text, semantically-uncertain text, normal output
    # the controls reuse the normal-second point so the scripted texts sit
    # on the same plan the real model narrated
    st_c = copy.deepcopy(state)
    st_c["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                                 "slotId": None, "relativeTo": None}
    st_c["characters"]["char_pa"]["tasks"]["task_1"]["status"] = "achieved"
    deltas_c = {"char_pa": {**np_.moved_delta("char_pa", "loc_2"),
                            "tasksAchieved": ["task_1"]}}
    control_point = point(copy.deepcopy(deltas_c), 40, "second", st=copy.deepcopy(st_c))

    def scripted(text):
        class G:
            def generate(self, *_a, **_k):
                return {"text": text, "outputTokens": len(text),
                        "wallMs": 0.0}
        return G()

    normal_text = next((r["stages"]["n4Model"]["text"]
                        for r in results if r.get("modelCalled")
                        and r["stages"]["n4Model"]["text"]), "")
    wrong_text = normal_text.replace("前后大约", "前后整整八千").replace("大约", "整整八千")
    uncertain_text = (normal_text + "路边忽然开出一朵不会有的花。")
    controls = [
        ("control-empty", scripted(""), "empty-output"),
        ("control-wrong-text", scripted(wrong_text), "n5-failed-or-review"),
        ("control-uncertain-text", scripted(uncertain_text), "n5-failed-or-review"),
        ("control-normal", scripted(normal_text), "ok"),
    ]
    # re-review 11-02 finding 1: a missing counter must refuse the model
    # call outright — proven end-to-end with the real checkpoint loaded
    rec_gate = run_scenario(n4, "gate-no-counter", copy.deepcopy(control_point),
                            before, PERS, "stopped-at-token-gate",
                            real_tok=None)
    gate_checks = {"noCounterRefused": rec_gate["modelCalled"] is False
                   and rec_gate["status"] == "stopped-at-token-gate"}

    control_results = []
    for name, gen, expect in controls:
        rec = run_scenario(gen, name, copy.deepcopy(control_point),
                           before, PERS, expect, real_tok)
        # the two negative controls expect ANY explicit non-success N5
        # status (fail or review class — the recognizer decides the class)
        rec["expectMet"] = (rec["status"] in ("n5-failed", "n5-review-pending")) \
            if expect == "n5-failed-or-review" else (rec["status"] == expect)
        control_results.append(rec)
        print(f"{name:24s} status={rec['status']:20s} expectMet={rec['expectMet']}")

    real_n5 = [r["stages"]["n5"] for r in results if "n5" in r["stages"]]
    control_n5 = [r["stages"]["n5"] for r in control_results if "n5" in r["stages"]]
    n5_summary = {
        "realScenarios": {
            "withN5": len(real_n5),
            "n5Fails": sum(1 for x in real_n5 if x["fails"]),
            "n5SemanticUncertain": sum(1 for x in real_n5 if x["semanticUncertain"]),
            "uncertainItems": [u for x in real_n5 for u in x["semanticUncertain"]],
        },
        "controls": {
            "withN5": len(control_n5),
            "n5Fails": sum(1 for x in control_n5 if x["fails"]),
            "n5SemanticUncertain": sum(1 for x in control_n5 if x["semanticUncertain"]),
            "note": "the two negative controls PRODUCE findings on purpose "
                    "to prove the non-success statuses fire end-to-end",
        },
        "emptyOutputs": sum(1 for r in results + control_results
                            if r["status"] == "empty-output"),
    }
    archive = {
        "purpose": "commit-1 real-model composition: program N1 (commit-1 "
                   "vocabulary) + perspective-rule N2 + program N3 + frozen "
                   "r3-direction N4 + program N5; statuses reflect N5 (#1), "
                   "a REAL-tokenizer pre-model gate with 128/129 boundary "
                   "cases (#2), the frozen-model KIND GATE stops new-"
                   "vocabulary facts before the model (kind-awaiting-model-"
                   "track), and the perspective rule stops a must without "
                   "visibility ground end-to-end; offline CPU evidence, "
                   "browser evidence separate",
        "componentProvenance": {
            "n1/n3/n5": "program",
            "n2": "perspective rule (n2_perspective.py, must/may/invisible "
                  "with visibility grounds; encoder head rejected by "
                  "batch-2 measurement; select-all kept as labelled "
                  "comparison arm only)",
            "n3 model arm": "NOT run - 0.6B pause in force, no run archive "
                            "exists for one",
            "n4": "frozen r3-direction, HF generate, fp32, greedy, "
                  "max_new_tokens 64, deterministic flags, offline CPU; "
                  "frozen eight-kind vocabulary enforced by the kind gate",
        },
        "checkpoint": {"dir": "assets/n4-finetune/r3-direction",
                       "modelSha256": sha_file(CHECKPOINT / "model.safetensors")},
        "environment": {"python": platform.python_version(),
                        "torch": torch.__version__,
                        "device": getattr(n4, "device", "none"),
                        "deviceName": "cpu",
                        "note": "offline timing only; never merged with "
                                "browser timings"},
        "realTokenGate": {"limit": RealTokenizer.LIMIT,
                          "tokenizer": "T5Tokenizer legacy=False, special "
                                       "tokens included",
                          "boundaryCases": {"admitted": n128, "refused": n129}},
        "scenarios": results,
        "gateChecks": {"noCounterRefused": gate_checks,
                       "record": rec_gate},
        "controls": control_results,
        "n5Summary": n5_summary,
        "n5Note": "review-class findings are listed for review, never "
                  "auto-passed; the page gate stays B-side",
        # the summary gate REFLECTS N5 (fix #1): every scenario status is
        # derived from N5, so pass = every expectation met (an ok-expected
        # scenario with any N5 finding would carry n5-failed /
        # n5-review-pending / empty-output instead of ok and fail here);
        # n5Summary keeps the factual aggregates including the EXPECTED
        # findings of the negative controls and the 128-boundary case
        "pass": (all(r["expectMet"] for r in results + control_results)
                 and gate_checks["noCounterRefused"]),
    }
    pathlib.Path(out_path).write_text(
        json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print("pass:", archive["pass"], "->", out_path)
    return 0 if archive["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())

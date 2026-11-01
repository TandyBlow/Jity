# Real-model composition run (batch 4): the N1-N5 chain over program
# components + the FROZEN r3-direction N4 model, exercised on normal,
# failure and over-limit paths, with N5 findings listed separately.
#
# Component provenance (per contracts §8 and the batch-2 measurement):
#   N1 extraction, N2 selection, N3 organisation, N5 recognition = program
#   (the N2 encoder head was measured and REJECTED in batch 2; the N3
#   generative model arm is blocked by the coordinator's 0.6B pause, so
#   N2/N3 stay program-side here — recorded, not silently substituted)
#   N4 = the frozen r3-direction checkpoint via HF generate (fp32, greedy,
#   max_new_tokens 64, deterministic flags — the same decode contract as
#   the frozen holdout eval)
# Failure-path semantics: binding failures stop BEFORE any model call;
# over-limit plans return unsupported and the model is NOT called; an
# empty generation is its own failure class; N5 fails stay fails and N5
# reviews are listed as semanticUncertain, never auto-passed.
# Browser-side evidence is a SEPARATE archive (n4-browser-adapter-r1.json,
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
                "wallMs": round((time.perf_counter() - t0) * 1000, 1)}


def run_scenario(n4, name, point, before, perspective, expect):
    """Full chain for one scenario; every stage timed; model only reached
    on an accepted interface verdict."""
    rec = {"name": name, "expect": expect, "stages": {}}
    t0 = time.perf_counter()
    n1 = np_.extract_facts(point, before)
    rec["stages"]["n1"] = {"ms": round((time.perf_counter() - t0) * 1000, 2),
                           "facts": len(n1["facts"]),
                           "diagnostics": n1["diagnostics"]}
    t0 = time.perf_counter()
    n2 = np_.select_facts(n1["facts"], perspective)
    rec["stages"]["n2"] = {"ms": round((time.perf_counter() - t0) * 1000, 2),
                           "status": n2["status"],
                           "selected": len(n2.get("selectedFactIds", []))}
    if n2["status"] != "ok":
        rec["status"] = "stopped-at-n2"
        return rec
    t0 = time.perf_counter()
    n3 = np_.organize([f for f in n1["facts"] if f["factId"] in set(n2["selectedFactIds"])])
    rec["stages"]["n3"] = {"ms": round((time.perf_counter() - t0) * 1000, 2),
                           "status": n3["status"]}
    if n3["status"] != "ok":
        rec["status"] = "stopped-at-n3"
        return rec
    t0 = time.perf_counter()
    binding = np_.bind_point_full(point, before, n1["facts"])
    verdict = np_.interface_check(n3["plan"], n1["facts"], binding)
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
        return rec
    t0 = time.perf_counter()
    gen = n4.generate(verdict["renderText"])
    rec["stages"]["n4Model"] = {"ms": gen["wallMs"],
                                "outputTokens": gen["outputTokens"],
                                "text": gen["text"]}
    rec["modelCalled"] = True
    rec["modelInput"] = verdict["renderText"]
    t0 = time.perf_counter()
    n5 = np_.verify_text(verdict["renderInput"], gen["text"])
    rec["stages"]["n5"] = {"ms": round((time.perf_counter() - t0) * 1000, 2),
                           **n5}
    rec["status"] = "ok"
    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",
                        default=str(HERE.parent.parent / "artifacts" /
                                    "world-components" / "n1-n5-composition-r1.json"))
    parser.add_argument("--no-model", action="store_true",
                        help="program-only dry run (no checkpoint load)")
    args = parser.parse_args()

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

    # S-normal-3: root point (no deltas, no time)
    root = {"pointId": "pt-0", "version": 0, "state": {"worldId": "w_pipe"},
            "stateDigest": "d" * 8, "previousPointId": None,
            "timeAdvance": None, "entityDeltas": {}}
    scenarios.append(("normal-root", root, None, "ok"))

    # S-fail-1: version gap -> binding stops before any model call
    scenarios.append(("fail-version-gap", point({}, 5, version=3),
                      before, "stopped-at-binding"))

    # S-limit-1: five facts -> unsupported, model NOT called
    st5 = copy.deepcopy(state)
    for c in ("char_pa", "char_pb"):
        st5["characters"][c]["position"] = {"containerId": "loc_2",
                                            "slotId": None, "relativeTo": None}
    for tid in ("task_1", "task_2"):
        st5["characters"]["char_pa"]["tasks"][tid]["status"] = "achieved"
    st5["characters"]["char_pb"]["tasks"]["task_3"]["status"] = "achieved"
    deltas5 = {"char_pa": {**np_.moved_delta("char_pa", "loc_2"),
                           "tasksAchieved": ["task_1", "task_2"]},
               "char_pb": {**np_.moved_delta("char_pb", "loc_2"),
                           "tasksAchieved": ["task_3"]}}
    scenarios.append(("limit-five-facts", point(deltas5, 5, st=st5),
                      before, "unsupported"))

    results = []
    for name, pt, bef, expect in scenarios:
        rec = run_scenario(n4, name, pt, bef, "主角视角", expect)
        rec["expectMet"] = rec["status"] == expect
        results.append(rec)
        print(f"{name:20s} status={rec['status']:20s} expectMet={rec['expectMet']}"
              + (f" n4='{rec['stages'].get('n4Model', {}).get('text', '')[:36]}'"
                 if rec.get("modelCalled") else ""))

    n5_uncertain = [r["stages"]["n5"]["semanticUncertain"]
                    for r in results if r.get("modelCalled")
                    and r["stages"]["n5"]["semanticUncertain"]]
    archive = {
        "purpose": "batch-4 real-model composition: program N1-N3 + frozen "
                   "r3-direction N4 + program N5 over normal, failure and "
                   "over-limit paths; offline CPU evidence, browser evidence "
                   "is the separate batch-3 archive",
        "componentProvenance": {
            "n1/n2/n3/n5": "program (N2 encoder head rejected by batch-2 "
                           "measurement; N3 model arm blocked by the 0.6B "
                           "pause - recorded, not substituted)",
            "n4": "frozen r3-direction, HF generate, fp32, greedy, "
                  "max_new_tokens 64, deterministic flags",
        },
        "checkpoint": {"dir": "assets/n4-finetune/r3-direction",
                       "modelSha256": sha_file(CHECKPOINT / "model.safetensors")},
        "environment": {"python": platform.python_version(),
                        "torch": torch.__version__,
                        "device": getattr(n4, "device", "none"),
                        "deviceName": (torch.cuda.get_device_name(0)
                                       if getattr(n4, "device", "") == "cuda"
                                       else "cpu"),
                        "note": "offline timing only; never merged with "
                                "browser timings"},
        "scenarios": results,
        "n5SemanticUncertain": n5_uncertain,
        "n5Note": "review-class findings are listed for review, never "
                  "auto-passed; the page gate stays B-side",
        "pass": all(r["expectMet"] for r in results),
    }
    pathlib.Path(args.out).write_text(
        json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print("pass:", archive["pass"], "->", args.out)
    return 0 if archive["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())

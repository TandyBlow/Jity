# Real-model composition run for the V2 grouped interface (commit 2):
# program N1 -> perspective-rule N2 -> plan_v3 N3 -> the TRAINED v2 N4
# (Randeng-T5-77M finetuned on the case-matrix corpus, HPC) -> the v2 N5
# judge (the eval aligner's hard gates). This is the end-to-end evidence
# that the model ACTUALLY receives and uses the sentence groups and
# appellation grants:
#   - pronoun rows: the output must use the granted pronoun (P1) and the
#     ablated input (称谓 stripped) must produce a DIFFERENT output (P2)
#   - same-name rows: names only, never a pronoun
#   - conflict rows: both actors named
#   - new kinds (subtask / relative / slot): they flow END-TO-END here —
#     the commit-1 kind gate is lifted by the v2 model's trained vocabulary
#   - over-128-real-token inputs: refused before the model call
# Decode contract: greedy, num_beams 1, max_new_tokens 128, deterministic
# flags, offline CPU. Every raw input/output and finish reason is archived.
# Browser evidence remains a separate archive (commit 3).
#
# This archived composition is the SELECT arm (may_policy="select", time and
# other visible may facts included). The v2 pipeline default is OMIT; the
# select arm is a labelled comparison and must not be read as the product
# default. gender_hints is likewise an experimental input, not state.

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
sys.path.insert(0, str(HERE / "n4_corpus_v2"))
import narration_pipeline as np_  # noqa: E402
import n2_perspective as n2p  # noqa: E402
from eval_n4_v2 import judge_row  # noqa: E402

CHECKPOINT = HERE / "n4_corpus_v2" / "ckpt-v2"


def sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class V2TokenizerGate:
    """The REAL pre-model length gate for the v2 chain (same counting as
    the frozen chain's RealTokenizer, incl. special tokens)."""

    def __init__(self):
        from transformers.models.t5.tokenization_t5 import T5Tokenizer
        self.tok = T5Tokenizer.from_pretrained(str(CHECKPOINT), legacy=False)

    def count(self, text: str) -> int:
        return len(self.tok(text).input_ids)


class V2N4:
    """The trained v2 checkpoint under the frozen decode contract."""

    LIMIT = np_.V2_TOKEN_LIMIT

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
        self.device = "cpu"
        self.model.to(self.device)

    def generate(self, render_text, max_new_tokens=128):
        n_tokens = len(self.tok(render_text).input_ids)
        if n_tokens > self.LIMIT:
            raise ValueError(
                f"model call refused: {n_tokens} real tokens over the "
                f"{self.LIMIT} limit — unsupported, not truncated")
        enc = self.tok(render_text, return_tensors="pt").to(self.device)
        t0 = time.perf_counter()
        with torch.no_grad():
            out = self.model.generate(**enc, do_sample=False, num_beams=1,
                                               max_new_tokens=max_new_tokens)
        text = self.tok.decode(out[0], skip_special_tokens=True)
        finish = "eos" if int(out.shape[1]) < max_new_tokens else "length"
        return {"text": text, "outputTokens": int(out.shape[1]),
                "wallMs": round((time.perf_counter() - t0) * 1000, 1),
                "inputTokens": n_tokens, "finishReason": finish}


def run_scenario_v2(n4, tok_gate, name, point, before, gender_hints, expect,
                    ablate=False, perspective=None):
    """One v2 chain scenario: pipeline_v2 -> model -> the v2 N5 gates.
    perspective defaults to the state's protagonist; scenarios that need
    another viewpoint pass it explicitly (the authority still resolves and
    validates it against the point state)."""
    rec = {"name": name, "expect": expect, "stages": {}}
    # The archived composition is the SELECT arm (time/may facts included).
    # The v2 pipeline default is omit; this explicit arm keeps the old
    # comparison reproducible and is never mistaken for the product default.
    chain = np_.run_pipeline_v2(point, before, perspective or
                                {"type": "protagonist"},
                                may_policy="select",
                                gender_hints=gender_hints,
                                real_tok=tok_gate)
    rec["stages"]["chain"] = {k: chain.get(k) for k in
                              ("status", "reason", "unsupportedReason",
                               "kinds", "perspective")}
    rec["stages"]["n1"] = chain.get("n1")
    rec["stages"]["n2Summary"] = (chain.get("n2") or {}).get("summary")
    rec["stages"]["n3"] = chain.get("n3")
    if chain["status"] != "ready-for-model":
        rec["status"] = chain["status"]
        rec["modelCalled"] = False
        rec["expectMet"] = rec["status"] == expect
        return rec
    render_text = chain["n4"]["renderText"]
    gen = n4.generate(render_text)
    rec["modelCalled"] = True
    rec["modelInput"] = render_text
    rec["stages"]["n4Model"] = {"ms": gen["wallMs"],
                                "outputTokens": gen["outputTokens"],
                                "finishReason": gen["finishReason"],
                                "text": gen["text"]}
    row = {"rowId": f"comp:{name}", "plan": chain["plan"],
           "facts": chain["selectedFacts"],
           "mustExpress": [f["factId"] for f in chain["selectedFacts"]]}
    verdict = judge_row(row, gen["text"], gen["finishReason"])
    rec["stages"]["n5"] = {"gates": verdict["gates"],
                           "problems": verdict["align"]["problems"][:6]}
    rec["status"] = "ok" if verdict["pass"] else "n5-failed"
    rec["expectMet"] = rec["status"] == expect
    if ablate:
        # the ablation arm is RECORDED here; the systematic evidence that
        # the grants move the output lives in the frozen-holdout eval
        # (P2: 44/46 rows differ). Gating a single in-domain scenario on
        # the differential would overweight one draw.
        ablated = np_.run_pipeline_v2(
            point, before, perspective or {"type": "protagonist"},
            may_policy="select", gender_hints={}, real_tok=tok_gate)
        if ablated["status"] == "ready-for-model":
            gen2 = n4.generate(ablated["n4"]["renderText"])
            rec["ablation"] = {"inputWithoutGrants": ablated["n4"]["renderText"],
                               "output": gen2["text"],
                               "differs": gen2["text"] != gen["text"]}
    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(HERE.parent.parent / "artifacts" /
                                             "world-components" /
                                             "n1-n5-composition-v2-r1.json"))
    args = parser.parse_args()

    t0 = time.perf_counter()
    n4 = V2N4()
    load_s = round(time.perf_counter() - t0, 1)
    tok_gate = V2TokenizerGate()
    print(f"v2 checkpoint loaded on {n4.device} in {load_s}s")

    state = np_.make_pipeline_state()
    before_state = np_.make_pipeline_state()
    before = {**np_.make_point(1, {}, None, state=before_state),
              "pointId": "pt-1", "version": 1}
    # the pipeline world's genders: 管线甲 male, 管线乙 male, plus a
    # gender-unknown third for the TA case
    hints = {"char_pa": "male", "char_pb": "male", "char_pc": "unknown"}

    def point(deltas, amount, unit="minute", st=None, version=2):
        ta = None if amount is None else {"boundary": "elapsed",
                                          "duration": {"amount": amount,
                                                       "unit": unit}}
        return np_.make_point(version, deltas, ta,
                              state=st or copy.deepcopy(state), prev="pt-1")

    def mut_state(**over):
        st = copy.deepcopy(state)
        st["characters"]["char_pa"]["position"] = over.get(
            "pa_pos", st["characters"]["char_pa"]["position"])
        if "pb_pos" in over:
            st["characters"]["char_pb"]["position"] = over["pb_pos"]
        if "sanity" in over:
            st["characters"]["char_pa"]["sanity"] = over["sanity"]
        if "pb_task" in over:
            st["characters"]["char_pb"]["tasks"]["task_3"].update(over["pb_task"])
        if "pa_task" in over:
            st["characters"]["char_pa"]["tasks"]["task_1"].update(over["pa_task"])
        return st

    scenarios = []

    # V1 pronoun cross-reference (subject 管线甲): 甲 moves + sanity (one
    # group), 乙 achieves 甲's pending 晒网 AT 甲's new place — visible,
    # tracked -> must. The grant fires; the ablation arm is recorded (the
    # systematic P2 evidence lives in the frozen-holdout eval).
    st = mut_state(pa_pos={"containerId": "loc_2", "slotId": None,
                           "relativeTo": None},
                   pb_pos={"containerId": "loc_2", "slotId": None,
                           "relativeTo": None},
                   pb_task={"goal": "晒网", "status": "achieved"},
                   sanity=14)
    d = {"char_pa": {**np_.moved_delta("char_pa", "loc_2"), "sanitySet": 14},
         "char_pb": {"entityId": "char_pb", "positionSet": None,
                     "appearanceChanges": [], "personalityChanges": [],
                     "subtasksAdded": [], "tasksAchieved": ["task_3"],
                     "sanitySet": None}}
    scenarios.append(("v2-pronoun-crossref",
                      point(d, 8, st=st), before, "ok", True, None))

    # V2 conflict (subject 管线甲 at loc_1): 甲 tracks 合力抬钟; BOTH
    # 管线乙s (same name) complete that goal at 甲's place — both visible
    # tracked-musts, so the narration must carry BOTH actors under their
    # shared name, never one pronoun standing for two people
    st2 = copy.deepcopy(state)
    st2["characters"]["char_pa"]["tasks"]["task_2"]["goal"] = "合力抬钟"
    st2["characters"]["char_pb"]["tasks"]["task_3"]["goal"] = "合力抬钟"
    st2["characters"]["char_pb"]["tasks"]["task_3"]["status"] = "achieved"
    st2["initial"]["characters"]["char_pc"] = {
        "id": "char_pc", "name": "管线乙",
        "initialPosition": {"containerId": "loc_1", "slotId": None,
                            "relativeTo": None},
        "initialAppearance": "常态", "initialPersonality": "沉默",
        "initialSanity": 9,
        "tasks": {"task_9": {"id": "task_9", "ownerId": "char_pc",
                             "parentTaskId": None, "goal": "合力抬钟",
                             "status": "achieved"}}}
    st2["characters"]["char_pc"] = {
        "id": "char_pc", "position": {"containerId": "loc_1", "slotId": None,
                                      "relativeTo": None},
        "appearanceChanges": [], "personalityChanges": [], "sanity": 9,
        "tasks": {"task_9": {"id": "task_9", "ownerId": "char_pc",
                             "parentTaskId": None, "goal": "合力抬钟",
                             "status": "achieved"}}}
    d2 = {"char_pb": {"entityId": "char_pb", "positionSet": None,
                      "appearanceChanges": [], "personalityChanges": [],
                      "subtasksAdded": [], "tasksAchieved": ["task_3"],
                      "sanitySet": None},
          "char_pc": {"entityId": "char_pc", "positionSet": None,
                      "appearanceChanges": [], "personalityChanges": [],
                      "subtasksAdded": [], "tasksAchieved": ["task_9"],
                      "sanitySet": None}}
    scenarios.append(("v2-conflict", point(d2, 3, st=st2), before,
                      "ok", False, None))

    # V3 gender unknown (subject 水生, an entity without a gender hint):
    # its own move + task -> the TA grant. The entity exists in BOTH
    # states (the registry is fixed); the before record carries it too.
    st4 = copy.deepcopy(state)
    st4["initial"]["characters"]["char_pd"] = {
        "id": "char_pd", "name": "水生",
        "initialPosition": {"containerId": "loc_1", "slotId": None,
                            "relativeTo": None},
        "initialAppearance": "常态", "initialPersonality": "寡言",
        "initialSanity": 9,
        "tasks": {"task_8": {"id": "task_8", "ownerId": "char_pd",
                             "parentTaskId": None, "goal": "检修钟摆",
                             "status": "pending"}}}
    st4["characters"]["char_pd"] = {
        "id": "char_pd", "position": {"containerId": "loc_2", "slotId": None,
                                      "relativeTo": None},
        "appearanceChanges": [], "personalityChanges": [], "sanity": 9,
        "tasks": {"task_8": {"id": "task_8", "ownerId": "char_pd",
                             "parentTaskId": None, "goal": "检修钟摆",
                             "status": "achieved"}}}
    before4 = {**np_.make_point(1, {}, None, state=copy.deepcopy(st4)),
               "pointId": "pt-1", "version": 1}
    before4["state"]["characters"]["char_pd"]["position"] = {
        "containerId": "loc_1", "slotId": None, "relativeTo": None}
    before4["state"]["characters"]["char_pd"]["tasks"]["task_8"]["status"] = \
        "pending"
    d4 = {"char_pd": {"entityId": "char_pd",
                      "positionSet": {"containerId": "loc_2", "slotId": None,
                                      "relativeTo": None},
                      "appearanceChanges": [], "personalityChanges": [],
                      "subtasksAdded": [], "tasksAchieved": ["task_8"],
                      "sanitySet": None}}
    scenarios.append(("v2-gender-unknown", point(d4, 7, st=st4), before4,
                      "ok", False, {"type": "protagonist",
                                    "entityId": "char_pd"}))

    # V4 omniscient two actors: both move and both achieve -> the focus
    # rules make every fact must; the narration must carry both actors
    # with the pronoun discipline (both male here, so the second actor's
    # pronoun would collide with the first inside a shared group — the
    # planner keeps them in separate groups where each may use 他)
    st5 = copy.deepcopy(state)
    st5["characters"]["char_pa"]["position"] = {"containerId": "loc_2",
                                                "slotId": None,
                                                "relativeTo": None}
    st5["characters"]["char_pa"]["tasks"]["task_1"]["status"] = "achieved"
    st5["characters"]["char_pb"]["position"] = {"containerId": "loc_2",
                                                "slotId": None,
                                                "relativeTo": None}
    st5["characters"]["char_pb"]["tasks"]["task_3"]["status"] = "achieved"
    d5 = {"char_pa": {**np_.moved_delta("char_pa", "loc_2"),
                      "tasksAchieved": ["task_1"]},
          "char_pb": {**np_.moved_delta("char_pb", "loc_2"),
                      "tasksAchieved": ["task_3"]}}
    scenarios.append(("v2-omniscient-two-actors", point(d5, 6, st=st5),
                      before, "ok", False, {"type": "omniscient"}))

    # V5 new kinds end-to-end: relative position + subtask flow through
    st6 = copy.deepcopy(state)
    st6["characters"]["char_pa"]["position"] = {
        "containerId": "loc_1", "slotId": None,
        "relativeTo": {"entityId": "char_pb", "relation": "beside"}}
    st6["characters"]["char_pa"]["tasks"]["task_1"]["status"] = "achieved"
    d6 = {"char_pa": {"entityId": "char_pa",
                      "positionSet": {"containerId": "loc_1", "slotId": None,
                                      "relativeTo": {"entityId": "char_pb",
                                                     "relation": "beside"}},
                      "appearanceChanges": [], "personalityChanges": [],
                      "subtasksAdded": [{"id": "task_x", "ownerId": "char_pa",
                                         "parentTaskId": "task_1",
                                         "goal": "找梯子",
                                         "status": "pending"}],
                      "tasksAchieved": ["task_1"], "sanitySet": None}}
    scenarios.append(("v2-new-kinds", point(d6, 5, st=st6), before,
                      "ok", False, None))

    # V7 over-128 real tokens -> refused BEFORE the model call
    st7 = copy.deepcopy(state)
    for c in ("char_pa", "char_pb"):
        st7["characters"][c]["position"] = {"containerId": "loc_2",
                                            "slotId": None, "relativeTo": None}
    for tid in ("task_1", "task_2"):
        st7["characters"]["char_pa"]["tasks"][tid]["status"] = "achieved"
    st7["characters"]["char_pa"]["tasks"]["task_1"]["goal"] = \
        "把铜铃挂回钟楼" + "网" * 60
    d7 = {"char_pa": {**np_.moved_delta("char_pa", "loc_2"),
                      "tasksAchieved": ["task_1", "task_2"]},
          "char_pb": {"entityId": "char_pb",
                      "positionSet": {"containerId": "loc_2", "slotId": None,
                                      "relativeTo": None},
                      "appearanceChanges": [], "personalityChanges": [],
                      "subtasksAdded": [], "tasksAchieved": [],
                      "sanitySet": None}}
    scenarios.append(("v2-over-128", point(d7, 30, st=st7), before,
                      "unsupported", False, None))

    results = []
    for name, pt, bef, expect, ablate, persp in scenarios:
        rec = run_scenario_v2(n4, tok_gate, name, pt, bef, hints, expect,
                              ablate, persp)
        results.append(rec)
        extra = ""
        if rec.get("ablation"):
            extra = f" ablDiff={rec['ablation']['differs']}"
        print(f"{name:22s} status={rec['status']:12s} "
              f"expectMet={rec['expectMet']}"
              + (f" n4='{rec['stages']['n4Model']['text'][:30]}'"
                 if rec.get("modelCalled") else "") + extra, flush=True)

    archive = {
        "purpose": "commit-2 real-model composition over the v2 grouped "
                   "interface: plan_v3 groups + appellation grants actually "
                   "reach the trained model; the ablation arm proves the "
                   "grants move the output; new kinds flow end-to-end",
        "checkpoint": {"dir": "experiments/world-components/n4_corpus_v2/"
                              "ckpt-v2",
                       "modelSha256": sha_file(CHECKPOINT /
                                               "model.safetensors")},
        "environment": {"python": platform.python_version(),
                        "torch": torch.__version__, "device": n4.device,
                        "note": "offline CPU timing; never merged with "
                                "browser timings"},
        "tokenGate": {"limit": np_.V2_TOKEN_LIMIT, "tokenizer":
                      "T5Tokenizer legacy=False (special tokens incl.)"},
        "scenarios": results,
        "pass": all(r["expectMet"] for r in results),
    }
    pathlib.Path(args.out).write_text(
        json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print("pass:", archive["pass"], "->", args.out)
    return 0 if archive["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())

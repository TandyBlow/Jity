# Real-model batch v2: the pre-registered 384-token output-budget comparison.
#
# Same 10 samples, same model digest, same prompts, same frozen judge and the
# same retry policy as v1. The ONLY change is `num_predict: 128 -> 384`, and
# the tripwire now follows the registered text (>=3 failing samples or >=2
# failing port CALLS — v1 counted port failures by sample and used `<7`).
#
# Two results are reported per sample:
#   primary = the FIRST call only (the budget comparison the owner asked for)
#   final   = after the one allowed retry (reported separately)
# Truncated samples stay in the denominator; whether 384 is enough is answered
# by the result, not assumed.
#
# Usage:
#   python -X utf8 test_tripwire_v2.py          # boundary tests first
#   python -X utf8 real_batch_v2.py            # run the batch
#   python -X utf8 apply_review.py --run out/real-batch-v2.json \
#       --review fixtures/review-v2.json --out out/real-batch-v2-reviewed.json

import argparse
import json
import pathlib
import platform
import sys
import time
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent.parent
for p in (str(WC), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import requests  # noqa: E402

import narration_pipeline as np_  # noqa: E402
import n2_perspective as n2p  # noqa: E402
import n3_organize as n3  # noqa: E402
import judge_v3  # noqa: E402
from n4_input_renderer.packer import pack_narrative_input  # noqa: E402
from n4_input_renderer.scene_context import build_scene_context  # noqa: E402

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "round_compose_v3", HERE / "compose_v3.py")
_round = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_round)
template_text = _round.template_text

REG = HERE / "fixtures" / "batch-v2.json"
CASES = HERE / "fixtures" / "batch-v1-cases.json"  # SAME samples as v1
DEFAULT_OUT = HERE / "out" / "real-batch-v2.json"
DEFAULT_RAW = HERE / "out" / "real-batch-v2-raw.jsonl"
MAX_ATTEMPTS = 2
TIMEOUT_S = 900


def tripwire(hard_gate_fail_samples: int, port_failure_calls: int) -> bool:
    """The registered line, verbatim: >=3/10 samples fail the hard gates, OR
    >=2 CALLS fail at the port. Boundary tests live in test_tripwire_v2.py."""
    return hard_gate_fail_samples >= 3 or port_failure_calls >= 2


class PortError(Exception):
    def __init__(self, code, detail=None):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def sha_file(path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ms(t0) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def call_model(endpoint, model, prompt, decode):
    options = {k: decode[k] for k in
               ("temperature", "seed", "num_predict", "top_p", "top_k",
                "repeat_penalty", "stop") if k in decode}
    payload = {"model": model, "prompt": prompt, "stream": False,
               "options": options}
    t0 = time.perf_counter()
    try:
        r = requests.post(endpoint, json=payload, timeout=TIMEOUT_S)
    except requests.Timeout:
        raise PortError("model-timeout", f">{TIMEOUT_S}s")
    except requests.RequestException as exc:
        raise PortError("model-transport", str(exc)[:200])
    wall = ms(t0)
    if r.status_code != 200:
        raise PortError(f"model-http-{r.status_code}", r.text[:300])
    try:
        data = r.json()
    except ValueError:
        raise PortError("model-bad-json", r.text[:300])
    return {"request": {"model": model, "prompt": prompt, "stream": False,
                        "options": options},
            "response": data, "text": data.get("response") or "",
            "finishReason": data.get("done_reason"), "wallMs": wall}


def build_chain(case):
    state = case["point"]["state"]
    resolved = n2p.resolve_perspective(
        state, case["perspective"].get("entityId"),
        case["perspective"].get("type", "protagonist"))
    if resolved["problems"]:
        return {"status": "incomplete", "reason": "perspective"}
    persp = resolved["perspective"]
    n1 = np_.extract_facts(case["point"], case["before"],
                           narrative_outcome=case["narrativeOutcome"])
    blocking = [d for d in n1["diagnostics"]
                if d["code"] in np_.INCOMPLETE_DIAGNOSTIC_CODES]
    if blocking:
        return {"status": "incomplete", "reason": "n1", "blocking": blocking}
    tasks = (state.get("characters") or {}).get(
        persp.get("entityId"), {}).get("tasks") if persp.get("entityId") else None
    sel = n2p.classify_facts(n1["facts"], persp, subject_tasks=tasks,
                             may_policy=case["options"]["mayPolicy"],
                             visible_other_actions=case["options"][
                                 "visibleOtherActions"])
    ids = sel.get("selectedFactIds") or []
    if sel["status"] != "ok" or not ids:
        return {"status": "stopped-at-selection",
                "reason": sel.get("reason") or "empty-selection"}
    selected = [f for f in n1["facts"] if f["factId"] in set(ids)]
    names = {f["entityId"]: f["name"] for f in selected if f.get("entityId")}
    hints = case.get("genderHints") or {}
    plan = n3.plan_v3(selected, names, hints, cross_group_guard=True)
    problems = (["plan-refusal"] if "refusal" in plan else
                n3.check_plan_v3(plan, selected, names, hints,
                                 cross_group_guard=True))
    if problems:
        return {"status": "stopped-at-organization", "problems": problems}
    scene = build_scene_context(state, persp, selected,
                                environment=case.get("environment"))
    if scene.get("status") != "ok":
        return {"status": "stopped-at-scene", "reason": scene.get("reason")}
    packed = pack_narrative_input(
        {"facts": selected, "perspective": persp,
         "sceneState": scene["sceneContext"]["sceneState"],
         "characterContext": scene["sceneContext"]["characterContext"]},
        plan, scene["worldView"], selected_fact_ids=ids)
    if packed.get("status") != "ok":
        return {"status": "stopped-at-input", "reason": packed.get("code")}
    return {"status": "ready-for-model", "perspective": persp,
            "n1Facts": n1["facts"], "n1Diagnostics": n1["diagnostics"],
            "selection": {"summary": sel["summary"], "ids": ids,
                          "decisions": sel["decisions"]},
            "selected": selected, "plan": plan, "renderText": packed["input"],
            "sceneDiagnostics": scene.get("diagnostics")}


def judge(selected, ids, plan, text, finish):
    try:
        v = judge_v3.judge(selected, ids, plan, text, finish or "eos")
        return {"status": "judged", **v}
    except judge_v3.JudgeBlocked as exc:
        return {"status": "blocked", "code": exc.code, "detail": exc.detail}


def status_of(judged, empty):
    if empty:
        return "empty-output"
    if judged["status"] == "blocked":
        return "blocked-at-judge"
    return "n5-pass" if judged.get("hardPass") else "n5-rejected"


def provenance(selected, plan, judged):
    groups = {}
    for s in (plan or {}).get("sentences") or []:
        for fid in s.get("factIds") or []:
            groups.setdefault(fid, []).append(s.get("index"))
    covered = set((judged or {}).get("covered") or [])
    return [{"factId": f.get("factId"), "kind": f.get("kind"),
             "entityId": f.get("entityId"), "source": f.get("source"),
             "planGroups": groups.get(f.get("factId"), []),
             "n5Covered": f.get("factId") in covered} for f in selected]


def run_case(case, reg, raw_fh):
    cid = case["caseId"]
    rec = {"caseId": cid, "title": case.get("title"),
           "notes": case.get("notes"), "attempts": [],
           "primaryStatus": None, "finalStatus": None, "reason": None,
           "d4": {"checked": False, "count": None, "items": []},
           "n6": {"status": "not-run", "result": None}, "quality": "pending"}
    t_case = time.perf_counter()
    chain = build_chain(case)
    rec["chain"] = {k: chain.get(k) for k in
                    ("status", "reason", "problems", "blocking", "selection",
                     "plan", "n1Diagnostics", "sceneDiagnostics")}
    if chain["status"] != "ready-for-model":
        rec["finalStatus"] = rec["primaryStatus"] = chain["status"]
        rec["reason"] = chain.get("reason")
        rec["timings"] = {"totalMs": ms(t_case)}
        return rec, 0
    selected, ids, plan = chain["selected"], chain["selection"]["ids"], \
        chain["plan"]
    rec["renderText"] = chain["renderText"]
    rec["renderChars"] = len(chain["renderText"])

    prompt = chain["renderText"]
    feedback, last, port_calls = None, None, 0
    for i in range(MAX_ATTEMPTS):
        t_call = time.perf_counter()
        sent = prompt if not feedback else (
            prompt + f"\n（上一轮的问题：{feedback}。请重写正文，只输出正文，"
                     f"不要解释。）\n")
        try:
            call = call_model(reg["model"]["endpoint"], reg["model"]["name"],
                              sent, reg["decode"])
        except PortError as exc:
            port_calls += 1
            rec["attempts"].append({"attempt": i + 1, "prompt": sent,
                                    "portError": {"code": exc.code,
                                                  "detail": exc.detail},
                                    "ms": ms(t_call),
                                    "decision": "retry" if i + 1 < MAX_ATTEMPTS
                                    else "stop"})
            raw_fh.write(json.dumps({"caseId": cid, "attempt": i + 1,
                                     "portError": exc.code,
                                     "detail": exc.detail},
                                    ensure_ascii=False) + "\n")
            st, reason = "sentence-port-failed", exc.code
            if i == 0:
                rec["primaryStatus"] = st
            rec["finalStatus"] = st
            feedback = f"端口错误 {exc.code}"
            continue
        text, finish = call["text"], call["finishReason"]
        empty = not text.strip("。，,：:；; \n\t")
        judged = ({"status": "empty", "hardPass": False,
                   "problems": ["empty-output"]} if empty
                  else judge(selected, ids, plan, text, finish))
        st = status_of(judged, empty)
        if i == 0:
            rec["primaryStatus"] = st
        rec["finalStatus"] = st
        raw_fh.write(json.dumps({"caseId": cid, "attempt": i + 1,
                                 "request": call["request"],
                                 "response": call["response"],
                                 "wallMs": call["wallMs"]},
                                ensure_ascii=False) + "\n")
        rec["attempts"].append({
            "attempt": i + 1, "prompt": sent, "response": call["response"],
            "output": text, "finishReason": finish, "wallMs": call["wallMs"],
            "promptTokens": call["response"].get("prompt_eval_count"),
            "outputTokens": call["response"].get("eval_count"),
            "n5": judged, "decision": None})
        last = judged
        if st in ("n5-pass", "blocked-at-judge"):
            rec["attempts"][-1]["decision"] = "accept"
            break
        reason = "; ".join(judged.get("problems") or []) or st
        rec["attempts"][-1]["decision"] = (
            "retry" if i + 1 < MAX_ATTEMPTS else "stop")
        feedback = reason

    rec["reason"] = None if rec["finalStatus"] == "n5-pass" else reason
    fallback = {"used": False, "reason": rec["finalStatus"]}
    if rec["finalStatus"] != "n5-pass":
        kinds = {f["kind"] for f in selected}
        unsupported = sorted(kinds - {"moved", "task_achieved", "outcome",
                                      "personality_changed",
                                      "sanity_changed",
                                      "appearance_changed",
                                      "positioned_at", "time", "no_change"})
        if unsupported:
            fallback["unavailableReason"] = "template-unsupported-kind"
            fallback["kinds"] = unsupported
        else:
            ftext = template_text(selected)
            fj = judge(selected, ids, plan, ftext, "eos")
            fallback.update({
                "used": True, "source": "compose_v3.template_text (program)",
                "text": ftext,
                "n5": {"hardPass": fj.get("hardPass"),
                       "gates": fj.get("gates"),
                       "problems": fj.get("problems")},
                "note": "program template, not a model output; the case "
                        "status stays the failure"})
    rec["fallback"] = fallback
    rec["n5"] = last
    rec["facts"] = provenance(selected, plan,
                              last if isinstance(last, dict) else None)
    rec["timings"] = {"totalMs": ms(t_case),
                      "modelCallsMs": [a.get("wallMs") for a in rec["attempts"]
                                       if a.get("wallMs")]}
    return rec, port_calls


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--raw", default=str(DEFAULT_RAW))
    args = ap.parse_args()

    reg = json.loads(REG.read_text(encoding="utf-8"))
    if sha_file(CASES) != reg["hashes"]["cases"]:
        raise SystemExit("cases file does not match the v2 registration")
    if sha_file(CASES) != reg["sameSamplesAsV1"]["casesSha256"]:
        raise SystemExit("v2 samples are not the v1 samples")
    if sha_file(HERE / "judge_v3.py") != reg["hashes"]["judge"]:
        raise SystemExit("judge_v3.py changed after registration")
    if sha_file(HERE / "real_batch_v2.py") != reg["hashes"]["runner"]:
        raise SystemExit("real_batch_v2.py changed after registration")
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    if [c["caseId"] for c in cases] != reg["sampleIds"]:
        raise SystemExit("sample ids differ from the registration")

    raw_path = pathlib.Path(args.raw)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    results, port_failure_calls = [], 0
    with raw_path.open("w", encoding="utf-8", newline="\n") as raw_fh:
        for case in cases:
            rec, pc = run_case(case, reg, raw_fh)
            port_failure_calls += pc
            results.append(rec)
            first = rec["attempts"][0] if rec["attempts"] else {}
            print(f"{rec['caseId']:26s} primary={str(rec['primaryStatus']):12s} "
                  f"final={str(rec['finalStatus']):12s} "
                  f"finish={first.get('finishReason')} "
                  f"out_tokens={first.get('outputTokens')} "
                  f"totalMs={rec['timings']['totalMs']}", flush=True)

    primary_counts, final_counts = {}, {}
    for r in results:
        primary_counts[r["primaryStatus"]] = primary_counts.get(
            r["primaryStatus"], 0) + 1
        final_counts[r["finalStatus"]] = final_counts.get(
            r["finalStatus"], 0) + 1
    hard_gate_fail = sum(1 for r in results
                         if r["finalStatus"] == "n5-rejected")
    truncated = 0
    for r in results:
        if r["attempts"] and r["attempts"][0].get("finishReason") == "length":
            truncated += 1
    archive = {
        "version": "real-batch-v2-run",
        "batchId": reg["batchId"],
        "registration": {"path": "fixtures/batch-v2.json",
                         "sha256": sha_file(REG)},
        "cases": {"path": "fixtures/batch-v1-cases.json",
                  "sha256": sha_file(CASES)},
        "model": reg["model"], "decode": reg["decode"],
        "acceptance": reg["acceptance"], "n6Rubric": reg["n6Rubric"],
        "primaryMetric": "first call only (attempt 1); retries are separate",
        "runAt": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": platform.python_version(),
                        "platform": platform.platform(),
                        "note": "local wall clock around the HTTP call; no "
                                "browser, no GPU assertion"},
        "summary": {
            "total": len(results),
            "primaryStatusCounts": primary_counts,
            "finalStatusCounts": final_counts,
            "primaryN5Pass": sum(1 for r in results
                                 if r["primaryStatus"] == "n5-pass"),
            "finalN5Pass": sum(1 for r in results
                               if r["finalStatus"] == "n5-pass"),
            "primaryTruncated": truncated,
            "hardGateFailSamples": hard_gate_fail,
            "portFailureCalls": port_failure_calls,
            "retriedSamples": sum(1 for r in results
                                  if len(r["attempts"]) > 1),
            "fallbacksUsed": sum(1 for r in results
                                 if r["fallback"].get("used")),
            "tripwireTriggered": tripwire(hard_gate_fail,
                                          port_failure_calls),
            "qualityPassed": 0,
            "qualityPending": len(results),
        },
        "caveat": "n5-pass means the hard gates passed only. D4 is unchecked "
                  "(count null) and N6 was not run in this file; quality is "
                  "pending until apply_review.py merges the review.",
        "cases": results,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"summary={json.dumps(archive['summary'], ensure_ascii=False)}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

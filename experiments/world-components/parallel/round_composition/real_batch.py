# First real-model offline batch for the C7 composition chain.
#
# Reads the PRE-REGISTERED batch (fixtures/batch-v1.json + batch-v1-cases.json),
# runs program N1/N2/N3/N4.0, sends the N4.0 record to the pinned local model,
# judges with judge_v3 (hard gates only), retries once with the gate problems as
# feedback, and records a program-template fallback when a rejection happens.
#
# Everything is archived verbatim: the exact prompt, the decode options, the
# raw ollama response, finish reason, wall time, retry decisions and the
# fallback text with its own verdict. D4 and N6 are NOT filled here: the archive
# starts with d4 count=null (unchecked) and n6 not-run, so nothing can look
# reviewed before a human pass exists. `apply_review.py` merges that pass in.
#
# Usage: python -X utf8 real_batch.py [--out out/real-batch-v1.json]
#                                     [--raw out/real-batch-v1-raw.jsonl]

import argparse
import copy
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
# `import compose_v3` would resolve to n4_corpus_v2/compose_v3.py (that
# directory is on sys.path via narration_pipeline), so load this directory's
# module by path and take only the template composer.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "round_compose_v3", HERE / "compose_v3.py")
_round = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_round)
template_text = _round.template_text

REG = HERE / "fixtures" / "batch-v1.json"
CASES = HERE / "fixtures" / "batch-v1-cases.json"
DEFAULT_OUT = HERE / "out" / "real-batch-v1.json"
DEFAULT_RAW = HERE / "out" / "real-batch-v1-raw.jsonl"
MAX_ATTEMPTS = 2
TIMEOUT_S = 900


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
            "response": data,
            "text": data.get("response") or "",
            "finishReason": data.get("done_reason"),
            "wallMs": wall}


def build_chain(case):
    """Program stages only; returns everything up to and including the N4.0
    text, or a stop record."""
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
                "reason": sel.get("reason") or "empty-selection",
                "stops": sel.get("stops")}
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
        verdict = judge_v3.judge(selected, ids, plan, text, finish or "eos")
        return {"status": "judged", **verdict}
    except judge_v3.JudgeBlocked as exc:
        return {"status": "blocked", "code": exc.code, "detail": exc.detail}


def provenance(selected, plan, judged):
    groups = {}
    for s in (plan or {}).get("sentences") or []:
        for fid in s.get("factIds") or []:
            groups.setdefault(fid, []).append(s.get("index"))
    covered = set((judged or {}).get("covered") or [])
    return [{"factId": f.get("factId"), "kind": f.get("kind"),
             "entityId": f.get("entityId"), "source": f.get("source"),
             "at": f.get("at"), "planGroups": groups.get(f.get("factId"), []),
             "n5Covered": f.get("factId") in covered} for f in selected]


def run_case(case, reg, raw_fh):
    cid = case["caseId"]
    rec = {"caseId": cid, "title": case.get("title"),
           "notes": case.get("notes"), "status": None, "reason": None,
           "d4": {"checked": False, "count": None, "items": []},
           "n6": {"status": "not-run", "result": None}, "quality": "pending",
           "attempts": [], "modelCalled": False}
    t_case = time.perf_counter()
    chain = build_chain(case)
    rec["chain"] = {k: chain.get(k) for k in
                    ("status", "reason", "problems", "blocking", "selection",
                     "plan", "n1Diagnostics", "sceneDiagnostics")}
    if chain["status"] != "ready-for-model":
        rec["status"] = chain["status"]
        rec["reason"] = chain.get("reason")
        rec["timings"] = {"totalMs": ms(t_case)}
        return rec
    rec["renderText"] = chain["renderText"]
    selected, ids, plan = chain["selected"], chain["selection"]["ids"], \
        chain["plan"]

    prompt = chain["renderText"]
    feedback = None
    status, reason, last = None, None, None
    for i in range(MAX_ATTEMPTS):
        t_call = time.perf_counter()
        sent = prompt if not feedback else (
            prompt + f"\n（上一轮的问题：{feedback}。请重写正文，只输出正文，"
                     f"不要解释。）\n")
        try:
            call = call_model(reg["model"]["endpoint"], reg["model"]["name"],
                              sent, reg["decode"])
            rec["modelCalled"] = True
        except PortError as exc:
            rec["modelCalled"] = True
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
            status, reason = "sentence-port-failed", exc.code
            feedback = f"端口错误 {exc.code}"
            continue
        text = call["text"]
        finish = call["finishReason"]
        empty = not text.strip("。，,：:；; \n\t")
        if empty:
            judged = {"status": "empty", "hardPass": False,
                      "problems": ["empty-output"]}
            st = "empty-output"
        else:
            judged = judge(selected, ids, plan, text, finish)
            st = ("blocked-at-judge" if judged["status"] == "blocked"
                  else ("n5-pass" if judged.get("hardPass") else "n5-rejected"))
        raw_fh.write(json.dumps({"caseId": cid, "attempt": i + 1,
                                 "request": call["request"],
                                 "response": call["response"],
                                 "wallMs": call["wallMs"]},
                                ensure_ascii=False) + "\n")
        rec["attempts"].append({
            "attempt": i + 1, "prompt": sent,
            "response": call["response"], "output": text,
            "finishReason": finish, "wallMs": call["wallMs"],
            "n5": judged, "decision": None})
        last = judged
        rec["status"] = st
        if st in ("n5-pass", "blocked-at-judge"):
            rec["attempts"][-1]["decision"] = "accept"
            break
        status, reason = st, "; ".join(judged.get("problems") or []) or st
        rec["attempts"][-1]["decision"] = (
            "retry" if i + 1 < MAX_ATTEMPTS else "stop")
        feedback = reason

    # fallback: program template, judged separately, never a success
    fallback = {"used": False, "reason": status}
    if rec["status"] != "n5-pass":
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
            fjudged = judge(selected, ids, plan, ftext, "eos")
            fallback.update({
                "used": True, "source": "compose_v3.template_text (program)",
                "text": ftext, "n5": {
                    "hardPass": fjudged.get("hardPass"),
                    "gates": fjudged.get("gates"),
                    "problems": fjudged.get("problems")},
                "note": "program template, not a model output; the case "
                        "status stays the failure"})
    rec["fallback"] = fallback
    rec["reason"] = reason
    rec["n5"] = last
    rec["facts"] = provenance(selected, plan, last if isinstance(last, dict)
                              else None)
    rec["renderChars"] = len(chain["renderText"])
    rec["timings"] = {"totalMs": ms(t_case),
                      "modelCallsMs": [a.get("wallMs") for a in rec["attempts"]
                                       if a.get("wallMs")]}
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--raw", default=str(DEFAULT_RAW))
    args = ap.parse_args()

    reg = json.loads(REG.read_text(encoding="utf-8"))
    cases_doc = json.loads(CASES.read_text(encoding="utf-8"))
    if sha_file(CASES) != reg["hashes"]["cases"]:
        raise SystemExit("cases file does not match the registration hash")
    if sha_file(HERE / "judge_v3.py") != reg["hashes"]["judge"]:
        raise SystemExit("judge_v3.py changed after registration")
    if sha_file(HERE / "real_batch.py") != reg["hashes"]["compose"]:
        raise SystemExit("real_batch.py changed after registration")
    cases = cases_doc["cases"]
    if [c["caseId"] for c in cases] != reg["sampleIds"]:
        raise SystemExit("sample ids differ from the registration")

    raw_path = pathlib.Path(args.raw)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    results = []
    with raw_path.open("w", encoding="utf-8", newline="\n") as raw_fh:
        for case in cases:
            rec = run_case(case, reg, raw_fh)
            results.append(rec)
            print(f"{rec['caseId']:26s} {str(rec['status']):20s} "
                  f"calls={len(rec['attempts'])} "
                  f"fallback={rec['fallback'].get('used')} "
                  f"totalMs={rec['timings']['totalMs']}", flush=True)

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    n5_pass = sum(1 for r in results if r["status"] == "n5-pass")
    port_fail = sum(1 for r in results
                    if r["status"] == "sentence-port-failed")
    archive = {
        "version": "real-batch-v1-run",
        "batchId": reg["batchId"],
        "registration": {"path": "fixtures/batch-v1.json",
                         "sha256": sha_file(REG)},
        "cases": {"path": "fixtures/batch-v1-cases.json",
                  "sha256": sha_file(CASES)},
        "model": reg["model"], "decode": reg["decode"],
        "acceptance": reg["acceptance"], "n6Rubric": reg["n6Rubric"],
        "runAt": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": platform.python_version(),
                        "platform": platform.platform(),
                        "note": "timings are local wall clock around the HTTP "
                                "call; no browser, no GPU assertion"},
        "summary": {"total": len(results), "statusCounts": counts,
                    "n5Pass": n5_pass, "portFailures": port_fail,
                    "retried": sum(1 for r in results
                                   if len(r["attempts"]) > 1),
                    "fallbacksUsed": sum(1 for r in results
                                         if r["fallback"].get("used")),
                    "qualityPassed": 0,
                    "qualityPending": sum(1 for r in results
                                          if r["quality"] == "pending"),
                    "tripwireTriggered": (n5_pass < 7) or (port_fail >= 2)},
        "caveat": "n5-pass means the hard gates passed only. D4 is unchecked "
                  "(count null) and N6 was not run in this file; quality is "
                  "pending for every sample until apply_review.py merges the "
                  "human pass.",
        "cases": results,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"summary={archive['summary']} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Offline round composer (C7 / R11): selection -> organization -> scene ->
# sentence -> verification, with MOCK ports for the three model-side
# stages. This verifies the composition plumbing and the program checks;
# it is NOT model-capability evidence.
#
# Chain per case:
#   N1   program  narration_pipeline.extract_facts(point, before)
#   N2   mock     selectedFactIds, validated against the perspective rule
#                 (must coverage / visibility / unknown ids)
#   N3   mock     the narrow plan shape, validated by check_plan_v3
#   scene program build_scene_context(state, perspective, selected)
#   N4.0 program  pack_narrative_input(...)  (fail-closed)
#   N4   mock     one text per attempt (scripted JSON)
#   N5   program  eval_n4_v2.judge_row hard gates (the frozen v2 gate);
#                 semantic review is NOT run and never auto-passed
#
# Failure semantics: every stop is a structured status; a rejected
# narration keeps `n5-rejected` even when the program template fallback is
# recorded next to it. A fallback is never reported as model success.
#
# Mock ports are scripted JSON in fixtures/mocks.json. Timings measure the
# composer only (no model inference), and are never merged with model or
# browser timings.
#
# Usage:
#   python -X utf8 compose.py --out out/composition-run.json
#   python -X utf8 compose.py --cases fixtures/cases.json --mocks fixtures/mocks.json

import argparse
import hashlib
import json
import pathlib
import platform
import sys
import time
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent.parent
for p in (str(WC), str(WC / "n4_corpus"), str(WC / "n4_corpus_v2")):
    if p not in sys.path:
        sys.path.insert(0, p)

import narration_pipeline as np_  # noqa: E402
import n2_perspective as n2p  # noqa: E402
import n3_organize as n3  # noqa: E402
from n4_input_renderer.packer import pack_narrative_input  # noqa: E402
from n4_input_renderer.scene_context import build_scene_context  # noqa: E402
from eval_n4_v2 import judge_row  # noqa: E402

VERSION = "round-composition-v0.1"
MAX_SENTENCE_ATTEMPTS = 2
TEMPLATE_KINDS = {"moved", "task_achieved", "personality_changed",
                 "sanity_changed", "appearance_changed", "positioned_at",
                 "time", "no_change"}


class PortError(Exception):
    """A sentence port failure (timeout, transport, missing response)."""

    def __init__(self, code, detail=None):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ms_since(t0) -> float:
    return round((time.perf_counter() - t0) * 1000, 3)


def load_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def stage(record, name, t0, **fields):
    record.setdefault("stages", {})[name] = {"ms": ms_since(t0), **fields}


def sentence_mock(mocks_case, attempt):
    entries = (mocks_case or {}).get("sentence") or []
    if attempt >= len(entries):
        raise PortError("no-mock-response",
                        f"sentence mock has {len(entries)} entries, "
                        f"attempt {attempt + 1} requested")
    entry = entries[attempt]
    if entry.get("error"):
        raise PortError(entry["error"], entry.get("detail"))
    return entry


def unsupported_kind_error(exc: ValueError) -> str:
    return str(exc)


def fact_provenance(selected, plan, verdict):
    groups = {}
    for s in (plan or {}).get("sentences") or []:
        for fid in s.get("factIds") or []:
            groups.setdefault(fid, []).append(s.get("index"))
    covered = set((verdict or {}).get("align", {}).get("covered") or [])
    out = []
    for f in selected:
        out.append({
            "factId": f.get("factId"),
            "kind": f.get("kind"),
            "entityId": f.get("entityId"),
            "entityGroup": f.get("entityGroup"),
            "source": f.get("source"),
            "at": f.get("at"),
            "atPath": f.get("atPath"),
            "planGroups": groups.get(f.get("factId"), []),
            "n5Covered": f.get("factId") in covered,
        })
    return out


def compose_case(case, mocks_case, config):
    cid = case["caseId"]
    rec = {"caseId": cid, "title": case.get("title"),
           "expect": case.get("expect"), "stages": {},
           "notes": case.get("notes"), "modelCalled": False,
           "status": None, "reason": None}
    t_case = time.perf_counter()
    state = (case.get("point") or {}).get("state") or {}

    # ---- perspective (authority check) --------------------------------
    t0 = time.perf_counter()
    persp_in = case.get("perspective") or {}
    resolved = n2p.resolve_perspective(state, persp_in.get("entityId"),
                                       persp_in.get("type", "protagonist"))
    stage(rec, "perspective", t0, request=persp_in,
          status="ok" if not resolved["problems"] else "stopped",
          perspective=resolved.get("perspective"),
          problems=resolved.get("problems"))
    if resolved["problems"]:
        rec["status"] = "incomplete"
        rec["reason"] = "perspective-unresolvable"
        rec["timings"] = {"totalMs": ms_since(t_case)}
        rec["expectMet"] = rec["status"] == rec["expect"]
        return rec
    persp = resolved["perspective"]
    rec["perspective"] = persp

    # ---- N1 program facts --------------------------------------------
    t0 = time.perf_counter()
    n1 = np_.extract_facts(case.get("point") or {}, case.get("before"))
    blocking = [d for d in n1["diagnostics"]
                if d["code"] in np_.INCOMPLETE_DIAGNOSTIC_CODES]
    stage(rec, "n1", t0, program="narration_pipeline.extract_facts",
          factCount=len(n1["facts"]), facts=n1["facts"],
          diagnostics=n1["diagnostics"], blocking=blocking)
    if blocking:
        rec["status"] = "incomplete"
        rec["reason"] = "n1-cannot-express"
        rec["timings"] = {"totalMs": ms_since(t_case)}
        rec["expectMet"] = rec["status"] == rec["expect"]
        return rec

    # ---- N2 mock selection + program validation -----------------------
    options = case.get("options") or {}
    may_policy = options.get("mayPolicy", "select")
    visible_others = bool(options.get("visibleOtherActions", False))
    subject_tasks = None
    if persp.get("entityId"):
        subject_tasks = ((state.get("characters") or {})
                         .get(persp["entityId"], {}).get("tasks"))
    t0 = time.perf_counter()
    rule = n2p.classify_facts(n1["facts"], persp,
                             subject_tasks=subject_tasks,
                             may_policy=may_policy,
                             visible_other_actions=visible_others)
    req = {"facts": n1["facts"], "perspective": persp,
           "mayPolicy": may_policy, "visibleOtherActions": visible_others}
    sel_mock = mocks_case.get("selection")
    valid_ids = {f["factId"] for f in n1["facts"]}
    validation = {"unknownIds": [], "missingMust": [], "invisible": [],
                  "shape": "ok"}
    selected_ids = []
    if not isinstance(sel_mock, dict) or not isinstance(
            sel_mock.get("selectedFactIds"), list):
        validation["shape"] = "selection-response-shape-invalid"
    else:
        selected_ids = sel_mock["selectedFactIds"]
        validation["unknownIds"] = [x for x in selected_ids
                                    if x not in valid_ids]
        must = {d["factId"] for d in rule.get("decisions") or []
                if d.get("class") == "must"}
        visible = {d["factId"] for d in rule.get("decisions") or []
                   if d.get("class") in ("must", "may")}
        validation["missingMust"] = sorted(must - set(selected_ids))
        validation["invisible"] = sorted(set(selected_ids) - visible)
    stage(rec, "selection", t0, program="n2_perspective.classify_facts + mock port",
          request=req, response=sel_mock, rule={"status": rule.get("status"),
                                                "summary": rule.get("summary"),
                                                "stops": rule.get("stops"),
                                                "refusals": rule.get("refusals"),
                                                "decisions": rule.get("decisions")},
          validation=validation)
    if rule.get("status") != "ok":
        rec["status"] = "incomplete"
        rec["reason"] = "n2-rule-stop"
    elif validation["shape"] != "ok":
        rec["status"] = "stopped-at-selection"
        rec["reason"] = validation["shape"]
    elif validation["unknownIds"]:
        rec["status"] = "stopped-at-selection"
        rec["reason"] = "unknown-fact-references"
    elif validation["missingMust"]:
        rec["status"] = "stopped-at-selection"
        rec["reason"] = "missing-must-facts"
    elif validation["invisible"]:
        rec["status"] = "stopped-at-selection"
        rec["reason"] = "invisible-fact-selected"
    elif n1["facts"] and not selected_ids:
        rec["status"] = "stopped-at-selection"
        rec["reason"] = "empty-selection"
    if rec["status"]:
        rec["timings"] = {"totalMs": ms_since(t_case)}
        rec["expectMet"] = rec["status"] == rec["expect"]
        return rec
    selected = [f for f in n1["facts"] if f["factId"] in set(selected_ids)]
    rec["selectedFactIds"] = selected_ids

    # ---- N3 mock organization + program invariants --------------------
    t0 = time.perf_counter()
    names = {f["entityId"]: f["name"] for f in selected if f.get("entityId")}
    org_mock = mocks_case.get("organization")
    req = {"selectedFacts": selected, "names": names,
           "genderHints": case.get("genderHints") or {},
           "crossGroupGuard": case.get("crossGroupGuard", True)}
    problems = []
    if not isinstance(org_mock, dict):
        problems = ["organization-response-missing"]
    elif "refusal" in org_mock:
        problems = ["plan-refusal"]
    elif not isinstance(org_mock.get("sentences"), list):
        problems = ["plan-shape-invalid"]
    else:
        try:
            problems = n3.check_plan_v3(
                org_mock, selected, names,
                case.get("genderHints") or {},
                cross_group_guard=case.get("crossGroupGuard", True))
        except Exception as exc:  # malformed mock shape, never a silent pass
            problems = [f"plan-check-error:{exc}"]
    stage(rec, "organization", t0,
          program="n3_organize.check_plan_v3 + mock port",
          request=req, response=org_mock, validation={"problems": problems})
    if problems:
        rec["status"] = "stopped-at-organization"
        rec["reason"] = "plan-invariant-violation"
        rec["timings"] = {"totalMs": ms_since(t_case)}
        rec["expectMet"] = rec["status"] == rec["expect"]
        return rec
    plan = org_mock

    # ---- scene context (N4.0a, program) -------------------------------
    t0 = time.perf_counter()
    scene = build_scene_context(state, persp, selected,
                                environment=case.get("environment"))
    stage(rec, "scene", t0, program="n4_input_renderer.scene_context",
          status=scene.get("status"), reason=scene.get("reason"),
          diagnostics=scene.get("diagnostics"),
          environment=case.get("environment"))
    if scene.get("status") != "ok":
        rec["status"] = "stopped-at-scene"
        rec["reason"] = scene.get("reason")
        rec["timings"] = {"totalMs": ms_since(t_case)}
        rec["expectMet"] = rec["status"] == rec["expect"]
        return rec

    # ---- N4.0 structured input (program, fail-closed) -----------------
    t0 = time.perf_counter()
    case_input = {"facts": selected, "perspective": persp,
                  "sceneState": scene["sceneContext"]["sceneState"],
                  "characterContext": scene["sceneContext"]["characterContext"]}
    packed = pack_narrative_input(case_input, plan, scene["worldView"],
                                  selected_fact_ids=selected_ids)
    stage(rec, "n4Input", t0, program="n4_input_renderer.packer",
          version=packed.get("version"), status=packed.get("status"),
          code=packed.get("code"), detail=packed.get("detail"),
          diagnostics=packed.get("diagnostics"),
          input=packed.get("input"),
          inputChars=len(packed.get("input") or ""))
    if packed.get("status") != "ok":
        rec["status"] = "stopped-at-input"
        rec["reason"] = packed.get("code")
        rec["timings"] = {"totalMs": ms_since(t_case)}
        rec["expectMet"] = rec["status"] == rec["expect"]
        return rec
    render_text = packed["input"]
    rec["modelInput"] = render_text

    # ---- N4 mock sentence + N5 frozen hard gates ----------------------
    row = {"rowId": f"comp:{cid}", "facts": selected,
           "mustExpress": list(selected_ids), "plan": plan}
    t0 = time.perf_counter()
    attempts, status, reason = [], None, None
    last_verdict, last_text = None, None
    feedback = None
    for i in range(config["maxSentenceAttempts"]):
        req = {"caseId": cid, "input": render_text, "attempt": i + 1,
               "feedback": feedback}
        t_attempt = time.perf_counter()
        try:
            resp = sentence_mock(mocks_case, i)
        except PortError as exc:
            rec["modelCalled"] = True
            attempts.append({"attempt": i + 1, "request": req,
                             "ms": ms_since(t_attempt),
                             "portError": {"code": exc.code,
                                           "detail": exc.detail},
                             "decision": "retry" if i + 1 < config[
                                 "maxSentenceAttempts"] else "stop"})
            status, reason = "sentence-port-failed", exc.code
            feedback = f"port-error:{exc.code}"
            continue
        rec["modelCalled"] = True
        text = resp.get("text") or ""
        finish = resp.get("finishReason") or "eos"
        empty = not text.strip("。，,：:；; \n\t")
        if empty:
            verdict = {"pass": False, "gates": {},
                       "align": {"covered": [], "problems": ["empty-output"]}}
        else:
            try:
                verdict = judge_row(row, text, finish)
            except ValueError as exc:
                attempts.append({"attempt": i + 1, "request": req,
                                 "ms": ms_since(t_attempt),
                                 "response": resp, "output": text,
                                 "finishReason": finish,
                                 "n5": {"status": "unsupported-kind",
                                        "error": unsupported_kind_error(exc)},
                                 "decision": "stop"})
                status, reason = "n5-unsupported-kind", str(exc)
                last_verdict, last_text = None, text
                break
        annotations = resp.get("annotations") or {}
        attempt_rec = {"attempt": i + 1, "request": req,
                       "ms": ms_since(t_attempt), "response": resp,
                       "output": text, "finishReason": finish,
                       "n5": verdict,
                       "fixtureAnnotations": annotations,
                       "decision": None}
        attempts.append(attempt_rec)
        last_verdict, last_text = verdict, text
        if verdict["pass"] and annotations.get("addsUnregisteredEntity"):
            # The fixture declares a defect the frozen v2 hard gates do not
            # cover (G2 scans only REGISTERED names/goals). Record the
            # disagreement; do not relax or override N5, do not retry.
            attempt_rec["decision"] = "stop"
            status, reason = "n5-false-pass", "unregistered-entity-not-gated"
            break
        if verdict["pass"]:
            attempt_rec["decision"] = "accept"
            status, reason = "ok", None
            break
        status = "empty-output" if empty else "n5-rejected"
        if empty:
            reason = "empty-output"
        else:
            problems = verdict.get("align", {}).get("problems") or []
            failed = [g for g, ok in (verdict.get("gates") or {}).items()
                      if not ok]
            reason = "; ".join(problems) if problems else \
                "failed-gates:" + ",".join(failed)
        attempt_rec["decision"] = "retry" if i + 1 < config[
            "maxSentenceAttempts"] else "stop"
        feedback = reason
    else:
        if status is None:
            status, reason = "sentence-port-failed", "no-mock-response"
    stage(rec, "n4n5", t0, program="mock sentence port + eval_n4_v2.judge_row",
          attempts=attempts, retryCount=max(0, len(attempts) - 1),
          maxAttempts=config["maxSentenceAttempts"],
          semanticReview="not-run",
          note="semantic review is a separate human/model step and is never "
               "auto-passed; 'ok' means the frozen hard gates passed")

    # ---- recorded cross-check: the OTHER program N5 core ----------------
    # corpus_check.check_narration (the v7 recognizer used by
    # narration_pipeline.verify_text) is a second program N5 core with a
    # different strictness profile: uncovered must facts and unrecognized
    # content are REVIEW-class there, and it has no truncation rule. It is
    # recorded only; it can never flip the status computed above and its
    # findings are not auto-passed either.
    if last_text:
        t0 = time.perf_counter()
        try:
            cross = np_.verify_text(selected, last_text)
            cross_rec = {"status": cross["status"],
                         "fails": cross["fails"],
                         "semanticUncertain": cross["semanticUncertain"]}
        except Exception as exc:  # shape mismatch must be visible, not silent
            cross_rec = {"status": "error", "error": str(exc)}
        stage(rec, "n5CrossCheck", t0,
              program="narration_pipeline.verify_text -> "
                      "corpus_check.check_narration",
              text=last_text, result=cross_rec,
              note="recorded only; never gates this composition")

    # ---- explicit template fallback (recorded, never counted as success) --
    fallback = None
    bad_kinds = sorted({f["kind"] for f in selected} - TEMPLATE_KINDS)
    if status != "ok" and case.get("fallback", True):
        if bad_kinds:
            fallback = {"used": False, "reason": status,
                        "unavailableReason": "template-unsupported-kind",
                        "kinds": bad_kinds}
        else:
            text = np_.generate_reference_text(selected)
            try:
                verdict = judge_row(row, text, "eos")
                v = {"pass": verdict["pass"], "gates": verdict["gates"],
                     "problems": verdict["align"]["problems"]}
            except ValueError as exc:
                v = {"pass": False, "status": "unsupported-kind",
                     "error": str(exc)}
            fallback = {"used": True, "reason": status,
                        "source": "narration_pipeline.generate_reference_text",
                        "text": text, "n5": v,
                        "note": "program template, not a model output; the "
                                "case status stays the failure"}
    elif status != "ok":
        fallback = {"used": False, "reason": status,
                    "unavailableReason": "disabled-for-case"}
    stage(rec, "fallback", time.perf_counter(), **(fallback or
                                                  {"used": False}))

    rec["status"] = status
    rec["reason"] = reason
    rec["facts"] = fact_provenance(selected, plan, last_verdict)
    rec["n5"] = {"rule": "eval_n4_v2.judge_row",
                 "gates": (last_verdict or {}).get("gates"),
                 "problems": (last_verdict or {}).get("align", {}).get(
                     "problems"),
                 "covered": (last_verdict or {}).get("align", {}).get(
                     "covered"),
                 "autoPassed": False,
                 "semanticReview": "not-run"}
    rec["timings"] = {"totalMs": ms_since(t_case)}
    rec["expectMet"] = rec["status"] == rec["expect"]
    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=str(HERE / "fixtures" / "cases.json"))
    parser.add_argument("--mocks", default=str(HERE / "fixtures" / "mocks.json"))
    parser.add_argument("--out", default=str(HERE / "out" /
                                             "composition-run.json"))
    args = parser.parse_args()

    cases_doc = load_json(args.cases)
    mocks_doc = load_json(args.mocks)
    cases = cases_doc.get("cases") or []
    mocks = mocks_doc.get("cases") or {}
    config = {"maxSentenceAttempts": MAX_SENTENCE_ATTEMPTS}

    results = []
    for case in cases:
        cid = case["caseId"]
        # Cases that stop before a port (N1/perspective) need no mock entry;
        # a missing entry for a case that reaches N2 is a shape failure, not
        # a silent skip.
        rec = compose_case(case, mocks.get(cid) or {}, config)
        results.append(rec)
        print(f"{cid:34s} status={rec['status']:22s} "
              f"expectMet={rec['expectMet']} "
              f"totalMs={rec['timings']['totalMs']}", flush=True)

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    archive = {
        "version": VERSION,
        "purpose": "offline round composition over the frozen N1/N2/N3/N4.0/"
                   "N5 interfaces with MOCK selection/organization/sentence "
                   "ports; verifies normal, module-failure and N5-rejection "
                   "paths, fact provenance, retries, fallbacks and composer "
                   "timing",
        "caveat": "Mock ports are scripted JSON. Nothing here measures a "
                  "model; no N4/N5 quality claim is made. 'ok' means the "
                  "frozen hard gates passed on a scripted text. Semantic "
                  "review is not run.",
        "runAt": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": platform.python_version(),
                        "platform": platform.platform(),
                        "timingScope": "composer only; mock ports return "
                                       "immediately; no model inference"},
        "config": config,
        "inputs": {
            "cases": {"path": str(pathlib.Path(args.cases).resolve()
                                 .relative_to(HERE.parent.parent.parent.parent)),
                      "sha256": sha256_file(args.cases),
                      "version": cases_doc.get("version")},
            "mocks": {"path": str(pathlib.Path(args.mocks).resolve()
                                 .relative_to(HERE.parent.parent.parent.parent)),
                      "sha256": sha256_file(args.mocks),
                      "version": mocks_doc.get("version"),
                      "source": mocks_doc.get("source")},
        },
        "summary": {"total": len(results), "statusCounts": counts,
                    "expectMet": sum(1 for r in results if r["expectMet"]),
                    "retried": sum(1 for r in results
                                   if (r["stages"].get("n4n5") or {})
                                   .get("retryCount", 0) > 0),
                    "fallbacksUsed": sum(1 for r in results
                                         if (r["stages"].get("fallback") or {})
                                         .get("used"))},
        "cases": results,
        "pass": all(r["expectMet"] for r in results),
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"pass={archive['pass']} -> {out}")
    return 0 if archive["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

# N4 narrative pipeline: N1(outcome/resultText) -> N2(select + visible
# other actions) -> N3(plan_v3) -> N4(render_plan_input).
#
# This is the production-shaped narrative path, but the N4 model itself is
# not called/trained here. The scene/character context is an explicit input:
# building it from the world state is a separate contract, not guessed here.
# Missing task resultText stops with `task-outcome-unavailable`; the goal is
# never used as a fallback surface.

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
sys.path.insert(0, str(WC))
sys.path.insert(0, str(HERE))

import n2_perspective as n2  # noqa: E402
import n3_organize as n3  # noqa: E402
import narration_pipeline as np  # noqa: E402
import n4_input_renderer as n4r  # noqa: E402


def run_narrative_pipeline(point, before, perspective, scene_context=None,
                           world=None, environment=None, may_policy="select",
                           input_format="structured"):
    out = {"pointId": point.get("pointId"),
           "version": point.get("version"),
           "chain": "narrative-n4"}
    resolved = n2.resolve_perspective(
        point.get("state") or {}, (perspective or {}).get("entityId"),
        (perspective or {}).get("type", "protagonist"))
    if resolved["problems"]:
        out.update(status="incomplete", reason="perspective-unresolvable",
                   problems=resolved["problems"])
        return out
    persp = resolved["perspective"]
    out["perspective"] = persp

    n1 = np.extract_facts(point, before, narrative_outcome=True)
    out["n1"] = {"factCount": len(n1["facts"]),
                 "diagnostics": n1["diagnostics"]}
    blocking = [d for d in n1["diagnostics"]
                if d["code"] in np.INCOMPLETE_DIAGNOSTIC_CODES]
    if blocking:
        out.update(status="incomplete", reason="n1-cannot-express",
                   blocking=blocking)
        return out

    subject_tasks = None
    if persp.get("entityId"):
        subject_tasks = ((point.get("state") or {}).get("characters")
                         or {}).get(persp["entityId"], {}).get("tasks")
    n2res = n2.classify_facts(
        n1["facts"], persp, subject_tasks=subject_tasks,
        may_policy=may_policy, visible_other_actions=True)
    out["n2"] = {"status": n2res["status"],
                 "summary": n2res.get("summary"),
                 "selectedFactIds": n2res.get("selectedFactIds"),
                 "decisions": n2res.get("decisions")}
    if n2res["status"] != "ok":
        out.update(status="stopped-at-n2", reason=n2res.get("status"))
        return out
    selected = [f for f in n1["facts"]
                if f["factId"] in set(n2res["selectedFactIds"])]
    if n1["facts"] and not selected:
        out.update(status="incomplete", reason="n2-empty-selection")
        return out

    names = {f["entityId"]: f["name"] for f in selected if f.get("entityId")}
    plan = n3.plan_v3(selected, names, cross_group_guard=True)
    if "refusal" in plan:
        out.update(status="stopped-at-n3", reason="plan-refusal",
                   n3={"refusal": plan["refusal"]})
        return out
    problems = n3.check_plan_v3(plan, selected, names)
    if problems:
        out.update(status="stopped-at-n3", reason="plan-invariant",
                   n3={"violations": problems})
        return out
    out["n3"] = {"status": "ok", "groups": len(plan["sentences"]),
                 "plan": plan, "selectedFacts": selected}

    if scene_context is None:
        built = n4r.build_scene_context(
            point.get("state") or {}, persp, selected, environment)
        if built.get("status") != "ok":
            out.update(status="incomplete", reason=built.get("reason"),
                       diagnostics=built.get("diagnostics"))
            return out
        scene_context = built["sceneContext"]
        if world is None:
            world = built["worldView"]
        out["sceneContext"] = scene_context
        out["sceneDiagnostics"] = built.get("diagnostics", [])
    if world is None:
        out.update(status="incomplete", reason="world-view-missing")
        return out
    case = {"facts": n1["facts"],
            "perspective": scene_context.get("perspective")
            or {"entityId": persp["entityId"]},
            "sceneState": scene_context["sceneState"],
            "characterContext": scene_context["characterContext"]}
    try:
        selected_ids = [f["factId"] for f in selected]
        if input_format == "legacy":
            input_text = n4r.render_plan_input(
                case, plan, world, strict=True,
                selected_fact_ids=selected_ids)
            out["inputVersion"] = n4r.N4_VERSION
        else:
            packed = n4r.pack_narrative_input(
                case, plan, world, selected_fact_ids=selected_ids,
                scene_diagnostics=out.get("sceneDiagnostics") or [])
            if packed["status"] != "ok":
                out.update(status="incomplete",
                           reason="n4-input-pack-failed",
                           code=packed.get("code"),
                           detail=packed.get("detail"))
                return out
            input_text = packed["input"]
            out["inputVersion"] = packed["version"]
            out["inputDiagnostics"] = packed["diagnostics"]
    except n4r.N4RenderError as exc:
        out.update(status="incomplete", reason="n4-render-failed",
                   code=exc.code, detail=exc.detail)
        return out
    except KeyError as exc:
        out.update(status="incomplete", reason="scene-context-incomplete",
                   missing=str(exc))
        return out
    out.update(status="ok", input=input_text)
    return out

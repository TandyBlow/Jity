# End-to-end input test for the N4 narrative path with N1 outcome/resultText.
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/test_pipeline_narrative.py

import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import narration_pipeline as np  # noqa: E402
import pipeline_narrative as pn  # noqa: E402


ENV = {"time": "夜", "weather": "雨", "wind": "无", "light": "灯",
       "atmosphere": "安静"}


def add_passive_npcs(state, n=100):
    """100 co-located NPCs with no selected facts: the scene builder must
    NOT enumerate them (the old co-presence regression)."""
    for i in range(n):
        eid = f"npc{i}"
        state["initial"]["characters"][eid] = {
            "id": eid, "name": f"路人{i}",
            "initialPosition": {"containerId": "loc_1", "slotId": None,
                                "relativeTo": None},
            "initialAppearance": "普通", "initialPersonality": "沉默",
            "initialSanity": 10, "tasks": {}}
        state["characters"][eid] = {
            "id": eid, "position": {"containerId": "loc_1", "slotId": None,
                                    "relativeTo": None},
            "appearanceChanges": [], "personalityChanges": [], "sanity": 10,
            "tasks": {}}
    return state


def build_point(with_result_text=True):
    before_state = np.make_pipeline_state()
    before = np.make_point(1, {}, None, state=before_state, prev=None)
    before = {**before, "pointId": "pt-1", "version": 1}
    state = np.make_pipeline_state()
    task = state["characters"]["char_pa"]["tasks"]["task_1"]
    task["status"] = "achieved"
    if with_result_text:
        task["resultText"] = "把铜铃挂回了钟楼"
    add_passive_npcs(state)
    point = np.make_point(2, {"char_pa": {"tasksAchieved": ["task_1"]}},
                          None, state=state, prev="pt-1")
    return point, before


def main():
    point, before = build_point(True)
    out = pn.run_narrative_pipeline(
        point, before, {"type": "protagonist"}, environment=ENV)
    assert out["status"] == "ok", out
    assert out["n1"]["factCount"] == 1, out["n1"]
    assert out["n1"]["diagnostics"] == [], out["n1"]
    assert out["n2"]["selectedFactIds"] == ["f0"], out["n2"]
    assert out["n3"]["groups"] == 1, out["n3"]
    present = out["sceneContext"]["sceneState"]["present"]
    assert present == ["char_pa"], present
    assert not any(x.startswith("npc") for x in present), present
    assert [c["name"] for c in out["sceneContext"]["characterContext"]] ==         ["管线甲"], out["sceneContext"]
    assert out["inputVersion"].startswith("n4-input-pack"), out
    assert "f0｜结果｜管线甲｜把铜铃挂回了钟楼" in out["input"], out["input"]
    # the new N4.0 contract carries records, not pre-written sentences
    assert "管线甲把铜铃挂回了钟楼。" not in out["input"], out["input"]
    # the internal goal may be a substring of the result text? In this
    # fixture it is not a contiguous substring; assert it never leaks.
    assert "把铜铃挂回钟楼" not in out["input"], out["input"]
    assert "task_achieved" not in out["input"], out["input"]

    legacy_out = pn.run_narrative_pipeline(
        point, before, {"type": "protagonist"}, environment=ENV,
        input_format="legacy")
    assert legacy_out["inputVersion"].startswith("n4-legacy-sentence")
    assert "管线甲把铜铃挂回了钟楼。" in legacy_out["input"]

    point2, before2 = build_point(False)
    out2 = pn.run_narrative_pipeline(
        point2, before2, {"type": "protagonist"}, environment=ENV)
    assert out2["status"] == "incomplete", out2
    assert out2["reason"] == "n1-cannot-express", out2
    assert any(d["code"] == "task-outcome-unavailable"
               for d in out2["blocking"]), out2
    assert "input" not in out2, out2

    # legacy N1 default still emits task_achieved + goal
    legacy = np.extract_facts(point2, before2)
    assert [f["kind"] for f in legacy["facts"]] == ["task_achieved"], legacy
    print("narrative pipeline input test: PASS")
    print("input:\n" + out["input"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

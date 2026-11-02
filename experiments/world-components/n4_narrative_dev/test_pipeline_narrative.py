# End-to-end input test for the N4 narrative path with N1 outcome/resultText.
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/test_pipeline_narrative.py

import copy
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import narration_pipeline as np  # noqa: E402
import pipeline_narrative as pn  # noqa: E402


WORLD = {
    "worldId": "w_pipe",
    "locations": {"loc_1": {"name": "管线镇", "appearance": "安静",
                            "sublocations": []}},
    "items": {},
    "characters": {"char_pa": {"name": "管线甲", "appearance": "常态",
                               "personality": "沉稳", "inventory": []}},
}

SCENE = {
    "sceneState": {
        "locationId": "loc_1", "locationPath": ["loc_1"],
        "time": "夜", "weather": "雨", "wind": "无", "light": "灯",
        "present": ["char_pa"], "visibleItems": [], "atmosphere": "安静",
    },
    "characterContext": [{
        "entityId": "char_pa", "name": "管线甲", "personality": "沉稳",
        "appearance": "常态", "inventory": [], "use": "read"}],
}


def build_point(with_result_text=True):
    before_state = np.make_pipeline_state()
    before = np.make_point(1, {}, None, state=before_state, prev=None)
    before = {**before, "pointId": "pt-1", "version": 1}
    state = np.make_pipeline_state()
    task = state["characters"]["char_pa"]["tasks"]["task_1"]
    task["status"] = "achieved"
    if with_result_text:
        task["resultText"] = "把铜铃挂回了钟楼"
    point = np.make_point(2, {"char_pa": {"tasksAchieved": ["task_1"]}},
                          None, state=state, prev="pt-1")
    return point, before


def main():
    point, before = build_point(True)
    out = pn.run_narrative_pipeline(
        point, before, {"type": "protagonist"},
        SCENE, WORLD)
    assert out["status"] == "ok", out
    assert out["n1"]["factCount"] == 1, out["n1"]
    assert out["n1"]["diagnostics"] == [], out["n1"]
    assert out["n2"]["selectedFactIds"] == ["f0"], out["n2"]
    assert out["n3"]["groups"] == 1, out["n3"]
    assert "管线甲把铜铃挂回了钟楼。" in out["input"], out["input"]
    # the internal goal may be a substring of the result text? In this
    # fixture it is not a contiguous substring; assert it never leaks.
    assert "把铜铃挂回钟楼" not in out["input"], out["input"]
    assert "task_achieved" not in out["input"], out["input"]

    point2, before2 = build_point(False)
    out2 = pn.run_narrative_pipeline(
        point2, before2, {"type": "protagonist"},
        SCENE, WORLD)
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

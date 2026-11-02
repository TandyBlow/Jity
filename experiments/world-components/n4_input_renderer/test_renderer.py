# N4 formal component tests: byte-identical approved corpus previews plus
# fail-closed contract cases.
#
# Run: python -X utf8 experiments/world-components/n4_input_renderer/test_renderer.py

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
sys.path.insert(0, str(WC))

from n4_input_renderer import renderer  # noqa: E402

DEV = WC / "n4_narrative_dev"


def _world():
    return {
        "locations": {
            "l1": {"name": "巷口", "appearance": "湿石板"},
            "l2": {"name": "渡口", "appearance": "木桩"},
        },
        "items": {
            "i1": {"name": "绳", "appearance": "粗麻"},
            "i2": {"name": "灯", "appearance": "黄铜"},
        },
        "characters": {"a": {"name": "甲"}, "b": {"name": "乙"}},
    }


def _case(facts, plan=None):
    return {
        "facts": facts,
        "sceneState": {"locationPath": ["l1"], "weather": "雨", "time": "夜",
                       "visibleItems": ["i1"]},
        "characterContext": [{
            "entityId": "a", "name": "甲", "personality": "话少",
            "appearance": "灰衣", "inventory": ["i2"],
        }],
        "perspective": {"entityId": "a"},
        "plan": plan,
    }


def _plan(*groups):
    return {"sentences": [
        {"index": i, "factIds": list(ids), "coreference": [], "time": time}
        for i, (ids, time) in enumerate(groups)
    ]}


def _numbered(text):
    return [line.split(". ", 1)[1] for line in text.splitlines()
            if line[:1].isdigit() and ". " in line]


def expect_error(fn, code):
    try:
        fn()
    except renderer.N4RenderError as exc:
        assert exc.code == code, (exc.code, code)
        return
    raise AssertionError(f"expected {code}")


def test_corpus_regression():
    world = json.loads((DEV / "world.json").read_text(encoding="utf-8"))
    cases = [json.loads(line) for line in
             (DEV / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    grouped = json.loads((DEV / "pipeline_preview.json").read_text(encoding="utf-8"))["cases"]
    flat = json.loads((DEV / "input_preview.json").read_text(encoding="utf-8"))
    assert len(cases) == len(grouped) == len(flat) == 12
    for case, row, flat_row in zip(cases, grouped, flat):
        assert case["id"] == row["id"] == flat_row["id"]
        selected = [d["factId"] for d in row["decisions"] if d["selected"]]
        text = renderer.render_plan_input(
            case, row["plan"], world, strict=True,
            selected_fact_ids=selected)
        assert text == row["input"], case["id"]
        assert renderer.render_input(case, world) == flat_row["input"], case["id"]
    return len(cases)


def test_missing_environment_is_omitted():
    world = _world()
    case = _case([{"factId": "f0", "kind": "no_change"}])
    case["sceneState"].pop("weather")
    case["sceneState"].pop("time")
    text = renderer.render_plan_input(case, _plan((["f0"], None)), world,
                                      strict=True, selected_fact_ids=["f0"])
    assert "天气：" not in text and "时间：" not in text
    assert "这一拍没有新的变化。" in text


def test_time_amount_never_rendered():
    world = _world()
    facts = [{"factId": "f0", "kind": "no_change"},
             {"factId": "f1", "kind": "time", "amount": 13, "unit": "minute"}]
    case = _case(facts)
    text = renderer.render_plan_input(
        case, _plan((["f0", "f1"], {"amount": 13, "unit": "minute"})),
        world, strict=True, selected_fact_ids=["f0", "f1"])
    assert "13" not in text and "分钟" not in text
    assert text.count("过去了一会儿（不写具体时长）") == 1


def test_global_time_fallback():
    world = _world()
    facts = [{"factId": "f0", "kind": "no_change"},
             {"factId": "f1", "kind": "time", "amount": 1, "unit": "minute"}]
    case = _case(facts)
    text = renderer.render_plan_input(
        case, _plan((["f0"], None)), world, strict=True,
        selected_fact_ids=["f0", "f1"])
    assert "时间：过去了一会儿（不写具体时长）。" in text


def test_goal_never_rendered():
    world = _world()
    facts = [{"factId": "f0", "kind": "outcome", "entityId": "a",
              "name": "甲", "goal": "秘密目标", "resultText": "挂好铜铃"}]
    case = _case(facts)
    text = renderer.render_plan_input(case, _plan((["f0"], None)), world,
                                      strict=True, selected_fact_ids=["f0"])
    assert "甲挂好铜铃。" in text
    assert "秘密目标" not in text


def test_plan_order_is_authoritative():
    world = _world()
    facts = [{"factId": "f0", "kind": "moved", "entityId": "a",
              "name": "甲", "from": "巷口", "to": "渡口"},
             {"factId": "f1", "kind": "no_change"}]
    case = _case(facts)
    text = renderer.render_plan_input(case, _plan((["f1"], None), (["f0"], None)),
                                      world, strict=True,
                                      selected_fact_ids=["f0", "f1"])
    assert _numbered(text) == ["这一拍没有新的变化。",
                               "甲从巷口来到渡口。"]


def test_fail_closed():
    world = _world()
    # unknown kind
    case = _case([{"factId": "f0", "kind": "weather_changed", "name": "甲"}])
    expect_error(lambda: renderer.render_fact_line(case["facts"][0]),
                 "unsupported-fact-kind")
    # outcome without resultText
    case = _case([{"factId": "f0", "kind": "outcome", "name": "甲",
                   "goal": "g"}])
    expect_error(lambda: renderer.render_fact_line(case["facts"][0]),
                 "outcome-result-missing")
    # unknown / duplicate plan ids
    case = _case([{"factId": "f0", "kind": "no_change"}])
    expect_error(lambda: renderer.render_plan_input(
        case, _plan((["f9"], None)), world, strict=True,
        selected_fact_ids=["f0"]), "plan-unknown-fact")
    expect_error(lambda: renderer.render_plan_input(
        case, _plan((["f0", "f0"], None)), world, strict=True,
        selected_fact_ids=["f0"]), "duplicate-fact")
    # coverage mismatch
    case = _case([{"factId": "f0", "kind": "no_change"},
                  {"factId": "f1", "kind": "no_change"}])
    expect_error(lambda: renderer.render_plan_input(
        case, _plan((["f0"], None)), world, strict=True,
        selected_fact_ids=["f0", "f1"]), "plan-coverage-mismatch")
    # incomplete character context
    case = _case([{"factId": "f0", "kind": "no_change"}])
    case["characterContext"][0].pop("personality")
    expect_error(lambda: renderer.render_plan_input(
        case, _plan((["f0"], None)), world, strict=True,
        selected_fact_ids=["f0"]), "character-personality-missing")
    # unresolved perspective
    case = _case([{"factId": "f0", "kind": "no_change"}])
    case["perspective"] = {"entityId": "nobody"}
    expect_error(lambda: renderer.render_plan_input(
        case, _plan((["f0"], None)), world, strict=True,
        selected_fact_ids=["f0"]), "world-character-missing")


def test_orchestrator_and_determinism():
    world = _world()
    facts = [{"factId": "f0", "kind": "no_change"}]
    case = _case(facts)
    plan = _plan((["f0"], None))
    first = renderer.render_narrative_input(
        case, plan, world, selected_fact_ids=["f0"],
        scene_diagnostics=[{"code": "environment-field-missing", "field": "wind"}])
    second = renderer.render_narrative_input(
        case, plan, world, selected_fact_ids=["f0"])
    assert first["status"] == second["status"] == "ok"
    assert first["version"] == renderer.N4_VERSION
    assert first["input"] == second["input"]
    assert first["diagnostics"] == [
        {"code": "environment-field-missing", "field": "wind"}]
    bad = renderer.render_narrative_input(
        case, {"sentences": [{"index": 0, "factIds": ["f9"]}]}, world,
        selected_fact_ids=["f0"])
    assert bad["status"] == "error" and bad["code"] == "plan-unknown-fact"


def main():
    count = test_corpus_regression()
    test_missing_environment_is_omitted()
    test_time_amount_never_rendered()
    test_global_time_fallback()
    test_goal_never_rendered()
    test_plan_order_is_authoritative()
    test_fail_closed()
    test_orchestrator_and_determinism()
    print(f"N4 renderer test: PASS ({count} grouped + {count} flat + 7 unit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# N4.0 structured input packing tests.
#
# Run: python -X utf8 experiments/world-components/n4_input_renderer/test_packer.py

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
sys.path.insert(0, str(WC))

from n4_input_renderer import N4_INPUT_VERSION, pack_narrative_input  # noqa: E402

DEV = WC / "n4_narrative_dev"


def _world():
    return {
        "locations": {"l1": {"name": "巷口", "appearance": "湿石板"}},
        "items": {"i1": {"name": "绳", "appearance": "粗麻"}},
        "characters": {"a": {"name": "甲"}},
    }


def _case(facts):
    return {
        "facts": facts,
        "sceneState": {"locationPath": ["l1"], "weather": "雨", "time": "夜",
                       "wind": "无", "light": "灯", "atmosphere": "安静",
                       "visibleItems": ["i1"]},
        "characterContext": [{
            "entityId": "a", "name": "甲", "personality": "话少",
            "appearance": "灰衣", "inventory": [],
        }],
        "perspective": {"entityId": "a"},
    }


def _plan(*groups):
    return {"sentences": [
        {"index": i, "factIds": list(ids), "coreference": [], "time": time}
        for i, (ids, time) in enumerate(groups)
    ]}


def _assert_error(result, code):
    assert result["status"] == "error", result
    assert result["code"] == code, result


def test_12_case_pack():
    world = json.loads((DEV / "world.json").read_text(encoding="utf-8"))
    cases = [json.loads(line) for line in
             (DEV / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    rows = json.loads((DEV / "pipeline_preview.json").read_text(encoding="utf-8"))["cases"]
    for case, row in zip(cases, rows):
        selected = [d["factId"] for d in row["decisions"] if d["selected"]]
        packed = pack_narrative_input(case, row["plan"], world,
                                      selected_fact_ids=selected)
        assert packed["status"] == "ok", (case["id"], packed)
        text = packed["input"]
        assert packed["version"] == N4_INPUT_VERSION
        for sentence in row["plan"]["sentences"]:
            assert f"G{sentence['index'] + 1}｜" in text, (case["id"], sentence)
            for fid in sentence["factIds"]:
                assert f"{fid}｜" in text, (case["id"], fid)
        for f in case["facts"]:
            if f["kind"] == "outcome":
                assert f["resultText"] in text
                # the hidden goal never enters the packed input
                assert f["goal"] not in text, (case["id"], f["goal"])
        # no pre-written legacy sentence rows
        assert "从潮生巷来到旧灯塔。" not in text
        assert "的呼吸比刚才顺了一些。" not in text
        # time amount/unit is not packed
        assert "分钟" not in text and "小时" not in text
        # deterministic
        again = pack_narrative_input(case, row["plan"], world,
                                     selected_fact_ids=selected)
        assert again["input"] == text
    return len(cases)


def test_records_not_sentences():
    world = _world()
    facts = [
        {"factId": "f0", "kind": "moved", "name": "甲",
         "from": "巷口", "to": "渡口"},
        {"factId": "f1", "kind": "outcome", "name": "甲",
         "resultText": "挂好铜铃", "goal": "秘密目标"},
        {"factId": "f2", "kind": "sanity_changed", "name": "甲",
         "from": 70, "to": 80},
        {"factId": "f3", "kind": "time", "amount": 8, "unit": "minute"},
    ]
    case = _case(facts)
    packed = pack_narrative_input(case, _plan((["f0", "f1", "f2", "f3"], {"amount": 8, "unit": "minute"})),
                                   world, selected_fact_ids=["f0", "f1", "f2", "f3"])
    assert packed["status"] == "ok", packed
    text = packed["input"]
    assert "f0｜移动｜甲｜巷口→渡口" in text
    assert "f1｜结果｜甲｜挂好铜铃" in text
    assert "f2｜理智｜甲｜上升" in text
    assert "f3｜时间｜时间经过" in text
    assert "甲从巷口来到渡口。" not in text
    assert "甲的呼吸" not in text
    assert "秘密目标" not in text
    assert "8" not in text and "分钟" not in text
    assert "G1｜f0 f1 f2 f3｜组后时间=过去了一会儿" in text


def test_fail_closed():
    world = _world()
    facts = [{"factId": "f0", "kind": "moved", "name": "甲",
              "from": "巷口", "to": "渡口"}]
    case = _case(facts)
    _assert_error(pack_narrative_input(case, _plan((["f9"], None)), world,
                                        selected_fact_ids=["f0"]),
                  "plan-unknown-fact")
    _assert_error(pack_narrative_input(case, _plan((["f0"], None)), world,
                                        selected_fact_ids=["f0", "f1"]),
                  "selected-unknown-fact")
    bad = _case([{"factId": "f0", "kind": "weather", "name": "甲"}])
    _assert_error(pack_narrative_input(bad, _plan((["f0"], None)), world,
                                        selected_fact_ids=["f0"]),
                  "unsupported-fact-kind")
    no_result = _case([{"factId": "f0", "kind": "outcome", "name": "甲",
                        "goal": "g"}])
    _assert_error(pack_narrative_input(no_result, _plan((["f0"], None)), world,
                                        selected_fact_ids=["f0"]),
                  "outcome-result-missing")
    bad_pov = _case([{"factId": "f0", "kind": "no_change"}])
    bad_pov["perspective"] = {"entityId": "nobody"}
    _assert_error(pack_narrative_input(bad_pov, _plan((["f0"], None)), world,
                                        selected_fact_ids=["f0"]),
                  "world-character-missing")


def main():
    count = test_12_case_pack()
    test_records_not_sentences()
    test_fail_closed()
    print(f"N4.0 packer test: PASS ({count} corpus cases + 2 unit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

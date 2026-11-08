# 判分器单元测试：每条规则一条最小案例。
# 运行：python -X utf8 test_checker.py   （也兼容 pytest）

import json
import pathlib

import checker

WORLD = {
    "worldId": "w_test",
    "characters": {"c1": {"name": "甲"}, "c2": {"name": "乙"}},
    "locations": {
        "l1": {"name": "东街", "sublocations": [{"name": "巷口"}]},
        "l2": {"name": "西桥", "sublocations": []},
    },
    "items": {"i1": {"name": "铜铃"}},
    "tasks": {},
}

CASE = {
    "id": "t1",
    "worldId": "w_test",
    "perspective": {"entityId": "c1"},
    "sceneState": {"locationPath": ["l2"], "present": ["c1"], "atmosphere": "桥下水声"},
    "facts": [
        {"factId": "f0", "kind": "moved", "entityId": "c1", "name": "甲",
         "from": "东街", "to": "西桥"},
        {"factId": "f1", "kind": "outcome", "entityId": "c1", "name": "甲",
         "taskId": "task_x", "goal": "把铜铃挂到西桥", "resultText": "把铜铃挂到西桥"},
        {"factId": "f2", "kind": "sanity_changed", "entityId": "c1", "name": "甲",
         "from": 8, "to": 10},
        {"factId": "f3", "kind": "time", "entityId": None, "name": None,
         "amount": 6, "unit": "minute"},
    ],
}


def verdict(text, case=None):
    r = checker.check_case(case or CASE, text, WORLD)
    return r["verdict"], {c["rule"] for c in r["checks"] if c["verdict"] == "fail"}


LEGIT = "甲从东街走到西桥，把铜铃挂好。胸口松了一些。"


def test_legit_passes():
    v, fails = verdict(LEGIT)
    assert v == "pass", (v, fails)


def test_scene_ellipsis_is_not_fail():
    # 已经站在西桥，只写"上了桥"，不写从哪儿来
    v, _ = verdict("甲上了西桥，在桥边站住，把铜铃挂好。")
    assert v != "fail"


def test_synonym_is_not_fail():
    v, fails = verdict("甲打东街过来，到了西桥，把铜铃挂上。胸口松了一些。")
    assert v != "fail", fails


def test_reverse_direction_fails():
    v, fails = verdict("甲从西桥走到东街，把铜铃挂好。胸口松了一些。")
    assert v == "fail" and "fact.moved.direction" in fails, fails


def test_outcome_actor_swap_fails():
    v, fails = verdict("甲从东街走到西桥。乙把铜铃挂到桥头。胸口松了一些。")
    assert v == "fail" and fails & {"fact.outcome.subject", "fact.attribution"}, fails


def test_missing_person_fails():
    v, fails = verdict("东街到西桥的路上没有人，铜铃挂在桥头。")
    assert v == "fail" and fails & {"fact.moved.subject", "fact.outcome.subject"}, fails


def test_goal_marker_fails():
    v, fails = verdict(LEGIT + "他想起还有任务没做完。")
    assert v == "fail" and "forbidden.goal" in fails, fails


def test_goal_text_alone_is_allowed():
    # 目标原文与结果动作同形时，写出来是合法的
    v, fails = verdict(LEGIT)
    assert "forbidden.goal" not in fails


def test_numeric_panel_fails():
    v, fails = verdict(LEGIT + "理智从8升到10。")
    assert v == "fail" and fails & {"forbidden.numeric", "forbidden.digit"}, fails


def test_explicit_duration_fails():
    v, fails = verdict(LEGIT + "他走了六分钟。")
    assert v == "fail" and "forbidden.duration" in fails, fails


def test_other_inner_thought_fails():
    v, fails = verdict(LEGIT + "乙心里一沉。")
    assert v == "fail" and "pov.innerOther" in fails, fails


def test_pov_inner_thought_is_allowed():
    v, fails = verdict(LEGIT + "甲心里松了一口气。")
    assert v == "pass", fails


def test_sanity_direction_wrong_fails():
    case = json.loads(json.dumps(CASE))
    case["facts"] = [f for f in case["facts"] if f["factId"] == "f2"]
    v, fails = verdict("甲站在桥头，胸口一阵发紧，喘不上气。", case)
    assert v == "fail" and "fact.sanity.direction" in fails, fails


def test_unknown_name_is_uncertain():
    v, fails = verdict(LEGIT + "赵渡站在桥头，没说话。")
    assert v == "uncertain" and "fabrication.name" in {
        c["rule"] for c in checker.check_case(CASE, LEGIT + "赵渡站在桥头，没说话。", WORLD)["checks"]
        if c["verdict"] == "uncertain"}, fails


def test_repetition_is_uncertain():
    r = checker.check_case(CASE, LEGIT + "甲把铜铃挂好。" + "甲把铜铃挂好。", WORLD)
    assert r["verdict"] == "uncertain"
    assert "style.repetition" in {c["rule"] for c in r["checks"]
                                  if c["verdict"] == "uncertain"}


def test_every_fail_carries_evidence():
    r = checker.check_case(CASE, "甲从西桥走到东街，乙把铜铃挂好。理智从8升到10。", WORLD)
    assert r["verdict"] == "fail"
    for c in r["checks"]:
        if c["verdict"] == "fail":
            assert c["evidence"], c
            assert "rule" in c


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as e:
                failed += 1
                print("FAIL", name, e)
    print("failed:", failed)
    raise SystemExit(1 if failed else 0)

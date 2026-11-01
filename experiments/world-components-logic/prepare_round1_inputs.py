"""Build review-pending round1 input supplements without running any model.

--check compares exact bytes. --write-new only creates absent files; a different
existing version is refused before any path is written. Original cards, labels,
receipts, lab.py and the user-edited README are never written by this tool.
"""
from __future__ import annotations

import argparse
import copy
from collections import Counter
import hashlib
import json
from pathlib import Path

import lab
from round1_input_specs import D02, D02_COMMANDS, D03, D04, D05, CHAIN_SCENES

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
DATA = BASE / "data/round1-inputs"
SOURCE = BASE / "data/round1"
REPORT = ROOT / "artifacts/world-components-logic/l3-3-input-coverage.md"
SOURCE_COMMIT = "e1e85986d75c960b2b5be0f7af257a98f6d4f292"
SCHEMA = "jity-d-round1-input-drafts-v1"
SPLITS = ("development", "sealed_candidate")
PERSON_IDS = ("a", "b", "c", "d")
STAGE_CUT = {"D02": "before_actor_decision", "D03": "frozen_source_before_current_targets",
             "D04": "frozen_threats_after_actual_admission_before_response",
             "D05": "closed_group_before_joint_results"}
SOURCE_FILES = ("source-cards.jsonl", "rubric-drafts.jsonl", "source-manifest.json")
# Verified against git show e1e8598:<path>; do not silently bind a different
# source revision to the same authoring supplement batch.
SOURCE_FILE_SHA256 = {
    "source-cards.jsonl": "fe0b9d2a877619b94d8faacc965dd300385bd2dd9afff84da9b6c08a7f6a6742",
    "rubric-drafts.jsonl": "0db0de16364a6fee91e75640d88f4f36f07a2371bb98ef9613d5240c19a60e6b",
    "source-manifest.json": "7274d68dba56240e2cdb9d4c173d652c1e51367015ab46b6dc8a584c4f52ed79",
}


def sha(value):
    return hashlib.sha256(lab.canonical_bytes(value)).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def jsonl_bytes(rows):
    return b"".join(lab.canonical_bytes(row) + b"\n" for row in rows)


def world_from(spec):
    """Pure registration/identity construction, not a behavioral decision."""
    places = [{"id": "room" if i == 0 else "remote" if i == 1 else f"p{i}",
               "name": name, "parentId": None, "appearance": "当前可见的登记工作区域。"}
              for i, name in enumerate(spec["places"])]
    def position(value):
        return "remote" if value == "p1" else value
    items = [{"id": f"i{i}", "name": name, "position": position(at), "appearance": text}
             for i, (name, at, text) in enumerate(spec["items"])]
    people = [{"id": PERSON_IDS[i], "name": name, "position": position(at),
               "appearance": f"{name}在登记位置，当前没有另述的能力或伤损。",
               "tasks": [{"id": f"task_{PERSON_IDS[i]}_1", "text": task,
                           "status": "pending", "parentId": None}],
               "personality": [personality], "sanity": 70}
              for i, (name, at, task, personality) in enumerate(spec["people"])]
    return {"time": {"calendar": "gregorian", "dateTime": "2026-11-01T09:00:01", "instantOrdinal": 0},
            "places": places, "items": items, "characters": people}


def frozen(member, text):
    return {"memberId": member, **({"actionText": text} if text is not None else {})}


def fixture_identity(case_id):
    prefix = "r1f_" + hashlib.sha256(case_id.encode()).hexdigest()[:16]
    return {key: prefix + "_" + suffix for key, suffix in
            (("worldId", "world"), ("advanceId", "advance"), ("inputId", "input"), ("roundId", "round"),
             ("pointId", "point"), ("groupId", "group"))}


def judgment(case_id, source, target, value, eligible=True, serial=0):
    """Program-owned reaction-d20-v1 fixture; never random or model assigned."""
    return {"sourceId": source, "targetId": target,
            "rollId": fixture_identity(case_id)["groupId"] + f"_roll_{source}_{target}_{serial}",
            "ruleVersion": "reaction-d20-v1", "value": value, "threshold": 11,
            "passed": value >= 11, "eligible": eligible,
            "admitted": eligible and value >= 11}


def case_for(card, value, *, case_id=None, derived=False):
    return {"caseId": case_id or card["caseId"], "sourceGroup": card["sourceGroup"],
            "anchorCase": not derived, "derivedFrom": card["caseId"] if derived else None,
            "split": card["split"], "purpose": "review_pending_input_supplement",
            "task": card["task"], "stageCut": STAGE_CUT[card["task"]], "input": value}


def roll_bindings(case):
    value = case["input"]
    rows = value.get("knownPriorJudgments", value.get("judgments", value.get("group", {}).get("judgments", [])))
    identity = fixture_identity(case["caseId"])
    return [{**identity, "sourceId": row["sourceId"], "targetId": row.get("targetId"),
             "triggerKey": identity["groupId"] + f"_trigger_{row['sourceId']}_{row['targetId']}" if "targetId" in row else None,
             "rollId": row.get("rollId"), "status": "authored_fixture_not_service_receipt" if "targetId" in row else "damaged_identity_no_binding"}
            for row in rows]


def group_history(case_id, root, actions, edges):
    """Construct the declared fixture history in DFS order from fixed edges.

    Targets/actions here are past, already-confirmed authoring facts for D05.
    This helper is never used to predict targets or actions in a short chain.
    """
    texts = dict(actions)
    targets = {member: [] for member in texts}
    for source, target, _ in edges:
        targets[source].append(target)
    accepted = {root}
    rows, events = [], [{"kind": "freeze_action", **frozen(root, texts[root])}]
    remaining = list(edges)
    def visit(source):
        events.append({"kind": "confirm_targets", "sourceId": source, "targetIds": targets[source]})
        for target in targets[source]:
            if not remaining or remaining[0][:2] != (source, target):
                raise ValueError(f"{case_id}: declared edges are not the DFS fixture sequence")
            _, _, value = remaining.pop(0)
            if value is None:
                events.append({"kind": "missing_judgment", "sourceId": source, "targetId": target})
                continue  # damaged guard only; never guess the lost dice value
            row = judgment(case_id, source, target, value, target not in accepted)
            rows.append(row)
            events.append({"kind": "actual_judgment", **row})
            if row["admitted"]:
                if target not in texts:
                    raise ValueError(f"{case_id}: admitted member has no declared action")
                accepted.add(target)
                events.append({"kind": "freeze_action", **frozen(target, texts[target])})
                visit(target)
    visit(root)
    if remaining or accepted != set(texts):
        raise ValueError(f"{case_id}: no legal single-initiator admission path to every member")
    return rows, [{"sourceId": source, "targetIds": target_ids} for source, target_ids in targets.items()], events


def task_input(card):
    task, split = card["task"], card["split"]
    index = int(card["caseId"].rsplit("-", 1)[1]) - 1
    cid = card["caseId"]
    supplement = {"assumptions": [
        "新增位置、物品状态、任务全文与个性全文均为出题补充，尚待人审；并非原卡意见的自动延伸。",
        "日期时间、人物理智70和无另述能力/伤损是新设定；不是实测世界或服务回执。"],
        "damage": None, "fixtureEvents": [], "fixtureInitiatorId": None}
    if task == "D02":
        world = world_from(D02[split][index])
        actor, status, command = D02_COMMANDS[split][index]
        if (split, index) in (("development", 5), ("sealed_candidate", 5)):
            world["characters"][0]["tasks"] = [
                {"id": "task_a_1", "text": "完成试灯" if split == "development" else "检查背景布固定点",
                 "status": "achieved", "parentId": None},
                {"id": "task_a_2", "text": "等待书面复演通知" if split == "development" else "等开拍通知前保持布景不动",
                 "status": "pending", "parentId": None}]
        value = {"world": world, "actorId": actor, "protagonistId": "a",
                 "advance": {"inputText": command, "intentStatus": status}, "confirmedPrefix": []}
    elif task == "D03":
        spec, source, text = D03[split][index]
        world = world_from(spec)
        members, prior, acted = [frozen(source, text)], [], []
        if index == 6:
            acted = ["b"]
            supplement["assumptions"].append("乙的已行动原文属于此前已确认前缀；本题只提供其资格标记，不重采样该行动。")
        elif index == 7:
            # A registered earlier source makes the current reaction's frozen
            # admission prefix explicit. No outgoing judgment from a is known.
            world["characters"].append({"id": "d", "name": "丁／先前源", "position": "room",
                "appearance": "丁已在本组冻结先前推送动作。", "tasks": [{"id": "task_d_1", "text": "交接盒子" if split == "development" else "调整滑轮", "status": "pending", "parentId": None}],
                "personality": ["按交接任务操作"], "sanity": 70})
            past = "丁沿台面把盒子推向甲。" if split == "development" else "丁移动滑轮朝甲。"
            members.insert(0, frozen("d", past))
            prior = [judgment(cid, "d", "a", 14)]
            acted = ["d"]
            supplement["assumptions"].append("新增丁及丁的已冻结威胁、14/11准入作为反应源的过去前缀；这不是当前源甲的未来判定。")
        elif index == 8:
            past = "甲朝自己一侧拉登记牵绳。" if split == "development" else "甲推共用门扇。"
            members.insert(0, frozen("a", past))
            prior = [judgment(cid, "a", "b", 16)]
            acted = ["a"]
            supplement["assumptions"].append("原卡未给甲到乙的过去骰点，本补充固定16/11，用于解释已冻结的乙；需新审。")
        elif index == 9:
            past = "甲敲击登记敲击块。" if split == "development" else "甲调整反光片照向乙的工位。"
            members.insert(0, frozen("a", past))
            prior = [judgment(cid, "a", "b", 8), judgment(cid, "a", "c", 14)]
            acted = ["a"]
            supplement["fixtureInitiatorId"] = "a"
            supplement["fixtureEvents"] = [
                {"kind": "freeze_action", **frozen("a", past)},
                {"kind": "confirm_targets", "sourceId": "a", "targetIds": ["b", "c"]},
                {"kind": "actual_judgment", **prior[0]},
                {"kind": "actual_judgment", **prior[1]},
                {"kind": "freeze_action", **frozen(source, text)},
            ]
            supplement["assumptions"].append("补充甲先发起且其信号也影响丙：按乙、丙处理，甲→乙8/11未准入，甲→丙14/11准入后冻结原卡的丙动作。原卡未给这些过去点数和准入，均须新审；当前源丙的未来目标/骰点不可见。")
        value = {"world": world, "source": frozen(source, text),
                 "candidateIds": [p["id"] for p in world["characters"]],
                 "alreadyActedIds": sorted(set(acted) | {m['memberId'] for m in members}),
                 "confirmedGroup": {"members": members},
                 "knownPriorJudgments": prior}
    elif task == "D04":
        spec, text, number = D04[split][index]
        world = world_from(spec)
        source = frozen("a", text)
        members = [copy.deepcopy(source)]
        eligible, admitted = index != 7, index not in (6, 7)
        rows = [judgment(cid, "a", "b", number, eligible)] if number is not None else []
        if index == 4:
            other = "丙推右侧空架朝乙。" if split == "development" else "丙拉共用桌板右端。"
            members.insert(0, frozen("c", other))
            rows = [judgment(cid, "c", "b", 8 if split == "development" else 7),
                    judgment(cid, "c", "a", 14), *rows]
            supplement["fixtureInitiatorId"] = "c"
            supplement["fixtureEvents"] = [
                {"kind": "freeze_action", **frozen("c", other)},
                {"kind": "confirm_targets", "sourceId": "c", "targetIds": ["b", "a"]},
                {"kind": "actual_judgment", **rows[0]},
                {"kind": "actual_judgment", **rows[1]},
                {"kind": "freeze_action", **source},
                {"kind": "confirm_targets", "sourceId": "a", "targetIds": ["b"]},
                {"kind": "actual_judgment", **rows[2]},
            ]
            supplement["assumptions"].append("新增过去前缀：丙先发起，目标按乙、甲处理；乙先因低骰点未准入，丙→甲14/11使甲准入并冻结原卡的甲动作；随后甲→乙通过，才进入本反应截点。两条原卡威胁均已发生，不含乙的未来行动。")
        if index == 7:
            members.append(frozen("b", "乙拧紧登记旋钮。" if split == "development" else "乙用双手托住登记盘。"))
        if index == 8:
            supplement["damage"] = {"path": "input.source.actionText", "kind": "empty_frozen_text" if text == "" else "missing_frozen_text", "rawSource": copy.deepcopy(source)}
        if index == 9:
            if split == "development":
                rows = [{"sourceId": "a", "targetId": "b", "rollId": fixture_identity(cid)["groupId"] + "_damaged_roll"}]
                supplement["damage"] = {"path": "input.judgments[0]", "kind": "missing_rule_value_threshold_flags", "rawJudgment": copy.deepcopy(rows[0])}
            else:
                # Preserve the actual missing target identity. Do not turn it
                # into an empty list, invent b, or claim this projects in lab.
                damaged = judgment(cid, "a", "b", 14)
                del damaged["targetId"]
                rows = [damaged]
                supplement["damage"] = {"path": "input.judgments[0].targetId", "kind": "missing_target_identity", "rawJudgment": copy.deepcopy(damaged), "projectionBlocked": True}
        value = {"world": world, "memberId": "b", "source": source,
                 "admission": {"eligible": eligible, "admitted": admitted},
                 "alreadyActedIds": sorted({m['memberId'] for m in members}),
                 "previouslySkippedIds": ["b"] if index == 3 else [],
                 "confirmedGroup": {"members": members}, "judgments": rows}
    elif task == "D05":
        spec, root, actions, edges = D05[split][index]
        world = world_from(spec)
        # A damaged member is still registered and admitted. Its absent text
        # remains absent in the payload; no placeholder action is supplied.
        rows, targets, events = group_history(cid, root, actions, edges)
        if index == 7:
            missing = next(person for person, text in actions if text is None)
            for event in events:
                if event.get("kind") == "freeze_action" and event.get("memberId") == missing:
                    event.pop("actionText", None)
                    event["payloadStatus"] = "missing_original_text"
            supplement["damage"] = {"path": f"input.group.members[{missing}].actionText", "kind": "missing_member_action", "memberId": missing}
        if split == "development" and index == 8:
            rows = rows[:1]
            supplement["damage"] = {"path": "input.group.judgments", "kind": "missing_relation_record", "missingRelation": {"sourceId": "b", "targetId": "a"}}
        if split == "sealed_candidate" and index == 8:
            rows.append(judgment(cid, "a", "b", 18, True, serial=1))
            supplement["damage"] = {"path": "input.group.judgments", "kind": "duplicate_relation_ambiguous_authority", "rawJudgments": copy.deepcopy(rows)}
            events.append({"kind": "ambiguous_duplicate_judgment", **rows[-1]})
        closed = index != 9
        if not closed:
            # No assertion that b's empty target set was accepted. This is the
            # exact boundary the guard must refuse, not a valid closed group.
            targets = [record for record in targets if record["sourceId"] != "b"]
            events = [event for event in events if not (event.get("kind") == "confirm_targets" and event.get("sourceId") == "b")]
            supplement["damage"] = {"path": "input.group.closed", "kind": "unfinished_source", "frontierIds": ["b"], "emptyTargetsConfirmed": False}
        else:
            events.append({"kind": "close_group", "memberIds": [person for person, _ in actions]})
        value = {"world": world, "group": {"closed": closed,
                 "memberIds": [person for person, _ in actions],
                 "members": [frozen(person, text) for person, text in actions],
                 "confirmedTargets": targets, "judgments": rows, "alreadyActedIds": []}}
        supplement["fixtureInitiatorId"], supplement["fixtureEvents"] = root, events
    else:
        raise ValueError(task)
    case = case_for(card, value)
    supplement["contextFacts"] = copy.deepcopy(value["world"])
    supplement["fixtureIdentity"] = fixture_identity(cid)
    supplement["fixtureStage"] = {"stageCut": case["stageCut"], "timeAdvanceAlreadyApplied": True,
        "inputProjectionHash": sha(value), "fenceEpoch": 1, "acceptedAttempt": 1,
        "provenance": "authored_offline_fixture_not_actual_service", "actualServiceReceipt": None}
    supplement["judgmentBindings"] = roll_bindings(case)
    return case, supplement


def chain_input(card, number):
    world = world_from(CHAIN_SCENES[number])
    commands = ["封好自己的标签袋。", "把登记托架交给乙。", "把甲端标记转到要求方向。", "调整登记支撑板位置。",
                "把自己的票夹交给乙。", "调整图板支座位置。", "把登记样本盘交给乙。", "把标尺零点对齐左线。", "核对并拼装登记陶片。", "核对手中登记册页码。"]
    prefix = [frozen("b", "乙稳住登记图板。")] if number == 5 else []
    order = [person["id"] for person in world["characters"]]
    if number in (5, 6, 9):
        order = ["b", "a"]
    initial = {"world": world, "actorId": "a" if number != 9 else "b", "protagonistId": "a",
               "advance": {"inputText": commands[number], "intentStatus": "pending"},
               "confirmedPrefix": prefix}
    state = {"frozenOrder": order, "actedIds": ["b"] if number == 5 else [],
             "visitedIds": ["b"] if number in (5, 6) else [],
             "cursor": 1 if number in (5, 6) else 0,
             "confirmedActions": prefix, "confirmedTargetSets": [], "judgments": []}
    return {"caseId": card["caseId"], "sourceGroup": card["sourceGroup"], "split": card["split"],
            "sourceCardId": card["caseId"], "sourceCardSha256": sha(card),
            "purpose": "short_chain_initial_state_and_unexecuted_plan",
            "initialCase": {**case_for({**card, "task": "D02"}, initial), "caseId": card["caseId"] + "-initial"},
            "initialControl": state,
            "fixtureIdentity": fixture_identity(card["caseId"]),
            "dynamicPlan": {
                "runnerStatus": "not_implemented", "actualPredictions": None,
                "steps": ["D02从真实当前人物输入预测act/skip，act经程序确认后冻结",
                          "仅对实际冻结源调用D03；保存完整目标集，含真实预测的空集",
                          "仅对已确认关系由夹具程序构造reaction-d20-v1判定及trigger/roll身份",
                          "准入且未行动才调用D04；冻结一次后继续实际D03扩张，已行动仅复用",
                          "所有实际来源/威胁完成才闭组，D05每个实际闭组一次；保存失败和未触发分支"],
                "dicePolicy": {"ruleVersion": "reaction-d20-v1", "threshold": 11,
                               "assignment": "program_only_after_actual_target_confirmation",
                               "seed": None, "values": None},
                "controlInjection": "after_first_actual_response_frozen_pause_then_resume_same_prefix" if number == 3 else None,
                "segmentBoundary": {"kindSequence": ["instant", "linked"], "preserveFrozenOrder": True,
                                    "timeAuthority": "peripheral_fixture_not_D08_validation"} if number == 8 else None,
                "contractStatus": "blocked_contract_g03" if number == 9 else "offline_fixture_plan_only"},
            "peripheralFixtures": ["时间推进/六阶段更新/叙事ready均未实现，不计D02-D05语义能力或完整游戏闭环"],
            "newAssumptions": ["完整实体、位置、任务、个性、时间与理智均为待人审新补充", "本文件只有已知初态；动态目标、反应、结果及骰点未填写"],
            "modelExecutionAuthorized": False, "trainingQuota": 0, "humanReview": "pending"}


def inspect_case(case):
    """Check actual lab interfaces; invalid guard payloads stay inspectable."""
    guard = lab.guard_case(case)
    try:
        projection = lab.build_model_input(case)
        return {"structuralStatus": "valid", "guard": guard,
                "inputSha256": sha(case["input"]), "modelProjectionSha256": sha(projection),
                "projectionEqualsInput": projection == case["input"]}
    except lab.LabValidationError as error:
        return {"structuralStatus": "invalid_intentional_guard", "guard": guard,
                "inputSha256": sha(case["input"]), "modelProjectionSha256": None,
                "projectionEqualsInput": False, "projectionError": str(error)}


def preflight_probe(probe):
    if probe["executionControl"].get("cancelled"):
        return {"shouldCall": False, "reason": "cancelled_before_inference"}
    return lab.guard_case(probe["case"])


def check_registered_world(world):
    """Guard these simple fixture graphs in addition to lab's field checks."""
    places = {row["id"] for row in world["places"]}
    parents = {row["id"]: row["parentId"] for row in world["places"]}
    for row in world["items"] + world["characters"]:
        if not isinstance(row["position"], str):
            raise ValueError("this authoring batch requires an explicit registered container ID")
        parents[row["id"]] = row["position"]
    for start in parents:
        current, seen = start, set()
        while current is not None:
            if current not in parents or current in seen:
                raise ValueError("unregistered or cyclic world position graph")
            seen.add(current)
            current = parents[current]
        if not (seen & places):
            raise ValueError("position graph never reaches a registered place")
    task_ids = [task["id"] for person in world["characters"] for task in person["tasks"]]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("task IDs must be globally unique within the fixture world")


def verify_chain_initial(chain):
    value, state = chain['initialCase']['input'], chain['initialControl']
    order, cursor = state['frozenOrder'], state['cursor']
    people = {p['id'] for p in value['world']['characters']}
    if (set(order) != people or len(order) != len(people)
            or type(cursor) is not int or not 0 <= cursor < len(order)
            or order[cursor] != value['actorId']):
        raise ValueError('chain cursor/order must identify the current actor')
    if set(state['visitedIds']) != set(order[:cursor]):
        raise ValueError('chain visited slots disagree with the frozen order/cursor')
    frozen_ids = {p['memberId'] for p in state['confirmedActions']}
    if (state['confirmedActions'] != value['confirmedPrefix']
            or set(state['actedIds']) != frozen_ids
            or not frozen_ids <= set(state['visitedIds'])
            or value['actorId'] in frozen_ids):
        raise ValueError('chain acted/frozen prefix disagrees with the initial cursor')


def build_materials():
    for name, expected in SOURCE_FILE_SHA256.items():
        if lab.sha256_file(SOURCE / name) != expected:
            raise ValueError(f"source revision 2 byte identity changed: {name}")
    cards = lab.load_jsonl(SOURCE / "source-cards.jsonl")
    source_manifest = json.loads((SOURCE / "source-manifest.json").read_text(encoding='utf-8'))
    if source_manifest["revision"] != 2:
        raise ValueError("input supplements require source-card revision 2")
    for name in SOURCE_FILES[:2]:
        if lab.sha256_file(SOURCE / name) != source_manifest["files"][name]:
            raise ValueError(f"source identity mismatch: {name}")
    cases, supplements, chains = [], [], []
    for card in cards:
        if card["task"] == "CHAIN":
            chains.append(chain_input(card, len(chains)))
        else:
            case, context = task_input(card)
            cases.append(case)
            supplements.append({"caseId": case["caseId"], "sourceGroup": card["sourceGroup"],
                "split": card["split"], "sourceCardId": card["caseId"],
                "sourceCardSha256": sha(card), "sourceCardInputSha256": sha(card["input"]),
                "contextStatus": "authored_supplement_pending_new_human_review", **context})
    # Counterfactual fixtures share source group/split, while a distinct fixture
    # execution namespace avoids changing a previously frozen business-key roll.
    for anchor_id, value in (("r1-dev-d04-02", 20), ("r1-sealed-d04-02", 11),
                             ("r1-dev-d05-06", 20), ("r1-sealed-d05-06", 19)):
        anchor = next(case for case in cases if case["caseId"] == anchor_id)
        derived = copy.deepcopy(anchor)
        derived["caseId"] = anchor_id + f"-dice-{value}"
        derived["anchorCase"], derived["derivedFrom"] = False, anchor_id
        rows = derived["input"].get("judgments", derived["input"].get("group", {}).get("judgments", []))
        current = rows[0]
        rows[0] = judgment(derived["caseId"], current["sourceId"], current["targetId"], value, current["eligible"])
        cases.append(derived)
        supplement = copy.deepcopy(next(s for s in supplements if s["caseId"] == anchor_id))
        supplement.update(caseId=derived["caseId"], fixtureIdentity=fixture_identity(derived["caseId"]),
                          judgmentBindings=roll_bindings(derived), fixtureEvents=[])
        supplement["fixtureStage"]["inputProjectionHash"] = sha(derived["input"])
        supplement["assumptions"].append("同源骰点对照仅变实际点数及独立执行身份，世界/动作/目标不变；不是修改已保存骰点。")
        supplements.append(supplement)
    anchor = cases[0]
    missing, cancelled = copy.deepcopy(anchor), copy.deepcopy(anchor)
    for case, suffix in ((missing, "missing-input"), (cancelled, "cancelled")):
        case.update(caseId=anchor["caseId"] + "-probe-" + suffix,
                    anchorCase=False, derivedFrom=anchor["caseId"], purpose="auxiliary_guard_probe_outside_90_group_quota")
    missing["input"]["advance"]["inputText"] = None
    probes = [{"probeId": case["caseId"], "case": case,
               "sourceCardId": anchor["caseId"], "sourceCardSha256": sha(cards[0]),
               "sourceGroup": anchor["sourceGroup"], "split": anchor["split"],
               "executionControl": {"cancelled": is_cancelled}, "outside90GroupQuota": True,
               "modelExecutionAuthorized": False, "trainingQuota": 0,
               "newHumanReview": "pending"}
              for case, is_cancelled in ((missing, False), (cancelled, True))]
    return cards, cases, supplements, chains, probes


def verify_closed_path(case, supplement):
    """Deterministic fixture-path check, not natural-language evaluation."""
    if case["task"] != "D05" or not lab.guard_case(case)["shouldCall"]:
        return
    group = case["input"]["group"]
    accepted = {supplement["fixtureInitiatorId"]}
    for row in group["judgments"]:
        if row["sourceId"] not in accepted:
            raise ValueError("judgment source has no frozen/admitted path")
        if row["eligible"] != (row["targetId"] not in accepted):
            raise ValueError("eligibility disagrees with the frozen admission prefix")
        if row["admitted"]:
            accepted.add(row["targetId"])
    if accepted != set(group["memberIds"]):
        raise ValueError("closed member has no legal admission path")


def validate_materials(cards, cases, supplements, chains, probes):
    anchors = [case for case in cases if case["anchorCase"]]
    if len(cards) != 90 or len(anchors) != 80 or len(chains) != 10 or len(cases) != 84:
        raise ValueError("90 source groups require 80 anchors + 10 chain plans; four dice derivatives are extra cases")
    if len({case["sourceGroup"] for case in anchors} | {c["sourceGroup"] for c in chains}) != 90:
        raise ValueError("source groups lost or duplicated")
    by_id = {s["caseId"]: s for s in supplements}
    if len(by_id) != len(cases) or len({case["caseId"] for case in cases}) != len(cases):
        raise ValueError("case/supplement IDs must be unique and paired")
    source_by_id = {card["caseId"]: card for card in cards}
    status = {case["caseId"]: inspect_case(case) for case in cases}
    invalid = [case_id for case_id, record in status.items() if record["structuralStatus"] != "valid"]
    if invalid != ["r1-sealed-d04-10"]:
        raise ValueError(f"unexpected structural failure: {invalid}")
    if "targetId" not in status[invalid[0]]["projectionError"]:
        raise ValueError("the intentional invalid input must preserve its missing targetId")
    expected = {"D02": ["ready"] * 10, "D03": ["ready"] * 10,
                "D04": ["ready"] * 6 + ["not_admitted", "already_acted_reuse", "missing_frozen_source_text", "missing_or_invalid_judgment"],
                "D05": ["ready"] * 7 + ["missing_member_action", "missing_or_duplicate_relation_judgment", "group_not_closed"]}
    for case in cases:
        check_registered_world(case["input"]["world"])
        record = status[case["caseId"]]
        anchor_id = case["derivedFrom"] or case["caseId"]
        origin, supplement = source_by_id[anchor_id], by_id[case["caseId"]]
        if (case["sourceGroup"], case["split"], case["task"]) != (origin["sourceGroup"], origin["split"], origin["task"]):
            raise ValueError("case changed its original source group/split/task")
        if (supplement["sourceCardId"] != anchor_id or supplement["sourceCardSha256"] != sha(origin)
                or supplement["contextFacts"] != case["input"]["world"]
                or supplement["fixtureIdentity"] != fixture_identity(case["caseId"])
                or supplement["fixtureStage"]["inputProjectionHash"] != sha(case["input"])
                or supplement["judgmentBindings"] != roll_bindings(case)):
            raise ValueError("supplement/source/projection identity mismatch")
        index = int(anchor_id.rsplit("-", 1)[1]) - 1
        reason = expected[case["task"]][index]
        if anchor_id == "r1-sealed-d04-10":
            reason = "invalid_input"
        if record["guard"]["reason"] != reason:
            raise ValueError(f"{case['caseId']}: {record['guard']['reason']} != declared guard {reason}")
        verify_closed_path(case, by_id[case["caseId"]])
    # Actual lab aggregate validation, with the raw structurally invalid guard
    # separately listed rather than repaired or claimed as valid.
    valid = [case for case in cases if status[case["caseId"]]["structuralStatus"] == "valid"]
    reviews = [{"caseId": case["caseId"], "coverageTags": [], "humanReview": "pending",
                "draftExpected": {"annotationStatus": "new_input_pending_review"}} for case in valid]
    checked = lab.validate_dataset(valid, reviews)
    if not checked["valid"]:
        raise ValueError(checked["problems"])
    for chain in chains:
        verify_chain_initial(chain)
        check_registered_world(chain["initialCase"]["input"]["world"])
        if lab.guard_case(chain["initialCase"])["reason"] != "ready":
            raise ValueError("chain initial input cannot be projected")
        lab.build_model_input(chain["initialCase"])
        if chain["initialControl"]["confirmedTargetSets"] or chain["initialControl"]["judgments"]:
            raise ValueError("chain initial state leaked dynamic targets/judgments")
        if chain["dynamicPlan"]["actualPredictions"] is not None:
            raise ValueError("chain has fabricated actual predictions")
    if [preflight_probe(probe)["reason"] for probe in probes] != ["missing_input_text", "cancelled_before_inference"]:
        raise ValueError("auxiliary guard probes do not block")
    return status, {"sourceGroupCount": 90, "independentTaskAnchors": 80,
        "shortChainInitialPlans": 10, "diceDerivedCases": 4, "taskCaseCount": 84,
        "auxiliaryD02ProbesOutsideQuota": 2, "structurallyValidTaskCases": len(valid),
        "rawStructurallyInvalidGuardCases": invalid,
        "guardReasons": dict(Counter(record["guard"]["reason"] for record in status.values())),
        "chainRunnerStatus": "not_implemented", "modelExecutionAuthorized": False,
        "trainingQuota": 0, "humanReview": "pending_new_input_review", "sourceIndependence": "unverified",
        "formalVerdict": "not_evaluated", "semanticQuality": "unverified", "latencyStatus": "latency_unverified"}


def build_files():
    cards, cases, supplements, chains, probes = build_materials()
    status, summary = validate_materials(cards, cases, supplements, chains, probes)
    checks = [{"caseId": case["caseId"], "caseSha256": sha(case), **status[case["caseId"]],
               "humanReview": "pending", "modelExecutionAuthorized": False} for case in cases]
    files = {DATA / "task-inputs.jsonl": jsonl_bytes(cases),
             DATA / "development-inputs.jsonl": jsonl_bytes([c for c in cases if c['split'] == 'development']),
             DATA / "context-supplements.jsonl": jsonl_bytes(supplements),
             DATA / "input-checks.jsonl": jsonl_bytes(checks),
             DATA / "chain-plans.jsonl": jsonl_bytes(chains),
             DATA / "auxiliary-guard-probes.jsonl": jsonl_bytes(probes)}
    manifest = {"schema": SCHEMA, "revision": 1, "createdDate": "2026-11-01", "status": "draft_not_frozen",
        "sourceCards": {"commit": SOURCE_COMMIT, "revision": 2,
                        "files": {name: lab.sha256_file(SOURCE / name) for name in SOURCE_FILES}},
        "authoringCode": {name: lab.sha256_file(BASE / name) for name in ("round1_input_specs.py", "prepare_round1_inputs.py")},
        "labContractSha256": lab.sha256_file(BASE / "lab.py"),
        "files": {path.name: hashlib.sha256(raw).hexdigest() for path, raw in files.items()},
        "summary": summary,
        "projection": {"function": "lab.build_model_input", "guard": "lab.guard_case", "aggregate": "lab.validate_dataset",
                       "metadataInModelInput": False, "invalidGuardPolicy": "preserve_raw_damage_and_never_infer"},
        "humanReviewCarryForward": "none_automatic_neither_42_approvals_nor_source_card_review_approves_new_context",
        "sourceReceipts": {"B": None, "C": None}, "trainingUses": [], "candidateModelCalls": 0,
        "limitations": ["新增实体/位置/任务/个性/历史前缀及实际夹具点数均须逐卡新审，不保证语义完整或独立来源。",
                        "完整来源核验、人审与明确执行授权均未完成；不得据结构检查开跑。",
                        "r1-sealed-d04-10保留缺targetId原损坏，lab结构检查拒绝；不生成替代目标或可运行投影。",
                        "短链动态执行器未实现；无真实预测/模型/服务/浏览器/性能证据。",
                        "D05守卫题不能结算；夹具历史不冒充真实服务确认回执。",
                        "G03短链的真实服务适配仍blocked_contract_g03；时间/更新/叙事外围未实现。"],
        "cases": [{"caseId": case["caseId"], "sourceGroup": case["sourceGroup"], "split": case["split"],
                   "anchorCase": case["anchorCase"], "derivedFrom": case["derivedFrom"], "caseSha256": sha(case),
                   "inputSha256": status[case["caseId"]]["inputSha256"],
                   "modelProjectionSha256": status[case["caseId"]]["modelProjectionSha256"],
                   "supplementSha256": sha(supplement)} for case, supplement in zip(cases, supplements)],
        "chains": [{"caseId": chain["caseId"], "sourceGroup": chain["sourceGroup"], "split": chain["split"],
                    "planSha256": sha(chain), "initialProjectionSha256": sha(lab.build_model_input(chain["initialCase"]))}
                   for chain in chains]}
    files[DATA / "input-manifest.json"] = json_bytes(manifest)
    lines = ["# L3 第三步：90来源卡输入补全草稿", "", "日期：2026-11-01。来源卡修订2保持原字节；所有新增上下文待人工复核，不自动沿用旧42题或卡片意见。", "",
             "80张独立任务卡均有完整世界/实体/任务/个性及当前阶段输入；其中14张是原计划守卫。另有4个同组同split骰点派生，任务输入共84项。",
             "83项通过lab结构投影；1项保留原缺targetId的损坏身份并被拒绝。66个基础卡+4派生满足程序调用形状，其余14个守卫不得调用模型。结构就绪不是运行授权。",
             "10条短链只准备初态与未执行计划；动态执行器未实现，没有未来目标、反应、结果或骰点。另列D02缺输入/取消两项守卫，不增加90来源组。",
             "执行授权false、训练配额0；无模型/服务/浏览器/网络/性能测试。", "",
             "| 来源卡 | 任务/用途 | 当前输入/计划 | 程序检查 |", "|---|---|---|---|"]
    for card in cards:
        if card["task"] == "CHAIN":
            chain = next(row for row in chains if row["caseId"] == card["caseId"])
            check = chain["dynamicPlan"]["contractStatus"] + "; runner_not_implemented"
        else:
            record = status[card["caseId"]]
            check = record["structuralStatus"] + "; " + record["guard"]["reason"]
        lines.append(f"| {card['caseId']} | {card['task']}/{card['split']} | {card['input']['sourceCard']['title']} | {check} |")
    lines += ["", "完整身份见data/round1-inputs/input-manifest.json；逐项可见投影哈希见input-checks.jsonl；新增上下文/损坏原字段/夹具历史见context-supplements.jsonl。",
              "D05可调用题按单一发起者和DFS已确认关系复算准入；四人画布严格保留丁→甲16、甲→丙12、丁→乙17、乙→已行动丙14。",
              "D03只携过去已冻结源的已发生判定，当前源判定不可见。D04仅携已冻结威胁，响应者未来行动未填写。",
              "所有骰点与trigger/roll身份由夹具程序构造；派生采用独立夹具执行身份，保留原sourceGroup/split，不能修改同键已保存roll。",
              "未完且禁止运行：90份新上下文的人审/来源同源核验；缺targetId守卫的合法恢复载荷；短链动态执行器/实际预测轨迹；G03服务适配；执行资源与授权。",
              "工具验证仅为结构、身份、准入及防泄漏工程检查，不判断自然语言后果、模型质量、500ms或来源独立。", ""]
    files[REPORT] = "\n".join(lines).encode("utf-8")
    return files, summary


def write_or_check(files, *, write_new):
    for path, content in files.items():
        if path.exists() and path.read_bytes() != content:
            raise ValueError(f"已有版本不同，拒绝覆盖：{path}")
        if not write_new and not path.exists():
            raise ValueError(f"缺少交付文件：{path}")
    if write_new:
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                with path.open("xb") as stream:
                    stream.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write-new", action="store_true")
    args = parser.parse_args()
    files, summary = build_files()
    write_or_check(files, write_new=args.write_new)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

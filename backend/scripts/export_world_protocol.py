"""Export frozen schemas and authored examples; never called by the game runtime.

Run from the repository root: python -X utf8 backend/scripts/export_world_protocol.py
Expected canonical strings below are authored independently of the encoder.
"""

import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic.json_schema import models_json_schema
from app.schemas.world.contracts import CONTRACT_MODELS

OUT = ROOT / "design" / "world-protocol" / "v1"


def write(name, value):
    target = OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    # Explicit bytes with LF: Path.write_text uses the platform newline,
    # which makes exported hashes differ between Windows and CI.
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    target.write_bytes(payload.encode("utf-8"))


def task(identity, owner, goal, parent=None, status="pending"):
    return {"id": identity, "ownerId": owner, "parentTaskId": parent, "goal": goal, "status": status}


def pos(container, slot=None, relative=None):
    return {"containerId": container, "slotId": slot, "relativeTo": relative}


def school():
    topology = [
        ("school", "学校", None), ("floor1", "一楼", "school"),
        ("lobby", "大堂", "floor1"), ("corridor", "走廊", "floor1"),
        ("floor2", "二楼", "school"), ("classroom1", "一号教室", "floor2"),
        ("classroom2", "二号教室", "floor2"),
    ]
    locations = {key: {"id": key, "name": name, "parentLocationId": parent,
                       "initialAppearance": f"{name}里光线昏暗，墙面保留着陈旧的擦痕。", "slots": []}
                 for key, name, parent in topology}
    characters = {}
    for index, key in enumerate("abcdef", 1):
        owner = f"person_{key}"
        root = task(f"task_{key}_root", owner, "安全度过校园中的这段时间。")
        characters[owner] = {
            "id": owner, "name": key.upper(),
            "initialPosition": pos("lobby" if index < 3 else "classroom1"),
            "initialAppearance": "穿着旧运动服，神情警惕，身体没有明显伤口。",
            "initialPersonality": "不喜欢交流，倾向于先观察周围再采取行动。",
            "initialSanity": index * 10, "tasks": {root["id"]: root},
            "slots": [{"id": "body", "label": "身上"}],
        }
    wait = task("task_wait_noon", "person_c", "坚持到中午十二点。", "task_c_root")
    characters["person_c"]["tasks"][wait["id"]] = wait
    items = {}
    for key, name in [
        ("coat", "外套"), ("key", "铜钥匙"), ("blackboard", "黑板"),
        ("door", "重门"), ("book", "书"), ("bag", "背包"),
        ("badge", "校徽"), ("phone", "手机"), ("bottle", "水瓶"), ("coin", "硬币"),
    ]:
        items[key] = {"id": key, "name": name, "initialPosition": pos("classroom1"),
                      "initialAppearance": f"一件表面有使用痕迹的{name}。", "slots": []}
    items["coat"]["initialPosition"] = pos("person_c", "body")
    items["coat"]["slots"] = [{"id": "left_pocket", "label": "左侧口袋"}]
    items["key"]["initialPosition"] = pos("coat", "left_pocket")
    return {"engineVersion": "world-engine-v1", "schemaVersion": 1,
            "worldId": "world_school", "protagonistId": "person_c",
            "initialTime": {"calendar": "gregorian", "dateTime": "2026-01-01T11:59:00", "instantOrdinal": 0},
            "locations": locations, "items": items, "characters": characters}


def initial_projection(world):
    return {"engineVersion": world["engineVersion"], "schemaVersion": 1,
            "worldId": world["worldId"], "protagonistId": world["protagonistId"],
            "time": copy.deepcopy(world["initialTime"]), "initial": copy.deepcopy(world),
            "locations": {key: {"id": key, "appearanceChanges": []} for key in world["locations"]},
            "items": {key: {"id": key, "appearanceChanges": [], "position": copy.deepcopy(item["initialPosition"])}
                      for key, item in world["items"].items()},
            "characters": {key: {"id": key, "appearanceChanges": [], "position": copy.deepcopy(char["initialPosition"]),
                                  "personalityChanges": [], "sanity": char["initialSanity"], "tasks": copy.deepcopy(char["tasks"])}
                           for key, char in world["characters"].items()}}


def advance():
    return {"advanceId": "advance_1", "inputId": "input_1", "inputText": "我推开重门。", "intentStatus": "consumed"}


def checkpoint(phase="assess_continuation", round_id="round_1"):
    return {"roundId": round_id, "advance": advance(), "trigger": "player",
            "order": [f"person_{key}" for key in "abcdef"], "cursor": 6,
            "actedIds": [f"person_{key}" for key in "abcd"],
            "visitedIds": [f"person_{key}" for key in "abcdef"],
            "phase": phase, "resumePhase": None, "pendingGroup": None, "conclusion": None}


def point(identity, previous, sequence, kind, duration, round_id="round_1", trigger="player"):
    return {"worldId": "world_school", "id": identity, "sequence": sequence, "kind": kind,
            "previousPointId": previous, "roundId": round_id, "advanceId": "advance_1", "trigger": trigger,
            "linkedFromPointId": None if kind == "normal" else previous,
            "timeAdvance": {"boundary": "elapsed" if kind == "normal" else "instant",
                            "duration": {"amount": duration, "unit": "second"}}, "entityDeltas": {}}


def unit(scope, actors, pure_time=False):
    return {"scopeId": scope, "actorIds": actors, "pureTime": pure_time,
            "positions": {}, "appearances": {}, "tasksAchieved": {}, "subtasksAdded": {},
            "personalities": {}, "sanities": {},
            "taskCoverageIds": [f"person_{key}" for key in "abcdef"], "personalityCoverageIds": []}


def build():
    _, schema = models_json_schema([(model, "validation") for model in CONTRACT_MODELS])
    schema.update({"$schema": "https://json-schema.org/draft/2020-12/schema",
                   "$id": "urn:jity:world-protocol:v1", "title": "Jity world protocol v1 (plan v0.3.1)"})
    write("world-protocol.schema.json", schema)
    world = school()
    write("fixtures/school.initial.json", world)
    write("fixtures/school.initial-state.json", initial_projection(world))
    root = {"worldId": "world_school", "id": "root_0", "sequence": 0, "kind": "root",
            "previousPointId": None, "roundId": None, "advanceId": None, "trigger": None,
            "linkedFromPointId": None, "timeAdvance": None, "entityDeltas": None}
    p1, p2, p3 = point("p1", "root_0", 1, "normal", 2), point("p2", "p1", 2, "instant", 0), point("p3", "p2", 3, "linked", 3)
    group = {"groupId": "group_cd", "initiatorId": "person_c", "memberIds": ["person_c", "person_d"],
             "frontierIds": [], "closed": True, "reactions": [{"sourceId": "person_c", "targetId": "person_d",
                 "triggerKey": "trigger_cd", "rollId": "roll_cd", "admitted": True}]}
    before = checkpoint("await_narration")
    before.update(cursor=2, actedIds=["person_a", "person_b"], visitedIds=["person_a", "person_b"],
                  resumePhase="settle_group", pendingGroup=group)
    before["advance"]["intentStatus"] = "pending"
    middle = checkpoint("await_narration")
    middle.update(cursor=3, visitedIds=["person_a", "person_b", "person_c"], resumePhase="continue_round")
    last = checkpoint("await_narration")
    last["resumePhase"] = "assess_continuation"
    write("fixtures/associated-points.json", {
        "root": root, "points": [p1, p2, p3], "checkpoints": [before, middle, last],
        "expectedTimes": ["2026-01-01T11:59:02/0", "2026-01-01T11:59:02/1", "2026-01-01T11:59:05/0"],
        "rolls": [{"worldId": "world_school", "advanceId": "advance_1", "roundId": "round_1",
                   "groupId": "group_cd", "sourceId": "person_c", "targetId": "person_d", "triggerKey": "trigger_cd",
                   "rollId": "roll_cd", "ruleVersion": "reaction-fixture-v1", "result": 15, "target": 11}],
        "requiredOrdering": ["p1.commit", "p1.narration.ready", "p2.settle", "p2.commit", "p2.narration.ready", "p3.commit", "p3.narration.ready", "round_1.conclusion"],
    })
    continu = {"kind": "continue", "closedBy": "model", "cancelReason": None,
              "candidateCharacterIds": ["person_c"], "nextRoundId": "round_2"}
    handback = {"kind": "handback", "closedBy": "model", "cancelReason": None}
    cancel = {"kind": "handback", "closedBy": "cancel", "cancelReason": "玩家结束本次推进。"}
    first = checkpoint("complete")
    first["conclusion"] = continu
    second = checkpoint("select_actor", "round_2")
    second.update(trigger="automatic", cursor=0, visitedIds=[], actedIds=[])
    ended = checkpoint("complete", "round_2")
    ended.update(trigger="automatic", conclusion=handback)
    ended["advance"]["inputText"] = None
    cancelled = checkpoint("complete")
    cancelled.update(cursor=2, visitedIds=["person_a", "person_b"], actedIds=["person_a", "person_b"], conclusion=cancel)
    cancelled["advance"].update(inputText=None, intentStatus="expired")
    write("fixtures/advance-chain.json", {"afterConclusion": first, "automatic": second, "handback": ended, "cancel": cancelled})
    timed = point("p4", "p3", 4, "normal", 60, "round_2", "automatic")
    timed["entityDeltas"] = {"person_c": {"entityId": "person_c", "tasksAchieved": ["task_wait_noon"],
        "personalityChanges": [{"id": "change_relief", "text": "暂时放松了对周围的警戒。", "supersedes": []}], "sanitySet": 35}}
    timed_cp = checkpoint("await_narration", "round_2")
    timed_cp.update(trigger="automatic", actedIds=[], resumePhase="assess_continuation")
    expected = initial_projection(world)
    expected["time"] = {"calendar": "gregorian", "dateTime": "2026-01-01T12:00:00", "instantOrdinal": 0}
    expected["characters"]["person_c"]["tasks"]["task_wait_noon"]["status"] = "achieved"
    expected["characters"]["person_c"]["personalityChanges"] = [{
        "id": "change_relief", "text": "暂时放松了对周围的警戒。", "supersedes": [],
        "sourcePointId": "time_only", "sourceSequence": 1, "active": True}]
    expected["characters"]["person_c"]["sanity"] = 35
    write("fixtures/time-only.json", {"standalone": {**timed, "id": "time_only", "sequence": 1, "previousPointId": "root_0", "roundId": "round_1", "trigger": "player"},
          "chainMiddle": timed, "checkpoint": timed_cp,
          "chainBaselineTime": {"calendar": "gregorian", "dateTime": "2026-01-01T11:59:05", "instantOrdinal": 0},
          "chainExpectedTime": "2026-01-01T12:00:05/0", "expectedStandaloneState": expected,
          "actions": [], "requiredStages": ["time", "tasks", "subtasks", "personality", "sanity", "narration"],
          "allowedNarration": "时间到了中午，目标已经达成，你暂时放松了警戒。"})
    parent = task("task_new_parent", "person_c", "检查教室内的安全状况。", "task_c_root")
    child = task("task_new_child", "person_c", "确认门边没有障碍。", "task_new_parent", "achieved")
    write("fixtures/task-normalization.json", {
        "stageCandidates": [{"stage": "subtasks", "added": [parent, {**child, "status": "pending"}]},
                            {"stage": "tasks", "achieved": ["task_new_child"]}],
        "finalDelta": {"entityId": "person_c", "subtasksAdded": [parent, child]},
        "expectedNewTasks": {parent["id"]: parent, child["id"]: child},
    })
    write("fixtures/frozen-action.json", {
        "groupId": "group_cd", "actorId": "person_c", "action": "C 推开重门，示意 D 避开门边。",
        "admittedIds": ["person_d"], "laterThreat": "E 从另一侧拉动重门。",
        "expectedAction": "C 推开重门，示意 D 避开门边。", "expectedAdmittedIds": ["person_d"],
        "expectedEffect": "later_threat_only_changes_settlement", "actionRevisions": 0})
    write("fixtures/description-changes.json", {
        "entityId": "person_c", "field": "appearance",
        "history": [{"id": "change_bleeding", "text": "嘴角开始流血。", "supersedes": [], "sourcePointId": "p1", "sourceSequence": 1, "active": True}],
        "replacement": {"id": "change_stopped", "text": "嘴角已止血。", "supersedes": ["change_bleeding"]},
        "pureRemoval": {"id": "change_remove", "text": None, "supersedes": ["change_bleeding"]},
        "samePointWorking": [{"localRef": "local_bleed", "text": "嘴角开始流血。"},
                             {"localRef": "local_stop", "text": "嘴角已止血。", "replacesLocal": "local_bleed"}],
        "expectedCollapsed": {"id": "change_final", "text": "嘴角已止血。", "supersedes": []}})
    write("fixtures/claims.json", {
        "rootHead": {"worldId": "world_school", "pointId": "root_0", "advanceId": None, "generation": 1,
                     "claimToken": "claim_root", "expiresAt": 1800, "mode": "head", "fenceEpoch": 7},
        "historyRoot": {"worldId": "world_school", "pointId": "root_0", "advanceId": None, "generation": 2,
                        "claimToken": "claim_history", "expiresAt": 1800, "mode": "history", "fenceEpoch": None},
        "lease": {"worldId": "world_school", "holderId": "tab_a", "leaseToken": "lease_a", "fenceEpoch": 7, "expiresAt": 120},
        "renewal": {"at": 20, "expectedFenceEpoch": 7, "expiresAt": 140},
        "takeover": {"at": 141, "newFenceEpoch": 8, "expectedOldClaimResult": "stale_epoch", "mayReclaimImmediately": True},
        "rootGate": {"narrationStatus": "pending", "startRoundAllowed": False},
        "terminalGroup": {"expectedKinds": ["normal", "instant", "linked"], "emptyLinkedNarrationCalls": 1},
    })
    time_unit = unit("time_scan", [], True)
    time_unit.update(tasksAchieved={"person_c": ["task_wait_noon"]},
                     personalities={"person_c": timed["entityDeltas"]["person_c"]["personalityChanges"]},
                     sanities={"person_c": 35}, personalityCoverageIds=[f"person_{key}" for key in "abcdef"])
    normal_request = {"worldId": "world_school", "advanceId": "advance_1", "expectedPointId": "root_0",
                      "expectedVersion": 0, "requestId": "request_p1", "roundId": "round_1",
                      "expectedCheckpointRevision": 1, "leaseToken": "lease_a", "fenceEpoch": 7,
                      "point": p1, "checkpoint": before,
                      "stageCandidates": [unit("slot_a", ["person_a"]), unit("slot_b", ["person_b"])]}
    timed_request = copy.deepcopy(normal_request)
    timed_request.update(expectedPointId="p3", expectedVersion=3, requestId="request_p4", roundId="round_2",
                         expectedCheckpointRevision=7, point=timed, checkpoint=timed_cp, stageCandidates=[time_unit])
    conclusion_request = {key: value for key, value in normal_request.items()
                          if key not in ("point", "checkpoint", "stageCandidates")}
    conclusion_request.update(expectedPointId="p3", expectedVersion=3, requestId="request_conclusion",
                              expectedCheckpointRevision=6, operation="conclude", conclusion=continu)
    write("fixtures/requests.json", {"normalCommit": normal_request, "timeCommit": timed_request,
          "conclusion": conclusion_request,
          "preview": {"worldId": "world_school", "advanceId": "advance_1", "roundId": "round_2",
                      "pointId": "p4", "expectedPointId": "p3", "expectedVersion": 3,
                      "expectedCheckpointRevision": 7, "timeAdvance": timed["timeAdvance"], "stageCandidates": [time_unit]}})
    vectors = [
        ("keys_unicode_integers", None, '{"z":1.0,"a":"学校😀","n":-0.0}', '{"a":"学校😀","n":0,"z":1}'),
        ("control_characters", None, '{"a":"\\n\\t\\u0000\\u001f","slash":"/","u":"\u2028\u2029"}', '{"a":"\\u000a\\u0009\\u0000\\u001f","slash":"/","u":"\u2028\u2029"}'),
        ("position_defaults", "Position", '{"containerId":"coat"}', '{"containerId":"coat","relativeTo":null,"slotId":null}'),
        ("set_and_noop_fields", "EntityDelta", '{"entityId":"person_c","tasksAchieved":["task_z","task_a"],"appearanceChanges":[]}', '{"entityId":"person_c","tasksAchieved":["task_a","task_z"]}'),
        ("pure_removal_null", "DescriptionChange", '{"id":"change_remove","text":null,"supersedes":["change_old"]}', '{"id":"change_remove","supersedes":["change_old"],"text":null}'),
        ("ordered_array_ab", None, '{"order":["a","b"]}', '{"order":["a","b"]}'),
        ("ordered_array_ba", None, '{"order":["b","a"]}', '{"order":["b","a"]}'),
        ("no_unicode_normalization", None, '{"a":"e\\u0301","b":"é"}', '{"a":"e\u0301","b":"é"}'),
    ]
    write("canonical-vectors.json", {"canonicalVersion": "world-canonical-v1", "vectors": [
        {"id": key, "schema": model, "inputJson": raw, "expectedCanonical": expected,
         "expectedUtf8Hex": expected.encode("utf-8").hex(), "expectedSha256": hashlib.sha256(expected.encode("utf-8")).hexdigest()}
        for key, model, raw, expected in vectors],
        "rejectedJson": ['{"a":1,"a":2}', '{"a":NaN}', '{"a":1.5}', '{"a":9007199254740992}', '{"a":"\\ud800"}', '{"键":1}']})


if __name__ == "__main__":
    build()
    print(f"Exported world protocol contracts to {OUT}")

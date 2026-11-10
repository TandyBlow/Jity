"""Author a new registered fixture and commit six cases through an isolated A service.

Never calls a model, trains, patches production code or overwrites an existing run.
Run only after audit_world_sources.py. See fresh/PROTOCOL.md.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys

OUT = Path(__file__).resolve().parents[1]
REPO = OUT.parents[2]
MAIN = REPO.parents[2]
FRESH = OUT / "fresh"
RUN = FRESH / "source"
sys.path.insert(0, str(MAIN / "backend"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(path, *args):
    return subprocess.check_output(["git", "-c", f"safe.directory={Path(path).as_posix()}",
                                    "-C", str(path), *args]).decode("utf-8").strip()


def pos(place, relative=None):
    return {"containerId": place, "slotId": None, "relativeTo": relative}


def new_fixture():
    locations = {}
    for lid, name, parent, appearance in [
        ("fy_yard", "岫砚检修院", None, "院内立着三根带刻线的陶柱，地面铺浅色碎石。"),
        ("fy_pump", "玄藻泵舱", "fy_yard", "地沟沿泵座外侧延伸，隔振垫上印着斜纹。"),
        ("fy_cal", "砾脊校准间", "fy_yard", "校准台分成两个刻度区，窗框嵌有琥珀色玻璃。"),
        ("fy_bridge", "苔铎栈桥", "fy_yard", "栈桥转角设着半圆挡板，踏板上压着细密菱纹。"),
        ("fy_store", "霜珀备件库", None, "备件库与检修院分属两栋建筑，入口有三层隔帘。"),
        ("fy_relay", "穹榛中继室", "fy_store", "窄长机架背面留出一条检修通道。"),
        ("fy_watch", "弧砂观测台", None, "观测台独立立在碎石坡上，平台中心有一道环形刻槽。"),
    ]:
        locations[lid] = {"id": lid, "name": name, "parentLocationId": parent,
                          "initialAppearance": appearance, "slots": []}
    tasks = {
        "fe_wen": [("ft_check", "核验瓷铯量规的双区刻度", None),
                   ("ft_mark", "登记量规右区的第三条刻线", "ft_check"),
                   ("ft_seal", "更换绛纹阀芯上的锆丝封签", None)],
        "fe_shao": [("ft_relay", "复核穹榛机架背面的联接编号", None)],
        "fe_nie": [("ft_sort", "将未拆封阀芯按批次分入陶格", None)],
        "fe_pu": [("ft_watch", "读出弧砂刻槽的偏移刻度", None)],
        "fe_yu": [("ft_bridge", "登记苔铎挡板的紧固次序", None)],
    }
    characters = {}
    for eid, name, place, sanity, personality, appearance in [
        ("fe_wen", "闻澈岑", "fy_pump", 43, "遇到刻度分歧先复测，再记录自己的判断。", "灰紫护袖束在前臂，胸前别着三角陶牌。"),
        ("fe_shao", "邵苇衡", "fy_store", 57, "交接零件前逐一复诵批次。", "短罩衣下摆压着两道平行缝线。"),
        ("fe_nie", "聂汀穗", "fy_cal", 61, "整理器具时习惯保留原来的朝向。", "靛白肩带斜跨在细格工作服外。"),
        ("fe_pu", "蒲砺弦", "fy_watch", 38, "读数后先等同伴确认再离开。", "窄檐护帽上留着一块方形织补。"),
        ("fe_yu", "郁棠序", "fy_bridge", 72, "喜欢把复杂步骤拆成可以复查的小项。", "浅赭绑腿外侧各缀一枚扁扣。"),
    ]:
        characters[eid] = {"id": eid, "name": name, "initialPosition": pos(place),
                           "initialAppearance": appearance, "slots": [],
                           "initialPersonality": personality, "initialSanity": sanity,
                           "tasks": {tid: {"id": tid, "ownerId": eid, "parentTaskId": parent,
                                           "goal": goal, "status": "pending"}
                                     for tid, goal, parent in tasks[eid]}}
    items = {}
    for eid, name, place, appearance in [
        ("fi_gauge", "瓷铯量规", "fy_cal", "量规左右各有一列凹刻线，末端刻着双点记号。"),
        ("fi_valve", "绛纹阀芯", "fy_pump", "阀芯侧边嵌着绛色条纹，顶部有六角浅槽。"),
        ("fi_seal", "锆丝封签", "fe_wen", "封签绕成扁环，接合处压着一枚椭圆印。"),
    ]:
        items[eid] = {"id": eid, "name": name, "initialPosition": pos(place),
                      "initialAppearance": appearance, "slots": []}
    return {"engineVersion": "world-engine-v1", "schemaVersion": 1,
            "protagonistId": "fe_wen", "initialTime": {"calendar": "gregorian",
            "dateTime": "2026-12-03T08:20:00", "instantOrdinal": 0},
            "locations": locations, "items": items, "characters": characters}


def scenario_specs():
    def group(actor, action, result, **changes):
        return {"actor": actor, "action": action, "result": result, **changes}
    return [
        {"id": "c8e01", "title": "三项转运，各有起终点", "seconds": 90,
         "coverage": ["多人物", "多地点"], "view": "omniscient",
         "inputText": "记录本次三人的转运去向，保留各自的起点和终点。",
         "groups": [
             group("fe_wen", "前往校准间核对量规。", "已从玄藻泵舱到砾脊校准间。", positions={"fe_wen": pos("fy_cal")}),
             group("fe_shao", "到中继室查看机架。", "已从霜珀备件库到穹榛中继室。", positions={"fe_shao": pos("fy_relay")}),
             group("fe_yu", "离开栈桥前往观测台。", "已从苔铎栈桥到弧砂观测台。", positions={"fe_yu": pos("fy_watch")})],
         "checks": ["三条移动的人物与起终点各自对应，不互换。", "未变化人物不得写成参与转运。"]},
        {"id": "c8e02", "title": "两栋建筑，视角只在校准间", "seconds": 45,
         "coverage": ["多人物", "多地点", "可见性"], "view": "protagonist",
         "inputText": "跟随闻澈岑查看校准间这一侧的动静。",
         "groups": [
             group("fe_wen", "去校准间。", "已到砾脊校准间。", positions={"fe_wen": pos("fy_cal")}),
             group("fe_shao", "进入备件库内部的中继室。", "已到穹榛中继室。", positions={"fe_shao": pos("fy_relay")})],
         "checks": ["视角位置从 after 解析为砾脊校准间。", "邵苇衡在另一栋建筑的移动不进入限知成句输入。", "不得把完整状态中的远处信息当成主体所见。"]},
        {"id": "c8e03", "title": "父子任务同时校准，另有人完成转移", "seconds": 180,
         "coverage": ["任务", "多人物", "多地点"], "view": "protagonist",
         "inputText": "记录闻澈岑完成的两项量规核验及本人的状态变化。",
         "groups": [
             group("fe_wen", "核验双区刻度并登记指定刻线。", "双区核验与第三条刻线登记均已完成。",
                   positions={"fe_wen": pos("fy_cal")},
                   tasksAchieved={"fe_wen": ["ft_check", "ft_mark"]},
                   personalities={"fe_wen": [{"key": "calibration", "text": "复测一致后愿意把核验步骤交给同伴复查。"}]},
                   sanities={"fe_wen": 47}),
             group("fe_nie", "前往栈桥核对挡板。", "已从砾脊校准间到苔铎栈桥。", positions={"fe_nie": pos("fy_bridge")})],
         "checks": ["明确只达成 ft_check 与 ft_mark，不把 ft_seal 算入。", "给定事实中的理智是43→47，人格文本保留原意。", "不因未提输入未给的其他 pending 状态扣分。"]},
        {"id": "c8e04", "title": "持有人与参照物，明确空间关系", "seconds": 30,
         "coverage": ["关系", "多人物"], "view": "protagonist",
         "inputText": "记录闻澈岑摆放量规的位置，保留谁在谁旁边。",
         "groups": [group("fe_wen", "到校准间并把量规放在聂汀穗旁边。", "本人已到校准间，量规位于聂汀穗旁边。",
                          positions={"fe_wen": pos("fy_cal"), "fi_gauge": pos("fy_cal", {"entityId": "fe_nie", "relation": "beside"})})],
         "checks": ["量规是关系主体，聂汀穗是参照物，不反转。", "位置只支持 beside，不引申交付、所有权或长期人际关系。", "限于支持 position_relative 的模块，不计当前页面投影成绩。"]},
        {"id": "c8e05", "title": "封签的持有转移和外貌变化", "seconds": 60,
         "coverage": ["关系", "多人物", "外貌"], "view": "protagonist",
         "inputText": "记录封签从谁处移到谁处，以及封签本身发生的变化。",
         "groups": [group("fe_wen", "把随身封签交由聂汀穗收存。", "封签已由聂汀穗持有，接合处新增一道横向压痕。",
                          positions={"fe_wen": pos("fy_cal"), "fi_seal": pos("fe_nie")},
                          appearances={"fi_seal": [{"key": "crimp", "text": "接合处新增一道横向压痕。"}]})],
         "checks": ["转移的是封签，不是人物移动；持有人从闻澈岑变为聂汀穗。", "外貌变化归于封签，不归于持有人。", "持有关系不等于所有权、友谊或因果；当前页面投影不支持这类包。"]},
        {"id": "c8e06", "title": "关注指令与世界事实分开", "seconds": 120,
         "coverage": ["玩家关注", "任务", "多人物"], "view": "omniscient",
         "inputText": "我只关心邵苇衡复核机架联接编号的结果；暂时别展开闻澈岑的移动。",
         "groups": [
             group("fe_wen", "去校准间准备复测。", "已从玄藻泵舱到砾脊校准间。", positions={"fe_wen": pos("fy_cal")}),
             group("fe_shao", "进入中继室复核机架背面联接编号。", "机架背面的联接编号已复核。",
                   positions={"fe_shao": pos("fy_relay")}, tasksAchieved={"fe_shao": ["ft_relay"]})],
         "attentionGold": {"focusEntityIds": ["fe_shao"], "focusTaskIds": ["ft_relay"],
                           "deprioritizedEntityIds": ["fe_wen"]},
         "checks": ["关注主体解析为fe_shao、任务为ft_relay；fe_wen只是暂不展开。", "指令本身不证明任务达成，达成必须来自提交事实。", "这是本轮作者提供的合成玩家指令，不是真实玩家原话；只核验关注解析数据，不称N2已支持此功能。"]},
    ]


def main():
    audit_path = OUT / "source-search/audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["summary"]["eligibleUnseen"] != 0:
        raise RuntimeError("Audit has an eligible source; review it before creating another")
    if RUN.exists():
        raise RuntimeError("Existing source run is immutable; use verification or a new version")
    RUN.mkdir()
    write(RUN / "initial-template.json", new_fixture())
    write(RUN / "scenario-specs.json", scenario_specs())
    registration = {"id": "c8-eval-geothermal-v1", "status": "registered-before-service-creation",
                    "createdUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "author": "Codex in this user-authorized C8 session", "purpose": "evaluation-only",
                    "sourceKind": "newly-authored-synthetic-registered-fixture",
                    "trainingOrTuningUse": "none in this session; not supplied to tuning agents",
                    "isR01ModelOutput": False, "isRealPlayerTranscript": False,
                    "humanReviewer": "user (identity/date/conclusions pending)",
                    "auditSha256": sha(audit_path), "protocolSha256": sha(FRESH / "PROTOCOL.md"),
                    "templateSha256": sha(RUN / "initial-template.json"),
                    "specsSha256": sha(RUN / "scenario-specs.json"),
                    "generatorSha256": sha(__file__), "parentC8Commit": git(REPO, "rev-parse", "HEAD"),
                    "authorityCommit": git(MAIN, "rev-parse", "HEAD"),
                    "python": sys.version, "device": platform.platform(), "modelCalls": 0}
    write(RUN / "registration.json", registration)

    from app.database.world_store import SQLiteBaselineStore
    from app.services.world.control import WorldService
    from app.services.world.merge import point_entity_deltas
    from app.schemas.world.v2.work import SettlementGroup
    from app.schemas.world.v2.requests import GetStateSuccess
    store = SQLiteBaselineStore(str(RUN / "authority.sqlite3"))
    service = WorldService(store)
    transcript, cases = [], []
    prefix = ""

    def call(operation, request):
        try:
            response = service.execute(operation, {"protocolVersion": 2, **request})
        except Exception as exc:
            transcript.append({"operation": operation, "request": request,
                               "exception": type(exc).__name__, "message": str(exc)})
            write(RUN / "service-transcript.json", transcript)
            raise
        transcript.append({"operation": operation, "request": {"protocolVersion": 2, **request},
                           "response": response})
        if response.get("status") in ("refused", "error") or "data" not in response:
            write(RUN / "service-transcript.json", transcript)
            raise RuntimeError(f"{operation}: {response}")
        return response

    def request_id(suffix):
        return f"{prefix}_{suffix}"

    def narrate(world, lease, point):
        # A fixture-only placeholder satisfies the service's ready gate; never a model output.
        claim = call("narration_claim", {"requestId": request_id("root_claim"), "worldId": world,
                      **lease, "pointId": point, "mode": "head", "currentClaim": None})["data"]
        call("narration_submit", {"requestId": request_id("root_submit"), "worldId": world, **lease,
             "pointId": point, "mode": "head", "claimToken": claim["claimToken"],
             "generation": claim["generation"], "issuedAtEpochMilli": claim["issuedAtEpochMilli"],
             "outcome": "ready", "text": "评测专用夹具已建立；此句由脚本提供。", "failureReason": None})

    for spec in scenario_specs():
        prefix = spec["id"]
        template = new_fixture()
        order = list(template["characters"])
        created = call("create_world", {"requestId": request_id("create"), "initial": template})["data"]
        world, root = created["worldId"], created["rootPointId"]
        lease = {"leaseToken": created["lease"]["leaseToken"], "fenceEpoch": created["lease"]["fenceEpoch"]}
        narrate(world, lease, root)
        slots = [{"slotKey": key, "kind": key, "scope": None} for key in ("advance", "input", "round", "point")]
        slots += [{"slotKey": f"group_{i}", "kind": "group", "scope": None} for i in range(len(spec["groups"]))]
        for i, g in enumerate(spec["groups"]):
            for field in ("personalities", "appearances"):
                for eid, changes in g.get(field, {}).items():
                    for ch in changes:
                        slots.append({"slotKey": f"change_{i}_{eid}_{ch['key']}", "kind": "change", "scope": None})
        allocated = call("allocate_ids", {"requestId": request_id("ids"), "worldId": world, **lease,
                         "allocationKey": request_id("allocation"), "slots": slots})["data"]["allocations"]
        ids = {a["slotKey"]: a["id"] for a in allocated}
        revision = 0

        def checkpoint(operation, **fields):
            nonlocal revision
            payload = {"requestId": request_id(f"checkpoint_{revision}"), "worldId": world, **lease,
                       "operation": operation.removeprefix("checkpoint_"), "expectedPointId": root,
                       "expectedVersion": 0, "expectedCheckpointRevision": revision, **fields}
            if operation != "checkpoint_start_advance":
                payload["pointId"] = ids["point"]
            response = call(operation, payload)
            revision += 1
            return response

        checkpoint("checkpoint_start_advance", advanceId=ids["advance"], inputId=ids["input"],
                   roundId=ids["round"], inputText=spec["inputText"], order=order)
        # The service orders the round itself (ascending initial sanity); read the
        # authoritative order back instead of assuming the template order.
        context = service.execute("get_context", {"protocolVersion": 2, "worldId": world,
                                                 "pointId": root,
                                                 "advanceId": ids["advance"]})
        order = context["world"]["round"]["order"]
        transcript.append({"operation": "derived-round-order", "order": order})
        time = {"boundary": "elapsed", "duration": {"amount": spec["seconds"], "unit": "second"}}
        checkpoint("checkpoint_begin_point", kind="normal", timeAdvance=time)
        groups = []
        acted = {g["actor"] for g in spec["groups"]}
        by_actor = {g["actor"]: (i, g) for i, g in enumerate(spec["groups"])}
        for actor in order:
            if actor not in acted:
                checkpoint("checkpoint_record_skip", slotActorId=actor)
                continue
            index, g = by_actor[actor]
            gid = ids[f"group_{index}"]
            checkpoint("checkpoint_discover_group", groupId=gid, initiatorId=actor,
                       actionText=g["action"], targetIds=None)
            checkpoint("checkpoint_extend_group", groupId=gid, sourceId=actor, targets=[], admittedMember=None)
            checkpoint("checkpoint_close_group", groupId=gid)
            body = {"groupId": gid, "actorIds": [actor], "positions": {}, "appearances": {},
                    "tasksAchieved": {}, "subtasksAdded": {}, "personalities": {}, "sanities": {},
                    "taskCoverageIds": sorted(order),
                    "personalityCoverageIds": sorted(order) if g.get("tasksAchieved") else []}
            for field in ("positions", "tasksAchieved", "sanities"):
                body[field] = g.get(field, {})
            for field in ("appearances", "personalities"):
                body[field] = {eid: [{"id": ids[f"change_{index}_{eid}_{ch['key']}"],
                                     "text": ch["text"], "supersedes": []} for ch in changes]
                               for eid, changes in g.get(field, {}).items()}
            unit = SettlementGroup.model_validate(body)
            checkpoint("checkpoint_stage_unit", groupId=gid, candidates=unit.model_dump(mode="json"),
                       results={actor: g["result"]})
            groups.append(unit)
        checkpoint("checkpoint_seal_point")
        merged = point_entity_deltas(groups, None)
        point = {"worldId": world, "id": ids["point"], "sequence": 1, "kind": "normal",
                 "previousPointId": root, "roundId": ids["round"], "advanceId": ids["advance"],
                 "trigger": "player", "linkedFromPointId": None, "timeAdvance": time,
                 "entityDeltas": {eid: delta.model_dump(mode="json") for eid, delta in merged.items()}}
        commit = call("commit_point", {"requestId": request_id("commit"), "worldId": world, **lease,
                      "advanceId": ids["advance"], "roundId": ids["round"], "expectedPointId": root,
                      "expectedVersion": 0, "expectedCheckpointRevision": revision,
                      "pointId": ids["point"], "point": point,
                      "settlementGroups": [g.model_dump(mode="json") for g in groups]})
        before = call("get_state", {"worldId": world, "point": root})
        after = call("get_state", {"worldId": world, "point": ids["point"]})
        GetStateSuccess.model_validate(before)
        GetStateSuccess.model_validate(after)
        write(RUN / f"{prefix}.before.json", before["data"])
        write(RUN / f"{prefix}.after.json", after["data"])
        cases.append({"id": prefix, "worldId": world, "pointId": ids["point"], "rootPointId": root,
                      "ids": ids, "commit": commit["data"], "sourceStatus": "committed-evaluation-fixture",
                      "rootDigest": before["data"]["stateDigest"], "afterDigest": after["data"]["stateDigest"]})
        write(RUN / "service-transcript.json", transcript)
        write(RUN / "cases.json", cases)
        print(f"{prefix}: committed and read back", flush=True)
    # Fresh store/service instance performs real persisted reads, independent of the writer instance.
    reloaded = WorldService(SQLiteBaselineStore(str(RUN / "authority.sqlite3")))
    recovered = []
    for case in cases:
        response = reloaded.execute("get_state", {"protocolVersion": 2, "worldId": case["worldId"], "point": case["pointId"]})
        expected = json.loads((RUN / f"{case['id']}.after.json").read_text(encoding="utf-8"))
        recovered.append({"id": case["id"], "readMatches": response["data"] == expected,
                          "stateDigest": response["data"]["stateDigest"]})
        assert recovered[-1]["readMatches"]
    write(RUN / "reopen-check.json", recovered)
    dependencies = {}
    for module in list(sys.modules.values()):
        file = getattr(module, "__file__", None)
        if file and Path(file).is_file() and Path(file).is_relative_to(MAIN / "backend"):
            dependencies[Path(file).relative_to(MAIN).as_posix()] = sha(file)
    write(RUN / "authority-dependencies.json", {"commit": registration["authorityCommit"], "files": dependencies,
                                               "note": "Exact imported bytes; includes already-present working-tree changes, which this task does not modify."})
    print(json.dumps({"committedCases": len(cases), "reopened": len(recovered), "modelCalls": 0}))


if __name__ == "__main__":
    main()

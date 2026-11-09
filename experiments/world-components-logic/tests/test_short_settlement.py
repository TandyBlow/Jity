"""Synthetic engineering fixtures only. No fixture is a model-quality result."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from short_contracts import result, incomplete, empty, digest, ContractError, ModelSession, ModelIdentity
from short_settlement import (settle_joint, run_updates, validate_group,
                              validate_positions, validate_fact_mapping, settlement_context, verify_candidate_packet, STAGES)


def world_fixture():
    initial = {"locations": {}, "items": {}, "characters": {}}
    world = {"worldId": "w", "time": {"dateTime": "2026-11-09T12:00:00"}, "initial": initial,
             "locations": {}, "items": {}, "characters": {}}
    for key in ("room", "far"):
        initial["locations"][key] = {"id": key, "name": key, "parentLocationId": None, "initialAppearance": "初始地点", "slots": []}
        world["locations"][key] = {"id": key, "appearanceChanges": []}
    for kind, keys in (("items", ("tool", "box")), ("characters", ("a", "b", "off"))):
        for key in keys:
            initial[kind][key] = {"id": key, "name": key, "initialAppearance": "初始外貌", "slots": []}
            world[kind][key] = {"id": key, "position": {"containerId": "far" if key == "off" else "room"}, "appearanceChanges": []}
            if kind == "characters":
                initial[kind][key].update(initialPersonality="愿意协作", initialSanity=60)
                world[kind][key].update(personalityChanges=[], sanity=60, tasks={key + "t": {"id": key + "t", "ownerId": key, "parentTaskId": None, "goal": "完成目标", "status": "pending"}})
    world["items"]["tool"]["appearanceChanges"] = [{"id": "scar", "text": "局部磨损", "supersedes": [], "active": True}]
    world["characters"]["off"]["personalityChanges"] = [{"id": "fear", "text": "回避冲突", "supersedes": [], "active": True}]
    return world


def context_fixture():
    return {"world": world_fixture(), "binding": {"pointId": "point", "version": 3, "epoch": 4}, "group": {
        "groupId": "group", "closed": True, "memberIds": ["a", "b"],
        "members": [{"memberId": "a", "actionText": "尝试取工具。"}, {"memberId": "b", "actionText": "尝试按住工具。"}],
        "confirmedTargets": [{"sourceId": "a", "targetIds": ["b", "off"]}, {"sourceId": "b", "targetIds": []}],
        "judgments": [
            {"sourceId": "a", "targetId": "b", "rollId": "r1", "result": 15, "target": 11, "groupId": "group", "triggerKey": "tr1", "eligibilityBaselineDigest": "0" * 64, "ruleVersion": "reaction-d20-v1", "eligible": True, "passed": True, "admitted": True},
            {"sourceId": "a", "targetId": "off", "rollId": "r2", "result": 1, "target": 11, "groupId": "group", "triggerKey": "tr2", "eligibilityBaselineDigest": "0" * 64, "ruleVersion": "reaction-d20-v1", "eligible": False, "passed": False, "admitted": False}],
        "alreadyActedIds": ["off"]}}


class FixtureSession:
    """Declared deterministic test double, never used in experiments."""
    def __init__(self, overrides=None, effects=False):
        self.calls = []
        self.overrides = overrides or {}
        self.effects = effects
    def call(self, component, payload):
        self.calls.append((component, copy.deepcopy(payload)))
        if component in self.overrides:
            value = self.overrides[component]
            return value(payload) if callable(value) else value
        if component == "D05.1":
            return result({"checkedActionIds": ["a", "b"], "relations": [{"sourceId": "a", "targetId": "b", "kind": "contests"}]})
        if component == "D05.2":
            return result({"judgments": [{"attemptId": a["attemptId"], "label": "not_achieved"} for a in payload["attempts"]]})
        if component == "D05.3":
            return result({"kind": "fact", "text": "两人均未拿起工具，工具表面的磨损已不再可见。"}) if not payload["candidates"] else result({"kind": "end"})
        if component == "D05.4":
            return result({"verdict": "pass", "checkedActionIds": ["a", "b"], "checkedFactIds": ["fact:1"], "checkedRollIds": ["r1", "r2"]})
        if component == "D05.5":
            return result({"facts": [{"factId": "fact:1", "memberIds": ["a", "b"]}], "checkedMemberIds": ["a", "b"]})
        if component == "U1.1":
            return result({"decisions": [{"entityId": k, "change": False} for k in payload["entityIds"]]})
        if component in ("U2.1", "U5.1"):
            operations = []
            for key in payload["entityIds"]:
                if self.effects and component == "U2.1" and key == "tool":
                    operations.append({"entityId": key, "op": "remove", "recordIds": ["scar"]})
                elif self.effects and component == "U5.1" and key == "off":
                    operations += [{"entityId": key, "op": "remove", "recordIds": ["fear"]}, {"entityId": key, "op": "add", "recordIds": []}, {"entityId": key, "op": "add", "recordIds": []}]
                else:
                    operations.append({"entityId": key, "op": "keep", "recordIds": list(payload["activeRecords"][key])})
            return result({"checkedEntityIds": payload["entityIds"], "checkedRecordIds": [r for key in payload["entityIds"] for r in payload["activeRecords"][key]], "operations": operations})
        if component == "U5.2":
            return result("愿意主动协作。" if len(payload["currentDescriptionCandidates"].get("off", {}).get("personalityChanges", [])) == 1 else "遇到争执时先询问同伴。")
        if component == "U3.1":
            return result({"checkedCharacterIds": payload["characterIds"], "decisions": [{"taskId": t, "label": "achieved" if self.effects and t == "at" else "pending"} for t in payload["taskIds"]]})
        if component == "U4.1":
            return result({"checkedParentTaskIds": payload["parentTaskIds"], "checkedCharacterIds": payload["characterIds"], "needs": [{"parentTaskId": key, "count": 2 if self.effects and key == "bt" else 0} for key in payload["parentTaskIds"]]})
        if component == "U4.2":
            return result("先检查工具。" if payload["goalIndex"] == 0 else "向同伴询问修理方式。")
        if component == "U6.1":
            return result(48)
        if component == "D06.P.review":
            return result({"verdict": "pass", "checkedEntityIds": list(payload["proposed"]["changes"])})
        if component == "D06.P.mapping":
            refs = payload["candidateRefs"]
            return result({"verdict": "pass", "mappings": [{"factId": (payload["timeFact"] or {"id": "fact:1"})["id"], "kind": "state" if refs else "unchanged", "targets": refs}]})
        raise AssertionError("unregistered test component " + component)


class FixturePreview:
    """Minimal deterministic apply TEST DOUBLE. Not a production preview."""
    def __init__(self, world):
        self.base = copy.deepcopy(world)
        self.calls = []
    def __call__(self, request):
        self.calls.append(copy.deepcopy(request))
        world = copy.deepcopy(self.base)
        for call in request["completedStages"]:
            for owner, delta in call["changes"].items():
                entity = next(world[k][owner] for k in ("locations", "items", "characters") if owner in world[k])
                if "positionSet" in delta:
                    entity["position"] = copy.deepcopy(delta["positionSet"])
                for field in ("appearanceChanges", "personalityChanges"):
                    for change in delta.get(field, []):
                        for old in entity[field]:
                            if old["id"] in change["supersedes"]:
                                old["active"] = False
                        entity[field].append({**change, "active": change["text"] is not None})
                for task in delta.get("tasksAchieved", []):
                    entity["tasks"][task]["status"] = "achieved"
                for task in delta.get("subtasksAdded", []):
                    entity["tasks"][task["id"]] = copy.deepcopy(task)
                if "sanitySet" in delta:
                    entity["sanity"] = delta["sanitySet"]
        return result({**{k: request[k] for k in ("binding", "candidateHash", "baseWorldHash", "stage")}, "world": world})


def allocate(kind, slot):
    return kind + ":" + slot


class JointTests(unittest.TestCase):
    def test_whole_group_actual_denied_and_acted_judgments_are_preserved(self):
        context = context_fixture()
        session = FixtureSession()
        output = settle_joint(session, context)
        self.assertEqual(output.status, "result")
        self.assertEqual(output.value["results"]["a"], output.value["facts"][0]["text"])
        self.assertEqual(set(output.value["results"]), {"a", "b"})
        for _, payload in session.calls:
            self.assertEqual(payload["context"], context)
        self.assertFalse(output.value["committed"])
    def test_missing_semantic_world_material_never_becomes_no_change(self):
        for path in (("initial", "items", "tool", "initialAppearance"),
                     ("initial", "characters", "a", "initialPersonality"),
                     ("characters", "a", "tasks", "at", "goal")):
            context = context_fixture()
            target = context["world"]
            for key in path[:-1]:
                target = target[key]
            del target[path[-1]]
            session = FixtureSession()
            self.assertEqual(settle_joint(session, context).status, "incomplete")
            self.assertEqual(session.calls, [])

    def test_missing_denied_roll_prevents_model_call(self):
        context = context_fixture(); context["group"]["judgments"].pop()
        session = FixtureSession()
        self.assertEqual(settle_joint(session, context).status, "incomplete")
        self.assertEqual(session.calls, [])
    def test_open_group_and_missing_action_are_incomplete(self):
        for mutation in (lambda c: c["group"].update(closed=False), lambda c: c["group"]["members"][0].update(actionText="")):
            context = context_fixture(); mutation(context)
            self.assertEqual(settle_joint(FixtureSession(), context).status, "incomplete")
    def test_admission_does_not_imply_success(self):
        output = settle_joint(FixtureSession(), context_fixture())
        self.assertTrue(all(j["label"] == "not_achieved" for j in output.value["joint"]["judgments"]))
        self.assertIn("磨损", output.value["facts"][0]["text"])

    def test_end_before_first_fact_is_missing_model_output_not_protocol_gap(self):
        session = FixtureSession({"D05.3": result({"kind": "end"})})
        output = settle_joint(session, context_fixture())
        self.assertEqual(output.status, "incomplete")
        self.assertIn("missing_result_facts", output.reason)
        self.assertNotIn("interface_gap", output.reason)
        self.assertNotIn("D05.4", [component for component, _ in session.calls])
        self.assertNotIn("D05.5", [component for component, _ in session.calls])

    def test_semantic_incomplete_stops_before_facts_and_keeps_all_judgments(self):
        joint = {"judgments": [{"attemptId": "a", "label": "incomplete"},
                               {"attemptId": "b", "label": "not_achieved"}]}
        provider = FixtureSession({"D05.2": result(joint)})
        session = ModelSession(provider.call, binding={"pointId": "point", "version": 3},
            identity=ModelIdentity("fixture", "fixture", "fixture", "fixture", "fp32", "test"))
        answer = settle_joint(session, context_fixture())
        self.assertEqual(answer.status, "incomplete")
        self.assertEqual(answer.reason, "semantic_incomplete:D05.2:a")
        self.assertEqual([c for c, _ in provider.calls], ["D05.1", "D05.2"])
        self.assertEqual(session.attempts[-1]["completion"]["value"], joint)

    def test_semantic_incomplete_attempts_follow_frozen_order_not_model_order(self):
        provider = FixtureSession({"D05.2": result({"judgments": [
            {"attemptId": "b", "label": "incomplete"}, {"attemptId": "a", "label": "incomplete"}]})})
        answer = settle_joint(provider, context_fixture())
        self.assertEqual(answer.reason, "semantic_incomplete:D05.2:a,b")

    def test_backend_semantic_incomplete_is_preserved_but_timeout_is_not_abstention(self):
        for reason in ("semantic_incomplete:D05.2:a", "timeout"):
            provider = FixtureSession({"D05.2": incomplete(reason)})
            answer = settle_joint(provider, context_fixture())
            self.assertEqual(answer.reason, reason)
            self.assertEqual([c for c, _ in provider.calls], ["D05.1", "D05.2"])

    def test_incomplete_label_does_not_hide_missing_attempt_coverage(self):
        provider = FixtureSession({"D05.2": result({"judgments": [{"attemptId": "a", "label": "incomplete"}]})})
        answer = settle_joint(provider, context_fixture())
        self.assertEqual(answer.status, "incomplete")
        self.assertNotIn("semantic_incomplete", answer.reason)
    def test_timeout_empty_or_missing_member_cannot_be_result(self):
        for override in (incomplete("timeout"), empty(), result({"facts": [{"factId": "fact:1", "memberIds": ["a"]}], "checkedMemberIds": ["a", "b"]})):
            self.assertEqual(settle_joint(FixtureSession({"D05.5": override}), context_fixture()).status, "incomplete")
    def test_conflict_rejects_without_rewriting_frozen_inputs(self):
        context = context_fixture(); before = copy.deepcopy(context)
        out = settle_joint(FixtureSession({"D05.4": result({"verdict": "fail"})}), context)
        self.assertEqual(out.status, "incomplete"); self.assertEqual(context, before)
    def test_fact_budget_is_incomplete_not_silent_end(self):
        out = settle_joint(FixtureSession({"D05.3": result({"kind": "fact", "text": "仍在生成"})}), context_fixture(), max_facts=1)
        self.assertEqual(out.status, "incomplete"); self.assertIn("budget_pause", out.reason)
    def test_all_fragment_attempts_require_judgment(self):
        context = context_fixture()
        context["group"]["members"][0]["fragments"] = [{"id": "f1", "text": "尝试走近"}, {"id": "f2", "text": "若能接近则尝试拿取"}]
        context["group"]["members"][0]["actionText"] = "\n".join(f["text"] for f in context["group"]["members"][0]["fragments"])
        out = settle_joint(FixtureSession(), context)
        self.assertEqual({j["attemptId"] for j in out.value["joint"]["judgments"]}, {"f1", "f2", "b"})


class UpdatesTests(unittest.TestCase):
    def run_case(self, session=None, context=None, preview=None, **kwargs):
        context = context or context_fixture()
        settlement = None if context.get("time_scan") else settle_joint(FixtureSession(), context).value
        preview = preview or FixturePreview(context["world"])
        return run_updates(session or FixtureSession(), context, settlement, preview, allocate, **kwargs), preview
    def test_six_stages_no_changes_remain_complete_with_mapping(self):
        out, preview = self.run_case()
        self.assertEqual(out.status, "result", out.reason)
        self.assertEqual([x["stage"] for x in out.value["updates"]], list(STAGES))
        self.assertEqual(len(preview.calls), 6)
        self.assertEqual(out.value["candidates"]["taskCoverageIds"], ["a", "b", "off"])
        self.assertFalse(out.value["committed"])
    def test_removal_multiple_subtasks_offscene_personality_and_sanity(self):
        session = FixtureSession(effects=True)
        out, _ = self.run_case(session)
        self.assertEqual(out.status, "result", out.reason)
        candidate = out.value["candidates"]
        self.assertIsNone(candidate["appearances"]["tool"][0]["text"])
        self.assertEqual(len(candidate["subtasksAdded"]["b"]), 2)
        self.assertTrue(all(t["status"] == "pending" for t in candidate["subtasksAdded"]["b"]))
        self.assertEqual(len(candidate["personalities"]["off"]), 3)
        self.assertEqual(candidate["sanities"], {"off": 48})
        self.assertEqual(candidate["personalityCoverageIds"], ["a", "b", "off"])
        u4 = next(p for c, p in session.calls if c == "U4.1")
        self.assertEqual(u4["world"]["characters"]["a"]["tasks"]["at"]["status"], "achieved")
        sanity = [p for c, p in session.calls if c == "U6.1"]
        self.assertEqual([p["entityId"] for p in sanity], ["off"])
    def test_claimed_record_scan_does_not_default_omitted_operations_to_keep(self):
        for component in ("U2.1", "U5.1"):
            with self.subTest(component=component):
                def omit(payload):
                    selection = FixtureSession().call(component, payload).value
                    operation = next(op for op in selection["operations"] if op["recordIds"])
                    operation["recordIds"] = []
                    return result(selection)
                session = FixtureSession({component: omit}, effects=component == "U5.1")
                out, preview = self.run_case(session)
                self.assertEqual(out.status, "incomplete")
                self.assertIn("record operation coverage incomplete", out.reason)
                self.assertEqual(len(preview.calls), 1 if component == "U2.1" else 4)
    def test_same_record_cannot_receive_multiple_keep_operations(self):
        for component in ("U2.1", "U5.1"):
            with self.subTest(component=component):
                def repeat(payload):
                    selection = FixtureSession().call(component, payload).value
                    selection["operations"].append(copy.deepcopy(next(op for op in selection["operations"] if op["recordIds"])))
                    return result(selection)
                out, _ = self.run_case(FixtureSession({component: repeat}, effects=component == "U5.1"))
                self.assertEqual(out.status, "incomplete")
                self.assertIn("repeated keep", out.reason)
    def test_simultaneous_moves_validate_final_graph(self):
        world = world_fixture()
        world["items"]["tool"]["position"] = {"containerId": "box"}
        # Individually applying box -> tool would cycle; simultaneous tool -> room removes it.
        validate_positions(world, {"box": {"containerId": "tool"}, "tool": {"containerId": "room"}})
        with self.assertRaises(ContractError):
            validate_positions(world, {"box": {"containerId": "tool"}})
    def test_cross_location_relative_target_rejected(self):
        with self.assertRaises(ContractError):
            validate_positions(world_fixture(), {"tool": {"containerId": "room", "relativeTo": {"entityId": "off", "relation": "beside"}}})
    def test_missing_task_or_offscene_person_is_not_empty(self):
        for override in (result({"checkedCharacterIds": ["a", "b", "off"], "decisions": []}), incomplete("truncated")):
            out, _ = self.run_case(FixtureSession({"U3.1": override}))
            self.assertEqual(out.status, "incomplete")
    def test_invalid_sanity_is_rejected_without_clamping(self):
        for value in (101, -1, 42.0, True, "42"):
            out, _ = self.run_case(FixtureSession({"U6.1": result(value)}, effects=True))
            self.assertEqual(out.status, "incomplete")
            self.assertIn("no clipping", out.reason)
    def test_stale_preview_rejected_and_progress_saved(self):
        context = context_fixture(); actual = FixturePreview(context["world"]); saved = []
        def stale(req):
            response = actual(req).value; response["candidateHash"] = "old"
            return result(response)
        out, _ = self.run_case(context=context, preview=stale, progress_sink=saved.append)
        self.assertEqual(out.status, "incomplete")
        self.assertEqual(saved[-1]["status"], "incomplete")
        self.assertEqual(len(saved[-1]["calls"]), 1)
    def test_initial_record_cannot_be_removed(self):
        def bad(payload):
            valid = FixtureSession(effects=True).call("U2.1", payload).value
            valid["operations"][2] = {"entityId": "tool", "op": "remove", "recordIds": ["initialAppearance"]}
            return result(valid)
        out, _ = self.run_case(FixtureSession({"U2.1": bad}))
        self.assertEqual(out.status, "incomplete")
    def test_conflicting_description_operations_rejected(self):
        def bad(payload):
            valid = FixtureSession(effects=True).call("U2.1", payload).value
            valid["operations"].append({"entityId": "tool", "op": "remove", "recordIds": ["scar"]})
            return result(valid)
        out, _ = self.run_case(FixtureSession({"U2.1": bad}))
        self.assertEqual(out.status, "incomplete"); self.assertIn("conflicting", out.reason)
    def test_parent_not_inferred_from_child(self):
        context = context_fixture()
        context["world"]["characters"]["a"]["tasks"]["child"] = {"id": "child", "ownerId": "a", "parentTaskId": "at", "goal": "局部目标", "status": "pending"}
        def task(payload):
            return result({"checkedCharacterIds": payload["characterIds"], "decisions": [{"taskId": key, "label": "achieved" if key == "child" else "pending"} for key in payload["taskIds"]]})
        out, _ = self.run_case(FixtureSession({"U3.1": task}), context=context)
        self.assertEqual(out.status, "result", out.reason)
        self.assertEqual(out.value["candidates"]["tasksAchieved"], {"a": ["child"]})
    def test_pure_time_full_task_scan_and_conditional_chain(self):
        context = {"world": world_fixture(), "binding": {"pointId": "time", "version": 2}, "time_scan": True,
                   "timeFact": {"id": "elapsed:1", "text": "一分钟经过。"}, "timeAdvance": {"boundary": "elapsed", "duration": {"amount": 1, "unit": "minute"}}}
        def no_appearance(payload):
            return FixtureSession().call("U2.1", payload)
        session = FixtureSession({"U2.1": no_appearance}, effects=True)
        out, _ = self.run_case(session, context=context)
        self.assertEqual(out.status, "result", out.reason)
        self.assertIsNone(out.value["candidates"]["groupId"])
        self.assertEqual(out.value["candidates"]["sanities"], {"off": 48})
        self.assertEqual(out.value["candidates"]["positions"], {})
    def test_fact_mapping_does_not_accept_ids_without_coverage(self):
        calls = [{"stage": "appearance", "changes": {"tool": {"entityId": "tool", "appearanceChanges": [{"id": "c", "text": "痕迹", "supersedes": []}]}}}]
        with self.assertRaises(ContractError):
            validate_fact_mapping({"verdict": "pass", "mappings": [{"factId": "f", "kind": "unchanged", "targets": []}]}, [{"id": "f", "text": "磨损"}], calls)
        with self.assertRaises(ContractError):
            validate_fact_mapping({"verdict": "pass", "mappings": [{"factId": "f", "kind": "gap", "targets": []}]}, [{"id": "f", "text": "知识"}], [])

    def test_fact_mapping_rejects_conflicting_duplicate_dispositions(self):
        calls = [{"stage": "position", "changes": {"tool": {"entityId": "tool", "positionSet": {"containerId": "a"}}}}]
        target = {"stage": "position", "entityId": "tool", "operationId": "positionSet"}
        mapping = {"verdict": "pass", "mappings": [
            {"factId": "f", "kind": "state", "targets": [target]},
            {"factId": "f", "kind": "unchanged", "targets": []}]}
        with self.assertRaises(ContractError):
            validate_fact_mapping(mapping, [{"id": "f", "text": "工具移到甲手中。"}], calls)

    def test_fact_mapping_rejects_repeated_target_within_one_fact(self):
        calls = [{"stage": "position", "changes": {"tool": {"entityId": "tool", "positionSet": {"containerId": "a"}}}}]
        target = {"stage": "position", "entityId": "tool", "operationId": "positionSet"}
        mapping = {"verdict": "pass", "mappings": [
            {"factId": "f", "kind": "state", "targets": [target, copy.deepcopy(target)]}]}
        with self.assertRaises(ContractError):
            validate_fact_mapping(mapping, [{"id": "f", "text": "工具移到甲手中。"}], calls)

    def test_fact_mapping_allows_multiple_facts_to_support_one_consequence(self):
        calls = [{"stage": "position", "changes": {"tool": {"entityId": "tool", "positionSet": {"containerId": "a"}}}}]
        target = {"stage": "position", "entityId": "tool", "operationId": "positionSet"}
        mapping = {"verdict": "pass", "mappings": [
            {"factId": key, "kind": "state", "targets": [copy.deepcopy(target)]} for key in ("f1", "f2")]}
        validate_fact_mapping(mapping, [{"id": "f1", "text": "乙松开工具。"},
                                        {"id": "f2", "text": "甲接住工具。"}], calls)
    def test_subtask_resource_limit_is_pause_not_partial_success(self):
        out, _ = self.run_case(FixtureSession(effects=True), max_new_tasks=1)
        self.assertEqual(out.status, "incomplete"); self.assertIn("budget_pause", out.reason)
    def test_preview_error_is_incomplete(self):
        def failed(_):
            raise TimeoutError("A preview timeout")
        out, _ = self.run_case(preview=failed)
        self.assertEqual(out.status, "incomplete"); self.assertIn("timeout", out.reason)


    def test_mutated_joint_packet_is_rejected_before_any_update_call(self):
        context = context_fixture()
        completed = settle_joint(FixtureSession(), context).value
        for field in ("facts", "joint", "associations", "results"):
            changed = copy.deepcopy(completed)
            changed[field] = {} if field != "facts" else [{"id": "fact:1", "text": "未经模型产生的新结果。"}]
            session = FixtureSession()
            outcome = run_updates(session, context, changed, FixturePreview(context["world"]), allocate)
            self.assertEqual(outcome.status, "incomplete")
            self.assertIn("content hash", outcome.reason)
            self.assertEqual(session.calls, [])
        update, _ = self.run_case()
        verify_candidate_packet(update.value)
        changed = copy.deepcopy(update.value)
        changed["factMapping"]["mappings"][0]["kind"] = "transient"
        with self.assertRaises(ContractError):
            verify_candidate_packet(changed)

    def test_result_and_time_fact_identity_collision_is_rejected(self):
        mapping = {"verdict": "pass", "mappings": [{"factId": "f", "kind": "unchanged", "targets": []}]}
        fact = {"id": "f", "text": "原事实"}
        with self.assertRaises(ContractError):
            validate_fact_mapping(mapping, [fact, copy.deepcopy(fact)], [])
        with self.assertRaises(ContractError):
            validate_fact_mapping(mapping, [fact], [], time_fact={"id": "f", "text": "时间事实"})

    def test_checkpoint_resumes_frozen_semantics_and_revalidates_all_previews(self):
        context = context_fixture()
        settled = settle_joint(FixtureSession(), context).value
        identity = ModelIdentity("fixture-explicit", "fixture-weights", "fixture-adapter", "fixture-tokenizer", "fp32", "fixture-code")
        provider1 = FixtureSession(effects=True)
        first = ModelSession(provider1.call, binding=context["binding"], identity=identity)
        preview1 = FixturePreview(context["world"])
        def paused_preview(request):
            if request["stage"] == "subtasks":
                return incomplete("temporary preview timeout")
            return preview1(request)
        stopped = run_updates(first, context, settled, paused_preview, allocate)
        self.assertEqual(stopped.status, "incomplete")
        snapshot = first.checkpoint()
        provider2 = FixtureSession(effects=True)
        resumed = ModelSession(provider2.call, binding=context["binding"], identity=identity)
        resumed.restore(snapshot)
        preview2 = FixturePreview(context["world"])
        completed = run_updates(resumed, context, settled, preview2, allocate)
        self.assertEqual(completed.status, "result", completed.reason)
        self.assertEqual(provider2.calls[0][0], "U5.1")
        self.assertFalse(any(c in ("U1.1", "U2.1", "U3.1", "U4.1", "U4.2") for c, _ in provider2.calls))
        self.assertEqual(len(preview2.calls), 6)
        self.assertEqual(len(resumed.replay_events), len(first.attempts))
        self.assertTrue(all(not event["modelCalled"] for event in resumed.replay_events))
        self.assertEqual(completed.value["updates"][3], next(event["input"]["proposed"] for event in first.attempts if event["component"] == "D06.P.review" and event["input"]["stage"] == "subtasks"))

    def test_checkpoint_wrong_model_or_point_cannot_restore(self):
        context = context_fixture()
        identity = ModelIdentity("fixture-explicit", "weights", "adapter", "tokenizer", "fp32", "code")
        first = ModelSession(FixtureSession().call, binding=context["binding"], identity=identity)
        first.call("U1.1", {"entityIds": ["a"]})
        for changed_binding, changed_identity in (({**context["binding"], "version": 99}, identity),
                (context["binding"], ModelIdentity("other", "weights", "adapter", "tokenizer", "fp32", "code"))):
            other = ModelSession(FixtureSession().call, binding=changed_binding, identity=changed_identity)
            with self.assertRaises(ContractError):
                other.restore(first.checkpoint())

    def test_checkpoint_replay_does_not_accept_stale_preview(self):
        context = context_fixture(); settled = settle_joint(FixtureSession(), context).value
        identity = ModelIdentity("fixture-explicit", "weights", "adapter", "tokenizer", "fp32", "code")
        first = ModelSession(FixtureSession().call, binding=context["binding"], identity=identity)
        self.assertEqual(run_updates(first, context, settled, FixturePreview(context["world"]), allocate).status, "result")
        resumed = ModelSession(lambda *_: self.fail("all completed model calls must replay"), binding=context["binding"], identity=identity)
        resumed.restore(first.checkpoint())
        preview = FixturePreview(context["world"])
        def stale(request):
            output = preview(request).value
            output["binding"]["version"] = 999
            return result(output)
        outcome = run_updates(resumed, context, settled, stale, allocate)
        self.assertEqual(outcome.status, "incomplete")
        self.assertIn("stale preview", outcome.reason)
        self.assertEqual(len(preview.calls), 1)

    def test_u5_preview_interface_gap_stops_before_u6_without_filling_old_sanity(self):
        context = context_fixture(); actual = FixturePreview(context["world"])
        def current_a_boundary(request):
            if request["stage"] == "personality":
                return incomplete("interface_gap: current SettlementGroup requires U6 sanity before U5 preview")
            return actual(request)
        session = FixtureSession(effects=True)
        out, _ = self.run_case(session, context=context, preview=current_a_boundary)
        self.assertEqual(out.status, "incomplete")
        self.assertIn("interface_gap", out.reason)
        self.assertFalse(any(c == "U6.1" for c, _ in session.calls))

    def test_d_baseline_inherited_a_validator_has_no_partial_u5_mode(self):
        # Execute the ACTUAL checked-out validator body without importing
        # Pydantic. This checks Python rule behavior, not full schema parsing.
        import ast
        import json
        from types import SimpleNamespace
        root = Path(__file__).resolve().parents[3]
        source = root / "backend/app/schemas/world/v2/work.py"
        module = ast.parse(source.read_text())
        cls = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "SettlementGroup")
        method = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "stages"))
        method.decorator_list = []
        scope = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(source), "exec"), scope)
        candidate = SimpleNamespace(groupId="group", actorIds=["a"], positions={}, appearances={},
            tasksAchieved={"a": ["at"]}, subtasksAdded={}, personalities={"off": [{"id": "new", "text": "更愿合作", "supersedes": []}]}, sanities={})
        with self.assertRaisesRegex(ValueError, "personality changes and sanity recalculation must pair"):
            scope["stages"](candidate)
        candidate.sanities = {"off": 48}
        self.assertIs(scope["stages"](candidate), candidate)
        schema = json.loads((root / "design/world-protocol/v2/world-protocol.schema.json").read_text())
        contract = schema["$defs"]["SettlementGroup"]
        self.assertIn("sanities", contract["required"])
        self.assertIn("personalities", contract["required"])
        self.assertNotIn("completedStage", contract["properties"])

    def test_d_baseline_inherited_a_schema_rejects_partial_u5_preview(self):
        try:
            import pydantic
            if not hasattr(pydantic.BaseModel, "model_validate"):
                self.skipTest("local Pydantic v2 unavailable")
        except ImportError:
            self.skipTest("local Pydantic v2 unavailable")
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
        from app.schemas.world.v2.work import SettlementGroup
        payload = {"groupId": "group", "actorIds": ["a"], "positions": {}, "appearances": {},
                   "tasksAchieved": {"a": ["at"]}, "subtasksAdded": {},
                   "personalities": {"off": [{"id": "new", "text": "愿意协作", "supersedes": []}]},
                   "sanities": {}, "taskCoverageIds": ["a", "b", "off"], "personalityCoverageIds": ["a", "b", "off"]}
        with self.assertRaises(pydantic.ValidationError) as rejection:
            SettlementGroup.model_validate(payload)
        self.assertIn("personality changes and sanity recalculation must pair", str(rejection.exception))
        payload["sanities"] = {"off": 48}
        self.assertEqual(SettlementGroup.model_validate(payload).sanities, {"off": 48})
        complete, _ = self.run_case(FixtureSession(effects=True))
        self.assertEqual(complete.status, "result", complete.reason)
        actual_wire = SettlementGroup.model_validate(complete.value["candidates"])
        self.assertEqual(actual_wire.sanities, {"off": 48})
        self.assertEqual(len(actual_wire.subtasksAdded["b"]), 2)
        self.assertIsNone(actual_wire.appearances["tool"][0].text)

    def test_actual_upstream_d02_d03_d04_output_drives_d05_and_all_six_stages(self):
        # Only engineering orchestration evidence. Every model is an explicit
        # fixture double; no fixed answer is shipped as a model implementation.
        from test_short_intent import canonical_context, Script, sequence, target_rows, receipt
        from short_intent import run_action_chain
        context = canonical_context()
        context["confirmedPrefix"] = [{"memberId": "c", "actionText": "池远尝试等待。"}]
        rows = sequence(["安禾尝试把图纸递给贝青。"])
        rows += target_rows(["b", "c"])
        rows += [("D04.1", result({"threatSourceIds": ["a"], "constraint": "回应递来的图纸。"}))]
        rows += sequence(["贝青尝试接住图纸。"], actor="b", decision=False)
        rows += target_rows([])
        actual = []
        def roll(source, targets):
            receipts = [receipt(source.actor_id, target, eligible=target != "c") for target in targets]
            actual.extend(copy.deepcopy(receipts))
            return receipts
        action_session = Script(rows)
        chain = run_action_chain(action_session, context, "op", roll_targets=roll)
        self.assertEqual(chain.status, "result", chain.reason)
        bound = settlement_context(context, chain, group_id="group", binding={"pointId": "p", "version": 3})
        self.assertEqual(bound["group"]["judgments"], actual)
        self.assertEqual(bound["group"]["alreadyActedIds"], ["c"])
        def audit(payload):
            return result({"verdict": "pass", "checkedActionIds": ["a", "b"], "checkedFactIds": ["fact:1"],
                           "checkedRollIds": [r["rollId"] for r in actual]})
        session = FixtureSession({"D05.4": audit})
        joint = settle_joint(session, bound)
        self.assertEqual(joint.status, "result", joint.reason)
        self.assertEqual({j["attemptId"] for j in joint.value["joint"]["judgments"]}, {"a:fragment-1", "b:fragment-1"})
        update = run_updates(session, bound, joint.value, FixturePreview(bound["world"]), allocate)
        self.assertEqual(update.status, "result", update.reason)
        self.assertEqual(update.value["candidates"]["actorIds"], ["a", "b"])
        self.assertEqual(update.value["candidates"]["taskCoverageIds"], ["a", "b", "c"])
        for component, payload in session.calls:
            self.assertEqual(payload["context"]["group"]["judgments"], actual)
        self.assertFalse(update.value["committed"])


if __name__ == "__main__":
    unittest.main()

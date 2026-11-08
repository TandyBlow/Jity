from copy import deepcopy
import unittest

from jity_eval.replay.probes import ProbeError, extract_probes, validate_probes


def history(length=55):
    records = []
    for turn in range(1, length + 1):
        records.append({
            "turn": turn, "turn_id": "node-%s" % turn,
            "player_action": "检查当天的照明。", "output": {
                "narration": "这一轮没有新的线索。", "dialogue": [], "memory_updates": {},
            }, "state": {"world_facts": [{"name": "档案位置", "description": "西塔第三个抽屉"}]},
        })
    records[1]["output"]["narration"] = "你确认档案位置是西塔第三个抽屉。"
    records[1]["output"]["memory_updates"] = {"world_facts_upserted": [
        {"name": "档案位置", "description": "西塔第三个抽屉", "aliases": ["那卷文件"]},
    ]}
    return {"initial": {"state": {}}, "turns": records}


class ReplayProbeTests(unittest.TestCase):
    def test_snapshot_copies_are_not_rementions_and_gold_is_separate(self):
        dataset = history()
        before = deepcopy(dataset)
        document = extract_probes(dataset)
        self.assertEqual(document["coverage"]["by_delay"], {"10": 2, "20": 2, "40": 2})
        self.assertEqual({p["source_turn"] for p in document["probes"]}, {2})
        self.assertTrue(all(p["review_required"] for p in document["probes"]))
        self.assertTrue(all(p["mention_detection"] == "literal_alias" for p in document["probes"]))
        self.assertNotIn("西塔第三个抽屉", str(document["probes"]))
        self.assertEqual(dataset, before)
        result = validate_probes(dataset, document["probes"], document["gold"])
        self.assertEqual(result["independent_branches"], 6)

    def test_alias_remention_restarts_the_delay(self):
        dataset = history(65)
        dataset["turns"][14]["player_action"] = "确认那卷文件仍然保存完好。"
        document = extract_probes(dataset)
        self.assertFalse(any(p["source_turn"] == 2 and p["delay"] in (20, 40) for p in document["probes"]))
        self.assertTrue(any(p["source_turn"] == 15 and p["checkpoint_turn"] == 55 for p in document["probes"]))
        validate_probes(dataset, document["probes"], document["gold"])

    def test_unselected_option_is_still_an_explicit_remention(self):
        dataset = history(55)
        dataset["turns"][4]["output"]["options"] = [
            "继续整理值班记录。", "检查照明。", "返回去检查档案位置是否改变。",
        ]
        document = extract_probes(dataset)
        candidate = document["candidates"][0]
        self.assertEqual(candidate["literal_mention_turns"], [2, 5])
        self.assertFalse(any(p["source_turn"] == 2 for p in document["probes"]))
        self.assertTrue(any(p["source_turn"] == 5 and p["checkpoint_turn"] == 45
                            for p in document["probes"]))
        self.assertIn("output.options[2]", {e["channel"] for e in candidate["literal_mention_evidence"]
                                           if e["turn"] == 5})
        validate_probes(dataset, document["probes"], document["gold"])

    def test_every_output_string_path_counts_as_a_remention(self):
        fields = [
            ({"current_location": "那卷文件旁边"}, "output.current_location"),
            ({"scene_prompt": "A desk near 那卷文件"}, "output.scene_prompt"),
            ({"action_check": {"check": {"stakes": "确认那卷文件的状态"}}},
             "output.action_check.check.stakes"),
            ({"option_checks": [{"stakes": "成功查明档案位置"}]}, "output.option_checks[0].stakes"),
            ({"memory_updates": {"key_event": "确认那卷文件仍完好。"}}, "output.memory_updates.key_event"),
            ({"memory_updates": {"player_status_patch": {"notes": "还要确认档案位置。"}}},
             "output.memory_updates.player_status_patch.notes"),
            ({"dialogue": [{"speaker": "管理员", "text": "再确认那卷文件。"}]}, "output.dialogue[0].text"),
            ({"custom-field": {"future": [{"text": "档案位置没有变化。"}]}},
             'output["custom-field"].future[0].text'),
        ]
        for extra_output, expected_path in fields:
            with self.subTest(channel=expected_path):
                dataset = history(55)
                dataset["turns"][14]["output"].update(extra_output)
                document = extract_probes(dataset)
                candidate = document["candidates"][0]
                self.assertEqual(candidate["literal_mention_turns"], [2, 15])
                self.assertIn(expected_path, {e["channel"] for e in candidate["literal_mention_evidence"]
                                             if e["turn"] == 15})
                self.assertFalse(any(p["source_turn"] == 2 and p["delay"] in (20, 40)
                                     for p in document["probes"]))
                self.assertTrue(any(p["source_turn"] == 15 and p["checkpoint_turn"] == 55
                                    for p in document["probes"]))
                validate_probes(dataset, document["probes"], document["gold"])

    def test_changed_fact_uses_the_version_available_at_each_checkpoint(self):
        dataset = history(65)
        dataset["turns"][29]["output"]["memory_updates"] = {"world_facts_upserted": [
            {"name": "档案位置", "description": "北楼密封保险柜"},
        ]}
        document = extract_probes(dataset)
        answers = {g["probe_id"]: g for g in document["gold"]}
        for probe in document["probes"]:
            expected = "西塔第三个抽屉" if probe["checkpoint_turn"] < 30 else "北楼密封保险柜"
            self.assertEqual(answers[probe["id"]]["expected_value"], expected)
        self.assertFalse(any(p["source_turn"] == 2 and p["delay"] == 40 for p in document["probes"]))
        validate_probes(dataset, document["probes"], document["gold"])

    def test_future_fact_cannot_create_an_earlier_probe(self):
        dataset = history(45)
        dataset["turns"][39]["output"]["memory_updates"] = {"npcs_upserted": [
            {"name": "新管理员", "description": "退休档案修复师"},
        ]}
        document = extract_probes(dataset)
        future = next(c for c in document["candidates"] if c["name"] == "新管理员")
        self.assertEqual(future["probe_ids"], [])

    def test_future_alias_does_not_retroactively_change_earlier_mentions(self):
        dataset = history(65)
        dataset["turns"][1]["output"]["memory_updates"]["world_facts_upserted"][0]["aliases"] = []
        dataset["turns"][9]["output"]["narration"] = "有人谈到了那卷文件。"
        dataset["turns"][29]["output"]["memory_updates"] = {"world_facts_upserted": [
            {"name": "档案位置", "description": "西塔第三个抽屉", "aliases": ["那卷文件"]},
        ]}
        document = extract_probes(dataset)
        fact = document["candidates"][0]
        self.assertEqual(fact["literal_mention_turns"], [2, 30])
        self.assertTrue(any(p["source_turn"] == 2 and p["checkpoint_turn"] == 22 for p in document["probes"]))

    def test_question_cannot_include_expected_value(self):
        dataset = history()
        dataset["turns"][1]["output"]["memory_updates"]["world_facts_upserted"][0]["description"] = "档案位置"
        document = extract_probes(dataset)
        self.assertFalse(document["probes"])
        self.assertEqual(document["coverage"]["leading_questions_excluded"], 6)

    def test_public_probe_cannot_contain_gold_or_source_quote(self):
        dataset = history()
        document = extract_probes(dataset)
        for field in ("expected_value", "evidence"):
            probes = deepcopy(document["probes"])
            probes[0][field] = "西塔第三个抽屉"
            with self.assertRaises(ProbeError):
                validate_probes(dataset, probes, document["gold"])

    def test_forged_delay_and_duplicate_branch_are_rejected(self):
        dataset = history()
        document = extract_probes(dataset)
        probes = deepcopy(document["probes"])
        probes[0]["source_turn"] = 1
        with self.assertRaises(ProbeError):
            validate_probes(dataset, probes, document["gold"])
        probes = deepcopy(document["probes"])
        probes[1]["branch_id"] = probes[0]["branch_id"]
        with self.assertRaises(ProbeError):
            validate_probes(dataset, probes, document["gold"])

    def test_unknown_answer_and_extra_gold_are_rejected(self):
        dataset = history()
        document = extract_probes(dataset)
        gold = deepcopy(document["gold"])
        gold[0]["expected_value"] = "未来才公开的地点"
        with self.assertRaises(ProbeError):
            validate_probes(dataset, document["probes"], gold)
        gold = deepcopy(document["gold"])
        gold.append({"probe_id": "unrelated"})
        with self.assertRaises(ProbeError):
            validate_probes(dataset, document["probes"], gold)

    def test_human_annotation_can_add_evidenced_semantic_mention(self):
        dataset = history(65)
        dataset["turns"][19]["output"]["narration"] = "收好的那份资料仍在原处。"
        preliminary = extract_probes(dataset)
        fact_id = preliminary["candidates"][0]["fact_id"]
        annotations = [{"fact_id": fact_id, "mention_turns": [2, 20],
                        "reviewed_through_turn": 65, "reviewer": "人工复核者",
                        "evidence": [{"turn": 20, "channel": "output.narration",
                                      "quote": "收好的那份资料仍在原处。"}]}]
        document = extract_probes(dataset, annotations=annotations)
        self.assertTrue(any(p["source_turn"] == 20 and p["checkpoint_turn"] == 60 for p in document["probes"]))
        self.assertFalse(any(p["source_turn"] == 2 and p["delay"] in (20, 40) for p in document["probes"]))
        self.assertTrue(all(not p["review_required"] for p in document["probes"]))
        validate_probes(dataset, document["probes"], document["gold"], annotations)
        with self.assertRaises(ProbeError):
            validate_probes(dataset, document["probes"], document["gold"])

    def test_annotation_cannot_erase_literal_mentions_or_invent_quotes(self):
        dataset = history(65)
        dataset["turns"][19]["output"]["narration"] = "档案位置依然没有改变。"
        fact_id = extract_probes(dataset)["candidates"][0]["fact_id"]
        annotation = {"fact_id": fact_id, "mention_turns": [2], "reviewed_through_turn": 65,
                      "reviewer": "reviewer", "evidence": []}
        with self.assertRaises(ProbeError):
            extract_probes(dataset, annotations=[annotation])
        annotation["mention_turns"] = [2, 20, 25]
        annotation["evidence"] = [{"turn": 25, "channel": "output.narration", "quote": "不存在的句子"}]
        with self.assertRaises(ProbeError):
            extract_probes(dataset, annotations=[annotation])

    def test_partial_review_does_not_confirm_later_checkpoints(self):
        dataset = history()
        fact_id = extract_probes(dataset)["candidates"][0]["fact_id"]
        annotation = {"fact_id": fact_id, "mention_turns": [2], "reviewed_through_turn": 15,
                      "reviewer": "reviewer", "evidence": []}
        document = extract_probes(dataset, annotations=[annotation])
        self.assertTrue(all(not p["review_required"] for p in document["probes"] if p["checkpoint_turn"] <= 15))
        self.assertTrue(all(p["review_required"] for p in document["probes"] if p["checkpoint_turn"] > 15))
        validate_probes(dataset, document["probes"], document["gold"], [annotation])

    def test_continuous_history_and_valid_delays_are_required(self):
        dataset = history()
        dataset["turns"][2]["turn"] = 40
        with self.assertRaises(ProbeError):
            extract_probes(dataset)
        for delays in ((True,), (0,), (10, 10), ()):
            with self.assertRaises(ProbeError):
                extract_probes(history(), delays)

    def test_extraction_is_deterministic_and_has_no_answered_branches(self):
        one, two = extract_probes(history()), extract_probes(history())
        self.assertEqual(one, two)
        self.assertTrue(all(p["answer_status"] == "not_queried" for p in one["probes"]))
        self.assertEqual(len({p["branch_id"] for p in one["probes"]}), len(one["probes"]))


if __name__ == "__main__":
    unittest.main()

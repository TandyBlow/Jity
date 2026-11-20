"""契约的固定样例测试：升、降各一条，逐字符比对送入模型的字符串。"""
import unittest
import fact_contract as FC


class ContractTests(unittest.TestCase):
    def test_sanity_up_exact_string(self):
        line = FC.serialize_fact({"kind": "sanity_changed", "name": "沈砚",
                                  "from": 9, "to": 12})
        self.assertEqual(line, "沈砚｜状态变化｜放松")

    def test_sanity_down_exact_string(self):
        line = FC.serialize_fact({"kind": "sanity_changed", "name": "沈砚",
                                  "from": 12, "to": 9})
        self.assertEqual(line, "沈砚｜状态变化｜发紧")

    def test_other_kinds_match_training_format(self):
        cases = [
            ({"kind": "moved", "name": "沈砚", "from": "潮渡", "to": "雾堤"},
             "沈砚｜移动｜潮渡→雾堤"),
            ({"kind": "outcome", "name": "沈砚", "text": "把灯罩擦得透亮"},
             "沈砚｜结果｜把灯罩擦得透亮"),
            ({"kind": "appearance_changed", "name": "沈砚", "text": "袖口沾了铜油"},
             "沈砚｜外貌变化｜袖口沾了铜油"),
            ({"kind": "no_change"}, "场景｜无变化"),
        ]
        for fact, want in cases:
            with self.subTest(kind=fact["kind"]):
                self.assertEqual(FC.serialize_fact(fact), want)

    def test_old_wrong_formats_are_rejected(self):
        bad = [("sanity_changed", "状态变化｜沈砚｜发紧"),
               ("sanity_changed", "理智｜沈砚｜下降"),
               ("appearance_changed", "外观｜沈砚｜袖口沾了油"),
               ("no_change", "无变化｜"),
               ("moved", "移动｜沈砚｜潮渡→雾堤")]
        for kind, line in bad:
            with self.subTest(line=line):
                with self.assertRaises(FC.ContractError):
                    FC.check_line(kind, line)

    def test_built_input_carries_the_checked_line(self):
        header = "短句任务。\n地点=旧灯塔\n地点可见=铜灯罩\n场景=夜；雾\n视角=沈砚；第三人称"
        for fact, want in (
                ({"kind": "sanity_changed", "name": "沈砚", "from": 12, "to": 9},
                 "沈砚｜状态变化｜发紧"),
                ({"kind": "sanity_changed", "name": "沈砚", "from": 9, "to": 12},
                 "沈砚｜状态变化｜放松")):
            build = FC.build_unit_input(header, fact)
            self.assertIn(f"事实={want}", build)
            self.assertEqual(FC.unit_fact_line(build), want)

    def test_bulk_check_flags_wrong_units(self):
        units = [{"unitId": "x", "kind": "sanity_changed",
                  "input": "短句任务。\n事实=状态变化｜沈砚｜发紧\n"}]
        self.assertEqual(len(FC.check_units(units, strict=False)), 1)
        with self.assertRaises(FC.ContractError):
            FC.check_units(units)


if __name__ == "__main__":
    unittest.main()

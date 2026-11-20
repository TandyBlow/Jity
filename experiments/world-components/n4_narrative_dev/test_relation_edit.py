import sys
from relation_edit import apply_before, VALIDATOR

UNITS = [("f0", "林川", "林川的袖口沾了雨。"),
         ("f1", "周宁", "周宁的斗篷下摆湿了一片。")]
AUTH = {"verdict": "pass", "validatorVersion": VALIDATOR,
        "relations": [{"type": "before", "fromFactId": "f0", "toFactId": "f1",
                       "evidence": [{"type": "event", "evidenceId": "p1/person_a/appearance/c1"}],
                       "authorization": {"verdict": "pass", "validatorVersion": VALIDATOR}}]}
fails = []
def case(name, auth, units, expect_text, expect_reason=None):
    out = apply_before(units, auth)
    if out["text"] != expect_text:
        fails.append(f"{name}: text={out['text']!r} 期望 {expect_text!r}")
    if expect_reason and not any(f["reason"] == expect_reason for f in out["fallbacks"]):
        fails.append(f"{name}: fallbacks={out['fallbacks']} 期望 {expect_reason}")

case("授权通过", AUTH, UNITS, "林川的袖口沾了雨。随后，周宁的斗篷下摆湿了一片。")
case("无关系", None, UNITS, "林川的袖口沾了雨。周宁的斗篷下摆湿了一片。", "no-authorized-relation")
case("校验失败", {**AUTH, "verdict": "reject", "relations": []}, UNITS,
     "林川的袖口沾了雨。周宁的斗篷下摆湿了一片。", "no-authorized-relation")
case("版本不符", {**AUTH, "validatorVersion": "v0"}, UNITS,
     "林川的袖口沾了雨。周宁的斗篷下摆湿了一片。", "validator-version-mismatch")
reversed_auth = {"verdict": "pass", "validatorVersion": VALIDATOR,
                 "relations": [{"type": "before", "fromFactId": "f1", "toFactId": "f0",
                                "evidence": [], "authorization": {"verdict": "pass",
                                                                  "validatorVersion": VALIDATOR}}]}
case("方向相反", reversed_auth, UNITS,
     "林川的袖口沾了雨。周宁的斗篷下摆湿了一片。", "relation-reversed")
spread = [("f0", "林川", "林川的袖口沾了雨。"), ("f1", "陈默", "陈默合上书。"),
          ("f2", "周宁", "周宁的斗篷下摆湿了一片。")]
far = {"verdict": "pass", "validatorVersion": VALIDATOR,
       "relations": [{"type": "before", "fromFactId": "f0", "toFactId": "f2",
                      "evidence": [], "authorization": {"verdict": "pass",
                                                        "validatorVersion": VALIDATOR}}]}
case("不相邻", far, spread, "林川的袖口沾了雨。陈默合上书。周宁的斗篷下摆湿了一片。",
     "not-adjacent")
shift = [("f0", "林川", "林川的袖口沾了雨。"), ("f1", "周宁", "他的斗篷下摆湿了一片。")]
case("后句不以姓名开头", AUTH, shift, "林川的袖口沾了雨。他的斗篷下摆湿了一片。",
     "subject-not-at-start")
print("version", VERSION if (VERSION := __import__('relation_edit').VERSION) else "")
print("失败", len(fails))
for f in fails: print(" ", f)
sys.exit(1 if fails else 0)

"""真实链条 → u240 短句 → 授权关系 → 加“随后”。四条验收一次跑完。"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from relation_edit import apply_before, VALIDATOR, VERSION

ART = HERE.parents[2] / "artifacts" / "world-provenance"
chain = json.loads((ART / "n3-authorized-relation.json").read_text(encoding="utf-8"))
generated = json.loads((ART / "chain-out.json").read_text(encoding="utf-8"))["rows"]
units = [(row["factId"], row["name"], row["text"]) for row in generated]
plain = "".join(text for _, _, text in units)

authorized = apply_before(units, chain)
negatives = {}
negatives["no-relation"] = apply_before(units, None)
negatives["rejected"] = apply_before(units, {**chain, "verdict": "reject", "relations": []})
negatives["reversed"] = apply_before(units, {
    "verdict": "pass", "validatorVersion": VALIDATOR,
    "relations": [{"type": "before", "fromFactId": "f1", "toFactId": "f0",
                   "evidence": [], "authorization": {"verdict": "pass",
                                                     "validatorVersion": VALIDATOR}}]})
spread = [units[0], ("f1x", "陈默", "陈默合上书。"), units[1]]
spread_text = "".join(text for _, _, text in spread)
negatives["not-adjacent"] = apply_before(
    spread,
    {"verdict": "pass", "validatorVersion": VALIDATOR,
     "relations": [{"type": "before", "fromFactId": "f0", "toFactId": "f1",
                    "evidence": [], "authorization": {"verdict": "pass",
                                                      "validatorVersion": VALIDATOR}}]})

fact_texts = [text.rstrip("。") for _, _, text in units]
checks = {
    "事件来源真实": [ev["evidenceId"] for rel in chain["relations"] for ev in rel["evidence"]],
    "授权结论": chain["verdict"],
    "校验器版本": chain["validatorVersion"],
    "两条事实都在": all(fragment in authorized["text"] for fragment in fact_texts),
    "姓名保留": all(name in authorized["text"] for _, name, _ in units),
    "句界未变": authorized["text"].count("。") == plain.count("。"),
    "连接操作可回退": (negatives["no-relation"]["text"] == plain
                     and negatives["rejected"]["text"] == plain
                     and negatives["reversed"]["text"] == plain
                     and negatives["not-adjacent"]["text"] == spread_text),
    "回退原因": {key: [f["reason"] for f in out["fallbacks"]]
                 for key, out in negatives.items()},
}
report = {"editor": VERSION, "validator": VALIDATOR,
          "plain": plain, "edited": authorized["text"],
          "ops": authorized["ops"], "checks": checks}
(ART / "chain-edit-result.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=1))
ok = checks["两条事实都在"] and checks["姓名保留"] and checks["句界未变"] \
    and checks["连接操作可回退"] and authorized["text"] != plain
print("ACCEPT", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)

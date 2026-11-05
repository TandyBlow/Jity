"""把浏览器真实链条里的两条变化做成 N4 单事实单元（不改事实序列化）。"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fact_contract as FC

CHAIN = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])
payload = json.loads(CHAIN.read_text(encoding="utf-8"))
NAMES = {"person_a": "林川", "person_b": "周宁"}
HEADER = ("短句任务。\n地点=走廊\n地点可见=外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币\n"
          "场景=白天\n视角=林川；第三人称")
facts = []
for fact_id, point in (("f0", payload["pointA"]), ("f1", payload["pointB"])):
    entity = "person_a" if fact_id == "f0" else "person_b"
    text = next(r["text"] for r in payload["evidenceRefs"] if r["pointId"] == point["id"])
    facts.append({"factId": fact_id, "kind": "appearance_changed",
                  "name": NAMES[entity], "text": text, "pointId": point["id"]})
units = []
for fact in facts:
    line = FC.serialize_fact(fact)
    FC.check_line(fact["kind"], line)
    units.append({"unitId": f"chain:{fact['factId']}", "sourceId": "chain", "kind": fact["kind"],
                  "fact": fact, "input": FC.build_unit_input(HEADER, fact)})
for u in units:
    print("---", u["unitId"])
    print(u["input"])
OUT.write_text("\n".join(json.dumps(u, ensure_ascii=False) for u in units) + "\n", encoding="utf-8")
FC.check_units(units)
print("units", len(units))

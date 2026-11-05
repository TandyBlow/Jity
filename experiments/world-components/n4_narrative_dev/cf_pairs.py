"""Build paired counterfactual inputs: same scene, exactly one fact changed.

Families
  A subject     : the actor of an outcome is replaced by another character who
                  is already in the same source's facts        (both arms)
  B origin      : a move starts from a different place          (paragraph only)
  C completion  : the same scene with and without the outcome fact
                  (paragraph: drop the 结果 line; fact: that unit becomes 无变化)
  D destination : a move is reversed, scene block taken from the origin's own
                  unit so the input stays legal                (fact arm only)

Labels are written with the pairs and frozen before generation.
"""
import json, pathlib, re, sys
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "artifacts" / "world-components" / "n4-cf-pairs-r1.json"
PER_FAMILY = 8


def rows(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8")
            .splitlines() if l.strip()]


def field(text, key):
    m = re.search(rf"^{key}=(.*)$", text, re.M)
    return m.group(1) if m else None


def main():
    corpus = {r["id"]: r for r in rows(HERE / "corpus_v1.jsonl") + rows(HERE / "corpus.jsonl")
              + rows(HERE / "corpus_v2.jsonl")}
    para = {r["sourceId"]: r for r in rows(HERE / "formal_pairs.jsonl")}
    units = defaultdict(list)
    for r in rows(HERE / "verbalizer_pairs.jsonl"):
        units[r["sourceId"]].append(r)
    keep = {"formal-dev", "formal-holdout"}          # not used for training
    pool = [s for s, p in para.items() if p["split"] in keep]

    by_place = defaultdict(list)                     # 地点 -> a unit whose scene is there
    for r in rows(HERE / "verbalizer_pairs.jsonl"):
        by_place[field(r["input"], "地点")].append(r)

    pairs, used = [], set()

    def add(family, scope, sid, fid, orig, mod, expect):
        pid = f"{family}-{len([p for p in pairs if p['family'] == family]) + 1:02d}"
        pairs.append({"pairId": pid, "family": family, "scope": scope,
                      "sourceId": sid, "factId": fid,
                      "variants": [{"variant": "orig", "input": orig},
                                   {"variant": "mod", "input": mod}],
                      "expect": expect})

    # ---------------- A subject swap
    for sid in pool:
        if sum(1 for p in pairs if p["family"] == "A") >= PER_FAMILY:
            break
        c = corpus[sid]
        chars = sorted({f["name"] for f in c["facts"]
                        if str(f.get("entityId") or "").startswith("char_")})
        outs = [f for f in c["facts"] if f["kind"] == "outcome"]
        if not outs:
            continue
        f = outs[0]
        a = f["name"]
        # 优先用同源里已有的角色；没有就取世界里的另一个角色。两种情况都只改
        # 事实行，人物／场景块不动 —— 这一对唯一的差别就是主语。
        roster = ["沈砚", "顾行舟", "叶知微", "阿棠", "韩渡"]
        b = next((x for x in chars if x != a), None) or             next((x for x in roster if x != a), None)
        if not b:
            continue
        line = f'{f["factId"]}｜结果｜{a}｜'
        unit = next(u for u in units[sid] if u["factId"] == f["factId"])
        if line not in para[sid]["input"] or f"事实={a}｜结果｜" not in unit["input"]:
            continue
        add("A", "both", sid, f["factId"],
            para[sid]["input"], para[sid]["input"].replace(line, f'{f["factId"]}｜结果｜{b}｜'),
            {"subject": b, "oldSubject": a, "arm": "paragraph"})
        add("A", "both", sid, f["factId"],
            unit["input"], unit["input"].replace(f"事实={a}｜结果｜", f"事实={b}｜结果｜"),
            {"subject": b, "oldSubject": a, "arm": "fact"})
        used.add(sid)

    # ---------------- B origin change (paragraph only)
    places = [p for p in by_place if p]
    for sid in pool:
        if sum(1 for p in pairs if p["family"] == "B") >= PER_FAMILY:
            break
        c = corpus[sid]
        mv = next((f for f in c["facts"] if f["kind"] == "moved"), None)
        if not mv:
            continue
        a, b = mv.get("from"), mv.get("to")
        other = next((p for p in places if p not in (a, b)), None)
        old = f'{mv["factId"]}｜移动｜{mv["name"]}｜{a}→{b}'
        if not other or old not in para[sid]["input"]:
            continue
        add("B", "paragraph", sid, mv["factId"], para[sid]["input"],
            para[sid]["input"].replace(old, f'{mv["factId"]}｜移动｜{mv["name"]}｜{other}→{b}'),
            {"origin": other, "oldOrigin": a, "destination": b, "arm": "paragraph"})

    # ---------------- C completion
    for sid in pool:
        if sum(1 for p in pairs if p["family"] == "C") >= PER_FAMILY:
            break
        c = corpus[sid]
        f = next((x for x in c["facts"] if x["kind"] == "outcome"), None)
        if not f:
            continue
        p_in = para[sid]["input"]
        line = next((l for l in p_in.splitlines()
                     if l.startswith(f'{f["factId"]}｜结果｜')), None)
        if not line:
            continue
        without = p_in.replace(line + "\n", "")
        without = re.sub(rf'(\nG\d+｜[^\n]*?) {re.escape(f["factId"])}(?=[ ｜])',
                         r"\1", without)
        unit = next(u for u in units[sid] if u["factId"] == f["factId"])
        add("C", "both", sid, f["factId"], p_in, without,
            {"completion": False, "arm": "paragraph"})
        add("C", "both", sid, f["factId"], unit["input"],
            re.sub(r"事实=.*?\n", "事实=场景｜无变化\n", unit["input"], count=1),
            {"completion": False, "arm": "fact"})

    # ---------------- D destination swap (fact only)
    for sid in pool:
        if sum(1 for p in pairs if p["family"] == "D") >= PER_FAMILY:
            break
        c = corpus[sid]
        mv = next((f for f in c["facts"] if f["kind"] == "moved"
                   and f.get("from") in by_place and f.get("to") in by_place), None)
        if not mv:
            continue
        a, b, who = mv["from"], mv["to"], mv["name"]
        unit_b = next(u for u in units[sid] if u["factId"] == mv["factId"])
        src = by_place[a][0]                      # a unit whose scene is at the old origin
        scene = {k: field(src["input"], k) for k in ("地点", "地点可见", "场景", "视角")}
        if not all(scene.values()):
            continue
        direction = field(unit_b["input"], "方向") or "平"
        flipped = {"上": "下", "下": "上", "平": "平"}.get(direction, "平")
        mod = unit_b["input"]
        mod = re.sub(r"地点=.*", f'地点={scene["地点"]}', mod, count=1)
        mod = re.sub(r"地点可见=.*", f'地点可见={scene["地点可见"]}', mod, count=1)
        mod = re.sub(r"场景=.*", f'场景={scene["场景"]}', mod, count=1)
        mod = mod.replace(f"事实={who}｜移动｜{a}→{b}", f"事实={who}｜移动｜{b}→{a}")
        if "方向=" in mod:
            mod = re.sub(r"方向=.*", f"方向={flipped}", mod, count=1)
        add("D", "fact", sid, mv["factId"], unit_b["input"], mod,
            {"origin": b, "destination": a, "arm": "fact"})

    rec = {"purpose": "paired counterfactual inputs, one fact changed",
           "sourcesAllowed": sorted(keep), "families": {},
           "pairs": pairs}
    for fam in ("A", "B", "C", "D"):
        rec["families"][fam] = sum(1 for p in pairs if p["family"] == fam)
    OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(rec["families"], "total pairs", len(pairs))
    for p in pairs:
        assert p["variants"][0]["input"] != p["variants"][1]["input"], p["pairId"]
    print("->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

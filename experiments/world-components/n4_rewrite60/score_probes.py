# 给判据打分：人工参考答案 + 语义核对样本
#
# 输出三样东西：
#   1. 人工参考答案 140 条落在 fail / review / pass 各多少（review 不是通过）
#   2. 15 条语义样本：每条应有判决 vs 实际判决，逐条列出不符
#   3. 结论：判据能不能用。不能用的定义是——
#        · 参考答案里出现 fail（把正确写法判成错）
#        · 该失败的样本被判 pass（抓不到真错）
#        · 该通过的样本没判 pass（误伤正确写法）
# 退出码非 0 表示不能冻结。
import json, pathlib, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import checker as C

CORPUS = HERE / "corpus140.jsonl"
PROBES = HERE / "semantic_probes.jsonl"
REPORT = HERE.parents[2] / "artifacts" / "world-components" / "n4-eval-credibility-r1.json"

CFG = C.DEFAULT_CFG


def main() -> int:
    rows = {json.loads(l)["id"]: json.loads(l)
            for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()}
    probes = [json.loads(l) for l in
              PROBES.read_text(encoding="utf-8").splitlines() if l.strip()]

    # ---------- 1. 人工参考答案
    ref = {"fail": [], "review": [], "pass": []}
    data_errors = []
    for r in rows.values():
        world = C.world_for(r)
        errs = C.world_ref_errors(r, world)
        if errs:
            data_errors.append({"id": r["id"], "errors": errs[:3]})
            continue
        res = C.check_row(r, world, CFG)
        ref[res["verdict"]].append(res)
    print(f"人工参考答案 {len(rows) - len(data_errors)} 条可判："
          f"pass {len(ref['pass'])} / review {len(ref['review'])} / "
          f"fail {len(ref['fail'])}")
    if data_errors:
        print(f"  数据错 {len(data_errors)} 条（实体表缺条目，不计入）："
              f"{[d['id'] for d in data_errors]}")
    notes = {}
    for res in ref["pass"]:
        for x in res.get("notes", []):
            notes[x["code"]] = notes.get(x["code"], 0) + 1
    if notes:
        print("   （通过里的提示，不计入结论：" +
              "，".join(f"{k} {v}" for k, v in sorted(notes.items(),
                                                     key=lambda kv: -kv[1])) + "）")
    reasons = {}
    for res in ref["review"]:
        for x in res["review"]:
            reasons[x["code"]] = reasons.get(x["code"], 0) + 1
    for code, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"   复核 {code}: {n}")
    for res in ref["fail"][:6]:
        print("   ✗ 误伤", res["id"],
              [(v["code"], v.get("detail")) for v in res["violations"]][:2],
              [(w["kind"], w.get("why")) for w in res["unexpressed"]
               if w.get("mandatory")][:2])

    # ---------- 2. 语义样本
    print("\n语义核对样本：")
    rows_out, bad = [], 0
    for p in probes:
        row = dict(rows[p["baseId"]], target=p["text"])
        res = C.check_row(row, C.world_for(row), CFG)
        got = res["verdict"]
        ok = (got == p["expect"])
        # 该失败的被判成 review 时：没放行，但没抓住，单独标出来
        soft = (p["expect"] == "fail" and got == "review")
        bad += (not ok) and (not soft)
        if not ok:
            bad += 0
        rows_out.append({"id": p["id"], "category": p["category"],
                         "expect": p["expect"], "got": got,
                         "judged": "hit" if ok else ("soft-miss" if soft else "miss"),
                         "codes": [v["code"] for v in res["violations"]]
                                  + [x["code"] for x in res["review"]],
                         "why": p["why"]})
        flag = "✓" if ok else ("△" if soft else "✗")
        print(f"   {flag} {p['id']} {p['category']:<24} 应 {p['expect']:<6}"
              f" 实 {got:<6} {rows_out[-1]['codes']}")

    hit = sum(1 for x in rows_out if x["judged"] == "hit")
    soft = sum(1 for x in rows_out if x["judged"] == "soft-miss")
    print(f"   命中 {hit}/{len(rows_out)}，软漏（只判到复核）{soft}，"
          f"硬漏 {len(rows_out) - hit - soft}")

    # ---------- 3. 结论
    blocking = []
    if ref["fail"]:
        blocking.append(f"参考答案有 {len(ref['fail'])} 条被判失败")
    hard = [x for x in rows_out if x["judged"] == "miss"]
    if hard:
        blocking.append("语义样本有 %d 条判错：%s"
                        % (len(hard), ", ".join(x["id"] for x in hard)))
    print()
    if blocking:
        print("判据不可冻结：")
        for b in blocking:
            print("  -", b)
    else:
        print("判据可用于自动闸门：参考答案无误伤，样本全部落在预期区间。")
        if ref["review"]:
            print(f"  注意：{len(ref['review'])} 条参考答案仍需人工复核，"
                  f"这部分不是通过。")

    # ---------- 4. 结构篡改探针（与 checker.py 同一组用例）
    base = list(rows.values())[0]
    world = C.world_for(base)
    tamper_cases = C.tamper(base["target"], base["facts"], world, base["input"])
    tamper_out = []
    for label, text in tamper_cases:
        res = C.check_row(dict(base, target=text), world, CFG)
        tamper_out.append({"case": label, "verdict": res["verdict"],
                           "caught": res["verdict"] != "pass"})
    tamper_caught = sum(x["caught"] for x in tamper_out)
    print()
    print(f"结构篡改探针 {tamper_caught}/{len(tamper_out)} 被抓")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "checkerSha256": __import__("hashlib").sha256(
            (HERE / "checker.py").read_bytes()).hexdigest(),
        "reference": {"rows": len(rows),
                      "pass": len(ref["pass"]),
                      "review": len(ref["review"]),
                      "fail": len(ref["fail"]),
                      "reviewReasons": reasons,
                      "reviewIds": [r["id"] for r in ref["review"]]},
        "probes": rows_out,
        "probesSummary": {"total": len(rows_out), "hit": hit,
                          "softMiss": soft, "miss": len(rows_out) - hit - soft},
        "tamper": {"cases": len(tamper_out), "caught": tamper_caught,
                   "detail": tamper_out},
        "dataErrors": data_errors,
        "blocking": blocking,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"报告 → {REPORT}")
    if "--freeze" in sys.argv and not blocking and tamper_caught == len(tamper_out):
        rec = {
            "checker": "checker.py v7",
            "sha256": __import__("hashlib").sha256(
                (HERE / "checker.py").read_bytes()).hexdigest(),
            "world": "world.json", "thresholds": CFG,
            "dataErrors": data_errors,
            "reference": {"rows": len(rows) - len(data_errors), "pass": len(ref["pass"]),
                          "review": len(ref["review"]), "fail": len(ref["fail"]),
                          "reviewIds": [r["id"] for r in ref["review"]]},
            "probes": {"file": "semantic_probes.jsonl",
                       "cases": len(rows_out), "hit": hit,
                       "categories": sorted({x["category"] for x in rows_out})},
            "tamper": {"cases": len(tamper_out), "caught": tamper_caught},
            "whyV5": "v4 的 140/140 只证明参考稿在这批复用词上没被判错，"
                     "不证明事实核对可靠：换主体、写成否定、册外新人物都直接"
                     "放过，还把‘不同物体一冷一热’和‘远近两盏灯’判成矛盾。"
                     "v5 把‘判不了’单独列成复核，并用带答案的样本计分。",
            "whyV7": "隔离集首轮盲测暴露三处结构错：① 方向正则的第二段是惰性的，只吃到"
                     "一个字，永远比不中目的地；② 判断“谁做的”时只在承载动作的那一小句"
                     "里找别人，主语在相邻小句就漏；③ 两个人同处一句时，句级“出现过主体”"
                     "被当成已经绑定。v7 改用整句范围找别人，并要求承载动作的小句主语不能"
                     "是另一个角色（actor-mismatch）。代价：参考稿待复核 13→16。",
            "whyV6": "v5 仍有五处被用户复跑抓到：局部换人不报（别处点过名就降级）、"
                     "出发地互换不报、册外人物只点名一次不报、远近两盏灯判矛盾、"
                     "别人被否定算成主体结果被否定。v6 逐条改：小句点名别人一律复核、"
                     "出发地串位复核、单次人名按姓氏+句首+动词、同一物体只认字面相同、"
                     "否定要落在主体所在小句。",
            "knownBlindSpots": [
                "谁做的这件事：小句主语不是事实主体时只进复核，不判违规",
                "结果只做了一半：词面覆盖对不上才进复核，可能漏",
                "文笔、心理是否可信、比喻是否误导：不查",
            ],
            "registeredBeforeAnyModelRun": True,
        }
        (HERE / "checker-v7-freeze.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        print("已冻结：checker-v7-freeze.json")
    if tamper_caught != len(tamper_out):
        blocking.append(f"结构篡改有 {len(tamper_out) - tamper_caught} 条漏检")
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())

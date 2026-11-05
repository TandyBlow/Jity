# 跨行回归集：每条参考稿做同样的几种改动，统计三类错误
#
# 和 semantic_probes.jsonl 的区别：那些样本是从 r01/r02 手工改的，规则也是
# 对着它们调的。这里对 140 条全部套同样的改动，一次生成、一次冻结，用来量
# 三个比率：
#   错误放行 = 该改坏的改坏了，判据却给了 pass
#   正确误拒 = 写法正确，判据判了 fail
#   复核率   = 判不了、需要人看的比例
#
# 用法：
#   python -X utf8 regression.py            # 用已冻结的 regression_set.jsonl 打分
#   python -X utf8 regression.py --rebuild  # 重新生成（旧集只留档，不静默覆盖）
import json, pathlib, sys
from collections import Counter

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import checker as C

CORPUS = HERE / "corpus140.jsonl"
SET = HERE / "regression_set.jsonl"
REPORT = HERE.parents[2] / "artifacts" / "world-components" / "n4-judge-regression-r1.json"

OUTSIDER = "任云川"
ROSTER = ["沈砚", "顾行舟", "叶知微", "阿棠", "韩渡"]


def mutations(row, world):
    """一行参考稿 → [(family, text, expect)]。expect 只有 pass / not-pass。"""
    t = row["target"]
    out = [("ref", t, "pass")]

    chars_in_input = [c for c in ROSTER if C.norm(c) in C.norm(row["input"])]
    chars_in_text = [c for c in chars_in_input if C.norm(c) in C.norm(t)]
    if len(chars_in_text) >= 2:
        victim = next((c for c in chars_in_text
                       if any(f.get("name") == c and f.get("kind") in
                              ("outcome", "appearance_changed", "moved")
                              for f in row["facts"])), None)
        if victim:
            other = next(c for c in chars_in_text if c != victim)
            out.append(("swap-actor", t.replace(victim, other), "not-pass"))

    out.append(("outsider-once", t + OUTSIDER + "站在远处看了一会儿，没有出声。",
                "not-pass"))
    out.append(("correct-two-lamps", t + "近处的灯灭了，远处的灯还亮着。", "pass"))
    out.append(("correct-cold-hot", t + "手背冰凉，铁皮发烫。", "pass"))

    key = next((f.get("resultText") or "" for f in row["facts"]
                if f.get("kind") in ("outcome", "task_achieved")), "")
    if key:
        sents = [x for x in C.re.split(r"(?<=[。；！？])", t) if x.strip()]
        if len(sents) >= 3:
            worst = max(sents, key=lambda s: C.coverage(key, s))
            kept = "".join(s for s in sents if s is not worst)
            # 只有“删完确实对不上了”才算该判 not-pass 的样本；删完仍覆盖
            # 大半的，剩下的话本身就讲清了结果，标 pass 才是对的。
            if C.coverage(key, worst) >= 0.3 and C.coverage(key, kept) < 0.4:
                out.append(("drop-result-sentence", kept, "not-pass"))
    return out


def build():
    world = C.load_world_names()
    rows = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    out = []
    for r in rows:
        for family, text, expect in mutations(r, world):
            assert text != r["target"] or family == "ref", (r["id"], family)
            out.append({"id": f"{r['id']}::{family}", "baseId": r["id"],
                        "family": family, "expect": expect, "text": text})
    SET.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out)
                   + "\n", encoding="utf-8")
    print(f"生成 {len(out)} 条 → {SET.name}")
    print(Counter(x["family"] for x in out))


def score():
    rows = {json.loads(l)["id"]: json.loads(l)
            for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()}
    cases = [json.loads(l) for l in SET.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    stat, detail, data_errors = {}, [], []
    for c in cases:
        base = rows[c["baseId"]]
        world = C.world_for(base)
        errs = C.world_ref_errors(base, world)
        if errs:
            data_errors.append({"id": c["id"], "errors": errs[:3]})
            continue
        res = C.check_row(dict(base, target=c["text"]), world, C.DEFAULT_CFG)
        got = res["verdict"]
        if c["expect"] == "pass":
            kind = {"pass": "ok", "review": "review", "fail": "false-reject"}[got]
        else:
            kind = {"fail": "ok", "review": "review", "pass": "wrong-pass"}[got]
        stat.setdefault(c["family"], Counter())[kind] += 1
        if kind in ("wrong-pass", "false-reject"):
            detail.append({"id": c["id"], "family": c["family"],
                           "expect": c["expect"], "got": got,
                           "codes": [v["code"] for v in res["violations"]]
                                    + [x["code"] for x in res["review"]]})

    def pct(a, b):
        return f"{a}/{b} = {a / b:.1%}" if b else "—"

    print()
    print(f"回归集 {len(cases)} 条")
    print(f"{'family':<24}{'条数':>5}{'判对':>6}{'复核':>6}{'错放':>6}{'误拒':>6}")
    for fam, s in stat.items():
        print(f"{fam:<24}{sum(s.values()):>5}{s['ok']:>6}{s['review']:>6}"
              f"{s['wrong-pass']:>6}{s['false-reject']:>6}")

    err = {k: v for k, v in stat.items() if k != "ref"
           and k not in ("correct-two-lamps", "correct-cold-hot")}
    ok = {k: v for k, v in stat.items()
          if k == "ref" or k in ("correct-two-lamps", "correct-cold-hot")}
    n_err = sum(sum(v.values()) for v in err.values())
    n_ok = sum(sum(v.values()) for v in ok.values())
    wrong = sum(v["wrong-pass"] for v in err.values())
    frej = sum(v["false-reject"] for v in ok.values())
    rev_ok = sum(v["review"] for v in ok.values())
    rev_all = sum(v["review"] for v in stat.values())
    n_all = sum(sum(v.values()) for v in stat.values())

    print()
    print("按分母分的口径（错放率只除以错误样本，不被正确样本稀释）：")
    print(f"  错误样本被放行      {pct(wrong, n_err)}")
    for fam in ("swap-actor", "outsider-once", "drop-result-sentence"):
        if fam in err:
            print(f"    {fam:<20} {pct(err[fam]['wrong-pass'], sum(err[fam].values()))}")
    print(f"  正确样本被判失败    {pct(frej, n_ok)}")
    print(f"  正确样本进入复核    {pct(rev_ok, n_ok)}")
    print(f"  全部样本复核率      {pct(rev_all, n_all)}")
    if data_errors:
        print(f"  数据错（世界实体表缺条目，未计入上面任何比率）：{len(data_errors)}")

    for d in detail[:8]:
        print("   ✗", d["id"], d["expect"], "→", d["got"], d["codes"])

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "cases": n_all,
        "errorSamples": n_err, "correctSamples": n_ok,
        "wrongPass": {"count": wrong, "denominator": n_err,
                      "rate": round(wrong / n_err, 4) if n_err else None},
        "wrongPassByFamily": {
            fam: {"count": v["wrong-pass"], "denominator": sum(v.values()),
                  "rate": round(v["wrong-pass"] / sum(v.values()), 4)}
            for fam, v in err.items()},
        "falseReject": {"count": frej, "denominator": n_ok,
                        "rate": round(frej / n_ok, 4) if n_ok else None},
        "reviewOnCorrect": {"count": rev_ok, "denominator": n_ok,
                            "rate": round(rev_ok / n_ok, 4) if n_ok else None},
        "reviewAll": {"count": rev_all, "denominator": n_all,
                      "rate": round(rev_all / n_all, 4) if n_all else None},
        "byFamily": {k: dict(v) for k, v in stat.items()},
        "dataErrors": data_errors,
        "failures": detail,
        "checkerSha256": __import__("hashlib").sha256(
            (HERE / "checker.py").read_bytes()).hexdigest(),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"报告 → {REPORT}")
    return 1 if (wrong or frej or data_errors) else 0


if __name__ == "__main__":
    if "--rebuild" in sys.argv or not SET.exists():
        if SET.exists():
            SET.rename(SET.with_suffix(".prev.jsonl"))
        build()
    raise SystemExit(score())

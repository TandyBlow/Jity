# 隔离集：格式、校验、一次性运行
#
# 隔离集和 regression_set.jsonl 的区别只有一条：**标签是人写的**，不是从
# 检查器的覆盖率推出来的。所以每条必须自带 facts / input / text，fail 的
# 还要写清错了哪条事实（facts 里的 factId）。
#
# 用法：
#   python -X utf8 isolated.py --validate  <set.jsonl>
#   python -X utf8 isolated.py --run       <set.jsonl>     # 跑过就不能再跑
#   python -X utf8 isolated.py --run fixtures/isolated-smoke.jsonl --smoke
import hashlib, json, pathlib, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import checker as C

GROUPS = {"same-world", "new-people-places", "new-world"}
ERROR_TYPES = {"subject-swap", "direction", "negation", "omission",
               "added-entity", "added-number", "contradiction", "other"}


def load(path):
    return [json.loads(l) for l in pathlib.Path(path).read_text(encoding="utf-8")
            .splitlines() if l.strip()]


def validate(cases, strict_groups=True):
    errs = []
    seen = set()
    for c in cases:
        cid = c.get("id", "?")
        if cid in seen:
            errs.append(f"{cid}: id 重复")
        seen.add(cid)
        for k in ("id", "group", "text", "input", "facts", "label"):
            if not c.get(k):
                errs.append(f"{cid}: 缺 {k}")
        if c.get("group") not in GROUPS:
            errs.append(f"{cid}: group 必须是 {sorted(GROUPS)}")
        if c.get("labelSource") != "human":
            errs.append(f"{cid}: labelSource 必须是 human；"
                        f"覆盖率算出来的标签不能当隔离集")
        if c.get("label") not in ("pass", "fail"):
            errs.append(f"{cid}: label 只能是 pass / fail")
        if c.get("label") == "fail":
            if not c.get("wrongFacts"):
                errs.append(f"{cid}: fail 样本必须写 wrongFacts")
            if not c.get("errorTypes"):
                errs.append(f"{cid}: fail 样本必须写 errorTypes")
            ids = {f.get("factId") for f in c.get("facts") or []}
            for fid in c.get("wrongFacts") or []:
                if fid not in ids:
                    errs.append(f"{cid}: wrongFacts 里的 {fid} 不在 facts 中")
            for t in c.get("errorTypes") or []:
                if t not in ERROR_TYPES:
                    errs.append(f"{cid}: errorTypes 里的 {t} 不认识")
        if c.get("label") == "pass" and c.get("errorTypes"):
            errs.append(f"{cid}: pass 样本不该有 errorTypes")
        w = C.world_for(c, HERE)
        for e in C.world_ref_errors(c, w):
            errs.append(f"{cid}: 世界实体表缺条目 → {e}")
    by_id = {c.get("id"): c for c in cases}
    for c in cases:
        pid = c.get("pairId")
        if not pid:
            continue
        o = by_id.get(pid)
        if not o:
            errs.append(f"{c.get('id')}: pairId {pid} 不存在")
            continue
        if o.get("label") == c.get("label"):
            errs.append(f"{c.get('id')}: pairId {pid} 标签相同，配对要一正一错")
        if o.get("group") != c.get("group"):
            errs.append(f"{c.get('id')}: pairId {pid} 不在同一 group")
        if (o.get("world") or "") != (c.get("world") or ""):
            errs.append(f"{c.get('id')}: pairId {pid} 用了不同世界")
    if strict_groups:
        for g in GROUPS:
            sub = [c for c in cases if c.get("group") == g]
            if not sub:
                errs.append(f"group {g} 没有样本")
                continue
            if not any(c["label"] == "pass" for c in sub):
                errs.append(f"group {g} 没有正确样本")
            if not any(c["label"] == "fail" for c in sub):
                errs.append(f"group {g} 没有错误样本")
            if not any(c.get("pairId") for c in sub):
                errs.append(f"group {g} 没有成对样本（pairId）")
    return errs


def run(path, smoke=False):
    path = pathlib.Path(path)
    cases = load(path)
    errs = validate(cases, strict_groups=not smoke)
    if errs:
        print(f"校验不通过（{len(errs)} 项），不跑：")
        for e in errs[:20]:
            print("  -", e)
        return 2

    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    ck = hashlib.sha256((HERE / "checker.py").read_bytes()).hexdigest()
    labels_file = path.parent / (path.stem + ".labels.json")
    if not smoke:
        if not labels_file.exists():
            print("没有冻结标签，先跑 --freeze-labels。跑过再定标签就不算盲测。")
            return 4
        frozen = json.loads(labels_file.read_text(encoding="utf-8"))
        if frozen["setSha256"] != sha:
            print("样本文件在冻结标签之后改过，标签不再对应当前内容，拒绝运行。")
            return 4
        run_kind = "blind" if frozen["checkerSha256"] == ck else "post-tuning"
        if run_kind == "post-tuning":
            print("注意：判据在冻结标签之后改过。这次结果只能当回归复跑，"
                  "不能再叫未见测试集。")
    else:
        run_kind = "smoke"

    lock = path.parent / (path.stem + ".runs.json")
    history = []
    if lock.exists():
        history = json.loads(lock.read_text(encoding="utf-8")).get("runs", [])

    stat, detail = {}, []
    for c in cases:
        world = C.world_for(c, HERE)
        res = C.check_row(dict(c, target=c["text"]), world, C.DEFAULT_CFG)
        got = res["verdict"]
        if c["label"] == "fail":
            kind = {"fail": "caught", "review": "escalated", "pass": "let-through"}[got]
        else:
            kind = {"pass": "ok", "review": "review", "fail": "false-reject"}[got]
        s = stat.setdefault(c["group"], {"pass": 0, "fail": 0, "ok": 0, "review": 0,
                                         "false-reject": 0, "caught": 0,
                                         "escalated": 0, "let-through": 0})
        s["pass" if c["label"] == "pass" else "fail"] += 1
        s[kind] += 1
        if kind in ("let-through", "false-reject"):
            detail.append({"id": c["id"], "label": c["label"], "got": got,
                           "codes": [v["code"] for v in res["violations"]]
                                    + [x["code"] for x in res["review"]],
                           "errorTypes": c.get("errorTypes")})

    def pct(a, b):
        return f"{a}/{b} = {a / b:.0%}" if b else "—"

    print(f"\n隔离集 {len(cases)} 条（{path.name}）")
    print(f"{'group':<20}{'错误条':>7}{'放行':>6}{'拦住':>6}{'复核':>6}"
          f"{'正确条':>7}{'误拒':>6}{'复核':>6}")
    for g, s in stat.items():
        print(f"{g:<20}{s['fail']:>7}{s['let-through']:>6}{s['caught']:>6}"
              f"{s['escalated']:>6}{s['pass']:>7}{s['false-reject']:>6}"
              f"{s['review']:>6}")

    n_err = sum(s["fail"] for s in stat.values())
    n_ok = sum(s["pass"] for s in stat.values())
    lt = sum(s["let-through"] for s in stat.values())
    fr = sum(s["false-reject"] for s in stat.values())
    rv = sum(s["review"] for s in stat.values())
    esc = sum(s["escalated"] for s in stat.values())
    print(f"\n错误样本被放行  {pct(lt, n_err)}")
    print(f"错误样本进复核  {pct(esc, n_err)}")
    print(f"正确样本被判失败 {pct(fr, n_ok)}")
    print(f"正确样本进复核  {pct(rv, n_ok)}")
    for d in detail[:10]:
        print("   ✗", d["id"], d["label"], "→", d["got"], d["codes"])

    if not smoke:
        history.append({
            "kind": run_kind, "setSha256": sha, "checkerSha256": ck,
            "at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "cases": len(cases), "letThrough": lt, "escalated": esc,
            "falseReject": fr, "review": rv,
        })
        lock.write_text(json.dumps({"runs": history}, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        print(f"已记入运行历史：{lock.name}（第 {len(history)} 次，{run_kind}）")
    return 0 if not (lt or fr) else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        raise SystemExit(2)
    if a[0] == "--validate":
        e = validate(load(a[1]), strict_groups="--smoke" not in a)
        print("校验通过" if not e else f"{len(e)} 项问题")
        for x in e[:20]:
            print("  -", x)
        raise SystemExit(0 if not e else 2)
    if a[0] == "--freeze-labels":
        path = pathlib.Path(a[1])
        cases = load(path)
        e = validate(cases, strict_groups=True)
        if e:
            print(f"校验不通过（{len(e)} 项），不冻结：")
            for x in e[:20]:
                print("  -", x)
            raise SystemExit(2)
        frozen = {
            "setSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "checkerSha256": hashlib.sha256(
                (HERE / "checker.py").read_bytes()).hexdigest(),
            "at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "cases": len(cases),
            "labels": {c["id"]: c["label"] for c in cases},
            "note": "标签在跑判据之前写定；此文件存在且哈希一致才允许 --run。",
        }
        out = path.parent / (path.stem + ".labels.json")
        out.write_text(json.dumps(frozen, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已冻结 {len(cases)} 条标签 → {out.name}（判据 {frozen['checkerSha256'][:12]}）")
        raise SystemExit(0)
    if a[0] == "--run":
        raise SystemExit(run(a[1], smoke="--smoke" in a))
    print(__doc__)
    raise SystemExit(2)

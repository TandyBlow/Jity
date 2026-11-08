"""C8 exclusion-rule checker and self-test.

Two uses:

1. `--selftest` (default): prove the exclusion rules actually reject the known
   material. The ten frozen three-arm items are parsed out of
   `narration-eval-samples.ts`, screened like any candidate, and must all come
   back rejected. Two renamed/paraphrased derivatives are constructed with fresh
   vocabulary and must be rejected by the signature rule alone (their text does
   not exist in the exclusion corpus). One synthetic fresh scenario must pass.

2. candidate screening: `--candidates <file.json>` reads a JSON list of
   candidate scenarios and prints/records a verdict per item. A candidate is
   {id, characters[], locations[], tasks[], texts[], facts[{kind, actor}],
   time:{amount, unit}}.

Rules (see sources/exclusion-scope.json):
  R1 substring  candidate text (>=4 CJK chars) vs every exclusion string,
                bidirectional containment; parentheses-stripped variants of the
                source string are also tested.
  R2 vocabulary any candidate character/location/task/term found in the used
                vocabulary union -> hit (target is zero).
  R3 signature  (sorted fact kinds, distinct actors, time amount+unit) equal to
                one of the ten three-arm signatures -> hit.

Verdict: `rejected` if any hit; `candidate` if none. `candidate` only means "not
caught by these rules" - it is not an acceptance. Human review decides.

Usage:
  python artifacts/world-components/fresh-eval/tools/exclusion_selftest.py
  python artifacts/world-components/fresh-eval/tools/exclusion_selftest.py --candidates x.json
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent
REPO = OUT.parents[2]
CJK = re.compile(r"[\u4e00-\u9fff]")
NOTE = re.compile(r"（[^）]*）")
TS_STR = re.compile(r"""'([^'\\\n]{2,})'|"([^"\\\n]{2,})"|`([^`\\\n]{2,})`""")


def load_sources():
    corpus = {}
    path = OUT / "sources/exclusion-corpus.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        corpus[row["text"]] = row["sources"]
    vocab = json.loads((OUT / "sources/vocab-used.json").read_text(encoding="utf-8"))
    vocab_union = set()
    for terms in vocab["buckets"].values():
        vocab_union.update(terms)
    scope = json.loads((OUT / "sources/exclusion-scope.json").read_text(encoding="utf-8"))
    return corpus, vocab_union, scope


def norm_variants(text: str) -> list[str]:
    """Source string plus its parentheses-stripped core (nv-cont-1 lesson)."""
    out = [text]
    if NOTE.search(text):
        core = NOTE.sub("", text).strip()
        if len(CJK.findall(core)) >= 4:
            out.append(core)
    return out


def screen(cand: dict, corpus: dict, vocab: set[str], signatures: dict) -> dict:
    reasons = []
    texts = [t for t in cand.get("texts", []) if len(CJK.findall(t)) >= 4]
    hits = []
    for t in texts:
        for src, sources in corpus.items():
            # A note may interrupt the substring. Test stripped variants even
            # when the original string has no containment match.
            if any(t in variant or variant in t for variant in norm_variants(src)):
                hits.append({"candidateText": t, "excluded": src,
                             "sources": sources})
                break
    if hits:
        reasons.append({"rule": "R1-substring", "hits": hits[:5],
                        "hitCount": len(hits)})
    terms = []
    for key in ("characters", "locations", "tasks", "items", "terms"):
        for v in cand.get(key, []) or []:
            if v in vocab:
                terms.append({"term": v, "field": key})
    if terms:
        reasons.append({"rule": "R2-vocabulary", "hits": terms})
    kinds = sorted(f["kind"] for f in cand.get("facts", []) or [])
    actors = {f.get("actor") for f in cand.get("facts", []) or [] if f.get("actor")}
    time = cand.get("time") or {}
    sig = f"{'+'.join(kinds) or 'none'}|{len(actors)}|{time.get('amount')}{time.get('unit')}"
    if sig in signatures:
        reasons.append({"rule": "R3-signature", "signature": sig,
                        "matches": signatures[sig]})
    return {"id": cand.get("id"), "verdict": "rejected" if reasons else "candidate",
            "signature": sig, "reasons": reasons}


def parse_three_arm(path: pathlib.Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    starts = [m.start() for m in re.finditer(r"id: 'nv-", text)]
    blocks = [text[s:(starts[i + 1] if i + 1 < len(starts) else len(text))]
              for i, s in enumerate(starts)]
    items = []
    for blk in blocks:
        sid = re.search(r"id: '([^']+)'", blk).group(1)
        kinds = re.findall(r"kind: '([a-z_]+)'", blk)
        actors = re.findall(r"actorId: '([^']+)'", blk)
        tm = re.search(r"time: \{ amount: (\d+), unit: '(\w+)' \}", blk)
        texts = []
        for m in re.finditer(r"\b(mechanical|reference|note):\s*'([^']*)'", blk):
            if m.group(1) != "note":
                texts.append(m.group(2))
        for arr in re.finditer(r"\bforbidden: \[([^\]]*)\]", blk):
            texts += [s for s in re.findall(r"'([^']*)'", arr.group(1))]
        items.append({"id": sid, "kinds": kinds, "actors": sorted(set(actors)),
                      "texts": texts,
                      "time": {"amount": int(tm.group(1)), "unit": tm.group(2)} if tm else {}})
    return items


def baseline_checks(items, rows, scope):
    expected_ids = {i["id"] for i in scope["threeArmItems"]}
    parsed_ids = [i["id"] for i in items]
    complete = (len(expected_ids) == 10 and len(parsed_ids) == 10
                and set(parsed_ids) == expected_ids
                and [r["id"] for r in rows] == parsed_ids)
    independent = len(rows) == 10 and all(
        {r["rule"] for r in row["reasons"]} >= {"R1-substring", "R3-signature"}
        for row in rows)
    return complete, independent


def main() -> int:
    corpus, vocab, scope = load_sources()
    signatures = {i["signature"]: i["id"] for i in scope["threeArmItems"]}
    head = git_head()

    args = sys.argv[1:]
    if "--candidates" in args:
        path = pathlib.Path(args[args.index("--candidates") + 1])
        cands = json.loads(path.read_text(encoding="utf-8"))
        rows = [screen(c, corpus, vocab, signatures) for c in cands]
        print(json.dumps({"head": head, "candidates": rows}, ensure_ascii=False, indent=1))
        return 0

    # ---- self-test -------------------------------------------------------
    samples_ts = REPO / "frontend/src/lib/world-engine/runtime/narration-eval-samples.ts"
    items = parse_three_arm(samples_ts)
    raw_check = []
    for it in items:
        acts = it["actors"] or [None]
        facts = [{"kind": k, "actor": acts[i] if i < len(acts) else acts[0]}
                 for i, k in enumerate(it["kinds"])]
        cand = {"id": it["id"], "texts": it["texts"], "facts": facts,
                "time": it["time"]}
        raw_check.append(screen(cand, corpus, vocab, signatures))

    # renamed derivative of nv-move-1: new names, new places, same 2-minute move
    renamed = {"id": "deriv-renamed-move-2min",
               "characters": ["寒枝"], "locations": ["南堤", "旧坊"],
               "texts": ["寒枝从南堤来到旧坊。"],
               "facts": [{"kind": "moved", "actor": "hanzhi"}],
               "time": {"amount": 2, "unit": "minute"}}
    # paraphrase of nv-empty-1: empty facts, 5 minutes, fresh vocabulary
    paraphrase = {"id": "deriv-paraphrase-empty-5min",
                  "texts": ["檐下只剩风声，五分钟就这么过去，什么都没有改变。"],
                  "facts": [], "time": {"amount": 5, "unit": "minute"}}
    # synthetic fresh scenario: 3 actors, 2 locations, one task, unseen signature
    fresh = {"id": "synthetic-fresh-ok",
             "characters": ["寒枝", "沙行者", "砚台客"],
             "locations": ["南堤", "旧坊"],
             "tasks": ["替沙行者找回落下的铜牌"],
             "texts": ["寒枝在南堤等了一会儿，沙行者从旧坊过来，两人一起去找砚台客落下的铜牌。"],
             "facts": [{"kind": "moved", "actor": "a"},
                       {"kind": "task_achieved", "actor": "b"},
                       {"kind": "sanity_changed", "actor": "c"}],
             "time": {"amount": 7, "unit": "minute"}}
    extra = [screen(c, corpus, vocab, signatures) for c in (renamed, paraphrase, fresh)]

    blocked = sum(1 for r in raw_check if r["verdict"] == "rejected")
    deriv_ok = all(r["verdict"] == "rejected" for r in extra[:2])
    fresh_ok = extra[2]["verdict"] == "candidate"
    complete, independent_rules = baseline_checks(items, raw_check, scope)
    derivatives_signature_only = all(
        [r["rule"] for r in row["reasons"]] == ["R3-signature"] for row in extra[:2])
    note_probe = screen(
        {"texts": ["寒枝从南堤来到旧坊"]},
        {"寒枝（测试注记）从南堤来到旧坊": ["regression-probe"]}, set(), {})
    note_ok = any(r["rule"] == "R1-substring" for r in note_probe["reasons"])
    ok = (complete and blocked == 10 and independent_rules and deriv_ok
          and derivatives_signature_only and fresh_ok and note_ok)

    report = {
        "worktreeHead": head,
        "inputs": {
            "checkerSha256": sha256(pathlib.Path(__file__)),
            "scopeSha256": sha256(OUT / "sources/exclusion-scope.json"),
            "exclusionCorpus": {"file": "sources/exclusion-corpus.jsonl",
                                "sha256": sha256(OUT / "sources/exclusion-corpus.jsonl"),
                                "strings": len(corpus)},
            "vocabulary": {"file": "sources/vocab-used.json",
                           "sha256": sha256(OUT / "sources/vocab-used.json"),
                           "terms": len(vocab)},
            "threeArmItems": {"file": str(samples_ts.relative_to(REPO)).replace("\\", "/"),
                              "sha256": sha256(samples_ts), "parsed": len(items)},
        },
        "result": {
            "exactTenItemsParsed": complete,
            "eachOldItemBlockedByR1AndR3": independent_rules,
            "derivativesBlockedByR3Only": derivatives_signature_only,
            "noteStrippingRegression": note_ok,
            "threeArmRejected": f"{blocked}/{len(items)}",
            "renamedDerivativeRejected": extra[0]["verdict"],
            "paraphraseDerivativeRejected": extra[1]["verdict"],
            "syntheticFreshVerdict": extra[2]["verdict"],
            "pass": ok,
        },
        "threeArm": raw_check,
        "derivatives": extra,
        "limits": [
            "只证明这十条旧题与两条构造派生被规则拦下；不证明排除集完整",
            "R1 只做子串双向包含；改写后不共享子串的派生不会被 R1 抓到",
            "R3 只比事实形状；换一种形状的语义派生仍需人工核验",
            "新场景判定为 candidate 只表示未被这三条规则命中，不构成验收",
        ],
    }
    (OUT / "selftest-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = ["# 排除规则自检（自动生成，勿手改）", "",
             f"工作树 HEAD：`{head}`；脚本 `tools/exclusion_selftest.py`。", "",
             "## 输入", "",
             f"- 排除串：{len(corpus)} 条（`sources/exclusion-corpus.jsonl`，"
             f"sha256 `{report['inputs']['exclusionCorpus']['sha256'][:16]}…`）",
             f"- 词表并集：{len(vocab)} 项（`sources/vocab-used.json`）",
             f"- 三臂十题：从 `narration-eval-samples.ts` 现场解析 {len(items)} 条", "",
             "## 结果", "",
             "| 用例 | 期望 | 实测 | 命中规则 |", "|---|---|---|---|"]
    for r in raw_check:
        rules = ", ".join(x["rule"] for x in r["reasons"]) or "（无）"
        lines.append(f"| `{r['id']}` | rejected | {r['verdict']} | {rules} |")
    for label, r in (("改名派生（nv-move-1 换名同形）", extra[0]),
                     ("改写派生（nv-empty-1 空点 5 分钟）", extra[1]),
                     ("新场景（三条事实、7 分钟）", extra[2])):
        rules = ", ".join(x["rule"] for x in r["reasons"]) or "（无）"
        expected = "candidate" if r is extra[2] else "rejected"
        lines.append(f"| {label} (`{r['id']}`) | {expected} | {r['verdict']} | {rules} |")
    lines += ["", f"十题完整性：{complete}；每题 R1/R3 独立命中：{independent_rules}；"
              f"派生仅 R3 命中：{derivatives_signature_only}；注记剥离回归：{note_ok}。"]
    lines += ["", f"**自检结论：{'通过' if ok else '未通过'}**"
              f"（三臂 {blocked}/{len(items)} 被拦、两条派生均被拦、新场景未被误拦）。", "",
              "## 边界", ""]
    lines += [f"- {x}" for x in report["limits"]]
    (OUT / "selftest-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"head={head[:12]} corpus={len(corpus)} vocab={len(vocab)} items={len(items)} "
          f"blocked={blocked}/{len(items)} renamed={extra[0]['verdict']} "
          f"paraphrase={extra[1]['verdict']} fresh={extra[2]['verdict']} PASS={ok}")
    for r in raw_check:
        if r["verdict"] != "rejected":
            print("  MISSED", r["id"], r["signature"], r["reasons"])
    return 0 if ok else 1


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head() -> str:
    try:
        return subprocess.run(["git", "-c", f"safe.directory={REPO.as_posix()}",
                               "-C", str(REPO), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())

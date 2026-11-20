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
import importlib.util
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


_spec = importlib.util.spec_from_file_location("screening", HERE / "screening.py")
_screening = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_screening)
load_sources = _screening.load_sources
norm_variants = _screening.norm_variants
signature_of = _screening.signature_of
write_artifact = _screening.write_artifact


def screen(cand, corpus, vocab, signatures, mode="new-world"):
    return _screening.screen(cand, corpus, vocab, signatures, mode=mode)


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
    # signature -> ALL old item ids sharing it (a later id must not overwrite an
    # earlier one: nv-empty-1 and nv-cont-3 share `none|0|300s`)
    signatures = {sig: list(ids) for sig, ids in scope.get("signatureOwners", {}).items()}
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
    # unit-renamed derivative of nv-empty-1: 5 minutes written as 300 seconds
    unit_renamed = {"id": "deriv-unit-renamed-300s",
                    "texts": ["檐下的风声一直没有停，时间就这么过去了。"],
                    "facts": [], "time": {"amount": 300, "unit": "second"}}
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
    extra = [screen(c, corpus, vocab, signatures)
             for c in (renamed, paraphrase, unit_renamed, fresh)]

    # each old item's R3 hit must list that item itself
    r3_self = {}
    for row in raw_check:
        owners = [o for reason in row["reasons"] if reason["rule"] == "R3-signature"
                  for o in reason.get("matches", [])]
        r3_self[row["id"]] = row["id"] in owners
    collisions = {sig: ids for sig, ids in signatures.items() if len(ids) > 1}

    blocked = sum(1 for r in raw_check if r["verdict"] == "rejected")
    deriv_ok = all(r["verdict"] == "rejected" for r in extra[:3])
    fresh_ok = extra[3]["verdict"] == "candidate"
    complete, independent_rules = baseline_checks(items, raw_check, scope)
    self_inclusion = all(r3_self.values())
    derivatives_signature_only = all(
        [r["rule"] for r in row["reasons"]] == ["R3-signature"] for row in extra[:3])
    note_probe = screen(
        {"texts": ["寒枝从南堤来到旧坊"]},
        {"寒枝（测试注记）从南堤来到旧坊": ["regression-probe"]}, set(), {})
    note_ok = any(r["rule"] == "R1-substring" for r in note_probe["reasons"])
    ok = (complete and blocked == 10 and independent_rules and self_inclusion
          and deriv_ok
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
            "eachOldItemR3HitListsItself": self_inclusion,
            "signatureCollisions": collisions,
            "derivativesBlockedByR3Only": derivatives_signature_only,
            "noteStrippingRegression": note_ok,
            "threeArmRejected": f"{blocked}/{len(items)}",
            "renamedDerivativeRejected": extra[0]["verdict"],
            "paraphraseDerivativeRejected": extra[1]["verdict"],
            "unitRenamedDerivativeRejected": extra[2]["verdict"],
            "syntheticFreshVerdict": extra[3]["verdict"],
            "pass": ok,
        },
        "threeArm": raw_check,
        "derivatives": extra,
        "limits": [
            "只证明这十条旧题与三条构造派生被规则拦下；不证明排除集完整",
            "R1 只做子串包含；改写后不共享子串的派生不会被 R1 抓到",
            "签名相同只说明形状相同；旧题本身的变化事实依据见 sources/three-arm-provenance.md（十条均为 undetermined）",
            "R3 只比事实形状；换一种形状的语义派生仍需人工核验",
            "新场景判定为 candidate 只表示未被这三条规则命中，不构成验收",
        ],
    }
    write_artifact(OUT / "selftest-report.json", 
        json.dumps(report, ensure_ascii=False, indent=1) + "\n")

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
                     ("单位改名派生（5 分钟写成 300 秒）", extra[2]),
                     ("新场景（三条事实、7 分钟）", extra[3])):
        rules = ", ".join(x["rule"] for x in r["reasons"]) or "（无）"
        expected = "candidate" if r is extra[3] else "rejected"
        lines.append(f"| {label} (`{r['id']}`) | {expected} | {r['verdict']} | {rules} |")
    lines += ["", f"十题完整性：{complete}；每题 R1/R3 独立命中：{independent_rules}；"
              f"派生仅 R3 命中：{derivatives_signature_only}；注记剥离回归：{note_ok}。"]
    if collisions:
        lines += ["", "## 签名碰撞（同一签名保留全部旧题 ID）", "",
                  "| 签名 | 旧题 |", "|---|---|"]
        for sig, ids in collisions.items():
            lines.append(f"| `{sig}` | {', '.join(ids)} |")
        lines += ["", "`nv-cont-3` 与 `nv-empty-1` 都只有时间流逝，按变化口径必然同形；"
                  "两者是否能互相替代，取决于它们的变化事实依据（见 `sources/three-arm-provenance.md`）。"]
    lines += ["", f"**自检结论：{'通过' if ok else '未通过'}**"
              f"（三臂 {blocked}/{len(items)} 被拦、三条派生均被拦、新场景未被误拦、"
              f"每题 R3 命中列表含自身：{self_inclusion}）。", "",
              "## 边界", ""]
    lines += [f"- {x}" for x in report["limits"]]
    write_artifact(OUT / "selftest-report.md", "\n".join(lines) + "\n")

    print(f"head={head[:12]} corpus={len(corpus)} vocab={len(vocab)} items={len(items)} "
          f"blocked={blocked}/{len(items)} renamed={extra[0]['verdict']} "
          f"paraphrase={extra[1]['verdict']} unit-renamed={extra[2]['verdict']} "
          f"fresh={extra[3]['verdict']} PASS={ok}")
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

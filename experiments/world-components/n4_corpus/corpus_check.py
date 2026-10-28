# N4 corpus row checker: per-row faithfulness checks + group consistency +
# rewrite overlap signal + distribution report.
#
# v2 (2026-10-29 review): keyword-presence checks were NOT faithfulness
# checks. This version adds:
#   - direction markers for moved (from-marker must exist; to-marker must
#     exist and must not be a from-marker), subject attribution (person name
#     before the from-marker; other names there = FAIL, absent = REVIEW)
#   - positioned_at requires an at-marker with the entity as the nearest
#     preceding person name
#   - time value must be the numeral IMMEDIATELY before the unit word
#   - task goal: negation words adjacent to the quote = FAIL; a completion
#     verb must be locatable, else REVIEW
#   - sanity direction: 升/涨 with to<=from (or 降/跌/掉 with to>=from) = FAIL
#   - event-verb scan with quote masking: verbs outside the referenced
#     kinds' allowed set = REVIEW (possible added event)
#   - no_change entries: cited sentence must not name concrete entities and
#     must contain a no-change assertion phrase
# Row verdict is three-valued: pass / needs-review / fail. needs-review is
# NOT a pass (per review instruction). Exit code 1 if any row is not pass.
#
# Negative self-test: SEVEN bad rows (out-of-range ref, uncovered must,
# flipped direction, swapped subject, wrong duration value, negated task,
# added event) MUST each be caught with the expected verdict class, else the
# report is void.
#
# Protocol: corpus_protocol.md §5. Usage:
#   python experiments/world-components/n4_corpus/corpus_check.py [files...]

import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent


def corpus_files() -> list:
    if len(sys.argv) > 1:
        return [pathlib.Path(p) for p in sys.argv[1:]]
    files = [HERE / "corpus.seeds.jsonl"]
    rewrites = HERE / "rewrites.jsonl"
    if rewrites.exists():
        files.append(rewrites)
    return files


REQUIRED = ["sourceGroupId", "rowOrigin", "rewriter", "task", "split", "plan",
            "planConstruction", "planValidation", "text", "planRefs",
            "mustExpress", "mayMention", "mustNotAdd", "hashes", "purpose"]

CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}

# 事件动词表：出现在正文且不在被引用条目的支持动词集内 = 新增事件待复核。
# 引语「…」内文本先遮蔽（B frozenQuotes 教训：引语内动词是引用不是主张）。
EVENT_VERBS = ["打开", "推开", "拿起", "捡起", "拾起", "扔", "投掷", "敲", "喊",
               "叫喊", "说道", "说话", "问道", "回答", "跑", "跳跃", "爬",
               "坐下", "躺", "摘下", "搬", "擦拭", "清洗", "拆除", "安装",
               "点燃", "吹灭", "撕", "剪断", "绑", "解开", "拧", "掀开",
               "挖", "埋", "挥舞", "挡住", "抱起", "推动", "拉动", "踢",
               "抚摸", "碰撞", "写下", "画出", "吹奏", "唱"]
ALLOWED_BY_KIND = {
    "moved": ["走", "来", "到", "去", "离开", "抵达", "进", "回", "返回",
              "穿过", "迈", "步行", "出发"],
    "task_achieved": ["完成", "达成", "办妥", "做到"],
    "personality_changed": ["变"],
    "sanity_changed": ["升", "降", "涨", "跌", "掉"],
    "appearance_changed": ["变"],
    "no_change": ["如旧", "动静", "无变化", "照旧"],
    "positioned_at": [],
    "time": [],
}
NO_CHANGE_ASSERTIONS = ["如旧", "没有动静", "无变化", "照旧", "平静如常"]
NEGATION = re.compile(r"没|未|尚未|不再|别|勿")


def cn_to_int(s: str):
    """Parse simple Chinese numerals up to 99; None if not a number."""
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + CN_DIGITS[s[1]] if len(s) == 2 else None
    if "十" in s:
        tens = CN_DIGITS.get(s[0])
        if tens is None or tens < 2:
            return None
        ones = CN_DIGITS.get(s[2], 0) if len(s) == 3 else 0
        return tens * 10 + ones
    return CN_DIGITS.get(s)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def num_before(word: str):
    v = cn_to_int(word)
    return v if v is not None else None


def check_row(r: dict, person_names: list, all_entity_names: list):
    """Returns (fails: list, reviews: list)."""
    fails, reviews = [], []
    text, plan, refs = r["text"], r["plan"], r["planRefs"]
    sentences = [s for s in text.split("。") if s.strip()]
    if len(sentences) != len(refs):
        fails.append(f"planRefs has {len(refs)} entries for {len(sentences)} sentences")

    cited = set()
    for si, srefs in enumerate(refs):
        sent = sentences[si] if si < len(sentences) else ""
        quoted = re.sub(r"「[^」]*」", "⟨Q⟩", sent)  # 引语遮蔽后扫动词
        for ref in srefs:
            if not isinstance(ref, int) or not (0 <= ref < len(plan)):
                fails.append(f"sentence {si}: plan ref {ref} out of range (plan has {len(plan)})")
                continue
            cited.add(ref)
            entry = plan[ref]
            kind = entry.get("kind")
            if kind == "time":
                amount, unit = entry["amount"], entry["unit"]
                unit_word = "分钟" if unit == "minute" else "小时"
                m = re.search(rf"([\d零一二两三四五六七八九十]+)({unit_word})", sent)
                if not m:
                    fails.append(f"sentence {si}: time unit {unit_word} not asserted")
                else:
                    v = num_before(m.group(1))
                    if v != amount:
                        fails.append(
                            f"sentence {si}: time value mismatch — numeral adjacent to "
                            f"{unit_word} is {m.group(1)}={v}, plan says {amount}")
            elif kind == "moved":
                frm, to, name = entry["from"], entry["to"], entry["name"]
                if name not in sent:
                    fails.append(f"sentence {si}: entity {name} not in cited sentence")
                start_mark = next((mk for mk in (f"从{frm}", f"由{frm}", f"离开{frm}") if mk in sent), None)
                if start_mark is None:
                    fails.append(
                        f"sentence {si}: moved from-marker missing (need 从/由/离开 + {frm}); "
                        f"direction may be flipped")
                else:
                    prefix = sent[:sent.index(start_mark)]
                    others = [n for n in person_names if n != name and n in prefix]
                    if others:
                        fails.append(
                            f"sentence {si}: subject attribution wrong — {others} appears "
                            f"before the from-marker of {name}'s move")
                    elif name not in prefix:
                        reviews.append(
                            f"sentence {si}: subject of '{start_mark}' not program-"
                            f"confirmable (no person name before marker) — needs review")
                if not re.search(rf"到[了]?{to}|进[了]?{to}|在{to}|往{to}", sent):
                    fails.append(f"sentence {si}: moved to-marker for {to} missing")
            elif kind == "positioned_at":
                at, name = entry["at"], entry["name"]
                idx = sent.find(f"在{at}")
                if idx < 0:
                    fails.append(f"sentence {si}: positioned marker 在{at} missing "
                                 f"(mere name/at co-occurrence is not a position claim)")
                else:
                    prefix = sent[:idx]
                    neg = NEGATION.search(sent[max(0, idx - 2):idx])
                    if neg:
                        fails.append(f"sentence {si}: negated position claim 在{at}")
                        continue
                    person_hits = sorted(
                        (n for n in person_names if n in prefix),
                        key=lambda n: prefix.rindex(n))
                    if not person_hits:
                        reviews.append(f"sentence {si}: subject of 在{at} not confirmable")
                    elif person_hits[-1] != name:
                        fails.append(
                            f"sentence {si}: position attribution wrong — nearest person "
                            f"before 在{at} is {person_hits[-1]}, entry is {name}")
            elif kind == "task_achieved":
                name, goal = entry["name"], entry["goal"]
                if name not in sent:
                    fails.append(f"sentence {si}: entity {name} not in cited sentence")
                idx = sent.find(goal)
                if idx < 0:
                    fails.append(f"sentence {si}: task goal quote not verbatim")
                else:
                    before = sent[max(0, idx - 8):idx]
                    if NEGATION.search(before):
                        fails.append(f"sentence {si}: negation adjacent to task goal quote")
                    after = sent[idx + len(goal):idx + len(goal) + 4]
                    if not re.search(r"完成|达成|办妥|做到|已", before + after):
                        reviews.append(
                            f"sentence {si}: completion verb not locatable around goal — "
                            f"achievement claim needs review")
            elif kind == "personality_changed":
                if entry["name"] not in sent:
                    fails.append(f"sentence {si}: entity {entry['name']} not in cited sentence")
                if entry["text"] not in sent:
                    fails.append(f"sentence {si}: personality text not asserted")
            elif kind == "sanity_changed":
                lo, hi, name = entry["from"], entry["to"], entry["name"]
                if name not in sent:
                    fails.append(f"sentence {si}: entity {name} not in cited sentence")
                if not re.search(rf"(?<!\d){lo}(?!\d)", sent) or not re.search(rf"(?<!\d){hi}(?!\d)", sent):
                    fails.append(f"sentence {si}: sanity {lo}->{hi} not both asserted")
                if f"从{lo}" not in sent:
                    fails.append(f"sentence {si}: sanity start value not marked with 从{lo}")
                if re.search(r"升|涨", sent) and hi <= lo:
                    fails.append(f"sentence {si}: sanity direction wrong — 升 with {lo}->{hi}")
                if re.search(r"降|跌|掉", sent) and hi >= lo:
                    fails.append(f"sentence {si}: sanity direction wrong — 降 with {lo}->{hi}")
            elif kind == "appearance_changed":
                if entry["name"] not in sent:
                    fails.append(f"sentence {si}: entity {entry['name']} not in cited sentence")
                if entry["text"] not in sent:
                    fails.append(f"sentence {si}: appearance text not asserted")
            elif kind == "no_change":
                concrete = [n for n in all_entity_names if n in sent]
                if concrete:
                    fails.append(
                        f"sentence {si}: no_change sentence asserts concrete entities "
                        f"{concrete} without supporting plan entries")
                if not any(w in sent for w in NO_CHANGE_ASSERTIONS):
                    reviews.append(f"sentence {si}: no-change assertion phrase not located")

        # event-verb scan on masked sentence vs allowed union of THIS sentence's kinds
        kinds_here = {plan[ref]["kind"] for ref in srefs
                      if isinstance(ref, int) and 0 <= ref < len(plan)}
        allowed = {v for k in kinds_here for v in ALLOWED_BY_KIND.get(k, [])}
        for verb in EVENT_VERBS:
            if verb in quoted and verb not in allowed:
                reviews.append(
                    f"sentence {si}: event verb '{verb}' outside supported verbs of "
                    f"{sorted(kinds_here)} — possible added event, needs review")

    must = set(r["mustExpress"])
    if not must <= cited:
        fails.append(f"mustExpress {sorted(must - cited)} not covered by planRefs")

    if r["rowOrigin"] == "rewrite":
        if r.get("rewriter") != "zcode-model":
            fails.append("rewrite row must register rewriter zcode-model")
        if "overlap" not in r or "ratio" not in r.get("overlap", {}):
            reviews.append("rewrite row missing overlap.ratio (computed by this checker)")
    elif r.get("rewriter") != "program":
        fails.append("template-seed row must have rewriter=program")

    if r["hashes"]["text"] != sha(text):
        fails.append("text hash mismatch")
    plan_canon = json.dumps(plan, ensure_ascii=False, sort_keys=True)
    if r["hashes"]["plan"] != hashlib.sha256(plan_canon.encode("utf-8")).hexdigest():
        fails.append("plan hash mismatch")

    return fails, reviews


def masked_bigrams(text: str, names: set, goals: set) -> set:
    t = text
    for name in sorted(names, key=len, reverse=True):
        t = t.replace(name, "⟨N⟩")
    for goal in sorted(goals, key=len, reverse=True):
        t = t.replace(goal, "⟨Q⟩")
    t = re.sub(r"[零一二两三四五六七八九十\d]+(分钟|小时)", "⟨V⟩", t)
    t = re.sub(r"精神值从\d+升到\d+|精神值从\d+降到\d+", "⟨V⟩", t)
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else set()


def main() -> None:
    inputs = corpus_files()
    rows = []
    for cf in inputs:
        rows += [json.loads(line) for line in
                 cf.read_text(encoding="utf-8").splitlines() if line.strip()]

    person_names = sorted({e["name"] for r in rows for e in r["plan"]
                           if e.get("kind") in ("moved", "positioned_at", "task_achieved",
                                                "personality_changed", "sanity_changed")})
    all_entity_names = sorted({e["name"] for r in rows for e in r["plan"] if "name" in e})

    # ---- negative self-test: 7 bad rows, each with expected verdict class ----
    base = dict(rows[0])  # n4-loc-001: 陈舟 东门→钟楼, 3 分钟
    multi = next(r for r in rows if r["sourceGroupId"].startswith("n4-multi"))
    task_row = next(r for r in rows if any(e["kind"] == "task_achieved" for e in r["plan"])
                    and r["split"] == "train")
    empty_row = next(r for r in rows if r["sourceGroupId"].startswith("n4-empty"))
    time_entry = [e for e in base["plan"] if e["kind"] == "time"][0]

    def variant(src, **kw):
        v = dict(src)
        v.update(kw)
        return v

    bads = [
        (variant(base, planRefs=[[7]]), "fail", "ref-range"),
        (variant(base, mustExpress=[5], planRefs=[[0, 1]]), "fail", "must-coverage"),
        (variant(base, text="陈舟从钟楼来到了东门。前后大约三分钟。", hashes={"plan": base["hashes"]["plan"], "text": sha("陈舟从钟楼来到了东门。前后大约三分钟。")}), "fail", "direction"),
        (variant(multi, text="沈青从柴房来到碑亭时，陈舟已经在碑亭了。前后大约三分钟。", hashes={"plan": multi["hashes"]["plan"], "text": sha("沈青从柴房来到碑亭时，陈舟已经在碑亭了。前后大约三分钟。")}), "fail", "subject-swap"),
        (variant(empty_row, text="三个人等了三分钟。", hashes={"plan": empty_row["hashes"]["plan"], "text": sha("三个人等了三分钟。")}), "fail", "time-value"),
        (variant(task_row, text=f"{task_row['plan'][0]['name']}没有完成任务「{task_row['plan'][0]['goal']}」。", hashes={"plan": task_row["hashes"]["plan"], "text": sha(f"{task_row['plan'][0]['name']}没有完成任务「{task_row['plan'][0]['goal']}」。")}), "fail", "task-negation"),
        (variant(base, text="陈舟从东门来到了钟楼，打开了一扇暗门。前后大约三分钟。", planRefs=[[0], [1]], hashes={"plan": base["hashes"]["plan"], "text": sha("陈舟从东门来到了钟楼，打开了一扇暗门。前后大约三分钟。")}), "review", "added-event"),
    ]
    void = []
    for bad, expected, label in bads:
        f, rv = check_row(bad, person_names, all_entity_names)
        verdict = "fail" if f else ("review" if rv else "pass")
        if verdict != expected:
            void.append(f"self-test {label}: expected {expected}, got {verdict} (fail={f}, review={rv})")
    if void:
        print("REPORT VOID — checker self-test failed:")
        for x in void:
            print(" ", x)
        sys.exit(2)
    print(f"self-test PASS: 7/7 negative rows caught with expected verdict class")

    # ---- overlap first (check_row reviews missing overlap) ----
    groups = {}
    for r in rows:
        groups.setdefault(r["sourceGroupId"], []).append(r)
    for r in (x for x in rows if x["rowOrigin"] == "rewrite"):
        seeds = [m for m in groups.get(r["sourceGroupId"], []) if m["rowOrigin"] == "template-seed"]
        if not seeds:
            continue
        names = {e["name"] for e in r["plan"] if "name" in e}
        goals = {e["goal"] for e in r["plan"] if e["kind"] == "task_achieved"}
        rb = masked_bigrams(r["text"], names, goals)
        ratios = []
        for s in seeds:
            sb = masked_bigrams(s["text"], names, goals)
            if sb:
                ratios.append(len(rb & sb) / len(rb))
        r["overlap"] = {"ratio": round(max(ratios), 3) if ratios else None,
                        "method": "masked-bigram-overlap-vs-seed (protocol §4)"}
        flag = " REVIEW-FLAG" if (r["overlap"]["ratio"] or 0) > 0.6 else ""
        print(f"overlap {r['sourceGroupId']} ({r['rewriter']}): ratio={r['overlap']['ratio']}{flag}")

    # ---- per-row verdicts ----
    counts = {"pass": 0, "review": 0, "fail": 0}
    for i, r in enumerate(rows):
        f, rv = check_row(r, person_names, all_entity_names)
        verdict = "fail" if f else ("review" if rv else "pass")
        counts[verdict] += 1
        if f or rv:
            print(f"{verdict.upper()} {r['sourceGroupId']} ({r['rowOrigin']}):")
            for p in f:
                print(f"   [fail]  {p}")
            for p in rv:
                print(f"   [review] {p}")
    print(f"row verdicts: {counts['pass']} pass / {counts['review']} needs-review / "
          f"{counts['fail']} fail  (needs-review is NOT a pass)")

    # ---- group consistency (purpose is per-row) ----
    gfail = 0
    for gid, members in groups.items():
        for key in ["split", "plan", "mustExpress"]:
            vals = {json.dumps(m.get(key), ensure_ascii=False, sort_keys=True) for m in members}
            if len(vals) > 1:
                gfail += 1
                print(f"GROUP FAIL {gid}: inconsistent {key}")
    print(f"group checks: {len(groups) - gfail}/{len(groups)} groups consistent")

    # ---- distribution ----
    print("\ndistribution:")
    for key in ["rowOrigin", "rewriter", "split"]:
        c = {}
        for r in rows:
            c[r[key]] = c.get(r[key], 0) + 1
        print(f"  {key}: {c}")
    fam = {}
    for r in rows:
        fam[r["sourceGroupId"].rsplit("-", 1)[0]] = fam.get(r["sourceGroupId"].rsplit("-", 1)[0], 0) + 1
    print(f"  families: {fam}")
    time_rows = sum(1 for r in rows if any(e["kind"] == "time" for e in r["plan"]))
    empty = sum(1 for r in rows if r["sourceGroupId"].startswith("n4-empty"))
    multi = sum(1 for r in rows if r["sourceGroupId"].startswith("n4-multi"))
    quote = sum(1 for r in rows if any(e["kind"] == "task_achieved" for e in r["plan"]))
    print(f"  time-statement rows: {time_rows}/{len(rows)}, empty-point: {empty}, "
          f"multi-entity: {multi}, task-quote: {quote}")

    sys.exit(0 if (counts["fail"] == 0 and counts["review"] == 0 and gfail == 0) else 1)


if __name__ == "__main__":
    main()

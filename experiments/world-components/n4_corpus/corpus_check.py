# N4 corpus row checker v3: recognizer-whitelist faithfulness.
#
# v3 (2026-10-29 review): v2's keyword-presence checks still let unknown
# expressions pass (five counterexamples all got `pass`). The verdict model
# is now WHITELIST-based: every sentence is split into clauses, and each
# clause must be FULLY COVERED by controlled recognizer patterns built from
# the row's own plan entries. pass = every clause recognized and consistent
# with the plan; any unrecognized residue (added details like 沿着石阶,
# negations like 没有/并非, intents like 打算, wrong actor/value/direction,
# added events) lands in needs-review. needs-review is NOT a pass.
# The old event-verb blocklist is gone: unrecognized content is caught by
# coverage, not by enumerating verbs.
#
# Negative self-test: TWELVE bad rows must each land on the expected verdict
# class (2 fail + 10 review), else the report is void.
#
# Corpus schema v3: rows carry `world` (before-state registry) and
# `rawDelta` (independently constructed delta); `plan` is its projection.
# Hashes cover plan/world/rawDelta/text.
#
# Usage: python experiments/world-components/n4_corpus/corpus_check.py [files...]

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


def split_isolation_problems(rows: list, expect_train_groups: int,
                             expect_dev_groups: int) -> list:
    """Shared train/eval-side isolation assertion (review round 9, extended
    round 10 for the two-plan time-choice structure): rows are grouped by
    sourceGroupId; within a group split must be constant; each group holds
    exactly two plans (expressed + omitted time), each a seed+rewrite pair
    (4 rows); the train and dev GROUP sets must be disjoint; group/row
    counts must match the expected shape. Both train_n4_sentence and
    eval_n4_finetune call this, so neither side can drift into training on
    its dev rows."""
    problems = []
    groups = {}
    for r in rows:
        groups.setdefault(r["sourceGroupId"], []).append(r)
    for gid, ms in groups.items():
        if len({m["split"] for m in ms}) != 1:
            problems.append(f"{gid}: split varies within group")
        if len(ms) != 4:
            problems.append(f"{gid}: expected 4 rows (2 plans x seed+rewrite), got {len(ms)}")
        plan_hashes = [m["hashes"]["plan"] for m in ms]
        if len(set(plan_hashes)) != 2:
            problems.append(f"{gid}: expected exactly 2 distinct plans, got {len(set(plan_hashes))}")
        scopes = sorted(m["timeScope"] for m in ms)
        if scopes != ["expressed", "expressed", "omitted", "omitted"]:
            problems.append(f"{gid}: timeScope pair broken: {scopes}")
        for ph in set(plan_hashes):
            pair = [m for m in ms if m["hashes"]["plan"] == ph]
            if sorted(m["rowOrigin"] for m in pair) != ["rewrite", "template-seed"]:
                problems.append(f"{gid}: plan {ph[:8]} is not a seed+rewrite pair")
    train_groups = {gid for gid, ms in groups.items()
                    if ms[0]["split"] == "train"}
    dev_groups = {gid for gid, ms in groups.items() if ms[0]["split"] == "dev"}
    if train_groups & dev_groups:
        problems.append(f"train/dev group overlap: {sorted(train_groups & dev_groups)}")
    if len(train_groups) != expect_train_groups:
        problems.append(f"expected {expect_train_groups} train groups, got {len(train_groups)}")
    if len(dev_groups) != expect_dev_groups:
        problems.append(f"expected {expect_dev_groups} dev groups, got {len(dev_groups)}")
    if expect_train_groups * 4 != sum(len(groups[g]) for g in train_groups):
        problems.append(f"expected {expect_train_groups * 4} train rows, got "
                        f"{sum(len(groups[g]) for g in train_groups)}")
    if expect_dev_groups * 4 != sum(len(groups[g]) for g in dev_groups):
        problems.append(f"expected {expect_dev_groups * 4} dev rows, got "
                        f"{sum(len(groups[g]) for g in dev_groups)}")
    return problems


REQUIRED = ["sourceGroupId", "rowOrigin", "rewriter", "task", "split", "world",
            "rawDelta", "fullPlan", "plan", "timeScope", "planConstruction",
            "planValidation", "text", "planRefs", "mustExpress", "mayMention",
            "mustNotAdd", "hashes", "purpose"]

CN_NUM = r"[\d零一二两三四五六七八九十]+"
QUOTE = r"「[^」]*」"


CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}


def cn_to_int(s: str):
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
        return tens * 10 + CN_DIGITS.get(s[2], 0) if len(s) == 3 else tens * 10
    return CN_DIGITS.get(s)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def esc(s: str) -> str:
    return re.escape(s)


UNIT_EN = {"分钟": "minute", "小时": "hour"}


def entry_patterns(entry: dict) -> list:
    """Controlled recognizer patterns for one plan entry (regex, unanchored).
    Free-value points are ONLY the numeric durations (moved-embedded and the
    time entry itself): both are parsed (value, unit) and compared against
    the plan by the caller. `rendered` is a construction hint and is NEVER
    trusted as a fact source (v5: a tampered rendered no longer defines what
    the text may say). All other patterns are built from plan values, so a
    match pins the value."""
    kind = entry.get("kind")
    if kind == "moved":
        name, frm, to = entry["name"], entry["from"], entry["to"]
        # v6: NO embedded duration — the plan's time entry is POINT TIME
        # ADVANCE (world clock), not walking time; the source has no
        # action-start/action-end times, so a 用了/花了 duration clause is a
        # different (unsupported) claim and falls out as unrecognized
        # residue -> needs review. 一路 may precede or follow the
        # from-marker; the from-marker takes an optional 了.
        return [rf"(?P<subj>{esc(name)})(?P<pre>(一路))?(从|由|离开)了?{esc(frm)}(一路)?((走|来|进)到了?|到了?|抵达|进入)了?{esc(to)}(时?)"]
    if kind == "task_achieved":
        return [rf"{esc(entry['name'])}(已经|已)?(完成|达成|办妥)了?任务「{esc(entry['goal'])}」"]
    if kind == "personality_changed":
        return [rf"(?:{esc(entry['name'])})?(?:形成了新的人格描述|变得)?了?「?{esc(entry['text'])}」?"]
    if kind == "sanity_changed":
        lo, hi = entry["from"], entry["to"]
        verb = "升到了|提升至|涨到了" if hi > lo else "降到了|降至|跌到了"
        return [rf"精神值从{lo}({verb}){hi}"]
    if kind == "appearance_changed":
        # v7 controlled equivalence (review round 9): 外貌/外观 and full/half
        # width colon are surface variants; entity, description text and the
        # change claim itself stay strict
        return [rf"{esc(entry['name'])}的(?:外貌|外观)变了[：:]{esc(entry['text'])}"]
    if kind == "positioned_at":
        # 已在/已经在 are the same current-state claim
        return [rf"{esc(entry['name'])}(?:已经在|已在){esc(entry['at'])}了?"]
    if kind == "time":
        # v5: value+unit parsed and compared to amount/unit; rendered unused
        return [rf"(?P<pre>前后)?(大约|约|整整)?(?P<num>{CN_NUM}|\d+)(?P<unit>分钟|小时)(?P<post>过去了?)?"]
    if kind == "no_change":
        return [rf"一切(如旧|照旧)|没有动静|平静如常|风平浪静"]
    return []


def time_value_ok(entry: dict, m: "re.Match", plan: list) -> tuple:
    """The time clause's parsed (value, unit) must equal the plan entry."""
    v = cn_to_int(m.group("num"))
    unit_en = UNIT_EN[m.group("unit")]
    if v != entry["amount"] or unit_en != entry["unit"]:
        return False, (f"time clause reads {v}{unit_en} but the plan says "
                       f"{entry['amount']}{entry['unit']}")
    return True, None


PARSERS = {"time": time_value_ok}


def moved_duration_ok(entry: dict, m: "re.Match", plan: list) -> tuple:
    """moved's parsed duration must agree with the row's time entry."""
    dur = m.group("dur")
    if not dur:
        return True, None
    time_entry = next((e for e in plan if e.get("kind") == "time"), None)
    if time_entry is None:
        return False, "moved clause embeds a duration but the plan has no time entry"
    num = re.sub(r"^(用了|花了)", "", dur)
    unit = "分钟" if num.endswith("分钟") else "小时" if num.endswith("小时") else None
    digits = num[: -len(unit)] if unit else num
    v = cn_to_int(digits)
    if v != time_entry["amount"]:
        return False, (f"embedded duration {dur}={v} contradicts the planned time "
                       f"{time_entry['amount']}{time_entry['unit']}")
    return True, None


def check_row(r: dict):
    """Returns (fails, reviews). v4: a plan entry counts as EXPRESSED only
    when a recognizer matched it AND parsed values agree with the plan;
    mustExpress requires expression evidence, not a planRefs mention."""
    fails, reviews = [], []
    text, plan, refs = r["text"], r["plan"], r["planRefs"]
    sentences = [s for s in text.split("。") if s.strip()]
    if len(sentences) != len(refs):
        fails.append(f"planRefs has {len(refs)} entries for {len(sentences)} sentences")

    cited = set()
    expressed = set()
    for si, srefs in enumerate(refs):
        sent = sentences[si] if si < len(sentences) else ""
        for ref in srefs:
            if not isinstance(ref, int) or not (0 <= ref < len(plan)):
                fails.append(f"sentence {si}: plan ref {ref} out of range (plan has {len(plan)})")
            else:
                cited.add(ref)
        # clause coverage + value-consistent expression evidence
        entries = [plan[ref] for ref in srefs
                   if isinstance(ref, int) and 0 <= ref < len(plan)]
        for clause in [c for c in re.split(r"[,，;；]", sent) if c.strip()]:
            core = clause.strip()
            spans = []
            for entry in entries:
                parser = PARSERS.get(entry.get("kind"))
                for p in entry_patterns(entry):
                    for m in re.finditer(p, core):
                        spans.append((m.start(), m.end()))
                        if parser is not None:
                            ok, why = parser(entry, m, plan)
                            if not ok:
                                reviews.append(why)
                                continue
                        expressed.add(entry["ref"])
            merged = []
            for s0, e0 in sorted(spans):
                if merged and s0 <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], e0))
                else:
                    merged.append((s0, e0))
            covered = sum(e0 - s0 for s0, e0 in merged)
            residue = re.sub(r"\s", "", core)
            if covered < len(residue):
                reviews.append(
                    f"clause '{core[:24]}' not fully covered by plan recognizers "
                    f"(covered {covered}/{len(residue)}) — unrecognized content, needs review")

    must = set(r["mustExpress"])
    if not must <= cited:
        fails.append(f"mustExpress {sorted(must - cited)} not covered by planRefs")
    unexpressed = sorted(must - expressed)
    if unexpressed:
        reviews.append(
            f"mustExpress {unexpressed} mentioned in planRefs but has no value-"
            f"consistent expression in the text — needs review")

    if r["rowOrigin"] == "rewrite":
        if r.get("rewriter") != "zcode-model":
            fails.append("rewrite row must register rewriter zcode-model")
    elif r.get("rewriter") != "program":
        fails.append("template-seed row must have rewriter=program")

    if r["hashes"]["text"] != sha(text):
        fails.append("text hash mismatch")
    if r["hashes"]["plan"] != hashlib.sha256(canon(r["plan"]).encode("utf-8")).hexdigest():
        fails.append("plan hash mismatch")
    if r["hashes"].get("fullPlan") != hashlib.sha256(
            canon(r["fullPlan"]).encode("utf-8")).hexdigest():
        fails.append("fullPlan hash mismatch")
    if r["hashes"]["world"] != hashlib.sha256(canon(r["world"]).encode("utf-8")).hexdigest():
        fails.append("world hash mismatch")
    if r["hashes"]["rawDelta"] != hashlib.sha256(canon(r["rawDelta"]).encode("utf-8")).hexdigest():
        fails.append("rawDelta hash mismatch")

    # v8 time-choice boundary: plan is fullPlan minus the time entry iff
    # omitted; fullPlan always carries exactly one time entry; an omitted
    # row's text must not state time at all
    def strip_refs(entries):
        return [{k: v for k, v in e.items() if k != "ref"} for e in entries]

    fp, pl = strip_refs(r["fullPlan"]), strip_refs(r["plan"])
    fp_time = [e for e in fp if e.get("kind") == "time"]
    pl_time = [e for e in pl if e.get("kind") == "time"]
    if len(fp_time) != 1:
        fails.append(f"fullPlan must carry exactly one time entry, got {len(fp_time)}")
    if r["timeScope"] == "expressed":
        if len(pl_time) != 1 or pl_time[0] != fp_time[0]:
            fails.append("expressed row: plan time entry missing or differs from fullPlan")
        if canon(fp) != canon(pl):
            fails.append("expressed row: plan must equal fullPlan")
    elif r["timeScope"] == "omitted":
        if pl_time:
            fails.append("omitted row: plan still carries a time entry")
        if canon(pl) != canon([e for e in fp if e.get("kind") != "time"]):
            fails.append("omitted row: plan is not fullPlan minus time")
        if re.search(r"分钟|小时", text):
            reviews.append("omitted row: text states time although the plan omits it")
    else:
        fails.append(f"unknown timeScope {r['timeScope']}")
    if pl_time and len(pl_time) == 1 and fp_time and pl_time[0] != fp_time[0]:
        fails.append("plan time entry differs from fullPlan time entry")

    return fails, reviews


def masked_bigrams(text: str, names: set, goals: set) -> set:
    t = text
    for name in sorted(names, key=len, reverse=True):
        t = t.replace(name, "⟨N⟩")
    for goal in sorted(goals, key=len, reverse=True):
        t = t.replace(goal, "⟨Q⟩")
    t = re.sub(r"[零一二两三四五六七八九十\d]+(分钟|小时)", "⟨V⟩", t)
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else set()


def main() -> None:
    inputs = corpus_files()
    rows = []
    for cf in inputs:
        rows += [json.loads(line) for line in
                 cf.read_text(encoding="utf-8").splitlines() if line.strip()]

    # ---- negative self-test: 12 rows with expected verdict classes ----
    loc1 = next(r for r in rows if r["sourceGroupId"] == "n4-loc-001")
    multi = next(r for r in rows if r["sourceGroupId"].startswith("n4-multi"))
    empty = next(r for r in rows if r["sourceGroupId"].startswith("n4-empty"))
    task = next(r for r in rows if any(e["kind"] == "task_achieved" for e in r["plan"])
                and r["split"] == "train" and r["plan"][0]["name"] == "周砚")
    task_entry = next(e for e in task["plan"] if e["kind"] == "task_achieved")

    def variant(src, **kw):
        v = json.loads(json.dumps(src, ensure_ascii=False))
        v.update(kw)
        return v

    def rehash(v):
        v["hashes"] = {"plan": hashlib.sha256(canon(v["plan"]).encode("utf-8")).hexdigest(),
                       "fullPlan": hashlib.sha256(canon(v["fullPlan"]).encode("utf-8")).hexdigest(),
                       "world": hashlib.sha256(canon(v["world"]).encode("utf-8")).hexdigest(),
                       "rawDelta": hashlib.sha256(canon(v["rawDelta"]).encode("utf-8")).hexdigest(),
                       "text": sha(v["text"])}
        return v

    def with_text(src, new_text, **extra):
        v = variant(src, text=new_text, **extra)
        return rehash(v)

    bads = [
        (variant(loc1, planRefs=[[7]]), "fail", "ref-range"),
        (variant(loc1, mustExpress=[5], planRefs=[[0, 1]]), "fail", "must-coverage"),
        (with_text(loc1, "陈舟从钟楼来到了东门。前后大约三分钟。"), "review", "direction-flip"),
        (with_text(multi, "沈青从水房来到柴房时，陈舟已经在柴房了。前后大约三分钟。"), "review", "subject-swap"),
        (with_text(empty, "三个人等了三分钟。"), "review", "time-value+residue"),
        (with_text(task, f"{task_entry['name']}没有完成任务「{task_entry['goal']}」。", planRefs=[[0]], mustExpress=[0]), "review", "task-negation"),
        (with_text(loc1, "陈舟从东门来到钟楼，打开了一扇暗门。前后大约三分钟。"), "review", "added-event"),
        (with_text(loc1, "陈舟沿着石阶从东门来到钟楼。前后大约三分钟。"), "review", "unsupported-detail"),
        (with_text(loc1, "陈舟没有从东门来到钟楼。前后大约三分钟。"), "review", "negated-move"),
        (with_text(loc1, "陈舟打算从东门来到钟楼。前后大约三分钟。"), "review", "intent-as-fact"),
        (with_text(empty, "大约八分钟过去了，一切并非如旧。"), "review", "negated-empty"),
        (with_text(task, f"沈青知道{task_entry['name']}完成了任务「{task_entry['goal']}」。", planRefs=[[0]], mustExpress=[0]), "review", "wrong-actor"),
        # v4 round-4 counterexamples
        (with_text(loc1, "前后大约三分钟。", planRefs=[[0, 1]]), "review", "must-not-expressed"),
        (with_text(loc1, "陈舟用了八分钟从东门走到了钟楼。前后大约三分钟。"), "review", "embedded-duration-mismatch"),
        (with_text(task, f"{task_entry['name']}任务尚未完成「{task_entry['goal']}」。前后大约三分钟。"), "review", "task-yet-incomplete"),
        # v5 round-5 counterexamples
        (with_text(loc1, "陈舟用了三小时从东门走到了钟楼。前后大约三分钟。"), "review", "embedded-unit-mismatch"),
        (with_text(loc1, "陈舟从东门走到了钟楼。前后大约八分钟。", ),
         "review", "time-clause-value-mismatch"),
    ]
    # rendered tamper: plan's rendered hint says 八分钟 but amount stays 3 —
    # the recognizer must follow amount/unit, not rendered. The tamper
    # syncs fullPlan so plan⊆fullPlan stays intact (isolating the rendered
    # variable from the plan/wholesale structure check).
    r_rendered = variant(loc1)
    r_rendered["plan"][1]["rendered"] = "八分钟"
    r_rendered["fullPlan"][1]["rendered"] = "八分钟"
    r_rendered["text"] = "陈舟从东门走到了钟楼。前后大约八分钟。"
    bads.append((rehash(r_rendered), "review", "rendered-not-trusted"))

    void = []
    # v7: positive-equivalence rows MUST pass (controlled variants), pinned
    # so the equivalence rules themselves are tested, not just the negatives
    appear = next(r for r in rows if r["sourceGroupId"].startswith("n4-appear"))
    multi = next(r for r in rows if r["sourceGroupId"].startswith("n4-multi"))
    equivalents = [
        (with_text(appear, "四十分钟过去了，石桥的外貌变了:门柱上的漆皮剥落了大半。",
                   planRefs=[[0, 1]]), "equiv-appearance-variant"),
        (with_text(multi, "陈舟从东门来到柴房时，林望已在柴房了。前后大约三分钟。"),
         "equiv-positioned-variant"),
    ]
    for good_row, label in equivalents:
        f, rv = check_row(good_row)
        if f or rv:
            void.append(f"equivalence {label}: expected pass, got fail={f} review={rv[:2]}")
    for bad, expected, label in bads:
        f, rv = check_row(bad)
        verdict = "fail" if f else ("review" if rv else "pass")
        if verdict != expected:
            void.append(f"self-test {label}: expected {expected}, got {verdict} (fail={f}; review={rv[:2]})")
    if void:
        print("REPORT VOID — checker self-test failed:")
        for x in void:
            print(" ", x)
        sys.exit(2)
    print(f"self-test PASS: {len(bads)}/{len(bads)} negative rows + "
          f"{len(equivalents)}/{len(equivalents)} equivalence rows")

    # ---- group consistency ----
    groups = {}
    for r in rows:
        groups.setdefault(r["sourceGroupId"], []).append(r)
    gfail = 0
    for gid, members in groups.items():
        # v8: a group intentionally holds two plans (expressed/omitted time);
        # plan/mustExpress/planRefs are per-plan-scope, only split/world/
        # rawDelta/claims are group-level
        for key in ["split", "world", "rawDelta", "planOnlyClaims"]:
            vals = {canon(m.get(key)) for m in members}
            if len(vals) > 1:
                gfail += 1
                print(f"GROUP FAIL {gid}: inconsistent {key}")
    print(f"group checks: {len(groups) - gfail}/{len(groups)} groups consistent")  # group-level keys only

    # ---- overlap signal for rewrites ----
    for r in (x for x in rows if x["rowOrigin"] == "rewrite"):
        seeds = [m for m in groups.get(r["sourceGroupId"], []) if m["rowOrigin"] == "template-seed"]
        if not seeds:
            continue
        names = {e["name"] for e in r["plan"] if "name" in e}
        goals = {e["goal"] for e in r["plan"] if e["kind"] == "task_achieved"}
        rb = masked_bigrams(r["text"], names, goals)
        ratios = [len(rb & sb) / len(rb) for s in seeds
                  if (sb := masked_bigrams(s["text"], names, goals))]
        r["overlap"] = {"ratio": round(max(ratios), 3) if ratios else None,
                        "method": "masked-bigram-overlap-vs-seed (protocol §4)"}
        flag = " REVIEW-FLAG" if (r["overlap"]["ratio"] or 0) > 0.6 else ""
        print(f"overlap {r['sourceGroupId']} ({r['rewriter']}): ratio={r['overlap']['ratio']}{flag}")

    # ---- per-row verdicts ----
    counts = {"pass": 0, "review": 0, "fail": 0}
    for r in rows:
        f, rv = check_row(r)
        verdict = "fail" if f else ("review" if rv else "pass")
        counts[verdict] += 1
        if f or rv:
            print(f"{verdict.upper()} {r['sourceGroupId']} ({r['rowOrigin']}):")
            for p in f:
                print(f"   [fail]   {p}")
            for p in rv:
                print(f"   [review] {p}")
    print(f"row verdicts: {counts['pass']} pass / {counts['review']} needs-review / "
          f"{counts['fail']} fail  (needs-review is NOT a pass)")

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

    sys.exit(0 if (counts["fail"] == 0 and counts["review"] == 0 and gfail == 0) else 1)


if __name__ == "__main__":
    main()

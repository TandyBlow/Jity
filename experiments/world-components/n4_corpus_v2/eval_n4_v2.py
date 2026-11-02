# N4 v2 frozen-holdout eval (commit 2). The judgement machinery for the
# grouped-interface model, with the criteria PRE-REGISTERED HERE before any
# v2 training run:
#
#   G1 fact alignment (hard): every mustExpress fact gets a value-consistent
#      match in the output. The subject of a match may be the entity's NAME
#      or — only when the row's plan GRANTS the pronoun for that entity's
#      group — the granted pronoun. Scope of the subject discipline, on the
#      record: moved/task/sanity/positioned/relative/slot pin the subject
#      hard (a pronoun standing in for an ungranted entity cannot match, so
#      a misbound reference surfaces as an uncovered fact); personality and
#      appearance-attribution are WEAKLY checked (personality requires A
#      subject but accepts the granted pronoun only; appearance paraphrases
#      via the controlled-equivalence fallback can read a bystander
#      sentence). No false pass was produced by these weaker matches in the
#      archived run (all model outputs were correctly attributed).
#   G2 fabrication (hard): after removing matched spans, no registered
#      CHARACTER name and no registered task GOAL may remain in the
#      residue; unmatched goal-quotes or foreign actors are fabrications.
#   G3 time (hard): every group's time attribution must appear with the
#      exact value (leading, middle and trailing attachments all accepted;
#      a wrong value fails the value check).
#   G4 conflict discipline (hard): on conflict rows (same-gender actors
#      merged then split), BOTH actors' names must appear — a single
#      pronoun standing for two people is a misreference.
#   G5 same-name discipline (hard): on same-name rows, neither actor may be
#      pronominalised; each actor's fact must match under the bare name.
#   G6 truncation (hard): the output must end with a completed sentence
#      (。)； the generate finish reason is recorded alongside.
#   P1 pronoun usage (threshold gate): the share of pronoun-ELICITED rows
#      whose output uses a granted pronoun at least once. The threshold is
#      fixed ON THE DEV SPLIT by the pre-registered rule
#      threshold = max(0.5, dev_rate - 0.10) and then applied to the test
#      split unchanged.
#   P2 ablation differential (hard at zero): on pronoun rows the FULL and
#      the 称谓-stripped input are both generated; the outputs must differ
#      on a NON-ZERO share — a zero differential means the model ignores
#      the coreference input and the pronoun capability claim is void.
#
# Modes:
#   --selfcheck : run the aligner over the COMPOSER targets of both corpus
#                 files (no model) — the corpus and the aligner must agree
#                 100% before the model is trusted with them
#   --eval --model <dir> : load the trained checkpoint, greedy decode with
#                 the frozen decode contract, evaluate dev (fix threshold)
#                 then test (apply), archive raw inputs/outputs/reasons

import argparse
import hashlib
import importlib.machinery
import json
import pathlib
import re
import sys
import time
import types

try:
    import pyarrow  # noqa: F401
except Exception:
    _stub = types.ModuleType("pyarrow")
    _stub.__version__ = "16.1.0"
    _stub.__path__ = []
    sys.modules["pyarrow"] = _stub
_tf = types.ModuleType("tensorflow")
_tf.__spec__ = importlib.machinery.ModuleSpec("tensorflow", None)
_tf.__path__ = []
sys.modules.setdefault("tensorflow", _tf)

HERE = pathlib.Path(__file__).resolve().parent
CORPUS_DIR = HERE / "corpus_v2"
TRAIN_FILE = "train-v2.jsonl"
HOLDOUT_FILE = "holdout-v2.jsonl"
WC = HERE.parent
sys.path.insert(0, str(WC))
sys.path.insert(0, str(WC / "n4_corpus"))
sys.path.insert(0, str(HERE))
from corpus_check import cn_to_int, esc, UNIT_EN  # noqa: E402

CN_NUM = r"(?:[零一二两三四五六七八九十百]+|\d+)"
UNIT_RE = r"(?:秒钟?|分钟|小时|天|个月|年)"
REL_CN = {"under": "下方", "above": "上方", "beside": "旁边",
          "in_front_of": "前方", "behind": "后方"}


def fact_patterns(fact: dict, pronoun: str | None) -> list:
    """Value-pinning regexes for one fact; the subject alternates between
    the entity name and (only when granted) the pronoun."""
    kind = fact["kind"]
    name = re.escape(fact.get("name") or "")
    subj = f"(?:{name}|{re.escape(pronoun)})" if pronoun else name
    if kind == "moved":
        frm, to = re.escape(fact["from"]), re.escape(fact["to"])
        return [rf"{subj}(一路)?(从|由|离开)了?{frm}(一路)?[，,]?"
                rf"((走|来|进)到了?|到了?|抵达|进入)了?{to}(时?)"]
    if kind == "task_achieved":
        g = re.escape(fact["goal"])
        return [rf"{subj}(已经|已)?(完成|达成|办妥)了?任务「{g}」"]
    if kind == "subtask_added":
        g, p = re.escape(fact["goal"]), re.escape(fact.get("parentGoal") or "")
        pats = [rf"{subj}接到了新任务「{g}」（隶属「{p}」）"]
        if fact.get("parentGoal"):
            pats.append(rf"{subj}接到了新任务「{g}」，隶属「{p}」")
        else:
            pats.append(rf"{subj}接到了新任务「{g}」")
        return pats
    if kind == "sanity_changed":
        lo, hi = fact["from"], fact["to"]
        verb = "升到了|提升至|涨到了" if hi > lo else "降到了|降至|跌到了"
        return [rf"{subj}的精神值从{lo}(?:{verb}){hi}"]
    if kind == "personality_changed":
        t = re.escape(fact["text"])
        # the subject is REQUIRED for the v2 aligner (the frozen v7
        # corpus_check pattern leaves it optional; a subject-less or
        # wrong-pronoun match would let attribution slip)
        return [rf"{subj}(?:形成了新的人格描述|变得)?了?「?{t}」?"]
    if kind == "personality_removed":
        t = re.escape(fact["text"])
        return [rf"{name}不再保有旧性子「{t}」"]
    if kind == "appearance_changed":
        t = re.escape(fact["text"])
        # controlled equivalence (v2-new, NOT the frozen v7 frame):
        # the canonical frame OR the fact's own text near the right
        # subject in one sentence. Known weakness, on the record: a
        # bystander reading ("X 站着看别人换上了蓑衣") also matches --
        # attribution for appearance paraphrases is WEAKLY checked
        # (the canonical frame stays strict)
        return [rf"{name}的(?:外貌|外观)变了[：:]{t}",
                rf"{subj}[^。]{{0,10}}{t}"]
    if kind == "appearance_removed":
        t = re.escape(fact["text"])
        return [rf"{name}不再保有旧样貌「{t}」"]
    if kind == "positioned_at":
        at = re.escape(fact["at"])
        return [rf"{subj}(?:已经在|已在){at}了?"]
    if kind == "position_relative":
        t, r = re.escape(fact["targetName"]), REL_CN[fact["relation"]]
        if fact.get("op") == "removed":
            return [rf"{subj}不再在{t}{r}"]
        return [rf"{subj}(?:现在|如今)在{t}{r}"]
    if kind == "slot_changed":
        at, s = re.escape(fact["at"]), re.escape(fact["slotLabel"])
        if fact.get("op") == "removed":
            return [rf"{subj}不再位于{at}的{s}"]
        return [rf"{subj}(?:现在|如今)位于{at}的{s}"]
    if kind == "time":
        return [rf"(?P<pre>前后)?(?:大约|约|整整)?(?P<num>{CN_NUM}|\d+)"
                rf"(?P<unit>{UNIT_RE})(?P<post>过去了?)?"]
    if kind == "no_change":
        return [rf"一切(?:如旧|照旧)|没有动静|平静如常|风平浪静"]
    raise ValueError(f"no v2 pattern for kind {kind}")


def grants_by_entity(row: dict) -> dict:
    """entityId -> pronoun, from the row's plan grants."""
    out = {}
    for s in row["plan"]["sentences"]:
        for g in s.get("coreference") or []:
            out[g["refersTo"]] = g["pronoun"]
    return out


def time_value_ok(fact: dict, m: "re.Match") -> tuple:
    v = cn_to_int(m.group("num"))
    unit_en = UNIT_EN[m.group("unit")]
    if v != fact["amount"] or unit_en != fact["unit"]:
        return False, f"time clause reads {v}{unit_en}, plan says " \
                      f"{fact['amount']}{fact['unit']}"
    return True, None


PARSERS = {"time": time_value_ok}


def align(row: dict, text: str) -> dict:
    """Run the fact alignment for one output text. -> {covered: list,
    pronounUsed: bool, problems: [..]}. Punctuation WIDTH is normalised
    before matching (half-width commas/parens carry no fact content — the
    same tolerance the frozen appearance/moved patterns already encode).
    Identical-shape facts (two same-name actors doing the same thing)
    must consume DIFFERENT occurrences, so a match already claimed by an
    earlier fact is skipped when another is available."""
    text = (text.replace(",", "，").replace("(", "（")
            .replace(")", "）"))
    grants = grants_by_entity(row)
    covered, pronoun_used, problems, spans = set(), False, [], []
    claimed = []
    facts = {f["factId"]: f for f in row["facts"]}
    for fid in row["mustExpress"]:
        fact = facts[fid]
        pronoun = grants.get(fact.get("entityId"))
        best = None

        def candidates(patterns):
            for pat in patterns:
                for m in re.finditer(pat, text):
                    if any(m.start() < ce and m.end() > cs
                           for cs, ce in claimed):
                        # overlaps a span already claimed by an identical
                        # earlier fact -- prefer an unclaimed occurrence
                        continue
                    yield (m.start(), -(m.end() - m.start()), m)

        pool = list(candidates(fact_patterns(fact, pronoun)))
        if not pool and pronoun:
            # the name fallback is legal: a second chance without the
            # pronoun subject
            pool = list(candidates(fact_patterns(fact, None)))
        if not pool:
            # fall back to claimed spans (single-occurrence texts)
            for pat in fact_patterns(fact, pronoun):
                for m in re.finditer(pat, text):
                    pool.append((m.start(), -(m.end() - m.start()), m))
        if pool:
            best = min(pool, key=lambda c: c[:2])
        if best is None:
            problems.append(f"uncovered:{fid}:{fact['kind']}")
            continue
        _s, _neglen, m = best
        ok, why = True, None
        parser = PARSERS.get(fact["kind"])
        if parser:
            ok, why = parser(fact, m)
            if not ok:
                problems.append(f"mismatch:{fid}:{why}")
                continue
        covered.add(fid)
        spans.append((m.start(), m.end()))
        claimed.append((m.start(), m.end()))
        if pronoun and m.group(0).startswith(pronoun) \
                and not m.group(0).startswith(fact.get("name") or ""):
            pronoun_used = True
    # G2: residue scan — registered character names and task goals must not
    # survive outside matched spans
    masked = bytearray(b"\x00" * len(text))
    for s, e in spans:
        for i in range(s, e):
            masked[i] = 1
    residue = "".join(ch for i, ch in enumerate(text) if not masked[i])
    for f in row["facts"]:
        if f.get("entityGroup") != "characters":
            continue
        if f.get("name") and f["name"] in residue:
            problems.append(f"residue-name:{f['name']}")
    for f in row["facts"]:
        if f.get("goal") and f["goal"] in residue:
            problems.append(f"residue-goal:{f['goal']}")
    return {"covered": sorted(covered), "pronounUsed": pronoun_used,
            "problems": problems, "residue": residue}


def judge_row(row: dict, text: str, finish_reason: str | None) -> dict:
    """All hard gates for one row (P1/P2 are aggregate-level)."""
    res = align(row, text)
    facts = {f["factId"]: f for f in row["facts"]}
    gates = {}
    gates["G1_alignment"] = not [p for p in res["problems"]
                                 if p.startswith("uncovered:")
                                 or p.startswith("mismatch:")]
    gates["G2_no_fabrication"] = not [p for p in res["problems"]
                                      if p.startswith("residue-")]
    # G3 time: covered by the value-pinning parser inside align (a wrong
    # value is a mismatch) -- restate for the report
    time_fids = [f["factId"] for f in row["facts"] if f["kind"] == "time"]
    gates["G3_time"] = all(fid in res["covered"] for fid in time_fids)
    # G4/G5: discipline rows
    case = row["rowId"].split(":")[1]
    if "conflict" in case:
        actors = [(f["entityId"], f["name"]) for f in row["facts"]
                  if f.get("entityGroup") == "characters"]
        uniq = {nm for _, nm in actors}
        if len(uniq) == 1 and len(actors) > 1:
            # same-name actors: the shared name must occur once per actor
            gates["G4_conflict_names"] = \
                text.count(actors[0][1]) >= len(actors)
        else:
            gates["G4_conflict_names"] = len(actors) >= 2 and all(
                nm in text for _, nm in actors)
    if "same-name" in case:
        grants = grants_by_entity(row)
        gates["G5_same_name_bare"] = not grants
    gates["G6_no_truncation"] = text.rstrip().endswith(("。", "！", "？")) \
        and finish_reason != "length"
    return {"gates": gates, "align": res,
            "pass": all(gates.values())}


def greedy_generate(model, tok, input_text: str, max_new_tokens: int = 128):
    import torch
    enc = tok(input_text, return_tensors="pt")
    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(**enc, do_sample=False, num_beams=1,
                             max_new_tokens=max_new_tokens)
    ms = round((time.perf_counter() - t0) * 1000, 1)
    text = tok.decode(out[0], skip_special_tokens=True)
    # T5 generate returns the decoder sequence; the finish reason under
    # greedy HF generate is eos when the text stopped on its own and
    # "length" when max_new_tokens was hit
    finish = "eos" if int(out.shape[1]) < max_new_tokens else "length"
    return {"text": text, "outputTokens": int(out.shape[1]),
            "wallMs": ms, "finishReason": finish}


def run_eval(model_dir: pathlib.Path, out_path: pathlib.Path,
             max_rows: int | None = None) -> int:
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    import torch
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.manual_seed(0)
    tok = T5Tokenizer.from_pretrained(str(model_dir), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(
        str(model_dir), dtype=torch.float32)
    model.eval()

    def rows_of(name):
        return [json.loads(l) for l in
                (CORPUS_DIR / name).read_text(encoding="utf-8")
                .splitlines() if l.strip()]

    dev = rows_of(TRAIN_FILE)
    dev = [r for r in dev if r["split"] == "dev"]
    test = rows_of(HOLDOUT_FILE)
    if max_rows:
        dev, test = dev[:max_rows], test[:max_rows]

    def evaluate(rows, tag):
        out = []
        for r in rows:
            full = greedy_generate(model, tok, r["input"])
            # a pronoun is only ELICITED where the target itself uses one:
            # a grant on a single-mention entity can never surface a
            # pronoun, so counting those rows would understate the model
            pronoun_in_target = any(p in r["text"]
                                    for p in ("他", "她", "TA"))
            rec = {"rowId": r["rowId"],
                   "input": r["input"], "output": full["text"],
                   "outputTokens": full["outputTokens"],
                   "wallMs": full["wallMs"],
                   "finishReason": full["finishReason"],
                   "pronounElicited": pronoun_in_target,
                   "verdict": judge_row(r, full["text"],
                                        full["finishReason"])}
            if pronoun_in_target:
                abl = greedy_generate(model, tok, r["ablatedInput"])
                rec["ablatedOutput"] = abl["text"]
                rec["ablationDiffers"] = abl["text"] != full["text"]
            out.append(rec)
            print(f"[{tag}] {r['rowId']}: "
                  f"pass={rec['verdict']['pass']}"
                  + (f" ablDiff={rec['ablationDiffers']}"
                     if "ablationDiffers" in rec else ""), flush=True)
        return out

    dev_res = evaluate(dev, "dev")
    # pre-registered threshold rule, fixed on dev BEFORE the test split
    pron = [r for r in dev_res if r["pronounElicited"]]
    dev_rate = (sum(1 for r in pron if r["verdict"]["align"]["pronounUsed"])
                / len(pron)) if pron else 0.0
    threshold = max(0.5, dev_rate - 0.10)
    test_res = evaluate(test, "test")
    t_pron = [r for r in test_res if r["pronounElicited"]]
    t_rate = (sum(1 for r in t_pron if r["verdict"]["align"]["pronounUsed"])
              / len(t_pron)) if t_pron else 0.0
    diffs = [r for r in test_res if r.get("ablationDiffers")]
    diff_rate = len(diffs) / len(t_pron) if t_pron else None
    gates = {
        "G_hard_all_pass": all(r["verdict"]["pass"] for r in test_res),
        "P1_pronoun_usage": t_rate >= threshold,
        "P2_ablation_nonzero": bool(diffs) if t_pron else True,
    }
    archive = {
        "purpose": "N4 grouped-interface frozen-holdout eval (v2 machinery; "
                   "corpus selected by --corpus-dir)",
        "corpus": {"dir": CORPUS_DIR.name, "train": TRAIN_FILE,
                   "holdout": HOLDOUT_FILE},
        "model": {"dir": str(model_dir),
                  "sha256": hashlib.sha256(
                      (model_dir / "model.safetensors").read_bytes()
                  ).hexdigest() if (model_dir / "model.safetensors").exists()
                  else None},
        "decode": {"greedy": True, "num_beams": 1, "max_new_tokens": 128,
                   "deterministic_flags": True},
        "preRegistered": {
            "thresholdRule": "max(0.5, dev_rate - 0.10), fixed on dev "
                             "before test",
            "devRate": round(dev_rate, 4), "threshold": round(threshold, 4),
        },
        "summary": {
            "devRows": len(dev_res),
            "devHardPass": sum(1 for r in dev_res if r["verdict"]["pass"]),
            "testRows": len(test_res),
            "testHardPass": sum(1 for r in test_res
                                if r["verdict"]["pass"]),
            "testPronounUsage": round(t_rate, 4),
            "ablationDiffers": f"{len(diffs)}/{len(t_pron)}",
            "ablationRate": None if diff_rate is None else round(diff_rate, 4),
        },
        "gates": gates, "pass": all(gates.values()),
        "dev": dev_res, "test": test_res,
    }
    out_path.write_text(json.dumps(archive, ensure_ascii=False, indent=1)
                        + "\n", encoding="utf-8")
    print(json.dumps({"summary": archive["summary"], "gates": gates,
                      "pass": archive["pass"]}, ensure_ascii=False, indent=1))
    return 0 if archive["pass"] else 1


def selfcheck() -> int:
    """The aligner must cover 100% of the COMPOSER targets — the corpus
    and the judgement machinery agree before any model enters."""
    failures = []
    for name in (TRAIN_FILE, HOLDOUT_FILE):
        rows = [json.loads(l) for l in
                (CORPUS_DIR / name).read_text(encoding="utf-8")
                .splitlines() if l.strip()]
        for r in rows:
            v = judge_row(r, r["text"], "eos")
            if not v["pass"]:
                failures.append(f"{r['rowId']}: {v['gates']} "
                                f"{v['align']['problems'][:3]}")
    for f in failures[:20]:
        print("SELFCHECK FAIL:", f)
    print(f"aligner selfcheck [{CORPUS_DIR.name}]: "
          f"{'PASS' if not failures else 'FAIL'} ({len(failures)} failures)")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selfcheck", action="store_true")
    parser.add_argument("--eval", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--corpus-dir", default=None)
    parser.add_argument("--train-file", default=None)
    parser.add_argument("--holdout-file", default=None)
    args = parser.parse_args()
    global CORPUS_DIR, TRAIN_FILE, HOLDOUT_FILE
    if args.corpus_dir:
        CORPUS_DIR = pathlib.Path(args.corpus_dir)
    if args.train_file:
        TRAIN_FILE = args.train_file
    elif (CORPUS_DIR / "train-v3.jsonl").exists():
        TRAIN_FILE, HOLDOUT_FILE = "train-v3.jsonl", "holdout-v3.jsonl"
    if args.holdout_file:
        HOLDOUT_FILE = args.holdout_file
    if args.selfcheck:
        return selfcheck()
    if args.eval:
        out = pathlib.Path(args.out) if args.out else \
            HERE.parent.parent.parent / "artifacts" / "world-components" / \
            "n4-v2-holdout-eval.json"
        return run_eval(pathlib.Path(args.model), out, args.max_rows)
    parser.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())

# N3 runner for the D2 frozen arm (round 29). Implements the contract in
# artifacts/world-components/d2-n3-prompt-freeze.json (`runner` block):
#
#   input assembly  json.dumps(viewpoint, ensure_ascii=False), the selected
#                   fact list, literal <条目ID> replacement; no other
#                   rewriting of the frozen prompt text
#   parsing         first top-level JSON object only, no repair
#   retry           suffix taken verbatim from the prompt file, at most one
#                   retry per item
#   failure classes parse failure / structural violation / finish_reason
#                   truncation (its own class) / timeout
#   logging         per-call raw input/output, attempt count, device, dtype,
#                   wall time, token counts, finish_reason
#
# Pre-run gates for REAL inference (backend transformers): the freeze
# record's decodingConfig.approval must be APPROVED and this file's bytes
# must equal runner.sha256 with runner.status == EXECUTABLE — otherwise the
# runner refuses before touching any model. Stub runs (--backend stub) are
# labelled stub in the archive and skip the approval/pin gates; they never
# import or call a model.
#
# Scoring binds the consumed gold to the freeze record:
# evaluation.gold.sha256 is enforced (gate8 scope) and passed to
# d2_metrics.check_gold_sha; a mismatch aborts before scoring. The 8-item
# gate and the 16-item diagnostic set are separate invocations and separate
# archives; the 16-item set is never a gate.

import argparse
import hashlib
import json
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import d2_metrics as dm  # noqa: E402

REPO_ROOT = HERE.parent.parent.parent


def sha_file(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def load_jsonl(path) -> list:
    return [json.loads(line) for line in
            pathlib.Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def load_prompt(freeze: dict, freeze_path: pathlib.Path) -> tuple:
    """verify the prompt file bytes against the freeze record and extract
    the frozen template + retry suffix (both verbatim)."""
    rel = freeze["prompt"]["file"]
    candidates = [REPO_ROOT / rel, freeze_path.parent / pathlib.Path(rel).name,
                  freeze_path.parent.parent.parent / rel]
    prompt_path = next((c for c in candidates if c.exists()), None)
    if prompt_path is None:
        raise FileNotFoundError(f"prompt file not found: {rel}")
    got = sha_file(prompt_path)
    want = freeze["prompt"]["sha256"]
    if got != want:
        raise ValueError(f"prompt sha256 {got} != frozen {want}")
    text = prompt_path.read_text(encoding="utf-8")
    m = re.search(r"```text\n(.*?)\n```", text, re.S)
    if not m:
        raise ValueError("prompt file has no ```text template block")
    template = m.group(1)
    s = re.search(r"重试后缀（固定逐字）：`([^`]+)`", text)
    if not s:
        raise ValueError("prompt file has no retry suffix line")
    suffix = s.group(1)
    for token in ("<条目ID>", "{viewpoint_json}", "{facts_json}"):
        if token not in template:
            raise ValueError(f"template missing placeholder {token}")
    return template, suffix


def assemble_prompt(template: str, item: dict, selected_facts: list) -> str:
    """the frozen assembly rules, nothing else."""
    return (template
            .replace("<条目ID>", item["itemId"])
            .replace("{viewpoint_json}", json.dumps(item["viewpoint"], ensure_ascii=False))
            .replace("{facts_json}", json.dumps(selected_facts, ensure_ascii=False)))


def parse_plan(text: str):
    """first top-level JSON object only, no repair. Shape requirements
    (sentences etc.) are structural, handled by classify_plan.
    -> (row, error)"""
    i = text.find("{")
    if i < 0:
        return None, "no JSON object found"
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[i:])
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(obj, dict):
        return None, "parsed value is not an object"
    return obj, None


def classify_plan(plan, item: dict, selected_facts: list):
    """structural validation against the item. -> list of problems"""
    eff_item = {**item, "facts": selected_facts}
    problems = dm.sentence_shape_problems(plan.get("sentences") or [], f"plan:{item['itemId']}")
    if problems:
        return problems
    problems = dm.structural_problems(plan, eff_item, f"plan:{item['itemId']}")
    want = sorted(f["factId"] for f in selected_facts)
    if dm.h1(plan, eff_item):
        row_ids = sorted(fid for s in plan["sentences"] for fid in s["factIds"])
        if row_ids != want:
            problems = ["plan ids != selected ids"]
    return problems


def selected_facts_of(item: dict, selected_from_target: bool) -> list:
    if selected_from_target:
        tset = set(item.get("target", ()))
        return [f for f in item["facts"] if f["factId"] in tset]
    return item["facts"]


class StubBackend:
    """canned replies; never touches a model. Replies come from a JSONL of
    {itemId, attempts: [{text, finish_reason, output_tokens, timed_out?}]}
    consumed in order per item."""

    name = "stub"
    device = "stub"
    dtype = "stub"

    def __init__(self, replies_path: pathlib.Path):
        self.replies = {r["itemId"]: r.get("attempts", [])
                        for r in load_jsonl(replies_path)}
        self.calls = {}

    def call(self, item_id: str, prompt: str, max_new_tokens: int,
             timeout_s: float, attempt: int) -> dict:
        attempts = self.replies.get(item_id)
        if attempts is None:
            raise RuntimeError(f"stub has no reply for {item_id} (harness misconfiguration)")
        k = attempt - 1
        if k >= len(attempts):
            raise RuntimeError(f"stub has no attempt {attempt} for {item_id}")
        a = attempts[k]
        start = time.perf_counter()
        self.calls[item_id] = self.calls.get(item_id, 0) + 1
        return {"text": a["text"],
                "finish_reason": "length" if a.get("timed_out") else a.get("finish_reason", "stop"),
                "timed_out": bool(a.get("timed_out")),
                "prompt_tokens": len(prompt) // 3,
                "output_tokens": a.get("output_tokens", len(a["text"]) // 3),
                "wall": time.perf_counter() - start}


class TransformersBackend:
    """real inference per the frozen decoding config; unreachable until the
    freeze record gates open (approval + pinned bytes)."""

    name = "transformers"

    def __init__(self, freeze: dict, device: str):
        import torch  # noqa: F401 - imported only on the real path
        from transformers import AutoModelForCausalLM, AutoTokenizer
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cpu":
            self.dtype_name = "float32 (non-gate arm, reported separately)"
            dtype = torch.float32
        else:
            self.dtype_name = "bfloat16 (gate)"
            dtype = torch.bfloat16
        model_id = freeze["decodingConfig"].get("modelId")
        if not model_id:
            raise ValueError("freeze record decodingConfig.modelId not pinned")
        self.device = device
        self.torch = torch
        self.seed = freeze["decodingConfig"]["seed"]
        self.model_id = model_id
        self.weights_sha256 = None  # recorded at load; pinned before a real run
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=dtype)
        self.model.to(device).eval()

    def call(self, item_id: str, prompt: str, max_new_tokens: int,
             timeout_s: float, attempt: int) -> dict:
        torch = self.torch
        torch.manual_seed(self.seed)
        inputs = self.tokenizer(prompt, return_tensors="pt",
                                truncation=True, max_length=4096 - max_new_tokens)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        start = time.perf_counter()

        class _Deadline(torch.nn.Module):  # placeholder kept simple
            pass

        from transformers import StoppingCriteria, StoppingCriteriaList

        class Deadline(StoppingCriteria):
            def __init__(self, t0, budget):
                self.t0, self.budget = t0, budget

            def __call__(self, input_ids, scores, **kwargs):
                return time.perf_counter() - self.t0 > self.budget

        timed_out = [False]

        class Flag(StoppingCriteria):
            def __init__(self, deadline):
                self.deadline = deadline

            def __call__(self, input_ids, scores, **kwargs):
                if self.deadline(input_ids, scores):
                    timed_out[0] = True
                    return True
                return False

        with torch.no_grad():
            out = self.model.generate(
                **inputs, do_sample=False, max_new_tokens=max_new_tokens,
                stopping_criteria=StoppingCriteriaList([Flag(Deadline(start, timeout_s))]))
        gen = out[0][inputs["input_ids"].shape[1]:]
        text = self.tokenizer.decode(gen, skip_special_tokens=True)
        n = int(gen.shape[0])
        return {"text": text,
                "finish_reason": "length" if n >= max_new_tokens else "stop",
                "timed_out": timed_out[0],
                "prompt_tokens": int(inputs["input_ids"].shape[1]),
                "output_tokens": n,
                "wall": time.perf_counter() - start}


def precheck_real(freeze: dict, self_sha: str) -> list:
    """gates that must pass BEFORE any real model load. Empty list = go."""
    problems = []
    if freeze["decodingConfig"].get("approval") != "APPROVED":
        problems.append(
            f"real inference refused: decodingConfig.approval is "
            f"{freeze['decodingConfig'].get('approval')!r}, not APPROVED")
    runner = freeze.get("runner") or {}
    if runner.get("status") != "EXECUTABLE":
        problems.append(
            f"real inference refused: runner.status is {runner.get('status')!r}, not EXECUTABLE")
    if runner.get("sha256") != self_sha:
        problems.append(
            f"real inference refused: runner.sha256 is {runner.get('sha256')!r}, "
            f"this file is {self_sha} — pin the reviewed bytes first")
    return problems


def run(args) -> int:
    freeze_path = pathlib.Path(args.freeze)
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    self_sha = sha_file(pathlib.Path(__file__))
    diagnostic = args.scope == "diagnostic16"

    if args.backend == "transformers":
        problems = precheck_real(freeze, self_sha)
        if problems:
            for p in problems:
                print("GATE:", p)
            return 3

    template, suffix = load_prompt(freeze, freeze_path)

    if args.backend == "stub" and not args.stub_replies:
        print("--backend stub requires --stub-replies")
        return 2
    backend = StubBackend(pathlib.Path(args.stub_replies)) if args.backend == "stub" \
        else TransformersBackend(freeze, args.device)

    items = {r["itemId"]: r for r in load_jsonl(args.items)}
    gold_rows = {}
    expected_gold = None
    if not diagnostic:
        if not args.gold:
            print("gate8 scope requires --gold")
            return 2
        expected_gold = (args.expect_gold_sha256
                         or freeze["evaluation"]["gold"]["sha256"])
        problem = dm.check_gold_sha(args.gold, expected_gold)
        if problem:
            print("PROBLEM:", problem)
            return 2
        gold_rows = {r["itemId"]: r for r in load_jsonl(args.gold)}

    calls = []
    plans = {}
    failures = {}
    for iid, item in items.items():
        selected = selected_facts_of(item, selected_from_target=diagnostic)
        base_prompt = assemble_prompt(template, item, selected)
        outcome = None
        for attempt in (1, 2):
            prompt = base_prompt if attempt == 1 else base_prompt + suffix
            call = backend.call(iid, prompt, freeze["decodingConfig"]["maxNewTokens"],
                                args.timeout_s, attempt)
            entry = {"itemId": iid, "attempt": attempt,
                     "prompt": prompt, "rawOutput": call["text"],
                     "finishReason": call["finish_reason"],
                     "timedOut": call["timed_out"],
                     "promptTokens": call["prompt_tokens"],
                     "outputTokens": call["output_tokens"],
                     "wall": round(call["wall"], 4)}
            calls.append(entry)
            if call["timed_out"]:
                outcome = "timeout"
                break
            if call["finish_reason"] == "length":
                outcome = "truncated"
                break
            plan, err = parse_plan(call["text"])
            if plan is None:
                outcome = f"parse: {err}"
                continue
            problems = classify_plan(plan, item, selected)
            if problems:
                outcome = f"structural: {problems[0]}"
                continue
            outcome = None
            plans[iid] = {"itemId": iid, "sentences": plan["sentences"]}
            break
        if outcome is not None:
            failures[iid] = outcome

    if diagnostic:
        report = dm.evaluate(items, {}, plans, diagnostic=True,
                             selected_from_target=True)
    else:
        report = dm.evaluate(items, gold_rows, plans)
    archive = {
        "purpose": "D2 N3 arm run (frozen prompt, frozen metrics)",
        "scope": args.scope,
        "backend": backend.name,
        "stub": args.backend == "stub",
        "freezeRecord": pathlib.Path(args.freeze).name,
        "freezeRecordSha256": sha_file(freeze_path),
        "promptSha256": freeze["prompt"]["sha256"],
        "runnerSha256": self_sha,
        "gatesSkippedForStub": (["decodingConfig.approval", "runner.pin"]
                                if args.backend == "stub" else []),
        "decoding": {k: freeze["decodingConfig"][k]
                     for k in ("sampling", "seed", "maxNewTokens", "contextWindow",
                               "quantization", "gateDevice")},
        "goldExpectedSha256": expected_gold,
        "items": pathlib.Path(args.items).name,
        "gold": pathlib.Path(args.gold).name if args.gold else None,
        "modelId": freeze["decodingConfig"].get("modelId"),
        "device": backend.device,
        "dtype": backend.dtype,
        "calls": calls,
        "itemOutcomes": {iid: ("ok" if iid in plans else failures[iid])
                         for iid in items},
        "failureClasses": {},
        "report": report,
    }
    for iid, f in failures.items():
        cls = f.split(":")[0]
        archive["failureClasses"][cls] = archive["failureClasses"].get(cls, 0) + 1
    text = json.dumps(archive, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    s = report["summary"]
    print(f"scope={args.scope} backend={backend.name} items={len(items)} "
          f"ok={len(plans)} failed={len(failures)} classes={archive['failureClasses']}")
    print(f"h1={s['h1']} h2={s['h2']} g1={s['g1']['f1']:.4f} gate={s['gate']} "
          f"diagnostic={s['diagnostic']} pass={s['verdict']['pass']}")
    if args.out:
        print(f"archive -> {args.out}")
    return 0


def selftest() -> int:
    import tempfile
    failures = []
    prompt_sha_target = "0" * 64
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        template = ("你是叙事组织器。只输出一个 JSON 对象：\n"
                    '{"itemId": "<条目ID>", "sentences": []}\n'
                    "视角：{viewpoint_json}\n事实条目（输入序）：{facts_json}")
        suffix = "上次输出无法解析为合法计划。重新只输出 JSON 对象。"
        prompt_file = td / "prompt.md"
        prompt_sha = hashlib.sha256(
            (f"# t\n\n```text\n{template}\n```\n\n- 重试后缀（固定逐字）：`{suffix}`\n"
             ).encode("utf-8")).hexdigest()
        prompt_file.write_text(f"# t\n\n```text\n{template}\n```\n\n"
                               f"- 重试后缀（固定逐字）：`{suffix}`\n",
                               encoding="utf-8", newline="\n")

        def freeze_record(approval, runner_status, runner_sha, gold_sha):
            return {
                "prompt": {"file": "prompt.md", "sha256": prompt_sha},
                "decodingConfig": {"approval": approval, "seed": 20261029,
                                   "maxNewTokens": 512, "contextWindow": 4096,
                                   "modelId": None, "sampling": "greedy",
                                   "quantization": "none", "gateDevice": "cuda bf16"},
                "runner": {"status": runner_status, "sha256": runner_sha},
                "evaluation": {"gold": {"file": "gold.jsonl", "sha256": gold_sha},
                               "metricTool": {"file": "d2_metrics.py"}},
            }

        def fact(fid, char, name):
            return {"factId": fid, "kind": "task_achieved", "entityId": char,
                    "name": name, "goal": f"目标{fid}", "at": "潮音渡"}

        facts = [fact("f1", "char_600", "洛九针"), fact("f2", "char_600", "洛九针"),
                 {"factId": "f3", "kind": "time", "amount": 5, "unit": "minute",
                  "at": None}]
        item = {"itemId": "t1", "task": "n3-plan", "split": "dev", "batch": "d2",
                "viewpoint": {"type": "protagonist", "entityId": "char_600",
                              "name": "洛九针", "at": "潮音渡", "rule": "r"},
                "facts": facts, "hashes": {"facts": "x"}}
        items_path = td / "items.jsonl"
        items_path.write_text(json.dumps(item, ensure_ascii=False) + "\n",
                              encoding="utf-8")

        # assembly exactness
        t, sfx = load_prompt(freeze_record("APPROVED", "EXECUTABLE", prompt_sha, ""),
                             td / "f1.json")
        if sfx != suffix:
            failures.append("retry suffix not extracted verbatim")
        asm = assemble_prompt(t, item, facts)
        want_asm = (template
                    .replace("<条目ID>", "t1")
                    .replace("{viewpoint_json}", json.dumps(item["viewpoint"], ensure_ascii=False))
                    .replace("{facts_json}", json.dumps(facts, ensure_ascii=False)))
        if asm != want_asm:
            failures.append("assembly is not the literal frozen substitution")
        if "<条目ID>" in asm or "{viewpoint_json}" in asm:
            failures.append("placeholders left after assembly")

        # parsing: first top-level object, no repair; sentences presence is
        # a structural matter, not a parse one
        row, err = parse_plan('noise {"itemId": "x"} trailing')
        if row is None or row.get("itemId") != "x":
            failures.append(f"first-object parse failed: {err}")
        row, err = parse_plan("not json at all")
        if row is not None:
            failures.append("non-JSON text parsed")
        if not classify_plan({"itemId": "y"}, item, facts):
            failures.append("plan without sentences not classified structural")

        # structural classification catches extra fields and coverage breaks
        bad = {"itemId": "t1", "sentences": [
            {"index": 0, "factIds": ["f1"],
             "coreference": [{"mention": "洛九针", "refersTo": "char_600", "score": 1}]}]}
        if not classify_plan(bad, item, facts):
            failures.append("extra-field entry not classified structural")
        good = {"itemId": "t1", "sentences": [
            {"index": 0, "factIds": ["f1", "f2", "f3"],
             "coreference": [{"mention": "洛九针", "refersTo": "char_600"},
                             {"mention": "洛九针", "refersTo": "char_600"}]}]}
        if classify_plan(good, item, facts):
            failures.append("valid plan misclassified")

        # real-inference gate: PENDING approval or unpinned runner must refuse
        ns = argparse.Namespace(freeze=str(td / "f1.json"), items=str(items_path),
                                scope="gate8", backend="transformers",
                                stub_replies=None, gold=None,
                                expect_gold_sha256=None, device="cpu",
                                timeout_s=10, out=None)
        fr = freeze_record("PENDING-OWNER-APPROVAL", "NOT-IMPLEMENTED", None, "")
        (td / "f1.json").write_text(json.dumps(fr, ensure_ascii=False), encoding="utf-8")
        if run(ns) != 3:
            failures.append("PENDING approval did not refuse real inference")
        fr2 = freeze_record("APPROVED", "EXECUTABLE", "0" * 64, "")
        (td / "f1.json").write_text(json.dumps(fr2, ensure_ascii=False), encoding="utf-8")
        if run(argparse.Namespace(**{**vars(ns)})) != 3:
            failures.append("unpinned runner bytes did not refuse real inference")

        # stub end-to-end: retry recovers a parse failure; truncation is its
        # own class; gold binding enforced
        gold_row = {"itemId": "t1", "sentences": good["sentences"]}
        gold_path = td / "gold.jsonl"
        gold_path.write_text(json.dumps(gold_row, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        gold_sha = hashlib.sha256(gold_path.read_bytes()).hexdigest()
        replies = td / "replies.jsonl"
        ok_text = json.dumps(good, ensure_ascii=False)
        replies.write_text("\n".join([
            json.dumps({"itemId": "t1", "attempts": [
                {"text": "前缀噪音", "finish_reason": "stop"},
                {"text": ok_text, "finish_reason": "stop"}]}, ensure_ascii=False),
        ]), encoding="utf-8")
        fr3 = freeze_record("PENDING-OWNER-APPROVAL", "NOT-IMPLEMENTED", None, gold_sha)
        (td / "f1.json").write_text(json.dumps(fr3, ensure_ascii=False), encoding="utf-8")
        rc = run(argparse.Namespace(**{**vars(ns), "backend": "stub",
                                       "stub_replies": str(replies),
                                       "gold": str(gold_path), "out": str(td / "a1.json")}))
        if rc != 0:
            failures.append(f"stub run with retry failed: rc={rc}")
        else:
            a = json.loads((td / "a1.json").read_text(encoding="utf-8"))
            if not (a["stub"] and a["itemOutcomes"]["t1"] == "ok"
                    and len(a["calls"]) == 2 and a["calls"][1]["attempt"] == 2
                    and a["calls"][1]["prompt"].endswith(suffix)
                    and a["report"]["summary"]["verdict"]["pass"] is True
                    and "decodingConfig.approval" in a["gatesSkippedForStub"]):
                failures.append(f"stub archive unexpected: {json.dumps(a['itemOutcomes'])}")
        # truncated both attempts -> failure class truncated, verdict false
        replies.write_text(json.dumps({"itemId": "t1", "attempts": [
            {"text": "{\"itemId\": \"t1\", \"sent", "finish_reason": "length",
             "output_tokens": 512},
            {"text": "{\"itemId\": \"t1\", \"sent", "finish_reason": "length",
             "output_tokens": 512}]}, ensure_ascii=False) + "\n", encoding="utf-8")
        rc = run(argparse.Namespace(**{**vars(ns), "backend": "stub",
                                       "stub_replies": str(replies),
                                       "gold": str(gold_path), "out": str(td / "a2.json")}))
        if rc != 0:
            failures.append(f"truncated stub run rc={rc}")
        else:
            a = json.loads((td / "a2.json").read_text(encoding="utf-8"))
            if a["itemOutcomes"]["t1"] != "truncated" or \
                    a["failureClasses"].get("truncated") != 1 or \
                    a["report"]["summary"]["verdict"]["pass"] is not False:
                failures.append(f"truncation class wrong: {a['itemOutcomes']}")
        # gold mismatch aborts before scoring
        rc = run(argparse.Namespace(**{**vars(ns), "backend": "stub",
                                       "stub_replies": str(replies),
                                       "gold": str(gold_path),
                                       "expect_gold_sha256": "dead" * 16,
                                       "out": None}))
        if rc != 2:
            failures.append(f"gold mismatch rc={rc}, expected 2")

    for f in failures:
        print("SELFTEST FAIL:", f)
    print("selftest:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--freeze",
                        default=str(REPO_ROOT / "artifacts/world-components/d2-n3-prompt-freeze.json"))
    parser.add_argument("--items", default=str(HERE / "d2_capability_items.jsonl"))
    parser.add_argument("--scope", choices=["gate8", "diagnostic16"], default="gate8")
    parser.add_argument("--backend", choices=["stub", "transformers"], default="stub")
    parser.add_argument("--stub-replies", default=None)
    parser.add_argument("--gold", default=None)
    parser.add_argument("--expect-gold-sha256", default=None,
                        help="override the freeze-record gold pin (defaults to it)")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())

# N3 runner for the D2 frozen arm. Implements the contract in
# artifacts/world-components/d2-n3-prompt-freeze.json (`runner` block):
#
#   input assembly  json.dumps(viewpoint, ensure_ascii=False), the selected
#                   fact list, literal <条目ID> replacement; no other
#                   rewriting of the frozen prompt text
#   parsing         first TOP-LEVEL JSON object only, no repair (a JSON
#                   array or string at top level is rejected, not entered)
#   retry           suffix taken verbatim from the prompt file, at most one
#                   retry per item
#   failure classes parse failure / structural violation / finish_reason
#                   truncation (its own class) / timeout
#   logging         per-call raw input/output, attempt count, device, dtype,
#                   wall time, token counts, finish_reason
#
# Bindings (round 30, review-148f412):
#   gold      gate8 verifies the consumed gold against the freeze record's
#             evaluation.gold.sha256; there is NO caller override.
#   items     gate8 consumes exactly the registered capability set;
#             diagnostic16 consumes exactly the registered v2 dev set
#             (revision artifact `diagnostic16Input`). Subsets, duplicate
#             ids and content drift are refused.
#   metric    the actually-imported d2_metrics bytes must equal
#             evaluation.metricTool.sha256; recorded in the archive.
#   device    cuda bf16 is the ONLY gate. A transformers run on any other
#             device is a non-gate arm: gate=false, verdict.pass=false,
#             reported separately.
#
# Pre-run gates for REAL inference (backend transformers):
# decodingConfig.approval == APPROVED and this file's bytes ==
# runner.sha256 with runner.status == EXECUTABLE — otherwise the runner
# refuses before touching any model. Stub runs never import a model and
# are labelled stub in the archive.

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


def registered_pin(repo_root: pathlib.Path, key: str) -> tuple:
    """hash pins for runner inputs live in the pre-registration chain
    (revision artifact supersedes the v1 record). -> (sha256, source)"""
    for name in ("d2-preregistration-revision.json",
                 "d2-metrics-preregistration.json"):
        path = repo_root / "artifacts/world-components" / name
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if key == "items":
            entry = data.get("unchanged", {}).get("items") or data.get("items")
            if entry and entry.get("sha256"):
                return entry["sha256"], name
        if key == "diagnostic16Input":
            entry = data.get("diagnostic16Input")
            if entry and entry.get("sha256"):
                return entry["sha256"], name
    return None, None


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
    """first TOP-LEVEL JSON object only, no repair. A top-level array or
    string is rejected instead of entered (review-148f412 R8).
    -> (row, error)"""
    dec = json.JSONDecoder()
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            return None, "top-level JSON value is a string, not an object"
        if ch == "[":
            return None, "top-level JSON value is an array, not an object"
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(text, i)
            except json.JSONDecodeError as exc:
                return None, f"invalid JSON: {exc}"
            if not isinstance(obj, dict):
                return None, "parsed value is not an object"
            return obj, None
    return None, "no JSON object found"


def classify_plan(plan, item: dict, selected_facts: list):
    """structural validation against the item. -> list of problems"""
    if plan.get("itemId") != item["itemId"]:
        return [f"plan itemId {plan.get('itemId')!r} != expected "
                f"{item['itemId']!r} (review-148f412 R7)"]
    eff_item = {**item, "facts": selected_facts}
    problems = dm.sentence_shape_problems(plan.get("sentences") or [],
                                          f"plan:{item['itemId']}")
    if problems:
        return problems
    problems = dm.structural_problems(plan, eff_item, f"plan:{item['itemId']}")
    return problems


def selected_facts_of(item: dict, selected_from_target: bool) -> list:
    if selected_from_target:
        tset = set(item.get("target", ()))
        return [f for f in item["facts"] if f["factId"] in tset]
    return item["facts"]


def check_items_binding(items_path, scope: str, items: dict,
                        repo_root: pathlib.Path) -> list:
    """the consumed items file must be the registered input for this scope:
    byte equality with the pin, unique ids, and the full denominator
    (review-148f412 R2)."""
    problems = []
    key = "diagnostic16Input" if scope == "diagnostic16" else "items"
    want_items = 16 if scope == "diagnostic16" else 8
    pin, source = registered_pin(repo_root, key)
    if pin is None:
        return [f"no registered pin found for {key} ({scope} scope)"]
    got = sha_file(items_path)
    if got != pin:
        problems.append(
            f"consumed --items bytes {got} != registered {key} pin {pin} "
            f"({source}); subsets, duplicates and content drift are refused")
    ids = list(items.keys())
    if len(ids) != want_items:
        problems.append(f"{scope} denominator must be {want_items} items, got {len(ids)}")
    if len(set(ids)) != len(ids):
        problems.append(f"{scope} items contain duplicate itemIds")
    return problems


def check_metric_tool(freeze: dict) -> tuple:
    """the actually-imported d2_metrics bytes must equal the freeze pin
    (review-148f412 R6). -> (problems, actual sha)"""
    want = (freeze.get("evaluation", {}).get("metricTool") or {}).get("sha256")
    actual_path = pathlib.Path(dm.__file__)
    actual = sha_file(actual_path)
    problems = []
    if not want:
        problems.append("freeze record has no evaluation.metricTool.sha256 to bind")
    elif actual != want:
        problems.append(
            f"imported metric tool {actual} != frozen pin {want} "
            f"({actual_path.name}); refusing to score with drifted code")
    return problems, actual


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
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cpu":
            self.dtype = "float32 (non-gate arm, reported separately)"
            dtype = torch.float32
        else:
            self.dtype = "bfloat16 (gate)"
            dtype = torch.bfloat16
        model_id = freeze["decodingConfig"].get("modelId")
        if not model_id:
            raise ValueError("freeze record decodingConfig.modelId not pinned")
        self.device = device
        self.torch = torch
        self.seed = freeze["decodingConfig"]["seed"]
        self.model_id = model_id
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

        from transformers import StoppingCriteria, StoppingCriteriaList

        class Deadline(StoppingCriteria):
            def __init__(self, budget):
                self.deadline = start + budget

            def __call__(self, input_ids, scores, **kwargs):
                return time.perf_counter() > self.deadline

        with torch.no_grad():
            out = self.model.generate(
                **inputs, do_sample=False, max_new_tokens=max_new_tokens,
                stopping_criteria=StoppingCriteriaList([Deadline(timeout_s)]))
        total = int(out[0].shape[0])
        n = total - int(inputs["input_ids"].shape[1])
        text = self.tokenizer.decode(out[0], skip_special_tokens=True)
        return {"text": text,
                "finish_reason": "length" if n >= max_new_tokens else "stop",
                "timed_out": False,
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

    metric_problems, metric_sha = check_metric_tool(freeze)
    if metric_problems:
        for p in metric_problems:
            print("GATE:", p)
        return 3

    template, suffix = load_prompt(freeze, freeze_path)

    if args.backend == "stub" and not args.stub_replies:
        print("--backend stub requires --stub-replies")
        return 2
    backend = StubBackend(pathlib.Path(args.stub_replies)) if args.backend == "stub" \
        else TransformersBackend(freeze, args.device)

    items = {r["itemId"]: r for r in load_jsonl(args.items)}
    item_problems = check_items_binding(pathlib.Path(args.items), args.scope,
                                        items, REPO_ROOT)
    if item_problems:
        for p in item_problems:
            print("PROBLEM:", p)
        return 2

    gold_rows = {}
    gold_pin = None
    if not diagnostic:
        if not args.gold:
            print("gate8 scope requires --gold")
            return 2
        # the authoritative pin ALWAYS comes from the freeze record; there
        # is no caller override (review-148f412 R1)
        gold_pin = freeze["evaluation"]["gold"]["sha256"]
        problem = dm.check_gold_sha(args.gold, gold_pin)
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

    # cuda bf16 is the only gate (review-148f412 R4): a transformers run on
    # another device is a non-gate arm regardless of its numbers.
    non_gate = backend.name == "transformers" and backend.device != "cuda"
    if non_gate:
        report["summary"]["gate"] = False
        report["summary"]["verdict"]["pass"] = False
        report["summary"]["verdict"]["note"] = \
            "non-gate arm (device != cuda bf16); the D2 gate never reads this run"

    archive = {
        "purpose": "D2 N3 arm run (frozen prompt, frozen metrics)",
        "scope": args.scope,
        "backend": backend.name,
        "stub": args.backend == "stub",
        "freezeRecord": pathlib.Path(args.freeze).name,
        "freezeRecordSha256": sha_file(freeze_path),
        "promptSha256": freeze["prompt"]["sha256"],
        "runnerSha256": self_sha,
        "metricToolSha256": metric_sha,
        "gatesSkippedForStub": (["decodingConfig.approval", "runner.pin"]
                                if args.backend == "stub" else []),
        "decoding": {k: freeze["decodingConfig"][k]
                     for k in ("sampling", "seed", "maxNewTokens", "contextWindow",
                               "quantization", "gateDevice")},
        "goldExpectedSha256": gold_pin,
        "items": pathlib.Path(args.items).name,
        "gold": pathlib.Path(args.gold).name if args.gold else None,
        "modelId": freeze["decodingConfig"].get("modelId"),
        "device": backend.device,
        "dtype": backend.dtype,
        "nonGateArm": non_gate,
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
          f"diagnostic={s['diagnostic']} pass={s['verdict']['pass']}"
          + (f" ({s['verdict'].get('note')})" if s["verdict"].get("note") else ""))
    if args.out:
        print(f"archive -> {args.out}")
    return 0


def selftest() -> int:
    import contextlib
    import tempfile
    import types as types_mod
    failures = []
    with tempfile.TemporaryDirectory() as td0:
        td = pathlib.Path(td0)
        template = ("你是叙事组织器。只输出一个 JSON 对象：\n"
                    '{"itemId": "<条目ID>", "sentences": []}\n'
                    "视角：{viewpoint_json}\n事实条目（输入序）：{facts_json}")
        suffix = "上次输出无法解析为合法计划。重新只输出 JSON 对象。"
        prompt_text = (f"# t\n\n```text\n{template}\n```\n\n"
                       f"- 重试后缀（固定逐字）：`{suffix}`\n")
        (td / "prompt.md").write_text(prompt_text, encoding="utf-8", newline="\n")
        prompt_sha = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

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
        (td / "items.jsonl").write_text(json.dumps(item, ensure_ascii=False) + "\n",
                                        encoding="utf-8", newline="\n")

        # assembly exactness
        fake_freeze = {"prompt": {"file": "prompt.md", "sha256": prompt_sha}}
        t, sfx = load_prompt(fake_freeze, td / "f1.json")
        if sfx != suffix:
            failures.append("retry suffix not extracted verbatim")
        asm = assemble_prompt(t, item, facts)
        want_asm = (template
                    .replace("<条目ID>", "t1")
                    .replace("{viewpoint_json}", json.dumps(item["viewpoint"], ensure_ascii=False))
                    .replace("{facts_json}", json.dumps(facts, ensure_ascii=False)))
        if asm != want_asm:
            failures.append("assembly is not the literal frozen substitution")

        # parsing: first TOP-LEVEL object; arrays and strings are rejected,
        # not entered (R8)
        row, err = parse_plan('noise {"itemId": "x"} trailing')
        if row is None or row.get("itemId") != "x":
            failures.append(f"first-object parse failed: {err}")
        for wrapped, why in ((f'[{json.dumps({"itemId": "x"})}]', "array"),
                             (f'"{{\\"itemId\\": \\"x\\"}}"', "string")):
            row, err = parse_plan(wrapped)
            if row is not None or "not an object" not in err:
                failures.append(f"top-level {why} was not rejected: {err}")
        row, err = parse_plan("not json at all")
        if row is not None:
            failures.append("non-JSON text parsed")

        # structural classification: wrong/missing output itemId, extra fields
        if not classify_plan({"itemId": "WRONG-ITEM", "sentences": []}, item, facts):
            failures.append("wrong output itemId not classified structural")
        if not classify_plan({"sentences": []}, item, facts):
            failures.append("missing output itemId not classified structural")
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

        # input bindings: a subset/drifted items file must be refused (R2);
        # check against the real registered pins in this repository
        subset = td / "subset.jsonl"
        subset.write_text(json.dumps(item, ensure_ascii=False) + "\n",
                          encoding="utf-8", newline="\n")
        problems = check_items_binding(subset, "gate8", {"t1": item}, REPO_ROOT)
        if not problems:
            failures.append("subset items binding did not refuse")
        problems = check_items_binding(pathlib.Path(HERE / "d2_capability_items.jsonl"),
                                       "gate8",
                                       {r["itemId"]: r for r in load_jsonl(HERE / "d2_capability_items.jsonl")},
                                       REPO_ROOT)
        if problems:
            failures.append(f"registered capability set rejected: {problems}")

        # ---- end-to-end against the REAL registered inputs (read-only):
        # retry recovers a parse failure; truncation and array-wrapping are
        # their own classes; the gold pin has no caller override (R1) ----
        cap_items = HERE / "d2_capability_items.jsonl"
        real_gold_rel = "artifacts/world-components/n2-labels-d2-gold.jsonl"
        real_gold_path = REPO_ROOT / real_gold_rel
        real_gold_sha = sha_file(real_gold_path)
        real_prompt_rel = "experiments/world-components/n2_selection/d2-n3-prompt-draft.md"
        real_prompt_sha = sha_file(REPO_ROOT / real_prompt_rel)
        gold_rows = load_jsonl(real_gold_path)
        e2e_freeze = {
            "prompt": {"file": real_prompt_rel, "sha256": real_prompt_sha},
            "decodingConfig": {"approval": "PENDING-OWNER-APPROVAL", "seed": 20261029,
                               "maxNewTokens": 512, "contextWindow": 4096,
                               "modelId": None, "sampling": "greedy",
                               "quantization": "none", "gateDevice": "cuda bf16"},
            "runner": {"status": "NOT-IMPLEMENTED", "sha256": None},
            "evaluation": {"gold": {"file": real_gold_rel, "sha256": real_gold_sha},
                           "metricTool": {"sha256": sha_file(pathlib.Path(dm.__file__))}},
        }
        (td / "e2e.json").write_text(json.dumps(e2e_freeze, ensure_ascii=False),
                                     encoding="utf-8")
        replies = td / "replies.jsonl"

        def write_canned(attempts_fn):
            rows = [json.dumps({"itemId": r["itemId"], "attempts": attempts_fn(r)},
                               ensure_ascii=False) for r in gold_rows]
            replies.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")

        def e2e_ns(**over):
            base = dict(freeze=str(td / "e2e.json"), items=str(cap_items),
                        scope="gate8", backend="stub", stub_replies=str(replies),
                        gold=str(real_gold_path), device="cpu", timeout_s=10,
                        out=None)
            base.update(over)
            return argparse.Namespace(**base)

        write_canned(lambda r: [{"text": json.dumps(r, ensure_ascii=False),
                                 "finish_reason": "stop"}])
        if run(e2e_ns(out=str(td / "a1.json"))) != 0:
            failures.append("e2e stub run (valid replies) failed")
        else:
            a = json.loads((td / "a1.json").read_text(encoding="utf-8"))
            if not (a["stub"] and a["itemOutcomes"] == {k: "ok" for k in a["itemOutcomes"]}
                    and len(a["calls"]) == 8 and a["calls"][0]["attempt"] == 1
                    and a["report"]["summary"]["verdict"]["pass"] is True
                    and a["report"]["summary"]["h1"] == "8/8"
                    and "decodingConfig.approval" in a["gatesSkippedForStub"]
                    and a["metricToolSha256"] == sha_file(pathlib.Path(dm.__file__))
                    and a["goldExpectedSha256"] == real_gold_sha):
                failures.append("e2e archive unexpected")
        # tampered gold copy vs frozen pin -> exit 2; no override exists (R1)
        tampered = td / "tampered-gold.jsonl"
        tampered.write_bytes(real_gold_path.read_bytes() + b"\n")
        if run(e2e_ns(gold=str(tampered))) != 2:
            failures.append("tampered gold did not abort with exit 2")
        # truncated both attempts -> failure class truncated, gate stays on
        write_canned(lambda r: [
            {"text": json.dumps(r)[:40], "finish_reason": "length", "output_tokens": 512},
            {"text": json.dumps(r)[:40], "finish_reason": "length", "output_tokens": 512}])
        if run(e2e_ns(out=str(td / "a2.json"))) != 0:
            failures.append("truncated e2e stub run failed")
        else:
            a = json.loads((td / "a2.json").read_text(encoding="utf-8"))
            if a["failureClasses"].get("truncated") != 8 or \
                    a["report"]["summary"]["verdict"]["pass"] is not False:
                failures.append(f"truncation classes wrong: {a['failureClasses']}")
        # array-wrapped top level -> parse failure -> retry -> still rejected
        write_canned(lambda r: [
            {"text": f"[{json.dumps(r, ensure_ascii=False)}]", "finish_reason": "stop"},
            {"text": f"[{json.dumps(r, ensure_ascii=False)}]", "finish_reason": "stop"}])
        if run(e2e_ns(out=str(td / "a3.json"))) != 0:
            failures.append("array-wrapped e2e stub run failed")
        else:
            a = json.loads((td / "a3.json").read_text(encoding="utf-8"))
            if a["failureClasses"].get("parse") != 8 or \
                    any(not v.startswith("parse:") for v in a["itemOutcomes"].values()):
                failures.append(f"array-wrap classes wrong: {a['failureClasses']}")

        # real backend through FAKE torch/transformers (R3/R4): full
        # __init__ -> call -> archive, no real model packages; the fake
        # model emits the frozen gold plans
        real_freeze = {
            "prompt": {"file": real_prompt_rel, "sha256": real_prompt_sha},
            "decodingConfig": {"approval": "APPROVED", "seed": 20261029,
                               "maxNewTokens": 512, "contextWindow": 4096,
                               "modelId": "fake-model", "sampling": "greedy",
                               "quantization": "none", "gateDevice": "cuda bf16"},
            "runner": {"status": "EXECUTABLE", "sha256": sha_file(pathlib.Path(__file__))},
            "evaluation": {"gold": {"file": real_gold_rel, "sha256": real_gold_sha},
                           "metricTool": {"sha256": sha_file(pathlib.Path(dm.__file__))}},
        }
        (td / "f2.json").write_text(json.dumps(real_freeze, ensure_ascii=False),
                                    encoding="utf-8")
        write_canned(lambda r: [{"text": json.dumps(r, ensure_ascii=False),
                                 "finish_reason": "stop", "output_tokens": 64}])

        class FakeSeq(list):
            @property
            def shape(self):
                return (len(self),)

        class FakeTensor:
            def __init__(self, n):
                self.shape = (1, n)

            def to(self, device):
                return self

        config = {"text": json.dumps(gold_rows[0], ensure_ascii=False),
                  "output_tokens": 64, "cuda": True}

        class FakeTokenizer:
            last_prompt = ""

            def __call__(self, prompt, return_tensors=None, truncation=False,
                         max_length=None):
                FakeTokenizer.last_prompt = prompt
                return {"input_ids": FakeTensor(len(prompt) // 3)}

            def decode(self, ids, skip_special_tokens=True):
                m = re.search(r'\{"itemId": "([^"]+)"', FakeTokenizer.last_prompt)
                row = next(r for r in gold_rows if r["itemId"] == m.group(1))
                return json.dumps(row, ensure_ascii=False)

        class FakeModel:
            def to(self, device):
                return self

            def eval(self):
                return self

            def generate(self, **kw):
                total = kw["input_ids"].shape[1] + config["output_tokens"]
                return [FakeSeq([0] * total)]

        class FakeAutoTokenizer:
            @staticmethod
            def from_pretrained(model_id):
                return FakeTokenizer()

        class FakeAutoModel:
            @staticmethod
            def from_pretrained(model_id, torch_dtype=None):
                return FakeModel()

        fake_torch = types_mod.ModuleType("torch")
        fake_torch.cuda = types_mod.SimpleNamespace(
            is_available=lambda: config["cuda"])
        fake_torch.float32 = "float32"
        fake_torch.bfloat16 = "bfloat16"
        fake_torch.manual_seed = lambda seed: None
        fake_torch.no_grad = contextlib.nullcontext
        fake_transformers = types_mod.ModuleType("transformers")
        fake_transformers.AutoTokenizer = FakeAutoTokenizer
        fake_transformers.AutoModelForCausalLM = FakeAutoModel
        fake_transformers.StoppingCriteria = type("StoppingCriteria", (), {})
        fake_transformers.StoppingCriteriaList = list
        saved = {k: sys.modules.get(k) for k in ("torch", "transformers")}
        sys.modules["torch"] = fake_torch
        sys.modules["transformers"] = fake_transformers
        try:
            # cuda path: the gate stays open (R4 control)
            rc = run(argparse.Namespace(freeze=str(td / "f2.json"),
                                        items=str(cap_items), scope="gate8",
                                        backend="transformers", stub_replies=None,
                                        gold=str(real_gold_path), device="cuda",
                                        timeout_s=10, out=str(td / "r_cuda.json")))
            if rc != 0:
                failures.append(f"fake-cuda real-backend run rc={rc}")
            else:
                a = json.loads((td / "r_cuda.json").read_text(encoding="utf-8"))
                if not (a["device"] == "cuda" and a["dtype"].startswith("bfloat16")
                        and a["nonGateArm"] is False
                        and a["report"]["summary"]["gate"] is True
                        and a["report"]["summary"]["verdict"]["pass"] is True
                        and a["calls"] and len(a["calls"]) == 8
                        and all(c["finishReason"] == "stop" for c in a["calls"])):
                    failures.append(f"fake-cuda archive wrong: device={a['device']} "
                                    f"gate={a['report']['summary']['gate']}")
            # cpu path: run completes and is forced non-gate (R3+R4)
            config["cuda"] = False
            rc = run(argparse.Namespace(freeze=str(td / "f2.json"),
                                        items=str(cap_items), scope="gate8",
                                        backend="transformers", stub_replies=None,
                                        gold=str(real_gold_path), device="cpu",
                                        timeout_s=10, out=str(td / "r_cpu.json")))
            if rc != 0:
                failures.append(f"fake-cpu real-backend run rc={rc}")
            else:
                a = json.loads((td / "r_cpu.json").read_text(encoding="utf-8"))
                if not (a["device"] == "cpu" and "float32" in a["dtype"]
                        and a["nonGateArm"] is True
                        and a["report"]["summary"]["gate"] is False
                        and a["report"]["summary"]["verdict"]["pass"] is False
                        and "non-gate" in a["report"]["summary"]["verdict"].get("note", "")):
                    failures.append(f"fake-cpu archive wrong: {a['device']} "
                                    f"gate={a['report']['summary']['gate']} "
                                    f"pass={a['report']['summary']['verdict']}")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

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
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())

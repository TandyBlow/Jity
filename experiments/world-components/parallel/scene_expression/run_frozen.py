"""Run each frozen model slot exactly once; refuse to overwrite an existing run.

From the worktree root:
  D:/software/Anaconda/envs/nndl_proj/python.exe -X utf8 \
    experiments/world-components/parallel/scene_expression/run_frozen.py
"""
import hashlib
import json
import pathlib
import platform
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = HERE / "step3"
EXPECTED_HEAD = "d8e03eb"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def git(*args):
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT, text=True, encoding="utf-8").strip()


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def finish_sentence(raw):
    text = raw.strip()
    if not any(c.isalnum() for c in text):
        return ""
    if text.endswith(("。", "！", "？")):
        return text.rstrip("。！？") + text[-1]
    return text.rstrip("，、；,.;：") + "。"


def preflight():
    head = git("rev-parse", "HEAD")
    assert head.startswith(EXPECTED_HEAD), f"Unexpected HEAD: {head}"
    manifest = read(HERE / "frozen/manifest.json")
    checks = []

    def check(path, expected):
        actual = sha(path)
        assert actual == expected, f"Hash mismatch: {path} {actual} != {expected}"
        checks.append({"path": str(path), "sha256": actual, "match": True})

    for key in ("samplesExport", "materials", "inputs", "builder"):
        item = manifest[key]
        check(ROOT / item["path"].replace("\\", "/"), item["sha256"])
    for name, expected in manifest["docs"].items():
        check(HERE / name, expected)
    samples = read(HERE / "step1/narration-split-samples.export.json")
    check(ROOT / samples["source"], manifest["samplesExport"]["sourceSha256"])

    main = pathlib.Path(git("rev-parse", "--path-format=absolute", "--git-common-dir")).parent
    model_dir = main / ".local/models"
    identity = read(HERE / "step1/step1-verify.json")
    for name in ("u240-model.safetensors", "config.json", "spiece.model"):
        item = identity["weights"]["files"][name]
        check(model_dir / name, item["sha256"])
        assert (model_dir / name).stat().st_size == item["bytes"]

    sources = {}
    paths = [pathlib.Path(__file__), ROOT / "experiments/world-components/n4_narrative_dev/sequence_policy.py",
             ROOT / "frontend/src/lib/world-engine/runtime/narration-split-eval.ts",
             ROOT / "frontend/src/lib/world-engine/runtime/narration-split.ts",
             ROOT / "frontend/src/lib/world-engine/runtime/narration-split-samples.ts"]
    for path in paths:
        rel = path.relative_to(ROOT).as_posix()
        item = {"sha256": sha(path), "workingBlob": git("hash-object", "--", rel)}
        if path != pathlib.Path(__file__):
            item["committedBlob"] = git("rev-parse", f"HEAD:{rel}")
            assert item["workingBlob"] == item["committedBlob"], f"Modified dependency: {rel}"
        sources[rel] = item
    return manifest, model_dir, {"head": head, "checks": checks, "sourceFiles": sources,
                                "manifestSha256": sha(HERE / "frozen/manifest.json")}


def main():
    started_at = now()
    for name in ("run.json", "calls.jsonl", "drafts.jsonl", "preflight.json", "failure.json"):
        assert not (OUT / name).exists(), f"Existing run; no retry or overwrite: {OUT / name}"
    manifest, model_dir, preflight_record = preflight()
    OUT.mkdir(exist_ok=True)
    save(OUT / "preflight.json", preflight_record)

    import sentencepiece
    import torch
    import transformers
    from safetensors.torch import load_file
    from transformers import T5Config, T5ForConditionalGeneration, T5Tokenizer

    torch.set_num_threads(14)
    load_started = time.perf_counter()
    tokenizer = T5Tokenizer.from_pretrained(str(model_dir), legacy=False, local_files_only=True)
    config = read(model_dir / "config.json")
    model = T5ForConditionalGeneration(T5Config(**config)).to(device="cpu", dtype=torch.float32)
    state = load_file(str(model_dir / "u240-model.safetensors"), device="cpu")
    result = model.load_state_dict(state, strict=False)
    assert set(result.missing_keys) == {"encoder.embed_tokens.weight", "decoder.embed_tokens.weight"}
    assert not result.unexpected_keys
    assert (model.shared.weight.data_ptr() == model.encoder.embed_tokens.weight.data_ptr()
            == model.decoder.embed_tokens.weight.data_ptr())
    model.eval()
    del state
    load_seconds = time.perf_counter() - load_started

    sys.path.insert(0, str(ROOT / "experiments/world-components/n4_narrative_dev"))
    from sequence_policy import generate_greedy, sequence_policy

    inputs = read(HERE / "frozen/inputs.json")
    measured = read(HERE / "frozen/prompt-tokens.json")["perSample"]
    encoded_inputs = {}
    # Validate EVERY prompt before the first forward pass. A mismatch must not
    # leave a half-run whose earlier candidates could subsequently be selected.
    for sid in manifest["targets"]:
        slots = inputs[sid]["slots"]
        assert sum(s["owner"] == "model" for s in slots) == manifest["modelCallCounts"][sid]
        expected = {r["slot"]: r["tokens"] for r in measured[sid]["calls"]}
        for idx, slot in enumerate(slots):
            if slot["owner"] != "model":
                continue
            tails = []
            for arm in "ABC":
                prompt = slot["prompts"][arm]
                tails.append(prompt[prompt.index("事实="):])
                enc = tokenizer(prompt, return_tensors="pt", truncation=False)
                ids = enc["input_ids"][0].tolist()
                assert ids == tokenizer.encode(prompt, truncation=False)
                assert len(ids) == expected[idx][arm], (sid, idx, arm, len(ids))
                assert max(ids) < model.config.vocab_size
                encoded_inputs[sid, idx, arm] = enc
            assert len(set(tails)) == 1, f"Different fact/instructions across arms: {sid}/{idx}"
    assert len(encoded_inputs) == 24

    records, drafts = [], []
    with (OUT / "calls.jsonl").open("x", encoding="utf-8", newline="\n") as call_log:
        with (OUT / "drafts.jsonl").open("x", encoding="utf-8", newline="\n") as draft_log:
            for sid in manifest["targets"]:
                for arm in "ABC":
                    parts = []
                    for idx, slot in enumerate(inputs[sid]["slots"]):
                        if slot["owner"] == "program":
                            parts.append({"slot": idx, "owner": "program", "kind": slot["kind"],
                                          "text": slot["programText"], "phrase": slot["phrase"]})
                            continue
                        prompt = slot["prompts"][arm]
                        enc = encoded_inputs[sid, idx, arm]
                        row = {"callId": f"{sid}/{arm}/{idx}", "sampleId": sid, "arm": arm,
                               "slot": idx, "kind": slot["kind"], "factLine": slot["factLine"],
                               "prompt": prompt, "promptSha256": hashlib.sha256(prompt.encode()).hexdigest(),
                               "inputTokenIds": enc["input_ids"][0].tolist(),
                               "inputTokens": int(enc["input_ids"].shape[1]),
                               "truncation": False, "attempt": 1, "startedAt": now()}
                        clock_started = time.perf_counter()
                        try:
                            ids, meta = generate_greedy(model, enc, timeout_seconds=30.0)
                            raw = tokenizer.decode(ids[0], skip_special_tokens=True)
                            row.update({"rawText": raw, "outputTokenIds": ids[0].tolist(),
                                        "generation": meta, "error": None})
                        except Exception as exc:
                            row.update({"rawText": "", "outputTokenIds": [],
                                        "generation": {"stopReason": "error", "complete": False},
                                        "error": {"type": type(exc).__name__, "message": str(exc),
                                                  "traceback": traceback.format_exc()}})
                        row["wallSeconds"] = round(time.perf_counter() - clock_started, 6)
                        row["finishedAt"] = now()
                        row["composedText"] = finish_sentence(row["rawText"])
                        row["status"] = ("complete" if row["generation"]["complete"]
                                         and row["composedText"] else "failed")
                        call_log.write(json.dumps(row, ensure_ascii=False) + "\n")
                        call_log.flush()
                        records.append(row)
                        parts.append({"slot": idx, "owner": "model", "kind": slot["kind"],
                                      "callId": row["callId"], "text": row["composedText"],
                                      "complete": row["generation"]["complete"], "phrase": slot["phrase"]})
                        print(f"{len(records):02d}/24 {row['callId']} tokens={row['inputTokens']} "
                              f"{row['generation']['stopReason']} {row['wallSeconds']:.3f}s "
                              f"{row['rawText']}", flush=True)
                    draft = {"sampleId": sid, "arm": arm, "parts": parts,
                             "text": "".join(p["text"] for p in parts),
                             "programOnly": inputs[sid]["modelCallCount"] == 0,
                             "modelCalls": inputs[sid]["modelCallCount"],
                             "allCallsComplete": all(p.get("complete", True) for p in parts)}
                    draft_log.write(json.dumps(draft, ensure_ascii=False) + "\n")
                    draft_log.flush()
                    drafts.append(draft)
    assert len(records) == 24 and len(drafts) == 30
    metadata = {"startedAt": started_at, "finishedAt": now(), "commit": preflight_record["head"],
                "runnerSha256": sha(pathlib.Path(__file__)),
                "manifestSha256": preflight_record["manifestSha256"],
                "device": "cpu", "dtype": "float32", "threads": torch.get_num_threads(),
                "pythonExecutable": sys.executable, "python": platform.python_version(),
                "platform": platform.platform(), "torch": torch.__version__,
                "transformers": transformers.__version__, "sentencepiece": sentencepiece.__version__,
                "modelDirectory": str(model_dir), "parameters": sum(p.numel() for p in model.parameters()),
                "modelVocabSize": model.config.vocab_size, "tokenizerLength": len(tokenizer),
                "modelLoadSeconds": round(load_seconds, 6), "decoding": sequence_policy(30.0),
                "order": "manifest target order, then A/B/C, then frozen slot order; one attempt per slot",
                "calls": len(records), "drafts": len(drafts), "retries": 0, "fallbacks": 0,
                "failedCalls": [r["callId"] for r in records if r["status"] != "complete"],
                "naturalnessGate": "not_evaluable", "effectivePairs": 6,
                "humanReview": "pending", "files": {name: sha(OUT / name) for name in
                    ("preflight.json", "calls.jsonl", "drafts.jsonl")}}
    save(OUT / "run.json", metadata)
    print(json.dumps({k: metadata[k] for k in ("calls", "drafts", "failedCalls", "retries")}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        if OUT.exists() and not (OUT / "failure.json").exists():
            save(OUT / "failure.json", {"at": now(), "type": type(exc).__name__,
                                       "message": str(exc), "traceback": traceback.format_exc()})
        raise

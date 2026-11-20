"""Preflight P1-P9 for the greedy vs beam-2 comparison (minimal inference only).

The run is capped at five fixed units, two arms, two repeats — exactly what the
determinism checks need. It is NOT the comparison run and produces no verdicts.

Checks
  P1 weight sha256            (against the frozen manifest)
  P2 config / tokenizer sha256
  P3 input file + every per-unit input sha256
  P4 judge script hashes
  P5 greedy twice on 5 units: identical token ids
  P6 beam-2 twice on the same units: identical token ids
  P7 beam-2 unit tests (delegates to preflight_beam2.py, no model)
  P8 both arms report the same input sha256 for every unit
  P9 environment versions match the frozen values

Writes artifacts/fact-wording/preflight/{env.json,runs.jsonl,preflight.json}.
Exits non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
EXPERIMENT = HERE.parents[1]
TREE = HERE.parents[5]
REPO = HERE.parents[8]
sys.path.insert(0, str(HERE.parent))

from beam2 import beam2, greedy  # noqa: E402

MANIFEST = EXPERIMENT / "freeze/comparison-inputs-v3.json"
OUT = EXPERIMENT / "artifacts/fact-wording/preflight"
UNITS = ["t01:f0", "t07:f0", "t11:f1", "t22:f0", "t24:f1"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(rows: list[dict], pid: str, ok: bool, detail: str) -> bool:
    rows.append(dict(id=pid, passed=bool(ok), detail=detail))
    print(f"{'PASS' if ok else 'FAIL'}  {pid}: {detail}")
    return bool(ok)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default=str(REPO / ".local/models"))
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--budget", type=float, default=20.0)
    ap.add_argument("--max-new", type=int, default=64)
    ap.add_argument("--limit", type=int, default=len(UNITS))
    args = ap.parse_args()

    os.environ.setdefault("OMP_NUM_THREADS", str(args.threads))
    os.environ.setdefault("MKL_NUM_THREADS", str(args.threads))

    import torch
    from transformers import T5ForConditionalGeneration, T5Tokenizer
    from transformers.modeling_outputs import BaseModelOutput

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows: list[dict] = []

    # ---- P1 / P2 ---------------------------------------------------------
    weights = manifest["weight"]
    p1 = all(sha256(Path(weights[name]["path"])) == weights[name]["sha256"]
             for name in ("model.safetensors", "config.json", "spiece.model"))
    check(rows, "P1/P2", p1,
          "weight " + weights["model.safetensors"]["sha256"][:16] +
          ", config " + weights["config.json"]["sha256"][:16] +
          ", tokenizer " + weights["spiece.model"]["sha256"][:16])

    # ---- P3 --------------------------------------------------------------
    units_row = next(s for s in manifest["inputSets"] if s["id"] == "cf24")
    unit_path = TREE / "artifacts/world-components/n4-cf24-contract.jsonl"
    units = [json.loads(line) for line in unit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    hashes = {u["unitId"]: hashlib.sha256(u["input"].encode("utf-8")).hexdigest() for u in units}
    p3 = (sha256(unit_path) == units_row["sha256"] and len(units) == units_row["units"]
          and hashes == manifest["perUnitInputSha256"]["cf24"])
    check(rows, "P3", p3,
          f"file {sha256(unit_path)[:16]}, units {len(units)}, per-unit hashes match={hashes == manifest['perUnitInputSha256']['cf24']}")

    # ---- P4 --------------------------------------------------------------
    p4 = all(sha256(REPO / s["path"]) == s["sha256"] for s in manifest["judgeScripts"] if s["exists"])
    check(rows, "P4", p4, f"{sum(1 for s in manifest['judgeScripts'] if s['exists'])} scripts")

    # ---- P7 (no model) ---------------------------------------------------
    p7 = subprocess.run([sys.executable, str(HERE.parent / "preflight_beam2.py")],
                        capture_output=True, text=True)
    check(rows, "P7", p7.returncode == 0,
          "beam2 unit tests exit=" + str(p7.returncode) + " (see p7-beam2.json)")

    # ---- environment -----------------------------------------------------
    import sentencepiece, transformers
    env = dict(
        python=platform.python_version(), pythonExecutable=sys.executable,
        torch=torch.__version__, transformers=transformers.__version__,
        sentencepiece=sentencepiece.__version__,
        device="cpu", threads=args.threads,
        cudaAvailable=torch.cuda.is_available(),
        os=platform.platform(), processor=platform.processor(),
        torchDeterministicAlgorithms=torch.are_deterministic_algorithms_enabled(),
    )
    (OUT / "env.json").write_text(json.dumps(env, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    required = manifest["environment"]["required"]
    p9 = (env["python"] == required["python"] and env["torch"] == required["torch"]
          and env["transformers"] == required["transformers"])
    check(rows, "P9", p9,
          f"python {env['python']} torch {env['torch']} transformers {env['transformers']}")

    # ---- model -----------------------------------------------------------
    torch.set_num_threads(args.threads)
    torch.manual_seed(0)
    model_dir = Path(args.model_dir)
    t0 = time.time()
    tokenizer = T5Tokenizer(vocab_file=str(model_dir / "spiece.model"), model_max_length=512)
    model = T5ForConditionalGeneration.from_pretrained(str(model_dir), torch_dtype=torch.float32)
    model.eval()
    load_seconds = time.time() - t0
    decoder_start = model.config.decoder_start_token_id
    eos_id = model.config.eos_token_id

    by_id = {u["unitId"]: u for u in units}
    chosen = [by_id[u] for u in UNITS[:args.limit] if u in by_id]
    if len(chosen) < args.limit:
        raise SystemExit(f"unit list missing ids: {[u for u in UNITS[:args.limit] if u not in by_id]}")

    def make_scorer(text: str):
        encoded = tokenizer(text, return_tensors="pt")
        with torch.no_grad():
            hidden = model.encoder(input_ids=encoded.input_ids,
                                   attention_mask=encoded.attention_mask).last_hidden_state

        def scorer(prefixes):
            batch = len(prefixes)
            dec = torch.tensor([[decoder_start, *p] for p in prefixes], dtype=torch.long)
            mask = torch.ones_like(dec)
            with torch.no_grad():
                out = model(
                    encoder_outputs=BaseModelOutput(last_hidden_state=hidden.expand(batch, -1, -1)),
                    attention_mask=encoded.attention_mask.expand(batch, -1),
                    decoder_input_ids=dec,
                    decoder_attention_mask=mask,
                )
            logprobs = torch.log_softmax(out.logits[:, -1, :].float(), dim=-1)
            return logprobs.tolist()
        return scorer

    run_rows = []
    determinism = {"greedy": [], "beam2": []}
    for unit in chosen:
        in_hash = hashlib.sha256(unit["input"].encode("utf-8")).hexdigest()
        scorer = make_scorer(unit["input"])
        for arm in ("greedy", "beam2"):
            seen = []
            for repeat in (1, 2):
                if arm == "greedy":
                    r = greedy(scorer, eos_id, max_new_tokens=args.max_new,
                               budget_seconds=args.budget)
                    tokens = tuple(t for t in r["tokens"])
                    payload = dict(tokens=list(tokens), score=r["score"],
                                   complete=r["complete"], stopReason=r["stop_reason"],
                                   searchExhausted=r["search_exhausted"],
                                   newTokens=len(tokens), seconds=r["seconds"])
                else:
                    r = beam2(scorer, eos_id, max_new_tokens=args.max_new,
                              budget_seconds=args.budget, start_tokens=())
                    tokens = tuple(t if t != decoder_start else t for t in r.tokens)
                    payload = dict(tokens=list(tokens), score=r.score,
                                   complete=r.complete, stopReason=r.stop_reason,
                                   searchExhausted=r.search_exhausted,
                                   newTokens=len(tokens), seconds=r.seconds,
                                   finishedCount=r.finished_count,
                                   retainedFinished=r.retained_finished,
                                   bestLiveScoreAtStop=r.best_live_score_at_stop,
                                   thresholdAtStop=r.threshold_at_stop)
                text = tokenizer.decode([t for t in tokens if t != decoder_start],
                                        skip_special_tokens=True)
                row = dict(unitId=unit["unitId"], arm=arm, repeat=repeat,
                           inputSha256=in_hash, text=text,
                           limitHit=payload["stopReason"] in ("budget", "cap")
                                    or not payload["searchExhausted"],
                           **payload)
                run_rows.append(row)
                seen.append(tuple(tokens))
            determinism[arm].append(dict(unitId=unit["unitId"],
                                         identical=seen[0] == seen[1],
                                         tokens=[list(t) for t in seen]))

    with (OUT / "runs.jsonl").open("w", encoding="utf-8") as fh:
        for row in run_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def detail(arm: str) -> str:
        items = determinism[arm]
        bad = [d["unitId"] for d in items if not d["identical"]]
        return (f"{arm} twice on {len(items)} units: all identical" if not bad
                else f"{arm} differs on {', '.join(bad)}")

    p5 = all(d["identical"] for d in determinism["greedy"])
    p6 = all(d["identical"] for d in determinism["beam2"])
    check(rows, "P5", p5, detail("greedy"))
    check(rows, "P6", p6, detail("beam2"))

    arm_hashes: dict[tuple[str, str], set[str]] = {}
    for row in run_rows:
        arm_hashes.setdefault((row["unitId"], row["arm"]), set()).add(row["inputSha256"])
    one_per_run = all(len(v) == 1 for v in arm_hashes.values())
    same_across_arms = all(
        next(iter(arm_hashes[(u["unitId"], "greedy")])) == next(iter(arm_hashes[(u["unitId"], "beam2")]))
        for u in chosen)
    check(rows, "P8", one_per_run and same_across_arms,
          f"{len(chosen)} units: single input hash per arm={one_per_run}, identical across arms={same_across_arms}")

    # ---- X1 archive cross-check (supporting evidence, not a numbered check) --
    x1 = dict(enabled=False)
    cross = manifest.get("crossCheck") or {}
    if cross.get("exists"):
        archive_path = REPO / cross["path"]
        if sha256(archive_path) == cross["sha256"]:
            archived = {r["unitId"]: r for r in json.loads(archive_path.read_text(encoding="utf-8"))["rows"]}
            detail_rows = []
            for unit in chosen:
                ours = next(r for r in run_rows
                            if r["unitId"] == unit["unitId"] and r["arm"] == "greedy" and r["repeat"] == 1)
                ref = archived.get(unit["unitId"], {})
                detail_rows.append(dict(
                    unitId=unit["unitId"], sameText=ours["text"] == ref.get("text"),
                    sameTokens=ours["newTokens"] == ref.get("newTokens"),
                    ours=ours["text"], archived=ref.get("text"),
                ))
            x1 = dict(enabled=True, archiveSha256=cross["sha256"],
                      allTextEqual=all(d["sameText"] for d in detail_rows),
                      allTokensEqual=all(d["sameTokens"] for d in detail_rows),
                      units=detail_rows)
        else:
            x1 = dict(enabled=False, reason="archive hash mismatch")

    summary = dict(
        protocol="c4-preflight-v1",
        x1=x1,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        manifestSha256=sha256(MANIFEST),
        modelDir=str(model_dir),
        loadSeconds=load_seconds,
        units=[u["unitId"] for u in chosen],
        checks=rows,
        passed=all(r["passed"] for r in rows),
        determinism=determinism,
        timings=dict(
            greedy=[r["seconds"] for r in run_rows if r["arm"] == "greedy"],
            beam2=[r["seconds"] for r in run_rows if r["arm"] == "beam2"],
        ),
        notRun=["comparison run", "independent acceptance", "human review"],
    )
    (OUT / "preflight.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
                                        encoding="utf-8")
    print("\npreflight passed:", summary["passed"])
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Run candidate T1 (greedy only) on the 85 cf24 units.

Checks before generating:
  * every T1 input equals the frozen v2 hash and differs from the r1 input in exactly
    the one frozen clause (count == 1 per unit);
Then runs greedy with the same model / decode / limits as protocol v3, writes its own
run directory, and snapshots itself so the executed bytes can be verified afterwards.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve()
EXPERIMENT = HERE.parents[1]
TREE = HERE.parents[5]
REPO = HERE.parents[8]
sys.path.insert(0, str(HERE.parent))

from beam2 import greedy  # noqa: E402

CANDIDATE = EXPERIMENT / "freeze/candidate-t1-v2.json"
UNIT_FILE = TREE / "artifacts/world-components/n4-cf24-contract.jsonl"
OUT_ROOT = EXPERIMENT / "artifacts/fact-wording/diagnostic-r2-cand-t1"
MODEL_DIR = REPO / ".local/models"


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    cand = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    old_req, new_req = cand["change"]["oldRequirement"], cand["change"]["newRequirement"]
    frozen = {row["unitId"]: row for row in cand["rows"]}

    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + sha256_bytes(CANDIDATE)[:8]
    run_dir = OUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    snapshot = run_dir / "runner-snapshot.py"
    shutil.copyfile(HERE, snapshot)
    runner_sha_start = sha256_bytes(HERE)
    assert sha256_bytes(snapshot) == runner_sha_start

    units = [json.loads(line) for line in UNIT_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    checks, problems = [], []
    for unit in units:
        row = frozen[unit["unitId"]]
        occurrences = unit["input"].count(old_req)
        new_input = unit["input"].replace(old_req, new_req)
        ok = (occurrences == 1
              and sha256_text(unit["input"]) == row["oldInputSha256"]
              and sha256_text(new_input) == row["newInputSha256"])
        checks.append(dict(unitId=unit["unitId"], occurrences=occurrences, ok=ok))
        if not ok:
            problems.append(unit["unitId"])
    if problems:
        raise SystemExit(f"input verification failed for {len(problems)} units: {problems[:5]}")

    os.environ.setdefault("OMP_NUM_THREADS", "4")
    os.environ.setdefault("MKL_NUM_THREADS", "4")
    import torch
    import sentencepiece
    import transformers
    from transformers import T5ForConditionalGeneration, T5Tokenizer
    from transformers.modeling_outputs import BaseModelOutput

    torch.set_num_threads(4)
    torch.manual_seed(0)
    t0 = time.time()
    tokenizer = T5Tokenizer(vocab_file=str(MODEL_DIR / "spiece.model"), model_max_length=512)
    model = T5ForConditionalGeneration.from_pretrained(str(MODEL_DIR), torch_dtype=torch.float32)
    model.eval()
    decoder_start = model.config.decoder_start_token_id
    eos_id = model.config.eos_token_id
    load_seconds = time.time() - t0

    env = dict(python=platform.python_version(), torch=torch.__version__,
               transformers=transformers.__version__, sentencepiece=sentencepiece.__version__,
               device="cpu", threads=4, cudaAvailable=torch.cuda.is_available(),
               os=platform.platform())
    (run_dir / "env.json").write_text(json.dumps(env, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    run_meta = dict(
        protocol="c4-diagnostic-r2-cand-t1",
        runId=run_id,
        startedAt=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        candidateSha256=sha256_bytes(CANDIDATE),
        oldRequirementSha256=cand["change"]["oldRequirementSha256"],
        newRequirementSha256=cand["change"]["newRequirementSha256"],
        unitFile=str(UNIT_FILE.relative_to(REPO)).replace(chr(92), "/"),
        unitFileSha256=sha256_bytes(UNIT_FILE),
        runnerSha256AtStart=runner_sha_start,
        runnerSnapshot="runner-snapshot.py",
        beam2Sha256=sha256_bytes(HERE.parent / "beam2.py"),
        scheme="T1 greedy only",
        budgetSeconds=20.0, maxNewTokens=64,
        unitOrder="contract file row order (1-85)",
        loadSeconds=load_seconds,
        inputVerification=dict(units=len(checks), allOk=all(c["ok"] for c in checks)),
        env=env,
    )
    (run_dir / "run.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

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
            return torch.log_softmax(out.logits[:, -1, :].float(), dim=-1).tolist()
        return scorer

    raw = (run_dir / "raw.jsonl").open("w", encoding="utf-8")
    order = (run_dir / "order.jsonl").open("w", encoding="utf-8")
    failures = (run_dir / "failures.jsonl").open("w", encoding="utf-8")

    for index, unit in enumerate(units, start=1):
        t1_input = unit["input"].replace(old_req, new_req)
        scorer = make_scorer(t1_input)
        attempt = 0
        while True:
            attempt += 1
            started = time.time()
            try:
                r = greedy(scorer, eos_id, max_new_tokens=64, budget_seconds=20.0)
                break
            except Exception as exc:
                failures.write(json.dumps(dict(unitId=unit["unitId"], attempt=attempt,
                                               error=type(exc).__name__, message=str(exc)[:300],
                                               traceback=traceback.format_exc()[-1200:]), ensure_ascii=False) + "\n")
                failures.flush()
                if attempt >= 2:
                    r = dict(tokens=[], score=0.0, complete=False, stop_reason="error",
                             seconds=round(time.time() - started, 3), search_exhausted=False)
                    break
        limit_hit = r["stop_reason"] in ("budget", "cap") or not r["search_exhausted"]
        text = tokenizer.decode(r["tokens"], skip_special_tokens=True)
        raw.write(json.dumps(dict(
            order=index, unitId=unit["unitId"], sourceId=unit["sourceId"], kind=unit["kind"],
            scheme="T1", text=text, inputSha256=sha256_text(t1_input),
            tokens=list(r["tokens"]), score=r["score"], complete=r["complete"],
            stopReason=r["stop_reason"], newTokens=len(r["tokens"]),
            searchExhausted=r["search_exhausted"], seconds=r["seconds"],
            retryCount=attempt - 1, limitHit=limit_hit,
        ), ensure_ascii=False) + "\n")
        raw.flush()
        order.write(json.dumps(dict(order=index, unitId=unit["unitId"],
                                    startedAt=time.strftime("%Y-%m-%dT%H:%M:%S"),
                                    seconds=round(r["seconds"], 3)), ensure_ascii=False) + "\n")
        order.flush()
        print(f"{index:3d}/85 {unit['unitId']:<8} {r['seconds']:5.2f}s tok={len(r['tokens']):2d} "
              f"stop={r['stop_reason']:<6} limit={limit_hit}", flush=True)

    raw.close()
    order.close()
    failures.close()

    runner_sha_end = sha256_bytes(HERE)
    run_meta.update(finishedAt=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    wallSeconds=round(time.time() - t0, 1),
                    runnerSha256AtEnd=runner_sha_end,
                    runnerUnchanged=runner_sha_end == runner_sha_start)
    (run_dir / "run.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("run dir:", run_dir)
    print("runner unchanged during run:", run_meta["runnerUnchanged"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

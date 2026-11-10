"""cf24 diagnostic run: 85 units x 2 arms, one generation each (protocol v3 §2).

Order is fixed: contract file row order, and within a unit greedy then beam-2.
Only infrastructure errors are retried (max 1). Budget and token cap are the same
for both arms; touching either marks the row `limitHit` and the caller must treat
that unit as undetermined.

Every run writes its own directory:
    artifacts/fact-wording/diagnostic-r1/<runId>/{run.json,raw.jsonl,order.jsonl,failures.jsonl,env.json}
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve()
EXPERIMENT = HERE.parents[1]
TREE = HERE.parents[5]
REPO = HERE.parents[8]
sys.path.insert(0, str(HERE.parent))

from beam2 import beam2, greedy  # noqa: E402

MANIFEST = EXPERIMENT / "freeze/comparison-inputs-v3.json"
PROTOCOL = EXPERIMENT / "comparison-protocol-v3.md"
OUT_ROOT = EXPERIMENT / "artifacts/fact-wording/diagnostic-r1"
UNIT_FILE = TREE / "artifacts/world-components/n4-cf24-contract.jsonl"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + sha256(MANIFEST)[:8]
    run_dir = OUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    os.environ.setdefault("OMP_NUM_THREADS", "4")
    os.environ.setdefault("MKL_NUM_THREADS", "4")
    import torch
    import sentencepiece
    import transformers
    from transformers import T5ForConditionalGeneration, T5Tokenizer
    from transformers.modeling_outputs import BaseModelOutput

    model_dir = REPO / ".local/models"
    torch.set_num_threads(4)
    torch.manual_seed(0)

    env = dict(
        python=platform.python_version(), torch=torch.__version__,
        transformers=transformers.__version__, sentencepiece=sentencepiece.__version__,
        device="cpu", threads=4, cudaAvailable=torch.cuda.is_available(),
        os=platform.platform(),
    )
    (run_dir / "env.json").write_text(json.dumps(env, ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8")

    t0 = time.time()
    tokenizer = T5Tokenizer(vocab_file=str(model_dir / "spiece.model"), model_max_length=512)
    model = T5ForConditionalGeneration.from_pretrained(str(model_dir), torch_dtype=torch.float32)
    model.eval()
    load_seconds = time.time() - t0
    decoder_start = model.config.decoder_start_token_id
    eos_id = model.config.eos_token_id

    units = [json.loads(line) for line in UNIT_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected_hashes = manifest["perUnitInputSha256"]["cf24"]
    assert len(units) == 85, len(units)
    for unit in units:
        assert hashlib.sha256(unit["input"].encode("utf-8")).hexdigest() == expected_hashes[unit["unitId"]], unit["unitId"]

    run_meta = dict(
        protocol="c4-diagnostic-r1",
        runId=run_id,
        startedAt=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        protocolSha256=sha256(PROTOCOL),
        manifestSha256=sha256(MANIFEST),
        beam2Sha256=sha256(HERE.parent / "beam2.py"),
        runnerSha256=sha256(HERE),
        decoderStartTokenId=decoder_start, eosTokenId=eos_id,
        budgetSeconds=20.0, maxNewTokens=64, bothArmsSameLimits=True,
        unitOrder="contract file row order (1-85)",
        armOrder="greedy then beam2, per unit",
        retryPolicy="infrastructure errors only, max 1 attempt retry, recorded",
        loadSeconds=load_seconds,
        unitFile=str(UNIT_FILE.relative_to(REPO)).replace(chr(92), "/"),
        unitFileSha256=sha256(UNIT_FILE),
        env=env,
    )
    (run_dir / "run.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8")

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

    raw = (run_dir / "raw.jsonl").open("w", encoding="utf-8")
    order = (run_dir / "order.jsonl").open("w", encoding="utf-8")
    failures = (run_dir / "failures.jsonl").open("w", encoding="utf-8")

    order_index = 0
    for unit in units:
        scorer = make_scorer(unit["input"])
        in_hash = hashlib.sha256(unit["input"].encode("utf-8")).hexdigest()
        for arm in ("greedy", "beam2"):
            order_index += 1
            attempt = 0
            while True:
                attempt += 1
                started = time.time()
                try:
                    if arm == "greedy":
                        r = greedy(scorer, eos_id, max_new_tokens=64, budget_seconds=20.0)
                        row = dict(tokens=list(r["tokens"]), score=r["score"], complete=r["complete"],
                                   stopReason=r["stop_reason"], newTokens=len(r["tokens"]),
                                   finishedCount=1 if r["complete"] else 0,
                                   searchExhausted=r["search_exhausted"], seconds=r["seconds"])
                    else:
                        r = beam2(scorer, eos_id, max_new_tokens=64, budget_seconds=20.0)
                        row = dict(tokens=list(r.tokens), score=r.score, complete=r.complete,
                                   stopReason=r.stop_reason, newTokens=len(r.tokens),
                                   finishedCount=r.finished_count,
                                   searchExhausted=r.search_exhausted, seconds=r.seconds,
                                   retainedFinished=r.retained_finished,
                                   bestLiveScoreAtStop=r.best_live_score_at_stop,
                                   thresholdAtStop=r.threshold_at_stop)
                    break
                except Exception as exc:  # infrastructure-only retry
                    failures.write(json.dumps(dict(
                        unitId=unit["unitId"], arm=arm, attempt=attempt,
                        error=type(exc).__name__, message=str(exc)[:400],
                        traceback=traceback.format_exc()[-1500:],
                        seconds=round(time.time() - started, 3),
                    ), ensure_ascii=False) + "\n")
                    failures.flush()
                    if attempt >= 2:
                        row = dict(tokens=[], score=0.0, complete=False,
                                   stopReason="error", newTokens=0, searchExhausted=False,
                                   seconds=round(time.time() - started, 3),
                                   infrastructureError=type(exc).__name__)
                        break

            limit_hit = row["stopReason"] in ("budget", "cap") or not row["searchExhausted"]
            text = tokenizer.decode(row["tokens"], skip_special_tokens=True)
            record = dict(
                order=order_index, unitId=unit["unitId"], sourceId=unit["sourceId"], kind=unit["kind"],
                arm=arm, inputSha256=in_hash, text=text,
                retryCount=attempt - 1, limitHit=limit_hit,
                **row,
            )
            raw.write(json.dumps(record, ensure_ascii=False) + "\n")
            raw.flush()
            order.write(json.dumps(dict(
                order=order_index, unitId=unit["unitId"], arm=arm,
                startedAt=time.strftime("%Y-%m-%dT%H:%M:%S"), seconds=round(row["seconds"], 3),
            ), ensure_ascii=False) + "\n")
            order.flush()
            print(f"{order_index:3d}/170 {unit['unitId']:<8} {arm:<6} {row['seconds']:6.2f}s "
                  f"tok={row['newTokens']:2d} stop={row['stopReason']:<6} limit={limit_hit}")

    raw.close()
    order.close()
    failures.close()
    run_meta["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    run_meta["wallSeconds"] = round(time.time() - t0, 1)
    (run_dir / "run.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8")
    print("run dir:", run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

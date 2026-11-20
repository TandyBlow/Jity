# -*- coding: utf-8 -*-
"""Real-model smoke arm (CPU, no training, no GPU).

This is a HARNESS control, not the missing capability arm. It loads the frozen
Randeng-T5-77M base (the same weights the old controllability run started
from, sha256 5cdc5721…), feeds four plan prompts (2 sources x 2 plans) and
records the raw text plus the text-conformance verdict. The base was never
trained to read a plan block, so a failure here is expected and says nothing
about the plan interface; it proves the measurement path works on a real
model and gives a floor for the next (trained) arm.

The old controllability checkpoint itself was not saved and is not available
locally; re-training it is out of scope for this round.

Usage:
    python -X utf8 model_smoke.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
_stub = Path(tempfile.mkdtemp()) / "sklearn"
_stub.mkdir()
(_stub / "__init__.py").write_text("")
(_stub / "metrics.py").write_text("def roc_curve(*a, **k):\n    raise RuntimeError('stub')\n")
sys.path.insert(0, str(_stub.parent))

import torch  # noqa: E402
from transformers import T5ForConditionalGeneration, T5Tokenizer  # noqa: E402

HERE = Path(__file__).resolve().parent
RUN = HERE / "runs" / "r1"
MODEL = Path("D:/others/Jity/.local/world-components-worktree/experiments/"
             "world-components/assets/randeng-t5-77m")
EXPECTED_MODEL_SHA = "5cdc572109cf25914b43fede20a6949b5fbf50b3a091a9c445fac60059bf5557"
MAX_NEW = 128

sys.path.insert(0, str(HERE))
import text_conformance  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    weight = MODEL / "model.safetensors"
    actual = sha256(weight)
    if actual != EXPECTED_MODEL_SHA:
        print(f"MODEL HASH MISMATCH: {actual} != {EXPECTED_MODEL_SHA}")
        return 1

    sources = {s["sourceId"]: s for s in json.loads(
        (HERE / "freeze/sources.json").read_text(encoding="utf-8"))["sources"]}
    plans = [json.loads(l) for l in (HERE / "freeze/plans-v1.jsonl").read_text(encoding="utf-8").splitlines()]
    chosen = [p for p in plans if p["sourceId"] in ("fixture-r1", "fixture-r2")]
    inputs = {}
    for line in (RUN / "downstream-inputs.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        inputs[(row["sourceId"], row["planId"])] = row

    tok = T5Tokenizer.from_pretrained(str(MODEL), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(MODEL), torch_dtype=torch.float32)
    model.to("cpu").eval()

    rows = []
    for p in chosen:
        src = sources[p["sourceId"]]
        facts = [f for f in src["facts"] if f["factId"] in p["factsUsed"]]
        prompt = inputs[(p["sourceId"], p["planId"])]["prompt"]
        x = tok(prompt, return_tensors="pt", truncation=True, max_length=512)
        t0 = time.perf_counter()
        with torch.no_grad():
            out = model.generate(**x, max_new_tokens=MAX_NEW, num_beams=1, do_sample=False,
                                 eos_token_id=1, pad_token_id=0)
        elapsed = time.perf_counter() - t0
        text = tok.decode(out[0], skip_special_tokens=True).strip()
        new_tokens = int(out.shape[1] - 1)
        stop = "eos" if int(out[0][-1]) == 1 else "length"
        verdict = text_conformance.check_text(facts, p["authorizedEdges"], p["plan"], text)
        rows.append({
            "sourceId": p["sourceId"],
            "planId": p["planId"],
            "shape": p["shape"],
            "promptSha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "output": text,
            "newTokens": new_tokens,
            "stop": stop,
            "seconds": round(elapsed, 3),
            "conformanceOk": verdict["ok"],
            "violations": [v["code"] for v in verdict["violations"]],
            "checks": verdict["checks"],
        })

    record = {
        "created": datetime.now(timezone.utc).isoformat(),
        "arm": "frozen base control (never trained on plan blocks)",
        "notTheMissingArm": ("the old controllability checkpoint was not saved; this base arm is a harness "
                             "control, not evidence about whether a plan-trained model can follow plans"),
        "model": {
            "path": str(MODEL),
            "modelSha256": actual,
            "base": "Randeng-T5-77M-MultiTask-Chinese",
            "device": "cpu",
            "dtype": "float32",
            "decode": "greedy, num_beams=1, max_new_tokens=128",
        },
        "rows": rows,
    }
    (RUN / "model-smoke.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (RUN / "model-smoke.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"wrote {RUN/'model-smoke.json'}")
    for r in rows:
        print(r["sourceId"], r["planId"], r["shape"], "conformance=", r["conformanceOk"],
              "stop=", r["stop"], "tokens=", r["newTokens"], "sec=", r["seconds"])
        print("  ", r["output"][:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

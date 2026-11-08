"""c9 offline half: run the same frozen fp32 graphs through ORT-python with
the same greedy loop the browser uses, on the same baked input ids, and keep
the outputs as the comparison target for the browser run.

Why a fresh run instead of trusting the stored `referenceIds`: the browser
gate is "browser == offline on identical input", so both sides must be
produced by the same loop shape on the same bytes in this session. The stored
ids are still compared, as a regression check on the fixtures.

Usage:
  D:/software/Anaconda/python.exe offline_reference.py [--out runs/offline-reference.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import statistics
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[6]
WT = HERE.parents[3]
GRAPH_DIR = REPO / ".local" / "world-components-worktree" / "experiments" / \
    "world-components" / "assets" / "n4-onnx" / "r3-direction"
GRAPH_DIR_INT8 = REPO / ".local" / "world-components-worktree" / "experiments" /     "world-components" / "assets" / "n4-onnx" / "r3-direction-int8"
CKPT = REPO / ".local" / "world-components-worktree" / "experiments" / \
    "world-components" / "assets" / "n4-finetune" / "r3-direction"
FIXTURE = WT / "experiments" / "world-components" / "browser_probe" / "probe_inputs.json"

MAX_NEW_TOKENS = 64


def greedy(enc_sess, dec_sess, input_ids, attention_mask, eos_id, pad_id,
           heads, d_kv):
    """Mirror of the browser loop: start from a zero-length self+cross cache,
    feed one token per step, stop on eos, never pad."""
    import numpy as np

    t_enc = time.perf_counter()
    enc = enc_sess.run(["encoder_hidden_states"], {
        "input_ids": input_ids.astype("int64"),
        "attention_mask": attention_mask.astype("int64"),
    })[0]
    enc_ms = (time.perf_counter() - t_enc) * 1000

    in_names = [i.name for i in dec_sess.get_inputs()][5:]
    past = {n: np.zeros((1, heads, 0, d_kv), dtype="float32") for n in in_names}
    dec_ids = np.array([[pad_id]], dtype="int64")
    out_ids, step_ms = [], []
    for step in range(MAX_NEW_TOKENS):
        feeds = {"decoder_input_ids": dec_ids,
                 "encoder_hidden_states": enc,
                 "encoder_attention_mask": attention_mask.astype("int64"),
                 "cache_position": np.array([step], dtype="int64"),
                 "self_mask": np.ones((1, step + 1), dtype="int64"),
                 **past}
        t0 = time.perf_counter()
        res = dec_sess.run(None, feeds)
        step_ms.append((time.perf_counter() - t0) * 1000)
        past = dict(zip(in_names, res[1:]))
        nxt = int(res[0][0, -1].argmax())
        if nxt == eos_id:
            break
        out_ids.append(nxt)
        dec_ids = np.array([[nxt]], dtype="int64")
    return out_ids, enc_ms, step_ms


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graphs", default="fp32", choices=["fp32", "int8"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    graph_dir = GRAPH_DIR_INT8 if args.graphs == "int8" else GRAPH_DIR
    out_path = pathlib.Path(args.out) if args.out else (
        HERE / "runs" / f"offline-reference{'-int8' if args.graphs == 'int8' else ''}.json")

    import onnxruntime as ort
    import sentencepiece as spm

    cfg = json.loads((CKPT / "config.json").read_text(encoding="utf-8"))
    sp = spm.SentencePieceProcessor(model_file=str(CKPT / "spiece.model"))
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]

    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    so.inter_op_num_threads = 1
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    providers = ["CPUExecutionProvider"]
    t0 = time.perf_counter()
    enc_sess = ort.InferenceSession(str(graph_dir / "encoder.onnx"), so, providers=providers)
    dec_sess = ort.InferenceSession(str(graph_dir / "decoder_kv.onnx"), so, providers=providers)
    load_ms = (time.perf_counter() - t0) * 1000

    out_cases = []
    all_match_stored = True
    for c in cases:
        import numpy as np
        ids = np.array([c["inputIds"]], dtype="int64")
        mask = np.ones_like(ids)
        gen, enc_ms, step_ms = greedy(enc_sess, dec_sess, ids, mask,
                                      cfg["eos_token_id"], cfg["pad_token_id"],
                                      cfg["num_heads"], cfg["d_kv"])
        match = gen == c["referenceIds"]
        all_match_stored = all_match_stored and match
        out_cases.append({
            "name": c["name"],
            "scope": c["scope"],
            "inputTokens": len(c["inputIds"]),
            "ids": gen,
            "text": sp.decode(gen),
            "generationMs": round(sum(step_ms), 1),
            "encoderMs": round(enc_ms, 1),
            "steps": len(step_ms),
            "meanStepMs": round(statistics.fmean(step_ms), 1) if step_ms else None,
            "idsSha256": hashlib.sha256(",".join(map(str, gen)).encode()).hexdigest(),
            "matchStoredReference": match,
        })

    record = {
        "purpose": "c9 offline reference: ORT-python greedy on the baked ids, "
                   "same graphs and loop shape as the browser adapter "
                   f"({args.graphs} graphs)",
        "environment": {
            "python": sys.version.split()[0],
            "onnxruntime": ort.__version__,
            "device": "CPUExecutionProvider, intra/inter threads = 1",
            "graphSet": args.graphs,
            "graphs": {
                "encoder.onnx": hashlib.sha256((graph_dir / "encoder.onnx").read_bytes()).hexdigest(),
                "decoder_kv.onnx": hashlib.sha256((graph_dir / "decoder_kv.onnx").read_bytes()).hexdigest(),
            },
        },
        "decodeParams": {"strategy": "greedy", "max_new_tokens": MAX_NEW_TOKENS,
                         "eos_token_id": cfg["eos_token_id"],
                         "pad_token_id": cfg["pad_token_id"],
                         "num_heads": cfg["num_heads"], "d_kv": cfg["d_kv"]},
        "sessionLoadMs": round(load_ms, 1),
        "cases": out_cases,
        # the stored referenceIds were produced with the fp32 graphs, so only
        # that set is expected to reproduce them
        "allMatchStoredReference": all_match_stored,
        "matchStoredReferenceExpected": args.graphs == "fp32",
    }
    out = out_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print("wrote", out, "graphs:", args.graphs)
    for c in out_cases:
        print(f"{c['name']:16s} steps={c['steps']:2d} "
              f"enc={c['encoderMs']:7.1f}ms gen={c['generationMs']:7.1f}ms "
              f"stored={c['matchStoredReference']} | {c['text'][:40]}")

    # Exit status answers "did this reference run produce a usable result",
    # not "does it equal the fp32 fixture". The stored referenceIds come from
    # the fp32 graphs, so int8 is EXPECTED to differ on some cases; failing
    # the process for that would make an automated check read a normal int8
    # run as a crash. Same-graph agreement is checked by compare.py against
    # this file, not here.
    complete = (
        len(out_cases) == len(cases)
        and all(c["steps"] > 0 for c in out_cases)
        and all(c["ids"] for c in out_cases)
    )
    expected_stored_match = args.graphs == "fp32"
    stored_ok = all_match_stored if expected_stored_match else True
    ok = complete and stored_ok
    if not complete:
        print("FAIL: incomplete reference (missing cases or empty ids)")
    if expected_stored_match and not all_match_stored:
        print("FAIL: fp32 reference does not reproduce the stored fixture ids")
    if not expected_stored_match and not all_match_stored:
        print(f"note: int8 differs from the stored fp32 ids on "
              f"{sum(1 for c in out_cases if not c['matchStoredReference'])}/"
              f"{len(out_cases)} case(s) - expected for a quantised graph set")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

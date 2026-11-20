"""Step 1 验证：u240 权重身份、运行环境、旧输入模板兼容性。

只读：共享源码（fact_contract / sequence_policy）、历史单元输入、权重文件。
只写：本目录下 step1/ 产物。

用法（仓库根，使用带 torch 的解释器）：
  /d/software/Anaconda/python.exe -X utf8 \
    experiments/world-components/parallel/scene_expression/step1_verify.py
"""
import hashlib
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]                      # 本工作树的仓库根
DEV = ROOT / "experiments/world-components/n4_narrative_dev"
OUT = HERE / "step1"


def main_worktree():
    """权重放在主工作树 .local/models；用 git 公共目录定位，不假设当前工作树有副本。"""
    import subprocess
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    return pathlib.Path(common).parent


MAIN = main_worktree()
MODEL_DIR = MAIN / ".local/models"
WEIGHTS = MODEL_DIR / "u240-model.safetensors"
EXPECT_SIZE = 309783976
EXPECT_SHA = "ab8a98264ee6b4f83eba17d624d7b92b23522c8eacef07d07a5be960e390184a"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def record():
    out = {"step": "1", "startedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    # --- 1. 权重身份 ---
    files = {}
    for p in [WEIGHTS, MODEL_DIR / "model.safetensors",
              MODEL_DIR / "config.json", MODEL_DIR / "spiece.model"]:
        if not p.exists():
            raise SystemExit(f"缺少文件: {p}")
        files[p.name] = {"path": str(p.relative_to(MAIN)),
                         "bytes": p.stat().st_size,
                         "sha256": sha256(p)}
    w = files[WEIGHTS.name]
    out["weights"] = {"files": files,
                      "expectedBytes": EXPECT_SIZE, "expectedSha256": EXPECT_SHA,
                      "match": w["bytes"] == EXPECT_SIZE and w["sha256"] == EXPECT_SHA}
    if not out["weights"]["match"]:
        raise SystemExit("u240 权重大小或 SHA-256 不匹配，停止")

    config = json.loads((MODEL_DIR / "config.json").read_text(encoding="utf-8"))
    out["config"] = {k: config.get(k) for k in
                     ["architectures", "model_type", "d_model", "d_ff",
                      "num_layers", "num_decoder_layers", "num_heads",
                      "vocab_size", "torch_dtype"]}

    # --- 2. 运行环境 ---
    import sentencepiece
    import torch
    import transformers
    out["env"] = {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "sentencepiece": sentencepiece.__version__,
        "device": "cpu",
        "torchThreads": torch.get_num_threads(),
        "cudaAvailable": bool(torch.cuda.is_available()),
    }

    # --- 3. 加载（按文件显式载入，避免目录里的重名权重被误选） ---
    from safetensors.torch import load_file
    from transformers import T5Config, T5ForConditionalGeneration, T5Tokenizer

    tok_started = time.perf_counter()
    tokenizer = T5Tokenizer.from_pretrained(str(MODEL_DIR), legacy=False,
                                            local_files_only=True)
    tok_seconds = time.perf_counter() - tok_started

    load_started = time.perf_counter()
    model = T5ForConditionalGeneration(T5Config(**config))
    state = load_file(str(WEIGHTS))
    # 权重文件是 HF safetensors 去重后的结果：encoder/decoder.embed_tokens 是
    # shared.weight 的别名，存盘时被丢掉，因此 strict=False，但只允许缺少这两个键。
    result = model.load_state_dict(state, strict=False)
    missing, unexpected = set(result.missing_keys), set(result.unexpected_keys)
    alias_ok = (model.encoder.embed_tokens.weight.data_ptr()
                == model.shared.weight.data_ptr()
                == model.decoder.embed_tokens.weight.data_ptr())
    model.eval()
    load_seconds = time.perf_counter() - load_started
    params = sum(p.numel() for p in model.parameters())
    out["load"] = {"tokenizerSeconds": round(tok_seconds, 3),
                   "modelSeconds": round(load_seconds, 3),
                   "parameters": params,
                   "vocab": len(tokenizer),
                   "missingKeys": sorted(missing),
                   "unexpectedKeys": sorted(unexpected),
                   "embedTiedToShared": alias_ok,
                   "status": "ok" if (missing == {"encoder.embed_tokens.weight",
                                                "decoder.embed_tokens.weight"}
                                       and not unexpected and alias_ok) else "mismatch"}
    if out["load"]["status"] != "ok":
        raise SystemExit(f"权重加载异常: {out['load']}")

    # --- 4. 旧输入模板兼容性：历史单元输入 ---
    sys.path.insert(0, str(DEV))
    from sequence_policy import generate_greedy  # noqa: E402

    units_path = DEV / "dev-units-v1.jsonl"
    units = [json.loads(line) for line in
             units_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    picked = [u for u in units if u["kind"] in
              ("moved", "appearance_changed", "sanity_changed")][:3]

    rows = []
    for u in picked:
        enc = tokenizer(u["input"], return_tensors="pt", truncation=False)
        n_tok = int(enc["input_ids"].shape[1])
        roundtrip = tokenizer.decode(enc["input_ids"][0], skip_special_tokens=True)

        started = time.perf_counter()
        ids, meta = generate_greedy(model, enc, timeout_seconds=60.0)
        elapsed = time.perf_counter() - started
        text = tokenizer.decode(ids[0], skip_special_tokens=True)
        rows.append({"unitId": u["id"], "kind": u["kind"],
                     "inputTokens": n_tok,
                     "roundtripEqual": roundtrip.strip() == u["input"].strip(),
                     "output": text, "seconds": round(elapsed, 3),
                     "reason": meta.get("reason") if isinstance(meta, dict) else str(meta)})

    # 同一输入重跑一次，确认贪心可复现
    enc = tokenizer(picked[0]["input"], return_tensors="pt", truncation=False)
    ids2, _ = generate_greedy(model, enc, timeout_seconds=60.0)
    rows[0]["reproduced"] = (tokenizer.decode(ids2[0], skip_special_tokens=True)
                             == rows[0]["output"])

    out["oldTemplate"] = {
        "template": "fact_contract.build_unit_input（短句任务/地点/地点可见/场景/视角/事实/方向/要求/短句）",
        "unitsFile": str(units_path.relative_to(ROOT)),
        "unitsFileSha256": sha256(units_path),
        "trainMaxInput": 160,
        "rows": rows,
    }

    out["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "step1-verify.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\n保存: {dst}")


if __name__ == "__main__":
    record()

# Randeng-T5-77M-MultiTask-Chinese offline smoke (deliverable 3 precondition).
#
# Purpose: gate-1 evidence for the plan table's two-step generation route —
# "offline loadable + tokenizer works + generates Chinese". This is a smoke,
# NOT a quality evaluation: quality gates run on the isolated dev corpus per
# design/world-engine-reports/components/README.md. Probes below are written
# new for this smoke (2026-10-29) and do not appear in any B-line narration /
# labeler corpus, calibration set, or archived sample (hv-*/nv-*/ns-* etc.).
#
# Model: IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese via hf-mirror resolve
# (files hashed into the report; param count computed from loaded weights to
# check the official 77,440,384 figure). Loaded as-is — the card's +100
# extra-token resize belongs to the finetune recipe, not this smoke.
#
# Usage: python experiments/world-components/randeng_smoke.py
# Output: artifacts/world-components/randeng-smoke.json

import hashlib
import importlib.machinery
import json
import pathlib
import sys
import time
import types

# base 环境的 pyarrow/h5py 与 numpy 2 二进制不匹配（import 即崩），与
# train-action-classifier.py 同源处理：进程内桩顶住 import，不动用户环境。
try:
    import pyarrow  # noqa: F401
except Exception:
    stub = types.ModuleType("pyarrow")
    stub.__version__ = "16.1.0"
    stub.__path__ = []
    sys.modules["pyarrow"] = stub
tf_stub = types.ModuleType("tensorflow")
tf_stub.__spec__ = importlib.machinery.ModuleSpec("tensorflow", None)
tf_stub.__path__ = []
sys.modules.setdefault("tensorflow", tf_stub)

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
MODEL_DIR = HERE / "assets" / "randeng-t5-77m"
REPORT_PATH = HERE.parent.parent / "artifacts" / "world-components" / "randeng-smoke.json"

# 探针句全部为本冒烟新写（2026-10-29），不属于任何既有语料；只记录行为，
# 不在此处判定质量。
PROBES = [
    {
        "name": "multitask-template-sentiment",
        "note": "模型卡风格的多任务模板探针：检查模板跟随行为",
        "input": "情感分析任务：【这间图书馆的藏书非常丰富。】这篇文章的情感态度是什么？正面/负面",
    },
    {
        "name": "narration-freeform",
        "note": "自由格式成句探针：一段自然语言变化描述",
        "input": "用一句中文叙述以下变化：学生A从大厅走到了走廊。时间过去了约三十分钟。",
    },
    {
        "name": "narration-template",
        "note": "结构化模板成句探针：位置事实＋时间",
        "input": "叙事生成任务：【位置：学生A 大厅→走廊】【时间：约30分钟】请用一句中文叙述这一变化。",
    },
    {
        "name": "narration-empty-point",
        "note": "空点探针：只有时间、无实体变化（对应叙事子步的时间/空点难点）",
        "input": "叙事生成任务：【时间：约30分钟】【变化：没有新的变化】请用一句中文叙述。",
    },
]

MAX_NEW_TOKENS = 64


def sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    report = {
        "purpose": "offline loadability smoke (not a quality gate)",
        "model": {
            "hfId": "IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese",
            "source": "https://hf-mirror.com/IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese",
            "localDir": str(MODEL_DIR),
            "files": {},
        },
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "device": "cpu",
        },
        "load": {},
        "probes": [],
        "disclaimers": [
            "probes are newly written for this smoke, not from any existing corpus",
            "no quality verdict is issued here; deliverable 3 quality gates use the isolated dev set",
            "card recipe resizes embeddings with 100 extra tokens; this smoke loads as-is",
        ],
    }

    import sentencepiece  # noqa: F401  (recorded only after install verified)

    report["environment"]["sentencepiece"] = sentencepiece.__version__
    import transformers

    report["environment"]["transformers"] = transformers.__version__

    for f in sorted(MODEL_DIR.iterdir()):
        report["model"]["files"][f.name] = {
            "bytes": f.stat().st_size,
            "sha256": sha256_of(f),
        }

    t0 = time.perf_counter()
    tokenizer = T5Tokenizer(vocab_file=str(MODEL_DIR / "spiece.model"))
    model = T5ForConditionalGeneration.from_pretrained(str(MODEL_DIR), torch_dtype=torch.float32)
    model.eval()
    load_s = time.perf_counter() - t0
    param_count = sum(p.numel() for p in model.parameters())
    report["load"] = {
        "seconds": round(load_s, 2),
        "paramCount": param_count,
        "officialClaim": 77440384,
        "paramCountMatches": param_count == 77440384,
    }

    for probe in PROBES:
        inputs = tokenizer(probe["input"], return_tensors="pt")
        t0 = time.perf_counter()
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                num_beams=1,
                do_sample=False,
            )
        wall_s = time.perf_counter() - t0
        text = tokenizer.decode(output[0], skip_special_tokens=True)
        report["probes"].append(
            {
                "name": probe["name"],
                "note": probe["note"],
                "input": probe["input"],
                "inputTokens": int(inputs["input_ids"].shape[1]),
                "output": text,
                "outputTokens": int(output.shape[1]),
                "wallSeconds": round(wall_s, 3),
            }
        )
        print(f"[{probe['name']}] {wall_s:.2f}s -> {text}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report -> {REPORT_PATH}")


if __name__ == "__main__":
    main()

# Randeng-T5-77M-MultiTask-Chinese offline smoke (deliverable 3 precondition).
#
# Purpose: gate-1 evidence for the plan table's two-step generation route —
# "offline loadable + tokenizer works + generates Chinese". This is a smoke,
# NOT a quality evaluation: quality gates run on the isolated dev corpus per
# design/world-engine-reports/components/README.md.
#
# DATA PROVENANCE (corrected 2026-10-29 after review; r1 report ed493e8
# wrongly claimed all probes were newly written and disjoint from B corpora):
# - narration-freeform input reuses the nv-cont-1 forbidden-string core
#   「学生A从大厅走到了走廊」 (narration-eval-samples.ts:136, minus the
#   parenthetical note) and inverts nv-move-1's mechanical direction; cast
#   name 学生A is from the shared school cast (b3-samples.ts:34 etc.).
# - narration-template input is the same entity pair 学生A 走廊→大厅
#   inverted — derived from nv-move-1's mechanical/forbidden, same family.
# - narration-empty-point reuses the phrase 「没有新的变化」 from B's empty-
#   point template sentence (committed-narration template work), though the
#   duration value 约30分钟 hits no archived sample text.
# - multitask-template-sentiment adapts the official model-card example and
#   has no string-level overlap with B corpora.
# Per README isolation rules these are registered derivation examples, NOT
# new dev samples; the smoke therefore never feeds model selection. If this
# script is ever reused for a quality evaluation, the derived probes MUST be
# replaced first (build-corpus tooling will exclude nv-*/hv-*/ns-* forbidden
# variants at string level, per the same review).
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

# 探针出处见文件头 DATA PROVENANCE（复核轮修正）；只记录行为，不在此处
# 判定质量，也不用于选型。
PROBES = [
    {
        "name": "multitask-template-sentiment",
        "note": "模型卡风格的多任务模板探针：检查模板跟随行为",
        "provenance": "官方模型卡示例改写；与 B 语料无字符串级交集",
        "input": "情感分析任务：【这间图书馆的藏书非常丰富。】这篇文章的情感态度是什么？正面/负面",
    },
    {
        "name": "narration-freeform",
        "note": "自由格式成句探针：一段自然语言变化描述",
        "provenance": "B 派生例：nv-cont-1 forbidden 串剥注记＋nv-move-1 方向反转；cast 名=共享学校名册",
        "input": "用一句中文叙述以下变化：学生A从大厅走到了走廊。时间过去了约三十分钟。",
    },
    {
        "name": "narration-template",
        "note": "结构化模板成句探针：位置事实＋时间",
        "provenance": "B 派生例：nv-move-1 实体对（学生A 走廊/大厅）反向＋forbidden 同族",
        "input": "叙事生成任务：【位置：学生A 大厅→走廊】【时间：约30分钟】请用一句中文叙述这一变化。",
    },
    {
        "name": "narration-empty-point",
        "note": "空点探针：只有时间、无实体变化（对应叙事子步的时间/空点难点）",
        "provenance": "B 派生例：「没有新的变化」=B 模板空点固定句式短语；时长值「约30分钟」未命中归档样本文本",
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
        "decodeConfig": {
            "maxNewTokens": MAX_NEW_TOKENS,
            "numBeams": 1,
            "doSample": False,
        },
        "tokenizerConfig": {
            "class": "T5Tokenizer(vocab_file=spiece.model)",
            "legacy": "transformers default (legacy behavior warning observed on 4.57.3); explicit pin required before finetune comparisons",
        },
        "probes": [],
        "disclaimers": [
            "provenance per-probe in the probes list; three of four are registered B-derivation examples (see script header)",
            "no quality verdict is issued here; deliverable 3 quality gates use the isolated dev set",
            "card recipe resizes embeddings with 100 extra tokens; this smoke loads as-is",
            "timings cover 4/19/8/8 output tokens (r2 measured); compare against Qwen only at matched token counts",
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
                "provenance": probe["provenance"],
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

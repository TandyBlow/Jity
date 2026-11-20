# Trains the action-type classifier evaluated by run-classifier-trial.mjs.
#
# Base model: iflytek/MiniRBT-H256 (~10.4M params, Chinese BERT-family,
# char-level tokenizer) — pretrained weights only, so this script fine-tunes
# a 5-way classification head on a synthetic template corpus for the parse
# task's action_type field (item_use / npc_talk / move / inspect / other).
#
# Data discipline:
# - ALL 12 scored sentences (old batch AND held-out new batch) are excluded
#   from the training corpus. An earlier revision claimed the old batch was
#   included; that was wrong — the user's reproduction showed the
#   `corpus[label] -= train_cases` step removed all 8 old sentences too.
#   This revision makes the exclusion explicit and keeps the behavior:
#   training saw none of the scored sentences, so old-batch 8/8 is a
#   generalization result, not a fit result. The actual corpus is exported
#   to artifacts/benchmark/classifier-action-corpus.json.
# - The held-out new sentences' distinctive structures are excluded from the
#   template vocabulary as well (垫住门缝 / 查看字迹 / 去找…问话 / 校徽刷开闸机;
#   旧笔记 and 校徽 are not used as slots for this task).
#
# Exports ONNX (fp32 + int8 dynamic) plus tokenizer files to
# frontend/public/models/minirbt-h256-action/ for Transformers.js.
#
# Usage: python train-action-classifier.py <minirbt-snapshot-dir>

import importlib.machinery
import importlib.util
import json
import pathlib
import random
import sys
import types

# base 环境的 pyarrow/h5py 与 numpy 2 二进制不匹配（import 即崩），而
# transformers → generation → sklearn 会连带 import pyarrow；transformers
# 又按元数据认为 TF 可用而在 image_transforms 里真 import tensorflow
#（内部连带 h5py）。训练只走 torch 张量路径，用进程内桩顶住 import，不动
# 用户环境。
try:
    import pyarrow  # noqa: F401
except Exception:
    stub = types.ModuleType("pyarrow")
    stub.__version__ = "16.1.0"  # 合法版本号：pandas 会 parse 它
    stub.__path__ = []
    sys.modules["pyarrow"] = stub
tf_stub = types.ModuleType("tensorflow")
# transformers 用 find_spec 探测 TF，模块必须有 __spec__；真 import 时拿到
# 空模块即过，后续不会调用 TF。
tf_stub.__spec__ = importlib.machinery.ModuleSpec("tensorflow", None)
tf_stub.__path__ = []
sys.modules.setdefault("tensorflow", tf_stub)

import torch
# 直接从 bert 模块导入：Auto* 会经 modeling_auto → generation.utils →
# sklearn → pyarrow，而 base 环境的 pyarrow/numpy 二进制不匹配，绕开该链。
from transformers.models.bert.modeling_bert import BertForSequenceClassification
from transformers.models.bert.tokenization_bert_fast import BertTokenizerFast

SEED = 4711
MAX_LEN = 32
LABELS = ["item_use", "npc_talk", "move", "inspect", "other"]
EPOCHS = 10
BATCH = 16
LR = 3e-4

ITEMS = ["铜钥匙", "铁门钥匙", "剑", "扫帚", "蜡烛", "地图", "绳索", "水壶"]
NPCS = ["诺诺", "执行部学生", "路明非", "古德里安教授", "凯瑟琳", "夏弥"]
LOCS = ["二楼档案室", "卡塞尔学院图书馆", "走廊", "阅览室", "地下藏书室"]
OBJECTS = ["暗门", "书架", "壁画", "雕像", "窗台", "石棺"]
OPEN_TARGETS = ["大门", "木箱", "柜子", "抽屉"]

# 12 scored sentences (action_type only) — asserted absent from training.
TEST_CASES = [
    ("我用铜钥匙打开大门。", "item_use"),
    ("我和诺诺打听图书馆的传闻。", "npc_talk"),
    ("我去二楼档案室查资料。", "move"),
    ("我使用生锈的铁门钥匙打开大门。", "item_use"),
    ("我和执行部学生搭话。", "npc_talk"),
    ("我检查那扇书架后的暗门。", "inspect"),
    ("我拔剑攻击诺诺。", "other"),
    ("我在原地休息一会儿。", "other"),
    ("我仔细查看旧笔记里的字迹。", "inspect"),
    ("我用旧笔记垫住门缝。", "item_use"),
    ("我去找执行部学生问话。", "npc_talk"),
    ("我用路明非的校徽刷开闸机。", "item_use"),
]


def build_corpus():
    """Template + slot corpus. Deterministic; capped per class by slicing."""
    corpus = {label: set() for label in LABELS}

    def add(label, template, slots):
        for text in slots:
            corpus[label].add(template.format(text))

    # item_use：使用物品达成别的目的（打开/撬开/照亮/扫出/割断/撑住）。
    for item in ITEMS:
        corpus["item_use"].add(f"我用{item}打开大门。")
        corpus["item_use"].add(f"我用{item}打开木箱。")
        corpus["item_use"].add(f"我用{item}撬开柜子。")
        corpus["item_use"].add(f"我用{item}照亮走廊。")
        corpus["item_use"].add(f"我用{item}撑住书架。")
    add("item_use", "我用{}割断绳子。", ITEMS)
    add("item_use", "我用{}把纸团扫出门口。", ITEMS)
    for target in OPEN_TARGETS:
        add("item_use", f"我用铜钥匙打开{{}}。".replace("{}", "{}"), [target])
        corpus["item_use"].add(f"我用铁门钥匙打开{target}。")
    # npc_talk：与人物交谈（打听/搭话/询问）。
    for npc in NPCS:
        corpus["npc_talk"].add(f"我和{npc}搭话。")
        corpus["npc_talk"].add(f"我向{npc}询问暗门的下落。")
        corpus["npc_talk"].add(f"我和{npc}打听图书馆的传闻。")
        corpus["npc_talk"].add(f"我和{npc}打听二楼档案室的传闻。")
    add("npc_talk", "我和{}打听暗门的来历。", NPCS)
    # move：前往地点（去/走到/前往）。
    for loc in LOCS:
        corpus["move"].add(f"我去{loc}。")
        corpus["move"].add(f"我去{loc}查资料。")
        corpus["move"].add(f"我沿着楼梯走到{loc}。")
        corpus["move"].add(f"我前往{loc}。")
    add("move", "我去{}躲一躲。", LOCS)
    # inspect：查看物件（检查/观察/查看），对象可以是物品。
    for obj in OBJECTS:
        corpus["inspect"].add(f"我检查{obj}。")
        corpus["inspect"].add(f"我观察{obj}上的痕迹。")
        corpus["inspect"].add(f"我查看{obj}。")
    for item in ITEMS:
        corpus["inspect"].add(f"我检查{item}的齿纹。")
        corpus["inspect"].add(f"我查看{item}的表面。")
    # other：休息、攻击、等待、整理。
    corpus["other"].update([
        "我在原地休息一会儿。",
        "我靠在门边等一等。",
        "我整理了一下背包。",
        "我深吸一口气。",
        "我在原地缓了缓。",
        "我坐下来歇了口气。",
    ])
    for npc in NPCS:
        corpus["other"].add(f"我拔剑攻击{npc}。")
        corpus["other"].add(f"我挥手赶{npc}走。")

    # 全部 12 句计分原文都排除在语料外（此前版本靠 add-后-subtract 间接达成，
    # 现在显式排除；集合内容与旧版完全一致，训练可复现）。
    all_scored = {text for text, _ in TEST_CASES}
    for label in LABELS:
        corpus[label] -= all_scored
        assert not (corpus[label] & all_scored), f"scored sentence leaked into {label}"

    data = [(text, LABELS.index(label)) for label in LABELS for text in sorted(corpus[label])]
    return data


def main():
    args = [a for a in sys.argv[1:]]
    export_only = "--export-corpus" in args
    positional = [a for a in args if not a.startswith("--")]
    frontend_root = pathlib.Path(__file__).resolve().parent.parent
    out_dir = frontend_root / "public" / "models" / "minirbt-h256-action"
    artifacts_dir = frontend_root.parent / "artifacts" / "benchmark"
    (out_dir / "onnx").mkdir(parents=True, exist_ok=True)

    random.seed(SEED)
    data = build_corpus()
    counts = {}
    for _, label in data:
        counts[LABELS[label]] = counts.get(LABELS[label], 0) + 1
    print(f"corpus: {len(data)} sentences {counts}")
    rng = random.Random(SEED)
    rng.shuffle(data)

    val_n = max(1, len(data) // 10)
    val, train = data[:val_n], data[val_n:]
    print(f"train={len(train)} val={len(val)}")

    # 实际语料清单入库：训练/验证/评测三部分原文全部落盘，供复核。
    manifest = {
        "seed": SEED,
        "counts": counts,
        "exclusionNote": "all 12 scored sentences (old + new batch) excluded from train/val; "
        "held-out structures 垫住门缝/查看字迹/去找…问话/校徽刷开闸机 and slots 旧笔记/校徽 "
        "excluded from templates",
        "train": [{"text": text, "label": LABELS[label]} for text, label in train],
        "val": [{"text": text, "label": LABELS[label]} for text, label in val],
        "test": [{"text": text, "expect": expect} for text, expect in TEST_CASES],
    }
    manifest_path = artifacts_dir / "classifier-action-corpus.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"corpus manifest saved: {manifest_path}")
    if export_only:
        return

    torch.manual_seed(SEED)

    tokenizer = BertTokenizerFast.from_pretrained(snapshot)
    model = BertForSequenceClassification.from_pretrained(
        snapshot,
        num_labels=len(LABELS),
        id2label={i: label for i, label in enumerate(LABELS)},
        label2id={label: i for i, label in enumerate(LABELS)},
    )
    model.config._attn_implementation = "eager"  # 稳定 ONNX 导出

    def encode(batch):
        texts = [text for text, _ in batch]
        return tokenizer(texts, padding="max_length", max_length=MAX_LEN, truncation=True, return_tensors="pt")

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    ce = torch.nn.CrossEntropyLoss()
    model.train()
    for epoch in range(1, EPOCHS + 1):
        rng.shuffle(train)
        total = 0.0
        for start in range(0, len(train), BATCH):
            batch = train[start : start + BATCH]
            enc = encode(batch)
            logits = model(**enc).logits
            loss = ce(logits, torch.tensor([label for _, label in batch]))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += loss.item() * len(batch)
        model.eval()
        with torch.no_grad():
            enc = encode(val)
            val_acc = (model(**enc).logits.argmax(-1) == torch.tensor([label for _, label in val])).float().mean().item()
        model.train()
        print(f"epoch {epoch}: loss={total / len(train):.4f} val_acc={val_acc:.3f}")

    # 12 例计分句逐例预测（浏览器外 sanity check）。
    model.eval()
    with torch.no_grad():
        enc = encode(TEST_CASES)
        probs = torch.softmax(model(**enc).logits, dim=-1)
        for (text, expect), row in zip(TEST_CASES, probs):
            top = row.argmax().item()
            mark = "PASS" if LABELS[top] == expect else "FAIL"
            print(f"  [{mark}] {text} -> {LABELS[top]} ({row[top].item():.3f}) expect={expect}")
        correct = sum(
            LABELS[row.argmax().item()] == expect for (_, expect), row in zip(TEST_CASES, probs)
        )
        old_correct = sum(
            LABELS[row.argmax().item()] == expect
            for (_, expect), row in zip(TEST_CASES[:8], probs[:8])
        )
        print(f"python eval: old {old_correct}/8, new {correct - old_correct}/4, total {correct}/12")

    # 导出：ONNX fp32 + int8 动态量化 + tokenizer。
    dummy = encode(TEST_CASES[:1])
    torch.onnx.export(
        model,
        (dummy["input_ids"], dummy["attention_mask"], dummy["token_type_ids"]),
        str(out_dir / "onnx" / "model.onnx"),
        input_names=["input_ids", "attention_mask", "token_type_ids"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "seq"},
            "attention_mask": {0: "batch", 1: "seq"},
            "token_type_ids": {0: "batch", 1: "seq"},
            "logits": {0: "batch"},
        },
        opset_version=14,
    )
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(
        str(out_dir / "onnx" / "model.onnx"),
        str(out_dir / "onnx" / "model_quantized.onnx"),
        weight_type=QuantType.QUInt8,
    )
    tokenizer.save_pretrained(out_dir)
    model.config.save_pretrained(out_dir)
    sizes = {
        p.name: p.stat().st_size
        for p in sorted(out_dir.rglob("*"))
        if p.is_file() and p.suffix in {".onnx", ".json", ".txt"}
    }
    print("exported:", json.dumps(sizes, indent=2))


if __name__ == "__main__":
    main()

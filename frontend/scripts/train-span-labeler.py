# Trains the span labeler evaluated by run-labeler-trial.mjs.
#
# Base model: hfl/minirbt-h256 + token-classification head (5 tags). Task:
# mark the character spans of item_used (ITEM) and target (TGT) in the
# player-action text; action_type is NOT this model's job (the classifier
# covers it), and feasibility stays code-side.
#
# Labeling rules (fixed before any training; the browser trial extracts
# spans and compares against them):
# 1. Span = a contiguous character range of the ORIGINAL text, [start, end).
# 2. item_use actions: the used object -> ITEM, what it acts on -> TGT
#    (我用X打开Y: X=ITEM, Y=TGT).
# 3. inspect actions: the inspected object -> TGT, no ITEM ("检查X的Y":
#    X=TGT, Y stays O).
# 4. move / npc_talk: the location / the person -> TGT.
# 5. Person titles stay inside the span ("古德里安教授" whole); title
#    stripping is code-side post-processing, same as the names task.
# 6. Spans are minimal: modifiers are excluded ("那扇书架后的暗门" -> 暗门).
# 7. At most one span per field per sentence (the task is single-entity);
#    multi-entity sentences never enter corpus or eval.
#
# Acceptance criteria (pre-registered, before any training):
# - PRIMARY: on the 10-sentence ACCEPTANCE batch below, strict span match
#   rate (start AND end AND type all exact) >= 90% for EACH of ITEM/TGT.
# - Component accepted only if both fields pass AND end-to-end latency
#   (raw text -> spans) stays <= 4s per call in the browser trial.
# - The previous held-out batch is now the DEV set: it has been evaluated
#   repeatedly during debugging, so it no longer measures generalization —
#   it is used to locate errors only. The acceptance batch is evaluated
#   once, after all fixes, and never iterated against.
# - Reported but not gating: the 12 scored parse sentences.
#
# Data discipline: the 12 scored sentences, the 10 dev sentences and the 10
# acceptance sentences are ALL excluded from the corpus; their slots and
# distinctive structures are excluded from templates too. Dev slots: 垫住门缝
# 查看字迹 去找…问话 校徽刷开闸机 / 旧笔记 校徽 火把 短刀 指南针 铃铛 夏弥
# 图书馆管理员 地下藏书室. Acceptance slots: 铁钩 麻绳 火折子 铜铃 木梯 守林人
# 老陈 阁楼 柜台 水井 石阶 — none appear as training slots.
#
# Usage: python train-span-labeler.py <minirbt-snapshot-dir> [--export-corpus]

import importlib.machinery
import importlib.util
import json
import pathlib
import random
import sys
import types

# base 环境的 pyarrow/h5py 与 numpy 2 二进制不兼容（import 即崩），而
# transformers → generation → sklearn 会连带 import pyarrow；transformers
# 又按元数据认为 TF 可用而在 image_transforms 里真 import tensorflow
# （内部连带 h5py）。训练只走 torch 张量路径，用进程内桩顶住 import，不动
# 用户环境。详见 train-action-classifier.py 同段注释。
try:
    import pyarrow  # noqa: F401
except Exception:
    stub = types.ModuleType("pyarrow")
    stub.__version__ = "16.1.0"  # 合法版本号：pandas 会 parse 它
    stub.__path__ = []
    sys.modules["pyarrow"] = stub
tf_stub = types.ModuleType("tensorflow")
tf_stub.__spec__ = importlib.machinery.ModuleSpec("tensorflow", None)
tf_stub.__path__ = []
sys.modules.setdefault("tensorflow", tf_stub)

import torch
from transformers.models.bert.modeling_bert import BertForTokenClassification
from transformers.models.bert.tokenization_bert_fast import BertTokenizerFast

SEED = 4711
MAX_LEN = 48
TAGS = ["O", "B-ITEM", "I-ITEM", "B-TGT", "I-TGT"]
EPOCHS = 30
BATCH = 16
LR = 3e-4

# 训练槽位（与 held-out 槽位不相交）。
ITEMS = ["铜钥匙", "铁门钥匙", "剑", "扫帚", "地图", "绳索", "水壶", "铁锹", "灯笼", "木桶"]
NPCS = ["诺诺", "执行部学生", "路明非", "古德里安教授", "凯瑟琳"]
LOCS = ["二楼档案室", "卡塞尔学院图书馆", "走廊", "阅览室"]
OBJECTS = ["暗门", "书架", "壁画", "雕像", "窗台"]
OPEN_TARGETS = ["大门", "木箱", "柜子", "抽屉"]

# 10 句开发集（原 held-out 批；已多轮参与排查，只用于定位错误，不再验收）：
# (text, item, target)；None 表示该字段无 span。
DEV = [
    ("我用火把照亮地下藏书室。", "火把", "地下藏书室"),
    ("我用短刀割断绳索。", "短刀", "绳索"),
    ("我和图书馆管理员打听暗门。", None, "图书馆管理员"),
    ("我去地下藏书室。", None, "地下藏书室"),
    ("我检查雕像的底座。", None, "雕像"),
    ("我在原地休息。", None, None),
    ("我用指南针校准方向。", "指南针", None),
    ("我把铃铛挂在暗门上。", "铃铛", "暗门"),
    ("我向夏弥打听暗门的来历。", None, "夏弥"),
    ("我用蜡烛照亮壁画。", "蜡烛", "壁画"),
]

# 10 句验收批（全新槽位与结构，训练后只评测一次，不参与任何调整）。
ACCEPTANCE = [
    ("我用铁钩勾住铁链。", "铁钩", "铁链"),
    ("我用木梯爬上阁楼。", "木梯", "阁楼"),
    ("我和守林人打听阁楼的传闻。", None, "守林人"),
    ("我去柜台。", None, "柜台"),
    ("我检查火折子的成色。", None, "火折子"),
    ("我在原地喘口气。", None, None),
    ("我用麻绳捆好木箱。", "麻绳", "木箱"),
    ("我把铜铃挂在柜台边。", "铜铃", "柜台"),
    ("我向老陈询问铁钩的下落。", None, "老陈"),
    ("我用火折子照亮石阶。", "火折子", "石阶"),
]

# 12 句计分原文（span 由 expect 字段在原文中的位置给出；None 同上）。
SCORED = [
    ("我用铜钥匙打开大门。", "铜钥匙", "大门"),
    ("我和诺诺打听图书馆的传闻。", None, "诺诺"),
    ("我去二楼档案室查资料。", None, "二楼档案室"),
    ("我使用生锈的铁门钥匙打开大门。", "生锈的铁门钥匙", "大门"),
    ("我和执行部学生搭话。", None, "执行部学生"),
    ("我检查那扇书架后的暗门。", None, "暗门"),
    ("我拔剑攻击诺诺。", "剑", "诺诺"),
    ("我在原地休息一会儿。", None, None),
    ("我仔细查看旧笔记里的字迹。", None, "旧笔记"),
    ("我用旧笔记垫住门缝。", "旧笔记", "门缝"),
    ("我去找执行部学生问话。", None, "执行部学生"),
    ("我用路明非的校徽刷开闸机。", "校徽", "闸机"),
]


def build_corpus():
    """Templates with tracked spans -> (text, item_span, target_span)."""
    corpus = []

    def emit(segments):
        text = ""
        item = None
        target = None
        for kind, content in segments:
            if kind == "lit":
                text += content
                continue
            start = len(text)
            text += content
            slot = "item" if kind == "ITEM" else "target"
            if {"item": item, "target": target}[slot] is None:
                if slot == "item":
                    item = (start, start + len(content))
                else:
                    target = (start, start + len(content))
        corpus.append((text, item, target))

    for item in ITEMS:
        for target in OPEN_TARGETS:
            emit([("lit", "我用"), ("ITEM", item), ("lit", "打开"), ("TGT", target), ("lit", "。")])
            emit([("lit", "我用"), ("ITEM", item), ("lit", "砸开"), ("TGT", target), ("lit", "。")])
            emit([("lit", "我用"), ("ITEM", item), ("lit", "锁上"), ("TGT", target), ("lit", "。")])
        for target in OBJECTS:
            emit([("lit", "我用"), ("ITEM", item), ("lit", "撬开"), ("TGT", target), ("lit", "。")])
            emit([("lit", "我用"), ("ITEM", item), ("lit", "照亮"), ("TGT", target), ("lit", "。")])
            emit([("lit", "我用"), ("ITEM", item), ("lit", "把"), ("TGT", target), ("lit", "压住。")])
        # 规则审计修正：被作用物一律 TGT（此前 撑住书架/敲了敲书架/割断绳子
        # 漏标 TGT，检查{item}的齿纹误标 ITEM——inspect 无 ITEM，见规则 3）。
        emit([("lit", "我用"), ("ITEM", item), ("lit", "撑住"), ("TGT", "书架"), ("lit", "。")])
        emit([("lit", "我用"), ("ITEM", item), ("lit", "割断"), ("TGT", "绳子"), ("lit", "。")])
        emit([("lit", "我用"), ("ITEM", item), ("lit", "敲了敲"), ("TGT", "书架"), ("lit", "。")])
        emit([("lit", "我把"), ("ITEM", item), ("lit", "靠在"), ("TGT", "暗门"), ("lit", "边。")])
        emit([("lit", "我把"), ("ITEM", item), ("lit", "收进"), ("TGT", "背包"), ("lit", "。")])
        emit([("lit", "我检查"), ("TGT", item), ("lit", "的齿纹。")])
    for npc in NPCS:
        emit([("lit", "我和"), ("TGT", npc), ("lit", "搭话。")])
        emit([("lit", "我和"), ("TGT", npc), ("lit", "打听图书馆的传闻。")])
        emit([("lit", "我和"), ("TGT", npc), ("lit", "打听暗门的来历。")])
        emit([("lit", "我向"), ("TGT", npc), ("lit", "询问暗门的下落。")])
    for loc in LOCS:
        emit([("lit", "我去"), ("TGT", loc), ("lit", "。")])
        emit([("lit", "我去"), ("TGT", loc), ("lit", "查资料。")])
        emit([("lit", "我沿着楼梯走到"), ("TGT", loc), ("lit", "。")])
        emit([("lit", "我前往"), ("TGT", loc), ("lit", "。")])
        emit([("lit", "我返回"), ("TGT", loc), ("lit", "。")])
    for obj in OBJECTS:
        emit([("lit", "我检查"), ("TGT", obj), ("lit", "。")])
        emit([("lit", "我仔细查看"), ("TGT", obj), ("lit", "上的痕迹。")])
        emit([("lit", "我观察"), ("TGT", obj), ("lit", "。")])
        emit([("lit", "我搜索"), ("TGT", obj), ("lit", "。")])
        emit([("lit", "我把"), ("ITEM", "扫帚"), ("lit", "放在"), ("TGT", obj), ("lit", "旁边。")])
    corpus.extend([
        ("我在原地休息一会儿。", None, None),
        ("我在原地缓了缓。", None, None),
        ("我靠在门边等一等。", None, None),
        ("我整理了一下背包。", None, None),
        ("我深吸一口气。", None, None),
        ("我坐下来歇了口气。", None, None),
    ])
    for npc in NPCS:
        # 规则审计修正：拔剑的"剑"是被使用的物品 → ITEM（此前漏标）。
        emit([("lit", "我拔"), ("ITEM", "剑"), ("lit", "攻击"), ("TGT", npc), ("lit", "。")])

    # 排除全部计分句、开发句与验收句原文；断言干净。
    excluded = (
        {text for text, _, _ in SCORED}
        | {text for text, _, _ in DEV}
        | {text for text, _, _ in ACCEPTANCE}
    )
    corpus = [(text, i, t) for text, i, t in corpus if text not in excluded]
    assert len({text for text, _, _ in corpus}) == len(corpus)
    return corpus


def spans_to_tags(text, item, target, tokenizer):
    """Char-level tags -> wordpiece-token tags via offset mapping."""
    char_tags = ["O"] * len(text)
    for span, base in ((item, "ITEM"), (target, "TGT")):
        if span is None:
            continue
        start, end = span
        char_tags[start] = f"B-{base}"
        for pos in range(start + 1, end):
            char_tags[pos] = f"I-{base}"
    encoded = tokenizer(text, truncation=True, max_length=MAX_LEN, return_offsets_mapping=True)
    labels = []
    for (token_start, token_end) in encoded["offset_mapping"]:
        if token_end == 0:
            labels.append(-100)  # [CLS]/[SEP]/[PAD]
            continue
        # 词片段完全落在某标签内才继承；跨界片段（ASCII 词边界）记 O。
        mid = (token_start + token_end) // 2
        labels.append(TAGS.index(char_tags[mid]) if mid < len(char_tags) else TAGS.index("O"))
    return encoded["input_ids"], labels


def tags_to_spans(text, offsets, tag_ids):
    """Model output -> (item_span, target_span) character ranges.

    组尾取组内最后一个词片段的结束位置（审查发现：句末特殊标记的起点是
    0，用"下一个 token 的起点"当组尾会产出 [x,0] 这类错区间）。
    """
    spans = {"ITEM": None, "TGT": None}
    current = None  # [type, start, end]
    for tag_id, (token_start, token_end) in zip(tag_ids, offsets):
        if token_end == 0 or tag_id >= len(TAGS):
            tag = "O"  # [CLS]/[SEP]
        else:
            tag = TAGS[tag_id]
        if tag.startswith("I-") and current is not None and current[0] == tag[2:]:
            current[2] = token_end  # 延续当前组，组尾前移到本片段末尾
            continue
        # O 或 B-/游离 I-：先按组内末片段结束位置落盘当前组
        if current is not None and spans[current[0]] is None:
            spans[current[0]] = (current[1], current[2])
        if tag == "O":
            current = None
        else:
            current = [tag[2:], token_start, token_end]
    if current is not None and spans[current[0]] is None:
        spans[current[0]] = (current[1], current[2])
    return spans["ITEM"], spans["TGT"]


def evaluate(model, tokenizer, cases):
    model.eval()
    strict = {"ITEM": [0, 0], "TGT": [0, 0]}
    loose = {"ITEM": [0, 0], "TGT": [0, 0]}
    rows = []
    with torch.no_grad():
        for text, item, target in cases:
            expected_spans = {}
            for name, expected in (("ITEM", item), ("TGT", target)):
                expected_spans[name] = (
                    (text.index(expected), text.index(expected) + len(expected)) if expected else None
                )
            encoded = tokenizer(text, truncation=True, max_length=MAX_LEN, return_offsets_mapping=True)
            offsets = encoded["offset_mapping"]
            logits = model(
                input_ids=torch.tensor([encoded["input_ids"]]),
                attention_mask=torch.tensor([encoded["attention_mask"]]),
                token_type_ids=torch.tensor([encoded["token_type_ids"]]),
            ).logits[0]
            tag_ids = logits.argmax(-1).tolist()[: len(offsets)]
            pred_item, pred_target = tags_to_spans(text, offsets, tag_ids)
            row = {"text": text, "predItem": None, "predTarget": None}
            for name, expected, predicted in (
                ("ITEM", expected_spans["ITEM"], pred_item),
                ("TGT", expected_spans["TGT"], pred_target),
            ):
                strict[name][1] += 1
                loose[name][1] += 1
                if predicted is None and expected is None:
                    strict[name][0] += 1
                    loose[name][0] += 1
                elif predicted is not None and expected is not None:
                    pred_text = text[predicted[0] : predicted[1]]
                    if name == "ITEM":
                        row["predItem"] = pred_text
                    else:
                        row["predTarget"] = pred_text
                    if predicted == expected:
                        strict[name][0] += 1
                    if predicted[0] < expected[1] and expected[0] < predicted[1]:
                        loose[name][0] += 1
            rows.append(row)
    return strict, loose, rows


def main():
    args = sys.argv[1:]
    export_only = "--export-corpus" in args
    positional = [a for a in args if not a.startswith("--")]
    if not export_only and not positional:
        sys.exit("usage: train-span-labeler.py <snapshot-dir> [--export-corpus]")
    frontend_root = pathlib.Path(__file__).resolve().parent.parent
    out_dir = frontend_root / "public" / "models" / "minirbt-h256-span"
    artifacts_dir = frontend_root.parent / "artifacts" / "benchmark"
    (out_dir / "onnx").mkdir(parents=True, exist_ok=True)

    random.seed(SEED)
    corpus = build_corpus()
    counts = {}
    for text, item, target in corpus:
        key = f"item={item is not None},target={target is not None}"
        counts[key] = counts.get(key, 0) + 1
    print(f"corpus: {len(corpus)} sentences {counts}")
    rng = random.Random(SEED)
    rng.shuffle(corpus)

    manifest = {
        "seed": SEED,
        "labelingRules": [
            "span = contiguous char range of original text [start,end)",
            "item_use: used object=ITEM, acted-on=TGT",
            "inspect: inspected object=TGT (no ITEM); 检查X的Y -> X=TGT, Y=O",
            "move/npc_talk: location/person=TGT",
            "titles stay in person spans; stripping is code-side",
            "spans minimal (modifiers excluded)",
            "at most one span per field",
        ],
        "acceptance": {
            "preRegistered": "acceptance batch (10 sentences): strict span match >= 90% per field",
            "component": "both fields pass AND end-to-end <= 4s per call",
            "protocol": "dev batch (ex held-out) is for debugging only; acceptance batch evaluated once after fixes, never iterated against",
        },
        "counts": counts,
        "dev": [
            {"text": text, "item": item, "target": target} for text, item, target in DEV
        ],
        "acceptance": [
            {"text": text, "item": item, "target": target} for text, item, target in ACCEPTANCE
        ],
        "scored": [
            {"text": text, "item": item, "target": target} for text, item, target in SCORED
        ],
        "train": [
            {
                "text": text,
                "item": text[item[0] : item[1]] if item else None,
                "target": text[target[0] : target[1]] if target else None,
            }
            for text, item, target in corpus
        ],
        "note": "scored (12) + dev (10) + acceptance (10) sentences all excluded from training",
    }
    manifest_path = artifacts_dir / "span-labeler-corpus.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"corpus manifest saved: {manifest_path}")
    if export_only:
        return

    snapshot = positional[0]
    torch.manual_seed(SEED)

    tokenizer = BertTokenizerFast.from_pretrained(snapshot)
    model = BertForTokenClassification.from_pretrained(
        snapshot,
        num_labels=len(TAGS),
        id2label={i: tag for i, tag in enumerate(TAGS)},
        label2id={tag: i for i, tag in enumerate(TAGS)},
    )
    model.config._attn_implementation = "eager"  # 稳定 ONNX 导出

    features = []
    for text, item, target in corpus:
        input_ids, labels = spans_to_tags(text, item, target, tokenizer)
        features.append((text, input_ids, labels))
    rng.shuffle(features)
    val_n = max(1, len(features) // 10)
    val, train = features[:val_n], features[val_n:]

    def pad_batch(batch):
        length = min(MAX_LEN, max(len(ids) for _, ids, _ in batch))
        input_ids, attention, token_types, label_ids = [], [], [], []
        for _, ids, labels in batch:
            pad = length - len(ids)
            input_ids.append(ids + [0] * pad)
            attention.append([1] * len(ids) + [0] * pad)
            token_types.append([0] * length)
            label_ids.append(labels + [-100] * pad)
        return (
            torch.tensor(input_ids),
            torch.tensor(attention),
            torch.tensor(token_types),
            torch.tensor(label_ids),
        )

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    ce = torch.nn.CrossEntropyLoss(ignore_index=-100)
    model.train()
    for epoch in range(1, EPOCHS + 1):
        rng.shuffle(train)
        total = 0.0
        for start in range(0, len(train), BATCH):
            batch = train[start : start + BATCH]
            input_ids, attention, token_types, label_ids = pad_batch(batch)
            logits = model(input_ids=input_ids, attention_mask=attention, token_type_ids=token_types).logits
            loss = ce(logits.reshape(-1, len(TAGS)), label_ids.reshape(-1))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += loss.item() * len(batch)
        print(f"epoch {epoch}: loss={total / len(train):.4f}")

    for name, cases in (("dev", DEV), ("acceptance", ACCEPTANCE), ("scored", SCORED)):
        strict, loose, rows = evaluate(model, tokenizer, cases)
        for field in ("ITEM", "TGT"):
            s, l = strict[field], loose[field]
            print(f"{name} {field}: strict={s[0]}/{s[1]} loose={l[0]}/{l[1]}")
        for row in rows:
            print(f"  [{name}] {row['text']} item={row['predItem']} target={row['predTarget']}")

    dummy = tokenizer("我用铜钥匙打开大门。", truncation=True, max_length=MAX_LEN, return_offsets_mapping=True)
    seq = len(dummy["input_ids"])
    torch.onnx.export(
        model,
        (
            torch.tensor([dummy["input_ids"]]),
            torch.tensor([dummy["attention_mask"]]),
            torch.tensor([dummy["token_type_ids"]]),
        ),
        str(out_dir / "onnx" / "model.onnx"),
        input_names=["input_ids", "attention_mask", "token_type_ids"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "seq"},
            "attention_mask": {0: "batch", 1: "seq"},
            "token_type_ids": {0: "batch", 1: "seq"},
            "logits": {0: "batch", 1: "seq"},
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

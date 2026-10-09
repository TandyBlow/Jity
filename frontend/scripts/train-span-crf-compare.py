# CRF head vs plain classification head — paired training on the frozen
# span-labeler corpus (user-directed round, 2026-10-09).
#
# Rationale (user): constrained decoding repairs the OUTPUT FORM at inference;
# a linear-chain CRF learns tag transitions JOINTLY with per-token scores
# during training (Lample et al. 2016, https://aclanthology.org/N16-1030 —
# BiLSTM-CRF for NER). Worth testing, but NOT presumed to fix wrong-field
# picks or hallucinated spans: the report keeps per-field strict, whole-
# sentence strict, empty-field false positives and per-example flips side by
# side so boundary gains cannot hide hallucination growth.
#
# Protocol (as specified, everything else frozen):
# - Corpus, split, labeling rules, pretraining start
#   (artifacts/benchmark/minirbt-h256-snapshot) and training budget
#   (EPOCHS=30, BATCH=16, AdamW lr 3e-4 wd 0.01) identical to the labeler
#   round. The rebuilt split is ASSERTED identical to
#   span-labeler-corpus.json's train/validation before anything trains.
# - Three fixed train seeds [4711, 20261009, 31337]; under each seed the
#   plain head and the CRF head train PAIRED: same head-init stream, same
#   per-epoch batch order. Seed 4711 + plain head doubles as the pipeline
#   anchor: its epoch-shuffle rng continues the split rng exactly like
#   train-span-labeler.main(), so it should reproduce the frozen shipped
#   model's dev numbers (greedy 31/53, constrained 35/53) case-by-case;
#   the anchor comparison runs first and any drift is printed, not hidden.
# - Decodes: plain head -> greedy + whole-sentence constrained (as shipped);
#   CRF head -> Viterbi (its native decode). CPU only, seeded, deterministic.
# - The SHIPPED model stays frozen: training happens on in-memory copies;
#   nothing is exported or overwritten.
#
# Output: artifacts/benchmark/crf-compare-<ts>.json
# Usage: python scripts/train-span-crf-compare.py

import importlib.util
import json
import pathlib
import random
import sys
import time

import torch

sys_path = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("train_span_labeler", sys_path / "train-span-labeler.py")
tsl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tsl)

from transformers.models.bert.modeling_bert import BertForTokenClassification  # noqa: E402
from transformers.models.bert.tokenization_bert_fast import BertTokenizerFast  # noqa: E402

FRONTEND_ROOT = sys_path.parent
ARTIFACTS = FRONTEND_ROOT.parent / "artifacts" / "benchmark"
SNAPSHOT = ARTIFACTS / "minirbt-h256-snapshot"
MANIFEST_PATH = ARTIFACTS / "span-labeler-corpus.json"
# 锚点工件：双解码计时轮的浏览器报告（q8 臂，贪心+约束逐例）。
FROZEN_ANCHOR_PATH = ARTIFACTS / "labeler-trial-1791516015611-spans.json"
TRAIN_SEEDS = [4711, 20261009, 31337]
MODES = ("greedy", "constrained")


class LinearChainCRF(torch.nn.Module):
    """线性链 CRF（5 标签）：发射分来自 BERT，转移分与首尾转移可学习。

    数值口径：log-sum-exp 前向算法算 logZ，损失 = (logZ - 金标路径分)；
    解码为标准 Viterbi。训练与评测都在同一实例上。
    """

    def __init__(self, num_tags):
        super().__init__()
        self.transitions = torch.nn.Parameter(torch.zeros(num_tags, num_tags))  # [from, to]
        self.start_transitions = torch.nn.Parameter(torch.zeros(num_tags))
        self.end_transitions = torch.nn.Parameter(torch.zeros(num_tags))

    def nll(self, emissions, mask, tags):
        # emissions [B,T,K]，mask [B,T] bool，tags [B,T]（pad=-100，被 mask 掉）
        tags_safe = tags.clamp(min=0)
        log_z = self._log_partition(emissions, mask)
        gold = self._gold_score(emissions, mask, tags_safe)
        return (log_z - gold).mean()

    def _log_partition(self, emissions, mask):
        batch, seq, _ = emissions.shape
        score = self.start_transitions + emissions[:, 0]
        for t in range(1, seq):
            next_score = torch.logsumexp(score.unsqueeze(2) + self.transitions + emissions[:, t].unsqueeze(1), dim=1)
            score = torch.where(mask[:, t].unsqueeze(1), next_score, score)
        return torch.logsumexp(score + self.end_transitions, dim=-1)

    def _gold_score(self, emissions, mask, tags_safe):
        batch, seq, _ = emissions.shape
        emit = emissions.gather(2, tags_safe.unsqueeze(2)).squeeze(2)
        score = self.start_transitions[tags_safe[:, 0]] + emit[:, 0]
        if seq > 1:
            trans = self.transitions[tags_safe[:, :-1], tags_safe[:, 1:]]
            score = score + ((trans + emit[:, 1:]) * mask[:, 1:].float()).sum(dim=1)
        lengths = mask.sum(1).long()
        ends = tags_safe.gather(1, (lengths - 1).unsqueeze(1)).squeeze(1)
        return score + self.end_transitions[ends]

    def viterbi(self, emissions, mask):
        batch, seq, _ = emissions.shape
        score = self.start_transitions + emissions[:, 0]
        history = []
        for t in range(1, seq):
            best_score, best_from = (score.unsqueeze(2) + self.transitions).max(dim=1)
            history.append(best_from)
            next_score = best_score + emissions[:, t]
            score = torch.where(mask[:, t].unsqueeze(1), next_score, score)
        best_last = (score + self.end_transitions).argmax(dim=-1)
        lengths = mask.sum(1).long()
        paths = []
        for b in range(batch):
            length = int(lengths[b])
            tag = int(best_last[b])
            path = [tag]
            for t in range(length - 1, 0, -1):
                tag = int(history[t - 1][b, tag])
                path.append(tag)
            path.reverse()
            full = [0] * seq
            full[: length] = path
            paths.append(full)
        return paths


def pad_batch(batch):
    length = min(tsl.MAX_LEN, max(len(ids) for _, ids, _ in batch))
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


def rebuild_split():
    """逐行镜像 tsl.main() 的语料组装与划分（同一 rng 流），并断言与冻结
    manifest 完全一致——划分冻结是配对对照的前提。"""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rng = random.Random(tsl.SEED)
    template_corpus = tsl.build_template_corpus()
    handwritten = tsl.rows_of(tsl.TRAIN_GROUPS)
    corpus = [(text, tsl.locate(text, i) if i else None, tsl.locate(text, t) if t else None)
              for _, text, i, t in handwritten]
    corpus += template_corpus
    rng.shuffle(corpus)
    val_n = max(1, len(corpus) // 10)
    val_sentences, train_sentences = corpus[: val_n], corpus[val_n:]

    def as_rows(rows):
        return [
            {"text": text, "item": text[item[0]: item[1]] if item else None,
             "target": text[target[0]: target[1]] if target else None}
            for text, item, target in rows
        ]

    assert as_rows(train_sentences) == manifest["train"], "train split drifted from frozen manifest"
    assert as_rows(val_sentences) == manifest["validation"], "validation split drifted from frozen manifest"
    assert len(template_corpus) == manifest["counts"]["templates"], "template corpus drifted"
    print(f"split freeze asserted: train={len(train_sentences)} validation={len(val_sentences)} (== manifest)")
    # 划分后 rng 的流位置就是 tsl.main() 进入训练循环时的位置（rng 全脚本只
    # 有 划分 shuffle 和 epoch shuffle 两处消费）。锚点臂必须从这一流位置继续。
    return train_sentences, val_sentences, rng.getstate()


def train_one(head, train_seed, epoch_rng, features, val_features, device, legacy_val_rng=False):
    torch.manual_seed(train_seed)
    model = BertForTokenClassification.from_pretrained(
        SNAPSHOT,
        num_labels=len(tsl.TAGS),
        id2label={i: tag for i, tag in enumerate(tsl.TAGS)},
        label2id={tag: i for i, tag in enumerate(tsl.TAGS)},
    )
    model.config._attn_implementation = "eager"
    model.to(device)
    crf = LinearChainCRF(len(tsl.TAGS)) if head == "crf" else None
    if crf is not None:
        crf.to(device)
    params = list(model.parameters()) + (list(crf.parameters()) if crf else [])
    optimizer = torch.optim.AdamW(params, lr=tsl.LR, weight_decay=0.01)
    ce = torch.nn.CrossEntropyLoss(ignore_index=-100)

    started = time.time()
    model.train()
    for epoch in range(1, tsl.EPOCHS + 1):
        epoch_rng.shuffle(features)
        total = 0.0
        for start in range(0, len(features), tsl.BATCH):
            batch = features[start: start + tsl.BATCH]
            input_ids, attention, token_types, label_ids = pad_batch(batch)
            input_ids, attention = input_ids.to(device), attention.to(device)
            token_types, label_ids = token_types.to(device), label_ids.to(device)
            mask = attention.bool()
            if head == "plain":
                logits = model(input_ids=input_ids, attention_mask=attention, token_type_ids=token_types).logits
                loss = ce(logits.reshape(-1, len(tsl.TAGS)), label_ids.reshape(-1))
            else:
                emissions = model(input_ids=input_ids, attention_mask=attention, token_type_ids=token_types).logits
                loss = crf.nll(emissions, mask, label_ids)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += loss.item() * len(batch)
        # 每 epoch 验证仅作观测（eval 态、no_grad，不触碰权重与训练 rng）。
        # --legacy-val-rng：复刻冻结模型的旧验证路径（train 态跑验证，
        # Dropout 继续消耗 torch rng）——fd02a44 修复前的语义，仅用于锚点
        # 逐位复现验证，不是推荐配置。
        if legacy_val_rng:
            model.train()
        else:
            model.eval()
        with torch.no_grad():
            val_total = 0.0
            for start in range(0, len(val_features), tsl.BATCH):
                batch = val_features[start: start + tsl.BATCH]
                input_ids, attention, token_types, label_ids = pad_batch(batch)
                logits = model(
                    input_ids=input_ids.to(device), attention_mask=attention.to(device),
                    token_type_ids=token_types.to(device),
                ).logits
                val_total += ce(logits.reshape(-1, len(tsl.TAGS)), label_ids.to(device).reshape(-1)).item() * len(batch)
        model.train()
        print(f"  [{head}@{train_seed}] epoch {epoch}: loss={total / len(features):.4f} val_loss={val_total / len(val_features):.4f} ({time.time() - started:.0f}s)", flush=True)
    return model, crf


def evaluate_head(model, crf, cases, device):
    model.eval()
    rows = []
    with torch.no_grad():
        for case in cases:
            text, item, target = case["text"], case["item"], case["target"]
            encoded = tsl_tokenizer(text, truncation=True, max_length=tsl.MAX_LEN, return_offsets_mapping=True)
            offsets = encoded["offset_mapping"]
            feed = {
                "input_ids": torch.tensor([encoded["input_ids"]]).to(device),
                "attention_mask": torch.tensor([encoded["attention_mask"]]).to(device),
                "token_type_ids": torch.tensor([encoded["token_type_ids"]]).to(device),
            }
            emissions = model(**feed).logits[0].cpu()
            decodes = {}
            if crf is not None:
                ids = crf.viterbi(emissions.unsqueeze(0), torch.ones(1, emissions.shape[0], dtype=torch.bool))[0]
                item_span, target_span = tsl.tags_to_spans(text, offsets, ids)
                decodes["viterbi"] = (item_span, target_span)
            else:
                greedy_ids = emissions.argmax(-1).tolist()[: len(offsets)]
                probs = torch.softmax(emissions, dim=-1)[: len(offsets)].tolist()
                g_item, g_tgt = tsl.tags_to_spans(text, offsets, greedy_ids)
                c_item, c_tgt, _ = tsl.constrained_decode(offsets, probs)
                decodes["greedy"] = (g_item, g_tgt)
                decodes["constrained"] = (c_item, c_tgt)

            expected = {
                "ITEM": (text.index(item), text.index(item) + len(item)) if item else None,
                "TGT": (text.index(target), text.index(target) + len(target)) if target else None,
            }

            def strict(expected_span, predicted_span):
                return expected_span == predicted_span

            row = {"batch": case["batch"], "group": case.get("group"), "text": text,
                   "expectItem": item, "expectTarget": target, "decodes": {}}
            for mode, (item_span, target_span) in decodes.items():
                empty_fps = [
                    {"field": name, "pred": text[span[0]: span[1]]}
                    for name, expected_span, span in (("ITEM", expected["ITEM"], item_span), ("TGT", expected["TGT"], target_span))
                    if expected_span is None and span is not None
                ]
                row["decodes"][mode] = {
                    "predItem": text[item_span[0]: item_span[1]] if item_span else None,
                    "predTarget": text[target_span[0]: target_span[1]] if target_span else None,
                    "itemStrict": strict(expected["ITEM"], item_span),
                    "targetStrict": strict(expected["TGT"], target_span),
                    "emptyFieldFalsePositives": empty_fps,
                }
            rows.append(row)
    return rows


tsl_tokenizer = None  # 在 main 里初始化（train_one/evaluate_head 共用）


def _rng_from_state(state):
    rng = random.Random()
    rng.setstate(state)
    return rng


def main():
    global tsl_tokenizer
    args = sys.argv[1:]
    device_name = "cpu"
    seeds_arg = None
    for i, a in enumerate(args):
        if a == "--device":
            device_name = args[i + 1]
        elif a.startswith("--device="):
            device_name = a.split("=", 1)[1]
        elif a == "--seeds":
            seeds_arg = args[i + 1]
        elif a.startswith("--seeds="):
            seeds_arg = a.split("=", 1)[1]
    train_seeds = [int(s) for s in seeds_arg.split(",")] if seeds_arg else TRAIN_SEEDS
    legacy_val_rng = "--legacy-val-rng" in args
    device = torch.device(device_name)
    print(f"device={device_name} seeds={train_seeds} legacyValRng={legacy_val_rng}", flush=True)
    train_sentences, val_sentences, split_rng_state = rebuild_split()
    tsl_tokenizer = BertTokenizerFast.from_pretrained(SNAPSHOT)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = (
        [{"batch": "devClassic", **r} for r in manifest["devClassic"]]
        + [{"batch": "devGroups", **r} for grp in manifest["devGroups"] for r in grp["sentences"]]
        + [{"batch": "scored", **r} for r in manifest["scored"]]
    )
    anchor_cases = None
    if FROZEN_ANCHOR_PATH.exists():
        frozen = json.loads(FROZEN_ANCHOR_PATH.read_text(encoding="utf-8"))
        # 锚点取浏览器报告的 fp32 臂：fp32 ONNX 与 Python fp32 逐例一致（历史
        # 轮已核对），q8 臂在 短刃 等例上有合法的量化差异，不能当锚。
        anchor_cases = frozen["arms"][1]["cases"]

    features_all = []
    for text, item, target in train_sentences:
        input_ids, labels = tsl.spans_to_tags(text, item, target, tsl_tokenizer)
        features_all.append((text, input_ids, labels))
    val_features = []
    for text, item, target in val_sentences:
        input_ids, labels = tsl.spans_to_tags(text, item, target, tsl_tokenizer)
        val_features.append((text, input_ids, labels))

    results = []
    for seed in train_seeds:
        # 锚点流（seed == 4711）：从划分 shuffle 消费完的流位置继续，逐位
        # 复刻 tsl.main 的 epoch 批序；两个臂各自从同一保存的流状态出发，
        # 保证配对。其余种子用独立流（划分不动，仍由 rebuild_split 断言）。
        if seed == tsl.SEED:
            make_rng = lambda: _rng_from_state(split_rng_state)  # noqa: E731
        else:
            make_rng = lambda s=seed: random.Random(s)  # noqa: E731
        for head in ("plain", "crf"):
            # 配对关键：每个 (seed, head) 都从同一份原始 features 顺序 + 同一
            # 新建 rng 出发 —— 两臂逐 epoch 批序完全一致；features 副本防止
            # shuffle 原地污染串到第二个臂。
            features = list(features_all)
            run_rng = make_rng()
            print(f"== train {head}@{seed} ==", flush=True)
            model, crf = train_one(head, seed, run_rng, features, val_features, device, legacy_val_rng)
            rows = evaluate_head(model, crf, cases, device)
            results.append({"seed": seed, "head": head, "rows": rows})
            merged = {mode: sum(1 for r in rows if r["decodes"][mode]["itemStrict"] and r["decodes"][mode]["targetStrict"]) for mode in rows[0]["decodes"]}
            print(f"== {head}@{seed} merged(53) both-fields: " + " ".join(f"{m} {n}/53" for m, n in merged.items()), flush=True)
            if head == "plain" and seed == tsl.SEED and anchor_cases is not None:
                diffs = []
                for i, r in enumerate(rows):
                    for mode in MODES:
                        if [r["decodes"][mode]["predItem"], r["decodes"][mode]["predTarget"]] != [
                            anchor_cases[i][mode]["predItem"], anchor_cases[i][mode]["predTarget"]
                        ]:
                            diffs.append((r["text"], mode))
                status = "ANCHOR OK (case-identical to frozen model, fp32 arm)" if not diffs else f"ANCHOR DRIFT: {len(diffs)} case(s) differ: {diffs[:5]}"
                print(f"== anchor plain@{seed}: {status}", flush=True)

    # 汇总（逐例得失、空字段误报、跨种子稳定性）在 crf-summarize 里做，
    # 训练脚本只落原始行。
    tag = f"{device_name}{'-legacyval' if legacy_val_rng else ''}"
    out = ARTIFACTS / f"crf-compare-raw-{tag}-{int(time.time() * 1000)}.json"
    out.write_text(json.dumps({"trainSeeds": train_seeds, "device": device_name, "legacyValRng": legacy_val_rng, "results": results}, ensure_ascii=False), encoding="utf-8")
    print(f"saved: {out}", flush=True)


if __name__ == "__main__":
    main()

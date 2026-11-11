"""Single-logit pairwise model, dataset and metrics (13-way action groups).

One text per (context, candidate group); a shared encoder and one linear head
produce one logit. 13 logits form the distribution over the 12 groups plus 不动;
the loss is BCEWithLogits with pos_weight=12, normalised per original decision.
This is deliberately *not* the old multi-head (step + 115 actions + pointer)
model: it has exactly one output.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import torch
from torch import nn
from torch.utils.data import Dataset
from transformers import AutoModel

import pairwise_serialize as ps


class PairwiseModel(nn.Module):
    def __init__(self, base_dir: str, dropout: float = 0.1) -> None:
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base_dir)
        hidden = int(self.encoder.config.hidden_size)
        self.dropout = nn.Dropout(dropout)
        self.head = nn.Linear(hidden, 1)

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        mask = attention_mask.unsqueeze(-1).to(out.dtype)
        pooled = (out * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1.0)
        return self.head(self.dropout(pooled)).squeeze(-1)


class PairwiseDataset(Dataset):
    """Pairs of one decision share a decisionIndex; the loss normalises per
    decision."""

    def __init__(self, rows: Sequence[Dict[str, Any]], tokenizer: Any, max_len: int,
                 predicate_to_group: Dict[str, str], decisions: Sequence[Tuple[str, int]]) -> None:
        self.pairs: List[Dict[str, Any]] = []
        self.decisions: List[List[int]] = []
        by_key = {(row["rowId"], step): row for row in rows for step in [0]}
        for row_id, step_index in decisions:
            row = by_key.get((row_id, 0)) or next(r for r in rows if r["rowId"] == row_id)
            group_pairs = ps.pairs_for_step(row, step_index, predicate_to_group=predicate_to_group)
            start = len(self.pairs)
            for pair in group_pairs:
                tokens = tokenizer(pair["text"], add_special_tokens=True)["input_ids"]
                if len(tokens) > max_len:
                    raise SystemExit(
                        f"REFUSED: {row_id} step {step_index} group {pair['group']} has "
                        f"{len(tokens)} tokens > maxLen {max_len}; no truncation")
                self.pairs.append({"input_ids": tokens, "label": pair["label"],
                                   "group": pair["group"], "rowId": row_id,
                                   "stepIndex": step_index})
            self.decisions.append(list(range(start, len(self.pairs))))

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, index: int) -> Dict[str, Any]:
        return self.pairs[index]

    def collate(self, batch: Sequence[Dict[str, Any]], pad_id: int) -> Dict[str, torch.Tensor]:
        width = max(len(item["input_ids"]) for item in batch)
        ids = torch.full((len(batch), width), pad_id, dtype=torch.long)
        mask = torch.zeros((len(batch), width), dtype=torch.long)
        for row, item in enumerate(batch):
            length = len(item["input_ids"])
            ids[row, :length] = torch.tensor(item["input_ids"], dtype=torch.long)
            mask[row, :length] = 1
        return {"input_ids": ids, "attention_mask": mask,
                "labels": torch.tensor([item["label"] for item in batch], dtype=torch.float32)}


def decision_loss(logits: torch.Tensor, labels: torch.Tensor, groups_per_decision: int,
                  pos_weight: float = 12.0) -> torch.Tensor:
    """Sum of BCE over all pairs in the batch, divided by decisions*13."""
    raw = nn.functional.binary_cross_entropy_with_logits(
        logits, labels, pos_weight=torch.tensor(pos_weight), reduction="sum")
    decisions = max(1, logits.shape[0] // groups_per_decision)
    return raw / (decisions * groups_per_decision)


def predict_decision(logits: Sequence[float]) -> Dict[str, Any]:
    order = sorted(range(len(logits)), key=lambda index: logits[index], reverse=True)
    return {
        "argmax": order[0],
        "top1": ps.ALL_GROUPS[order[0]],
        "top2": ps.ALL_GROUPS[order[1]],
        "margin": float(logits[order[0]] - logits[order[1]]),
    }


def metrics(decisions: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """decisions: [{stepIndex, gold, pred, logits}] with one entry per decision."""
    from collections import Counter

    total = len(decisions)
    hits = sum(1 for row in decisions if row["pred"] == row["gold"])
    skip_tp = sum(1 for row in decisions if row["gold"] == ps.SKIP_GROUP and row["pred"] == ps.SKIP_GROUP)
    skip_pred = sum(1 for row in decisions if row["pred"] == ps.SKIP_GROUP)
    skip_gold = sum(1 for row in decisions if row["gold"] == ps.SKIP_GROUP)
    per_group: Dict[str, Dict[str, float]] = {}
    for group in ps.ALL_GROUPS:
        tp = sum(1 for row in decisions if row["gold"] == group and row["pred"] == group)
        fp = sum(1 for row in decisions if row["pred"] == group and row["gold"] != group)
        fn = sum(1 for row in decisions if row["gold"] == group and row["pred"] != group)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_group[group] = {"support": tp + fn, "precision": round(precision, 4),
                            "recall": round(recall, 4), "f1": round(f1, 4)}
    scored = [group for group in ps.ALL_GROUPS if per_group[group]["support"] > 0]
    worst = sorted(scored, key=lambda group: per_group[group]["f1"])[:3]
    steps = Counter(row["stepIndex"] for row in decisions)
    return {
        "decisions": total,
        "rowHit": round(hits / total, 4) if total else 0.0,
        "skipPrecision": round(skip_tp / skip_pred, 4) if skip_pred else None,
        "skipRecall": round(skip_tp / skip_gold, 4) if skip_gold else None,
        "perGroup": per_group,
        "worstThreeGroups": [{"group": group, **per_group[group]} for group in worst],
        "stepDecisions": dict(sorted(steps.items())),
        "predictedGroups": dict(Counter(row["pred"] for row in decisions)),
    }

# Next-action model: a MiniRBT-H256 encoder with heads that can actually emit
# the protocol's Y, not a 12-group tag.
#
# Y is `steps: [{action, object}]` with 0/1/2 steps. One 12-way classifier can
# never express it: a 12-group hit says nothing about the fine predicate, the
# number of steps, or which candidate the step acts on. So the model has:
#
#   step head      3-way: skip / one step / two steps
#   action heads   115-way fine predicate per step slot (two slots)
#   object heads   pointer over [null, candidate_1..candidate_n] per step slot
#
# The pointer is what lets the model act on a candidate list whose ids change
# per scene: candidates are encoded as their own sequences and scored against
# the step's query, so nothing is tied to a fixed id vocabulary. `null` is a
# learned vector, so "the action needs no object" is a real choice rather than
# an index-0 artefact of an empty list.

from __future__ import annotations

import math

import torch
from torch import nn

from labels import MAX_STEPS, STEP_CLASSES

N_FINE_DEFAULT = 115


class NextStepModel(nn.Module):
    def __init__(
        self,
        encoder: nn.Module,
        *,
        hidden: int,
        n_fine: int = N_FINE_DEFAULT,
        dropout: float = 0.1,
        freeze_encoder: bool = True,
    ):
        super().__init__()
        self.encoder = encoder
        self.hidden = hidden
        self.n_fine = n_fine
        self.freeze_encoder = freeze_encoder
        if freeze_encoder:
            for parameter in self.encoder.parameters():
                parameter.requires_grad_(False)
        self.dropout = nn.Dropout(dropout)
        # Shared trunk for the three head families: a 256-dim encoder output is
        # thin enough that one projection is all the model can support on a few
        # hundred rows.
        self.trunk = nn.Sequential(nn.Linear(hidden, hidden), nn.Tanh())
        self.step_head = nn.Linear(hidden, STEP_CLASSES)
        self.step_query = nn.ModuleList([nn.Linear(hidden, hidden) for _ in range(MAX_STEPS)])
        self.action_heads = nn.ModuleList([nn.Linear(hidden, n_fine) for _ in range(MAX_STEPS)])
        self.candidate_key = nn.Linear(hidden, hidden)
        self.null_key = nn.Parameter(torch.zeros(MAX_STEPS, hidden))
        nn.init.normal_(self.null_key, std=0.02)

    def encode(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        states = out.last_hidden_state
        mask = attention_mask.unsqueeze(-1).to(states.dtype)
        return (states * mask).sum(1) / mask.sum(1).clamp(min=1e-9)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        cand_ids: torch.Tensor,
        cand_mask: torch.Tensor,
    ) -> dict:
        pooled = self.encode(input_ids, attention_mask)
        trunk = self.trunk(self.dropout(pooled))
        step_logits = self.step_head(trunk)

        batch, width, cand_len = cand_ids.shape
        flat_ids = cand_ids.view(batch * width, cand_len)
        flat_mask = cand_mask.view(batch * width, cand_len)
        candidate_hidden = self.encode(flat_ids, flat_mask).view(batch, width, -1)
        keys = self.candidate_key(candidate_hidden)  # [B, C, H]

        action_logits = []
        object_logits = []
        for slot in range(MAX_STEPS):
            query = self.step_query[slot](trunk)
            action_logits.append(self.action_heads[slot](trunk))
            scores = torch.einsum("bh,bch->bc", query, keys) / math.sqrt(self.hidden)
            null = torch.einsum("bh,h->b", query, self.null_key[slot]).unsqueeze(1)
            logits = torch.cat([null, scores], dim=1)  # [B, 1+C]
            # A padded candidate slot can never be chosen. Every row has at
            # least one column so the tensor shape stays uniform.
            padding = torch.zeros((batch, 1), dtype=torch.bool, device=logits.device)
            pad_mask = torch.cat([padding, cand_mask.sum(-1) == 0], dim=1)
            logits = logits.masked_fill(pad_mask, torch.finfo(logits.dtype).min)
            object_logits.append(logits)
        return {
            "step_logits": step_logits,
            "action_logits": torch.stack(action_logits, dim=1),   # [B, 2, 115]
            "object_logits": torch.stack(object_logits, dim=1),   # [B, 2, 1+C]
        }


def build_encoder(base_dir: str, *, unfreeze: bool = False) -> tuple[nn.Module, int]:
    """Load MiniRBT-H256 as a plain BERT encoder. Hidden size comes from the
    checkpoint's config, never from a constant in this file."""
    from transformers.models.bert.modeling_bert import BertModel

    encoder = BertModel.from_pretrained(base_dir)
    hidden = int(encoder.config.hidden_size)
    if unfreeze:
        for parameter in encoder.parameters():
            parameter.requires_grad_(True)
    return encoder, hidden


def build_tiny_encoder(*, hidden: int = 32, layers: int = 2, vocab: int = 256) -> tuple[nn.Module, int]:
    """Offline CPU test encoder. Never used for a real training run; the trainer
    refuses a base whose config name is not the registered MiniRBT directory."""
    from transformers.models.bert.modeling_bert import BertModel
    from transformers.models.bert.configuration_bert import BertConfig

    config = BertConfig(
        vocab_size=vocab, hidden_size=hidden, num_hidden_layers=layers,
        num_attention_heads=4, intermediate_size=hidden * 2, max_position_embeddings=512,
    )
    return BertModel(config), hidden

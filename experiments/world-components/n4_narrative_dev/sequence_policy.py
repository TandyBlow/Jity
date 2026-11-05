"""Full-sequence training and EOS/timeout greedy decoding for N4 experiments.

No token-count ceiling is applied. This bypasses generate()'s default length
ceiling rather than accidentally falling back to it when max_new_tokens is
omitted. Only the single-row greedy path used by these experiments is covered.
"""

import math
import time


DEFAULT_GENERATION_TIMEOUT = 30.0


def generation_timeout(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Generation timeout must be positive and finite")
    return value


def encode_training_batch(tokenizer, rows):
    enc = tokenizer([r["input"] for r in rows], padding=True,
                    truncation=False, return_tensors="pt")
    labels = tokenizer(text_target=[r["target"] for r in rows], padding=True,
                       truncation=False, return_tensors="pt")
    labels.input_ids.masked_fill_(labels.attention_mask == 0, -100)
    return enc, labels


def generate_greedy(model, encoded, timeout_seconds=DEFAULT_GENERATION_TIMEOUT,
                    logits_processor=None):
    """Return (decoder ids including start token, completion metadata).

    Encode once, then decode with KV cache until EOS or wall-clock timeout.
    Timeout is checked between model calls; a running call is not preempted.
    Incomplete output is retained for diagnosis and must not count as success.
    """
    import torch

    timeout_seconds = generation_timeout(timeout_seconds)
    if encoded["input_ids"].shape[0] != 1:
        raise ValueError("EOS/timeout decoder expects one row at a time")
    if model.training:
        raise ValueError("Call model.eval() before generation")
    cfg = model.generation_config
    start = cfg.decoder_start_token_id
    if start is None:
        start = model.config.decoder_start_token_id
    eos = cfg.eos_token_id
    if eos is None:
        eos = model.config.eos_token_id
    if start is None or eos is None:
        raise ValueError("Decoder start and EOS tokens are required")
    eos_ids = {eos} if isinstance(eos, int) else set(eos)
    if not eos_ids:
        raise ValueError("At least one EOS token is required")

    started = time.perf_counter()
    current = torch.full((1, 1), start, dtype=torch.long,
                         device=encoded["input_ids"].device)
    tokens = [current]
    past = None
    reason = "timeout"
    with torch.inference_mode():
        encoder_out = model.get_encoder()(**encoded, return_dict=True)
        while time.perf_counter() - started < timeout_seconds:
            out = model(encoder_outputs=encoder_out,
                        attention_mask=encoded.get("attention_mask"),
                        decoder_input_ids=current, past_key_values=past,
                        use_cache=True, return_dict=True)
            scores = out.logits[:, -1, :]
            if logits_processor is not None:
                scores = logits_processor(torch.cat(tokens, dim=1), scores)
            current = scores.argmax(dim=-1, keepdim=True)
            past = out.past_key_values
            tokens.append(current)
            # item() also waits for this GPU step before checking its duration.
            if current.item() in eos_ids:
                reason = "eos"
                break
    return torch.cat(tokens, dim=1), {
        "stopReason": reason, "complete": reason == "eos",
        "newTokens": len(tokens) - 1,
        "seconds": round(time.perf_counter() - started, 6),
    }


def step_summary(enc, labels):
    """给 OOM 报错用的形状摘要：批大小、输入/目标最长 token 数。"""
    return {"batch": int(enc["input_ids"].shape[0]),
            "inputTokens": int(enc["input_ids"].shape[1]),
            "targetTokens": int(labels.shape[1])}


class OutOfMemory(RuntimeError):
    pass


def rethrow_oom(exc, enc, labels):
    """显存不足时给一条能行动的报错，不静默退回截断或缩小 batch。"""
    info = step_summary(enc, labels)
    raise OutOfMemory(
        "CUDA out of memory on a full-length batch "
        f"(batch={info['batch']}, input={info['inputTokens']} tokens, "
        f"target={info['targetTokens']} tokens). Sequence lengths are not "
        "truncated; reduce the batch size or split the input, or raise "
        "gradient checkpointing - do not re-enable truncation."
    ) from exc


def sequence_policy(timeout_seconds):
    return {"maxInput": None, "maxTarget": None, "maxNewTokens": None,
            "truncation": False, "padding": "longest-in-batch",
            "decoding": "greedy-cached", "normalStop": "eos",
            "generationTimeoutSeconds": timeout_seconds,
            "incompleteIsSuccess": False}

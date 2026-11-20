"""束宽 2 的两种实现：整段重算（原版）与 KV 缓存版。

搜索规则完全一致，改的只有计算复用：

  * 编码只做一次；
  * 每条活动路径保存自己的 KV 缓存，父路径选定后把缓存按新顺序重排；
  * 已完成（EOS）的路径不再解码；
  * 束宽 2、累计对数概率、并列时按“先父路径顺序、再 top-k 名次”的稳定顺序、
    每源 20 秒预算、256 token 防死循环，全部不变。
"""
import time

SAFETY_TOKENS = 256


def _special_ids(model):
    config = model.generation_config
    start = config.decoder_start_token_id
    if start is None:
        start = model.config.decoder_start_token_id
    eos = config.eos_token_id
    if eos is None:
        eos = model.config.eos_token_id
    eos_set = {eos} if isinstance(eos, int) else set(eos)
    return start, eos_set


def generate_beam_recompute(model, encoded, width=2, timeout_seconds=20.0):
    """原版：每一步对每条路径整段重算。"""
    import torch

    model.eval()
    start, eos_set = _special_ids(model)
    started = time.perf_counter()
    beams = [([start], 0.0)]
    finished = []
    steps = 0
    switches = 0
    truncated = False
    with torch.inference_mode():
        while time.perf_counter() - started < timeout_seconds:
            if not beams:
                break
            candidates = []
            for parent, (tokens, score) in enumerate(beams):
                decoder = torch.tensor([tokens], dtype=torch.long,
                                       device=encoded['input_ids'].device)
                out = model(input_ids=encoded['input_ids'],
                            attention_mask=encoded.get('attention_mask'),
                            decoder_input_ids=decoder, return_dict=True)
                logp = torch.log_softmax(out.logits[0, -1, :].float(), dim=-1)
                top_values, top_index = logp.topk(width)
                for rank in range(width):
                    candidates.append((parent, tokens + [int(top_index[rank])],
                                       score + float(top_values[rank])))
            steps += 1
            candidates.sort(key=lambda item: -item[2])
            beams = []
            for parent, tokens, score in candidates:
                if tokens[-1] in eos_set:
                    finished.append((tokens, score))
                else:
                    beams.append((tokens, score))
                if len(beams) == width:
                    break
            if len(finished) >= width and (
                    not beams or max(s for _, s in beams) <= min(s for _, s in finished)):
                break
            if steps >= SAFETY_TOKENS:
                truncated = True
                break
    seconds = round(time.perf_counter() - started, 3)
    if finished:
        tokens, score = max(finished, key=lambda item: item[1])
        complete = True
    elif beams:
        tokens, score = max(beams, key=lambda item: item[1])
        complete = False
    else:
        tokens, score = [start], float('-inf')
        complete = False
    return tokens, {'complete': complete, 'steps': steps, 'candidates': len(finished),
                    'seconds': seconds, 'truncated': truncated,
                    'score': round(score, 6), 'switches': 0}


def generate_beam_cached(model, encoded, width=2, timeout_seconds=20.0):
    """KV 缓存版：用批量前向 + 缓存重排，规则与原版逐条一致。"""
    import torch

    model.eval()
    start_token, eos_set = _special_ids(model)
    started = time.perf_counter()
    with torch.inference_mode():
        encoder_out = model.get_encoder()(
            input_ids=encoded['input_ids'],
            attention_mask=encoded.get('attention_mask'), return_dict=True)
        beam_tokens = [[start_token]]
        beam_scores = [0.0]
        cache = None
        finished = []
        steps = 0
        switches = 0
        truncated = False
        while time.perf_counter() - started < timeout_seconds:
            if not beam_tokens:
                break
            last = torch.tensor([[tokens[-1]] for tokens in beam_tokens],
                                dtype=torch.long, device=encoded['input_ids'].device)
            out = model(encoder_outputs=encoder_out,
                        attention_mask=encoded.get('attention_mask'),
                        decoder_input_ids=last, past_key_values=cache,
                        use_cache=True, return_dict=True)
            step_cache = out.past_key_values
            step_logits = out.logits[:, -1, :]
            steps += 1
            candidates = []
            for parent in range(len(beam_tokens)):
                logp = torch.log_softmax(step_logits[parent].float(), dim=-1)
                top_values, top_index = logp.topk(width)
                for rank in range(width):
                    candidates.append((parent, int(top_index[rank]),
                                       beam_scores[parent] + float(top_values[rank])))
            candidates.sort(key=lambda item: -item[2])
            new_tokens, new_scores, parents = [], [], []
            for parent, token, score in candidates:
                if token in eos_set:
                    finished.append((beam_tokens[parent] + [token], score))
                    continue
                new_tokens.append(beam_tokens[parent] + [token])
                new_scores.append(score)
                parents.append(parent)
                if len(new_tokens) == width:
                    break
            # 缓存对齐：批量前向返回的缓存里，每条活动路径占一行。
            # 第一条事实第一次前向只有 1 行，需要按父路径复制成 width 行；
            # 之后若父路径顺序/数量变化，就地按父索引重排。
            cache_rows = step_cache.self_attention_cache[0][0].shape[0]
            if cache_rows == 1 and len(parents) > 1:
                step_cache.batch_repeat_interleave(len(parents))
                switches += len(parents) - 1
            elif parents != list(range(cache_rows)):
                switches += sum(1 for slot, parent in enumerate(parents) if parent != slot)
                step_cache.batch_select_indices(torch.tensor(parents, dtype=torch.long))
            cache = step_cache
            beam_tokens, beam_scores = new_tokens, new_scores
            if len(finished) >= width and (
                    not beam_scores or max(beam_scores) <= min(s for _, s in finished)):
                break
            if steps >= SAFETY_TOKENS:
                truncated = True
                break
    seconds = round(time.perf_counter() - started, 3)
    if finished:
        tokens, score = max(finished, key=lambda item: item[1])
        complete = True
    elif beam_tokens:
        best = max(range(len(beam_tokens)), key=lambda i: beam_scores[i])
        tokens, score = beam_tokens[best], beam_scores[best]
        complete = False
    else:
        tokens, score = [start_token], float('-inf')
        complete = False
    return tokens, {'complete': complete, 'steps': steps, 'candidates': len(finished),
                    'seconds': seconds, 'truncated': truncated,
                    'score': round(score, 6), 'switches': switches}

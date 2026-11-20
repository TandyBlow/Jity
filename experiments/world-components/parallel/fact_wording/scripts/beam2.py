"""Beam-2 search with a sound stopping rule (comparison-protocol-v3.md §1.4).

The search is written against a batch scorer so the same code can be driven by a
synthetic table (preflight P7) or by the T5 model (preflight P5/P6 and later runs):

    score_batch(list_of_token_tuples) -> list[list[float]]
        one log-probability row per hypothesis, length = vocabulary size

Score = sum of natural-log probabilities of every generated token, EOS included.
All comparisons go through `rank_key`, so ties, rounding and ordering never depend
on dict/set iteration order.

Stopping rule (v3): a live hypothesis can only lose score as it grows, because
every log-probability is <= 0. Ordering, however, uses round(score, 6), so a live
hypothesis whose rounded score EQUALS the rounded second-best finished score can
still win on the tie-break (length, token ids). The search therefore stops only
when the rounded best live score is STRICTLY BELOW the rounded second-best
finished score; equal rounded values keep searching, and pruning uses the same
strict comparison. The v1 rule ("stop as soon as two hypotheses finished") is NOT
used: it can discard a live path that would have finished with a better score.

If the token cap or the wall-clock budget ends the search first, the result is
marked `searchExhausted=False` and must be treated as undetermined by the caller.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

EOS_VERDICT_TIE_DIGITS = 6


@dataclass(frozen=True)
class Hypothesis:
    tokens: tuple[int, ...]
    score: float

    def key(self, beam_index: int = 0):
        """Total order used everywhere: higher score, fewer tokens, smaller ids.

        Scores are compared after rounding to 6 decimals so that two runs on the
        same device agree bit-for-bit on ordering; the remaining fields make the
        order total even when rounded scores are equal.
        """
        return (-round(self.score, EOS_VERDICT_TIE_DIGITS), len(self.tokens),
                self.tokens, beam_index)


@dataclass
class BeamResult:
    tokens: tuple[int, ...]
    score: float
    complete: bool                 # emitted EOS
    search_exhausted: bool         # stopped by the sound rule, not by cap/budget
    stop_reason: str               # "rule" | "cap" | "budget" | "no-live"
    steps: int
    finished_count: int            # how many hypotheses ever emitted EOS
    retained_finished: list[dict] = field(default_factory=list)
    best_live_score_at_stop: float | None = None
    threshold_at_stop: float | None = None
    seconds: float = 0.0


def _topk(row: list[float], k: int) -> list[int]:
    """Token ids of the k largest entries, ordered by (-value, id)."""
    order = sorted(range(len(row)), key=lambda i: (-row[i], i))
    return order[:k]


def _step_score(scorer, hypotheses: list[Hypothesis]) -> list[list[float]]:
    return scorer([h.tokens for h in hypotheses])


def beam2(scorer, eos_token_id: int, *, width: int = 2, expand: int = 2,
          max_new_tokens: int = 64, budget_seconds: float = 20.0,
          clock=time.monotonic, start_tokens: tuple[int, ...] = ()) -> BeamResult:
    """Run beam search. `start_tokens` is the already-known prefix (decoder start)."""
    began = clock()
    live = [Hypothesis(start_tokens, 0.0)]
    finished: list[Hypothesis] = []
    steps = 0
    finished_count = 0
    stop_reason = "no-live"
    exhausted = False
    best_live_at_stop = None
    threshold_at_stop = None

    while True:
        if not live:
            stop_reason = "no-live"
            exhausted = True
            break

        # --- budget -------------------------------------------------------
        if clock() - began >= budget_seconds:
            stop_reason = "budget"
            break
        # --- token cap ----------------------------------------------------
        if max(len(h.tokens) for h in live) - len(start_tokens) >= max_new_tokens:
            stop_reason = "cap"
            break

        rows = _step_score(scorer, live)
        steps += 1
        candidates: list[Hypothesis] = []
        for hyp, row in zip(live, rows):
            for tok in _topk(row, expand):
                candidates.append(Hypothesis(hyp.tokens + (tok,), hyp.score + float(row[tok])))

        candidates.sort(key=lambda h: h.key())
        next_live: list[Hypothesis] = []
        for cand in candidates:
            if cand.tokens[-1] == eos_token_id:
                finished_count += 1
                finished.append(cand)
                finished.sort(key=lambda h: h.key())
                del finished[width:]
            else:
                next_live.append(cand)
            if len(next_live) >= width:
                break
        live = next_live

        # --- sound stop rule (rounded, strict) ---------------------------
        threshold = finished[-1].score if len(finished) >= width else None
        if threshold is not None:
            threshold_rounded = round(threshold, EOS_VERDICT_TIE_DIGITS)
            # keep anything that could still tie at the rounded value
            live = [h for h in live
                    if round(h.score, EOS_VERDICT_TIE_DIGITS) >= threshold_rounded]
            if not live:
                stop_reason = "rule"
                exhausted = True
                best_live_at_stop = None
                threshold_at_stop = threshold
                break
            best_live = max(h.score for h in live)
            if round(best_live, EOS_VERDICT_TIE_DIGITS) < threshold_rounded:
                stop_reason = "rule"
                exhausted = True
                best_live_at_stop = best_live
                threshold_at_stop = threshold
                break

    chosen: Hypothesis | None = None
    if finished:
        chosen = min(finished, key=lambda h: h.key())
    else:
        pool = live or [Hypothesis(start_tokens, 0.0)]
        chosen = min(pool, key=lambda h: h.key())

    return BeamResult(
        tokens=chosen.tokens,
        score=chosen.score,
        complete=bool(chosen.tokens and chosen.tokens[-1] == eos_token_id),
        search_exhausted=exhausted and bool(finished),
        stop_reason=stop_reason,
        steps=steps,
        finished_count=finished_count,
        retained_finished=[dict(tokens=list(h.tokens), score=h.score) for h in finished],
        best_live_score_at_stop=best_live_at_stop,
        threshold_at_stop=threshold_at_stop,
        seconds=clock() - began,
    )


def greedy(scorer, eos_token_id: int, *, max_new_tokens: int = 64,
           budget_seconds: float = 20.0, clock=time.monotonic,
           start_tokens: tuple[int, ...] = ()) -> dict:
    """Plain argmax decoding with the same budget/cap accounting as beam2."""
    began = clock()
    tokens = list(start_tokens)
    score = 0.0
    complete = False
    stop_reason = "cap"
    steps = 0
    while True:
        if clock() - began >= budget_seconds:
            stop_reason = "budget"
            break
        if len(tokens) - len(start_tokens) >= max_new_tokens:
            stop_reason = "cap"
            break
        row = _step_score(scorer, [Hypothesis(tuple(tokens), score)])[0]
        tok = min(range(len(row)), key=lambda i: (-row[i], i))
        tokens.append(tok)
        score += float(row[tok])
        steps += 1
        if tok == eos_token_id:
            complete = True
            stop_reason = "eos"
            break
    return dict(tokens=tuple(tokens), score=score, complete=complete,
                stop_reason=stop_reason, steps=steps,
                search_exhausted=stop_reason in ("eos", "cap"),
                seconds=clock() - began)

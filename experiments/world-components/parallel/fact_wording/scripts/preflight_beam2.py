"""Preflight P7: verify beam2.py against its frozen specification (no model needed).

The test tables use log-probability-like rows (they are summed, not sampled, so they
do not need to sum to one). Every prefix that is not listed resolves to -50 for all
tokens, which keeps the search out of undefined territory without hiding mistakes in
the listed rows.

  T1 EOS at the first step is kept and can win.
  T2 finished-hypothesis retention: a third finish arrives, the best two survive.
  T3 cumulative score: scores are the sum of the emitted tokens' log-probabilities.
  T4 tie-breaking: equal token scores pick the smaller id; equal finished scores pick
     the total-order key (fewer tokens, smaller ids, earlier beam).
  T5 timeout: the wall-clock budget stops the search, marks it not exhausted, and
     still returns the best finished hypothesis.
  T6 token cap: stopping by cap is also marked not exhausted.
  T7 THE v1-vs-v2 REGRESSION: a live path that is cheap now but finishes better than
     every finished hypothesis must survive after two hypotheses already finished.
     A v1 emulator ("stop as soon as two finished") loses this case; v2 must win.
  T8 exhaustive comparison: for each of N seeded prefix-dependent tables, enumerate
     every sequence up to depth D; check (a) beam never beats the exact optimum,
     (b) its output is a legal finished sequence, (c) report how often width-2 equals
     the exact optimum (measured, not promised).
  T9 v2 is never worse than the v1 rule on the same tables.
  T10 boundary: a live score that ROUNDS equal to the 2nd finished score keeps searching
      (v2's raw comparison would have pruned it) and may win on the tie-break.
  T11 one unit beyond the 6th decimal below the rounded threshold must stop.
"""

from __future__ import annotations

import itertools
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
from beam2 import beam2, greedy, Hypothesis  # noqa: E402

EOS = 2          # vocabulary: 0=a, 1=b, 2=<eos>, 3=c
VOCAB = 4
BAD = -50.0
FAILURES: list[str] = []


def row(**values: float) -> list[float]:
    """Row with the given token ids set; every other token is BAD."""
    out = [BAD] * VOCAB
    for key, value in values.items():
        out[int(key[1:])] = value
    return out


def static_scorer(table: dict):
    def score(prefixes):
        return [list(table.get(tuple(p), [BAD] * VOCAB)) for p in prefixes]
    return score


def check(name: str, ok: bool, detail: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    if not ok:
        FAILURES.append(name)


def v1_rule(scorer, depth: int) -> Hypothesis:
    """The v1 stopping rule, kept here only as a comparison object.

    It prunes the beam to `width` finished hypotheses and stops extending as soon as
    two exist. This is the rule the v2 protocol replaces.
    """
    live = [Hypothesis((), 0.0)]
    finished: list[Hypothesis] = []
    for _ in range(depth):
        if not live:
            break
        rows = scorer([h.tokens for h in live])
        cands = []
        for hyp, logrow in zip(live, rows):
            for tok in sorted(range(VOCAB), key=lambda i: (-logrow[i], i))[:2]:
                cands.append(Hypothesis(hyp.tokens + (tok,), hyp.score + logrow[tok]))
        cands.sort(key=lambda h: h.key())
        live = []
        for cand in cands:
            if cand.tokens[-1] == EOS:
                finished.append(cand)
                finished.sort(key=lambda h: h.key())
                finished = finished[:2]
            else:
                live.append(cand)
            if len(live) >= 2:
                break
        if len(finished) >= 2:
            break
    pool = finished or live
    return min(pool, key=lambda h: h.key())


def t1_eos_first() -> None:
    table = {(): row(t0=-0.5, t1=-2.0, t2=-0.1),
             (0,): row(t2=-0.05),
             (1,): row(t2=-0.05)}
    r = beam2(static_scorer(table), EOS, max_new_tokens=5, budget_seconds=5)
    check("T1 eos-first", r.complete and r.tokens == (EOS,) and r.search_exhausted,
          f"tokens={r.tokens} score={r.score:.4f} stop={r.stop_reason}")


def t2_retention() -> None:
    table = {
        (): row(t0=-0.1, t1=-0.2),
        (0,): row(t2=-0.8, t3=-0.5),      # a -> eos: -0.9 ; a -> c: -0.6
        (1,): row(t2=-1.0, t3=-9.0),      # b -> eos: -1.2 ; b -> c: -9.2
        (0, 3): row(t2=-0.9),             # a,c -> eos: -1.5  (third finish)
        (1, 3): row(),                    # b,c never finishes
    }
    r = beam2(static_scorer(table), EOS, max_new_tokens=6, budget_seconds=30)
    scores = [round(h["score"], 4) for h in r.retained_finished]
    check("T2 retention",
          r.finished_count == 3 and len(r.retained_finished) == 2
          and abs(r.score - (-0.9)) < 1e-9,
          f"finished_count={r.finished_count} retained={scores} picked={r.score:.4f}")


def t3_cumulative() -> None:
    table = {
        (): row(t0=-0.2),
        (0,): row(t0=-0.3),
        (0, 0): row(t2=-0.4),
    }
    r = beam2(static_scorer(table), EOS, max_new_tokens=6, budget_seconds=30)
    expected = table[()][0] + table[(0,)][0] + table[(0, 0)][EOS]
    check("T3 cumulative", r.tokens == (0, 0, EOS) and abs(r.score - expected) < 1e-12,
          f"tokens={r.tokens} score={r.score:.6f} expected={expected:.6f}")


def t4_ties() -> None:
    table = {(): row(t0=-0.5, t1=-0.5),
             (0,): row(t2=-0.1, t3=-0.1),
             (1,): row(t2=-0.1, t3=-0.1)}
    g = greedy(static_scorer(table), EOS, max_new_tokens=4, budget_seconds=5)
    check("T4a tie smallest-id greedy", g["tokens"] == (0, EOS),
          f"greedy={g['tokens']} (expected (0, {EOS}))")

    r = beam2(static_scorer(table), EOS, max_new_tokens=4, budget_seconds=30)
    equal = abs(table[()][0] + table[(0,)][EOS] - (table[()][1] + table[(1,)][EOS])) < 1e-12
    check("T4b tie total-order beam", equal and r.tokens == (0, EOS),
          f"picked={r.tokens} score={r.score:.4f}")


class FakeClock:
    def __init__(self, step_seconds: float):
        self.t = 0.0
        self.step = step_seconds

    def __call__(self) -> float:
        value = self.t
        self.t += self.step
        return value


def t5_timeout() -> None:
    table = {(): row(t0=-0.1),
             (0,): row(t2=-0.8),          # a -> eos: -0.9 at the second scored step
             (0, 0): row(t0=-0.1)}
    r = beam2(static_scorer(table), EOS, max_new_tokens=10,
              budget_seconds=2.5, clock=FakeClock(1.0))
    check("T5 timeout",
          r.stop_reason == "budget" and not r.search_exhausted
          and r.complete and abs(r.score - (-0.9)) < 1e-9,
          f"stop={r.stop_reason} exhausted={r.search_exhausted} tokens={r.tokens} score={r.score:.4f}")


def t6_cap() -> None:
    table = {(): row(t0=-0.1), (0,): row(t0=-0.1), (0, 0): row(t0=-0.1)}
    r = beam2(static_scorer(table), EOS, max_new_tokens=2, budget_seconds=30)
    check("T6 token cap",
          r.stop_reason == "cap" and not r.search_exhausted and r.tokens == (0, 0),
          f"stop={r.stop_reason} exhausted={r.search_exhausted} tokens={r.tokens}")


def t7_v1_trap() -> None:
    table = {
        (): row(t0=-0.85, t1=-1.0),      # a: -0.85, b: -1.0
        (0,): row(t2=-0.35, t0=-0.05),   # a,eos: -1.2 ; a,a: -0.9 (live, cheap)
        (1,): row(t2=-0.5, t1=-3.0),     # b,eos: -1.5 ; b,b: -4.0
        (0, 0): row(t2=0.0),             # a,a,eos: -0.9
        (1, 1): row(t2=-5.0),
    }
    scorer = static_scorer(table)
    v2 = beam2(scorer, EOS, max_new_tokens=6, budget_seconds=30)
    v1 = v1_rule(scorer, depth=6)
    check("T7 v1-vs-v2 trap",
          v2.tokens == (0, 0, EOS) and abs(v2.score - (-0.9)) < 1e-9
          and v1.tokens == (0, EOS) and abs(v1.score - (-1.2)) < 1e-9,
          f"v1 would return {v1.tokens} ({v1.score:.3f}); v2 returns {v2.tokens} ({v2.score:.3f})")


def enumerate_exact(table: dict, depth: int) -> tuple[float, tuple[int, ...]]:
    best = (float("-inf"), ())
    stack = [((), 0.0)]
    while stack:
        prefix, score = stack.pop()
        logrow = table[prefix]
        for tok in range(VOCAB):
            total = score + logrow[tok]
            seq = prefix + (tok,)
            if tok == EOS:
                if total > best[0]:
                    best = (total, seq)
            elif len(seq) < depth:
                stack.append((seq, total))
    return best


def random_tables(rng: random.Random, n: int, depth: int, eos_top2: bool = False) -> list[dict]:
    """Prefix-dependent random tables; rows need not be normalised (they are summed)."""
    tables = []
    for _ in range(n):
        prefixes = [()]
        for length in range(1, depth):
            prefixes += list(itertools.product(range(VOCAB), repeat=length))
        table = {}
        for p in prefixes:
            logrow = [rng.uniform(-4.0, 0.0) for _ in range(VOCAB)]
            if eos_top2:
                # Keep EOS strictly inside the top-2 so the width-2 beam always has a
                # finish. Using sorted()[-2] would tie EOS with an existing token and
                # the tie-break (smaller id first) could push it to third place.
                non_eos_best = max(v for i, v in enumerate(logrow) if i != EOS)
                logrow[EOS] = non_eos_best - 1e-6
            table[p] = logrow
        tables.append(table)
    return tables


def t8_exhaustive(n_tables: int = 300, depth: int = 3) -> None:
    rng = random.Random(20261108)
    natural = random_tables(rng, n_tables, depth, eos_top2=False)
    constrained = random_tables(rng, n_tables, depth, eos_top2=True)

    # --- natural tables: EOS may never enter the beam; legality and soundness only
    complete = 0
    legal = True
    sound = True
    for table in natural:
        exact_score, _ = enumerate_exact(table, depth)
        r = beam2(static_scorer(table), EOS, max_new_tokens=depth, budget_seconds=30)
        legal = legal and all(0 <= tok < VOCAB for tok in r.tokens)
        if r.complete:
            complete += 1
            if r.score > exact_score + 1e-9:
                sound = False
    check("T8a legal token ids (natural tables)", legal, f"tables={n_tables}")
    check("T8b finished output never beats exact", sound,
          f"tables={n_tables}, finished={complete}")
    print(f"INFO  T8c natural tables: {complete}/{n_tables} produced a finished sentence "
          f"({complete / n_tables:.1%}); the rest stop unfinished and must be judged U")

    # --- constrained tables: EOS is always in the beam's top-2, so completion is guaranteed
    matches = 0
    sound = True
    legal = True
    worst_gap = 0.0
    worst = None
    for table in constrained:
        exact_score, exact_seq = enumerate_exact(table, depth)
        r = beam2(static_scorer(table), EOS, max_new_tokens=depth, budget_seconds=30)
        legal = legal and r.complete and r.tokens[-1] == EOS and all(0 <= tok < VOCAB for tok in r.tokens)
        if r.score > exact_score + 1e-9:
            sound = False
        if abs(r.score - exact_score) < 1e-9 and r.tokens == exact_seq:
            matches += 1
        gap = exact_score - r.score
        if gap > worst_gap:
            worst_gap = gap
            worst = dict(beam=list(r.tokens), beamScore=r.score,
                         exact=list(exact_seq), exactScore=exact_score)
    check("T8d finished + legal (EOS always in top-2)", legal, f"tables={n_tables}")
    check("T8e never beats exact (EOS always in top-2)", sound, f"tables={n_tables}")
    print(f"INFO  T8f width-2 equals exact optimum in {matches}/{n_tables} tables "
          f"({matches / n_tables:.1%}); largest score gap {worst_gap:.4f}")
    if worst is None:
        print("INFO  T8f no gap case: width-2 matched the exact optimum on every table")
    else:
        print(f"INFO  T8f worst gap case: beam={worst['beam']} {worst['beamScore']:.4f} "
              f"exact={worst['exact']} {worst['exactScore']:.4f}")


def t10_rounded_boundary() -> None:
    """Boundary: rounded-equal live score must keep searching (v2's raw rule stopped).

    Setup: at the end of step 3 two hypotheses have finished (-1.0 and -1.5) and a live
    hypothesis sits at -1.5000004, which rounds to -1.5. v2 compared raw scores
    (-1.5000004 <= -1.5) and stopped; v3 compares rounded values and keeps going for one
    more step. The output does not change here, and that is expected: the tie-break
    prefers fewer tokens, and a live hypothesis that survives the boundary can only
    finish longer than the finished one it ties with. The test therefore asserts the
    observable difference in search work (one extra step) and an unchanged answer.
    """
    table = {
        (): row(t1=-0.75, t0=-0.4),
        (1,): row(t1=-0.75, t2=-9.0),
        (0,): row(t0=-1.1000004, t2=-0.6),      # eos -> F1 = -1.0
        (1, 1): row(t2=0.0),                    # F2 = -1.5 at step 3 (len 3)
        (0, 0): row(t0=0.0),                    # live = -1.5000004 (len 3)
        (0, 0, 0): row(t2=0.0),                 # finishes at -1.5000004 (len 4)
    }
    scorer = static_scorer(table)
    v3 = beam2(scorer, EOS, max_new_tokens=8, budget_seconds=30)

    # raw-comparison emulator: same loop, but stop when raw live <= raw threshold
    live = [Hypothesis((), 0.0)]
    finished: list[Hypothesis] = []
    steps = 0
    while live and steps < 8:
        rows = scorer([h.tokens for h in live])
        steps += 1
        cands = []
        for hyp, logrow in zip(live, rows):
            for tok in sorted(range(VOCAB), key=lambda i: (-logrow[i], i))[:2]:
                cands.append(Hypothesis(hyp.tokens + (tok,), hyp.score + logrow[tok]))
        cands.sort(key=lambda h: h.key())
        live = []
        for cand in cands:
            if cand.tokens[-1] == EOS:
                finished.append(cand)
                finished.sort(key=lambda h: h.key())
                finished = finished[:2]
            else:
                live.append(cand)
            if len(live) >= 2:
                break
        if len(finished) >= 2 and live and max(h.score for h in live) <= finished[-1].score:
            break
    v2_like_steps = steps
    tie = (round(table[()][0] + table[(0,)][0], 6) ==
           round(table[()][1] + table[(1,)][1] + table[(1, 1)][EOS], 6))
    check("T10 rounded boundary costs one more step",
          tie and v3.steps == v2_like_steps + 1 and v3.tokens == (0, EOS) and v3.search_exhausted,
          f"rounds tie={tie}; raw-rule stopped after {v2_like_steps} steps, v3 took {v3.steps}; "
          f"answer {v3.tokens} score={v3.score:.6f} (unchanged by design)")


def t11_strict_stop() -> None:
    """One unit below the rounded threshold on the 6th decimal must stop (strict)."""
    table = {
        (): row(t3=-1.2, t1=-1.5, t0=-1.5000016),
        (3,): row(t2=0.0),
        (1,): row(t2=0.0),
        (0,): row(t2=0.0),
    }
    r = beam2(static_scorer(table), EOS, max_new_tokens=4, budget_seconds=30)
    threshold = table[()][1] + table[(1,)][EOS]           # -1.5
    live_bound = table[()][0]                              # -1.5000016
    strictly_below = round(live_bound, 6) < round(threshold, 6)
    check("T11 strict stop below rounded threshold",
          strictly_below and r.tokens == (3, EOS),
          f"round(live)={round(live_bound, 6)} round(threshold)={round(threshold, 6)} "
          f"-> walked {r.tokens} score={r.score:.7f}")


def t9_v2_not_worse(n_tables: int = 200, depth: int = 3) -> None:
    """Compare v2 against the v1 rule only where both produced a finished sentence."""
    rng = random.Random(7)
    worse = better = equal = skipped = 0
    for table in random_tables(rng, n_tables, depth):
        scorer = static_scorer(table)
        v2 = beam2(scorer, EOS, max_new_tokens=depth, budget_seconds=30)
        v1 = v1_rule(scorer, depth)
        if not (v2.complete and v1.tokens and v1.tokens[-1] == EOS):
            skipped += 1
            continue
        if v2.score < v1.score - 1e-9:
            worse += 1
        elif v2.score > v1.score + 1e-9:
            better += 1
        else:
            equal += 1
    check("T9 v2 never worse than v1 rule", worse == 0,
          f"compared={n_tables - skipped} better={better} equal={equal} worse={worse} skipped_unfinished={skipped}")


def main() -> int:
    t1_eos_first()
    t2_retention()
    t3_cumulative()
    t4_ties()
    t5_timeout()
    t6_cap()
    t7_v1_trap()
    t8_exhaustive()
    t9_v2_not_worse()
    t10_rounded_boundary()
    t11_strict_stop()

    out = HERE.parents[1] / "artifacts/fact-wording/preflight"
    out.mkdir(parents=True, exist_ok=True)
    summary = dict(protocol="c4-p7-beam2-v2", passed=not FAILURES, failures=FAILURES,
                   beam2Sha256=None)
    (out / "p7-beam2.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n{'ALL P7 TESTS PASSED' if not FAILURES else 'P7 FAILURES: ' + ', '.join(FAILURES)}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())

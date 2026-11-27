# E24 20-input acceptance on the new default

**Question.** With the micro hybrid workflow now the product default (D-121),
does the formal acceptance set still pass: first readable ≤60 s, turn ≤300 s,
no failures, on 20 real page inputs?

**Setup.** Five frozen chunks (`turns-20-chunk1..5.json`, 4 inputs each),
default query `seed=11` (micro on by default, `taskProposer=micro`, heads
continuation, prose-facts scene narration), desktop Edge, current build.
Evidence: `evidence-20-default-20261127-chunk{1..5}.json`; summary:
`artifacts/goal/acceptance/summary-micro-default-20261127.json`.

**Results.**
- Gates: inputs 20, **firstReadablePass 20/20**, **turnCapPass 20/20**,
  deadline stops 0, failures none.
- First readable 2.7-11.9 s; submission-to-handback 44.9-71.3 s. Four turns
  exceed 60 s on the handback clock (64.2, 71.3, 64.6, 64.1 …), which is the
  product's 60 s *turn* target, not the formal gate (first readable ≤60 s and
  turn ≤300 s); the early-handback arm question is D-024.
- This is the first 20-input acceptance run on the micro default; run41 was on
  the LLM default (and took 210-295 s per turn).

**Conditions.** One seed, one world, desktop only; the summary tool's gates
were used unchanged. The phone lane is measured separately.

**Principle.** Moving the default to the micro workflow keeps the formal
acceptance green on the 20-input set and cuts turn time roughly threefold
against run41; the remaining 60 s handback question is a scheduling decision
(D-024), not a regression.

**Artifacts.** chunk evidence, `summary-micro-default-20261127.json`, D-124.

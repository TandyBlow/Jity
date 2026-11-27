# E22 Mobile-proxy timing: current build vs the E04 baseline

**Question.** E04 measured 276.7/278.1 s per turn under the mobile proxy on an
older build. What does the current build (tasks skip, retrained extraction
head, per-role guard) measure on the identical protocol?

**Setup.** Same two env-success turns (`llm2-turns.json`), same query
(`micro=1&microContinuation=heads&microReaction=1&taskProposer=micro`), same
proxy flags `--cpu-throttle 4 --gpu-lite`, desktop Edge with forced iGPU. One
run, `evidence-mobile-proxy-2.json`.

**Results.**
- Turn 1: 218.6 s (was 276.7 s, −21%). Turn 2: 252.8 s (was 278.1 s, −9%).
  Both completed with 0 problems.
- Narration draft/accepted on the proxy: 22.6/25.5 s and 13.7/22.1 s.
- Still 3.6-4.2× over the 60 s target; the desktop micro arm on the 8
  scenarios is 61.9 s mean, so the proxy slowdown factor is roughly 3.5-4×.

**Conditions.** Desktop Edge under CPU throttling with the iGPU, not a phone
(E04 shows the iGPU path dominates and CPU throttling bounds at 6-15%); two
turns, not the 20-input set. The improvement is consistent with the tasks-stage
skip (D-103) and other build changes but is not attributed per-change here.

**Principle.** The current build is faster on the mobile proxy but nowhere
near the 60 s bar; the bottleneck remains per-call prefill/decode on the iGPU
(E04), so the levers are prompt reuse/chunking and output budget, not call
count. A phone claim still needs a device.

**Artifacts.** `evidence-mobile-proxy-2.json`,
`evidence-mobile-proxy-1.json`, D-120.

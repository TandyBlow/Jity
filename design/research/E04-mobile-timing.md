# E04 Mobile-proxy timing composition

**Question.** Where does the 3.2–3.6× turn slowdown under the mobile proxy come
from — more model calls, or slower calls?

**Setup.** Same two env-success turns, same driver hash, micro arm + shadow.
Arm A: 4× CPU throttle + gpu-lite; arm B: normal. Evidence
`evidence-mobile-proxy-1-*` vs `evidence-no-api-1-*`.

**Results.** Turns 276.7/278.1 s vs 76.7/87.0 s. Wllama wall time is 99.4%/
100.7% of each turn. Of the two-turn excess, 98.1% is generation wall (prefill
57.2%, decode 38.3%, other 2.6%); extra model calls contribute 0% (turn 2 has 4
fewer generations than baseline). Turn-1 composition: action/targets 101.5 s
(36.7%), narration 67.3 s (24.3%), tasks 56.8 s (20.5%), subtasks 39.4 s
(14.2%), results/appearance 10.2 s (3.7%), everything else 1.6 s. Per-call
slowdown: narration decode 5.2–5.3×, semantic prefill 3.9×/token, action
3.0–3.3×, tasks 3.1–3.4×. Engine load is not the cause (ready 28.0 vs 14.7 s;
fetch 1.06–1.12×). A prior same-iGPU A/B bounds CPU throttling at 6–15%; the
iGPU path dominates.

**Conditions.** Desktop Edge with CPU throttling + forced iGPU, not a phone;
two turns; the arm changes CPU and GPU together, so the split is bounded, not
measured.

**Principle.** Mobile cost is dominated by per-call prefill/decode on the iGPU,
not by call count; the levers are prompt reuse/chunking and output budget, and
any claim about phones needs a device (the proxy cannot substitute).

**Artifacts.** `evidence-mobile-proxy-1-*`, `evidence-no-api-1-*`, D-078/D-086.

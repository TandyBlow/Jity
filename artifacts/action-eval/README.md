# Action/targets/reaction evidence

Real on-device runs: headless Edge 157 + wllama + `Qwen3-0.6B-Q4_K_M.gguf`
(sha256 `ac2d9771…`), COOP/COEP, temperature 0, seed 42, max 160 tokens per call.
Each archive records, per case: the exact prompt, every raw completion
(including rejected repair attempts), the decoded value, `source`/`fallback`,
all guard issues, call timings and the scene (visible/absent/items) the handler saw.

## Runs

| archive | code state | outcome |
|---|---|---|
| `dry-prompts.json` | current | no model; 17 scenes/prompts dumped to prove the runnable interface |
| `run-1-unguarded.json` | first handlers | 17 cases / 16 calls, mean 6.3s, p50 7.1s, max 11.3s. Three false-accept classes found (below) |
| `run-2-guarded.json` | after run-1 guards | targets fixed (T3/T5 empty, T4 nono); A3 stopped echoing; A1/A6 fell back; A4b plan-like text accepted; R1/R3 item animation |
| `run-3-action-prompt.json` | contrast example | 6 action cases. The example ("伸手把电池按进卡槽") was copied verbatim into unrelated cases → this prompt direction was rejected |
| `run-4-copy-constraint.json` | "no 8-char copy" rule, example removed | A2 first attempt fixed; A1/A6 still fell back |
| `run-5-subject.json` | "subject must be the actor" | A1/A6 looked fixed but were **false accepts**: the player's sentence with "诺诺" prepended, and Nono's goal as the protagonist's step. Guards tightened, subject rule reverted |
| `run-6-final.json` | delivered code | 17 cases / 16 calls, mean 6.1s, p50 6.9s, max 10.6s. Results below |

## Run-6 final results

- **Action (8)**: A1 unnamed autonomous → fallback inaction (the 0.6B model kept
  restating the player's action; the guard rejected both attempts and never let an
  NPC speak the player's words). A2 named request, A3 named small talk, A7 player
  mentions an absent person → real model actions, accepted first attempt or after
  one repair. A4a off-screen skip → program, 0 calls. A4b off-screen judge →
  accepted a plan-like sentence (quality miss, not a guard catch). A5 pending
  player command → program, 0 calls. A6 consumed protagonist → first attempt echoed
  the player, second attempt "把胸前护目镜推上去" accepted (partial echo remains a
  limitation).
- **Targets (6)**: T1 pronoun single → nono; T2 pronoun ambiguous → fingel
  (argued from the scene); T3 absent person visit → empty + absence recorded; T4
  container scene → nono (Qin in the cage not selectable); T5 movement → empty; T6
  two named people → nono only (under-selection: fingel omitted).
- **Reaction (3)**: R1/R3 model text passes actor/echo/causality guards but still
  invents uncommitted item behaviour ("识别带微微发烫") and does not really answer
  the handed-map threat; R2 protagonist member → program "路明非没有作出反应。",
  0 calls.

## Failures that changed the code

1. **Paraphrase echo accepted** (run-1 A1): the player's action with the subject
   dropped. Fixed with in-order coverage; run-5 showed a prefixed subject evades a
   value-only ratio, so coverage is checked in both directions.
2. **Task goals accepted as actions** (run-1 A4b/A6/A7): fixed with a goal-copy
   guard; run-5 showed another character's goal passing, so all registered
   characters' goals are scanned.
3. **Spurious targets accepted with a warning** (run-1 T3/T4/T5): upgraded to an
   error with one repair; a second failure returns an empty target set (precision
   first: a phantom target forces a roll and a fabricated reaction).
4. **Reaction item animation** (run-1/2/6 R1/R3): prompt forbids it, no program
   guard (would need a sensory-verb list and risks rejecting legitimate events).
5. **Prompt examples copy into unrelated cases** (run-3): a concrete example in
   the instruction became the answer for five cases. The final prompt has only the
   quoted-dialogue example, which did not leak.

Reproduce (self-service lease; do not run while another lane holds it):

```bash
python D:/others/Jity/.local/parallel-local-game/resource_lease.py acquire --lane 03-actions --purpose "action probe"
cd frontend
node scripts/parallel-actions/run-action-eval.mjs \
  --assets D:/others/Jity/.local/world-narration-worktree/frontend/public \
  --out ../artifacts/action-eval/run.json
python D:/others/Jity/.local/parallel-local-game/resource_lease.py release --lane 03-actions
```

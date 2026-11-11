# Archived narration checking (not part of the product)

Per `NARRATION-RAW-OUTPUT-20261111.md`, the runtime no longer inspects, refuses, rewrites or replaces
non-empty model prose. These modules are the old checking stack, kept here as historical review
material:

- `narration-alignment.ts` — entity/event/attribute alignment
- `licensed-sense.ts`, `licensed-action.ts` — licence for actions and senses
- `guidance.ts`, `narration-generation-verify.ts` — revision guidance and the old verifier
- `realize.ts` — the program realizer
- `licensed-action.test.ts` — the one test that stayed with its module

They are outside `frontend/` so they are not compiled or bundled, and nothing under `frontend/src`
imports them. The rest of the old tests were deleted together with the product checks; git history
before `e68ee286` holds them if a historical comparison is ever needed.

Do not wire any of this back into the product without a new user decision.

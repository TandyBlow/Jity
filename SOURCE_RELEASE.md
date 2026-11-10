# Source-only release record

- Branch: `codex/api-small-model-windows-20261110`
- Base: `51bd76e97a8892a6ff012a2ebea57476deb22d4b` (clean D source release; no withdrawn weight-archive ancestry added).
- Active architecture: API for other semantic tasks, D03 MacBERT is the only small-model candidate.
- D03 source/evidence: original R1/R2/R3 data and reports copied without modifying recorded bytes. R3 is NOT quality-approved.
- New portable entry: CPU default, explicit CUDA/MPS, UTF-8, repository-relative paths, teammate-owned R2 checkpoint identity for R3.
- Local checks: original 9 data/metric tests + 4 portable tests + 4 API contract tests passed. Portable tests include the actual 8-epoch entry with a randomly initialized tiny CPU model, in addition to save/reload equality. This is engineering validation, not real MacBERT training or semantic validation.
- No live API calls were made for this release. API tests use controlled fixtures.
- CI: `.github/workflows/api-d03-windows.yml` runs on Windows and Linux after push, with no private API keys, no MacBERT download, and no full-model retraining. The actual GitHub run is the authority for CI status.
- Scope limits: no complete Windows/CUDA MacBERT retraining, browser integration, production state writes or full-chain latency acceptance is claimed.
- Publish audit: `scripts/hybrid/check_release.py` rejects model extensions, LFS pointers, files over 2 MiB, possible credentials and Windows-incompatible paths. Historical existing text evidence below this bound remains in the D baseline.
- All weights, checkpoints, caches and local environments remain outside the tracked release.

## Observed GitHub results for code commit `ccb1fae188ee97294af3d2f19096859635dd28b6`

- [API/D03 source handoff run](https://github.com/TandyBlow/Jity/actions/runs/42804774150): **Windows and Ubuntu both passed**. Includes source-only audit, D03 data/portable CPU tests and mocked API orchestration. This does not mean full Windows/CUDA MacBERT training was run.
- [Inherited application CI](https://github.com/TandyBlow/Jity/actions/runs/42804774056): frontend tests/lint/build passed; backend had 75 failed / 814 passed; world-interface failed on `generated artifact drift: api-contract.json`. Protocol/schema/fixture mismatches remain unresolved.
- `backend/`, `design/world-protocol/`, and inherited `.github/workflows/ci.yml` are byte-identical to base `51bd76e9` in this release. No attempt was made to rewrite the authoritative world protocol as part of a D03 source handoff.
- The following documentation-only commit records these observed results; it does not alter the code tested above.

## Gameplay continuation update (2026-11-10)

- Adds the user-accepted 17-scene subset from four recorded games (train 7 / development 4 / test 6), plus seven excluded candidates and provenance. All four games share one campaign.
- Preserves historical gameplay source/data/reports byte-for-byte; excludes event logs, caches and all weights. Historical author paths are evidence only; PORTABLE.md routes teammates to the supported entry.
- Adds `portable_train.py --stage gameplay`, starting from a teammate-owned R3 run with its actual verified checkpoint and frozen R3 dataset identity. A failed R3 exploratory gate is permitted for this research continuation, not treated as production approval.
- Historical Mac gameplay result: test 5/6 versus parent 1/6; R2 regression 24/24. Still not quality-approved; no integration or deployment.
- Local D03 checks: 16 tests passed, including actual eight-epoch tiny CPU gameplay training, input equivalence and parent preservation. Full Windows/CUDA MacBERT training was not run.
- New commit CI status must be checked independently of the earlier run above. No paid API calls or model publication are part of this update.

## Authoritative D runtime (2026-11-10)

- `D_LINE_AUTHORITY.md` records the user's authoritative two-API-per-unit workflow on this branch.
- Added DLinePort/createDLineDriver over the inherited scheduler/ControllerDriver: local D03, merged results + six updates, sequential A previews including U6, bounded suffix repair, pure-time scan, committed C narration delegation.
- D01 batches use program-issued entity/task IDs and graph preflight. D07 uses fresh final-state evidence and a program-owned next-round allocator; D08 remains a fresh standalone request.
- Added a token-protected loopback Python API/MacBERT bridge. No model weights, API keys or environment files are included. Old run.py remains a historical shadow comparison tool.
- Validation: world TypeScript check passed; 555 world-engine tests passed (28 files); 7 Python hybrid/bridge tests passed. Targeted lint: no errors, seven existing unused-variable warnings. Added a controlled end-to-end D composition with an admitted reaction, six previews, stage, commit and post-commit narration; not a live-model or live-A-service acceptance.
- No paid API invocation, full model training, model publication, or browser deployment was performed. MacBERT quality/support limitations remain unchanged. Match A/B protocol and supply the documented transport/identity/C adapters before live integration.

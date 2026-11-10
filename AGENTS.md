# API + D03 source-only handoff (2026-11-10)

The user explicitly selected the D architecture and only D03 as the small-model task. All other semantic tasks belong to API generation/judgment; deterministic code owns IDs, rolls, admission, freeze, state writes and persistence. The inherited MiniRBT/Qwen/D02 experiments are historical, not active routing.

This release starts from source-only commit 51bd76e97a8892a6ff012a2ebea57476deb22d4b; it does not inherit the withdrawn model-archive commits. Read DEVELOPMENT_WINDOWS.md first. Preserve all existing records and their limitations. D03 R3 is NOT quality-approved or connected to production.

Never commit/push weights, checkpoints, optimizer states, model archives, local environments, .env files or API keys. Use explicit staging paths. Run scripts/hybrid/check_release.py on the staged tracked tree before committing. No LFS pointers in this branch.

Windows entry: experiments/d03-macbert/portable_train.py. Preserve LF bytes and UTF-8. R3 uses the teammate's own completed R2 model with its recorded SHA, not the author's historical model identity. Do not modify original historical scripts/data/reports to make fresh results appear identical.

The historical scripts/hybrid/run.py demo remains offline-development/shadow only. The authoritative D runtime is now documented in D_LINE_AUTHORITY.md: reuse ControllerDriver and A transport, local D03, two API calls per normal settlement unit, sequential previews and bounded suffix repair. Only A may write world state. Tests use mocked API responses; do not spend API credits for packaging unless authorized separately. Do not merge or publish other branches.

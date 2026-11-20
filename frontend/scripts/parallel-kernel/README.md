# Kernel differential fixtures

`fixtures/kernel-differential.json` is generated from the pinned Python world
kernel, not from the browser implementation. It is test data only; the running
game never imports it.

## Source

- Reference commit: `fc60a603c7e0b57805fffea0458192bcfebf6ffc` (`world-server` line).
- World asset: `data/worlds/dragon-raja-free-day.world.json`
  - SHA-256 of the LF-normalized UTF-8 text: `6262d5fcf088959bb427fbd2dfef7472bcf2cbf78edb9c76b98d4ea2b25db92e`
  - SHA-256 of the current working-tree bytes (CRLF checkout): `0a8b63be2932ceb5d597adf332123d8cfb584c2fd92ddd351770d4a9fa09f24a`
  - `world-canonical-v1` state digest: `3f65452daf352c636ac4b24dcefcfb1cc8633ee811a6613a34ce5c43ef233f4e`
  - `world-canonical-v1` initial digest: `c82f058fda8fbe8000887b36b05a9b62a1bf5ae72672f3460472056381061ccb`
- Fixture SHA-256 after generation: `7d68a392bbcd51bb39d276ffc9a37902e919b8c8b9cc1a7e78e74c67d2e2f977`

The fixture's `source.files` block records the SHA-256 of every Python file that
produced the expected values:

| path | sha256 |
|---|---|
| backend/app/schemas/world/canonical.py | 2c2dd4de9fb743d8932d59b9b04e246c5dceda2d61844649732762384b9cfca1 |
| backend/app/schemas/world/contracts.py | 97b0b59b727761565fed1873ded256e3698b49049aae31ce9a5ca6e6f16f4a9c |
| backend/app/schemas/world/v2/work.py | 3e8eebd8e285f872831ae21bf15c2c9678836dd13d77310f57beeeea805a1e31 |
| backend/app/services/world/apply.py | e626fdbb0679ca0cff73053f06b5887bf8a8a0f42280219fdd94b8e4b257af66 |
| backend/app/services/world/merge.py | dbe5fb4b22c62d0bc6bc86599c84227528cb9a636e5728021ad44d748a4647c4 |
| backend/app/services/world/preview.py | 55e7852e74b0db0de9b213833155b33d3577cb8388f43d0c31bd7f4e63fd888d |
| backend/app/services/world/replay.py | af45a5d18bdb4adc08282082f3b7555c48353f7757b574a948f8a3f4f5cde7ed |
| backend/app/services/world/state.py | b13ce5de770e7be883bae03ad682482f097393b597dce7e8d117b151df0a1ed6 |
| backend/app/services/world/timing.py | 3dfd9c8072177dd26cf8875fe0b09881af41f56c3124bea2a60ca29d4d4b2407 |
| backend/app/services/world/units.py | 9f8f080fed827352faa984d381f1d2f0868b789e063d2038939ddf2588111753 |
| backend/app/services/world/violations.py | 84b8a529cb688675f2a7e12da7ed0f84838f58c182f81f1234065644c8fd5e7e |

## Regenerate

```powershell
python -X utf8 frontend/scripts/parallel-kernel/build-kernel-fixtures.py
```

The script extracts `backend/app` from the reference commit into a temporary
directory, imports it there and writes the fixture. It never imports this
worktree's backend. Re-running it with the same reference commit and world file
must reproduce the same fixture hash.

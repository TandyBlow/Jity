# b01 six frozen texts: 01 current-checker diagnosis

- pinned checker: `92eccd94daa58ed9d075ce91d9be93ec96fc260fb9866b767b07700567219d5f`
- current checker: `a7b12f8f87461c1c77c26d031bc64ddabd4c4b84954bfbd701f58bad00fe9eac`
- model rerun: no; N expanded: no; diagnostic only, not a quality pass

| seed | pinned | current | new kinds | gone kinds | coverage |
|---|---|---|---|---|---|
| 17 | fail | fail | - | - | 1/3 |
| 29 | fail | fail | - | - | 1/3 |
| 43 | fail | fail | - | - | 1/3 |
| 61 | fail | fail | - | - | 1/3 |
| 79 | fail | fail | - | - | 1/3 |
| 97 | fail | fail | - | - | 0/3 |

## Handoff checks

```json
{
  "timeMissingStillFlagged": true,
  "personalityOmittedStillFlagged": true,
  "staleRemovedItemCaught": false,
  "traitOwnerOrTraitCopyCaught": false,
  "firstPersonCaught": false,
  "statusRecitalStyleCaught": false
}
```

No reference answer was read. This does not change the pinned b01 result or 01's standard.

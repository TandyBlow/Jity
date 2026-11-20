# Local progress sync service

A standalone storage service for browser-local game snapshots. It stores the
existing `LocalGameSnapshot` as an opaque payload and owns only protocol
metadata: content identity, parent lineage, revision CAS and idempotent request
replay. It does not import the world engine, run inference, roll dice or rewrite
game facts.

## Run

```bash
cd backend
# optional:
#   LOCAL_PROGRESS_DB=data/local_progress.sqlite3
#   LOCAL_PROGRESS_TOKEN=secret
#   LOCAL_PROGRESS_CORS_ORIGINS=http://localhost:3000
python -m uvicorn app.services.local_progress.standalone:app --port 8010
```

Health check: `GET /local-progress/health`.

## Mount into the existing API

The router is independent and deliberately not added to `app/main.py` by this
lane. The integrator adds:

```python
from app.routers.local_progress import router as local_progress_router

app.include_router(local_progress_router)
```

No existing world route or shared database schema is changed. Storage defaults
to `data/local_progress.sqlite3` (ignored by git), configurable with
`LOCAL_PROGRESS_DB`.

## Real-page run (06 product + 09 acceptance)

The product page defaults to `http://127.0.0.1:8000/local-progress`. Either
mount the router into the API that already serves :8000, or run the standalone
service on :8010 and tell the frontend at start time. A browser fetch is
cross-origin, so the page's origin must be in `LOCAL_PROGRESS_CORS_ORIGINS`:

```bash
# progress service
cd backend
LOCAL_PROGRESS_DB=../../.tmp/09-progress/progress.sqlite3 LOCAL_PROGRESS_CORS_ORIGINS=http://127.0.0.1:3221,http://localhost:3221,http://127.0.0.1:3241,http://localhost:3241 python -X utf8 -m uvicorn app.services.local_progress.standalone:app --port 8010 --host 127.0.0.1

# product page, started with the service URL (Next inlines NEXT_PUBLIC_*)
cd worktrees/06-recovery/frontend
NEXT_PUBLIC_LOCAL_PROGRESS_URL=http://127.0.0.1:8010/local-progress npx next dev --port 3221
```

Acceptance runs can leave `LOCAL_PROGRESS_TOKEN` unset (localhost service).
If the token is set, the page must pass it through `createProductSync({ token })`;
the current product page does not, so a token-protected service needs that one
wiring line from 06.

## Protocol

`POST /local-progress/worlds/{worldId}/snapshots`

```json
{
  "requestId": "stable-id-for-retries",
  "parentSnapshotIds": ["snap_..."],
  "expectedHead": "snap_...",
  "expectedRevision": 7,
  "activate": true,
  "payload": { "transport": {}, "commands": [] }
}
```

- `contentDigest` is `sha256(canonical payload)`: content identity only.
- `snapshotId` is `snap_<sha256(worldId + contentDigest + sorted parents)>`: the
  identity of one save document at one lineage position. The same payload may
  legitimately appear as two nodes in two branches; it does not overwrite a
  previous node and does not merge their game facts.
- `parentSnapshotIds` is the lineage DAG edge list (not a timestamp ordering).
- `expectedHead` + `expectedRevision` are the CAS values. A stale pair returns
  HTTP 409 with the current head and branch list; nothing is overwritten.
- `activate: false` stores a fork without moving the head. A later
  `POST /worlds/{worldId}/head` explicitly selects a branch leaf.
- The same `requestId` replayed with the same body returns the original result
  with `idempotent: true` and the current head/revision. Reusing it with a
  different body returns 409 `request_id_reused`. The request log also stores
  the expected head/revision that the CAS was based on.
- Saving the exact current payload again is a no-op (same head, no revision bump).

Reads:

- `GET /local-progress/worlds/{worldId}/head`
- `GET /local-progress/worlds/{worldId}/graph` (all node metadata + leaf IDs)
- `GET /local-progress/worlds/{worldId}/snapshots/{snapshotId}`

## Limits

- payload limit 4 MiB (canonical JSON bytes), configured by
  `LOCAL_PROGRESS_MAX_PAYLOAD_BYTES`;
- 5000 snapshots per world by default (`LOCAL_PROGRESS_MAX_SNAPSHOTS`);
- at most 64 named parents (`LOCAL_PROGRESS_MAX_PARENTS`);
- optional global bearer token (`LOCAL_PROGRESS_TOKEN`), checked with
  constant-time comparison. Per-user authorization is not part of this service.

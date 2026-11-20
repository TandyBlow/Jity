-- Append-only evidence ledger for the new commit path.
-- Kept out of world_storage_v2.sql so the frozen core DDL is untouched:
-- this companion schema is additive and versioned separately.
CREATE TABLE IF NOT EXISTS world_evidence_schema (
    version INTEGER NOT NULL CHECK(version=1)
);

CREATE TABLE IF NOT EXISTS world_point_evidence (
    world_id TEXT NOT NULL,
    point_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence>0),
    previous_point_id TEXT NOT NULL,
    delta_status TEXT NOT NULL CHECK(delta_status IN ('recorded','none')),
    contract TEXT NOT NULL,
    PRIMARY KEY (world_id, point_id)
);

CREATE TABLE IF NOT EXISTS world_evidence (
    evidence_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    point_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence>0),
    entity_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    item_key TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json))
);

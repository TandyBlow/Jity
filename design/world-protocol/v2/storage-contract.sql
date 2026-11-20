-- IF-03 executable storage specification, not an application migration.
-- STRICT requires SQLite >= 3.37. TTL, ownership and transitions use the
-- injected service clock and remain transaction validations (failure-cases.json).
PRAGMA foreign_keys = ON;

CREATE TABLE worlds (
    id TEXT PRIMARY KEY,
    initial_json TEXT NOT NULL CHECK(json_valid(initial_json)),
    version INTEGER NOT NULL DEFAULT 0 CHECK(version BETWEEN 0 AND 9007199254740991),
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision BETWEEN 0 AND 9007199254740991),
    paused INTEGER NOT NULL DEFAULT 0 CHECK(paused IN (0,1)),
    active_point_id TEXT,
    active_round_id TEXT,
    FOREIGN KEY(id,active_point_id) REFERENCES world_points(world_id,id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(id,active_round_id) REFERENCES world_rounds(world_id,id) DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE world_advances (
    world_id TEXT NOT NULL REFERENCES worlds(id), id TEXT NOT NULL, input_id TEXT NOT NULL,
    input_text TEXT, intent_status TEXT NOT NULL CHECK(intent_status IN ('pending','consumed','expired')),
    ended INTEGER NOT NULL DEFAULT 0 CHECK(ended IN (0,1)),
    PRIMARY KEY(world_id,id), UNIQUE(world_id,input_id), CHECK(ended=0 OR input_text IS NULL)
) STRICT;

CREATE TABLE world_rounds (
    world_id TEXT NOT NULL, id TEXT NOT NULL, advance_id TEXT NOT NULL,
    trigger TEXT NOT NULL CHECK(trigger IN ('player','automatic')),
    intent_status TEXT NOT NULL CHECK(intent_status IN ('pending','consumed','expired')),
    phase TEXT NOT NULL CHECK(phase IN ('select_actor','build_group','settle_group','continue_round','assess_continuation','complete')),
    order_json TEXT NOT NULL CHECK(json_valid(order_json) AND json_type(order_json)='array'),
    cursor INTEGER NOT NULL CHECK(cursor>=0 AND cursor<=json_array_length(order_json)),
    acted_json TEXT NOT NULL CHECK(json_valid(acted_json) AND json_type(acted_json)='array'),
    visited_json TEXT NOT NULL CHECK(json_valid(visited_json) AND json_type(visited_json)='array'),
    conclusion_json TEXT CHECK(conclusion_json IS NULL OR json_valid(conclusion_json)),
    PRIMARY KEY(world_id,id), UNIQUE(world_id,id,advance_id),
    FOREIGN KEY(world_id,advance_id) REFERENCES world_advances(world_id,id),
    CHECK(trigger<>'automatic' OR intent_status='consumed'),
    CHECK((phase='complete')=(conclusion_json IS NOT NULL)),
    CHECK(conclusion_json IS NULL OR COALESCE(
        (json_extract(conclusion_json,'$.kind')='continue'
         AND json_extract(conclusion_json,'$.closedBy')='model'
         AND json_type(conclusion_json,'$.cancelReason')='null'
         AND json_type(conclusion_json,'$.candidateCharacterIds')='array'
         AND json_array_length(conclusion_json,'$.candidateCharacterIds')>0
         AND json_type(conclusion_json,'$.nextRoundId')='text') OR
        (json_extract(conclusion_json,'$.kind')='handback' AND
          ((json_extract(conclusion_json,'$.closedBy')='model' AND json_type(conclusion_json,'$.cancelReason')='null') OR
           (json_extract(conclusion_json,'$.closedBy')='cancel' AND json_type(conclusion_json,'$.cancelReason')='text'
            AND length(trim(json_extract(conclusion_json,'$.cancelReason')))>0))),0))
) STRICT;

CREATE TABLE world_points (
    world_id TEXT NOT NULL REFERENCES worlds(id), id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence BETWEEN 0 AND 9007199254740991),
    kind TEXT NOT NULL CHECK(kind IN ('root','normal','instant','linked')),
    previous_point_id TEXT, round_id TEXT, advance_id TEXT, linked_from_point_id TEXT,
    time_json TEXT CHECK(time_json IS NULL OR json_valid(time_json)),
    delta_json TEXT CHECK(delta_json IS NULL OR json_valid(delta_json)),
    state_digest TEXT NOT NULL CHECK(length(state_digest)=64 AND state_digest NOT GLOB '*[^0-9a-f]*'),
    narration_status TEXT NOT NULL CHECK(narration_status IN ('pending','ready','failed','missing')),
    generation INTEGER NOT NULL CHECK(generation BETWEEN 1 AND 9007199254740991),
    claim_token TEXT, claim_mode TEXT CHECK(claim_mode IN ('head','history')),
    claim_epoch INTEGER CHECK(claim_epoch BETWEEN 1 AND 9007199254740991),
    issued_at INTEGER CHECK(issued_at BETWEEN 1 AND 9007199254740991),
    expires_at INTEGER CHECK(expires_at BETWEEN 1 AND 9007199254740991),
    PRIMARY KEY(world_id,id), UNIQUE(world_id,sequence), UNIQUE(world_id,id,generation),
    FOREIGN KEY(world_id,previous_point_id) REFERENCES world_points(world_id,id),
    FOREIGN KEY(world_id,linked_from_point_id) REFERENCES world_points(world_id,id),
    FOREIGN KEY(world_id,round_id,advance_id) REFERENCES world_rounds(world_id,id,advance_id),
    CHECK((kind='root' AND sequence=0 AND previous_point_id IS NULL AND round_id IS NULL
      AND advance_id IS NULL AND linked_from_point_id IS NULL AND time_json IS NULL AND delta_json IS NULL)
      OR (kind<>'root' AND sequence>0 AND previous_point_id IS NOT NULL AND round_id IS NOT NULL
      AND advance_id IS NOT NULL AND time_json IS NOT NULL AND delta_json IS NOT NULL)),
    CHECK(previous_point_id IS NULL OR previous_point_id<>id),
    CHECK(kind NOT IN ('root','normal') OR linked_from_point_id IS NULL),
    CHECK(kind NOT IN ('instant','linked') OR COALESCE(linked_from_point_id=previous_point_id,0)),
    CHECK(COALESCE((claim_token IS NULL AND claim_mode IS NULL AND claim_epoch IS NULL AND issued_at IS NULL AND expires_at IS NULL)
      OR (claim_token IS NOT NULL AND issued_at>0 AND expires_at>issued_at AND
        ((claim_mode='head' AND claim_epoch>0) OR (claim_mode='history' AND claim_epoch IS NULL))),0))
) STRICT;
CREATE UNIQUE INDEX one_root ON world_points(world_id) WHERE kind='root';
CREATE UNIQUE INDEX one_successor ON world_points(world_id,previous_point_id) WHERE previous_point_id IS NOT NULL;

-- Retain the first/player round root-ready guard, not v1's blanket control gate.
-- Pause/resume and raw-copy transactions do not insert rounds and can pass a gate.
CREATE TRIGGER player_round_requires_ready_head BEFORE INSERT ON world_rounds
WHEN NEW.trigger='player' AND NOT EXISTS(
    SELECT 1 FROM worlds w JOIN world_points p ON p.world_id=w.id AND p.id=w.active_point_id
    WHERE w.id=NEW.world_id AND p.narration_status='ready')
BEGIN SELECT RAISE(ABORT,'head_narration_not_ready'); END;

CREATE TABLE world_leases (
    world_id TEXT PRIMARY KEY REFERENCES worlds(id), holder_id TEXT NOT NULL, token TEXT NOT NULL,
    epoch INTEGER NOT NULL CHECK(epoch BETWEEN 1 AND 9007199254740991),
    expires_at INTEGER NOT NULL CHECK(expires_at BETWEEN 1 AND 9007199254740991)
) STRICT;
CREATE TABLE world_gates (
    world_id TEXT PRIMARY KEY REFERENCES worlds(id), point_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK(generation>0), token TEXT NOT NULL,
    epoch INTEGER NOT NULL CHECK(epoch>0), issued_at INTEGER NOT NULL CHECK(issued_at>0),
    expires_at INTEGER NOT NULL CHECK(expires_at>issued_at),
    FOREIGN KEY(world_id,point_id,generation) REFERENCES world_points(world_id,id,generation) DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE world_point_work (
    world_id TEXT NOT NULL, point_id TEXT NOT NULL, round_id TEXT NOT NULL, advance_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('normal','instant','linked')),
    baseline_point_id TEXT NOT NULL, baseline_version INTEGER NOT NULL CHECK(baseline_version>=0),
    baseline_digest TEXT NOT NULL CHECK(length(baseline_digest)=64 AND baseline_digest NOT GLOB '*[^0-9a-f]*'),
    time_json TEXT NOT NULL CHECK(json_valid(time_json)), time_locked INTEGER NOT NULL CHECK(time_locked IN (0,1)),
    sealed INTEGER NOT NULL CHECK(sealed IN (0,1)), prefix_digest TEXT,
    phase TEXT NOT NULL CHECK(phase IN ('select_actor','build_group','settle_group')),
    progress_json TEXT NOT NULL CHECK(json_valid(progress_json)),
    time_scan_json TEXT CHECK(time_scan_json IS NULL OR json_valid(time_scan_json)),
    successor_point_id TEXT, predecessor_point_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('active','consumed','abandoned')),
    PRIMARY KEY(world_id,point_id), UNIQUE(world_id,point_id,round_id,advance_id),
    FOREIGN KEY(world_id,round_id,advance_id) REFERENCES world_rounds(world_id,id,advance_id),
    FOREIGN KEY(world_id,successor_point_id) REFERENCES world_point_work(world_id,point_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(world_id,predecessor_point_id) REFERENCES world_point_work(world_id,point_id) DEFERRABLE INITIALLY DEFERRED,
    CHECK((sealed=1)=(prefix_digest IS NOT NULL)),
    CHECK(prefix_digest IS NULL OR (length(prefix_digest)=64 AND prefix_digest NOT GLOB '*[^0-9a-f]*')),
    CHECK(sealed=0 OR (time_locked=1 AND phase='select_actor'))
) STRICT;
CREATE UNIQUE INDEX one_reservation ON world_point_work(world_id,predecessor_point_id) WHERE predecessor_point_id IS NOT NULL;
-- A reservation's baseline is its SEALED, not-yet-committed predecessor.
-- A direct FK to world_points here would make prepare_successor impossible.
-- The actual prefix/state/time match and atomic promotion remain A3 checks.
CREATE TRIGGER work_baseline_insert BEFORE INSERT ON world_point_work
WHEN NOT (
    (NEW.predecessor_point_id IS NULL AND EXISTS(SELECT 1 FROM world_points p
      WHERE p.world_id=NEW.world_id AND p.id=NEW.baseline_point_id)) OR
    (NEW.predecessor_point_id IS NOT NULL AND NEW.predecessor_point_id=NEW.baseline_point_id AND EXISTS(SELECT 1 FROM world_point_work p
      WHERE p.world_id=NEW.world_id AND p.point_id=NEW.predecessor_point_id AND p.sealed=1 AND p.status='active')))
BEGIN SELECT RAISE(ABORT,'invalid_work_baseline'); END;
CREATE TRIGGER work_baseline_update BEFORE UPDATE OF baseline_point_id,predecessor_point_id ON world_point_work
WHEN NOT (
    (NEW.predecessor_point_id IS NULL AND EXISTS(SELECT 1 FROM world_points p
      WHERE p.world_id=NEW.world_id AND p.id=NEW.baseline_point_id)) OR
    (NEW.predecessor_point_id IS NOT NULL AND NEW.predecessor_point_id=NEW.baseline_point_id AND EXISTS(SELECT 1 FROM world_point_work p
      WHERE p.world_id=NEW.world_id AND p.point_id=NEW.predecessor_point_id AND p.sealed=1 AND p.status='active')))
BEGIN SELECT RAISE(ABORT,'invalid_work_baseline'); END;

CREATE TABLE world_groups (
    world_id TEXT NOT NULL, point_id TEXT NOT NULL, id TEXT NOT NULL,
    source_id TEXT NOT NULL, members_json TEXT NOT NULL CHECK(json_valid(members_json) AND json_type(members_json)='array'),
    status TEXT NOT NULL CHECK(status IN ('open','closed','staged','consumed','abandoned')),
    PRIMARY KEY(world_id,point_id,id), UNIQUE(world_id,id),
    FOREIGN KEY(world_id,point_id) REFERENCES world_point_work(world_id,point_id)
) STRICT;
CREATE TABLE world_settled_units (
    world_id TEXT NOT NULL, point_id TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    group_id TEXT NOT NULL, unit_id TEXT NOT NULL,
    candidates_json TEXT NOT NULL CHECK(json_valid(candidates_json)),
    content_hash TEXT NOT NULL CHECK(length(content_hash)=64 AND content_hash NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY(world_id,point_id,ordinal), UNIQUE(world_id,point_id,group_id), UNIQUE(world_id,unit_id),
    FOREIGN KEY(world_id,point_id,group_id) REFERENCES world_groups(world_id,point_id,id)
) STRICT;
CREATE TABLE world_accepted_work (
    world_id TEXT NOT NULL, point_id TEXT NOT NULL, group_id TEXT NOT NULL, member_id TEXT NOT NULL,
    epoch INTEGER NOT NULL CHECK(epoch BETWEEN 1 AND 9007199254740991),
    attempt INTEGER NOT NULL CHECK(attempt BETWEEN 1 AND 9007199254740991),
    input_projection_hash TEXT NOT NULL CHECK(length(input_projection_hash)=64),
    hashes_json TEXT NOT NULL CHECK(json_valid(hashes_json)),
    PRIMARY KEY(world_id,point_id,group_id,member_id,epoch,attempt),
    FOREIGN KEY(world_id,point_id,group_id) REFERENCES world_groups(world_id,point_id,id)
) STRICT;
CREATE TABLE world_frozen_work (
    world_id TEXT NOT NULL, point_id TEXT NOT NULL, group_id TEXT NOT NULL, member_id TEXT NOT NULL,
    epoch INTEGER NOT NULL, attempt INTEGER NOT NULL,
    action_bytes BLOB NOT NULL, targets_json TEXT CHECK(targets_json IS NULL OR json_valid(targets_json)),
    result_bytes BLOB, candidates_json TEXT CHECK(candidates_json IS NULL OR json_valid(candidates_json)),
    source_epoch INTEGER, source_attempt INTEGER,
    PRIMARY KEY(world_id,point_id,group_id,member_id,epoch,attempt),
    FOREIGN KEY(world_id,point_id,group_id,member_id,epoch,attempt)
      REFERENCES world_accepted_work(world_id,point_id,group_id,member_id,epoch,attempt),
    FOREIGN KEY(world_id,point_id,group_id,member_id,source_epoch,source_attempt)
      REFERENCES world_accepted_work(world_id,point_id,group_id,member_id,epoch,attempt),
    CHECK((source_epoch IS NULL)=(source_attempt IS NULL))
) STRICT;
CREATE TRIGGER accepted_work_immutable BEFORE UPDATE ON world_accepted_work
BEGIN SELECT RAISE(ABORT,'accepted_work_is_immutable'); END;
CREATE TRIGGER frozen_work_immutable BEFORE UPDATE ON world_frozen_work
BEGIN SELECT RAISE(ABORT,'frozen_work_is_immutable'); END;
CREATE TABLE world_work_refs (
    world_id TEXT NOT NULL, point_id TEXT NOT NULL, group_id TEXT NOT NULL, member_id TEXT NOT NULL,
    epoch INTEGER NOT NULL, attempt INTEGER NOT NULL,
    PRIMARY KEY(world_id,point_id,group_id,member_id),
    FOREIGN KEY(world_id,point_id,group_id,member_id,epoch,attempt)
      REFERENCES world_accepted_work(world_id,point_id,group_id,member_id,epoch,attempt)
) STRICT;
-- Scope by current epoch BEFORE choosing maximum attempt; TTL checked by service.
CREATE VIEW visible_frozen_work AS
SELECT f.* FROM world_frozen_work f JOIN world_leases l ON l.world_id=f.world_id AND l.epoch=f.epoch
JOIN world_point_work p ON p.world_id=f.world_id AND p.point_id=f.point_id AND p.status='active'
JOIN world_groups g ON g.world_id=f.world_id AND g.point_id=f.point_id AND g.id=f.group_id
WHERE g.status IN ('open','closed','staged') AND f.attempt=(
    SELECT max(a.attempt) FROM world_frozen_work a WHERE a.world_id=f.world_id AND a.point_id=f.point_id
      AND a.group_id=f.group_id AND a.member_id=f.member_id AND a.epoch=l.epoch);

CREATE TABLE world_rolls (
    world_id TEXT NOT NULL, id TEXT NOT NULL, point_id TEXT NOT NULL, round_id TEXT NOT NULL,
    advance_id TEXT NOT NULL, group_id TEXT NOT NULL, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
    trigger_key TEXT NOT NULL, rule_version TEXT NOT NULL CHECK(rule_version IN ('reaction-fixture-v1','reaction-d20-v1')),
    result INTEGER NOT NULL CHECK(result BETWEEN 1 AND 20), target INTEGER NOT NULL CHECK(target BETWEEN 1 AND 20),
    eligibility_digest TEXT NOT NULL CHECK(length(eligibility_digest)=64),
    eligible INTEGER NOT NULL CHECK(eligible IN (0,1)), admitted INTEGER NOT NULL CHECK(admitted IN (0,1)),
    PRIMARY KEY(world_id,id), UNIQUE(world_id,round_id,group_id,source_id,target_id,trigger_key),
    FOREIGN KEY(world_id,point_id,round_id,advance_id) REFERENCES world_point_work(world_id,point_id,round_id,advance_id),
    FOREIGN KEY(world_id,point_id,group_id) REFERENCES world_groups(world_id,point_id,id),
    CHECK(admitted=(eligible=1 AND result>=target)), CHECK(rule_version<>'reaction-d20-v1' OR target=11)
) STRICT;
CREATE TRIGGER roll_immutable BEFORE UPDATE ON world_rolls
BEGIN SELECT RAISE(ABORT,'roll_is_final'); END;

CREATE TABLE world_submissions (
    world_id TEXT NOT NULL REFERENCES worlds(id), request_id TEXT NOT NULL, operation TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK(length(request_hash)=64), result_json TEXT NOT NULL CHECK(json_valid(result_json)),
    PRIMARY KEY(world_id,request_id)
) STRICT;
CREATE TRIGGER no_input_in_submission BEFORE INSERT ON world_submissions
WHEN EXISTS(SELECT 1 FROM json_tree(NEW.result_json) WHERE key IN ('inputText','activeInput','actionText','claimToken'))
BEGIN SELECT RAISE(ABORT,'private_payload_in_idempotency_result'); END;
CREATE TABLE world_creations (
    request_id TEXT PRIMARY KEY, world_id TEXT NOT NULL UNIQUE REFERENCES worlds(id),
    request_hash TEXT NOT NULL, result_json TEXT NOT NULL CHECK(json_valid(result_json))
) STRICT;
CREATE TABLE world_copy_results (
    world_id TEXT NOT NULL, point_id TEXT NOT NULL, group_id TEXT NOT NULL, target_epoch INTEGER NOT NULL CHECK(target_epoch>0),
    source_epoch INTEGER NOT NULL CHECK(source_epoch>0), source_attempt INTEGER NOT NULL CHECK(source_attempt>0),
    manifest_hash TEXT NOT NULL CHECK(length(manifest_hash)=64), attempt INTEGER NOT NULL CHECK(attempt>0),
    PRIMARY KEY(world_id,point_id,group_id,target_epoch,source_epoch,source_attempt,manifest_hash),
    FOREIGN KEY(world_id,point_id,group_id) REFERENCES world_groups(world_id,point_id,id)
) STRICT;
CREATE TABLE world_id_allocations (
    world_id TEXT NOT NULL REFERENCES worlds(id), allocation_key TEXT NOT NULL, slot_key TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('advance','input','round','point','group','trigger','task','change')),
    allocated_id TEXT NOT NULL, scope_json TEXT NOT NULL CHECK(json_valid(scope_json)),
    PRIMARY KEY(world_id,allocation_key,slot_key), UNIQUE(world_id,allocated_id)
) STRICT;
CREATE TABLE world_narrations (
    world_id TEXT NOT NULL, point_id TEXT NOT NULL, generation INTEGER NOT NULL CHECK(generation>0),
    text TEXT NOT NULL, PRIMARY KEY(world_id,point_id,generation),
    FOREIGN KEY(world_id,point_id) REFERENCES world_points(world_id,id)
) STRICT;
CREATE TABLE world_state_checkpoints (
    world_id TEXT NOT NULL, point_id TEXT NOT NULL, canonical_version TEXT NOT NULL CHECK(canonical_version='world-canonical-v1'),
    state_json TEXT NOT NULL CHECK(json_valid(state_json)), state_digest TEXT NOT NULL CHECK(length(state_digest)=64),
    PRIMARY KEY(world_id,point_id), FOREIGN KEY(world_id,point_id) REFERENCES world_points(world_id,id)
) STRICT;

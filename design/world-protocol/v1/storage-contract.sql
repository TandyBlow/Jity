-- Stage-0 executable contract reference, NOT an application migration.
-- Dynamic head/lease/time/transition validation remains a later service task.
PRAGMA foreign_keys = ON;

CREATE TABLE worlds (
    id TEXT PRIMARY KEY,
    initial_json TEXT NOT NULL CHECK (json_valid(initial_json)),
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    active_point_id TEXT,
    active_round_id TEXT,
    checkpoint_revision INTEGER NOT NULL DEFAULT 0 CHECK (checkpoint_revision >= 0),
    FOREIGN KEY (id, active_point_id) REFERENCES world_points(world_id, id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (id, active_round_id) REFERENCES world_round_checkpoints(world_id, round_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE world_round_checkpoints (
    world_id TEXT NOT NULL REFERENCES worlds(id),
    round_id TEXT NOT NULL,
    advance_id TEXT NOT NULL,
    input_id TEXT NOT NULL,
    input_text TEXT,
    intent_status TEXT NOT NULL CHECK (intent_status IN ('pending','consumed','expired')),
    revision INTEGER NOT NULL CHECK (revision >= 0),
    trigger TEXT NOT NULL CHECK (trigger IN ('player','automatic')),
    phase TEXT NOT NULL CHECK (phase IN (
        'select_actor','build_group','settle_group','await_narration',
        'continue_round','assess_continuation','paused','complete')),
    resume_phase TEXT CHECK (resume_phase IN (
        'select_actor','build_group','settle_group','continue_round','assess_continuation','complete')),
    pending_group_json TEXT CHECK (pending_group_json IS NULL OR json_valid(pending_group_json)),
    conclusion_json TEXT CHECK (conclusion_json IS NULL OR json_valid(conclusion_json)),
    order_json TEXT NOT NULL CHECK (json_valid(order_json)),
    cursor INTEGER NOT NULL CHECK (cursor >= 0),
    acted_ids_json TEXT NOT NULL CHECK (json_valid(acted_ids_json)),
    visited_ids_json TEXT NOT NULL CHECK (json_valid(visited_ids_json)),
    PRIMARY KEY (world_id, round_id),
    UNIQUE (world_id, round_id, advance_id),
    CHECK (trigger <> 'automatic' OR intent_status = 'consumed'),
    CHECK ((phase IN ('paused','await_narration')) = (resume_phase IS NOT NULL)),
    CHECK ((phase = 'complete') = (conclusion_json IS NOT NULL)),
    CHECK (phase NOT IN ('complete','assess_continuation') OR pending_group_json IS NULL),
    CHECK (phase NOT IN ('build_group','settle_group') OR pending_group_json IS NOT NULL),
    CHECK (conclusion_json IS NULL OR COALESCE(
        (json_extract(conclusion_json,'$.kind') = 'continue'
         AND json_extract(conclusion_json,'$.closedBy') = 'model'
         AND json_type(conclusion_json,'$.cancelReason') = 'null'
         AND json_type(conclusion_json,'$.candidateCharacterIds') = 'array'
         AND json_array_length(conclusion_json,'$.candidateCharacterIds') > 0
         AND json_type(conclusion_json,'$.nextRoundId') = 'text')
        OR
        (json_extract(conclusion_json,'$.kind') = 'handback'
         AND ((json_extract(conclusion_json,'$.closedBy') = 'model'
               AND json_type(conclusion_json,'$.cancelReason') = 'null')
              OR (json_extract(conclusion_json,'$.closedBy') = 'cancel'
                  AND json_type(conclusion_json,'$.cancelReason') = 'text'
                  AND length(trim(json_extract(conclusion_json,'$.cancelReason'),
                      char(9)||char(10)||char(11)||char(12)||char(13)||
                      char(28)||char(29)||char(30)||char(31)||char(32)||char(133)||
                      char(160)||char(5760)||char(8192)||char(8193)||char(8194)||
                      char(8195)||char(8196)||char(8197)||char(8198)||char(8199)||
                      char(8200)||char(8201)||char(8202)||char(8232)||char(8233)||
                      char(8239)||char(8287)||char(12288))) > 0))), 0))
);

CREATE TABLE world_points (
    world_id TEXT NOT NULL REFERENCES worlds(id),
    id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    kind TEXT NOT NULL CHECK (kind IN ('root','normal','instant','linked')),
    previous_point_id TEXT,
    round_id TEXT,
    advance_id TEXT,
    trigger TEXT CHECK (trigger IN ('player','automatic')),
    linked_from_point_id TEXT,
    time_advance TEXT CHECK (time_advance IS NULL OR json_valid(time_advance)),
    entity_deltas TEXT CHECK (entity_deltas IS NULL OR json_valid(entity_deltas)),
    state_hash TEXT NOT NULL,
    narration_status TEXT NOT NULL DEFAULT 'pending' CHECK (narration_status IN ('pending','ready','failed')),
    narration_generation INTEGER NOT NULL DEFAULT 0 CHECK (narration_generation >= 0),
    narration_claim_token TEXT,
    narration_claim_expires_at INTEGER,
    narration_claim_mode TEXT CHECK (narration_claim_mode IN ('head','history')),
    narration_claim_fence_epoch INTEGER,
    narration_error_code TEXT,
    PRIMARY KEY (world_id,id),
    UNIQUE (world_id,sequence),
    FOREIGN KEY (world_id,previous_point_id) REFERENCES world_points(world_id,id),
    FOREIGN KEY (world_id,linked_from_point_id) REFERENCES world_points(world_id,id),
    FOREIGN KEY (world_id,round_id,advance_id)
        REFERENCES world_round_checkpoints(world_id,round_id,advance_id),
    CHECK ((kind='root' AND sequence=0 AND previous_point_id IS NULL
        AND round_id IS NULL AND advance_id IS NULL AND trigger IS NULL
        AND linked_from_point_id IS NULL AND time_advance IS NULL AND entity_deltas IS NULL)
        OR (kind<>'root' AND sequence>0 AND previous_point_id IS NOT NULL
        AND round_id IS NOT NULL AND advance_id IS NOT NULL AND trigger IS NOT NULL
        AND time_advance IS NOT NULL AND entity_deltas IS NOT NULL)),
    CHECK (previous_point_id IS NULL OR previous_point_id <> id),
    CHECK (kind NOT IN ('root','normal') OR linked_from_point_id IS NULL),
    CHECK (kind NOT IN ('instant','linked') OR COALESCE(linked_from_point_id=previous_point_id,0)),
    CHECK (COALESCE((narration_claim_token IS NULL AND narration_claim_mode IS NULL
        AND narration_claim_fence_epoch IS NULL AND narration_claim_expires_at IS NULL)
        OR (narration_claim_token IS NOT NULL AND narration_generation>0
        AND narration_claim_expires_at>0 AND
           ((narration_claim_mode='head' AND narration_claim_fence_epoch>0)
            OR (narration_claim_mode='history' AND narration_claim_fence_epoch IS NULL))),0))
);
CREATE UNIQUE INDEX one_world_root ON world_points(world_id) WHERE kind='root';
CREATE UNIQUE INDEX one_world_successor ON world_points(world_id,previous_point_id)
    WHERE previous_point_id IS NOT NULL;

-- Executable stage-0 gate: the first round cannot bypass root narration.
CREATE TRIGGER round_requires_ready_head
BEFORE INSERT ON world_round_checkpoints
WHEN NOT EXISTS (
    SELECT 1 FROM worlds w JOIN world_points p
      ON p.world_id=w.id AND p.id=w.active_point_id
    WHERE w.id=NEW.world_id AND p.narration_status='ready'
)
BEGIN
    SELECT RAISE(ABORT, 'head_narration_not_ready');
END;

CREATE TABLE world_leases (
    world_id TEXT PRIMARY KEY REFERENCES worlds(id),
    holder_id TEXT,
    lease_token TEXT,
    fence_epoch INTEGER NOT NULL CHECK (fence_epoch >= 0),
    expires_at INTEGER NOT NULL,
    CHECK ((holder_id IS NULL) = (lease_token IS NULL))
);

CREATE TABLE world_submissions (
    world_id TEXT NOT NULL REFERENCES worlds(id),
    request_id TEXT NOT NULL,
    operation_kind TEXT NOT NULL,
    advance_id TEXT,
    content_digest TEXT NOT NULL,
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    PRIMARY KEY (world_id,request_id)
);

CREATE TABLE world_rolls (
    world_id TEXT NOT NULL,
    id TEXT NOT NULL,
    advance_id TEXT NOT NULL,
    round_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    trigger_key TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    result INTEGER NOT NULL CHECK (result BETWEEN 1 AND 20),
    target INTEGER NOT NULL CHECK (target BETWEEN 1 AND 20),
    PRIMARY KEY (world_id,id),
    UNIQUE (world_id,round_id,group_id,source_id,target_id,trigger_key),
    FOREIGN KEY (world_id,round_id,advance_id)
        REFERENCES world_round_checkpoints(world_id,round_id,advance_id)
);

CREATE TABLE world_id_allocations (
    world_id TEXT NOT NULL REFERENCES worlds(id),
    allocation_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    allocated_id TEXT NOT NULL,
    scope_json TEXT NOT NULL CHECK (json_valid(scope_json)),
    PRIMARY KEY (world_id,allocation_key,kind),
    UNIQUE (world_id,allocated_id)
);

CREATE TABLE world_narrations (
    world_id TEXT NOT NULL,
    point_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation>0),
    text TEXT NOT NULL,
    model_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    PRIMARY KEY (world_id,point_id,generation),
    FOREIGN KEY (world_id,point_id) REFERENCES world_points(world_id,id)
);

CREATE TABLE world_state_checkpoints (
    world_id TEXT NOT NULL,
    point_id TEXT NOT NULL,
    canonical_version TEXT NOT NULL CHECK (canonical_version='world-canonical-v1'),
    state_json TEXT NOT NULL CHECK (json_valid(state_json)),
    state_hash TEXT NOT NULL,
    PRIMARY KEY (world_id,point_id),
    FOREIGN KEY (world_id,point_id) REFERENCES world_points(world_id,id)
);

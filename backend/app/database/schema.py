"""SQLite DDL and column migrations."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS game_sessions (
  id TEXT PRIMARY KEY,
  game_name TEXT NOT NULL,
  model TEXT NOT NULL,
  state_json TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 0,
  active_turn_id INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaign_progress (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id TEXT NOT NULL,
  slot_name TEXT NOT NULL DEFAULT 'default',
  arc_index INTEGER NOT NULL DEFAULT 0,
  session_index INTEGER NOT NULL DEFAULT 0,
  turn_in_session INTEGER NOT NULL DEFAULT 0,
  fsm_state TEXT NOT NULL DEFAULT 'idle',
  revealed_anchors TEXT NOT NULL DEFAULT '[]',
  completed_arcs TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(campaign_id, slot_name)
);

CREATE TABLE IF NOT EXISTS session_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  turn_node_id INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (session_id) REFERENCES game_sessions(id)
);

CREATE TABLE IF NOT EXISTS story_turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  parent_turn_id INTEGER,
  depth INTEGER NOT NULL DEFAULT 0,
  player_action TEXT NOT NULL DEFAULT '',
  output_json TEXT,
  state_json TEXT NOT NULL,
  campaign_progress_json TEXT NOT NULL DEFAULT '{}',
  model TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'scripted',
  model_output_id INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (session_id) REFERENCES game_sessions(id),
  FOREIGN KEY (parent_turn_id) REFERENCES story_turns(id),
  FOREIGN KEY (model_output_id) REFERENCES model_outputs(id)
);

CREATE INDEX IF NOT EXISTS idx_story_turns_session_parent
  ON story_turns(session_id, parent_turn_id);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  keywords TEXT NOT NULL DEFAULT '[]',
  importance INTEGER NOT NULL DEFAULT 3,
  source_path TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_outputs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  model TEXT NOT NULL,
  input_text TEXT NOT NULL,
  output_json TEXT NOT NULL,
  latency_ms INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'llm',
  status TEXT NOT NULL DEFAULT 'ok',
  raw_output_text TEXT NOT NULL DEFAULT '',
  error_text TEXT NOT NULL DEFAULT '',
  retrieved_chunks_json TEXT NOT NULL DEFAULT '[]',
  prompt_sections_json TEXT NOT NULL DEFAULT '{}',
  prompt_text TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (session_id) REFERENCES game_sessions(id)
);

-- commit-turn idempotency (design/component-io-and-commit-turn.md §3.1).
-- One row per accepted submission attempt: replaying the same requestId
-- with the same content digest returns result_json verbatim and never
-- moves the session head again.
CREATE TABLE IF NOT EXISTS turn_submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  content_digest TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(session_id, request_id),
  FOREIGN KEY (session_id) REFERENCES game_sessions(id)
);

-- commit-turn pending-task ledger (design §4). Stateful claims (review
-- round 6): 'running' proves WORK IN FLIGHT, not success — recovery may
-- re-claim a stale running claim (timeout or dead executor) but must not
-- confirm it away; 'done' + result_json prove the effect was applied and
-- saved in a confirm transaction. The maintainer is a PURE function that
-- RETURNS a candidate result; the confirm transaction applies binding
-- checks, the result, the done record and the queue change atomically.
CREATE TABLE IF NOT EXISTS memory_task_claims (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  task_key TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'running',
  executor TEXT,
  result_json TEXT NOT NULL DEFAULT '{}',
  claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(session_id, task_key),
  FOREIGN KEY (session_id) REFERENCES game_sessions(id)
);

CREATE TABLE IF NOT EXISTS evaluations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model_output_id INTEGER NOT NULL,
  coherence INTEGER,
  lore_consistency INTEGER,
  npc_consistency INTEGER,
  action_relevance INTEGER,
  creativity INTEGER,
  controllability INTEGER,
  playability INTEGER,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (model_output_id) REFERENCES model_outputs(id)
);
"""

# (table, column, definition) — added lazily for older databases
_COLUMN_MIGRATIONS = [
    ("model_outputs", "source", "TEXT NOT NULL DEFAULT 'llm'"),
    ("model_outputs", "status", "TEXT NOT NULL DEFAULT 'ok'"),
    ("model_outputs", "raw_output_text", "TEXT NOT NULL DEFAULT ''"),
    ("model_outputs", "error_text", "TEXT NOT NULL DEFAULT ''"),
    ("model_outputs", "retrieved_chunks_json", "TEXT NOT NULL DEFAULT '[]'"),
    # What the prompt actually contained, per turn. Without these the injected
    # campaign context is unrecoverable after the fact.
    ("model_outputs", "prompt_sections_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("model_outputs", "prompt_text", "TEXT NOT NULL DEFAULT ''"),
    ("knowledge_chunks", "importance", "INTEGER NOT NULL DEFAULT 3"),
    ("game_sessions", "version", "INTEGER NOT NULL DEFAULT 0"),
    ("game_sessions", "active_turn_id", "INTEGER"),
    ("model_outputs", "word_count", "INTEGER NOT NULL DEFAULT 0"),
    ("model_outputs", "option_count", "INTEGER NOT NULL DEFAULT 0"),
    ("model_outputs", "sanity_delta", "INTEGER NOT NULL DEFAULT 0"),
    ("model_outputs", "health_delta", "INTEGER NOT NULL DEFAULT 0"),
    ("model_outputs", "dialogue_lines", "INTEGER NOT NULL DEFAULT 0"),
    ("model_outputs", "location_changed", "INTEGER NOT NULL DEFAULT 0"),
    ("model_outputs", "token_count", "INTEGER NOT NULL DEFAULT 0"),
    ("campaign_progress", "turn_in_session", "INTEGER NOT NULL DEFAULT 0"),
    ("campaign_progress", "recap_compressed", "TEXT NOT NULL DEFAULT ''"),
    ("campaign_progress", "recap_full", "TEXT NOT NULL DEFAULT ''"),
    ("game_sessions", "campaign_id", "TEXT"),
    ("game_sessions", "campaign_filename", "TEXT"),
    ("game_sessions", "active_slot_name", "TEXT NOT NULL DEFAULT 'default'"),
    ("session_messages", "campaign_session_index", "INTEGER NOT NULL DEFAULT 0"),
    # Messages remember the ARC the action happened in: session_index resets
    # to 0 at every arc boundary, so arc1/session0 would collide with
    # arc0/session0 in message filtering (review round 6).
    ("session_messages", "campaign_arc_index", "INTEGER NOT NULL DEFAULT 0"),
    ("session_messages", "turn_node_id", "INTEGER"),
    ("campaign_progress", "npc_relations", "TEXT NOT NULL DEFAULT '[]'"),
    ("campaign_progress", "head_turn_id", "INTEGER"),
    # commit-turn: audit entry + server-recomputed roll record per submission.
    ("model_outputs", "audit_json", "TEXT NOT NULL DEFAULT '{}'"),
    # commit-turn pending-task ledger: stateful claims (v3.4).
    ("memory_task_claims", "state", "TEXT NOT NULL DEFAULT 'running'"),
    ("memory_task_claims", "executor", "TEXT"),
    ("memory_task_claims", "result_json", "TEXT NOT NULL DEFAULT '{}'"),
]


def ensure_column(db, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_schema(db) -> None:
    """Create tables and apply column migrations on a live connection."""
    db.executescript(SCHEMA_SQL)
    for table, column, definition in _COLUMN_MIGRATIONS:
        ensure_column(db, table, column, definition)
    _migrate_campaign_progress_pk(db)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_messages_turn ON session_messages(turn_node_id)"
    )


def _migrate_campaign_progress_pk(db) -> None:
    """Migrate campaign_progress: old PK → auto-increment id + UNIQUE(campaign_id, slot_name)."""
    existing_cols = {row["name"] for row in db.execute("PRAGMA table_info(campaign_progress)")}
    if "id" not in existing_cols:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS campaign_progress_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL,
                slot_name TEXT NOT NULL DEFAULT 'default',
                arc_index INTEGER NOT NULL DEFAULT 0,
                session_index INTEGER NOT NULL DEFAULT 0,
                turn_in_session INTEGER NOT NULL DEFAULT 0,
                fsm_state TEXT NOT NULL DEFAULT 'idle',
                revealed_anchors TEXT NOT NULL DEFAULT '[]',
                completed_arcs TEXT NOT NULL DEFAULT '[]',
                recap_compressed TEXT NOT NULL DEFAULT '',
                recap_full TEXT NOT NULL DEFAULT '',
                npc_relations TEXT NOT NULL DEFAULT '[]',
                head_turn_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(campaign_id, slot_name)
            );
            INSERT OR IGNORE INTO campaign_progress_new
                (campaign_id, slot_name, arc_index, session_index, turn_in_session,
                 fsm_state, revealed_anchors, completed_arcs, recap_compressed, recap_full)
                SELECT campaign_id, 'default', arc_index, session_index, turn_in_session,
                       fsm_state, revealed_anchors, completed_arcs,
                       COALESCE(recap_compressed, ''), COALESCE(recap_full, '')
                FROM campaign_progress;
            DROP TABLE campaign_progress;
            ALTER TABLE campaign_progress_new RENAME TO campaign_progress;
        """)
        ensure_column(db, "campaign_progress", "npc_relations", "TEXT NOT NULL DEFAULT '[]'")
        ensure_column(db, "campaign_progress", "head_turn_id", "INTEGER")

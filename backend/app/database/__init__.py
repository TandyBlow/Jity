"""Database package — SQLite access layer.

Modules:
  - connection:      Database core (connection context manager, schema bootstrap)
  - schema:          DDL, column migrations and PK migration
  - sessions:        game session + message persistence
  - campaign_store:  campaign progress persistence
  - knowledge_store: knowledge chunk persistence
  - outputs:         model output persistence
"""

from app.database.connection import Database

__all__ = ["Database"]

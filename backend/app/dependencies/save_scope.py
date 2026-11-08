"""Save ownership seam for future authenticated accounts; purpose is not auth."""

from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Header, HTTPException

SavePurpose = Literal["user", "development", "test", "legacy"]


@dataclass(frozen=True)
class SaveScope:
    account_id: str | None = None
    purpose: SavePurpose = "development"


def get_save_scope(
    purpose: Annotated[SavePurpose, Header(alias="X-Jity-Save-Purpose")] = "development",
) -> SaveScope:
    # No login exists yet: only unassigned saves are visible. When authentication
    # is added, derive account_id from the verified principal HERE, never from a
    # client-supplied account ID, browser ID, display name or query parameter.
    return SaveScope(account_id=None, purpose=purpose)


def require_owned_session(row, scope: SaveScope) -> None:
    if row is None or row["account_id"] != scope.account_id:
        raise HTTPException(status_code=404, detail="Session not found")

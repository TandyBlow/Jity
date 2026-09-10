"""Thread-safe CampaignManager cache with TTL eviction."""

import threading
import time

from app.dependencies.singletons import db, health_monitor, llm_client, prompt_builder, scripted_story, settings
from app.services.campaign_manager import CampaignManager


class CampaignManagerCache:
    """Thread-safe LRU-like cache for CampaignManager instances.

    Replaces the bare ``campaign_managers: dict`` + ``_evict_stale_managers``
    that lived at module scope in main.py.
    """

    _TTL = 3600  # 1 hour

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: dict[tuple[str, str], tuple[float, CampaignManager]] = {}

    def get(self, session_id: str, slot_name: str) -> CampaignManager | None:
        """Return cached manager or *None*.  Refreshes timestamp on hit."""
        with self._lock:
            self._evict()
            key = (session_id, slot_name)
            if key in self._cache:
                ts, mgr = self._cache[key]
                self._cache[key] = (time.time(), mgr)
                return mgr
        return None

    def put(self, session_id: str, slot_name: str, manager: CampaignManager) -> None:
        with self._lock:
            self._cache[(session_id, slot_name)] = (time.time(), manager)

    def invalidate(self, session_id: str, slot_name: str) -> None:
        with self._lock:
            self._cache.pop((session_id, slot_name), None)

    def _evict(self) -> None:
        """Remove entries older than TTL. Caller must hold ``_lock``."""
        now = time.time()
        stale = [k for k, (ts, _) in self._cache.items() if now - ts > self._TTL]
        for k in stale:
            self._cache.pop(k, None)

    def get_or_load(
        self,
        session_id: str,
        slot_name: str,
        session_row: dict,
    ) -> CampaignManager | None:
        """Return the manager, loading from DB if not cached.

        Validates cached entry against the session's current campaign_filename
        to prevent stale managers after campaign switch.
        """
        with self._lock:
            self._evict()
            key = (session_id, slot_name)
            if key in self._cache:
                ts, mgr = self._cache[key]
                # Refresh timestamp on hit
                self._cache[key] = (time.time(), mgr)
                return mgr

        # Not cached — try to load
        if not session_row or not session_row["campaign_filename"]:
            return None

        campaign_path = settings.campaigns_dir / session_row["campaign_filename"]
        if not campaign_path.exists():
            return None

        manager = build_campaign_manager()
        manager.load(
            campaign_path,
            campaign_id=session_row["campaign_id"] or session_id,
            slot_name=slot_name,
        )

        with self._lock:
            self._cache[(session_id, slot_name)] = (time.time(), manager)

        return manager


campaign_manager_cache = CampaignManagerCache()


def build_campaign_manager() -> CampaignManager:
    """Factory used by both routes and cache to create fresh managers."""
    return CampaignManager(
        db=db,
        campaigns_dir=settings.campaigns_dir,
        scripted_story=scripted_story,
        prompt_builder=prompt_builder,
        llm_client=llm_client,
        health_monitor=health_monitor,
    )


def get_campaign_manager_for_session(
    session_id: str, slot_name: str = "default"
) -> CampaignManager | None:
    """Public helper preserving the old ``get_campaign_manager_for_session`` API."""
    session_row = db.get_session(session_id)
    if not session_row:
        return None
    active_slot = slot_name or session_row["active_slot_name"] or "default"
    return campaign_manager_cache.get_or_load(session_id, active_slot, session_row)

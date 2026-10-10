"""Snapshot-owned memory jobs; a worker never mutates the live controller."""

import asyncio
import json
from uuid import uuid4

from app.services.memory.memory_controller import MemoryController


class MemoryLifecycleMixin:
    async def _wait_memory(self, session_id: str) -> None:
        job = self._memory_jobs.get(session_id)
        if job is not None:
            await asyncio.gather(job, return_exceptions=True)

    def _schedule_memory(self, session_id, turn_id, state, campaign_manager) -> None:
        controller = self._get_memory_controller(session_id, state, campaign_manager)
        snapshot = controller.export_state()
        # Capture the source branch's committed dialogue now, before any await.
        dialogues = controller._get_recent_dialogues(session_id, campaign_session_index=state.get("_campaign_session_index"))
        job = asyncio.create_task(self._maintain_memory_snapshot(
            session_id, turn_id, state.get("turn", 0), snapshot, dialogues, controller._embedding,
            list(controller.nsb._embedding_cache),
        ))
        self._memory_jobs[session_id] = job
        self._memory_tasks.add(job)
        job.add_done_callback(self._log_memory_task_done)
        job.add_done_callback(lambda done: self._memory_jobs.pop(session_id, None)
                              if self._memory_jobs.get(session_id) is done else None)

    async def _maintain_memory_snapshot(self, session_id, turn_id, turn, snapshot, dialogues, embedding=None, embedding_cache=()):
        worker = MemoryController(self.llm_client, self.db, session_id, embedding_client=embedding)
        worker.load_state(snapshot)
        worker.nsb._embedding_cache = list(embedding_cache)
        await worker.maintain(session_id, turn, dialogues=dialogues)
        worker.version = uuid4().hex
        if self.db.commit_memory_snapshot(session_id, turn_id, snapshot["version"], worker.export_state()):
            self._memory_controllers[session_id] = worker

    def _feed_memory(self, session_id, state, output, action, campaign_manager):
        controller = self._get_memory_controller(session_id, state, campaign_manager)
        narration = output.narration + "\n" + "\n".join(f"{d.speaker}: {d.text}" for d in output.dialogue)
        updates = output.memory_updates.model_dump()
        updates["items_upserted"] += output.items_gained
        updates["items_removed"] += output.items_lost
        updates["npcs_upserted"] += output.npcs_encountered
        updates["quests_upserted"] += output.quests_updated
        narration += "\n[权威物品状态] " + json.dumps(controller.score_tracker.get_all_states(), ensure_ascii=False)
        controller.on_turn_generated(action, narration, int(state.get("turn", 0)), memory_updates=updates)
        state["_memory_controller"] = controller.export_state()
        state["_campaign_session_index"] = self._campaign_session_index(campaign_manager)

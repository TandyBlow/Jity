"""Isolated adapter around Jity's complete, unmodified game pipeline.

No application singleton or router is imported. The adapter only supplies
dependencies, deterministic opaque IDs and observations at existing boundaries.
The actual narrator, validation, campaign rules, memory and commits are Jity's.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager, nullcontext
from copy import deepcopy
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch
import uuid

from ..storage import digest


def plain(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def differences(before, after, path=""):
    """Lossless field-level change list; the full before/after are also saved."""
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            at = path + "/" + str(key).replace("~", "~0").replace("/", "~1")
            if key not in before:
                result.append({"path": at, "operation": "add", "after": after[key]})
            elif key not in after:
                result.append({"path": at, "operation": "remove", "before": before[key]})
            else:
                result.extend(differences(before[key], after[key], at))
        return result
    return [{"path": path or "/", "operation": "replace", "before": before, "after": after}]


def normalize_checkpoint(checkpoint):
    """Exclude only SQLite wall-clock metadata, never state, IDs or prose."""
    result = deepcopy(checkpoint)
    for field in ("progress", "session"):
        if isinstance(result.get(field), dict):
            for key in ("created_at", "updated_at"):
                result[field].pop(key, None)
    return result


class JityRuntime:
    def __init__(self, jity_root, run_dir, *, config, transport, api_key="offline-recording", event_sink=None):
        self.root = Path(jity_root).resolve()
        self.run_dir = Path(run_dir).resolve()
        if self.run_dir == self.root or self.root in self.run_dir.parents:
            raise ValueError("Capture runtime database must be outside Jity")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.config = deepcopy(config)
        # Credentials are supplied separately and never enter config/events.
        if any("key" in key.lower() or "secret" in key.lower() for key in self.config):
            raise ValueError("Credentials must not be included in recorded runtime config")
        self.transport = transport
        self.event_sink = event_sink
        self.events = []
        self.session_id = config.get("session_id") or str(uuid.uuid5(uuid.NAMESPACE_URL, "jity-capture:" + str(config.get("seed", 0))))
        self.game_id = config.get("game_id", self.session_id)
        self.uuid_counter = int(config.get("uuid_counter", 0))
        self.slot_name = config.get("slot_name", "capture")
        self._api_key = api_key
        self._fatal_memory = []
        self._old_path = list(sys.path)
        self._old_bytecode = sys.dont_write_bytecode
        self._old_tokenizer_cache = os.environ.get("TIKTOKEN_CACHE_DIR")
        backend = self.root / "backend"
        app = sys.modules.get("app")
        if app is not None and getattr(app, "__file__", None):
            if backend not in Path(app.__file__).resolve().parents:
                raise ValueError("Another Jity checkout is imported; use a fresh process")
        sys.path.insert(0, str(backend))
        sys.dont_write_bytecode = True
        self._build(api_key)
        owner = self

        class CaptureWarnings(logging.Handler):
            def emit(self, record):
                if record.name == "app" or record.name.startswith("app."):
                    owner._event("runtime_warning", {"logger": record.name, "level": record.levelname,
                                                     "message": record.getMessage(),
                                                     "exception_type": record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else None})

        self._warning_handler = CaptureWarnings(level=logging.WARNING)
        self._app_logger = logging.getLogger("app")
        self._old_app_propagate = self._app_logger.propagate
        self._app_logger.addHandler(self._warning_handler)
        # The durable warning includes sanitized text, not duplicate full
        # tracebacks or exception locals in an application console handler.
        self._app_logger.propagate = False

    def _scope(self, **values):
        from .transport import capture_scope
        return capture_scope(**values)

    def _event(self, kind, payload):
        value = plain(deepcopy(payload))
        # API error strings can contain provider response bodies. Apply a final
        # credential filter even though headers are owned by the transport.
        if self._api_key:
            value = json.loads(json.dumps(value, ensure_ascii=False).replace(self._api_key, "[REDACTED]"))
        from .transport import current_scope
        event = {**plain(current_scope()), "game_id": self.game_id, **value}
        self.events.append({"kind": kind, "payload": event})
        if self.event_sink is not None:
            self.event_sink(kind, event)

    def _next_uuid(self):
        self.uuid_counter += 1
        return uuid.uuid5(uuid.NAMESPACE_URL, "%s:%s:%s" % (self.session_id, self.config.get("seed", 0), self.uuid_counter))

    @contextmanager
    def _identities(self):
        # Only internal memory revision IDs are made deterministic. Dice are
        # supplied in the durable player intent and validated by Jity itself.
        with patch("app.services.memory.memory_controller.controller.uuid4", self._next_uuid), \
             patch("app.services.scenario_generator.memory_lifecycle.uuid4", self._next_uuid):
            yield

    def _build(self, api_key):
        import httpx
        from openai import AsyncOpenAI
        from app.config import Settings
        from app.database import Database
        from app.services.campaign_manager import CampaignManager
        from app.services.context_strategy import _FallbackEncoding
        from app.services.embedding_client import EmbeddingClient
        from app.services.game_state import GameStateManager
        from app.services.health_monitor import HealthMonitor
        from app.services.knowledge_base import KnowledgeBase
        from app.services.llm_client import LLMClient
        from app.services.memory.memory_controller import MemoryController
        from app.services.prompt_builder import PromptBuilder
        from app.services.retriever import RAGRetriever
        from app.services.scenario_generator import ScenarioGenerator

        owner = self
        model = self.config.get("llm_model", "deepseek-flash")
        settings_fields = {key: self.config[key] for key in ("max_turns_per_session", "max_turns_per_campaign") if key in self.config}
        self.settings = Settings.model_construct(
            **settings_fields, deepseek_api_key=api_key, image_api_key="",
            llm_model=model, llm_base_url=self.config.get("llm_base_url", "https://api.deepseek.com"),
            database_file=self.run_dir / "runtime.sqlite3", prompt_logging_enabled=False,
            prompt_log_dir=self.run_dir / "unused-prompt-logs", backgrounds_dir=self.run_dir / "unused-backgrounds",
            campaigns_dir=Path(self.config.get("campaigns_dir", self.root / "backend/data/campaigns")),
            knowledge_dir=Path(self.config.get("knowledge_dir", self.root / "knowledge")),
            rulebook_file=Path(self.config.get("rulebook_file", self.root / "RULEBOOK.md")),
        )
        self.db = Database(self.settings.database_file)
        self.state_manager = GameStateManager(self.db)
        self.health_monitor = HealthMonitor(self.db)
        self.prompt_builder = PromptBuilder()

        class ObservedLLM(LLMClient):
            async def _request_completion(self, *args, **kwargs):
                purpose = kwargs.get("purpose", "chat_completion")
                context = kwargs.get("context") or {}
                # OpeningOptions currently uses the generic structured default;
                # the enclosing generator scope supplies its exact role.
                if purpose == "structured_generation" and owner._opening:
                    purpose = "opening_options"
                with owner._scope(purpose=purpose, role=purpose, model_context=context):
                    owner._event("completion_request", {"purpose": purpose, "context": context,
                                                       "arguments": {k: v for k, v in kwargs.items() if k != "context"}})
                    result = await super()._request_completion(*args, **kwargs)
                    owner._event("completion_text", {"purpose": purpose, "text": result})
                    return result

            def _parse_story_output(self, raw_text):
                try:
                    result = super()._parse_story_output(raw_text)
                except BaseException as exc:
                    owner._event("story_parse_failure", {"raw_text": raw_text, "error_type": type(exc).__name__})
                    raise
                owner._event("story_parsed", {"raw_text": raw_text, "parsed": plain(result)})
                return result

            async def generate_json(self, *args, **kwargs):
                result = await super().generate_json(*args, **kwargs)
                owner._event("json_parsed", {"purpose": "opening_options" if owner._opening else kwargs.get("purpose", "structured_generation"),
                                             "parsed": result})
                return result

        self._opening = False
        self.llm = ObservedLLM(self.settings)
        self.http_client = httpx.AsyncClient(transport=self.transport, timeout=self.config.get("timeout", 60.0))
        self.sdk = AsyncOpenAI(api_key=api_key, base_url=self.settings.llm_base_url.rstrip("/"),
                              max_retries=int(self.config.get("max_retries", 2)),
                              timeout=float(self.config.get("timeout", 60.0)), http_client=self.http_client)
        # SDK telemetry lazily probes platform.platform(), which can spawn
        # `uname -p` on macOS. Static telemetry avoids that unrecorded process;
        # it has no effect on model messages, decoding or gameplay.
        self.sdk._platform = {"darwin": "MacOS", "linux": "Linux", "win32": "Windows"}.get(sys.platform, "Unknown")
        if self.config.get("thinking", "disabled") == "disabled":
            original_create = self.sdk.chat.completions.create

            async def completion_create(**kwargs):
                extra = dict(kwargs.get("extra_body") or {})
                extra["thinking"] = {"type": "disabled"}
                kwargs["extra_body"] = extra
                if "max_completion_tokens" in owner.config:
                    kwargs["max_tokens"] = min(kwargs.get("max_tokens", 50000), int(owner.config["max_completion_tokens"]))
                return await original_create(**kwargs)

            self.sdk.chat.completions.create = completion_create
        self.llm._client = self.sdk
        if self.config.get("embeddings", True):
            # Bypass the constructor solely to avoid creating an uninstrumented
            # SDK client. All detection/embed/fallback methods remain Jity's.
            self.embedding = EmbeddingClient.__new__(EmbeddingClient)
            self.embedding._client = self.sdk
            self.embedding._dim = None
            self.embedding._model = None
            self.embedding._fallback_dim = 256
            self.embedding._api_available = None
            original_embed = self.embedding.embed

            async def embed(texts):
                with owner._scope(purpose="embedding", role="embedding"):
                    result = await original_embed(texts)
                    owner._event("embedding_result", {"texts": texts, "model": owner.embedding.model,
                                                      "shape": list(result.shape), "vectors_sha256": digest(result.tolist()),
                                                      "api_available": owner.embedding._api_available})
                    return result

            self.embedding.embed = embed
        else:
            self.embedding = None
        self.knowledge = KnowledgeBase(self.db, self.settings.knowledge_dir, self.settings.rulebook_file)
        chunks = self.knowledge.load_chunks()
        self.retriever = RAGRetriever(chunks, embedding_client=self.embedding)
        original_retrieve = self.retriever.retrieve_async

        async def retrieve(query, top_k=5):
            with owner._scope(component="knowledge_retrieval"):
                result = await original_retrieve(query, top_k)
                owner._event("retrieval", {"query": query, "top_k": top_k, "results": result})
                return result

        self.retriever.retrieve_async = retrieve

        class IsolatedGenerator(ScenarioGenerator):
            @staticmethod
            def _observe_controller(controller):
                if getattr(controller.score_tracker, "_capture_observed", False):
                    return controller
                original_validate = controller.score_tracker.validate_output

                def validate(output, turn):
                    before = plain(output)
                    result = original_validate(output, turn)
                    after = plain(output)
                    owner._event("output_validation", {"turn": turn, "before": before, "after": after,
                                                        "changes": differences(before, after), "violations": result})
                    return result

                controller.score_tracker.validate_output = validate
                controller.score_tracker._capture_observed = True
                return controller

            def _get_memory_controller(self, session_id, state=None, campaign_manager=None):
                cached = self._memory_controllers.get(session_id)
                if cached is not None and (state is None or "_memory_controller" not in state or
                                          state["_memory_controller"].get("version") == cached.version):
                    return self._observe_controller(cached)
                controller = MemoryController(self.llm_client, self.db, session_id, embedding_client=owner.embedding)
                if state and "_memory_controller" in state:
                    controller.load_state(state["_memory_controller"])
                if state:
                    controller.score_tracker.seed(state.get("items", []), int(state.get("turn", 0)))
                self._memory_controllers[session_id] = controller
                return self._observe_controller(controller)

            async def _generate_opening_options(self, *args, **kwargs):
                owner._opening = True
                try:
                    result = await super()._generate_opening_options(*args, **kwargs)
                    owner._event("opening_options_adopted", {"parsed": plain(result)})
                    return result
                finally:
                    owner._opening = False

            async def _run_director_stage(self, *args, **kwargs):
                result = await super()._run_director_stage(*args, **kwargs)
                owner._event("director_adopted", {"parsed": plain(result)})
                return result

            async def _build_prompt(self, *args, **kwargs):
                result = await super()._build_prompt(*args, **kwargs)
                prompt, meta, retrieved, stored, tokens = result
                controller = self._memory_controllers.get(owner.session_id)
                owner._event("prompt_assembled", {"prompt": prompt, "sections": meta.sections,
                                                  "estimated_tokens": tokens, "retrieved": retrieved,
                                                  "memory_hits": getattr(controller, "last_hits", [])})
                return result

            def _feed_memory(self, session_id, state, output, action, campaign_manager):
                before = deepcopy(state.get("_memory_controller"))
                super()._feed_memory(session_id, state, output, action, campaign_manager)
                owner._event("memory_write", {"turn": state.get("turn"), "before": before,
                                              "after": state.get("_memory_controller")})

            async def _maintain_memory_snapshot(self, session_id, turn_id, turn, snapshot, dialogues, embedding=None, embedding_cache=()):
                try:
                    with owner._scope(timeline_node=turn_id, component="memory_maintenance"):
                        owner._event("memory_maintenance_start", {"turn": turn, "timeline_node": turn_id, "snapshot": snapshot, "dialogues": dialogues})
                        await super()._maintain_memory_snapshot(session_id, turn_id, turn, snapshot, dialogues, embedding, embedding_cache)
                        owner._event("memory_maintenance_end", {"turn": turn, "timeline_node": turn_id,
                                                                 "state": owner.state_manager.get_session_payload(session_id)["state"]})
                except BaseException as exc:
                    owner._fatal_memory.append(exc)
                    raise

            async def _wait_memory(self, session_id):
                await super()._wait_memory(session_id)
                if owner._fatal_memory:
                    raise owner._fatal_memory.pop(0)
                owner.transport.raise_if_failed()

        # CampaignSessionAdvancer otherwise reads .env in its constructor.
        with patch("app.services.campaign_advancer.get_settings", lambda: self.settings):
            self.campaign = CampaignManager(self.db, self.settings.campaigns_dir, self.prompt_builder, self.llm, self.health_monitor)
        if self.config.get("tokenizer", "cl100k_base") == "offline-estimator":
            self.campaign._strategy._enc = _FallbackEncoding()
        else:
            self.campaign._strategy._enc = self._local_tokenizer()
        self.generator = IsolatedGenerator(self.db, self.state_manager, self.retriever,
                                           self.prompt_builder, self.llm, model, campaign_manager=self.campaign)

    def _local_tokenizer(self):
        import tempfile
        import tiktoken
        cache_value = self.config.get("tokenizer_cache") or os.environ.get("TIKTOKEN_CACHE_DIR")
        # Do not eagerly evaluate gettempdir() when a cache was supplied: its
        # first call probes system temp with a write, forbidden during replay.
        cache = Path(cache_value) if cache_value else Path(tempfile.gettempdir()) / "data-gym-cache"
        vocab = cache / "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
        expected = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
        if not vocab.is_file() or hashlib.sha256(vocab.read_bytes()).hexdigest() != expected:
            raise ValueError("Verified local cl100k_base tokenizer cache required; network download is disabled")
        os.environ["TIKTOKEN_CACHE_DIR"] = str(cache)
        return tiktoken.get_encoding("cl100k_base")

    async def start(self, session_id=None, restore=False):
        from app.services.game_state.defaults import default_state
        if session_id is not None:
            self.session_id = str(session_id)
        path = self.settings.campaigns_dir / self.config.get("campaign_filename", "default_campaign.json")
        with self._identities(), self._scope(game_id=self.game_id, turn=0, operation_id="initialize", timeline_node=0):
            if restore:
                if not self.db.get_session(self.session_id):
                    raise ValueError("Cannot restore nonexistent capture session")
                self.campaign.load(path, campaign_id=self.session_id, slot_name=self.slot_name)
            else:
                if self.db.get_session(self.session_id):
                    raise ValueError("Capture session exists; explicit restore is required")
                state = default_state()
                self.db.write_session(self.session_id, self.config.get("game_name", "Jity fixed regression capture"),
                                      self.settings.llm_model, state, account_id=None, save_purpose="test")
                self.db.ensure_timeline_root(self.session_id, state, self.settings.llm_model)
                if "session_turn_budget" in self.config:
                    self.db.set_session_turn_budget(self.session_id, self.config["session_turn_budget"])
                self.campaign.load(path, campaign_id=self.session_id, start_arc_index=0, start_session_index=0, slot_name=self.slot_name)
                self.db.set_session_campaign_id(self.session_id, self.session_id, path.name, self.slot_name)
                state = self.state_manager.merge_entry_state(state, self.campaign.campaign, 0, 0, initialize=True)
                self.state_manager.save_state(self.session_id, self.config.get("game_name", "Jity fixed regression capture"), self.settings.llm_model, state)
                self.db.update_active_turn_snapshot(self.session_id, state, self.db.read_campaign_progress(self.session_id, self.slot_name))
            result = self.checkpoint()
            self._event("runtime_initialized", {"checkpoint": result, "config": self.config})
            return result

    async def prepare(self, action, option_index=None, roll=None):
        from app.services.action_checks import resolve_action_check, is_check_transition
        await self.generator._wait_memory(self.session_id)
        before = self.checkpoint()
        resolution = await resolve_action_check(action, before["state"], before["output"], option_index,
                                                defer_feasibility=is_check_transition(self.campaign))
        payload = {"player_action": action, "timeline_node_id": before["head"], "model": self.settings.llm_model,
                   "slot_name": self.slot_name, "style": self.config.get("style", "horror"),
                   "constraints": self.config.get("constraints", "")}
        if resolution.option_index is not None:
            payload["option_index"] = resolution.option_index
        if resolution.check is not None:
            if roll is None:
                raise ValueError("This action requires a persisted die value; runtime never rolls dice")
            payload["action_check"] = {"roll": roll, "option_index": resolution.option_index}
        self._event("action_prepared", {"turn": before["turn"] + 1, "payload": payload,
                                        "check": plain(resolution.check), "ruling": plain(resolution.ruling)})
        return payload

    async def generate(self, payload):
        from app.schemas import GenerateRequest
        before = self.checkpoint()
        target = int(before["turn"]) + 1
        with self._identities(), self._scope(game_id=self.game_id, turn=target, timeline_node=before["head"], operation_id="turn-%d" % target):
            self._event("turn_before", {"turn": target, "payload": payload, "checkpoint": before})
            try:
                response = await self.generator.generate(self.session_id, GenerateRequest.model_validate(payload))
                await self.generator._wait_memory(self.session_id)
            except BaseException as exc:
                self._event("turn_error", {"turn": target, "error_type": type(exc).__name__, "error": str(exc),
                                            "checkpoint": self.checkpoint()})
                raise
            after = self.checkpoint()
            self._event("turn_committed", {"turn": target, "response": plain(response), "checkpoint": after,
                                           "state_changes": differences(before["state"], after["state"])})
            return plain(response)

    def checkpoint(self):
        session = self.state_manager.get_session_payload(self.session_id)
        if session is None:
            raise ValueError("Runtime has not started")
        head = session["active_turn_id"]
        row = self.db.get_story_turn(self.session_id, head)
        progress = self.db.read_campaign_progress(self.session_id, self.slot_name)
        return normalize_checkpoint({"session_id": self.session_id, "head": head, "turn": session["state"].get("turn", 0),
                                     "state": session["state"], "output": json.loads(row.get("output_json") or "{}"),
                                     "progress": progress, "uuid_counter": self.uuid_counter,
                                     "model": session["model"], "source": row.get("source")})

    async def reload(self):
        """Reopen authoritative state without advancing, calling a model or rolling."""
        from app.database import Database
        from app.services.memory.memory_controller import MemoryController
        await self.generator._wait_memory(self.session_id)
        before = self.checkpoint()
        reopened = Database(self.db.path)
        row = reopened.get_session(self.session_id)
        node = reopened.get_story_turn(self.session_id, before["head"])
        restored = json.loads(row["state_json"])
        if restored != before["state"] or restored != json.loads(node["state_json"]):
            raise AssertionError("Reloaded session and timeline snapshot differ")
        if "_memory_controller" in restored:
            # Hydrate the actual memory implementation from the reopened row.
            # Its temporary constructor UUID is immediately replaced by the
            # persisted version; no runtime revision counter is advanced.
            memory = MemoryController(self.llm, reopened, self.session_id, embedding_client=self.embedding)
            memory.load_state(restored["_memory_controller"])
            if memory.export_state() != restored["_memory_controller"]:
                raise AssertionError("Memory controller hydration differs after database reopen")
        self.campaign.reload_runtime_state()
        self.generator.invalidate_timeline_caches(self.session_id, self.slot_name)
        after = self.checkpoint()
        if before != after:
            raise AssertionError("Reload changed authoritative checkpoint")
        self._event("reload_verified", {"checkpoint_sha256": digest(after), "turn": after["turn"]})
        return after

    def backup(self, path):
        path = Path(path).resolve()
        if path.exists():
            raise FileExistsError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect("file:%s?mode=ro" % self.db.path, uri=True)
        destination = sqlite3.connect(path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        return path

    async def close(self):
        try:
            # Cleanup must not replace the original strict-boundary exception.
            tasks = list(self.generator._memory_tasks)
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            await self.sdk.close()
            self._app_logger.removeHandler(self._warning_handler)
            self._app_logger.propagate = self._old_app_propagate
            sys.path[:] = self._old_path
            sys.dont_write_bytecode = self._old_bytecode
            if self._old_tokenizer_cache is None:
                os.environ.pop("TIKTOKEN_CACHE_DIR", None)
            else:
                os.environ["TIKTOKEN_CACHE_DIR"] = self._old_tokenizer_cache

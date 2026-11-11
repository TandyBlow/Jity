"""Generate + evaluate routes."""

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.dependencies import (
    db,
    evaluation_module,
    knowledge_service,
    state_manager,
)
from app.schemas import ActionCheckRequest, ActionCheckResponse, GenerateRequest, GenerateResponse, StoryOutput
from app.services.action_checks import ActionCheckError, is_check_transition, resolve_action_check
from app.services.llm_client import MissingAPIKeyError
from app.services.scenario_generator import ScenarioGenerationError
from app.exceptions import CampaignRequiredError, ConcurrentModificationError

router = APIRouter(tags=["generate"])


@router.post("/sessions/{session_id}/check", response_model=ActionCheckResponse)
async def check_action(session_id: str, request: ActionCheckRequest) -> ActionCheckResponse:
    """Preview the active turn's rule without rolling or changing story state."""
    generator = knowledge_service.scenario_generator
    lock = generator._generation_locks.setdefault(session_id, asyncio.Lock())
    async with lock:
        await generator._wait_memory(session_id)
        session = state_manager.get_session_payload(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        active_id = session.get("active_turn_id")
        if request.timeline_node_id != active_id:
            raise HTTPException(status_code=409, detail="剧情进度已更新，请刷新后重新选择行动。")
        active_turn = db.get_story_turn(session_id, active_id)
        previous_output = json.loads((active_turn or {}).get("output_json") or "{}")
        if previous_output.get("game_over"):
            raise HTTPException(status_code=409, detail="Campaign already ended")
        campaign_provider = getattr(generator, "_campaign_manager_for", None)
        campaign_manager = campaign_provider(session_id, "") if callable(campaign_provider) else None
        try:
            resolution = await resolve_action_check(
                request.player_action, session["state"], previous_output, request.option_index,
                defer_feasibility=is_check_transition(campaign_manager),
            )
        except ActionCheckError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ActionCheckResponse(check=resolution.check, option_index=resolution.option_index)


@router.post("/sessions/{session_id}/generate", response_model=GenerateResponse)
async def generate(session_id: str, request: GenerateRequest) -> GenerateResponse:
    try:
        response = await knowledge_service.scenario_generator.generate(session_id, request)
    except CampaignRequiredError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ActionCheckError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MissingAPIKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ScenarioGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ConcurrentModificationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not response:
        raise HTTPException(status_code=404, detail="Session not found")
    return response


@router.post("/evaluate")
def evaluate(output: StoryOutput) -> dict[str, int]:
    return evaluation_module.score(output)


# ── Optional SSE companion ────────────────────────────────────────────
#
# The block below is additive: /generate keeps its exact response shape and
# remains the only path the current frontend uses. This route reuses the same
# single generation call, so Examiner/Director/Narrator, campaign progress and
# memory writes are identical; it only changes how the finished result is
# delivered (narration slices first, then the complete GenerateResponse).

def _sse_event(event: str, data: object) -> str:
    """Format one server-sent event. `data` must be JSON-serialisable."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _narration_slices(text: str, size: int = 48) -> list[str]:
    return [text[index:index + size] for index in range(0, len(text), size)]


@router.post("/sessions/{session_id}/generate/stream")
async def generate_stream(session_id: str, request: GenerateRequest) -> StreamingResponse:
    """SSE view of one turn: `open` → `narration` deltas → `done` (full JSON).

    Errors are delivered as an `error` event instead of an HTTP status, because
    the response headers are already on the wire by then.

    Note: the LLM call itself is not token-streamed here. The narrator returns
    a JSON object, so slicing it server-side keeps the campaign/memory contract
    untouched; a真·token stream would need incremental JSON parsing inside the
    narrator, which is deliberately out of scope.
    """

    async def events():
        # Flush headers immediately: generation can take tens of seconds.
        yield _sse_event("open", {"session_id": session_id})

        try:
            response = await knowledge_service.scenario_generator.generate(session_id, request)
        except MissingAPIKeyError as exc:
            yield _sse_event("error", {"status": 503, "detail": str(exc)})
            return
        except CampaignRequiredError as exc:
            yield _sse_event("error", {"status": 422, "detail": str(exc)})
            return
        except ActionCheckError as exc:
            yield _sse_event("error", {"status": 422, "detail": str(exc)})
            return
        except ScenarioGenerationError as exc:
            yield _sse_event("error", {"status": 502, "detail": str(exc)})
            return
        except ConcurrentModificationError as exc:
            yield _sse_event("error", {"status": 409, "detail": str(exc)})
            return
        except Exception as exc:  # keep the stream well-formed for the client
            yield _sse_event("error", {"status": 500, "detail": f"{type(exc).__name__}: {exc}"})
            return

        if response is None:
            yield _sse_event("error", {"status": 404, "detail": "Session not found"})
            return

        payload = response.model_dump(mode="json")
        narration = ((payload.get("output") or {}).get("narration")) or ""
        yield _sse_event("start", {
            "session_id": session_id,
            "turn": (payload.get("state") or {}).get("turn"),
        })
        for delta in _narration_slices(narration):
            yield _sse_event("narration", {"delta": delta})
            await asyncio.sleep(0)
        yield _sse_event("done", payload)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

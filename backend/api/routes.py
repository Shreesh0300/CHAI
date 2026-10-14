import asyncio
import time
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.core.schemas import SolveRequest, FinalResponse
from backend.core.coordinator import Coordinator
from backend.core.execution_events import execution_event_manager
from backend.shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()
coordinator = Coordinator()


@router.post("/solve", response_model=FinalResponse)
async def solve_problem(request: SolveRequest):
    """Executes a solve request through the coordinated multi-agent workflow."""
    req_id = request.request_id or str(uuid.uuid4())
    request.request_id = req_id
    execution_event_manager.create_session(req_id)
    try:
        response = await coordinator.process_request(request)
        if not getattr(response, "title", None) and getattr(request, "problem", None):
            from backend.chat.title_service import title_service
            try:
                response.title = await asyncio.wait_for(
                    title_service.generate_title(request.problem),
                    timeout=3.0,
                )
            except Exception:
                response.title = title_service.generate_fallback_title(request.problem)
        return response
    except Exception as e:
        from backend.core.execution_events import RequestCancelledException
        if isinstance(e, (RequestCancelledException, asyncio.CancelledError)) or execution_event_manager.is_cancelled(req_id):
            return coordinator._build_cancelled_response(
                request=request,
                req_id=req_id,
                agent_outputs={},
                execution_statuses=[],
                execution_trace=[],
            )
        logger.error(f"Solve problem execution error: {e}")
        await execution_event_manager.emit(
            request_id=req_id,
            event="request_failed",
            status="failed",
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/solve/{request_id}/pause")
async def pause_solve(request_id: str):
    """Pauses generation for an active solve request."""
    if not execution_event_manager.has_session(request_id):
        raise HTTPException(status_code=404, detail=f"Execution request '{request_id}' not found")
    res = await execution_event_manager.pause_request(request_id)
    return {"request_id": request_id, "status": "paused", "success": res}


@router.post("/solve/{request_id}/resume")
async def resume_solve(request_id: str):
    """Resumes generation for a paused solve request."""
    if not execution_event_manager.has_session(request_id):
        raise HTTPException(status_code=404, detail=f"Execution request '{request_id}' not found")
    res = await execution_event_manager.resume_request(request_id)
    return {"request_id": request_id, "status": "resumed", "success": res}


@router.post("/solve/{request_id}/cancel")
async def cancel_solve(request_id: str):
    """Cancels generation for an active solve request."""
    if not execution_event_manager.has_session(request_id):
        raise HTTPException(status_code=404, detail=f"Execution request '{request_id}' not found")
    res = await execution_event_manager.cancel_request(request_id)
    return {"request_id": request_id, "status": "cancelled", "success": res}


@router.get("/solve/{request_id}/events")
async def get_solve_events(request_id: str, request: Request):
    """
    Server-Sent Events (SSE) endpoint streaming live agent execution events.
    Clients receive real-time updates as each specialist agent runs and finishes.
    """
    # Wait up to 3.0s in case client connected milliseconds before POST is processed
    start_wait = time.time()
    while not execution_event_manager.has_session(request_id):
        if time.time() - start_wait > 3.0:
            raise HTTPException(status_code=404, detail=f"Execution request '{request_id}' not found")
        await asyncio.sleep(0.05)

    async def event_generator():
        try:
            async for event in execution_event_manager.subscribe(request_id, wait_for_init_seconds=0.1):
                if await request.is_disconnected():
                    break
                yield f"data: {event.model_dump_json()}\n\n"
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"SSE event stream ended for {request_id}: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

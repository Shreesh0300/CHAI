import asyncio
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from backend.core.schemas import SolveRequest, FinalResponse
from backend.core.coordinator import Coordinator
from backend.shared.supabase_client import get_supabase_client

router = APIRouter()
coordinator = Coordinator()


async def _async_persist(request: SolveRequest, response: FinalResponse, auth_header: Optional[str] = None):
    """Background persistence to Supabase if client is available."""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return

        user_id = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            try:
                user_res = supabase.auth.get_user(token)
                if user_res and user_res.user:
                    user_id = str(user_res.user.id)
            except Exception:
                pass

        sr_payload = {
            "problem": request.problem,
            "status": response.request_status,
            "selected_agents": response.selected_agents,
            "final_answer": response.final_synthesized_answer,
            "limitations": response.limitations or [],
        }
        if user_id:
            sr_payload["user_id"] = user_id

        inserted = supabase.table("solve_requests").insert(sr_payload).execute()
        if inserted.data and len(inserted.data) > 0:
            request_id = inserted.data[0].get("id")
            for agent_name, output in response.agent_outputs.items():
                if isinstance(agent_name, str) and agent_name.islower():
                    supabase.table("agent_outputs").insert({
                        "request_id": request_id,
                        "agent_name": agent_name,
                        "status": "completed",
                        "output_data": output if isinstance(output, dict) else {"output": output},
                    }).execute()
    except Exception:
        pass


@router.post("/solve", response_model=FinalResponse)
async def solve_problem(
    request: SolveRequest,
    authorization: Optional[str] = Header(None),
):
    try:
        response = await coordinator.process_request(request)
        asyncio.create_task(_async_persist(request, response, authorization))
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


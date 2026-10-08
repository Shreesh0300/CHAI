"""
History API routes — provides conversation/solve history to the frontend sidebar.
"""

from fastapi import APIRouter
from typing import List, Dict, Any
from backend.shared.supabase_client import get_supabase_client

router = APIRouter()


@router.get("/history", response_model=List[Dict[str, Any]])
async def get_solve_history() -> List[Dict[str, Any]]:
    """Return past solve history formatted for the frontend workspace sidebar."""
    supabase = get_supabase_client()
    if not supabase:
        return []
    try:
        res = (
            supabase.table("solve_requests")
            .select("id, problem, status, final_answer, created_at")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        if not res.data:
            return []

        formatted = []
        for row in res.data:
            problem = row.get("problem") or "Conversation"
            answer = row.get("final_answer") or ""
            formatted.append({
                "id": str(row.get("id", "")),
                "title": problem[:60] + ("..." if len(problem) > 60 else ""),
                "mode": "ask",
                "layout": "chat",
                "messages": [
                    {"id": f"u_{row.get('id')}", "role": "user", "content": problem},
                    {"id": f"a_{row.get('id')}", "role": "assistant", "content": answer},
                ],
                "created_at": row.get("created_at"),
            })
        return formatted
    except Exception:
        return []

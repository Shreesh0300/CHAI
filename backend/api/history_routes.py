"""
History API routes — provides conversation/solve history to the frontend sidebar.
Supports both Supabase persistence and a local resilient file/memory cache.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header
from backend.shared.logger import get_logger
from backend.shared.supabase_client import get_supabase_client

logger = get_logger(__name__)

router = APIRouter()

HISTORY_FILE = Path("backend/data/history_cache.json")
_MEMORY_HISTORY: List[Dict[str, Any]] = []
_LOADED_FROM_DISK = False


def _load_local_history() -> List[Dict[str, Any]]:
    global _MEMORY_HISTORY, _LOADED_FROM_DISK
    if not _LOADED_FROM_DISK:
        if HISTORY_FILE.exists():
            try:
                data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    _MEMORY_HISTORY = data
            except Exception as e:
                logger.debug(f"Could not load local history file: {e}")
        _LOADED_FROM_DISK = True
    return _MEMORY_HISTORY


def _save_local_history() -> None:
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(json.dumps(_MEMORY_HISTORY[:100], indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to persist local history file: {e}")


SOLVE_DETAILS_FILE = Path("backend/data/solve_details_cache.json")
_MEMORY_SOLVE_DETAILS: Dict[str, Any] = {}


def record_solve_details(solve_id: str, details: Dict[str, Any]) -> None:
    global _MEMORY_SOLVE_DETAILS
    _MEMORY_SOLVE_DETAILS[solve_id] = details
    try:
        SOLVE_DETAILS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if SOLVE_DETAILS_FILE.exists():
            try:
                data = json.loads(SOLVE_DETAILS_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data[solve_id] = details
        keys = list(data.keys())[-50:]
        trimmed = {k: data[k] for k in keys}
        SOLVE_DETAILS_FILE.write_text(json.dumps(trimmed, indent=2), encoding="utf-8")
    except Exception as e:
        logger.debug(f"Failed to cache solve details: {e}")


def get_cached_solve_details(solve_id: str) -> Optional[Dict[str, Any]]:
    global _MEMORY_SOLVE_DETAILS
    if solve_id in _MEMORY_SOLVE_DETAILS:
        return _MEMORY_SOLVE_DETAILS[solve_id]
    if SOLVE_DETAILS_FILE.exists():
        try:
            data = json.loads(SOLVE_DETAILS_FILE.read_text(encoding="utf-8"))
            if solve_id in data:
                _MEMORY_SOLVE_DETAILS[solve_id] = data[solve_id]
                return data[solve_id]
        except Exception:
            pass
    return None


def record_solve_history(
    problem: str,
    answer: str,
    mode: str = "ask",
    layout: str = "chat",
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Saves a solve interaction to local history cache.
    Called on every successful /api/solve execution so the UI never loses the thread.
    """
    global _MEMORY_HISTORY
    _load_local_history()

    item_id = request_id or str(uuid.uuid4())
    ts = created_at or datetime.now(timezone.utc).isoformat()
    clean_problem = problem.strip()
    title = clean_problem[:60] + ("..." if len(clean_problem) > 60 else "")

    entry = {
        "id": item_id,
        "title": title,
        "mode": mode,
        "layout": layout,
        "prompt": clean_problem,
        "answer": answer,
        "messages": [
            {"id": f"u_{item_id}", "role": "user", "content": clean_problem},
            {"id": f"a_{item_id}", "role": "assistant", "content": answer},
        ],
        "created_at": ts,
        "user_id": user_id,
    }

    # Dedup and prepend
    _MEMORY_HISTORY = [e for e in _MEMORY_HISTORY if e.get("id") != item_id and e.get("prompt") != clean_problem]
    _MEMORY_HISTORY.insert(0, entry)
    _save_local_history()
    return entry


@router.get("/history", response_model=List[Dict[str, Any]])
async def get_solve_history(authorization: Optional[str] = Header(None)) -> List[Dict[str, Any]]:
    """Return past solve history formatted for the frontend workspace sidebar."""
    local_items = _load_local_history()

    token = (
        authorization.split(" ", 1)[1]
        if (isinstance(authorization, str) and authorization.startswith("Bearer "))
        else None
    )
    supabase = get_supabase_client(token) or get_supabase_client()

    supabase_items: List[Dict[str, Any]] = []
    if supabase:
        try:
            query = (
                supabase.table("solve_requests")
                .select("id, problem, status, final_answer, created_at, user_id")
                .order("created_at", desc=True)
                .limit(40)
            )
            res = query.execute()
            if res.data:
                for row in res.data:
                    problem = row.get("problem") or "Conversation"
                    answer = row.get("final_answer") or ""
                    row_id = str(row.get("id", ""))
                    supabase_items.append({
                        "id": row_id,
                        "title": problem[:60] + ("..." if len(problem) > 60 else ""),
                        "mode": "ask",
                        "layout": "chat",
                        "prompt": problem,
                        "answer": answer,
                        "messages": [
                            {"id": f"u_{row_id}", "role": "user", "content": problem},
                            {"id": f"a_{row_id}", "role": "assistant", "content": answer},
                        ],
                        "created_at": row.get("created_at"),
                        "user_id": row.get("user_id"),
                    })
        except Exception as e:
            logger.debug(f"[History API] Supabase query skipped/failed: {e}")

    # Combine Supabase records with local items, deduplicated by ID and prompt
    combined: List[Dict[str, Any]] = []
    seen_ids = set()
    seen_prompts = set()

    for item in supabase_items + local_items:
        iid = str(item.get("id", ""))
        prompt_snippet = str(item.get("prompt", ""))[:50]
        if iid and iid in seen_ids:
            continue
        if prompt_snippet and prompt_snippet in seen_prompts:
            continue
        if iid:
            seen_ids.add(iid)
        if prompt_snippet:
            seen_prompts.add(prompt_snippet)
        combined.append(item)

    return combined


@router.delete("/history/{history_id}")
async def delete_history_item(
    history_id: str,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Delete a specific history entry by ID."""
    global _MEMORY_HISTORY
    _load_local_history()
    _MEMORY_HISTORY = [e for e in _MEMORY_HISTORY if str(e.get("id")) != str(history_id)]
    _save_local_history()

    token = (
        authorization.split(" ", 1)[1]
        if (isinstance(authorization, str) and authorization.startswith("Bearer "))
        else None
    )
    supabase = get_supabase_client(token) or get_supabase_client()
    if supabase:
        try:
            supabase.table("solve_requests").delete().eq("id", history_id).execute()
        except Exception:
            pass

    return {"success": True, "id": history_id}


@router.delete("/history")
async def clear_all_history() -> Dict[str, Any]:
    """Clear all stored history."""
    global _MEMORY_HISTORY
    _MEMORY_HISTORY = []
    _save_local_history()
    return {"success": True}

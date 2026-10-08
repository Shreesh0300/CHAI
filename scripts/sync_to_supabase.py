"""
Script to sync local cached conversation threads and user profile into Supabase.
Can be executed anytime or automatically when credentials/policies are ready.
"""
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.shared.supabase_client import get_supabase_client
from backend.shared.logger import get_logger

logger = get_logger(__name__)

HISTORY_FILE = Path("backend/data/history_cache.json")


def sync_conversations(email: Optional[str] = None, full_name: Optional[str] = None):
    supabase = get_supabase_client()
    if not supabase:
        print("[Sync] Error: Supabase client could not be initialized. Check SUPABASE_URL in .env.")
        return False

    # 1. Sync User Profile if provided
    if email:
        try:
            user_id = str(uuid.uuid4())
            p_res = supabase.table("profiles").upsert({
                "id": user_id,
                "email": email,
                "full_name": full_name or email.split("@")[0],
            }).execute()
            print(f"[Sync] Profile synced for {email}: {p_res.data}")
        except Exception as e:
            print(f"[Sync] Could not sync profile: {e}")

    # 2. Sync Conversations from history_cache.json
    if not HISTORY_FILE.exists():
        print("[Sync] No local history_cache.json found.")
        return True

    try:
        conversations = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[Sync] Error reading history cache: {e}")
        return False

    print(f"[Sync] Found {len(conversations)} conversations in local cache. Attempting sync to Supabase...")
    success_count = 0
    fail_count = 0

    for item in conversations:
        problem = item.get("prompt") or item.get("title")
        answer = item.get("answer") or ""
        created_at = item.get("created_at")

        payload = {
            "problem": problem,
            "status": "completed",
            "selected_agents": ["researcher", "strategist", "engineer", "guardian", "security", "evaluator"],
            "final_answer": answer,
        }
        if created_at:
            payload["created_at"] = created_at

        try:
            res = supabase.table("solve_requests").insert(payload).execute()
            if res.data:
                success_count += 1
                print(f" [OK] Synced: {problem[:50]}...")
            else:
                fail_count += 1
                print(f" [FAIL] Insert returned empty for: {problem[:50]}")
        except Exception as e:
            fail_count += 1
            print(f" [RLS/PERMISSION ERROR] Could not insert '{problem[:40]}...': {e}")

    print(f"[Sync Complete] Successfully synced: {success_count}, Failed: {fail_count}")
    return success_count > 0


if __name__ == "__main__":
    email_arg = sys.argv[1] if len(sys.argv) > 1 else None
    name_arg = sys.argv[2] if len(sys.argv) > 2 else None
    sync_conversations(email_arg, name_arg)

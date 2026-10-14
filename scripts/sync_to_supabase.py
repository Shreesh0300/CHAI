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
        user_id = str(uuid.uuid4())
        # Try user_profiles first (unrestricted TEXT primary key)
        try:
            supabase.table("user_profiles").upsert({
                "user_id": user_id,
                "email": email,
                "name": full_name or email.split("@")[0],
            }).execute()
            print(f"[Sync] user_profiles synced for {email}")
        except Exception as e:
            logger.debug(f"[Sync] user_profiles table not available: {e}")

        # Also try public.profiles (linked to auth.users)
        try:
            p_res = supabase.table("profiles").upsert({
                "id": user_id,
                "email": email,
                "full_name": full_name or email.split("@")[0],
            }).execute()
            print(f"[Sync] Profile synced for {email}: {p_res.data}")
        except Exception as e:
            logger.debug(f"[Sync] profiles table upsert: {e}")

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
    synced_convs = 0
    synced_solves = 0

    for item in conversations:
        conv_id = item.get("id") or str(uuid.uuid4())
        problem = item.get("prompt") or item.get("title") or "Conversation"
        answer = item.get("answer") or ""
        created_at = item.get("created_at")
        user_id = item.get("user_id") or "guest_default"
        title = item.get("title") or problem[:50]
        mode = item.get("mode") or "ask"
        layout = item.get("layout") or "chat"

        # A. Sync to conversations table
        try:
            conv_payload = {
                "id": conv_id,
                "user_id": user_id,
                "title": title,
                "mode": mode,
                "layout": layout,
            }
            if created_at:
                conv_payload["created_at"] = created_at
                conv_payload["updated_at"] = created_at

            c_res = supabase.table("conversations").upsert(conv_payload).execute()
            if c_res.data:
                # Sync messages for this conversation
                msgs = item.get("messages", [])
                for idx, m in enumerate(msgs):
                    msg_id = m.get("id") or f"{conv_id}_{idx}"
                    supabase.table("messages").upsert({
                        "id": msg_id,
                        "conversation_id": conv_id,
                        "user_id": user_id,
                        "role": m.get("role") or "user",
                        "content": m.get("content") or "",
                        "attachments": [],
                    }).execute()
                synced_convs += 1
                print(f" [OK] Synced thread: '{title[:45]}...' ({len(msgs)} messages)")
        except Exception as e:
            logger.debug(f" [conversations table] Note: {e}")

        # B. Sync to solve_requests table
        solve_payload = {
            "problem": problem,
            "status": "completed",
            "selected_agents": ["researcher", "strategist", "engineer", "guardian", "security", "evaluator"],
            "final_answer": answer,
        }
        if created_at:
            solve_payload["created_at"] = created_at

        try:
            res = supabase.table("solve_requests").insert(solve_payload).execute()
            if res.data:
                synced_solves += 1
                print(f" [OK] Synced solve_request: '{problem[:45]}...'")
        except Exception as e:
            logger.debug(f" [solve_requests table] Note: {e}")

    print(f"\n[Sync Summary] Threads synced: {synced_convs}/{len(conversations)}, Solves synced: {synced_solves}/{len(conversations)}")
    return (synced_convs + synced_solves) > 0


if __name__ == "__main__":
    email_arg = sys.argv[1] if len(sys.argv) > 1 else None
    name_arg = sys.argv[2] if len(sys.argv) > 2 else None
    sync_conversations(email_arg, name_arg)

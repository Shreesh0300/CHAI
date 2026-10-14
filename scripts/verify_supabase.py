"""
CHAI Platform — Supabase Connection & Schema Verification Script
Verifies connection, table schemas, permissions, and storage for project lkgezucyebjyxatpdxzv.
"""
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import get_settings
from backend.shared.supabase_client import get_supabase_client


def verify_supabase():
    settings = get_settings()
    url = (os.getenv("SUPABASE_URL") or settings.supabase_url or "").strip()
    service_key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or settings.supabase_service_role_key or "").strip()
    anon_key = (os.getenv("SUPABASE_ANON_KEY") or settings.supabase_anon_key or "").strip()

    print("=" * 65)
    print("  CHAI SUPABASE CONNECTION & SCHEMA VERIFICATION")
    print("=" * 65)
    print(f"Target URL:         {url}")
    print(f"Service Role Key:   {'Configured (Admin Access)' if service_key else 'Not Set (Using Anon Key)'}")
    print(f"Anon/Pub Key:       {'Configured' if anon_key else 'Not Set'}")
    print("-" * 65)

    client = get_supabase_client()
    if not client:
        print("[FAIL] Could not initialize Supabase client. Check .env configuration.")
        return False

    print("[OK] Supabase client initialized successfully.\n")

    tables = [
        ("profiles", "User profiles linked to auth"),
        ("solve_requests", "Multi-agent problem solving requests"),
        ("agent_outputs", "Individual agent outputs"),
        ("evaluations", "Multi-agent evaluation & consistency"),
        ("security_findings", "Security scan findings"),
        ("sources", "Source attribution & references"),
        ("conversations", "Chat sessions & thread history"),
        ("messages", "Chat messages & turns"),
        ("files", "File metadata & attachments"),
        ("memories", "Long-term memories & user facts"),
        ("user_profiles", "Detailed workspace user preferences"),
    ]

    print("--- 1. TABLE PRESENCE & READ ACCESS ---")
    present_tables = []
    missing_tables = []
    for table_name, description in tables:
        try:
            res = client.table(table_name).select("*").limit(1).execute()
            count_str = f"{len(res.data)} sample rows"
            print(f" [PASS] Table '{table_name}': Exists ({description})")
            present_tables.append(table_name)
        except Exception as e:
            err_msg = str(e)
            if "PGRST205" in err_msg or "schema cache" in err_msg:
                print(f" [MISSING] Table '{table_name}': Not found in schema")
                missing_tables.append(table_name)
            else:
                print(f" [ERROR] Table '{table_name}': {err_msg[:60]}...")

    print(f"\nTables Present: {len(present_tables)}/{len(tables)}")
    if missing_tables:
        print(f"Missing Tables: {', '.join(missing_tables)}")

    print("\n--- 2. WRITE PERMISSION (RLS) PROBE ---")
    write_status = {}
    test_id = "test_probe_verify_999"

    # Test conversations write
    if "conversations" in present_tables:
        try:
            r = client.table("conversations").upsert({
                "id": test_id,
                "user_id": "test_user",
                "title": "Probe Test",
                "mode": "ask",
                "layout": "chat",
            }).execute()
            client.table("conversations").delete().eq("id", test_id).execute()
            print(" [PASS] 'conversations' write & delete succeeded.")
            write_status["conversations"] = True
        except Exception as e:
            print(f" [RLS BLOCK] 'conversations' write blocked: {e}")
            write_status["conversations"] = False

    # Test solve_requests write
    if "solve_requests" in present_tables:
        try:
            r = client.table("solve_requests").insert({
                "problem": "Probe Test",
                "status": "completed",
            }).execute()
            inserted_id = r.data[0]["id"] if r.data else None
            if inserted_id:
                client.table("solve_requests").delete().eq("id", inserted_id).execute()
            print(" [PASS] 'solve_requests' write & delete succeeded.")
            write_status["solve_requests"] = True
        except Exception as e:
            print(f" [RLS BLOCK] 'solve_requests' write blocked: {e}")
            write_status["solve_requests"] = False

    # Test user_profiles write
    if "user_profiles" in present_tables:
        try:
            r = client.table("user_profiles").upsert({
                "user_id": test_id,
                "name": "Probe Operator",
            }).execute()
            client.table("user_profiles").delete().eq("user_id", test_id).execute()
            print(" [PASS] 'user_profiles' write & delete succeeded.")
            write_status["user_profiles"] = True
        except Exception as e:
            print(f" [RLS BLOCK] 'user_profiles' write blocked: {e}")
            write_status["user_profiles"] = False

    print("\n--- 3. STORAGE BUCKET CHECK ---")
    try:
        buckets = client.storage.list_buckets()
        bucket_names = [b.name for b in buckets] if buckets else []
        if "chai-files" in bucket_names:
            print(" [PASS] Storage bucket 'chai-files' is active.")
        else:
            print(f" [NOTICE] Storage buckets found: {bucket_names}. 'chai-files' bucket not found.")
    except Exception as e:
        print(f" [STORAGE] Could not query storage buckets: {e}")

    print("\n" + "=" * 65)
    all_ready = len(missing_tables) == 0 and all(write_status.values())
    if all_ready:
        print("  RESULT: FULLY OPERATIONAL (All tables, RLS, and storage ready)")
    else:
        print("  RESULT: ACTION NEEDED (SQL Migration required in Supabase Dashboard)")
        print("  Run: supabase/migrations/004_complete_chai_setup.sql in:")
        print(f"  https://supabase.com/dashboard/project/{url.split('//')[1].split('.')[0]}/sql/new")
    print("=" * 65)
    return all_ready


if __name__ == "__main__":
    verify_supabase()

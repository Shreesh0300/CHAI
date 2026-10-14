import uuid
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from backend.shared.supabase_client import get_supabase_client
from backend.shared.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

# In-memory storage for demonstration and local sessions
_users_db: Dict[str, dict] = {}
_sessions_db: Dict[str, str] = {}

class SignUpRequest(BaseModel):
    name: str
    email: str
    password: Optional[str] = None

class SignInRequest(BaseModel):
    email: str
    password: Optional[str] = None

class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None

class SyncProfileRequest(BaseModel):
    id: str
    email: str
    name: Optional[str] = None

class AuthResponse(BaseModel):
    id: str
    name: str
    email: str
    token: str


def _sync_profile_to_supabase(user_id: str, email: str, name: Optional[str] = None):
    """Upserts user profile to Supabase public.profiles table."""
    try:
        supabase = get_supabase_client()
        if supabase:
            supabase.table("profiles").upsert({
                "id": user_id,
                "email": email,
                "full_name": name or email.split("@")[0],
                "updated_at": "now()",
            }).execute()
            logger.info(f"[AUTH] Profile synced to Supabase for user_id={user_id}")
    except Exception as e:
        logger.warning(f"[AUTH] Supabase profile sync failed: {e}")


@router.post("/sign-up", response_model=AuthResponse)
async def sign_up(req: SignUpRequest):
    if req.email in _users_db:
        # Existing user returns session
        user = _users_db[req.email]
        token = str(uuid.uuid4())
        _sessions_db[token] = user["id"]
        return AuthResponse(id=user["id"], name=user["name"], email=user["email"], token=token)
    
    user_id = str(uuid.uuid4())
    user = {
        "id": user_id,
        "name": req.name,
        "email": req.email,
        "password": req.password or ""
    }
    _users_db[req.email] = user
    token = str(uuid.uuid4())
    _sessions_db[token] = user_id

    # Sync to Supabase
    _sync_profile_to_supabase(user_id, req.email, req.name)

    return AuthResponse(id=user_id, name=user["name"], email=user["email"], token=token)


@router.post("/sign-in", response_model=AuthResponse)
async def sign_in(req: SignInRequest):
    user = _users_db.get(req.email)
    if not user:
        # Auto-create for demo/guest experience
        user_id = str(uuid.uuid4())
        name = req.email.split("@")[0].capitalize()
        user = {
            "id": user_id,
            "name": name,
            "email": req.email,
            "password": req.password or ""
        }
        _users_db[req.email] = user
    
    token = str(uuid.uuid4())
    _sessions_db[token] = user["id"]

    # Sync to Supabase
    _sync_profile_to_supabase(user["id"], req.email, user.get("name"))

    return AuthResponse(id=user["id"], name=user["name"], email=user["email"], token=token)


@router.post("/sync-profile")
async def sync_profile(
    req: SyncProfileRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Syncs a user profile to Supabase public.profiles table.
    Called by the frontend after sign-in/sign-up.
    """
    _sync_profile_to_supabase(req.id, req.email, req.name)
    return {"success": True, "id": req.id, "email": req.email}


@router.get("/profile")
async def get_profile(user_id: str):
    """Fetches a user profile from Supabase public.profiles."""
    try:
        supabase = get_supabase_client()
        if supabase:
            result = supabase.table("profiles").select("*").eq("id", user_id).maybe_single().execute()
            if result.data:
                return result.data
    except Exception as e:
        logger.warning(f"[AUTH] Profile fetch failed: {e}")
    return {"id": user_id, "email": "", "full_name": ""}


@router.post("/sign-out")
async def sign_out():
    return {"success": True, "message": "Signed out successfully"}


@router.get("/session")
async def get_session():
    # Returns default session or guest user
    return {"authenticated": True, "user": {"name": "CHAI Operator", "email": "operator@chai.ai"}}


@router.post("/update-user")
async def update_user(req: UpdateUserRequest):
    return {"success": True, "updated": req.dict(exclude_unset=True)}

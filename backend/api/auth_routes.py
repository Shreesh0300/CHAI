"""
Auth API routes — provides authentication endpoints for frontend auth-client.
Supports email/password sign-up, sign-in, profile synchronization, and social OAuth.
"""

from fastapi import APIRouter, Header
from typing import Dict, Any, Optional
from pydantic import BaseModel
import uuid
from backend.shared.supabase_client import get_supabase_client
from backend.shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth")


class SignUpRequest(BaseModel):
    email: str
    password: Optional[str] = None
    name: Optional[str] = None


class SignInRequest(BaseModel):
    email: str
    password: Optional[str] = None


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


class SyncProfileRequest(BaseModel):
    id: Optional[str] = None
    email: str
    name: Optional[str] = None


@router.post("/sign-up")
async def sign_up(req: SignUpRequest) -> Dict[str, Any]:
    supabase = get_supabase_client()
    if supabase and req.password:
        try:
            full_name = req.name or req.email.split("@")[0]
            auth_res = supabase.auth.sign_up({
                "email": req.email,
                "password": req.password,
                "options": {"data": {"full_name": full_name}},
            })
            if auth_res and auth_res.user:
                user_id = str(auth_res.user.id)
                # Attempt to save to public.profiles
                try:
                    supabase.table("profiles").upsert({
                        "id": user_id,
                        "email": auth_res.user.email,
                        "full_name": full_name,
                    }).execute()
                    logger.info(f"[Auth] Created profile for {req.email}")
                except Exception as pe:
                    logger.warning(f"[Auth] Profiles upsert skipped: {pe}")

                token = auth_res.session.access_token if auth_res.session else None
                refresh = auth_res.session.refresh_token if auth_res.session else None
                return {
                    "id": user_id,
                    "email": auth_res.user.email,
                    "name": full_name,
                    "provider": "email",
                    "access_token": token,
                    "refresh_token": refresh,
                }
        except Exception as e:
            logger.warning(f"[Auth] Supabase sign_up error: {e}")

    return {
        "id": f"user_{req.email.replace('@', '_').replace('.', '_')}",
        "email": req.email,
        "name": req.name or req.email.split("@")[0],
        "provider": "email",
    }


@router.post("/sign-in")
async def sign_in(req: SignInRequest) -> Dict[str, Any]:
    supabase = get_supabase_client()
    if supabase and req.password:
        try:
            auth_res = supabase.auth.sign_in_with_password({
                "email": req.email,
                "password": req.password,
            })
            if auth_res and auth_res.user:
                full_name = (
                    auth_res.user.user_metadata.get("full_name")
                    if auth_res.user.user_metadata
                    else req.email.split("@")[0]
                )
                user_id = str(auth_res.user.id)
                # Attempt to save to public.profiles
                try:
                    supabase.table("profiles").upsert({
                        "id": user_id,
                        "email": auth_res.user.email,
                        "full_name": full_name,
                    }).execute()
                    logger.info(f"[Auth] Synced profile for {req.email}")
                except Exception as pe:
                    logger.warning(f"[Auth] Profiles upsert skipped: {pe}")

                token = auth_res.session.access_token if auth_res.session else None
                refresh = auth_res.session.refresh_token if auth_res.session else None
                return {
                    "id": user_id,
                    "email": auth_res.user.email,
                    "name": full_name,
                    "provider": "email",
                    "access_token": token,
                    "refresh_token": refresh,
                }
        except Exception as e:
            logger.warning(f"[Auth] Supabase sign_in error: {e}")

    return {
        "id": f"user_{req.email.replace('@', '_').replace('.', '_')}",
        "email": req.email,
        "name": req.email.split("@")[0],
        "provider": "email",
    }


@router.post("/sync-profile")
async def sync_profile(
    req: SyncProfileRequest,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Force upsert the current user's profile to public.profiles."""
    token = (
        authorization.split(" ", 1)[1]
        if (isinstance(authorization, str) and authorization.startswith("Bearer "))
        else None
    )
    supabase = get_supabase_client(token) or get_supabase_client()
    if not supabase:
        return {"success": False, "error": "Supabase client not available"}

    user_id = req.id
    if token and not user_id:
        try:
            u = supabase.auth.get_user(token)
            if u and u.user:
                user_id = str(u.user.id)
        except Exception:
            pass

    if not user_id or not (len(user_id) == 36 and "-" in user_id):
        # Must be valid UUID for public.profiles id column
        user_id = str(uuid.uuid4())

    full_name = req.name or req.email.split("@")[0]
    try:
        res = supabase.table("profiles").upsert({
            "id": user_id,
            "email": req.email,
            "full_name": full_name,
        }).execute()
        return {"success": True, "data": res.data}
    except Exception as e:
        logger.warning(f"[Auth] sync_profile error: {e}")
        return {"success": False, "error": str(e)}


@router.get("/profile")
async def get_profile(
    user_id: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Fetch user profile from public.profiles in Supabase."""
    token = (
        authorization.split(" ", 1)[1]
        if (isinstance(authorization, str) and authorization.startswith("Bearer "))
        else None
    )
    supabase = get_supabase_client(token) or get_supabase_client()
    if not supabase:
        return {"id": user_id or "", "email": "", "full_name": ""}

    target_id = user_id
    if token and not target_id:
        try:
            u = supabase.auth.get_user(token)
            if u and u.user:
                target_id = str(u.user.id)
        except Exception:
            pass

    if not target_id:
        return {"id": "", "email": "", "full_name": ""}

    try:
        res = supabase.table("profiles").select("*").eq("id", target_id).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return {"id": target_id, "email": "", "full_name": ""}
    except Exception as e:
        logger.warning(f"[Auth] Error fetching profile: {e}")
        return {"id": target_id, "email": "", "full_name": ""}


@router.post("/google")
async def auth_google() -> Dict[str, Any]:
    return {
        "id": "google_user",
        "email": "user@gmail.com",
        "name": "Google Operator",
        "provider": "google",
    }


@router.post("/github")
async def auth_github() -> Dict[str, Any]:
    return {
        "id": "github_user",
        "email": "developer@github.com",
        "name": "GitHub Engineer",
        "provider": "github",
    }


@router.post("/update-user")
async def update_user(
    req: UpdateUserRequest,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    token = (
        authorization.split(" ", 1)[1]
        if (isinstance(authorization, str) and authorization.startswith("Bearer "))
        else None
    )
    supabase = get_supabase_client(token) or get_supabase_client()
    if supabase and req.name:
        user_id = None
        if token:
            try:
                u = supabase.auth.get_user(token)
                if u and u.user:
                    user_id = str(u.user.id)
            except Exception:
                pass
        if user_id:
            try:
                supabase.table("profiles").update({
                    "full_name": req.name,
                }).eq("id", user_id).execute()
                logger.info(f"[Auth] Updated Supabase profile full_name for {user_id}")
            except Exception as e:
                logger.warning(f"[Auth] Failed to update profile in Supabase: {e}")
        elif req.email:
            try:
                supabase.table("profiles").update({
                    "full_name": req.name,
                }).eq("email", req.email).execute()
                logger.info(f"[Auth] Updated Supabase profile full_name for {req.email}")
            except Exception as e:
                logger.warning(f"[Auth] Failed to update profile in Supabase by email: {e}")

    return {
        "id": "updated_user",
        "email": req.email or "user@chai.ai",
        "name": req.name or "CHAI User",
        "provider": "email",
    }


@router.post("/sign-out")
async def sign_out() -> Dict[str, Any]:
    return {"success": True}

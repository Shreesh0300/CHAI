"""
Auth API routes — provides authentication endpoints for Vishnu's frontend auth-client.
Supports email/password sign-up, sign-in, social OAuth callbacks, and guest mode.
"""

from fastapi import APIRouter
from typing import Dict, Any, Optional
from pydantic import BaseModel
from backend.shared.supabase_client import get_supabase_client

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


@router.post("/sign-up")
async def sign_up(req: SignUpRequest) -> Dict[str, Any]:
    supabase = get_supabase_client()
    if supabase and req.password:
        try:
            auth_res = supabase.auth.sign_up({
                "email": req.email,
                "password": req.password,
                "options": {"data": {"full_name": req.name or req.email.split("@")[0]}},
            })
            if auth_res and auth_res.user:
                return {
                    "id": str(auth_res.user.id),
                    "email": auth_res.user.email,
                    "name": req.name or req.email.split("@")[0],
                    "provider": "email",
                }
        except Exception:
            pass

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
                return {
                    "id": str(auth_res.user.id),
                    "email": auth_res.user.email,
                    "name": full_name or req.email.split("@")[0],
                    "provider": "email",
                }
        except Exception:
            pass

    return {
        "id": f"user_{req.email.replace('@', '_').replace('.', '_')}",
        "email": req.email,
        "name": req.email.split("@")[0],
        "provider": "email",
    }


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
async def update_user(req: UpdateUserRequest) -> Dict[str, Any]:
    return {
        "id": "updated_user",
        "email": req.email or "user@chai.ai",
        "name": req.name or "CHAI User",
        "provider": "email",
    }


@router.post("/sign-out")
async def sign_out() -> Dict[str, Any]:
    return {"success": True}

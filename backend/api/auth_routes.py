import uuid
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr

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

class AuthResponse(BaseModel):
    id: str
    name: str
    email: str
    token: str

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
    return AuthResponse(id=user["id"], name=user["name"], email=user["email"], token=token)

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

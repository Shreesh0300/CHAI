from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import get_settings
from backend.api.health import router as health_router
from backend.api.routes import router as api_router
from backend.api.chat_routes import router as chat_router
from backend.api.auth_routes import router as auth_router
from backend.api.history_routes import router as history_router

def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CHAI Platform API", version="0.1.0")

    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        settings.frontend_url,
    ]
    unique_origins = list(dict.fromkeys(filter(None, allowed_origins)))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=unique_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def root_health_check():
        return {"status": "ok", "service": "chai-backend"}

    app.include_router(health_router, prefix="/api")
    app.include_router(api_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(history_router, prefix="/api/history")
    
    return app

app = create_app()

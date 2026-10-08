from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import get_settings
from backend.api.health import router as health_router
from backend.api.routes import router as api_router
from backend.api.auth_routes import router as auth_router
from backend.api.history_routes import router as history_router
from backend.api.voice_routes import router as voice_router

def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CHAI Platform API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*", settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api")
    app.include_router(api_router, prefix="/api")
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(history_router, prefix="/api/history")
    app.include_router(voice_router, prefix="/api")
    app.include_router(voice_router)
    
    return app

app = create_app()

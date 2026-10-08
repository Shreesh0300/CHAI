from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import get_settings
from backend.api.health import router as health_router
from backend.api.routes import router as api_router
from backend.api.voice_routes import router as voice_router
from backend.api.auth_routes import router as auth_router
from backend.api.history_routes import router as history_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CHAI Platform API", version="0.1.0")

    # Vite and development frontend origins
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    if settings.frontend_url and settings.frontend_url not in allowed_origins:
        allowed_origins.append(settings.frontend_url)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health endpoints
    app.include_router(health_router, prefix="/api")
    app.include_router(health_router)

    # Primary solve API (/api/solve)
    app.include_router(api_router, prefix="/api")

    # History API (/api/history)
    app.include_router(history_router, prefix="/api")

    # Auth API (/api/auth/...)
    app.include_router(auth_router, prefix="/api")

    # Voice API (/api/voice/..., /voice/..., /api/stt)
    app.include_router(voice_router, prefix="/api")
    app.include_router(voice_router)

    return app


app = create_app()

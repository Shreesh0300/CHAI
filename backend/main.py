import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.api.health import router as health_router
from backend.api.routes import router as api_router
from backend.api.voice_routes import router as voice_router
from backend.api.auth_routes import router as auth_router
from backend.api.history_routes import router as history_router
from backend.voice.wakeup_daemon import get_voice_wakeup_daemon
from backend.shared.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start background daemon only if explicitly requested; frontend Web Speech API handles browser voice
    autostart = os.getenv("VOICE_WAKEUP_AUTOSTART", "false").lower() in ("true", "1", "yes")
    daemon = get_voice_wakeup_daemon()
    if autostart:
        logger.info("[ServerStartup] 🎙️ Initializing hands-free autonomous Voice Wake-Up Daemon (Apple/Alexa style)...")
        daemon.start()
    else:
        logger.info("[ServerStartup] Voice wake-up daemon autostart disabled via VOICE_WAKEUP_AUTOSTART.")

    # Background opportunistic sync of cached conversations to Supabase
    try:
        from scripts.sync_to_supabase import sync_conversations
        import threading
        threading.Thread(target=sync_conversations, daemon=True).start()
    except Exception:
        pass

    yield

    # Shutdown
    logger.info("[ServerShutdown] Halting Voice Wake-Up Daemon...")
    daemon.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CHAI Platform API", version="0.1.0", lifespan=lifespan)

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

    # Optional Production SPA Static Serving (for Docker / Render Single-Service Deployment)
    dist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
    if os.path.isdir(dist_dir):
        from starlette.staticfiles import StaticFiles
        from starlette.responses import FileResponse

        assets_dir = os.path.join(dist_dir, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}")
        async def serve_frontend(full_path: str):
            if full_path.startswith("api") or full_path.startswith("voice") or full_path == "health":
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Not Found")
            target = os.path.join(dist_dir, full_path)
            if os.path.isfile(target):
                return FileResponse(target)
            return FileResponse(os.path.join(dist_dir, "index.html"))

    return app


app = create_app()

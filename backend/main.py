from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import get_settings
from backend.api.health import router as health_router
from backend.api.routes import router as api_router

def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CHAI Platform API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api")
    app.include_router(api_router, prefix="/api")
    
    return app

app = create_app()

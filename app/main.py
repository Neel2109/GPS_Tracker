"""
TrackGuard — Live Device GPS Tracking & Remote Control System
Unified FastAPI Backend + React Frontend Entry Point
"""
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from app.config import settings
from app.database import engine, init_db
from app.routers import access_requests, admin, auth, devices, locations, commands, websocket, tracking
from app.routers import privacy
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Path to built React frontend
FRONTEND_DIR = Path(__file__).parent.parent / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("🚀 TrackGuard Backend starting up...")
    await init_db()
    logger.info("✅ Database initialized")
    if FRONTEND_DIR.exists():
        logger.info(f"✅ Serving frontend from {FRONTEND_DIR}")
    else:
        logger.warning(f"⚠️  Frontend not built. Run: cd frontend && npm run build")
    yield
    logger.info("🛑 TrackGuard Backend shutting down...")


app = FastAPI(
    title="TrackGuard API",
    description=(
        "Secure real-time device tracking and remote control API. "
        "Monitor and manage registered devices from any browser or mobile device."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(access_requests.router)
app.include_router(devices.router)
app.include_router(locations.router)
app.include_router(commands.router)
app.include_router(websocket.router)
app.include_router(tracking.router)
app.include_router(privacy.router)


@app.get("/api")
async def api_root():
    """API health check."""
    return {
        "name": "TrackGuard API",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Report API and database readiness."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Health check database probe failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "database": "unavailable"},
        )
    return {"status": "healthy", "database": "healthy"}


# ─── Serve React Frontend (SPA) ──────────────────────────────
# Mount static assets (JS, CSS, images) from frontend/dist/assets
if FRONTEND_DIR.exists():
    assets_dir = FRONTEND_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # Serve other static files (favicon, manifest, icons, images)
    @app.get("/favicon.svg")
    @app.get("/favicon.ico")
    @app.get("/manifest.json")
    @app.get("/icon-192.png")
    @app.get("/icon-512.png")
    @app.get("/auth-bg.png")
    async def serve_static(request: Request):
        """Serve known static files from frontend dist."""
        file_path = FRONTEND_DIR / request.url.path.lstrip("/")
        if file_path.exists():
            return FileResponse(str(file_path))
        return HTMLResponse(status_code=404)

    # SPA catch-all: serve index.html for all non-API routes
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA for all non-API routes."""
        # Don't serve index.html for API, docs, or WebSocket routes
        if full_path.startswith(("api/", "docs", "redoc", "openapi", "ws/", "health")):
            return HTMLResponse(status_code=404)

        # Try to serve the exact file first
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))

        # Otherwise serve index.html (SPA routing)
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))

        return HTMLResponse("<h1>Frontend not built</h1><p>Run: cd frontend && npm run build</p>", status_code=404)

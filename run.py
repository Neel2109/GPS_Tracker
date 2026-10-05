"""
TrackGuard — Unified Server
Starts the FastAPI backend which serves both the API and the React frontend.

Usage:
    python run.py              # Start on port 8000
    python run.py --port 3000  # Start on custom port
    python run.py --build      # Build frontend first, then start
"""
import argparse
import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent
FRONTEND_DIR = ROOT
DIST_DIR = ROOT / "dist"


def build_frontend():
    """Build the React frontend."""
    print("[BUILD] Building frontend...")
    if not (FRONTEND_DIR / "node_modules").exists():
        print("   Installing npm dependencies...")
        subprocess.run(["npm", "install"], cwd=str(FRONTEND_DIR), check=True, shell=True)
    subprocess.run(["npm", "run", "build"], cwd=str(FRONTEND_DIR), check=True, shell=True)
    print("[OK] Frontend built successfully!")


def main():
    parser = argparse.ArgumentParser(description="TrackGuard Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run on (default: 8000)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--build", action="store_true", help="Build frontend before starting")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    if args.build or not DIST_DIR.exists():
        try:
            build_frontend()
        except Exception as e:
            print(f"[WARN] Frontend build failed: {e}")

    if not DIST_DIR.exists():
        print("[WARN] Frontend not built. Starting API only.")
        print("   Run: npm run build")

    print(f"\n[START] TrackGuard starting on http://{args.host}:{args.port}")
    print(f"   API docs:  http://localhost:{args.port}/docs")
    if DIST_DIR.exists():
        print(f"   Dashboard: http://localhost:{args.port}/")
    print()

    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()

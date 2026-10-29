"""
app/main.py — Project SAMARTH API entry point.

CHANGES IN THIS VERSION
  - Logging is configured BEFORE the app's own modules are imported, so
    messages those modules log at import time (e.g. the LLM mode) appear.
  - The user database is created on startup.
  - The authentication router is mounted.
  - CORS allows only the known frontend origins instead of "*". Auth uses
    bearer tokens in a header, not cookies, so credentials are not needed.
"""

import logging
import os

# Configure logging first — must run before importing app modules
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("samarth.main")

from contextlib import asynccontextmanager                      # noqa: E402
from pathlib import Path                                        # noqa: E402

from dotenv import load_dotenv                                  # noqa: E402
from fastapi import FastAPI, HTTPException                      # noqa: E402
from fastapi.middleware.cors import CORSMiddleware              # noqa: E402
from fastapi.responses import FileResponse                      # noqa: E402
from fastapi.staticfiles import StaticFiles                     # noqa: E402

from agents.model_config import DEMO_MODE                       # noqa: E402
from sqlmodel import Session                                     # noqa: E402

from app.db import engine, init_db                              # noqa: E402
from app.services.auth import ensure_admin_from_env             # noqa: E402
from app.services import demo                                   # noqa: E402
from app.routers.auth import router as auth_router             # noqa: E402
from app.routers.iep import router as iep_router               # noqa: E402
from app.routers.students import router as students_router     # noqa: E402
from app.routers.analytics import router as analytics_router   # noqa: E402
from app.routers.settings import router as settings_router     # noqa: E402
from rag.retriever import initialize_retriever, get_retriever_stats  # noqa: E402

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SAMARTH starting up…")

    init_db()
    with Session(engine) as session:
        ensure_admin_from_env(session)
    logger.info(f"Database ready ({engine.url.get_backend_name()})")

    if DEMO_MODE:
        demo.ensure_demo_account()
        info = demo.public_info()
        logger.info(
            f"DEMO MODE — replay only, no Gemini calls. "
            f"{len(info['samples'])} sample student(s), recorded on {info['recorded_on'] or '?'}"
        )

    logger.info("Initialising ChromaDB retriever…")
    try:
        initialize_retriever(docs_dir="./rag/documents")
        stats = get_retriever_stats()
        logger.info(f"Retriever ready — {stats['total_chunks']} chunks indexed")
    except Exception as e:
        logger.error(f"Retriever init failed: {e}")

    logger.info("SAMARTH ready ✓")
    yield
    logger.info("SAMARTH shutting down…")


app = FastAPI(
    title       = "Project SAMARTH",
    description = (
        "## Agentic Multi-Agent Suite for Inclusive Education\n\n"
        "Automates **IEP generation** for students with special needs.\n\n"
        "**Legally compliant** with RPwD Act 2016 and NCTE Guidelines.\n\n"
        "### Authentication\n"
        "Click **Authorize** and log in with your email as the username. "
        "Accounts are created by an administrator.\n\n"
        "### Pipeline\n"
        "`Student Input` → `Scraper` → `Compliance (RAG)` → `Drafting` → `PDF` → `Human Review`"
    ),
    version     = "1.1.0",
    lifespan    = lifespan,
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

# Only the frontend may call the API from a browser. Add your deployed
# frontend URL here (comma-separated) when you deploy.
_origins = [
    o.strip() for o in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins     = _origins,
    allow_credentials = False,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(auth_router)
app.include_router(iep_router)
app.include_router(students_router)
app.include_router(analytics_router)
app.include_router(settings_router)


# ── Optional: serve the built website from this server ──────────────────
# Set SAMARTH_FRONTEND_DIST to frontend/dist (the Docker image does). The
# site and the API then share one address: one link to share, no CORS.
# In local development leave it unset and use `npm run dev` as before.
_dist = os.getenv("SAMARTH_FRONTEND_DIST", "").strip()
FRONTEND_DIST = Path(_dist) if _dist and (Path(_dist) / "index.html").is_file() else None

if FRONTEND_DIST is not None:
    logger.info(f"Serving the website from {FRONTEND_DIST}")
    if (FRONTEND_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/", tags=["Root"])
async def root():
    if FRONTEND_DIST is not None:
        return FileResponse(FRONTEND_DIST / "index.html")
    return {
        "project":    "Project SAMARTH",
        "version":    "1.1.0",
        "docs":       "/docs",
        "compliance": ["RPwD Act 2016", "NCTE/NCERT Guidelines"],
        "iep_format": "NASET 11-section standard",
        "demo_mode":  DEMO_MODE,
    }


@app.get("/demo", tags=["Root"], summary="Online-demo details (public)")
async def demo_details():
    """
    Whether this server is the public demo and, if so, the shared login and
    the sample students. Returns {"enabled": false} on a normal server.
    """
    return demo.public_info()


if FRONTEND_DIST is not None:
    @app.get("/{filename}", include_in_schema=False)
    async def website_file(filename: str):
        """Top-level website files such as /favicon.svg. Registered last, so
        it never shadows an API route."""
        path = (FRONTEND_DIST / filename).resolve()
        if path.parent != FRONTEND_DIST.resolve() or not path.is_file():
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(path)
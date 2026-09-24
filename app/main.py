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

from dotenv import load_dotenv                                  # noqa: E402
from fastapi import FastAPI                                     # noqa: E402
from fastapi.middleware.cors import CORSMiddleware              # noqa: E402

from app.db import init_db                                      # noqa: E402
from app.routers.auth import router as auth_router             # noqa: E402
from app.routers.iep import router as iep_router               # noqa: E402
from rag.retriever import initialize_retriever, get_retriever_stats  # noqa: E402

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SAMARTH starting up…")

    init_db()
    logger.info("User database ready")

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


@app.get("/", tags=["Root"])
async def root():
    return {
        "project":    "Project SAMARTH",
        "version":    "1.1.0",
        "docs":       "/docs",
        "compliance": ["RPwD Act 2016", "NCTE/NCERT Guidelines"],
        "iep_format": "NASET 11-section standard",
    }
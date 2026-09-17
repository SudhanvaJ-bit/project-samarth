import logging
from contextlib import asynccontextmanager
from rag.retriever import initialize_retriever, get_retriever_stats
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.iep import router as iep_router
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("samarth.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info("SAMARTH starting up…")

    # Build or load ChromaDB vector index
    logger.info("Initialising ChromaDB retriever…")
    try:
        initialize_retriever(docs_dir="./rag/documents")
        stats = get_retriever_stats()
        logger.info(f"Retriever ready — {stats['total_chunks']} chunks indexed")
    except Exception as e:
        logger.error(f"Retriever init failed: {e}")
        # Don't crash — fallback to simple retriever if needed

    logger.info("SAMARTH ready ✓")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("SAMARTH shutting down…")



app = FastAPI(
    title       = "Project SAMARTH",
    description = (
        "## Agentic Multi-Agent Suite for Inclusive Education\n\n"
        "Automates **IEP generation** for students with special needs.\n\n"
        "**Legally compliant** with RPwD Act 2016 and NCTE Guidelines.\n\n"
        "### Pipeline\n"
        "`Student Input` → `Scraper` → `Compliance (RAG)` → `Drafting` → `PDF`\n\n"
        "### Standard\n"
        "Output follows the **NASET 11-section IEP format** adapted for India."
    ),
    version     = "1.0.0",
    lifespan    = lifespan,
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(iep_router)

@app.get("/", tags=["Root"])
async def root():
    return {
        "project":     "Project SAMARTH",
        "description": "Agentic IEP Generator for Inclusive Education",
        "version":     "1.0.0",
        "docs":        "/docs",
        "compliance":  ["RPwD Act 2016", "NCTE/NCERT Guidelines"],
        "iep_format":  "NASET 11-section standard",
        "endpoints": {
            "generate": "POST /iep/generate",
            "download": "GET  /iep/{iep_id}/download",
            "health":   "GET  /iep/health",
            "docs":     "GET  /docs",
        },
    }
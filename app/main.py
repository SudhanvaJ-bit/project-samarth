import logging
from contextlib import asynccontextmanager
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
    logger.info("🚀 SAMARTH API starting up...")
    from agents.graph import samarth_graph
    logger.info("  ✅ LangGraph compiled and ready")
    from rag.retriever import retriever
    retriever._cache_built if hasattr(retriever, '_cache_built') else None
    logger.info("  ✅ RAG retriever ready")
    logger.info("🎉 SAMARTH API ready!")
    yield
    logger.info("🛑 SAMARTH API shutting down...")



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
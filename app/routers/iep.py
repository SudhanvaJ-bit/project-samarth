"""
app/routers/iep.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IEP generation + HUMAN REVIEW endpoints.

Existing:
  POST /iep/generate               — manual form entry
  POST /iep/generate-from-report   — psychoeducational PDF upload
  GET  /iep/{id}/download          — stream the PDF
  GET  /iep/health

NEW — Human Review (Option 2: section editing before finalisation):
  GET  /iep/drafts                 — review queue
  GET  /iep/{id}/draft             — load 14 sections for editing
  PUT  /iep/{id}/draft             — save human edits (no LLM calls)
  POST /iep/{id}/finalize          — rebuild PDF from edited sections

Design note: editing and finalising make ZERO LLM calls. The pipeline
output is persisted by draft_store, and generate_iep_pdf() is invoked
directly on the edited content. This keeps review free of API quota.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import uuid
import logging
from pathlib import Path
from typing import Optional, Dict

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from rag.retriever import get_retriever_stats
from models.student import StudentInput, IEPResponse
from agents.graph import run_iep_pipeline
from app.services.report_extractor import extract_student_data_from_pdf
from app.services import draft_store
from pdf_generator.iep_pdf import generate_iep_pdf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/iep", tags=["IEP Generation"])

OUTPUTS_DIR = Path("./outputs")


# ─────────────────────────────────────────────────────────────────────────────
# Request models for the review endpoints
# ─────────────────────────────────────────────────────────────────────────────

class DraftEditRequest(BaseModel):
    """Human edits to one or more of the 14 NASET sections."""
    sections:     Dict[str, str] = Field(default_factory=dict)
    reviewed_by:  Optional[str]  = ""
    review_notes: Optional[str]  = ""
    approve:      bool           = False


class FinalizeRequest(BaseModel):
    """Optional last-moment edits applied before rebuilding the PDF."""
    sections:     Optional[Dict[str, str]] = None
    reviewed_by:  Optional[str] = ""
    review_notes: Optional[str] = ""


# ─────────────────────────────────────────────────────────────────────────────
# Helper — normalise enums / leaked enum strings to display strings
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_status(value) -> str:
    if value is None:
        return "Unknown"
    if hasattr(value, "value"):
        raw = str(value.value)
    elif hasattr(value, "name"):
        raw = str(value.name)
    else:
        raw = str(value)
    if "." in raw:
        raw = raw.split(".")[-1]
    return raw.replace("_", " ").title()


# ─────────────────────────────────────────────────────────────────────────────
# Shared helper — run pipeline, persist draft, build response
# ─────────────────────────────────────────────────────────────────────────────

def _run_and_respond(
    student_data: dict, iep_id: str, student_name: str, source: str
) -> IEPResponse:
    logger.info(f"[{source}] Starting IEP pipeline for: {student_name}")
    final_state = run_iep_pipeline(student_data, iep_id)

    workflow_status   = _normalise_status(final_state.get("workflow_status"))
    compliance_status = _normalise_status(
        (final_state.get("compliance_report") or {}).get("status", "unknown")
    )

    pdf_full_path = final_state.get("pdf_output_path", "")
    errors        = final_state.get("error_log", [])
    succeeded     = "completed" in workflow_status.lower()

    # ── Persist for Human Review — never let this break the response ──
    if final_state.get("drafted_iep"):
        try:
            draft_store.save_draft(final_state, iep_id, pdf_full_path)
        except Exception as e:
            logger.error(f"Draft persistence failed for {iep_id}: {e}")
            errors = list(errors) + [f"Draft not saved for review: {e}"]

    return IEPResponse(
        iep_id            = iep_id,
        student_name      = student_name,
        workflow_status   = workflow_status,
        compliance_status = compliance_status,
        pdf_output_path   = pdf_full_path if succeeded else None,
        generated_at      = final_state.get("generated_at"),
        errors            = errors,
        message           = (
            f"IEP generated. Review and edit at /iep/{iep_id}/draft, "
            f"or download at GET /iep/{iep_id}/download"
            if succeeded else
            f"IEP generation failed: {errors}"
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /iep/generate — manual form entry
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/generate",
    response_model = IEPResponse,
    status_code    = 201,
    summary        = "Generate a complete IEP for a student",
    description    = (
        "Runs the full SAMARTH multi-agent pipeline:\n\n"
        "Scraper → Compliance (RAG) → Drafting → PDF\n\n"
        "The drafted sections are saved for human review."
    ),
)
async def generate_iep(payload: StudentInput):
    iep_id = str(uuid.uuid4())
    try:
        student_data = {
            "student_id":           iep_id,
            "student_name":         payload.student_name,
            "age":                  payload.age,
            "grade":                payload.grade,
            "school_name":          payload.school_name,
            "disability_category":  payload.disability_category.value,
            "disability_severity":  payload.disability_severity.value,
            "raw_notes":            payload.raw_notes,
            "academic_history":     payload.academic_history     or "",
            "teacher_observations": payload.teacher_observations or "",
            "parent_concerns":      payload.parent_concerns      or "",
        }
        return _run_and_respond(student_data, iep_id, payload.student_name, "manual")

    except Exception as e:
        logger.error(f"Pipeline error for IEP {iep_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /iep/generate-from-report — psychoeducational PDF upload
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/generate-from-report",
    response_model = IEPResponse,
    status_code    = 201,
    summary        = "Upload a psychoeducational report PDF and generate an IEP",
)
async def generate_iep_from_report(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF too large. Maximum 20 MB.")

    iep_id = str(uuid.uuid4())

    try:
        extracted = extract_student_data_from_pdf(pdf_bytes)
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract student data from PDF: {str(e)}"
        )

    try:
        student_data = {
            "student_id":           iep_id,
            "student_name":         extracted["student_name"],
            "age":                  extracted["age"],
            "grade":                extracted["grade"],
            "school_name":          extracted.get("school_name", "Not Specified"),
            "disability_category":  extracted["disability_category"],
            "disability_severity":  extracted["disability_severity"],
            "raw_notes":            extracted["raw_notes"],
            "academic_history":     extracted.get("academic_history", ""),
            "teacher_observations": extracted.get("teacher_observations", ""),
            "parent_concerns":      extracted.get("parent_concerns", ""),
        }
    except KeyError as e:
        raise HTTPException(
            status_code=422, detail=f"Extraction missing required field: {e}"
        )

    try:
        return _run_and_respond(
            student_data, iep_id, extracted["student_name"], "pdf-report"
        )
    except Exception as e:
        logger.error(f"Pipeline error for IEP {iep_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


# ═════════════════════════════════════════════════════════════════════════════
# HUMAN REVIEW ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════════

# NOTE: /drafts is declared before /{iep_id}/... routes. FastAPI matches in
# declaration order; keeping single-segment literal paths first avoids any
# chance of them being captured as a path parameter.

@router.get(
    "/drafts",
    summary     = "List IEPs awaiting or completed human review",
    description = "Returns the review queue, newest first.",
)
async def list_drafts(limit: int = 50):
    return {"drafts": draft_store.list_drafts(limit=limit)}


@router.get(
    "/{iep_id}/draft",
    summary     = "Load the 14 editable NASET sections for human review",
    description = (
        "Returns each section's current text alongside its display label, "
        "plus a flag showing whether a human has already edited it."
    ),
)
async def get_draft(iep_id: str):
    record = draft_store.load_draft(iep_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No draft found for IEP ID: {iep_id}. "
                   f"The IEP may predate the review feature, or generation failed.",
        )

    drafted  = record.get("drafted_iep", {})
    original = record.get("original_iep", {})
    edited   = set(record.get("edited_sections", []))

    sections = [
        {
            "key":         key,
            "label":       label,
            "content":     str(drafted.get(key, "")),
            "original":    str(original.get(key, "")),
            "human_edited": key in edited,
        }
        for key, label in draft_store.EDITABLE_SECTIONS
    ]

    return {
        "iep_id":        iep_id,
        "student_name":  record.get("student_profile", {}).get("student_name", ""),
        "review_status": record.get("review_status", "pending"),
        "reviewed_by":   record.get("reviewed_by", ""),
        "review_notes":  record.get("review_notes", ""),
        "revision":      record.get("revision", 0),
        "edited_count":  len(edited),
        "sections":      sections,
    }


@router.put(
    "/{iep_id}/draft",
    summary     = "Save human edits to IEP sections",
    description = (
        "Merges edited sections into the stored draft. Makes no LLM calls. "
        "Unknown section keys are ignored."
    ),
)
async def update_draft(iep_id: str, payload: DraftEditRequest):
    record = draft_store.apply_edits(
        iep_id          = iep_id,
        edited_sections = payload.sections,
        reviewed_by     = payload.reviewed_by or "",
        review_notes    = payload.review_notes or "",
        approve         = payload.approve,
    )
    if record is None:
        raise HTTPException(
            status_code=404, detail=f"No draft found for IEP ID: {iep_id}"
        )

    return {
        "iep_id":        iep_id,
        "review_status": record["review_status"],
        "revision":      record["revision"],
        "edited_sections": record["edited_sections"],
        "message": (
            f"Saved. {len(record['edited_sections'])} section(s) human-edited. "
            f"Finalize at POST /iep/{iep_id}/finalize to rebuild the PDF."
        ),
    }


@router.post(
    "/{iep_id}/finalize",
    summary     = "Rebuild the PDF from human-reviewed sections",
    description = (
        "Applies any sections supplied in the body, marks the draft approved, "
        "and regenerates the PDF from the edited content. No LLM calls are made, "
        "so this consumes no API quota."
    ),
)
async def finalize_draft(iep_id: str, payload: FinalizeRequest = FinalizeRequest()):
    # Apply last-moment edits and mark approved in one step
    record = draft_store.apply_edits(
        iep_id          = iep_id,
        edited_sections = payload.sections or {},
        reviewed_by     = payload.reviewed_by or "",
        review_notes    = payload.review_notes or "",
        approve         = True,
    )
    if record is None:
        raise HTTPException(
            status_code=404, detail=f"No draft found for IEP ID: {iep_id}"
        )

    # Rebuild the PDF directly — no pipeline, no Gemini
    try:
        pdf_state = draft_store.to_pdf_state(record)
        pdf_path  = generate_iep_pdf(pdf_state, output_dir="outputs")
        draft_store.set_pdf_path(iep_id, pdf_path)
    except Exception as e:
        logger.error(f"Finalize PDF rebuild failed for {iep_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"PDF regeneration failed: {str(e)}"
        )

    logger.info(f"  ✅ Finalized IEP {iep_id} rev {record['revision']} → {pdf_path}")

    return {
        "iep_id":          iep_id,
        "review_status":   record["review_status"],
        "revision":        record["revision"],
        "edited_sections": record["edited_sections"],
        "pdf_output_path": pdf_path,
        "download_url":    f"/iep/{iep_id}/download",
        "message":         "IEP finalized. PDF rebuilt from reviewed content.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /iep/{iep_id}/download
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{iep_id}/download",
    summary     = "Download the generated IEP PDF",
    description = "Streams the most recent PDF for a given IEP id.",
)
async def download_iep(iep_id: str):
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    all_pdfs = list(OUTPUTS_DIR.glob("IEP_*.pdf"))

    matches = [p for p in all_pdfs if iep_id in p.name]
    if not matches:
        matches = [p for p in all_pdfs if iep_id[:8] in p.name]
    if not matches:
        matches = [p for p in all_pdfs if iep_id.replace("-", "")[:8] in p.name]

    if not matches:
        logger.error(
            f"Download 404: no PDF for IEP ID {iep_id}. "
            f"Files present: {[p.name for p in all_pdfs[:10]]}"
        )
        raise HTTPException(
            status_code=404,
            detail=f"No PDF found for IEP ID: {iep_id}. "
                   f"It may still be generating, or the ID may be incorrect.",
        )

    # Most recently modified wins — after finalize, that's the reviewed version
    pdf_path = max(matches, key=lambda p: p.stat().st_mtime)
    logger.info(f"Serving PDF: {pdf_path.name} for IEP ID: {iep_id}")

    return FileResponse(
        path       = str(pdf_path),
        filename   = pdf_path.name,
        media_type = "application/pdf",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /iep/health
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health", summary="Health check")
async def health():
    stats = get_retriever_stats()
    return {
        "status":         "ok",
        "service":        "SAMARTH IEP Generator",
        "rag_backend":    "ChromaDB",
        "chunks_indexed": stats["total_chunks"],
        "rag_ready":      stats["ready"],
        "drafts_stored":  len(draft_store.list_drafts(limit=1000)),
    }
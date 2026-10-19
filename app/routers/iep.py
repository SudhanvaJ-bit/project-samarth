"""
app/routers/iep.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IEP generation + HUMAN REVIEW endpoints.

ALL endpoints except /iep/health require an educator login.
Every IEP belongs to the educator who generated it; another account asking
for it receives 404, exactly as if it didn't exist.

  POST /iep/generate               — manual form entry
  POST /iep/generate-from-report   — psychoeducational PDF upload
  GET  /iep/drafts                 — your IEPs
  GET  /iep/{id}/draft             — student details + prose sections
  PUT  /iep/{id}/draft             — save edits (no LLM calls)
  POST /iep/{id}/finalize          — approve + rebuild PDF (no LLM calls)
  GET  /iep/{id}/download
  GET  /iep/health                 — public

REVIEWER IDENTITY
"reviewed_by" is taken from the logged-in account, not from the request.
Previously any name could be typed in; now the audit trail records who
actually made each change.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agents.graph import run_iep_pipeline
from agents.model_config import DEMO_MODE
from app.db import User
from app.services import demo, draft_store
from app.services.auth import require_educator
from app.services.report_extractor import extract_student_data_from_pdf
from models.student import IEPResponse, StudentInput
from pdf_generator.iep_pdf import generate_iep_pdf
from rag.retriever import get_retriever_stats

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/iep", tags=["IEP Generation"])

OUTPUTS_DIR = Path("./outputs")


# ─────────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────────

class DraftEditRequest(BaseModel):
    """Human edits — prose sections and/or structured student fields."""
    sections:     Dict[str, str] = Field(default_factory=dict)
    profile:      Dict[str, Any] = Field(default_factory=dict)
    review_notes: Optional[str]  = ""
    approve:      bool           = False
    # reviewed_by is intentionally absent: it comes from the logged-in user


class FinalizeRequest(BaseModel):
    sections:     Optional[Dict[str, str]] = None
    profile:      Optional[Dict[str, Any]] = None
    review_notes: Optional[str] = ""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
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


def _reviewer_label(user: User) -> str:
    return f"{user.full_name} ({user.email})"


def _not_found(iep_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"No IEP found with ID {iep_id}.")


def _owned_or_404(iep_id: str, user: User) -> dict:
    record = draft_store.load_owned_draft(iep_id, user.id)
    if record is None:
        raise _not_found(iep_id)
    return record


def _run_and_respond(student_data: dict, iep_id: str, student_name: str,
                     source: str, user: User) -> IEPResponse:
    logger.info(f"[{source}] {user.email} started IEP pipeline for: {student_name}")
    final_state = run_iep_pipeline(student_data, iep_id)

    workflow_status   = _normalise_status(final_state.get("workflow_status"))
    compliance_status = _normalise_status(
        (final_state.get("compliance_report") or {}).get("status", "unknown")
    )
    pdf_full_path = final_state.get("pdf_output_path", "")
    errors        = final_state.get("error_log", [])
    succeeded     = "completed" in workflow_status.lower()

    if final_state.get("drafted_iep"):
        try:
            draft_store.save_draft(final_state, iep_id, pdf_full_path, owner_id=user.id)
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
            "IEP generated. Open it in Review to check and approve it."
            if succeeded else f"IEP generation failed: {errors}"
        ),
    )


def _apply_or_error(iep_id: str, user: User, **kwargs) -> dict:
    """Apply edits; validation errors → 422, missing/not-owned → 404."""
    try:
        record = draft_store.apply_edits(iep_id=iep_id, owner_id=user.id, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if record is None:
        raise _not_found(iep_id)
    return record


# ─────────────────────────────────────────────────────────────────────────────
# Generation
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=IEPResponse, status_code=201,
             summary="Generate a complete IEP for a student")
async def generate_iep(payload: StudentInput, user: User = Depends(require_educator)):
    iep_id = str(uuid.uuid4())
    if DEMO_MODE and demo.matching_sample(payload.model_dump(mode="json")) is None:
        raise HTTPException(
            status_code=422,
            detail=("This online demo replays recorded runs, so it can only generate "
                    "the sample students. Pick one from 'Load a sample student' and "
                    "generate it without editing the fields."),
        )
    try:
        student_data = payload.to_pipeline_input(iep_id)
        return _run_and_respond(student_data, iep_id, payload.student_name, "manual", user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline error for IEP {iep_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@router.post("/generate-from-report", response_model=IEPResponse, status_code=201,
             summary="Upload a psychoeducational report PDF and generate an IEP")
async def generate_iep_from_report(file: UploadFile = File(...),
                                   user: User = Depends(require_educator)):
    if DEMO_MODE:
        # A public demo must never receive a real child's report
        raise HTTPException(status_code=403,
                            detail="PDF upload is turned off in the online demo.")
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
        raise HTTPException(status_code=422,
                            detail=f"Could not extract student data from PDF: {str(e)}")

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
        raise HTTPException(status_code=422, detail=f"Extraction missing required field: {e}")

    try:
        return _run_and_respond(student_data, iep_id, extracted["student_name"],
                                "pdf-report", user)
    except Exception as e:
        logger.error(f"Pipeline error for IEP {iep_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


# ═════════════════════════════════════════════════════════════════════════════
# HUMAN REVIEW
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/drafts", summary="Your IEPs, newest first")
async def list_drafts(limit: int = 50, user: User = Depends(require_educator)):
    return {"drafts": draft_store.list_drafts(owner_id=user.id, limit=limit)}


@router.get("/{iep_id}/draft", summary="Load student details and prose sections for review")
async def get_draft(iep_id: str, user: User = Depends(require_educator)):
    record = _owned_or_404(iep_id, user)

    profile          = record.get("student_profile", {})
    original_profile = record.get("original_profile", {})
    edited_fields    = set(record.get("edited_profile_fields", []))
    drafted          = record.get("drafted_iep", {})
    original         = record.get("original_iep", {})
    edited           = set(record.get("edited_sections", []))

    def as_text(v):
        return "" if v is None else str(v)

    return {
        "iep_id":        iep_id,
        "student_name":  profile.get("student_name", ""),
        "review_status": record.get("review_status", "pending"),
        "reviewed_by":   record.get("reviewed_by", ""),
        "review_notes":  record.get("review_notes", ""),
        "revision":      record.get("revision", 0),
        "edited_count":  len(edited) + len(edited_fields),
        "student": [
            {
                "key":          key,
                "label":        label,
                "value":        as_text(profile.get(key)),
                "original":     as_text(original_profile.get(key)),
                "human_edited": key in edited_fields,
            }
            for key, label in draft_store.EDITABLE_PROFILE_FIELDS
        ],
        "severity_options": list(draft_store.SEVERITY_VALUES),
        "sections": [
            {
                "key":          key,
                "label":        label,
                "content":      as_text(drafted.get(key, "")),
                "original":     as_text(original.get(key, "")),
                "human_edited": key in edited,
            }
            for key, label in draft_store.EDITABLE_SECTIONS
        ],
    }


@router.put("/{iep_id}/draft", summary="Save edits (no LLM calls)")
async def update_draft(iep_id: str, payload: DraftEditRequest,
                       user: User = Depends(require_educator)):
    record = _apply_or_error(
        iep_id, user,
        edited_sections = payload.sections,
        profile_edits   = payload.profile,
        reviewed_by     = _reviewer_label(user),
        review_notes    = payload.review_notes or "",
        approve         = payload.approve,
    )
    return {
        "iep_id":                iep_id,
        "review_status":         record["review_status"],
        "revision":              record["revision"],
        "reviewed_by":           record.get("reviewed_by", ""),
        "edited_sections":       record["edited_sections"],
        "edited_profile_fields": record["edited_profile_fields"],
        "message": (
            f"Saved. {len(record['edited_sections'])} section(s) and "
            f"{len(record['edited_profile_fields'])} student field(s) human-edited."
        ),
    }


@router.post("/{iep_id}/finalize", summary="Approve and rebuild the PDF (no LLM calls)")
async def finalize_draft(iep_id: str, payload: FinalizeRequest = FinalizeRequest(),
                         user: User = Depends(require_educator)):
    record = _apply_or_error(
        iep_id, user,
        edited_sections = payload.sections or {},
        profile_edits   = payload.profile or {},
        reviewed_by     = _reviewer_label(user),
        review_notes    = payload.review_notes or "",
        approve         = True,
    )

    try:
        pdf_path = generate_iep_pdf(draft_store.to_pdf_state(record), output_dir="outputs")
        draft_store.set_pdf_path(iep_id, pdf_path)
    except Exception as e:
        logger.error(f"Finalize PDF rebuild failed for {iep_id}: {e}")
        raise HTTPException(status_code=500, detail=f"PDF regeneration failed: {str(e)}")

    logger.info(f"  ✅ {user.email} finalized IEP {iep_id} rev {record['revision']}")
    return {
        "iep_id":                iep_id,
        "review_status":         record["review_status"],
        "revision":              record["revision"],
        "reviewed_by":           record.get("reviewed_by", ""),
        "edited_sections":       record["edited_sections"],
        "edited_profile_fields": record["edited_profile_fields"],
        "pdf_output_path":       pdf_path,
        "download_url":          f"/iep/{iep_id}/download",
        "message":               "IEP finalized. PDF rebuilt from reviewed content.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Download / health
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{iep_id}/download", summary="Download your IEP PDF")
async def download_iep(iep_id: str, user: User = Depends(require_educator)):
    record = _owned_or_404(iep_id, user)

    # Prefer the exact path recorded on the draft (updated on every rebuild)
    pdf_path = Path(record.get("pdf_path") or "")
    if not pdf_path.is_file():
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        matches = [p for p in OUTPUTS_DIR.glob("IEP_*.pdf") if iep_id[:8] in p.name]
        if not matches:
            raise HTTPException(status_code=404, detail="The PDF for this IEP is missing.")
        pdf_path = max(matches, key=lambda p: p.stat().st_mtime)

    logger.info(f"{user.email} downloaded {pdf_path.name}")
    return FileResponse(path=str(pdf_path), filename=pdf_path.name,
                        media_type="application/pdf")


@router.get("/health", summary="Health check (public)")
async def health():
    # Deliberately reveals nothing about stored IEPs — this endpoint is public.
    stats = get_retriever_stats()
    return {
        "status":         "ok",
        "service":        "SAMARTH IEP Generator",
        "rag_backend":    "ChromaDB",
        "chunks_indexed": stats["total_chunks"],
        "rag_ready":      stats["ready"],
        "demo_mode":      DEMO_MODE,
    }
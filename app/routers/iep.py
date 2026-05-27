"""
app/routers/iep.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 10 — IEP generation endpoints
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import uuid
import logging
from pathlib import Path

from fastapi           import APIRouter, HTTPException
from fastapi.responses import FileResponse

from models.student import StudentInput, IEPResponse
from agents.graph   import run_iep_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/iep", tags=["IEP Generation"])


@router.post(
    "/generate",
    response_model = IEPResponse,
    status_code    = 201,
    summary        = "Generate a complete IEP for a student",
    description    = (
        "Runs the full SAMARTH multi-agent pipeline:\n\n"
        "Scraper → Compliance (RAG) → Drafting → PDF\n\n"
        "Returns compliance status and PDF download path.\n"
        "Typical generation time: 60–90 seconds."
    ),
)
async def generate_iep(payload: StudentInput):
    iep_id = str(uuid.uuid4())

    try:
        # ── Build student data dict ───────────────────
        student_data = {
            "student_id":          iep_id,
            "student_name":        payload.student_name,
            "age":                 payload.age,
            "grade":               payload.grade,
            "school_name":         payload.school_name,
            "disability_category": payload.disability_category.value,
            "disability_severity": payload.disability_severity.value,
            "raw_notes":           payload.raw_notes,
            "academic_history":    payload.academic_history    or "",
            "teacher_observations":payload.teacher_observations or "",
            "parent_concerns":     payload.parent_concerns     or "",
        }

        # ── Run the pipeline ──────────────────────────
        logger.info(f"Starting IEP pipeline for: {payload.student_name}")
        final_state = run_iep_pipeline(student_data, iep_id)

        # ── Extract results ───────────────────────────
        workflow_status   = str(final_state.get("workflow_status",  "unknown"))
        compliance_status = str(
            final_state.get("compliance_report", {}).get("status", "unknown")
        )
        pdf_path  = final_state.get("pdf_output_path", "")
        errors    = final_state.get("error_log", [])
        succeeded = "completed" in workflow_status.lower()

        return IEPResponse(
            iep_id            = iep_id,
            student_name      = payload.student_name,
            workflow_status   = workflow_status,
            compliance_status = compliance_status,
            pdf_output_path   = pdf_path if succeeded else None,
            generated_at      = final_state.get("generated_at"),
            errors            = errors,
            message           = (
                f"IEP generated successfully. "
                f"Download at: GET /iep/{iep_id}/download"
                if succeeded else
                f"IEP generation failed: {errors}"
            ),
        )

    except Exception as e:
        logger.error(f"Pipeline error for IEP {iep_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@router.get(
    "/{iep_id}/download",
    summary     = "Download the generated IEP PDF",
    description = "Streams the PDF file for a previously generated IEP.",
)
async def download_iep(iep_id: str):
    outputs_dir = Path("./outputs")
    matches     = list(outputs_dir.glob(f"IEP_*_{iep_id[:8]}*.pdf"))

    if not matches:
        raise HTTPException(
            status_code = 404,
            detail      = f"No PDF found for IEP ID: {iep_id}",
        )

    pdf_path = matches[0]
    return FileResponse(
        path       = str(pdf_path),
        filename   = pdf_path.name,
        media_type = "application/pdf",
    )


@router.get("/health", summary="Health check")
async def health():
    return {"status": "ok", "service": "SAMARTH IEP Generator"}
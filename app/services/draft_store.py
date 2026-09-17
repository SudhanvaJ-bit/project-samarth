"""
app/services/draft_store.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DRAFT STORE — persistence layer for the Human Review step.

Saves the full pipeline state needed to regenerate a PDF, so a
teacher can edit any of the 14 NASET sections and rebuild the
document WITHOUT re-running any LLM calls.

Storage: JSON files under ./drafts/{iep_id}.json
(Swap for PostgreSQL when that roadmap item lands — the interface
 here is deliberately small so the swap is contained.)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DRAFTS_DIR = Path("./drafts")
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

# The 14 editable NASET sections, in document order.
# Used by both the API validator and the frontend editor.
EDITABLE_SECTIONS = [
    ("background_info",                 "Section 1 — Background Information"),
    ("academic_performance",            "Section 2A — Academic / Educational Achievement"),
    ("social_development",              "Section 2B — Social Development"),
    ("physical_development",            "Section 2C — Physical Development"),
    ("management_needs",                "Section 2D — Management Needs"),
    ("long_term_outcomes",              "Section 3 — Long-Term Adult Outcomes"),
    ("annual_goals",                    "Section 4 — Annual Goals & Short-Term Objectives"),
    ("special_education_services",      "Section 5 — Special Education Programs & Services"),
    ("general_education_participation", "Section 6 — Participation in General Education"),
    ("participating_agencies",          "Section 7 — Participating Agencies"),
    ("coordinated_activities",          "Section 8 — Coordinated Set of Activities"),
    ("graduation_info",                 "Section 9 — Graduation / School Completion"),
    ("recommendations_summary",         "Section 10 — Summary of Recommendations"),
    ("progress_reporting",              "Section 11 — Reporting Progress to Parents"),
]

SECTION_KEYS = [k for k, _ in EDITABLE_SECTIONS]


def _draft_path(iep_id: str) -> Path:
    """Resolve the JSON path for an IEP id, guarding against traversal."""
    safe_id = "".join(c for c in str(iep_id) if c.isalnum() or c in "-_")
    if not safe_id:
        raise ValueError(f"Invalid iep_id: {iep_id!r}")
    return DRAFTS_DIR / f"{safe_id}.json"


def _enum_safe(value):
    """Convert enums (ComplianceStatus, WorkflowStatus) to plain strings."""
    if hasattr(value, "value"):
        return str(value.value)
    if hasattr(value, "name"):
        return str(value.name)
    return value


def _clean_for_json(obj):
    """Recursively strip enums so the state can be JSON-serialised."""
    if isinstance(obj, dict):
        return {k: _clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_for_json(v) for v in obj]
    if hasattr(obj, "value") or hasattr(obj, "name"):
        return _enum_safe(obj)
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# SAVE
# ─────────────────────────────────────────────────────────────────────────────

def save_draft(state: dict, iep_id: str, pdf_path: str = "") -> str:
    """
    Persist everything generate_iep_pdf() needs to rebuild the document:
      student_profile, drafted_iep, compliance_report.

    Called automatically at the end of the pipeline run.
    Returns the path written.
    """
    path = _draft_path(iep_id)

    record = {
        "iep_id":            iep_id,
        "student_profile":   _clean_for_json(state.get("student_profile", {})),
        "drafted_iep":       _clean_for_json(state.get("drafted_iep", {})),
        "compliance_report": _clean_for_json(state.get("compliance_report", {})),

        # Review metadata
        "review_status":     "pending",   # pending | edited | approved
        "reviewed_by":       "",
        "review_notes":      "",
        "edited_sections":   [],          # keys the human changed
        "revision":          0,

        # Provenance — the ORIGINAL AI output, never overwritten.
        # Lets the UI show a diff and lets you prove what the model produced.
        "original_iep":      _clean_for_json(state.get("drafted_iep", {})),

        "pdf_path":          pdf_path,
        "created_at":        datetime.now(timezone.utc).isoformat(),
        "updated_at":        datetime.now(timezone.utc).isoformat(),
    }

    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"  💾 Draft saved for review: {path}")
    return str(path)


# ─────────────────────────────────────────────────────────────────────────────
# LOAD
# ─────────────────────────────────────────────────────────────────────────────

def load_draft(iep_id: str) -> Optional[dict]:
    """Return the stored draft record, or None if not found."""
    path = _draft_path(iep_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.error(f"Draft file corrupt for {iep_id}: {e}")
        return None


def list_drafts(limit: int = 50) -> list:
    """
    Return summaries of stored drafts, newest first.
    Used by the My IEPs / review queue view.
    """
    out = []
    for p in DRAFTS_DIR.glob("*.json"):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({
            "iep_id":        rec.get("iep_id", p.stem),
            "student_name":  rec.get("student_profile", {}).get("student_name", "Unknown"),
            "review_status": rec.get("review_status", "pending"),
            "revision":      rec.get("revision", 0),
            "created_at":    rec.get("created_at", ""),
            "updated_at":    rec.get("updated_at", ""),
        })
    out.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return out[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE
# ─────────────────────────────────────────────────────────────────────────────

def apply_edits(
    iep_id: str,
    edited_sections: dict,
    reviewed_by: str = "",
    review_notes: str = "",
    approve: bool = False,
) -> Optional[dict]:
    """
    Merge human edits into the stored draft.

    Only keys in SECTION_KEYS are accepted — anything else is ignored,
    so a malformed request can't inject arbitrary fields into state.

    Tracks WHICH sections the human changed (compared against the
    original AI output) so the audit trail shows human vs machine authorship.

    Returns the updated record, or None if the draft doesn't exist.
    """
    record = load_draft(iep_id)
    if record is None:
        return None

    drafted  = dict(record.get("drafted_iep", {}))
    original = record.get("original_iep", {})
    changed  = set(record.get("edited_sections", []))

    rejected = []
    for key, value in (edited_sections or {}).items():
        if key not in SECTION_KEYS:
            rejected.append(key)
            continue
        if not isinstance(value, str):
            value = str(value)
        drafted[key] = value
        # Mark as human-edited only if it differs from the ORIGINAL AI text
        if value.strip() != str(original.get(key, "")).strip():
            changed.add(key)
        else:
            changed.discard(key)

    if rejected:
        logger.warning(f"apply_edits: ignored unknown section keys: {rejected}")

    record["drafted_iep"]     = drafted
    record["edited_sections"] = sorted(changed)
    record["revision"]        = record.get("revision", 0) + 1
    record["updated_at"]      = datetime.now(timezone.utc).isoformat()

    if reviewed_by:
        record["reviewed_by"] = reviewed_by
    if review_notes:
        record["review_notes"] = review_notes

    record["review_status"] = "approved" if approve else "edited"

    _draft_path(iep_id).write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(
        f"  ✏️  Draft {iep_id} rev {record['revision']} — "
        f"{len(changed)} section(s) human-edited, status={record['review_status']}"
    )
    return record


def set_pdf_path(iep_id: str, pdf_path: str) -> None:
    """Record the regenerated PDF path against a draft."""
    record = load_draft(iep_id)
    if record is None:
        return
    record["pdf_path"]   = pdf_path
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    _draft_path(iep_id).write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def to_pdf_state(record: dict) -> dict:
    """
    Rebuild the minimal state dict that generate_iep_pdf() expects.

    generate_iep_pdf() reads:
      student_id / iep_id, student_profile, drafted_iep, compliance_report
    """
    return {
        "student_id":        record.get("iep_id", ""),
        "iep_id":            record.get("iep_id", ""),
        "student_profile":   record.get("student_profile", {}),
        "drafted_iep":       record.get("drafted_iep", {}),
        "compliance_report": record.get("compliance_report", {}),
    }
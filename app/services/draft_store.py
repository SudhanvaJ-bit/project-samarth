"""
app/services/draft_store.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DRAFT STORE — persistence layer for the Human Review step.

Saves everything generate_iep_pdf() needs to rebuild the document, so a
teacher can edit the IEP and rebuild it WITHOUT any LLM calls.

Storage: one row per IEP in the iep_drafts table (app/db.py) — SQLite
locally, PostgreSQL online. The draft is kept as one JSON document, so the
editing logic below works on a plain dict. Earlier versions wrote
./drafts/{iep_id}.json; import those with scripts/import_file_drafts.py.

WHAT CAN BE EDITED
  1. Student details (Section 1) — STRUCTURED fields on student_profile:
     name, age, grade, school, disability, severity, language.
     The PDF's Section 1 table reads these directly.
  2. Prose sections (Sections 2–11) — the drafting agent's text.

WHY SECTION 1 IS A FORM, NOT A TEXT BOX
Section 1 used to be edited as background_info prose. But the PDF builds
Section 1 from the structured profile, not from that prose — so editing
the prose (e.g. grade 5.7 → 5) saved correctly yet changed nothing in the
PDF. Structured data is now edited as structured data.

AUDIT TRAIL
original_iep and original_profile hold the untouched AI output forever.
edited_sections / edited_profile_fields record exactly what a human changed.

OWNERSHIP
Every draft records owner_id — the educator who generated it. Only that
educator can read, edit, rebuild or download it.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import copy
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app.db import IEPDraft, engine

logger = logging.getLogger(__name__)


# ── Section 1: structured student fields ─────────────
EDITABLE_PROFILE_FIELDS = [
    ("student_name",        "Student Name"),
    ("age",                 "Age"),
    ("grade",               "Current Grade"),
    ("school_name",         "School / Agency"),
    ("disability_category", "Disability Category"),
    ("disability_severity", "Severity"),
    ("dominant_language",   "Dominant Language"),
]
PROFILE_KEYS = [k for k, _ in EDITABLE_PROFILE_FIELDS]

SEVERITY_VALUES = ("Mild", "Moderate", "Severe")


# ── Sections 2–11: prose written by the drafting agent ──
# background_info is intentionally NOT here — its facts are edited through
# the structured fields above, and the prose itself is not printed.
EDITABLE_SECTIONS = [
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


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_id(iep_id: str) -> str:
    """IEP ids are UUIDs; reject anything else outright."""
    text = str(iep_id)
    if not text or len(text) > 64 or any(not (c.isalnum() or c in "-_") for c in text):
        raise ValueError(f"Invalid iep_id: {iep_id!r}")
    return text


def _db_now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_for_json(obj):
    """Recursively convert enums to plain strings so state serialises."""
    if isinstance(obj, dict):
        return {k: _clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_for_json(v) for v in obj]
    if hasattr(obj, "value"):
        return str(obj.value)
    if hasattr(obj, "name") and not isinstance(obj, (str, int, float, bool)):
        return str(obj.name)
    return obj


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(iep_id: str, record: dict) -> None:
    """Insert or update one draft row."""
    iep_id = _safe_id(iep_id)
    # Round-trip through JSON so only plain data is stored (no enums, dates)
    record = json.loads(json.dumps(record, ensure_ascii=False, default=str))
    now = _db_now()
    with Session(engine) as session:
        row = session.get(IEPDraft, iep_id)
        if row is None:
            row = IEPDraft(iep_id=iep_id, owner_id=record.get("owner_id"),
                           record=record, created_at=now, updated_at=now)
        else:
            row.record     = record
            row.owner_id   = record.get("owner_id")
            row.updated_at = now
            flag_modified(row, "record")     # JSON column changed in place
        session.add(row)
        session.commit()


def _validate_profile_value(key: str, value) -> object:
    """
    Validate and normalise one structured field.
    Raises ValueError with a human-readable message on bad input — the
    router turns that into a 422 so the UI can show it.
    """
    text = "" if value is None else str(value).strip()

    if key == "age":
        try:
            age = int(float(text))
        except ValueError:
            raise ValueError(f"Age must be a whole number, got '{text}'.")
        if not 3 <= age <= 25:
            raise ValueError(f"Age must be between 3 and 25, got {age}.")
        return age

    if key == "student_name" and not text:
        raise ValueError("Student name cannot be empty.")

    if key == "disability_severity" and text:
        match = next((s for s in SEVERITY_VALUES if s.lower() == text.lower()), None)
        if not match:
            raise ValueError(f"Severity must be one of {', '.join(SEVERITY_VALUES)}.")
        return match

    if len(text) > 120:
        raise ValueError(f"{key.replace('_', ' ').title()} is too long (max 120 characters).")

    return text


def _same(a, b) -> bool:
    """Compare two field values as trimmed strings (so 11 == '11')."""
    return str(a if a is not None else "").strip() == str(b if b is not None else "").strip()


# ─────────────────────────────────────────────────────────────────────────────
# SAVE
# ─────────────────────────────────────────────────────────────────────────────

def save_draft(state: dict, iep_id: str, pdf_path: str = "", owner_id: Optional[int] = None) -> str:
    """Persist everything needed to rebuild the PDF. Called after the pipeline."""
    profile = _clean_for_json(state.get("student_profile", {}))
    drafted = _clean_for_json(state.get("drafted_iep", {}))

    record = {
        "iep_id":            iep_id,
        "owner_id":          owner_id,
        "student_profile":   profile,
        "drafted_iep":       drafted,
        "compliance_report": _clean_for_json(state.get("compliance_report", {})),

        # Review metadata
        "review_status":         "pending",   # pending | edited | approved
        "reviewed_by":           "",
        "review_notes":          "",
        "edited_sections":       [],
        "edited_profile_fields": [],
        "revision":              0,

        # Provenance — the ORIGINAL AI output, never overwritten
        "original_iep":     copy.deepcopy(drafted),
        "original_profile": copy.deepcopy(profile),

        "pdf_path":   pdf_path,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _write(iep_id, record)
    logger.info(f"  💾 Draft saved for review: {iep_id}")
    return iep_id


# ─────────────────────────────────────────────────────────────────────────────
# LOAD
# ─────────────────────────────────────────────────────────────────────────────

def load_draft(iep_id: str) -> Optional[dict]:
    with Session(engine) as session:
        row = session.get(IEPDraft, _safe_id(iep_id))
        if row is None:
            return None
        record = copy.deepcopy(row.record or {})

    # Backfill fields for drafts created before profile editing existed
    record.setdefault("original_profile", copy.deepcopy(record.get("student_profile", {})))
    record.setdefault("edited_profile_fields", [])
    return record


def load_owned_draft(iep_id: str, owner_id: int) -> Optional[dict]:
    """
    Return the draft only if it belongs to owner_id.

    A draft owned by someone else is reported exactly like a missing draft
    (None → 404). Returning "forbidden" instead would confirm that the IEP
    exists, which is itself a leak.
    """
    try:
        record = load_draft(iep_id)
    except ValueError:
        return None
    if record is None or record.get("owner_id") != owner_id:
        return None
    return record


def list_drafts(owner_id: int, limit: int = 50) -> list:
    """Drafts belonging to one educator, newest first."""
    with Session(engine) as session:
        rows = session.exec(
            select(IEPDraft)
            .where(IEPDraft.owner_id == owner_id)
            .order_by(IEPDraft.updated_at.desc())
            .limit(max(1, min(int(limit), 500)))
        ).all()
        records = [(row.iep_id, row.record or {}) for row in rows]

    out = []
    for iep_id, rec in records:
        profile = rec.get("student_profile", {})
        out.append({
            "iep_id":              rec.get("iep_id", iep_id),
            "student_name":        profile.get("student_name", "Unknown"),
            "disability_category": profile.get("disability_category", ""),
            "grade":               str(profile.get("grade", "") or ""),
            "review_status": rec.get("review_status", "pending"),
            "revision":      rec.get("revision", 0),
            "created_at":    rec.get("created_at", ""),
            "updated_at":    rec.get("updated_at", ""),
        })
    return out


def count_created_since(owner_id: int, since: datetime) -> int:
    """How many IEPs this educator generated since `since` (timezone-aware)."""
    with Session(engine) as session:
        return session.exec(
            select(func.count()).select_from(IEPDraft)
            .where(IEPDraft.owner_id == owner_id, IEPDraft.created_at >= since)
        ).one()


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE
# ─────────────────────────────────────────────────────────────────────────────

def apply_edits(
    iep_id: str,
    owner_id: int,
    edited_sections: dict = None,
    profile_edits: dict = None,
    reviewed_by: str = "",
    review_notes: str = "",
    approve: bool = False,
) -> Optional[dict]:
    """
    Merge human edits into the stored draft.

    - edited_sections : {section_key: text} for Sections 2–11
    - profile_edits   : {profile_key: value} for Section 1 structured fields

    Unknown keys are ignored. All profile values are validated first; if any
    is invalid, ValueError is raised and NOTHING is written — a half-applied
    edit would leave the record inconsistent.

    Returns the updated record, or None if the draft doesn't exist or
    belongs to a different educator.
    """
    # Ownership is checked here as well as in the router — defence in depth,
    # so a future endpoint that forgets the check still can't edit others' IEPs.
    record = load_owned_draft(iep_id, owner_id)
    if record is None:
        return None

    # ── Validate profile edits up-front (all-or-nothing) ──
    validated_profile = {}
    for key, value in (profile_edits or {}).items():
        if key not in PROFILE_KEYS:
            logger.warning(f"apply_edits: ignored unknown profile field '{key}'")
            continue
        validated_profile[key] = _validate_profile_value(key, value)

    # ── Apply prose section edits ──
    drafted  = dict(record.get("drafted_iep", {}))
    original = record.get("original_iep", {})
    changed_sections = set(record.get("edited_sections", []))

    for key, value in (edited_sections or {}).items():
        if key not in SECTION_KEYS:
            logger.warning(f"apply_edits: ignored unknown section '{key}'")
            continue
        value = "" if value is None else str(value)
        drafted[key] = value
        if _same(value, original.get(key, "")):
            changed_sections.discard(key)
        else:
            changed_sections.add(key)

    # ── Apply structured profile edits ──
    profile          = dict(record.get("student_profile", {}))
    original_profile = record.get("original_profile", {})
    changed_profile  = set(record.get("edited_profile_fields", []))

    for key, value in validated_profile.items():
        profile[key] = value
        if _same(value, original_profile.get(key, "")):
            changed_profile.discard(key)
        else:
            changed_profile.add(key)

    record["drafted_iep"]           = drafted
    record["student_profile"]       = profile
    record["edited_sections"]       = sorted(changed_sections)
    record["edited_profile_fields"] = sorted(changed_profile)
    record["revision"]              = record.get("revision", 0) + 1
    record["updated_at"]            = _now()
    if reviewed_by:
        record["reviewed_by"] = reviewed_by
    if review_notes:
        record["review_notes"] = review_notes
    record["review_status"] = "approved" if approve else "edited"

    _write(iep_id, record)
    logger.info(
        f"  ✏️  Draft {iep_id} rev {record['revision']} — "
        f"{len(changed_sections)} section(s), {len(changed_profile)} student field(s) "
        f"human-edited, status={record['review_status']}"
    )
    return record


def set_pdf_path(iep_id: str, pdf_path: str) -> None:
    record = load_draft(iep_id)
    if record is None:
        return
    record["pdf_path"]   = pdf_path
    record["updated_at"] = _now()
    _write(iep_id, record)


def to_pdf_state(record: dict) -> dict:
    """Minimal state dict that generate_iep_pdf() expects."""
    return {
        "student_id":        record.get("iep_id", ""),
        "iep_id":            record.get("iep_id", ""),
        "student_profile":   record.get("student_profile", {}),
        "drafted_iep":       record.get("drafted_iep", {}),
        "compliance_report": record.get("compliance_report", {}),
    }
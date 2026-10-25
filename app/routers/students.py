"""
app/routers/students.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The student register. Educators only; each sees only their own students.

  GET    /students                 — your students (add ?include_archived=true)
  POST   /students                 — register a student → gets a unique code
  GET    /students/{code}          — one student
  PATCH  /students/{code}          — update details, or archive/restore
  DELETE /students/{code}          — remove a student who has no IEPs
  GET    /students/{code}/ieps     — that student's IEPs

To generate an IEP for a registered student, send their code as
"student_code" to POST /iep/generate (the website does this for you).

ARCHIVE, DON'T DELETE
A student with IEPs can't be deleted — that would orphan their records.
Archive them instead: they disappear from the list but keep their history.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session

from agents.model_config import current_date
from app.db import Student, User, get_session
from app.services import draft_store
from app.services import students as register
from app.services.auth import require_educator
from models.student import DisabilityCategory, DisabilitySeverity

router = APIRouter(prefix="/students", tags=["Students"])


# ── Schemas ─────────────────────────────────────────────────────────────

def _check_dob(dob: date) -> date:
    today = current_date()
    if dob > today:
        raise ValueError("Date of birth can't be in the future.")
    age = register.age_on(dob, today)
    if not register.AGE_MIN <= age <= register.AGE_MAX:
        raise ValueError(
            f"Student must be {register.AGE_MIN}–{register.AGE_MAX} years old "
            f"(this date of birth gives {age})."
        )
    return dob


class _Fields(BaseModel):
    """Validation shared by create and update."""

    @field_validator("full_name", "grade", "school_name", "dominant_language",
                     "guardian_name", "guardian_contact", "notes",
                     "academic_history", "teacher_observations", "parent_concerns",
                     mode="before", check_fields=False)
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("date_of_birth", check_fields=False)
    @classmethod
    def _dob(cls, v):
        return _check_dob(v) if v is not None else v


class StudentCreate(_Fields):
    full_name:            str                 = Field(..., min_length=2, max_length=100)
    date_of_birth:        date
    grade:                str                 = Field(..., min_length=1, max_length=20)
    school_name:          str                 = Field(..., min_length=1, max_length=200)
    disability_category:  DisabilityCategory
    disability_severity:  DisabilitySeverity  = DisabilitySeverity.MODERATE
    dominant_language:    str                 = Field("", max_length=40)
    guardian_name:        str                 = Field("", max_length=100)
    guardian_contact:     str                 = Field("", max_length=100)
    notes:                str                 = Field("", max_length=4000)
    academic_history:     str                 = Field("", max_length=4000)
    teacher_observations: str                 = Field("", max_length=4000)
    parent_concerns:      str                 = Field("", max_length=4000)


class StudentUpdate(_Fields):
    """Send only the fields you want to change."""
    full_name:            Optional[str]                = Field(None, min_length=2, max_length=100)
    date_of_birth:        Optional[date]               = None
    grade:                Optional[str]                = Field(None, min_length=1, max_length=20)
    school_name:          Optional[str]                = Field(None, min_length=1, max_length=200)
    disability_category:  Optional[DisabilityCategory] = None
    disability_severity:  Optional[DisabilitySeverity] = None
    dominant_language:    Optional[str]                = Field(None, max_length=40)
    guardian_name:        Optional[str]                = Field(None, max_length=100)
    guardian_contact:     Optional[str]                = Field(None, max_length=100)
    notes:                Optional[str]                = Field(None, max_length=4000)
    academic_history:     Optional[str]                = Field(None, max_length=4000)
    teacher_observations: Optional[str]                = Field(None, max_length=4000)
    parent_concerns:      Optional[str]                = Field(None, max_length=4000)
    is_archived:          Optional[bool]               = None


class LatestIEP(BaseModel):
    iep_id:        str
    review_status: str
    updated_at:    str


class StudentOut(BaseModel):
    student_code:         str
    full_name:            str
    date_of_birth:        date
    age:                  int
    grade:                str
    school_name:          str
    disability_category:  str
    disability_severity:  str
    dominant_language:    str
    guardian_name:        str
    guardian_contact:     str
    notes:                str
    academic_history:     str
    teacher_observations: str
    parent_concerns:      str
    is_archived:          bool
    created_at:           datetime
    updated_at:           datetime
    iep_count:            int = 0
    latest_iep:           Optional[LatestIEP] = None


# ── Helpers ─────────────────────────────────────────────────────────────

def _plain(fields: dict) -> dict:
    """Enums → their stored string values."""
    return {k: (v.value if hasattr(v, "value") else v) for k, v in fields.items()}


def _ieps_by_student(owner_id: int) -> dict:
    """{student_code: [draft summaries, newest first]} for one educator."""
    out = {}
    for d in draft_store.list_drafts(owner_id=owner_id, limit=500):
        if d.get("student_code"):
            out.setdefault(d["student_code"], []).append(d)
    return out


def _out(student: Student, ieps: list) -> StudentOut:
    latest = ieps[0] if ieps else None
    return StudentOut(
        **student.model_dump(exclude={"id", "owner_id"}),
        age=register.age_on(student.date_of_birth, current_date()),
        iep_count=len(ieps),
        latest_iep=LatestIEP(
            iep_id=latest["iep_id"], review_status=latest["review_status"],
            updated_at=str(latest.get("updated_at", "")),
        ) if latest else None,
    )


def _owned_or_404(session: Session, code: str, user: User) -> Student:
    student = register.get_owned(session, code, user.id)
    if student is None:
        raise HTTPException(status_code=404, detail=f"No student found with ID {code}.")
    return student


# ── Endpoints ───────────────────────────────────────────────────────────

@router.get("", response_model=List[StudentOut], summary="Your students")
def list_students(include_archived: bool = False,
                  user: User = Depends(require_educator),
                  session: Session = Depends(get_session)):
    ieps = _ieps_by_student(user.id)
    return [_out(s, ieps.get(s.student_code, []))
            for s in register.list_owned(session, user.id, include_archived)]


@router.post("", response_model=StudentOut, status_code=201,
             summary="Register a student (they get a unique ID)")
def create_student(payload: StudentCreate,
                   user: User = Depends(require_educator),
                   session: Session = Depends(get_session)):
    student = register.create(session, user.id, _plain(payload.model_dump()))
    return _out(student, [])


@router.get("/{code}", response_model=StudentOut, summary="One student")
def get_student(code: str, user: User = Depends(require_educator),
                session: Session = Depends(get_session)):
    student = _owned_or_404(session, code, user)
    return _out(student, _ieps_by_student(user.id).get(student.student_code, []))


@router.patch("/{code}", response_model=StudentOut, summary="Update or archive a student")
def update_student(code: str, payload: StudentUpdate,
                   user: User = Depends(require_educator),
                   session: Session = Depends(get_session)):
    student = _owned_or_404(session, code, user)
    changes = _plain(payload.model_dump(exclude_unset=True))
    # A required field can't be cleared by sending null
    for key in ("full_name", "date_of_birth", "grade", "school_name",
                "disability_category", "disability_severity", "is_archived"):
        if key in changes and changes[key] is None:
            raise HTTPException(status_code=422, detail=f"{key.replace('_', ' ')} can't be empty.")
    changes = {k: ("" if v is None else v) for k, v in changes.items()}
    student = register.update(session, student, changes)
    return _out(student, _ieps_by_student(user.id).get(student.student_code, []))


@router.delete("/{code}", status_code=204, summary="Delete a student who has no IEPs")
def delete_student(code: str, user: User = Depends(require_educator),
                   session: Session = Depends(get_session)):
    student = _owned_or_404(session, code, user)
    if _ieps_by_student(user.id).get(student.student_code):
        raise HTTPException(
            status_code=409,
            detail="This student has IEPs, so they can't be deleted. Archive them instead.",
        )
    register.delete(session, student)
    return Response(status_code=204)


@router.get("/{code}/ieps", summary="A student's IEPs, newest first")
def student_ieps(code: str, user: User = Depends(require_educator),
                 session: Session = Depends(get_session)):
    student = _owned_or_404(session, code, user)
    return {"student_code": student.student_code,
            "ieps": _ieps_by_student(user.id).get(student.student_code, [])}

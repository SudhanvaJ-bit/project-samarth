"""
app/services/students.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The student register: each educator's list of students.

UNIQUE STUDENT CODES
Every student gets a code like STU-7K3M9Q:
  - random, not sequential — STU-000124 would tell anyone that STU-000123
    exists, and invite guessing;
  - from an alphabet without look-alike characters (no 0/O, 1/I/L), so it
    can be read aloud or copied from paper without mistakes;
  - 6 characters from 31 → about 887 million combinations. Uniqueness is
    still guaranteed by the database (a UNIQUE column); on the rare clash a
    new code is drawn.

OWNERSHIP
A student belongs to the educator who registered them. Another account
asking for that student gets "not found", exactly as for a code that does
not exist (the same rule as IEPs).

IEPs AND STUDENTS
An IEP generated for a registered student stores the student's code in its
record, so the student's page can list all their IEPs. The IEP keeps its
own snapshot of the details used, so later edits to the student never
rewrite an IEP that was already generated.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging
import secrets
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db import Student

logger = logging.getLogger(__name__)

CODE_PREFIX   = "STU-"
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"     # no 0 O 1 I L
CODE_LENGTH   = 6

AGE_MIN, AGE_MAX = 3, 25      # same limits as the IEP form


def new_code() -> str:
    return CODE_PREFIX + "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalise_code(code: str) -> str:
    """Accept 'stu-7k3m9q' or ' STU-7K3M9Q ' — codes are case-insensitive."""
    return (code or "").strip().upper()


def age_on(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Queries ─────────────────────────────────────────────────────────────

def get_owned(session: Session, code: str, owner_id: int) -> Optional[Student]:
    """The student with this code if it belongs to owner_id, else None."""
    student = session.exec(
        select(Student).where(Student.student_code == normalise_code(code))
    ).first()
    if student is None or student.owner_id != owner_id:
        return None
    return student


def list_owned(session: Session, owner_id: int, include_archived: bool = False) -> list:
    query = select(Student).where(Student.owner_id == owner_id)
    if not include_archived:
        query = query.where(Student.is_archived == False)   # noqa: E712 (SQL, not Python)
    return list(session.exec(query.order_by(Student.full_name)).all())


# ── Changes ─────────────────────────────────────────────────────────────

def create(session: Session, owner_id: int, fields: dict) -> Student:
    """Register a student with a fresh unique code."""
    for _ in range(10):
        student = Student(student_code=new_code(), owner_id=owner_id, **fields)
        session.add(student)
        try:
            session.commit()
        except IntegrityError:          # code already taken — draw another
            session.rollback()
            continue
        session.refresh(student)
        logger.info(f"🧒 Registered student {student.student_code} for user {owner_id}")
        return student
    raise RuntimeError("Could not generate a unique student code. Try again.")


def update(session: Session, student: Student, fields: dict) -> Student:
    for key, value in fields.items():
        setattr(student, key, value)
    student.updated_at = _utcnow()
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


def delete(session: Session, student: Student) -> None:
    session.delete(student)
    session.commit()

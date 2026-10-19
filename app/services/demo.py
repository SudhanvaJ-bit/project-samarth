"""
app/services/demo.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The public online demo (SAMARTH_LLM_MODE=demo).

WHAT THE DEMO IS
A showcase that replays the full pipeline for a few SYNTHETIC sample
students, recorded once with scripts/record_demo.py. It needs no Gemini key
and costs nothing to run.

WHAT IT DELIBERATELY DOES NOT DO
- Accept arbitrary students: there is nothing recorded for them, and the
  server holds no API key to call Gemini.
- Accept PDF uploads: a visitor could upload a real child's report.
- Let anyone change the shared demo password and lock others out.

THE DEMO ACCOUNT
One shared educator account, created on every startup. Its credentials are
shown on the login page on purpose — every record it can see is synthetic.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import logging
import os

from sqlmodel import Session

from agents.model_config import DEMO_DIR, DEMO_MODE, _read_demo_manifest
from app.db import engine
from app.services.auth import create_user, get_user_by_email, hash_password

logger = logging.getLogger(__name__)

DEMO_EMAIL    = os.getenv("DEMO_EMAIL", "demo@samarth.app").strip().lower()
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "samarth-demo")
DEMO_NAME     = "Demo Educator"

# The fields a sample must match exactly for its recordings to replay
STUDENT_FIELDS = (
    "student_name", "age", "grade", "school_name", "disability_category",
    "disability_severity", "raw_notes", "academic_history",
    "teacher_observations", "parent_concerns",
)


def _normalise(student: dict) -> dict:
    out = {}
    for key in STUDENT_FIELDS:
        value = student.get(key)
        out[key] = "" if value is None else str(value).strip()
    return out


def load_samples() -> list:
    """Samples that were recorded AND verified to replay (see manifest.json)."""
    try:
        data = json.loads((DEMO_DIR / "samples.json").read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Demo samples unreadable: {e}")
        return []
    verified = set(_read_demo_manifest().get("verified", []))
    return [s for s in data.get("samples", []) if s.get("id") in verified]


def matching_sample(student_data: dict):
    """The sample this input is identical to, or None."""
    wanted = _normalise(student_data)
    for sample in load_samples():
        if _normalise(sample["student"]) == wanted:
            return sample
    return None


def public_info() -> dict:
    """What the frontend needs to show the demo. Public endpoint."""
    if not DEMO_MODE:
        return {"enabled": False}
    return {
        "enabled":     True,
        "recorded_on": _read_demo_manifest().get("recorded_on", ""),
        "login":       {"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        "samples":     [
            {"id": s["id"], "label": s["label"], "student": s["student"]}
            for s in load_samples()
        ],
    }


def ensure_demo_account() -> None:
    """Create the shared demo educator, or restore it if changed."""
    with Session(engine) as session:
        user = get_user_by_email(session, DEMO_EMAIL)
        if user is None:
            create_user(session, DEMO_EMAIL, DEMO_NAME, DEMO_PASSWORD, "educator")
            logger.info(f"Demo account ready: {DEMO_EMAIL}")
            return
        user.password_hash = hash_password(DEMO_PASSWORD)
        user.is_active     = True
        user.role          = "educator"
        session.add(user)
        session.commit()
        logger.info(f"Demo account restored: {DEMO_EMAIL}")

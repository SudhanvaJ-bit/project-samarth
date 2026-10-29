"""
app/routers/settings.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  GET /settings/preferences   — your saved defaults
  PUT /settings/preferences   — save them
  GET /settings/system        — how this server is set up (read-only)

PREFERENCES
Defaults that pre-fill the Generate IEP and Add Student forms, saved per
educator in the database so they follow you to any browser.

WHY THE AI SETTINGS ARE READ-ONLY
Models, mode and limits are chosen by whoever runs the server (environment
variables), because they affect cost and every user. The page shows them so
a teacher knows what is producing their drafts — it doesn't pretend they
can be switched from the browser.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session

from agents import model_config
from app.db import User, UserPreferences, get_session
from app.services import draft_store
from app.services.auth import get_current_user, require_educator
from models.student import DisabilitySeverity
from rag.retriever import get_retriever_stats

router = APIRouter(prefix="/settings", tags=["Settings"])


class Preferences(BaseModel):
    default_school_name: str = Field("", max_length=200)
    default_grade:       str = Field("", max_length=20)
    default_severity:    DisabilitySeverity = DisabilitySeverity.MODERATE
    default_language:    str = Field("", max_length=40)

    @field_validator("default_school_name", "default_grade", "default_language", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


def _load(session: Session, user: User) -> Preferences:
    row = session.get(UserPreferences, user.id)
    try:
        return Preferences(**(row.prefs if row else {}))
    except Exception:
        return Preferences()            # stored values from an older version


@router.get("/preferences", response_model=Preferences, summary="Your saved defaults")
def get_preferences(user: User = Depends(require_educator),
                    session: Session = Depends(get_session)):
    return _load(session, user)


@router.put("/preferences", response_model=Preferences, summary="Save your defaults")
def save_preferences(payload: Preferences,
                     user: User = Depends(require_educator),
                     session: Session = Depends(get_session)):
    if model_config.DEMO_MODE:
        raise HTTPException(status_code=403, detail="Settings can't be changed in the online demo.")
    row = session.get(UserPreferences, user.id) or UserPreferences(user_id=user.id)
    row.prefs      = payload.model_dump(mode="json")
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    return payload


@router.get("/system", summary="How this server is set up (read-only)")
def system_info(user: User = Depends(get_current_user)):
    from app.routers import iep as iep_router      # DAILY_LIMIT lives there

    used = None
    if user.role == "educator":
        used = draft_store.count_created_since(
            user.id, datetime.now(timezone.utc) - timedelta(hours=24))
    try:
        rag = get_retriever_stats()
    except Exception:
        rag = {}

    return {
        "llm_mode":        model_config.LLM_MODE,
        "demo_mode":       model_config.DEMO_MODE,
        "models":          {role: chain[0] for role, chain in model_config.MODEL_CHAINS.items()},
        "fallback_models": {role: chain[1:] for role, chain in model_config.MODEL_CHAINS.items()},
        "fallback_rounds": getattr(model_config, "FALLBACK_ROUNDS", 1),
        "daily_limit":     iep_router.DAILY_LIMIT or None,
        "used_last_24h":   used,
        "legal_corpus": {
            "documents": ["RPwD Act 2016", "NCTE / NCERT guidelines"],
            "chunks":    rag.get("total_chunks"),
            "ready":     rag.get("ready", False),
        },
        "saves_recordings": getattr(model_config, "SAVE_RECORDINGS", True),
    }

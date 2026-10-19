"""
app/db.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Database setup and the User table.

WHY SQLModel + SQLite
SQLite is a single file (samarth.db) with no server to run — right for
development and a demo. SQLModel sits on top of SQLAlchemy, so moving to
PostgreSQL later means changing ONE setting:

    DATABASE_URL=postgresql://user:pass@host:5432/samarth

No model or query code changes.

WHAT IS STORED
  users       — accounts
  iep_drafts  — every generated IEP and its review history, one row each.
                The draft itself is a JSON document (see draft_store.py);
                owner_id and the timestamps are real columns so they can be
                filtered and sorted.

Drafts used to be files in ./drafts/. Files vanish when a cloud server
restarts, a database does not. Old file drafts can be imported with
scripts/import_file_drafts.py.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
from datetime import datetime, timezone
from typing import Iterator, Optional

from dotenv import load_dotenv
from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel, create_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./samarth.db").strip()
# Some hosts hand out "postgres://", which SQLAlchemy no longer accepts
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

# SQLite needs this flag because FastAPI may use the connection from a
# different thread than the one that opened it. PostgreSQL does not.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)

ROLES = ("educator", "admin")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    """
    An account.

    role:
      educator — creates, reviews and downloads their OWN IEPs
      admin    — manages accounts; deliberately cannot read IEPs
                 (least privilege: account management does not require
                 access to children's diagnoses)

    password_hash never holds the password — only a one-way scrypt hash.
    """
    __tablename__ = "users"

    id:            Optional[int] = Field(default=None, primary_key=True)
    email:         str           = Field(index=True, unique=True, max_length=254)
    full_name:     str           = Field(max_length=120)
    password_hash: str
    role:          str           = Field(default="educator", max_length=20)
    is_active:     bool          = Field(default=True)
    created_at:    datetime      = Field(default_factory=_utcnow)


class IEPDraft(SQLModel, table=True):
    """
    One IEP. `record` holds the full draft document — student profile,
    drafted sections, the original AI text, review history — exactly as
    draft_store.py builds it. Only the educator in owner_id can see it.
    Timestamps are timezone-aware UTC.
    """
    __tablename__ = "iep_drafts"

    iep_id:     str            = Field(primary_key=True, max_length=64)
    owner_id:   Optional[int]  = Field(default=None, foreign_key="users.id", index=True)
    record:     dict           = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime       = Field(index=True)
    updated_at: datetime       = Field(index=True)


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency — one session per request, closed afterwards."""
    with Session(engine) as session:
        yield session
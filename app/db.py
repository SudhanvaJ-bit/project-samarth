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
Only account data. IEP drafts still live in ./drafts/ as JSON for now;
each draft records its owner's user id.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
from datetime import datetime, timezone
from typing import Iterator, Optional

from dotenv import load_dotenv
from sqlmodel import Field, Session, SQLModel, create_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./samarth.db")

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


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency — one session per request, closed afterwards."""
    with Session(engine) as session:
        yield session
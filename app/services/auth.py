"""
app/services/auth.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Authentication core: password hashing, tokens, and the dependencies that
protect endpoints.

HOW IT WORKS
1. Login   — email + password are checked; the server returns a signed
             token (a JWT) that expires after a few hours.
2. Request — the frontend sends "Authorization: Bearer <token>" with every
             call. The server checks the signature, then loads the user.
3. Logout  — the frontend discards the token.

PASSWORDS
Stored only as a one-way scrypt hash from Python's standard library
(hashlib.scrypt). No third-party hashing package — one fewer dependency
that can break on upgrade. A random 16-byte salt per password means two
users with the same password get different hashes.

WHY THE USER IS RELOADED ON EVERY REQUEST
The token names a user, but the database is the source of truth. Reloading
means a deactivated account or a changed role takes effect immediately,
rather than lasting until the token expires.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from app.db import ROLES, User, get_session

load_dotenv()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Password hashing (scrypt, standard library)
# ─────────────────────────────────────────────────────────────────────────────

_SCRYPT_N     = 2 ** 14   # CPU/memory cost
_SCRYPT_R     = 8
_SCRYPT_P     = 1
_SCRYPT_DKLEN = 32

PASSWORD_MIN = 8
PASSWORD_MAX = 128


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def hash_password(password: str) -> str:
    """
    Return a self-describing hash string:
        scrypt$<n>$<r>$<p>$<salt>$<hash>
    Storing the parameters alongside the hash means they can be raised in
    future without breaking passwords hashed with the old settings.
    """
    salt   = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison; returns False for any malformed hash."""
    try:
        algo, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        expected = _b64d(hash_b64)
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=_b64d(salt_b64),
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


# Used when an email doesn't exist, so a failed login takes the same time
# whether or not the account exists. Otherwise response timing would reveal
# which emails are registered.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email) or len(email) > 254:
        raise ValueError("Enter a valid email address.")
    return email


def validate_password(password: str) -> None:
    if not password or len(password) < PASSWORD_MIN:
        raise ValueError(f"Password must be at least {PASSWORD_MIN} characters.")
    if len(password) > PASSWORD_MAX:
        raise ValueError(f"Password must be at most {PASSWORD_MAX} characters.")


# ─────────────────────────────────────────────────────────────────────────────
# Tokens (JWT)
# ─────────────────────────────────────────────────────────────────────────────

_ALGORITHM      = "HS256"
EXPIRE_MINUTES  = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))   # 8 hours

_SECRET = os.getenv("JWT_SECRET", "")
if len(_SECRET) < 32:
    logger.warning(
        "JWT_SECRET is missing or shorter than 32 characters. Using a random "
        "secret for this run only — every restart will log all users out. "
        "Set JWT_SECRET in .env to fix this."
    )
    _SECRET = secrets.token_urlsafe(48)


def create_access_token(user: User) -> Tuple[str, datetime]:
    now     = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=EXPIRE_MINUTES)
    payload = {
        "sub":  str(user.id),      # PyJWT requires "sub" to be a string
        "role": user.role,         # informational — the DB is authoritative
        "type": "access",
        "iat":  now,
        "exp":  expires,
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM), expires


def _decode_token(token: str) -> dict:
    return jwt.decode(
        token, _SECRET, algorithms=[_ALGORITHM],
        options={"require": ["exp", "sub"]},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Account operations
# ─────────────────────────────────────────────────────────────────────────────

def get_user_by_email(session: Session, email: str) -> Optional[User]:
    return session.exec(select(User).where(User.email == email)).first()


def authenticate(session: Session, email: str, password: str) -> Optional[User]:
    """Return the user if the credentials are valid and the account is active."""
    try:
        email = normalise_email(email)
    except ValueError:
        verify_password(password or "", _DUMMY_HASH)
        return None

    user = get_user_by_email(session, email)
    if user is None:
        verify_password(password or "", _DUMMY_HASH)   # equalise timing
        return None
    if not verify_password(password or "", user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


def create_user(session: Session, email: str, full_name: str,
                password: str, role: str = "educator") -> User:
    """Validate and create an account. Raises ValueError with a readable message."""
    email     = normalise_email(email)
    full_name = (full_name or "").strip()
    if not full_name:
        raise ValueError("Full name is required.")
    if len(full_name) > 120:
        raise ValueError("Full name is too long (max 120 characters).")
    if role not in ROLES:
        raise ValueError(f"Role must be one of: {', '.join(ROLES)}.")
    validate_password(password)
    if get_user_by_email(session, email):
        raise ValueError("An account with this email already exists.")

    user = User(email=email, full_name=full_name,
                password_hash=hash_password(password), role=role)
    session.add(user)
    session.commit()
    session.refresh(user)
    logger.info(f"👤 Created {role} account: {email}")
    return user


def ensure_admin_from_env(session: Session) -> None:
    """
    Create the first administrator from ADMIN_EMAIL / ADMIN_PASSWORD when
    that account doesn't exist yet. Needed on hosts with no command line
    (Render's free plan); locally `python -m app.cli` does the same job.

    Runs on every startup but only ever CREATES: an existing account's
    password is never overwritten, so changing it later sticks. Once the
    admin exists, these two settings can be removed.
    """
    email    = os.getenv("ADMIN_EMAIL", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not email or not password:
        return
    try:
        if get_user_by_email(session, normalise_email(email)):
            return
        create_user(session, email, os.getenv("ADMIN_NAME", "Administrator"), password, "admin")
        logger.info(f"Created administrator {email} from ADMIN_EMAIL")
    except ValueError as e:
        logger.error(f"ADMIN_EMAIL/ADMIN_PASSWORD not used: {e}")


def set_password(session: Session, user: User, new_password: str) -> None:
    validate_password(new_password)
    user.password_hash = hash_password(new_password)
    session.add(user)
    session.commit()


def public_user(user: User) -> dict:
    """The fields safe to send to a client — never the password hash."""
    return {
        "id":        user.id,
        "email":     user.email,
        "full_name": user.full_name,
        "role":      user.role,
        "is_active": user.is_active,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI dependencies
# ─────────────────────────────────────────────────────────────────────────────

# tokenUrl points Swagger's "Authorize" button at the login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    """Resolve the bearer token to an active user, or fail with 401."""
    unauthorised = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Your session is invalid or has expired. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = _decode_token(token)
    except jwt.PyJWTError:
        raise unauthorised
    if payload.get("type") != "access":
        raise unauthorised

    try:
        user = session.get(User, int(payload["sub"]))
    except (TypeError, ValueError):
        raise unauthorised
    if user is None or not user.is_active:
        raise unauthorised
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


def require_educator(user: User = Depends(get_current_user)) -> User:
    """IEP access is for educators only — admins manage accounts, not records."""
    if user.role != "educator":
        raise HTTPException(
            status_code=403,
            detail="IEP records are available to educator accounts only.",
        )
    return user
"""
app/routers/auth.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  POST  /auth/login          — email + password → access token
  GET   /auth/me             — the logged-in user
  POST  /auth/me/password    — change your own password
  GET   /auth/users          — list accounts            (admin)
  POST  /auth/users          — create an account        (admin)
  PATCH /auth/users/{id}     — activate / deactivate    (admin)

There is no public sign-up. Accounts are created by an administrator,
because these records contain children's disability information.

Swagger: click "Authorize", enter email as username and the password.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlmodel import Session, select

from agents.model_config import DEMO_MODE
from app.db import User, get_session
from app.services.auth import (
    authenticate, create_access_token, create_user, get_current_user,
    public_user, require_admin, set_password, verify_password, EXPIRE_MINUTES,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Schemas ───────────────────────────────────────────

class UserOut(BaseModel):
    id:        int
    email:     str
    full_name: str
    role:      str
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    expires_at:   datetime
    expires_in:   int          # seconds
    user:         UserOut


class UserCreate(BaseModel):
    email:     str
    full_name: str
    password:  str
    role:      str = "educator"


class UserUpdate(BaseModel):
    is_active: bool


class PasswordChange(BaseModel):
    current_password: str
    new_password:     str


# ── Endpoints ─────────────────────────────────────────

@router.post("/login", response_model=TokenOut, summary="Log in and receive an access token")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    # OAuth2 calls the field "username"; we use it for the email address.
    user = authenticate(session, form.username, form.password)
    if user is None:
        # Same message for wrong email, wrong password and inactive account —
        # a specific message would tell an attacker which part was right.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires = create_access_token(user)
    logger.info(f"🔐 Login: {user.email} ({user.role})")
    return TokenOut(
        access_token=token,
        expires_at=expires,
        expires_in=EXPIRE_MINUTES * 60,
        user=UserOut(**public_user(user)),
    )


@router.get("/me", response_model=UserOut, summary="The currently logged-in user")
def me(user: User = Depends(get_current_user)):
    return UserOut(**public_user(user))


@router.post("/me/password", summary="Change your own password")
def change_password(
    payload: PasswordChange,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if DEMO_MODE:
        # One shared account — a visitor must not lock everyone else out
        raise HTTPException(status_code=403,
                            detail="Passwords cannot be changed in the online demo.")
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    try:
        set_password(session, user, payload.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "Password changed."}


@router.get("/users", response_model=List[UserOut], summary="List all accounts (admin)")
def list_users(
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    users = session.exec(select(User).order_by(User.created_at)).all()
    return [UserOut(**public_user(u)) for u in users]


@router.post("/users", response_model=UserOut, status_code=201,
             summary="Create an educator or admin account (admin)")
def admin_create_user(
    payload: UserCreate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    try:
        user = create_user(session, payload.email, payload.full_name,
                           payload.password, payload.role)
    except ValueError as e:
        code = 409 if "already exists" in str(e) else 400
        raise HTTPException(status_code=code, detail=str(e))
    logger.info(f"   created by admin {admin.email}")
    return UserOut(**public_user(user))


@router.patch("/users/{user_id}", response_model=UserOut,
              summary="Activate or deactivate an account (admin)")
def admin_update_user(
    user_id: int,
    payload: UserUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.id == admin.id and not payload.is_active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")
    user.is_active = payload.is_active
    session.add(user)
    session.commit()
    session.refresh(user)
    logger.info(f"👤 {admin.email} set {user.email} active={user.is_active}")
    return UserOut(**public_user(user))
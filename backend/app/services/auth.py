from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    hash_password,
    needs_rehash,
    new_session_token,
    sha256_hex,
    verify_password,
)
from app.models import User, UserSession


def register(db: Session, email: str, password: str) -> User:
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "email_taken", "An account with this email already exists.") from None
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    # verify_password runs a full hash even for unknown emails (timing equalization).
    if not verify_password(user.password_hash if user else None, password) or user is None:
        raise AppError(401, "invalid_credentials", "Email or password is incorrect.")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    return user


def start_session(db: Session, user: User) -> str:
    """Create a session and return the plaintext token for the cookie."""
    token = new_session_token()
    now = datetime.now(UTC)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=sha256_hex(token),
            expires_at=now + timedelta(hours=get_settings().session_ttl_hours),
        )
    )
    # Opportunistic cleanup of this user's expired sessions.
    db.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= now)
    )
    return token


def end_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == sha256_hex(token)))

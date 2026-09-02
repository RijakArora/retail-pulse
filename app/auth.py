"""Minimal session-cookie auth. One retailer = one account. Passwords
hashed with bcrypt directly (not via passlib - passlib 1.7.4 is
incompatible with modern bcrypt releases, a known unresolved upstream
issue: https://github.com/pyca/bcrypt/issues/684). Sessions are signed
cookies via Starlette's SessionMiddleware - no separate session store
needed at this scale."""
import bcrypt
from fastapi import Request
from sqlalchemy.orm import Session

from app.models import User

# bcrypt has a hard 72-byte input limit - truncate defensively rather
# than let a long password throw at signup time.
_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    truncated = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    truncated = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    try:
        return bcrypt.checkpw(truncated, password_hash.encode("utf-8"))
    except ValueError:
        return False


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    return db.query(User).filter(User.id == user_id).first() if user_id else None

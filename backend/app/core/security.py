"""Password hashing and opaque secrets (session tokens, API keys).

Only hashes of session tokens and API keys are stored. Both are high-entropy
random values, so a fast hash (SHA-256) is appropriate; passwords use Argon2id.
"""

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()  # Argon2id with library defaults
# Verified when the email is unknown, so login timing does not reveal registered emails.
_DUMMY_HASH = _hasher.hash("timing-equalizer-not-a-real-password")

API_KEY_PREFIX = "tb_"
API_KEY_DISPLAY_CHARS = 9  # "tb_" + 6 hex chars, safe to show in the UI


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def new_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_hex(24)


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())

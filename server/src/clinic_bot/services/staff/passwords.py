"""Password hashing (stdlib scrypt) and session tokens for the staff portal (SPEC 17.1).

Stored form: ``scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>``. Hashing runs in a worker thread.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
from functools import cache

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
KEY_BYTES = 32
SALT_BYTES = 16
MAX_MEM = 64 * 1024 * 1024
TOKEN_BYTES = 32


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=MAX_MEM, dklen=KEY_BYTES
    )


def hash_password_sync(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    key = _derive(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    b64 = base64.b64encode
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt).decode()}${b64(key).decode()}"


def verify_password_sync(password: str, stored: str) -> bool:
    """False for a wrong password or a malformed stored hash. Constant-time compare."""
    try:
        scheme, n, r, p, salt, key = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(key)
        actual = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


@cache
def dummy_hash() -> str:
    """Checked when the email is unknown, so both failures take the same time."""
    return hash_password_sync(secrets.token_urlsafe(16))


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(hash_password_sync, password)


async def verify_password(password: str, stored: str | None) -> bool:
    return await asyncio.to_thread(verify_password_sync, password, stored or dummy_hash())


def token_digest(token: str) -> str:
    """Only this digest is stored; the token itself is shown to the client once."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    return token, token_digest(token)

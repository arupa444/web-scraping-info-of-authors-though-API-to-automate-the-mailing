"""Argon2id password hashing for user credentials (spec §6.7).

Low-entropy user passwords are hashed with Argon2id (memory-hard, per-user
salt). API keys and session tokens are high-entropy and hashed elsewhere with
SHA-256 — do not use this module for those.
"""

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

# Single shared hasher; argon2-cffi defaults are sensible and tunable later.
_hasher = PasswordHasher()


def hash_password(pw: str) -> str:
    """Hash a plaintext password and return an Argon2id encoded string.

    The returned string embeds the algorithm parameters and a fresh random
    salt, so two calls with the same password yield different hashes.
    """
    return _hasher.hash(pw)


def verify_password(hash: str, pw: str) -> bool:
    """Verify a plaintext password against an Argon2id hash.

    Returns True on a match, False on any mismatch or malformed hash. Never
    raises, so callers can run it unconditionally to avoid timing enumeration.
    """
    try:
        return _hasher.verify(hash, pw)
    except (Argon2Error, ValueError, TypeError):
        return False

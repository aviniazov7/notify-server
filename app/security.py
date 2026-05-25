import secrets

import bcrypt


def hash_password(password: str) -> str:
    """Hash a plaintext password with a per-password random salt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time comparison of a plaintext password against its hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


def generate_token() -> str:
    """Opaque, URL-safe session token (256 bits of entropy)."""
    return secrets.token_urlsafe(32)

"""Encryption at rest and HMAC signing shared by inbound and outbound calls."""

import hashlib
import hmac
import time

from cryptography.fernet import Fernet

_fernet: Fernet | None = None


def configure_encryption(key: str) -> None:
    global _fernet
    _fernet = Fernet(key.encode())


def _cipher() -> Fernet:
    if _fernet is None:
        raise RuntimeError("Encryption is not configured; call configure_encryption() at startup")
    return _fernet


def encrypt_bytes(data: bytes) -> bytes:
    return _cipher().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return _cipher().decrypt(token)


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """Hex HMAC-SHA256 over "<timestamp>.<body>"."""
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify_signature(
    secret: str, timestamp: str | None, body: bytes, signature: str | None, max_skew_seconds: int
) -> bool:
    if not timestamp or not signature:
        return False
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - sent_at) > max_skew_seconds:
        return False
    signature = signature.removeprefix("sha256=")
    return hmac.compare_digest(sign(secret, timestamp, body), signature)


def signed_headers(secret: str, body: bytes, prefix: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        f"{prefix}-Timestamp": timestamp,
        f"{prefix}-Signature": f"sha256={sign(secret, timestamp, body)}",
    }

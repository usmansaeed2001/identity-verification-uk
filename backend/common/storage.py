"""Evidence files, encrypted before they touch the disk."""

import uuid
from pathlib import Path

from django.conf import settings

from common.crypto import decrypt, encrypt


def _path(key: str) -> Path:
    root = settings.EVIDENCE_DIR.resolve()
    path = (root / key).resolve()
    if root not in path.parents:
        raise ValueError("Evidence key escapes the evidence directory.")
    return path


def save(prefix: str, data: bytes) -> str:
    key = f"{prefix}/{uuid.uuid4().hex}.bin"
    path = _path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt(data))
    return key


def load(key: str) -> bytes:
    return decrypt(_path(key).read_bytes())


def delete(key: str) -> None:
    _path(key).unlink(missing_ok=True)

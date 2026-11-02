"""Fernet encryption for personal data at rest. The first key encrypts; every key can decrypt."""

from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings


@lru_cache(maxsize=1)
def _fernet(keys: tuple[str, ...]) -> MultiFernet:
    return MultiFernet([Fernet(k.encode()) for k in keys])


def fernet() -> MultiFernet:
    return _fernet(tuple(settings.DATA_ENCRYPTION_KEYS))


def encrypt(data: bytes) -> bytes:
    return fernet().encrypt(data)


def decrypt(token: bytes) -> bytes:
    return fernet().decrypt(token)

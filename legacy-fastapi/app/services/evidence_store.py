"""Evidence file storage. Files are Fernet-encrypted before they leave the process."""

import asyncio
from pathlib import Path
from typing import Protocol

from app.config import Settings
from app.security import decrypt_bytes, encrypt_bytes


class EvidenceStore(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...


class LocalEvidenceStore:
    def __init__(self, root: str):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Invalid evidence key")
        return path

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encrypt_bytes(data))

        await asyncio.to_thread(write)

    async def get(self, key: str) -> bytes:
        return decrypt_bytes(await asyncio.to_thread(self._path(key).read_bytes))

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, True)


class S3EvidenceStore:
    def __init__(self, settings: Settings):
        import boto3

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self.client.put_object, Bucket=self.bucket, Key=key, Body=encrypt_bytes(data))

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        return decrypt_bytes(await asyncio.to_thread(response["Body"].read))

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)


def get_evidence_store(settings: Settings) -> EvidenceStore:
    if settings.evidence_backend == "s3":
        return S3EvidenceStore(settings)
    return LocalEvidenceStore(settings.evidence_dir)

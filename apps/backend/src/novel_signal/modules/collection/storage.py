from __future__ import annotations

import gzip
import hashlib
from dataclasses import dataclass
from typing import Protocol

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from novel_signal.config import Settings, get_settings


@dataclass(frozen=True)
class StoredRawObject:
    sha256: str
    bucket: str
    object_key: str
    byte_length: int
    compressed_byte_length: int


class RawObjectStore(Protocol):
    def put_raw(self, *, platform: str, page_type: str, body: bytes) -> StoredRawObject: ...


class S3RawObjectStore:
    """Immutable, gzip-compressed, SHA-256 addressed raw-response storage."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.bucket = self.settings.object_store_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=self.settings.object_store_endpoint,
            aws_access_key_id=self.settings.object_store_access_key.get_secret_value(),
            aws_secret_access_key=self.settings.object_store_secret_key.get_secret_value(),
            region_name=self.settings.object_store_region,
        )

    def put_raw(self, *, platform: str, page_type: str, body: bytes) -> StoredRawObject:
        digest = hashlib.sha256(body).hexdigest()
        object_key = f"raw/{platform}/{page_type}/{digest[:2]}/{digest}.gz"
        compressed = gzip.compress(body, compresslevel=6, mtime=0)
        self._ensure_bucket()

        try:
            self.client.head_object(Bucket=self.bucket, Key=object_key)
        except ClientError as error:
            status = int(error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
            code = str(error.response.get("Error", {}).get("Code", ""))
            if status not in {404} and code not in {"404", "NoSuchKey", "NotFound"}:
                raise
            self.client.put_object(
                Bucket=self.bucket,
                Key=object_key,
                Body=compressed,
                ContentType="application/gzip",
                Metadata={"sha256": digest, "original-bytes": str(len(body))},
            )

        return StoredRawObject(
            sha256=digest,
            bucket=self.bucket,
            object_key=object_key,
            byte_length=len(body),
            compressed_byte_length=len(compressed),
        )

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as error:
            status = int(error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
            if status not in {400, 403, 404}:
                raise
            self.client.create_bucket(Bucket=self.bucket)

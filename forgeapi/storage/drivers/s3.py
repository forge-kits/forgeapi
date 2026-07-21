from __future__ import annotations

import asyncio
from typing import Any

from .base import StorageDriver


class S3Driver(StorageDriver):
    """Stores files in an S3-compatible bucket (AWS S3, MinIO, Cloudflare R2).

    Requires ``boto3``::

        pip install forge-kits[s3]

    Args:
        bucket:       Bucket name.
        region:       AWS region (default ``"us-east-1"``).
        access_key:   AWS access key ID (falls back to env / IAM role if empty).
        secret_key:   AWS secret access key.
        endpoint_url: Custom endpoint for S3-compatible services
                      (e.g. ``"http://localhost:9000"`` for MinIO).
        base_url:     Public URL prefix for :meth:`url`.
                      Defaults to the standard AWS S3 URL.
        acl:          Canned ACL applied on upload (e.g. ``"public-read"``).
                      ``None`` → no ACL header sent.

    Example::

        Storage.configure(
            driver="s3",
            bucket="my-bucket",
            region="eu-central-1",
            access_key="AKIA...",
            secret_key="...",
        )
    """

    def __init__(
        self,
        bucket: str,
        *,
        region: str = "us-east-1",
        access_key: str = "",
        secret_key: str = "",
        endpoint_url: str | None = None,
        base_url: str | None = None,
        acl: str | None = None,
    ) -> None:
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "S3Driver requires boto3. Install it: pip install forge-kits[s3]"
            )
        self._bucket = bucket
        self._acl = acl
        self._base_url = (
            base_url or f"https://{bucket}.s3.{region}.amazonaws.com"
        ).rstrip("/")
        self._client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            endpoint_url=endpoint_url,
        )

    def _run(self, fn, *args, **kwargs) -> Any:
        return asyncio.to_thread(fn, *args, **kwargs)

    async def put(self, path: str, data: bytes) -> str:
        extra: dict[str, Any] = {}
        if self._acl:
            extra["ACL"] = self._acl

        def _do() -> None:
            self._client.put_object(Bucket=self._bucket, Key=path, Body=data, **extra)

        await asyncio.to_thread(_do)
        return path

    async def get(self, path: str) -> bytes:
        def _do() -> bytes:
            resp = self._client.get_object(Bucket=self._bucket, Key=path)
            return resp["Body"].read()

        return await asyncio.to_thread(_do)

    async def delete(self, path: str) -> bool:
        def _do() -> bool:
            self._client.delete_object(Bucket=self._bucket, Key=path)
            return True

        return await asyncio.to_thread(_do)

    async def exists(self, path: str) -> bool:
        import botocore.exceptions

        def _do() -> bool:
            try:
                self._client.head_object(Bucket=self._bucket, Key=path)
                return True
            except botocore.exceptions.ClientError:
                return False

        return await asyncio.to_thread(_do)

    async def list(self, directory: str = "") -> list[str]:
        prefix = directory.rstrip("/") + "/" if directory else ""

        def _do() -> list[str]:
            result: list[str] = []
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    result.append(obj["Key"])
            return result

        return await asyncio.to_thread(_do)

    def url(self, path: str) -> str:
        return f"{self._base_url}/{path}"

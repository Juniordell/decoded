from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass
class UploadResult:
    key: str
    url: str
    size_bytes: int


class R2Client:
    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        public_url: str | None = None,
    ) -> None:
        import boto3
        from botocore.config import Config

        self._bucket = bucket
        self._public_url = (public_url or "").rstrip("/")

        self._client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            # R2 exige assinatura v4 e ignora região, mas o boto3
            # precisa de uma string qualquer
            config=Config(signature_version="s3v4", region_name="auto"),
        )

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        cache_seconds: int = 31_536_000,
    ) -> UploadResult:
        """
        Sobe um objeto.

        O cache de um ano é seguro porque a chave contém a versão do
        roteiro — regenerar produz uma chave nova, então nada precisa
        ser invalidado.
        """
        loop = asyncio.get_running_loop()

        def _put() -> None:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                CacheControl=f"public, max-age={cache_seconds}, immutable",
            )

        await loop.run_in_executor(None, _put)

        url = f"{self._public_url}/{key}" if self._public_url else key

        logger.info("r2.uploaded", key=key, bytes=len(data), url=url)

        return UploadResult(key=key, url=url, size_bytes=len(data))

    async def delete(self, key: str) -> None:
        loop = asyncio.get_running_loop()

        def _delete() -> None:
            self._client.delete_object(Bucket=self._bucket, Key=key)

        await loop.run_in_executor(None, _delete)
        logger.info("r2.deleted", key=key)

    async def exists(self, key: str) -> bool:
        loop = asyncio.get_running_loop()

        def _head() -> bool:
            try:
                self._client.head_object(Bucket=self._bucket, Key=key)
                return True
            except Exception:
                return False

        return await loop.run_in_executor(None, _head)
"""Private S3 operations used by the attachment service."""

from typing import Protocol
from urllib.parse import quote, urlsplit, urlunsplit

from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.integrations.s3.client import get_s3_client
from app.integrations.s3.object_verification import (
    ObjectInfo,
    ObjectNotReadyError,
    ObjectStorageError,
)


class ObjectStorage(Protocol):
    def create_upload_url(
        self, *, object_key: str, content_type: str, expires_in: int
    ) -> str: ...

    def head_object(self, *, object_key: str) -> ObjectInfo: ...

    def create_download_url(
        self,
        *,
        object_key: str,
        file_name: str,
        content_type: str,
        expires_in: int,
    ) -> str: ...

    def delete_object(self, *, object_key: str) -> None: ...


class S3ObjectStorage:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.s3_bucket_name:
            raise ObjectStorageError("S3_BUCKET_NAME is not configured")
        self.bucket = settings.s3_bucket_name
        self.public_host = None
        if settings.s3_public_base_url:
            public_url = urlsplit(settings.s3_public_base_url)
            if (
                public_url.scheme != "https"
                or not public_url.hostname
                or public_url.username is not None
                or public_url.password is not None
                or public_url.path not in {"", "/"}
                or public_url.query
                or public_url.fragment
            ):
                raise ObjectStorageError("S3_PUBLIC_BASE_URL must be an HTTPS origin")
            self.public_host = public_url.netloc
        try:
            self.client = get_s3_client()
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageError from exc

    def create_upload_url(
        self, *, object_key: str, content_type: str, expires_in: int
    ) -> str:
        try:
            signed_url = self.client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": object_key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
                HttpMethod="PUT",
            )
            return self._browser_url(signed_url)
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageError from exc

    def head_object(self, *, object_key: str) -> ObjectInfo:
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=object_key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
                raise ObjectNotReadyError from exc
            raise ObjectStorageError from exc
        except BotoCoreError as exc:
            raise ObjectStorageError from exc
        return ObjectInfo(
            size_bytes=int(response["ContentLength"]),
            content_type=str(response.get("ContentType", "application/octet-stream")),
        )

    def create_download_url(
        self,
        *,
        object_key: str,
        file_name: str,
        content_type: str,
        expires_in: int,
    ) -> str:
        try:
            signed_url = self.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": object_key,
                    "ResponseContentType": content_type,
                    "ResponseContentDisposition": (
                        "attachment; filename*=UTF-8''" + quote(file_name, safe="")
                    ),
                },
                ExpiresIn=expires_in,
                HttpMethod="GET",
            )
            return self._browser_url(signed_url)
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageError from exc

    def _browser_url(self, signed_url: str) -> str:
        if not self.public_host:
            return signed_url
        # CloudFront forwards the exact path/query and restores the S3 origin Host.
        # It must have caching disabled and must not replace the viewer signature.
        signed = urlsplit(signed_url)
        return urlunsplit(("https", self.public_host, signed.path, signed.query, ""))

    def delete_object(self, *, object_key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=object_key)
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageError from exc

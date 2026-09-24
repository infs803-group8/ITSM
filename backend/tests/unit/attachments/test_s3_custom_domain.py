"""Verify the S3 signature survives the CloudFront URL adapter without networking."""

from urllib.parse import parse_qs, urlsplit

import pytest

from app.core.config import get_settings
from app.integrations.s3.client import get_s3_client
from app.integrations.s3.object_verification import ObjectStorageError
from app.integrations.s3.presigned_urls import S3ObjectStorage


@pytest.fixture(autouse=True)
def s3_settings(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "offline-test-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "offline-test-secret-key")
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    monkeypatch.setenv("S3_BUCKET_NAME", "infs803-group8-dev-attachments-256329410824")
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.ap-southeast-2.amazonaws.com")
    monkeypatch.setenv("S3_PUBLIC_BASE_URL", "https://s3.infs803-group8.com")
    get_settings.cache_clear()
    get_s3_client.cache_clear()
    yield
    get_settings.cache_clear()
    get_s3_client.cache_clear()


def test_presigned_put_uses_custom_domain_and_sigv4():
    storage = S3ObjectStorage()
    result = urlsplit(
        storage.create_upload_url(
            object_key="attachments/pending/42/upload-id",
            content_type="text/plain",
            expires_in=300,
        )
    )
    query = parse_qs(result.query)
    assert result.scheme == "https"
    assert result.netloc == "s3.infs803-group8.com"
    assert result.path == "/attachments/pending/42/upload-id"
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["X-Amz-SignedHeaders"] == ["content-type;host"]
    assert query["X-Amz-Expires"] == ["300"]
    assert "/ap-southeast-2/s3/aws4_request" in query["X-Amz-Credential"][0]


def test_presigned_download_keeps_filename_response_parameters():
    result = urlsplit(
        S3ObjectStorage().create_download_url(
            object_key="attachments/a b+%.txt",
            file_name="network log.txt",
            content_type="text/plain",
            expires_in=60,
        )
    )
    query = parse_qs(result.query)
    assert result.netloc == "s3.infs803-group8.com"
    assert result.path == "/attachments/a%20b%2B%25.txt"
    assert query["response-content-type"] == ["text/plain"]
    assert query["response-content-disposition"] == [
        "attachment; filename*=UTF-8''network%20log.txt"
    ]


def test_adapter_preserves_exact_encoded_path_and_signature_query():
    signed = (
        "https://bucket.s3.ap-southeast-2.amazonaws.com/attachments/a%20b%2B.txt"
        "?X-Amz-Signature=abc&response-content-disposition=a%2Bb%20c"
    )
    rewritten = S3ObjectStorage()._browser_url(signed)
    assert rewritten == signed.replace(
        "https://bucket.s3.ap-southeast-2.amazonaws.com",
        "https://s3.infs803-group8.com",
        1,
    )


def test_omitting_public_domain_preserves_regional_s3_host(monkeypatch):
    monkeypatch.setenv("S3_PUBLIC_BASE_URL", "")
    get_settings.cache_clear()
    storage = S3ObjectStorage()
    result = urlsplit(
        storage.create_upload_url(
            object_key="attachments/test",
            content_type="text/plain",
            expires_in=60,
        )
    )
    assert result.netloc == (
        "infs803-group8-dev-attachments-256329410824.s3.ap-southeast-2.amazonaws.com"
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://s3.infs803-group8.com",
        "https://s3.infs803-group8.com/path",
        "https://user:password@s3.infs803-group8.com",
        "https://s3.infs803-group8.com/?x=1",
    ],
)
def test_invalid_public_origin_is_rejected(monkeypatch, base_url):
    monkeypatch.setenv("S3_PUBLIC_BASE_URL", base_url)
    get_settings.cache_clear()
    with pytest.raises(ObjectStorageError, match="HTTPS origin"):
        S3ObjectStorage()

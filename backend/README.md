# Backend

FastAPI service owned by members A, B, and C. Implement the approved contract in `docs/api/openapi.yaml`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Start MySQL first from the repository root:

```powershell
docker compose -f docker-compose.local.yml up -d mysql
```

The backend runs locally (including PyCharm debugging); it is not started by the local Compose file. API-02 through API-05 additionally require `S3_BUCKET_NAME` and AWS credentials with access to the shared attachment bucket.

## Shared S3 attachment configuration

`.env.example` uses the shared `attachments/` prefix and
`S3_PUBLIC_BASE_URL=https://s3.infs803-group8.com`. Development and production
use the same prefix. Previously stored object keys remain usable.

Provide AWS credentials through the backend process environment, an AWS profile,
or an ECS task role. Pydantic's `.env` loading does not export AWS credentials for
boto3. The frontend receives short-lived presigned URLs and does not need AWS keys.

`S3_PUBLIC_BASE_URL` optionally replaces only the origin of browser-facing
presigned PUT/GET URLs. Keep `S3_ENDPOINT_URL` unset for AWS S3 so the SDK signs
against the actual S3 endpoint. Leave `S3_PUBLIC_BASE_URL` empty to return S3 URLs
directly, including when using a local S3 emulator.

The configured CloudFront distribution forwards requests to the bucket's regional
REST endpoint with `Managed-CachingDisabled` and
`Managed-AllViewerExceptHostHeader`. It must preserve the signed path and query,
restore the S3 origin Host, permit PUT, and must not replace the viewer's S3
signature with OAC signing. The bucket remains private; unsigned reads are denied.
Server-side HEAD and delete calls continue to use S3 directly.

The current shared bucket, CloudFront distribution, ACM certificate and Cloudflare
DNS were configured through their consoles. Reconcile and import these resources
before applying the existing Terraform configurations, which still describe the
earlier development/final separation.

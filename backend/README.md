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
DNS were configured through their consoles. Final Terraform now consumes the
existing bucket. Import the bucket into `dev-storage` before using that stack
to manage its settings; its old expiration rule remains disabled.

## MySQL regression verification

With local MySQL running, set `ITSM_TEST_ADMIN_URL` to your local administrative
MySQL connection URL and run `python scripts/run_mysql_integration.py`.
The runner creates `service_desk_member_a_test` only if absent, initializes the
canonical SQL and executes the full suite, then drops only the schema it created.
It never resets `service_desk`. S3 remains mocked during these tests.

The regression covers all seven Member A APIs and 201 orphan uploads spanning
multiple cleanup pages. Cleanup uses a stable upload-ID cursor, rechecks each
locked session and retries eligible terminal sessions on subsequent runs.
Repeated S3 DELETE calls are intentional: failed deletes and late PUT completions
must remain retryable. No schema change or automatic expiry of completed objects
is required.

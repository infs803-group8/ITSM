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

The backend runs locally (including PyCharm debugging); it is not started by the local Compose file. API-02 through API-05 additionally require `S3_BUCKET_NAME` and local AWS credentials with access to the development S3 bucket.

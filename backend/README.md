# Backend

FastAPI service owned by members A, B, and C. Implement the approved contract in `docs/api/openapi.yaml`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

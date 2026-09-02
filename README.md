# INFS803 Group 8 — IT Service Desk

Monorepo for the INFS803 Cloud Computing assignment. The system uses a FastAPI backend, React frontend, MySQL database, S3 attachments, and a final AWS Fargate architecture.

## Workspaces

- `backend/` — FastAPI, tests, database schema, and scripts.
- `frontend/` — React + TypeScript + Vite.
- `infrastructure/` — Terraform, ECS templates, policies, and deployment scripts.
- `docs/` — baseline, API contract, database design, runbooks, and evidence.
- `.github/` — issue/PR templates and CI/CD.

## Local quick start

1. Copy `backend/.env.example` to `backend/.env`.
2. Copy `frontend/.env.example` to `frontend/.env`.
3. Run `docker compose -f docker-compose.local.yml up -d mysql` to start only the shared MySQL 8.4 schema locally.
4. In `backend/`, create the Python 3.12 virtual environment, install `requirements-dev.txt`, and run `uvicorn app.main:app --reload` from PyCharm or a terminal.
5. In `frontend/`, run `npm install` and `npm run dev`.
6. Open http://localhost:5173 and backend docs at http://localhost:8000/api/docs.

During development the backend and frontend run directly on each member's computer; Docker Compose starts MySQL only. Attachment APIs use the configured private development S3 bucket. Member A's platform, attachment, and dashboard endpoints follow `docs/api/openapi.yaml`.

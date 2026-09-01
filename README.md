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
3. Run `docker compose -f docker-compose.local.yml up --build`.
4. Open http://localhost:5173 and backend docs at http://localhost:8000/api/docs.

The initial scaffold exposes a health endpoint. Business endpoints must follow `docs/api/openapi.yaml`.

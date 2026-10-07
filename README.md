# INFS803 Group 8 — IT Service Desk

Monorepo for the INFS803 Cloud Computing assignment. The system uses a FastAPI backend, React frontend, MySQL database, S3 attachments, and a final AWS Fargate architecture.

## Workspaces

- `backend/` — FastAPI, tests, database schema, and scripts.
- `frontend/` — React + TypeScript + Vite.
- `infrastructure/` — Terraform, ECS templates, policies, and deployment scripts.
- `docs/` — the four supplied English process documents: baseline, API specification, OpenAPI v1.1 and database design.
- `backend/contracts/` — the current 33-operation OpenAPI contract used by code generation and contract tests.
- `.github/` — two manual release workflows, issue/PR templates, and code ownership.

Use **Actions → Frontend / Backend - manual build and deploy → Run workflow** on `main`.
Choose `build-only`, `build-and-deploy`, or `deploy-existing`. Both components share
the existing immutable ECR repository and deploy independently to their ECS services.
There are no push or PR triggers. The release workflow definitions are
[frontend.yml](.github/workflows/frontend.yml) and
[backend.yml](.github/workflows/backend.yml).

## Project documents

- [Development baseline v6.0](docs/IT-Service-Desk-Unified-Project-Baseline-v6.0.md)
- [API specification v1.1](docs/IT-Service-Desk-Final-API-Specification-v1.1.md)
- [Process OpenAPI v1.1](docs/IT-Service-Desk-OpenAPI-v1.1.yaml)
- [Database design v1.1](docs/IT-Service-Desk-Database-Final-Design-v1.1.md)

These process documents preserve the supplied 32-operation baseline. The current
implementation also includes API-33 for vendor request history; use
[backend/contracts/openapi.yaml](backend/contracts/openapi.yaml) for generation
and contract tests, with its JSON counterpart in the same directory.

## Local quick start

1. Copy `backend/.env.example` to `backend/.env`.
2. Copy `frontend/.env.example` to `frontend/.env`.
3. Run `docker compose -f docker-compose.local.yml up -d mysql` to start only the shared MySQL 8.4 schema locally.
4. In `backend/`, create the Python 3.12 virtual environment, install `requirements-dev.txt`, and run `uvicorn app.main:app --reload` from PyCharm or a terminal.
5. In `frontend/`, run `npm install` and `npm run dev`.
6. Open http://localhost:5173 and backend docs at http://localhost:8000/api/docs.

During development the backend and frontend run directly on each member's computer; Docker Compose starts MySQL only. Attachment APIs use the configured private development S3 bucket. Member A's platform, attachment, and dashboard endpoints follow `backend/contracts/openapi.yaml`.

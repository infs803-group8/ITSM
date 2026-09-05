# Member A cleanup and release repair verification

Date: 2026-09-05. Baseline: main `1d12dd6`.
Branch: `bugfix/WBS-A03-cleanup-release-pipeline`.

## Repairs

- Cleanup uses stable upload-ID pagination through all eligible sessions instead
  of repeatedly selecting the same first 200 rows. Failed deletes and late uploads
  remain retryable. Each session is locked and rechecked before deletion; completed
  attachments remain protected. No schema change is needed.
- PowerShell smoke checks read `data.status` and `data.checks.database`.
- Release scripts now build/reuse immutable ECR images, register complete ECS
  revisions, verify service activation and health, preserve scheduled task settings,
  and attempt rollback on release failure. Native process failures propagate.
- Frontend rollback restores the service before invalidating CloudFront and waiting
  for completion. Regression tests cover a later scheduler failure, a frontend
  rollout failure, and cache invalidation failure without blocking backend rollback.
- Terraform defines idle services, job tasks, separate job networking, DB/JWT secret
  injection, scoped IAM/OIDC, and disabled schedules. The final stack reuses the
  existing shared S3 bucket; the old development expiration rule stays disabled.
- Production frontend uses `/api/v1`. Backend images include canonical SQL and the
  MySQL RSA authentication dependency. Both image contexts exclude local env files.
- GitHub backend CI now runs actual MySQL integration; infrastructure CI validates
  deployment behavior, PowerShell and Terraform without cloud credentials.

## Evidence

| Check | Result |
|---|---|
| Local MySQL 8.4.11, canonical SQL bootstrap | 19 tables created successfully |
| Backend regression including API-01 through API-07 | 36 passed, 3 pre-existing database placeholders skipped |
| Real MySQL cleanup with 201 orphan records | All 201 processed in one run; retry run succeeds; 2 completed attachments retained |
| Deployment Python tests with AWS stubs/mocks | 17 passed |
| PowerShell smoke and failure propagation | Passed |
| Backend/infrastructure Ruff | Passed |
| Terraform final/dev-storage validate | Passed |
| Terraform final mock-provider release test | Passed; no real AWS resources created |
| Backend and frontend production image builds | Passed |
| Backend container health against local MySQL | HTTP 200; backend and database healthy |
| Frontend container homepage | HTTP 200 |
| Backend image SQL/RSA dependency check | Passed |

The MySQL runner creates only `service_desk_member_a_test`, refuses to overwrite
an existing schema, and deletes its own test schema afterward. Application data
in `service_desk` is not modified. Temporary application containers are stopped
after checks; the user's MySQL remains running.

## Remaining integration dependencies

This is code verification, not a live AWS deployment. Member B's bootstrap/seed
implementation and Member C's SLA implementation are still their responsibilities.
Both schedules start disabled. Before cloud release, follow the deployment runbook,
add the final frontend origin to the shared bucket CORS, and validate real S3,
OIDC, RDS, ECS, scheduler, frontend workflows and rollback in AWS.

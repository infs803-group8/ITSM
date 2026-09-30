# Infrastructure

- `.github/workflows/frontend.yml` and `backend.yml` are manually dispatched releases.
  They use OIDC, a shared ECR repository, and the existing ECS services.
- `environments/production.json` records the existing deployment's non-secret resource IDs.
- `scripts/release.py` resolves component-prefixed tags to immutable digests, preserves
  active task configuration, verifies rollout/health, and rolls back failed releases.
- `scripts/setup_github_oidc.py` previews the checked-in IAM policies; `--apply` creates
  the OIDC provider and project-scoped release role. See
  [GitHub Actions setup and usage](../docs/deployment/github-actions.md).

- `terraform/dev-storage/` manages the existing shared S3 bucket after import; object expiry is disabled.
- `terraform/final/` defines idle ECS services, full task definitions, private RDS,
  CloudFront/ALB, secrets, IAM and disabled schedules. It reuses the shared S3 bucket.
- `ecs/task-definitions/` points to the single definition source in Terraform.
- `scripts/deploy.py` builds and pushes immutable images, updates ECS services,
  verifies health, updates scheduled task revisions and rolls back failed releases.
- `policies/` contains least-privilege templates.

A commit creates no AWS resource. Review placeholders, run `terraform plan`, and obtain team approval before applying.

Use `docs/deployment/aws-deployment-runbook.md` for configuration, S3 import,
bootstrap, release and verification. Member B's database bootstrap/seed implementation
and Member C's SLA implementation remain required inputs for their respective tasks.
Deployment tests use stubbed AWS clients and Terraform mock providers; live AWS
integration must still be performed during the planned cloud milestone.

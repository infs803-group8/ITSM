# Infrastructure

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

# Infrastructure

- `terraform/dev-storage/` provisions only the shared development S3 bucket.
- `terraform/final/` contains the final AWS Fargate architecture scaffold.
- `ecs/task-definitions/` contains task-definition templates.
- `scripts/` contains controlled deployment and cleanup entry points.
- `policies/` contains least-privilege templates.

A commit creates no AWS resource. Review placeholders, run `terraform plan`, and obtain team approval before applying.

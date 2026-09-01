# AWS deployment runbook

Provision reviewed Terraform, bootstrap RDS once, build immutable frontend and
backend images, push ECR, register separate Fargate task definitions, update each
service independently, run smoke tests, and record commit/image/task revisions.

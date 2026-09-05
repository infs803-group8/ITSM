# ECS task definitions

The executable definitions are maintained once, in
`infrastructure/terraform/final/tasks.tf`. Terraform registers the initial
backend, frontend, attachment cleanup, database bootstrap and SLA task families.
They include environment, Secrets Manager references, IAM roles and CloudWatch logs.

`infrastructure/scripts/deploy.py` reads the registered definitions and creates
new image revisions while preserving those settings. The former incomplete JSON
templates have been removed to avoid two conflicting definitions.

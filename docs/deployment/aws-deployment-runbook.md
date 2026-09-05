# AWS deployment runbook

The release code uses the resources defined in `infrastructure/terraform/final`.
Local and CI tests validate code, MySQL and mocked cloud behavior; they do not
provision AWS or prove live cloud connectivity.

## Prepare the cloud candidate

1. Merge and review the release code. Member B must implement and verify
   `app.db.bootstrap` and seed/schema checks against canonical SQL; its current
   placeholder exits with an error. Member C must implement the SLA monitor before
   enabling its schedule. Deployment does not silently skip failed bootstrap.
2. Copy `terraform.tfvars.example` to an ignored `.tfvars` file. Set the account's
   ECR image URIs and budget email. Terraform can register the initial image tags
   before they exist because both ECS services start with desired count zero.
3. If GitHub OIDC is already registered in the AWS account, set
   `github_oidc_provider_arn` to that provider's ARN; otherwise this stack creates
   the provider. The deployment role trusts only this repository's `final` environment.
4. Run `terraform init`, `terraform validate` and review a saved plan before the
   team's approved apply. Terraform state contains secret values and must stay out
   of Git. Both job schedules remain disabled by default.
5. Export resource IDs using `terraform output -json deployment_config` to a file
   outside the checkout. This contains resource identifiers, not DB/JWT values.
   Application containers receive those values through ECS Secrets Manager injection.

## Existing shared attachments

The final stack reads `infs803-group8-dev-attachments-256329410824` as an existing
bucket and uses `attachments/` plus `https://s3.infs803-group8.com`. It does not
create a second bucket or change the existing attachment distribution/certificate.

The `dev-storage` directory is the optional single owner of bucket settings. Before
its first apply, import the existing bucket and settings into its state:

```powershell
terraform import aws_s3_bucket.development_attachments $BucketName
terraform import aws_s3_bucket_public_access_block.development_attachments $BucketName
terraform import aws_s3_bucket_server_side_encryption_configuration.development_attachments $BucketName
terraform import aws_s3_bucket_cors_configuration.development_attachments $BucketName
terraform import aws_s3_bucket_lifecycle_configuration.development_attachments $BucketName
```

Run these in `infrastructure/terraform/dev-storage` with `$BucketName` set to the
shared bucket and reviewed variables loaded. Preserve existing origins and add
the final frontend's exact `https://...cloudfront.net` origin to
`attachment_cors_allowed_origins`. Review the plan: the old development expiration
rule must remain **Disabled**, and completed attachments must have no expiration.
Do not apply both stacks as owners of the same bucket settings.

## GitHub Actions configuration

In the repository's `final` Environment, set:

- Secret `AWS_GITHUB_ACTIONS_ROLE_ARN`: Terraform's `github_deploy_role_arn` output.
- Variable `AWS_REGION`: `ap-southeast-2`.
- Variable `DEPLOYMENT_CONFIG_JSON`: the exact JSON value exported above.

Set environment reviewers and permitted release branches as agreed by the team.
The workflow uses OIDC and serializes releases with one concurrency group. It is
manual; pushing code or creating a PR never launches a deployment.

## Bootstrap and release

1. On a clean checkout of a full 40-character commit SHA, install
   `backend/requirements-dev.txt`, ensure Docker is available and set
   `DEPLOY_CONFIG_PATH` to the exported JSON file.
2. Once Member B's bootstrap implementation is ready, run the workflow with
   component `bootstrap` against the empty final RDS. This builds/reuses the
   backend image and runs the separate one-off task. The workflow waits for STOPPED
   and fails for missing or nonzero container exit codes. Never rerun bootstrap
   on a populated database unless the reviewed implementation explicitly supports it.
3. Run component `all`, `backend` or `frontend`. Local equivalents are
   `deploy-final.ps1`, `deploy-backend.ps1` and `deploy-frontend.ps1`, passing
   `-CommitSha` and `-ConfigPath`. The Python entry point is also cross-platform.
4. The scripts push commit-tagged images to immutable ECR repositories and deploy
   digest-pinned images. Retrying the same SHA reuses its existing digest. Frontend
   builds use `/api/v1`, so browsers call the public origin instead of localhost.
5. The release waits for ECS stability and verifies the requested revision really
   became PRIMARY; an ECS circuit-breaker rollback is a failure, not success.
   Backend checks verify `data.status`, database health and the release SHA.
   Frontend deployment invalidates CloudFront and checks that the homepage serves HTML.
6. Backend releases update both scheduled job image revisions while preserving
   each schedule's enabled/disabled state, role, timezone and retry settings.
7. Perform real browser attachment upload/download, authentication, workflow and
   private-network checks. Verify CloudWatch logs. Enable attachment cleanup using
   `enable_attachment_cleanup=true` only after these checks; enable the SLA job
   separately after Member C's implementation is validated.

Retain the commit SHA, image digest, ECS revision, bootstrap task ARN, public URLs,
smoke results and rollback evidence with the release record.

AWS references: [ECS scheduled tasks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/tasks-scheduled-eventbridge-scheduler.html),
[preserving schedule fields when updating](https://docs.aws.amazon.com/scheduler/latest/APIReference/API_UpdateSchedule.html),
[managed CloudFront cache policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html),
[origin request forwarding](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-origin-request-policies.html).

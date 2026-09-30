# Manual GitHub Actions releases

Only `frontend.yml` and `backend.yml` appear as release workflows. Neither runs on
push, pull request, or a schedule. Each workflow operates on one component and uses
the same immutable ECR repository:

`256329410824.dkr.ecr.ap-southeast-2.amazonaws.com/infs803-group8-itsm-backend`

The `frontend-` and `backend-` tag prefixes separate the images. ECS services remain
separate in the `infs803-group8-itsm` cluster, region `ap-southeast-2`.

## Run a release

1. Open the repository's **Actions** tab.
2. Select **Frontend - manual build and deploy** or **Backend - manual build and deploy**.
3. Click **Run workflow** and leave the branch set to **main**.
4. Select the operation:

   | Operation | Behavior | `image_tag` |
   | --- | --- | --- |
   | `build-only` (default) | Run component checks, build Linux/amd64 image, push to ECR | Leave empty |
   | `build-and-deploy` | Build and push, then update the selected ECS service | Leave empty |
   | `deploy-existing` | Deploy an existing image without rebuilding application code | Enter its full component-prefixed tag |

5. Inspect the run summary for source commit, tag, digest and task revision.

Build tags are `<component>-<40-character commit SHA>-<run ID>-<attempt>`.
The attempt suffix permits a full rerun without overwriting an immutable ECR tag.
If only deployment failed, use `deploy-existing` with the tag recorded in the build
step. This reuses exactly the previously built image. Existing `*-<SHA>-opt1` images
are also accepted. A frontend workflow rejects backend tags and vice versa.

All AWS access is restricted to `main`. Selecting another branch skips the release
job. Merge the desired application changes before publishing. Same-component runs
are serialized with `cancel-in-progress: false`; GitHub may replace an older pending
run when another is queued. Frontend and backend can run independently.

## Checks and deployment

- Frontend: `npm ci`, TypeScript checks, Vitest, then production Vite/Nginx Docker build.
- Backend: install dependencies, Ruff, Pytest, then FastAPI Docker build. Integration
  tests requiring a separately provisioned database retain their existing skip rules.
- Both: run release-tool tests, obtain temporary AWS credentials through GitHub OIDC,
  and deploy an ECR digest rather than a moving tag.

The deployer clones the task definition currently used by the selected service,
preserving its roles, secrets, environment, ports, CPU/memory and startup command.
It refuses to start while another ECS deployment is active. It waits for stability
and verifies that the requested revision actually became active, so an ECS circuit
breaker rollback is reported as failure.

ECS can report matching task counts before its rollout state reaches `COMPLETED`.
The deployer keeps polling during this interval within the same 15-minute timeout,
instead of rolling back a healthy release. It logs the requested/current revision,
rollout state and reason, and task counts to make actual failures diagnosable.

Frontend releases invalidate the existing application CloudFront distribution and
verify the HTML endpoint. Backend releases check `/api/v1/health`, including database
health and `RELEASE_VERSION`, then update the attachment-cleanup and SLA-monitor
task definitions to the same image. Existing schedule state, timing, network and
retry configuration are preserved.

A deployment or smoke-check failure restores the previous service revision and
desired count. If a scheduled-task update fails, prior schedule targets are also
restored. Rollback failures remain visible as errors. If a run is force-cancelled
or its runner is lost, inspect ECS and rerun `deploy-existing` as needed; Python
cleanup cannot be guaranteed after an abrupt process termination.

For a planned rollback, run the affected workflow with `deploy-existing` and a
previous successful tag. Independent releases require compatible API and database
changes. Database bootstrap and schema migrations are not run by these workflows.

## One-time setup

1. Verify the resource IDs in `infrastructure/environments/production.json` against
   the existing AWS deployment. The file contains no database passwords or JWT secrets.
2. Review `infrastructure/policies/github-actions-trust.json` and
   `github-actions-release.json`. The trust policy accepts both GitHub's legacy and
   immutable-ID subject formats for this exact repository and `main` only.
3. Run `python infrastructure/scripts/setup_github_oidc.py` to preview. After review,
   run it with `--apply` using an AWS administrator session. It creates the provider
   and `infs803-group8-itsm-github-release` role without changing ECS or ECR resources.
4. In **Settings → Secrets and variables → Actions → Variables**, create:

   `AWS_RELEASE_ROLE_ARN=arn:aws:iam::256329410824:role/infs803-group8-itsm-github-release`

5. Merge the workflows into the default branch so GitHub exposes **Run workflow**.
   Verify `build-only` for each component before the first deployment.

The role can push/read only the shared repository, update the two named services
and schedules, pass the three existing task/scheduler roles to their respective AWS
services, and invalidate only the application CloudFront distribution. ECR login
and ECS task-definition registration/description use `Resource: "*"` because those
operations do not support the same resource scoping; ECS calls are region-limited.
The role cannot fetch secret values directly or change IAM policies or networking.

The existing Terraform ECR resource address remains `aws_ecr_repository.backend`;
both repository outputs now refer to it. If the existing repository is not already
in the correct Terraform state, import it instead of creating it again. Do not apply
the entire final stack merely to enable Actions: the live deployment has additional
domain/database settings managed by its existing deployment configuration.

## Local validation

```sh
python -m pip install -r infrastructure/requirements-release.txt
python -m ruff check infrastructure/scripts/release.py infrastructure/scripts/setup_github_oidc.py infrastructure/tests/test_release.py
python -m pytest infrastructure/tests -q
```

Use `actionlint` to validate `.github/workflows/*.yml`. Published actions are pinned
to commit SHAs. Check and update pins deliberately when upgrading them.

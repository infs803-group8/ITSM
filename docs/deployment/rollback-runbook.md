# Rollback runbook

Redeploy the last verified image and task-definition revision for the affected
service. Do not reverse database changes without an approved recovery plan and
backup.

The release script records the previous task definition and desired count before
each service update. A failed stabilization or health check restores those values;
an `all` release also rolls back previously updated services. Scheduler updates
preserve their prior settings and are restored on a subsequent release failure.

Inspect the failed task's CloudWatch log and verify the restored service's PRIMARY
revision, running count and health. If rollback itself fails, the workflow remains
failed and requires operator recovery; never describe that run as deployed.
After a frontend rollback, invalidate CloudFront again so cached files match the
restored image. For a manual rollback, use the prior task revision directly rather
than rebuilding or retagging an existing immutable ECR SHA.

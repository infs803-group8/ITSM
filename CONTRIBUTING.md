# Contributing

One Trello/WBS task equals one short-lived branch and one pull request.

Examples:

```text
feature/WBS-A15-s3-presigned-upload
feature/WBS-B09-create-ticket
feature/WBS-C23-tier2-escalation
feature/WBS-D12-ticket-detail-page
```

After repository bootstrap, do not push feature work directly to `main`. Do not use long-lived personal branches, force push, or shared-history rewriting. Merge with **Create a merge commit**.

UI pull requests include screenshots. API pull requests include tests and the corresponding OpenAPI update. Schema changes use a dedicated pull request and update both `backend/database/schema.sql` and database documentation.

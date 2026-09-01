# Database bootstrap runbook

1. Verify the target is a new private RDS MySQL instance.
2. Record the source commit and release dump checksum.
3. Import the schema-frozen dump once.
4. Run idempotent reference-data seeds.
5. Run constraint and smoke checks.
6. Save evidence under `backend/database/release/` and `docs/evidence/aws/`.

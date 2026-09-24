# Risk register

Track probability, impact, mitigation owner, early warning, contingency, and
review date. Priorities include limited development experience, contract drift,
integration delay, AWS credit use, and late evidence.

| ID | Date raised | Risk | Probability | Impact | Mitigation owner | Early warning | Contingency | Review date | Status |
|---|---|---|---|---|---|---|---|---|---|
| R01 | 2026-09-05 | The team's S3 handover notes contained a real, plaintext long-lived AWS access key/secret for the shared attachments bucket, sitting outside `.gitignore` protection. | Medium (accidental commit) | High (credential compromise, hard to fully revoke once in git history) | A | Any commit that touches a doc containing `AKIA...`/secret-looking strings | Rotate the IAM key immediately; move credential distribution to Secrets Manager or a short-lived channel | 2026-09-15 | Open — no rotation evidence from A yet; not closed by this doc review |
| R02 | 2026-09-05 | No documented, controlled process yet for provisioning non-USER accounts (Tier1/Tier2/Manager/Vendor) for local dev, integration testing, or the Final environment. | Medium | Medium (risk of ad-hoc DB edits or an open registration hole under deadline pressure) | B | Any local branch adding an open registration endpoint for non-USER roles | Define `seed.py` scope and an explicit approval step before M4 | 2026-09-15 | Open — no confirmed process from B yet; not closed by this doc review |
| R03 | 2026-09-05 | Member C (assignment/workflow/vendor_workflow/audit/sla, 12 of the 32 public APIs) had not started implementation as of this date, close to the original M2 window end. | Medium | High (cascades into M3–M8 if not caught up) | C | No open PR touching `backend/app/domains/{assignment,workflow,vendor_workflow,audit,sla}` by the next weekly check-in | Confirm remaining scope with the team, replan the C-owned milestones without skipping database/contract/test gates | 2026-09-15 | Open — in progress: audit domain has an open PR (#21, draft, CI passing) and decision-log/risk-register PR (#22, draft); assignment/workflow/vendor_workflow/sla domains not yet confirmed complete, so not closed |

Add new risks below this line as they're found; keep resolved rows with an updated status rather than deleting them — the report needs this table as risk-management evidence.

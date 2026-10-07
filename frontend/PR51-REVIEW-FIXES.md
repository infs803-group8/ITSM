# PR #51 R1–R4 local fixes and R3 coordination notes

> Follow-up status: this file records gaps identified during PR #51 review. PR #53 added API-33 to main; D04 regenerated the client and integrated persisted Vendor history reads. See [D04-HANDOFF.md](D04-HANDOFF.md) for the current implementation and verification.

Date: 2026-09-28. Branch: `feature/WBS-D03-ticket-workspace`.
Review baseline: `499767e1021dcc3b51cc1272ddc1ff9cc51c8a0e`.
These fixes changed only `frontend/`, without backend, OpenAPI, database, dependency or lockfile changes. They were completed and reported locally first; the user then authorized submission to existing PR #51. See that PR's fix commit for the final SHA.

## Local fixes

| Item | Location | Result |
| --- | --- | --- |
| R1 | `src/api/attachmentTransfer.ts`, `AttachmentsPanel.tsx` | Resolve extension/MIME once from the reference-data allowlist, filling only an empty File.type; validation and API-02 reuse that result, preserving rejection rules and raw signed-header PUT |
| R2 | `src/features/workspace/shared.tsx`, attachment/comment/ticket/workflow forms | Downloads use a separate read helper with duplicate/error/unmount protection and no query interference; writes cancel a narrower scope, resume cancelled active reads on failure and refresh affected data on success |
| R3 (D) | `src/mocks/workspaceHandlers.ts`, API/browser tests, README, D03-HANDOFF | Removed invented reply-body event metadata and returned `{}` to match the backend; tests distinguish successful submission/state/event changes from missing persisted reads |
| R4 | `src/features/workspace/WorkflowPanel.tsx` | CLOSE limit 1,000 and REOPEN limit 4,000, validated at input and submission; close reason remains optional and reopen requires nonblank text |

Regression locations:

- `tests/component/workspace.test.tsx`: empty MIME and rejection boundaries; download success/failure while reference data is delayed; duplicate-download prevention; rejection of late results after unmount; write scope and read recovery after failure; close/reopen length boundaries.
- `tests/e2e/attachment-flow.spec.ts` + `tests/fixtures/debug.log`: select a real disk file without injecting MIME; check empty File.type, text/plain presign, raw signed-header PUT without API Bearer and completion order.
- `tests/api/workspace.test.ts` + `tests/e2e/vendor-flow.spec.ts`: API-27 returns the reply immediately, while API-32 metadata contains no reply body. At this stage a returning Tier 2 user saw only events, which did not establish completed reply reading.

## Coordination note for B/C: remaining R3 / Q03 work at review time

PR #51 R3 identified an existing read gap, not a failure to save replies:

1. `VendorResponseService.respond()` in `backend/app/domains/vendor_workflow/service.py` already called the repository to save the response, but did not pass reply-body metadata when appending `VENDOR_RESPONDED`.
2. `backend/app/domains/audit/service.py` returned only stored metadata, using `{}` for empty values; it did not fill in reply text.
3. The API-27 write response included `vendor_response.message`, but API-17's `TicketDetail.vendor_request` and API-32 did not expose the reply body. An engineer reopening a ticket or starting another session could not retrieve the saved reply/discussion history.

**C was to lead, with B supporting**, following the original Q03 decision proposal:

- Confirm the read contract with the team first. Q03's proposed `GET /tickets/{id}/vendor-requests` was still a draft, not an approved interface. Changes to existing detail fields were another option requiring an explicit decision. A new endpoint required synchronized API count, OpenAPI, baseline and decision-record updates.
- Specify request/reply association IDs, bodies, timestamps, nulls for unanswered requests, history order/pagination and read rules for ACTIVE/RESPONDED/CANCELLED requests; include success and unauthorized examples.
- C implements persistent database reads and Vendor organisation isolation. B supports ticket-route registration, cross-domain detail fields/serialization and contract alignment. Historical reading must preserve existing ticket-access scope.
- Authorized Tier 2 / Manager users can read history within their ticket scope; Vendor can read only its organisation's current/history records. USER and Tier 1 cannot read Vendor collaboration bodies, and guessed IDs must not grant access to another organisation.
- Backend acceptance must verify that an authorized Tier 2 user can read the saved response after leaving/reopening, logging in again or using another authorized session. Cover multiple historical requests, organisation isolation, unanswered requests, closed/cancelled states and unauthorized cases, with contract/integration tests.
- **Do not copy full response bodies into audit metadata or substitute frontend caching of API-27 responses for persisted reads.**

D had corrected the Mocks, tests and completion notes. Once the contract and backend implementation were ready, D would regenerate the client, add the reply/history view and perform real integration. Q03 remained incomplete at the time of this review; passing a reply-submission test did not establish a complete Vendor discussion feature. The follow-up note at the top records its later resolution.

## Verification results

Local verification on 2026-09-28:

- `npm run check`: generation consistency, TypeScript, 129 unit/component tests and production build all passed, up from 117 with 12 new tests and strengthened existing cases.
- `npm run test:api:browser`: three passed.
- `npm run test:auth:e2e`: six passed.
- `npm run test:e2e`: seven passed, including a real disk `.log` upload with empty MIME and the close/reopen lifecycle.
- Valid close requests at 1,000 characters and reopen requests at 4,000 passed the existing contract-validation Mock, with actual CLOSED / REOPENED state assertions; over-limit inputs were blocked before HTTP.
- `git diff --check` passed. All changes/new files were under `frontend/`; verification preceded committing and used baseline `499767e`.
- Browser tests refreshed six `docs/evidence/d03-*.png` images. The successful real `.log` upload screenshot was inspected.
- The existing non-blocking bundle warning remained: main JavaScript 721.67 kB / gzip 233.69 kB. The warning threshold was not raised.

Real Python/MySQL/S3 integration is outside these results. Downloaded object bytes, CORS, signature expiry and backend authorization still require integration with the responsible members.

## PR #51 fix-description reference

### Trello / WBS task

D03 — service desk workspace; PR #51 review follow-up (R1–R4).

### What changed

- Resolve empty file MIME from reference data and reuse it for presign; retain signed-header raw uploads.
- Separate download reads from writes; scope cache cancellation and resume interrupted active reads.
- Match vendor audit Mock payloads to the backend and remove misleading reply-read assertions.
- Align close/reopen text limits with the contract and add boundary regressions.

### Evidence

- [x] Tests pass: 129 unit/component, 3 API-browser, 6 account-browser and 7 business-browser tests; generation, typecheck and build pass.
- [ ] API changes include tests and OpenAPI updates — N/A, no contract changes.
- [x] UI changes include screenshots (`docs/evidence/d03-*.png`).
- [ ] Schema changes update schema.sql and database documentation — N/A, no schema changes.
- [x] No secrets or .env files are included.

### Reviewer notes

At the time of PR #51 review, persisted Vendor reply/history reading remained incomplete pending Q03: C led, B coordinated contract/routing and D consumed the frontend API. API-27 submission and state transitions were tested separately; no complete Vendor discussion flow or real Python/MySQL/S3 integration was claimed. PR #53 and D04 subsequently addressed the history-reading gap, as recorded above.

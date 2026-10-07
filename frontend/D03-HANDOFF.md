# D03 business-page handoff

## Branch and scope

- Created `feature/WBS-D03-ticket-workspace` from main `01fad63`, which already included D02 / PR #50.
- Main already contained profile concurrency fix `515723b`; no additional cherry-pick was needed.
- Implementation changes were limited to `frontend/`, without backend, database, OpenAPI, dependency or lockfile changes.
- Retained the yellow/black/white desktop theme; added no mobile-specific layouts.
- The initial work was left locally for user review, without automatic commit, push, PR creation or main merge.

## Pages and features

| Route / file | Implementation |
| --- | --- |
| `/tickets` · `src/features/workspace/TicketListPage.tsx` | Role-scoped ticket / Vendor-request lists; search, status, category, priority, SLA and manager `assignee_id` filters; sorting, pagination, empty states and retry |
| `/tickets/new` · `TicketForm.tsx` | USER creation with title, description, category and priority; length/whitespace validation; opens detail after creation |
| `/tickets/:id` · `TicketDetailPage.tsx` | Description, role-visible status, assignee, SLA, waiting reason/deadline, resolution, closure and Vendor request; safe null handling and read-only terminal states |
| Same detail page · `TicketForm.tsx` | Editing when EDIT is available; sends only changed core fields, without directly changing status, assignee or SLA |
| Same detail page · `WorkflowPanel.tsx` | API-21–31: assign/reassign, start, request user information, resume, escalate, request Vendor, Vendor response, submit resolution, confirm, reopen and close; paginated eligible-engineer and Vendor selection |
| Same detail page · `CommentsPanel.tsx` | Comment list/pagination, reference-data visibility selection and submission; no ordinary Vendor comment entry; reminder that comments do not replace workflow actions |
| Same detail page · `AttachmentsPanel.tsx` | Attachment list/pagination, on-demand download, type/size checks, upload progress and confirmation retry; expired uploads must restart |
| Same detail page · Activity | API-32 role-scoped event timeline, including system events, cycle, time and simple metadata returned by the server |
| `/dashboard` · `DashboardPage.tsx` | Tier 1/Tier 2/Manager scope, status counts, SLA risk/overdue and reopened-unassigned counts; manual refresh |
| `/overdue` · `DashboardPage.tsx` | Current/history overdue views, category/priority filters, pagination and detail links |
| `src/app/router.tsx` / `components/layout/AppLayout.tsx` | Role guards, sidebar entries and current-page title; retains D02 login protection |
| `src/styles/global.css` | Tables, forms, workflow controls, risk labels and desktop dashboard; keyboard Skip link remains usable |

Login still opens the profile page, with business pages available from the sidebar. No out-of-contract password-reset, role-management, ticket-deletion, attachment-deletion or push-notification pages were added.

**Historical gap, PR #51 R3 / Q03, resolved by D04:** D03 initially provided only API-27 submission, state changes and event display. After PR #53, D04 integrated persisted request/reply history through API-33. See [D04-HANDOFF.md](D04-HANDOFF.md).

## Key rules

1. Workflow buttons use server-provided `available_actions`; the page does not infer authorization from status. It displays server-provided `display_status`. Vendor views hide requester, description, internal comments, assignee and SLA.
2. Successful Tier 1 escalation immediately leaves detail and removes its cache. Detail 403/404 returns to the list with a neutral notice, preserving a valid login. Detail queries retain no cache after leaving the page.
3. A 409 conflict never automatically replays a write; workflow forms request a fresh ticket read. A 422 preserves entered values. A 401 uses D02's session/cache cleanup.
4. `shared.tsx` acquires the write lock before any asynchronous wait. Around writes, it cancels only affected ticket, list, summary and engineer-directory reads; success invalidates and refreshes those reads, while failure resumes cancelled reads that remain active. Reference data, Vendor directories and unrelated tickets are unaffected. Downloads use a separate read-only helper with lock/error/unmount protection and no query cancellation or invalidation. Unmounted components reject late results.
5. Close requires an explicit irreversible-action warning and a required checkbox, sending `acknowledge: true`. Vendor requests warn against including User names, emails, IDs or other personal information.
6. `src/api/attachmentTransfer.ts` uses a separate XHR: API-02 → raw PUT with original signed headers and no API Bearer token → API-03 with only `upload_id`. Completion appears only after confirmation succeeds. A failed confirmation retains the session and does not re-upload bytes.
7. Upload extension/MIME mapping comes from API-12 reference data and follows API-02's type enum. An empty browser MIME is filled only from this allowlist. Validation and presign share the resolved result; explicit mismatches remain rejected. Raw PUT always uses the returned signed headers.
8. ASSIGN / ESCALATE / CLOSE allow 1,000 characters; REOPEN 4,000; RESOLVE 5,000. Both HTML maxlength and submit handlers validate the limits. Close reasons remain optional; reopen reasons reject whitespace-only text.

## Mocks and generation

- `scripts/generate-api.mjs` generated 32 operations at D03. D04 added API-33, bringing examples and validation schemas to 33 operations. `api:check` verifies generated files too.
- The original nine baseline fixtures, generated client, contract hash and OpenAPI were unchanged by D03.
- `src/mocks/workspaceHandlers.ts`, `workspaceModel.ts` and `state.ts` provide multi-role demonstrations and state transitions; the original `handlers.ts` adds role coverage.
- The development login's Demo role supports USER / Tier 1 / Tier 2 / Vendor / Manager. It only fills fake credentials; it does not switch roles in a live session. Production does not import this entry point.
- Fake accounts: `user@example.com`, `tier1@example.com`, `tier2@example.com`, `vendor@example.com`, `manager@example.com`, all with fake password `MockPass123!`. Registration still creates USER only.
- Refresh clears the in-memory token and Mock data. For demonstrations across roles, Sign out in the page and log in as another account without refreshing.
- Examples include requester ticket 5001, Vendor collaboration ticket 6001 and overdue ticket 6002. The latter two do not belong to the example USER and cannot be viewed by that USER.
- Mock downloads open `public/mock-download.txt`, explicitly identifying a placeholder rather than claiming to download the uploaded original. Real-backend mode uses API-05's download URL.

Mocks do not simulate MySQL transaction locks, real automatic assignment, scheduled SLA jobs, historical multi-organisation Vendor permissions or full upload-session expiry, cleanup and integrity guarantees. Those require backend implementation/tests; this work does not establish real-service acceptance.

## Verification commands

Run in `ITSM/frontend`:

```powershell
npm run check
npm run test:api:browser
npm run test:auth:e2e
npm run test:e2e
```

- `check`: generation consistency, TypeScript, unit/component tests and production build.
- Existing API-browser regressions: three; account-page regressions: six.
- D03 business-browser regressions: seven. The original four skipped placeholders were replaced and a Manager scenario added. Chromium runs at 1440×1000; ticket list/detail and original account tests also cover 1280×800.
- New API tests exercise generated SDK → Axios → MSW, checking response shape, permissions and workflows. The 32 new fixtures are checked against the repository contract, not handwritten DTOs.
- Component cases cover loading, empty data, 503 retry/request IDs, null, Vendor redaction and absence of ordinary-comment requests, 401, cache cleanup/navigation for 403/404, 409 conflicts, comment retention on 422, confirmation failure without duplicate PUT, and write-lock/cancellation/unmount protection.
- Results below record the actual checks. Mock tests are not Python/MySQL/AWS acceptance.

## Local preview

1. Run `npm run dev` inside this branch's `frontend` and keep the terminal running.
2. Set `VITE_USE_MOCKS=true` in `.env`, preserving any existing settings. Restart the server after changes.
3. Open the printed URL, usually `http://localhost:5173`. Choose Demo role → Use demo account → Sign in, then use the sidebar.
4. Create an unassigned ticket as USER; sign out within the page, switch to Manager and assign it; switch to an engineer to process it, then back to USER to provide information/confirm. Ticket 5001 supports a Tier 1 escalation demonstration; 6001 supports a Vendor response.
5. For the real backend, set `VITE_USE_MOCKS=false` and verify the API base URL, CORS and team test accounts. Do not put credentials in source or VITE variables.

## Screenshots

`docs/evidence/d03-*.png` covers ticket list, creation, detail, engineer actions, Vendor workspace, attachments, management dashboard and overdue list. Account regressions also refreshed D02 screenshots with the business sidebar/development role selector.

## Release acceptance outside this work

- Real Python/MySQL/S3 integration, including downloaded object bytes, expired links, CORS and actual multi-role permissions.
- Docker/Nginx/AWS deployment and public HTTPS acceptance.
- Backend scheduled jobs, real SLA boundaries, historical multi-Vendor access and database concurrency are not covered by this frontend Mock completion claim.
- Final user manual, team report and human PR review still require real deployment results.

## Initial D03 verification record, before review fixes

Latest results after the PR #51 fixes: `npm run check` passed with 129 unit/component tests; all three API-browser, six account-browser and seven business-browser tests passed. Coverage includes a real disk `.log` file with empty MIME, downloads leaving reference data unaffected and text-length boundaries. Fixes were first verified locally; the user then authorized submission to existing PR #51. See [PR51-REVIEW-FIXES.md](PR51-REVIEW-FIXES.md) for individual fixes and B/C coordination notes. The original D03 record follows.

2026-09-28:

- `npm run check` passed: consistent generated files, TypeScript, **117 unit/component tests** and production build.
- `npm run test:api:browser`: **three passed**.
- `npm run test:auth:e2e`: **six passed**.
- `npm run test:e2e`: **seven passed**, with no skipped business placeholders.
- `git diff --check` passed; changes were confined to `frontend/`.
- Production JavaScript contained no fake password `MockPass123!`, Tier 1 fake account, development role-entry text or Mock Vendor names.
- Desktop screenshots were generated and inspected. No deployment or real-service integration was claimed.
- The existing non-blocking bundle warning from D02 remained: main JavaScript about **721 kB / gzip 233 kB**. Its threshold was not raised; route-level splitting can be addressed separately.

# Frontend

React + TypeScript + Vite application owned by member D. The source of truth for HTTP requests and responses is `docs/api/openapi.yaml`.

## Local development

Run the following **inside the team's `ITSM/frontend` directory**, not the older standalone prototype. The selected local runtime is **Node.js 22.23.3** (recorded in `.nvmrc`). With jsdom 30, Node 22 must be **22.22.2 or newer**; the old Node 22.19.0 installation is not supported by that dependency. `engines.node` records the supported Node release ranges.

The shared dependency ranges and all 16 shared direct dependency versions match main at `6736508`: Vite 8.2.2, React plugin 6.1.1, Vitest 5.0.1, jsdom 30.0.1 and jest-dom 7.0.1 are the lockfile baseline. D01 keeps its additional generator, validation packages and test scripts. `@types/node` is separately pinned to 22.19.0 to satisfy Vite 8's type-package requirement; its version is not the installed Node runtime version.

Use `npm ci` to reproduce the committed lockfile. The `^` ranges inherited from main are not an instruction to upgrade dependencies on every checkout. Review intentional dependency upgrades separately. D01 now incorporates main at `6736508`, including the team's backend fixes, contract updates and GitHub Actions removal. D01's own changes remain frontend-only; do not overwrite the merged backend or contract with older branch files.

```powershell
npm ci
# Preserve existing local settings.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`. Keep that terminal running. `npm run test:unit` runs tests and exits; it does **not** start the website.

## Account pages (D02)

D02 added desktop web pages at `/login`, `/register` and `/profile`, plus a shared yellow/black/white theme, workspace layout, session management and route guards. D02 and its concurrency fix are merged into main at `01fad63`. D03 adds the business pages below; the older standalone prototype has not been copied over the repository.

In local Mock mode, choose a **Demo role**, click **Use demo account**, then **Sign in**. This development-only selector fills a fake account; it does not change roles in a live session and is absent from the production application. Registration still creates USER accounts only. In real-backend mode these pages call generated API-08/09/10/11 operations; actual Python/database integration is still to be verified with the team. Only engineer accounts receive the availability control.

Profile saves cancel and await the current account's pending profile query before sending PATCH, so a delayed refresh cannot overwrite the saved response. A synchronous submission lock covers cancellation and the write; leaving the page or signing out cancels the pending operation. Refresh and read-error retry share a guard, and automatic focus/reconnect refetches are disabled for this editable profile page. Save failures release the lock so users can retry.

`antd` **6.6.5** and `@ant-design/icons` **6.3.4** are exact-pinned additions. Existing direct dependency versions remain unchanged. Desktop viewports are the acceptance target; mobile-specific layouts and tests are not included.

See [D02-HANDOFF.md](D02-HANDOFF.md) for its historical change map and tests. D02, the PR #49 review fixes and the PR #50 concurrency fix are now merged into the D03 base.

## Business pages (D03)

Work branch: `feature/WBS-D03-ticket-workspace`, based on main `01fad63`. Desktop-only, frontend-only; no dependency changes.

| Route | Function |
| --- | --- |
| `/tickets` | Role-scoped queue / vendor requests, search, filtering, sorting, pagination |
| `/tickets/new` | USER creation, field validation and real API-15 client |
| `/tickets/:id` | Detail, edit, workflow actions, comments, attachment upload/download and event timeline |
| `/dashboard` | Engineer / manager counts, SLA risk and action-required summary |
| `/overdue` | Current/history SLA breaches with filters, pagination and ticket links |

The sidebar exposes only role-appropriate routes. Ticket buttons come from `available_actions`, not an invented status-to-permission mapping in the UI. The detail page handles nullable fields, USER/Vendor-visible statuses, read-only closure, conflict/reload, and neutral unavailable navigation. Workflow forms use API-21–31; a permanent close requires explicit acknowledgement. Form writes lock synchronously, cancel only affected ticket/queue/summary/assignee reads, abort on unmount, and invalidate affected caches before refreshing. Failed writes restart interrupted active reads; reference data, vendor directories and unrelated ticket details are not cancelled. Download URL reads use a separate guarded helper without query cancellation or invalidation.

**Not complete — Q03:** vendor reply submission and its status/event transitions work, but persisted vendor reply bodies and request/reply history have no approved read API yet. API-27 returns the immediate reply; API-17 has no reply body and the actual API-32 `VENDOR_RESPONDED` metadata is empty. The Mock/tests now preserve that limitation instead of fabricating reply text in the timeline. C owns the read capability, B coordinates ticket routing/contract fields, and D will implement the reader after the team approves and delivers the contract. See [PR51-REVIEW-FIXES.md](PR51-REVIEW-FIXES.md) for the handoff. This is not a claim that the full vendor discussion workflow is complete.

See [D03-HANDOFF.md](D03-HANDOFF.md) for the exact change map, evidence and remaining real-service checks.

## Generated API (D01)

`@hey-api/openapi-ts` is pinned to **0.99.0** in `package.json` and the lockfile. Configuration lives in `openapi.config.mjs`.

### Development dependency security maintenance

The 2026-09-24 security fix pins `ajv` to **8.20.0** and `yaml` to **2.9.1**. A narrow npm `overrides` entry replaces only `@hey-api/json-schema-ref-parser@1.4.4`'s `js-yaml` dependency with **4.3.2**. The parser currently pins vulnerable js-yaml 4.2.0 upstream; the override keeps the generator at 0.99.0 without changing the API contract or generated output. It does not disable security auditing.

Keep the override until the generator's parser dependency includes the upstream security fix. When upgrading that dependency, review/remove the version-scoped override and rerun `npm ci`, `npm audit`, `npm run check`, and `npm run test:api:browser`. Do not use `npm audit fix --force` to silently replace the fixed generator version.

After this fix, full and production-only npm audits reported **0 known vulnerabilities**; all 66 unit/component tests and both browser tests passed. Audit results are time-specific, so repeat the audit before a dependency upgrade or release.

### Regeneration

```powershell
npm run api:generate
npm run api:check
```

- Input: `../docs/api/openapi.yaml` (read-only; do not edit it to make the frontend pass).
- Output: `src/api/generated/` (all 32 operation functions, types, bundled Axios runtime, contract hash), `src/mocks/fixtures.generated.json` (unchanged nine baseline examples) and `src/mocks/workspace-fixtures.generated.json` (D03: all 32 canonical examples and schemas). Both fixture files are generated, never hand-edited.
- Commit the generated source and `public/mockServiceWorker.js`. Do not edit generated files manually. `api:generate` replaces stale generated files; `api:check` regenerates into a temporary directory and checks differences without changing the working files.
- Line endings are normalized for Windows/Linux reproducibility. The contract-hash test detects source changes whenever the unit suite runs. Full generated-file drift is checked by `npm run api:check`.
- Run generation from the full repository. The production Docker build uses the committed generated files; it does not need the parent `docs` directory in its frontend-only build context.

**Resolved contract annotation:** main removed the incorrect `writeOnly` flag from `LoginData.access_token`. The old `readWrite: false` workaround has been removed; generation now uses the default read/write handling. The response token remains required. Passwords legitimately remain write-only, so the generated SDK uses `RegisterRequestWritable` and `LoginRequestWritable` for request bodies. `src/api/types.ts` exposes convenient `RegisterRequest` and `LoginRequest` aliases derived directly from the generated operations' `body` types; import those aliases for forms and authentication rather than the read-view names in `types.gen.ts`. Contract, type and request tests protect both token and password fields.

Generator documentation: [Axios runtime configuration](https://heyapi.dev/docs/openapi/typescript/clients/axios), [generated output](https://heyapi.dev/docs/openapi/typescript/output).

## Using the client in future pages

Import operations from `src/api/generated/sdk.gen.ts`, and DTOs from `src/api/generated/types.gen.ts` (also re-exported from `src/api/types.ts`). Do not create a second set of handwritten request/response interfaces.

```typescript
import { login } from "./api/auth";
import { api16ListTickets } from "./api/generated/sdk.gen";
import { normalizeApiError } from "./api/errorHandler";

try {
  const session = await login({ email, password });
  // login stores the bearer token; protected SDK operations read it automatically.
  const response = await api16ListTickets({ query: { page: 1, page_size: 20 } });
  const tickets = response.data.data;
  const pagination = response.data.meta;
  // Store session.user / tickets / pagination in your page or query state.
} catch (error) {
  const failure = normalizeApiError(error);
  // failure.message, code, status, details, requestId, kind
}
```

The first `.data` is Axios's HTTP body; the second is the contract's `data` field. Workflow operations return `response.data.data.ticket`. Do not flatten or rename these envelopes, numeric IDs, uppercase enums, or nullable fields.

`src/api/httpClient.ts` applies the base URL, 10-second timeout, `X-Request-ID`, and normalized errors. Public health/register/login operations do not automatically carry a bearer token. HTTP errors retain the safe message, code, details and request ID; network, timeout and cancellation errors are distinguished. `ApiErrorNotice` is an optional accessible display component; it does not expose raw details or stack traces.

Tokens live **only in memory** (`tokenStorage.ts`); page reload requires sign-in again. A 401 for the current bearer token clears it and notifies `onUnauthorized`. D02's `AuthProvider` subscribes to clear user/query state and return to login. Pages should call the provider's `signOut()` rather than only the low-level `logout()` helper, so account caches are cleared too. Failed public logins, 403 responses and stale requests from an older session do not clear a newer token. Logout is local: the contract has no logout or refresh endpoint. Do not invent automatic refresh/retry of writes.

Attachment uploads now use `src/api/attachmentTransfer.ts`: presign → raw XHR PUT with returned signed headers and progress → complete with `upload_id` only. The PUT bypasses the authenticated API client. Completion failures keep the upload session for retry without resending bytes; expired sessions require a new upload. File size, extension and MIME checks use reference data. When the browser supplies an empty MIME (for example a disk `.log` file), validation and presign share the MIME resolved from API-12's allowed extension/type pair, constrained to API-02's contract enum. An explicit mismatched MIME or unsupported extension is still rejected. Download URLs are requested on click and are not stored in browser persistence.

### Tier 1 escalation and detail-page scope

API-25's success example now has `data.ticket.available_actions: []`: a Tier 1 caller loses access to the ticket after escalating it to Tier 2. The action can succeed with HTTP 200 while a later API-17 GET by the same caller returns 404. Do not recreate START/COMMENT/UPLOAD_ATTACHMENT actions from the ticket status.

D03 leaves detail after successful Tier 1 escalation, removes the old detail cache and loads the queue. Detail 403/404 returns to the queue with a neutral unavailable message without logging the user out. Other API errors are shown in context. Component and browser regressions cover these behaviours.

## Mock mode and its limits

In your local `.env`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_USE_MOCKS=true
```

Restart Vite after changing environment variables. The worker starts before React renders. It is enabled only in development with the explicit flag; production never starts or imports the Mock modules. If worker setup fails, the app shows a startup error rather than silently using the real backend.

The original D01/D02 baseline behaviours remain covered:

| API | Local behavior |
| --- | --- |
| 01 | Contract-shaped health response |
| 08–09 | Register, duplicate email, login and invalid credentials |
| 10–11 | Read/update own profile; reject USER availability changes |
| 12 | USER-scoped reference data: no PENDING_VENDOR option; only USER_VISIBLE comment/attachment visibility |
| 15 | Create own ticket using the deterministic UNASSIGNED/no-eligible-engineer branch |
| 16–17 | Own ticket list/detail, filters, sorting, pagination, and scope-safe 404 |

Fake demo accounts: `user@example.com`, `tier1@example.com`, `tier2@example.com`, `vendor@example.com`, `manager@example.com`; all use `MockPass123!`. These are **not** real backend accounts or real JWTs. Accounts, tokens and tickets reset on page reload. Request bodies use generated schemas; baseline filters and pagination are validated. The USER Mock strips engineer-only actions from the example ticket.

PR #49 review follow-up (included in D02): API-12 clones the canonical fixture before filtering USER-only options, leaving other reference settings and the generated fixture unchanged. API-16 rejects an explicit USER `status=PENDING_VENDOR` filter with `403 DATA_SCOPE_DENIED` after query validation. That response retains the request ID and must not clear the token or invoke `onUnauthorized`. SDK/MSW and browser regressions protect these rules; existing legal filtering, pagination and user isolation tests remain in place.

D03 adds typed, stateful UI scenarios for directories, editing, comments, workflow, vendor response, attachment transfer/confirmation, events and dashboards in `workspaceHandlers.ts` / `workspaceModel.ts`. All 32 contract operations have a handler. Unknown operations still fail locally, never falling through to a real server. The sandbox has one vendor organisation and controlled sample tickets; it is **not** a faithful implementation of backend transactions, historical multi-vendor authorisation, auto-assignment, scheduler timers, AWS expiry or integrity/security guarantees. Overdue history uses explicitly seeded events. The Mock download is an openly labelled placeholder, not the original file. Validate those behaviours against the Python/MySQL/S3 stack before release.

Set `VITE_USE_MOCKS=false` to call the Python backend. Confirm backend routes, credentials and CORS are ready. Production defaults to same-origin `/api/v1`; the team Dockerfile also supplies that value. Never store AWS keys, passwords, bearer tokens or other secrets in `VITE_*` variables: they are public browser configuration.

`public/mockServiceWorker.js` is installed/generated by MSW and must match the locked dependency. If updating MSW, run `npm run mocks:worker` again. It may be copied as a static build asset, but is never registered by the production app.

## Checks before your manual PR

The merged main removed GitHub Actions checks, so run these checks locally before your manual PR; there are no active repository workflow checks to rely on.

```powershell
npm run check
npm run test:api:browser
npm run test:auth:e2e
npm run test:e2e
```

`check` verifies generated-file drift, TypeScript, Vitest tests, and the production build. It no longer permits a false green result with zero unit tests. The browser check launches its own development server on `127.0.0.1:5181` with Mock enabled and shuts it down afterward. If Chromium is missing, install it once with `npx playwright install chromium`.

- `tests/api/contract.test.ts`: all 32 success examples, generation hash, nine fixtures, readable login token, empty post-escalation actions and important generated types.
- `tests/api/client.test.ts`: actual generated SDK → Axios → MSW requests, token behavior, validation, errors, query parameters, USER isolation and test-only escalation-success/detail-404 handling.
- `tests/api/errorHandler.test.ts`: HTTP, network, timeout, cancellation and production Mock guard.
- `tests/component/ApiErrorNotice.test.tsx`: accessible message/request ID, retry click, no raw details.
- `tests/api-browser/api-foundation.spec.ts`: three real Chromium/Service Worker checks, including the PR #49 USER-permission regression; not full user-page flows.

`tests/component/auth-pages.test.tsx` has 23 account-page integration cases using React StrictMode and the generated SDK through MSW. The five PR #50 regressions use controlled request/cancellation promises to cover stale refreshes, duplicate submissions and retry, sign-out/navigation during cancellation, and refresh/retry guards. `tests/auth-browser/auth-pages.spec.ts` adds six desktop Chromium account flows, including keyboard interaction. `test:auth:e2e` uses an isolated server on port 5182; API browser checks use 5181. Browser tests require those ports to be free and shut down their servers after completion.

The four original `tests/e2e` placeholders are now executable business flows; the manager suite makes five files / seven tests, using an isolated Mock server on port 5183. They cover creation/edit/search/comment, user/engineer lifecycle, Tier 1 escalation, vendor response/request, raw attachment PUT and manager assignment/dashboard. `tests/api/workspace.test.ts` checks canonical schemas and SDK/Mock flows; `tests/component/workspace.test.tsx` checks loading, errors, role boundaries, cache cleanup, cancellation, duplicate submissions and confirmation retry. No real backend integration, Docker deployment or S3 upload is claimed by these Mock tests.

After the 2026-09-24 main sync, generated-file checks, TypeScript, all **69 unit/component tests**, both browser tests and the production build passed. Full and production-only npm audits reported 0 known vulnerabilities. The merged backend's 403 unit/contract tests also passed using an existing isolated Python environment, with one test-library deprecation warning; no real database or AWS tests were run.

See `D01-HANDOFF.md` for the Chinese change summary and next development steps.

# D02 login, registration and profile-page handoff

## Work location and scope

- Repository: `ITSM`, not the older standalone `INFS803/frontend` prototype.
- Branch: `feature/WBS-D02-auth-pages`, created from main `6bdcdf8` after D01 was merged.
- All implementation changes are under `frontend/`. Backend, database, OpenAPI and generated client files are unchanged.
- With subsequent user authorization, D02 and the PR #49 review fixes were submitted together for review. The team decides separately whether to merge into main.
- The requested target is desktop web, without mobile-specific layouts or mobile acceptance checks. Ordinary layout adjustments for narrower desktop windows remain.

## Delivered features

| Feature | File | Implementation |
| --- | --- | --- |
| Login | `src/features/auth/LoginPage.tsx` | Email/password validation, password visibility toggle, duplicate-submission prevention, errors and request IDs; calls API-09 and opens the profile page on success |
| Registration | `src/features/auth/RegisterPage.tsx` | Display name, email, password and confirmation; calls API-08, then returns to login with the email filled in; sends neither confirmation password nor role and does not log in automatically |
| Profile | `src/features/profile/ProfilePage.tsx` | API-10 reading and API-11 updates; sends only changed fields; loading, retry, save confirmation and cancellation |
| Role differences | `src/features/auth/roleLabels.ts`, profile page | Email, role and vendor organisation are read-only; only Tier 1/2 engineers can edit `is_available`; public registration creates USER only |
| Session management | `src/features/auth/AuthProvider.tsx` | Signed-in user, logout, 401 expiry notice, account-query cache cleanup and stale-request isolation; token remains in memory and refresh requires login again |
| Page access | `src/app/roleRoutes.tsx`, `router.tsx` | Profile requires login; signed-in users do not revisit login/registration; reusable role-allowlist guard and 403/404 pages |
| Shared layout | `src/components/layout/` | Brand bar, authentication shell, dark sidebar, top bar and sign-out control; no placeholder links to unfinished ticket pages |
| Shared forms | `src/components/forms/` | Shared name/email/password rules and a keyboard-accessible password-visibility button |
| Theme | `src/styles/theme.ts`, `global.css` | Ant Design with yellow primary buttons, black structural areas, white content, small corner radii and clear borders; no gradients or large shadows |
| Development demo | `src/features/auth/DevDemoAccount.tsx` | “Use demo account” appears only in development Mock mode; the production build excludes the component and fake credentials |
| Dependencies and entry point | `package.json`, `package-lock.json`, `src/app/providers.tsx` | Added exact-pinned Ant Design 6.6.5 and icons 6.3.4; connected theme and session providers while retaining existing dependency versions |
| Request cancellation | `src/api/auth.ts` | Optional AbortSignal for login; cancels on leaving the page and prevents a late response from restoring the token |

`/` opens the profile route and redirects unauthenticated users to `/login`. There is no remember-me, password-recovery or token-refresh feature because the contract provides no such endpoints.

Frontend role guards control page access and visible actions; they cannot replace backend authorization. Engineer/Vendor component tests use test-only role data. D01's shared USER Mock was not expanded into a complete multi-role backend at this stage.

## Local preview

Run in an `ITSM/frontend` terminal:

```powershell
npm ci
# Preserve any existing .env settings.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
npm run dev
```

Open the printed URL, usually `http://localhost:5173`, and keep the terminal running. `npm run test:unit` runs tests and exits; it does not keep a website running.

Set `VITE_USE_MOCKS=true` in local `.env`, restart the development server and choose **Use demo account → Sign in**. The demo uses `user@example.com` / `MockPass123!`, not a real backend account. Mock registrations and data changes reset on refresh.

For the Python backend, set `VITE_USE_MOCKS=false`, check `VITE_API_BASE_URL`, backend availability and CORS, then use a real backend test account. The pages use the generated client, but this handoff does not claim completed database integration.

## Tests and verification

After the local PR #49 review fixes on 2026-09-27, generation consistency, TypeScript, **91 unit/component tests**, **six desktop-page tests**, **three API-browser tests** and the production build all passed. Earlier that day, D02's `npm ci` and full/production-only security audits passed with **zero known findings**. The review fixes did not change dependencies. Direct dependencies were not upgraded, and installed versions matched the lockfile.

Dependencies and the MSW worker damaged during an interruption were restored from the lockfile. `public/mockServiceWorker.js` ultimately matched main and was excluded from D02's changes. Production JavaScript contained no demo credentials or Mock demo entry point.

```powershell
npm run check
npm run test:api:browser
npm run test:auth:e2e
npm audit
npm audit --omit=dev
```

- `check`: consistency of 32 generated APIs/nine baseline Mocks, TypeScript, unit/component tests and the production build.
- Component tests: `tests/component/auth-pages.test.tsx`, with 18 original cases plus five PR #50 concurrency regressions, 23 total. Coverage includes forms, profile updates, roles, sessions, cancellation and the concurrency cases below.
- New browser tests: six cases in `tests/auth-browser/auth-pages.spec.ts`, covering registration/login/profile changes/logout/back-navigation protection, errors, refresh clearing the session, desktop viewports, keyboard use and navigation from 404.
- API-browser tests: the original two plus one PR #49 USER-permission regression, three total. Existing API assertions were retained.
- Ticket, engineer, Vendor and attachment business E2E tests still consisted of four skipped placeholders at this stage; they do not count as passes.
- Desktop acceptance used Chromium at 1440×1000 and 1280×800. Mobile and all-browser validation were not claimed.

Desktop screenshots generated by browser tests with fake data:

- [Login](docs/evidence/d02-login-desktop.png)
- [Registration](docs/evidence/d02-register-desktop.png)
- [Profile](docs/evidence/d02-profile-desktop.png)

## Included D01 / PR #49 review fixes

The Member D PR #49 review notes dated 2026-09-25 were addressed on the D02 branch, without a separate push or PR. Two new regressions were first run and failed, reproducing the review findings; the fixes then passed full verification.

| File | Additional change |
| --- | --- |
| `src/mocks/handlers.ts` | After cloning the shared API-12 fixture, excludes `PENDING_VENDOR` for USER and limits both comment and attachment visibility to `["USER_VISIBLE"]`; preserves other valid states, settings and the original fixture. API-16 rejects USER's `PENDING_VENDOR` filter after query-format validation, returning `403 DATA_SCOPE_DENIED` with a request ID |
| `tests/api/client.test.ts` | Added four SDK → Axios → MSW regressions: USER options and unchanged source fixture; 403 error instance/request ID/token retention/no logout; authentication and format validation first; all valid status filters. Existing pagination and user-isolation cases remain and pass |
| `tests/api-browser/api-foundation.spec.ts` | Added one real-browser Service Worker regression for role options, permission errors and successful requests/session retention after the error |
| `README.md`, this file | Updated Mock limits, fix details and actual test counts |

These fixes changed neither backend, OpenAPI, generated client nor `fixtures.generated.json`, and did not implement full engineer/Vendor/attachment/SLA Mock workflows. The 91 tests and nine browser tests were the actual D02-plus-fix results, not old counts copied from the review notes. The production build retained only the non-blocking size warning recorded below.

## PR #50 profile refresh/save concurrency fix (2026-09-28)

Following the Member D PR #50 review notes dated 2026-09-28, the fix stayed on `feature/WBS-D02-auth-pages`. With user confirmation, the branch was committed and pushed to update existing PR #50. No new PR or main merge was created.

### Changes

- `src/features/profile/ProfilePage.tsx`: mutation `onMutate` awaits `queryClient.cancelQueries({ queryKey, exact: true })`, cancelling only the current account/session's profile query before PATCH. The successful response updates the form, account summary, AuthProvider and query cache, preventing an older GET from overwriting it.
- The submission lock is set synchronously before awaiting cancellation and released by request identity on success/failure. This prevents repeated submissions and allows retry after failure.
- AbortSignal is checked after the cancellation wait and before/after PATCH. Signing out or leaving prevents a queued PATCH and rejects cancelled write results. Existing session-version protection remains.
- Refresh and the error notice's Try again use the same guarded entry point. Neither starts a read while saving or while unsaved edits exist. Automatic window-focus and reconnect refreshes are disabled on this editable page.
- `tests/component/auth-pages.test.tsx`: added five controlled-Promise tests for an old GET arriving after a successful PATCH; repeated submission and failure/retry while awaiting cancellation; logout during that wait; navigation away during that wait; and protection of both refresh and read-retry while saving. Assertions cover consistency of the form, summary, AuthProvider and cache without fixed sleeps to determine request order.
- `README.md` and this file record concurrency handling and the new coverage.

This fix changed no backend, OpenAPI, generated client, generated fixtures or dependencies and did not alter the PR #49 permission fixes. Automated coverage still stops at MSW and does not establish real database integration.

### Verification results

- `npm run check`: generation consistency for 32 APIs/nine baseline Mocks, TypeScript, **96 unit/component tests** and the production build passed.
- `npm run test:api:browser`: **three passed**, including PR #49's USER-permission regression.
- `npm run test:auth:e2e`: **six passed**, including profile updates, logout and session protection on refresh.
- `git diff --check` passed. The existing non-blocking production bundle warning remained, approximately 663 kB / gzip 219 kB.
- Browser tests regenerated the profile desktop screenshot, which was inspected; no layout changes were made.
- Fix commit: see the update history of existing PR #50.

## Follow-up work outside this handoff

1. Ticket list, creation and detail pages, followed by comments, attachments, engineer/Vendor workflows and the management dashboard.
2. Show actions from `available_actions`. After successful Tier 1 escalation, leave the detail page and clear its cache; treat detail 404 as unavailable. These were later ticket-page tasks, not D02 deliverables.
3. Verify account APIs with the team's real Python service/database, especially engineer permissions, Vendor information, CORS and session expiry.
4. Complete business E2E, Docker/AWS/S3 integration and final-report evidence.

The production build had one non-blocking size warning: main JavaScript about 663 kB, gzip about 219 kB, from React, Ant Design and the API/state foundation. The warning threshold was not raised. Route-level splitting can be considered when business pages are added; this was not a version conflict or build failure.

UI references: [Ant Design Form](https://ant.design/components/form/) and [theme configuration](https://ant.design/docs/react/customize-theme/).

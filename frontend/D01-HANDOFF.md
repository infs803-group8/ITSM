# D01 frontend API foundation handoff

## Scope

Work location: `ITSM/frontend` in the team repository, on `feature/WBS-D01-openapi-client`.

D01's implementation changes are confined to the frontend. With the user's authorization, main `6736508` was merged into D01, bringing in the team's existing backend, OpenAPI, `.github` and infrastructure updates. Those files were not independently rewritten, and the older standalone `INFS803/frontend` was not changed. The synchronization was saved as a local merge commit, without a push or PR; the main branch pointer stayed unchanged.

## 2026-09-24: synchronization with main and the latest contract

Starting from D01 `1db9797`, local main `6736508` was merged. That main includes the workflow P1 fixes and updates to B/C's shared TicketDetail assembler. A merge commit preserves both histories; no rebase, force-push or direct commit to main was used.

| Location | Change |
| --- | --- |
| `package.json`, `package-lock.json` | Resolved conflicts in both files; retained D01's verified dependency set, main's shared versions and security overrides; did not upgrade tools again |
| `openapi.config.mjs` | Removed the old `readWrite: false` compatibility option and restored the generator's default read/write handling |
| `src/api/generated/` | Regenerated the SDK, types, type exports and contract fingerprint from main's contract; the token remains a required response field, and login/registration passwords appear in generated Writable request types |
| `src/api/types.ts`, `auth.ts`, `src/mocks/handlers.ts` | Derived input types directly from generated operation `body` types, preserving password fields without handwritten duplicate DTOs |
| `tests/api/contract.test.ts` | Added assertions for a readable, required token and empty actions after escalation, plus login/registration writable-type assertions |
| `tests/api/client.test.ts` | Added a test-only escalation-success → GET 404 case covering empty actions, error details and token retention; this is not a complete engineer Mock |
| `README.md`, this file | Recorded the resolved token issue, removed CI, synchronization results and remaining detail-page requirements |

The two backend contract changes were handled as follows:

1. The backend removed `LoginData.access_token.writeOnly`. The frontend no longer needs to disable read/write splitting globally. Password `writeOnly` annotations are correct, so inputs use SDK-derived aliases in `src/api/types.ts`.
2. `API25Success.available_actions` is now `[]`. The contract fingerprint and a regression assertion were updated. A future Tier 1 detail page must leave the page after successful escalation, clear its old detail cache and refresh the list. A subsequent GET 404 must show an unavailable/access-denied message and return to the list. It must preserve the login session and avoid redirecting every 404 from a global interceptor. D01 verifies only the API layer; page navigation was not implemented at this stage.

Local verification after the merge:

- `npm ci` and the full dependency-tree check passed, with no Node engine or peer-dependency conflicts.
- All 16 shared direct dependencies still matched main. Local Node 22.23.3 and npm 10.9.9 were unchanged.
- `npm run check` passed generation checks for 32 APIs and nine baseline Mocks, TypeScript, **69 unit/component tests** and the production build.
- `npm run test:api:browser`: **2 browser tests passed**.
- `npm audit` and `npm audit --omit=dev`: **0 known findings** in each.
- **403 backend unit/contract tests passed** in the existing isolated Python environment. There was one test-library deprecation warning and no failures.
- Real MySQL, S3, AWS and deployment checks were not run. Mock tests do not establish acceptance of pages against the real backend.

The earlier dependency-alignment and security-fix records below are retained as history. The synchronization results above supersede those earlier branch states.

## 2026-09-24: dependency and local-environment alignment only

At this earlier stage, the user selected dependency alignment without merging all of main into D01. The reference was main `5ff9efb`; backend, OpenAPI and GitHub Actions changes were not synchronized then. This is not the branch state after the later merge.

- `package.json` and `package-lock.json`: shared direct-dependency ranges matched main, and all 16 installed shared versions were checked individually. Main tools were Vite 8.2.2, React plugin 6.1.1, Vitest 5.0.1, jsdom 30.0.1 and jest-dom 7.0.1.
- Retained D01's generator 0.99.0, Ajv, YAML, token/error handling, Mocks and full check scripts. Main's empty API scaffold and pass-with-no-tests configuration were not restored.
- D01's additional `@types/node` dependency changed from 22.10.0 to 22.19.0 for Vite 8 compatibility. This is a development type package, not the Node runtime.
- The system Node installation changed from 22.19.0 to the official 22.23.3 package, including npm 10.9.9. The official installer SHA256 and Windows signature were verified. Other projects using that system path also use this installation.
- Added `.nvmrc` to record the selected Node version and narrowed `engines.node` to the ranges supported by the newer jsdom/Vitest. Windows MSI installation does not require nvm; `.nvmrc` records the team's version and does not download Node itself.
- Updated the README's Node, dependency-reproduction and local-check instructions. In `tests/api/contract.test.ts`, only one test name changed to remove a reference to old CI status; its assertions were unchanged.

Verification at the alignment stage, before the security fixes in the next section:

- `npm ci` passed in the new environment without dependency conflicts or Node engine warnings; `npm ls --depth=0` passed.
- `npm run check` passed: generation consistency for 32 APIs/nine Mocks, TypeScript, 66 unit/component tests and the Vite 8 production build.
- Both `npm run test:api:browser` tests passed. The existing MSW worker matched the installed MSW version.
- The API contract and generated source were unchanged. Regeneration was deferred until main's contract changes were actually merged.
- Main's original lockfile had zero `npm audit` findings. D01's `npm audit --omit=dev` also had zero findings.
- D01's full development-dependency audit then reported six package-level findings: four high and two moderate. They came from js-yaml 4.2.0 in the generator chain and D01's pinned Ajv 8.17.1 and yaml 2.8.1. The four high counts included propagation of the same js-yaml issue through dependent packages, not four separate browser-runtime vulnerabilities. Ajv's advisory-related `$data` option was disabled, but dependency updates were still needed.
- No `npm audit fix` or generator downgrade was used during alignment. The findings were addressed separately below. Do not run the generator on unreviewed external YAML.

After that installation, reopening the VS Code terminal and running `node -v` and `npm -v` was expected to show `v22.23.3` and `10.9.9`. Development still uses `npm run dev`; dependency restoration uses `npm ci`.

The alignment and security fixes were later saved in D01 commit `1db9797`. The local Node installation is not part of the Git commit.

## 2026-09-24: development-dependency security fixes (historical)

This stage changed only the frontend, without merging main or changing the backend or OpenAPI:

| File | Fix |
| --- | --- |
| `package.json` | Ajv 8.17.1 → 8.20.0; yaml 2.8.1 → 2.9.1; a js-yaml 4.3.2 override scoped to `@hey-api/json-schema-ref-parser@1.4.4` |
| `package-lock.json` | Recorded the three fixed versions, download locations and integrity data for reproduction with `npm ci` |
| `README.md`, this file | Explained the override, its removal conditions and verification results |

The generator remains pinned to `@hey-api/openapi-ts@0.99.0`. At the time of the check, its latest release and the latest parser still pinned js-yaml 4.2.0, which had an advisory. A narrow override installed the fixed dependency without upgrading or downgrading the generator. Once the upstream parser includes the fix, review the version-scoped rule, remove it if no longer needed and repeat the checks below.

Verification after the fix:

- `npm ci` passed; all 248 locally installed package versions matched the lockfile.
- `npm ls --all --json` passed with no missing or invalid dependencies. All 16 direct dependencies shared with main still matched.
- Full `npm audit`: **0 known findings**, down from six; `npm audit --omit=dev` also reported zero. These results reflect the advisory database at that time and do not remove the need for future audits.
- `npm run check` passed: generation consistency for 32 APIs/nine Mocks, TypeScript, 66 unit/component tests and the production build.
- `npm run test:api:browser`: 2 browser tests passed.
- Generated API source, generated Mocks and the contract were unchanged. `npm audit fix --force` was not used.

These changes were later saved in `1db9797`. Its larger lockfile difference from old D01 also includes tool-version alignment, not just the three security fixes.

## Implementation map

| Location, relative to this frontend | Content |
| --- | --- |
| `package.json`, `package-lock.json` | Pinned generator 0.99.0; installed dependencies; added generation, check and browser-test commands; removed pass-with-no-tests behavior |
| `openapi.config.mjs`, `scripts/generate-api.mjs` | Read-only use of the repository OpenAPI contract, repeatable generation, stale-output checks and normalized Windows/Linux line endings |
| `src/api/generated/` | 32 API functions, request/response types, client runtime and contract fingerprint at the D01 stage; replaced the empty `client.ts` with standard generator outputs such as `client.gen.ts` |
| `src/api/types.ts` | Re-exported generated types instead of maintaining a simplified handwritten error contract |
| `src/api/config.ts`, `httpClient.ts` | API URL, timeout, Bearer token, request ID and 401 session-expiry notification |
| `src/api/tokenStorage.ts`, `auth.ts` | In-memory token, token storage on login and clearing on logout; no invented refresh/logout endpoints |
| `src/api/errorHandler.ts`, `src/components/ApiErrorNotice.tsx` | Shared error object and reusable error component with request ID and retry support |
| `src/mocks/fixtures.generated.json` | Nine baseline Mock examples and request-validation rules extracted from the contract; generated, not hand-edited |
| `src/mocks/handlers.ts`, `state.ts`, `validation.ts` | USER registration, login, profile, reference data and ticket creation/reading; field, pagination, permission and error validation |
| `src/main.tsx`, `.env.example`, `public/mockServiceWorker.js` | Local Mock switch; wait for Mock readiness before loading pages; prevent Mock activation in production |
| `tests/api/`, `tests/component/ApiErrorNotice.test.tsx`, `vite.config.ts` | Contract, client, error-handling and component tests with substantive assertions |
| `tests/api-browser/`, `playwright.api.config.ts`, `tsconfig.json` | Chromium Mock smoke tests on a separate port and configuration type checks |
| `README.md`, this file | Run instructions, usage examples, scope limits and manual pre-PR checks |

## Next implementation steps

1. Continue in the team repository's frontend. Keep the old prototype for reference instead of copying it over this repository.
2. Add page/feature code under `src/features`, `src/components` and related locations. Call `src/api/generated/sdk.gen.ts` and use its generated types.
3. Connect the login page and authentication provider to `login()`, `logout()` and `onUnauthorized()`. Clear user/query state and return to login on session expiry.
4. Connect ticket list, creation and detail pages, adding real interactions and assertions to their tests. The baseline Mock only supports USER; engineer, manager and Vendor scenarios need later expansion.
5. Disable Mocks and integrate with the real Python backend when its endpoints are ready. Passing Mock tests does not establish backend integration.

## Scope boundaries at the D01 stage

- D01 delivered the API foundation, not complete login and ticket-page behavior. The team's original placeholder homepage remained; the old prototype's yellow/black theme was not migrated here.
- The SDK covered 32 APIs. The baseline Mock covered only API-01, 08–12 and 15–17, nine operations in total. Other requests failed locally instead of silently reaching the backend.
- Mock registration supports additional USER accounts and ticket-isolation checks. Accounts/passwords are in-memory development data, not production authentication.
- Tokens exist only in memory; refreshing requires login again. There is no real JWT verification, refresh token or server-side logout.
- Ticket creation uses the fixed no-suitable-engineer → UNASSIGNED path. Backend assignment, SLA and scheduling logic were not reimplemented.
- Four existing business Playwright files remained skipped placeholders. The two new browser tests covered the API foundation, not complete workflows for four roles.
- Real backend, S3 and Docker deployment checks had not been performed.

## Resolved token-contract issue

The old contract marked `LoginData.access_token` both required in a response and `writeOnly`. Main fixed the annotation, and D01 restored default generation and regenerated. Regression checks cover token readability, password request fields and operation types; the old issue no longer awaited B's confirmation.

## Local verification and manual PR process

Local results from 2026-09-09:

- Generated-file consistency, TypeScript and the production build passed.
- 66 Vitest tests passed: 36 contract, 15 client/Mock, 13 error/switch and two component tests.
- Two Chromium browser Mock smoke tests passed, including cold-cache startup.
- `git diff --check` passed. All changed and added paths were under the team's `frontend/`.
- Production JavaScript contained no new Mock accounts, fake-token markers or Mock startup module. The presence of the static MSW worker does not mean production enables it.

Run inside the `frontend` directory containing this file:

```powershell
npm ci
npm run check
npm run test:api:browser
```

For development, copy `.env.example` to `.env` only if `.env` is absent; otherwise inspect and preserve its settings. Run `npm run dev` and keep the server running to view the site. Tests normally exit when complete.

At this handoff, synchronization was saved as a local merge commit. Before preparing a PR, verify repository `ITSM`, branch `feature/WBS-D01-openapi-client` and base `main`. D01's implementation difference from main should be frontend-only. Backend changes inherited through the merge history are expected and are not D01's independent implementation changes. Commit generated source and `package-lock.json`; exclude `node_modules`, `dist`, `.env` and test reports. Pushing and PR creation were left for separate user authorization; no direct main commit was made.

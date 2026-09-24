# Frontend

React + TypeScript + Vite application owned by member D. The source of truth for HTTP requests and responses is `docs/api/openapi.yaml`.

## Local development

Run the following **inside the team's `ITSM/frontend` directory**, not the older standalone prototype. The selected local runtime is **Node.js 22.23.3** (recorded in `.nvmrc`). With jsdom 30, Node 22 must be **22.22.2 or newer**; the old Node 22.19.0 installation is not supported by that dependency. `engines.node` records the supported Node release ranges.

The shared dependency ranges match main at `5ff9efb`: Vite 8.2.2, React plugin 6.1.1, Vitest 5.0.1, jsdom 30.0.1 and jest-dom 7.0.1 are the lockfile baseline. D01 keeps its additional generator, validation packages and test scripts. `@types/node` is separately pinned to 22.19.0 to satisfy Vite 8's type-package requirement; its version is not the installed Node runtime version.

Use `npm ci` to reproduce the committed lockfile. The `^` ranges inherited from main are not an instruction to upgrade dependencies on every checkout. Review intentional dependency upgrades separately. This version-alignment change does **not** merge main's backend, API contract or workflow changes into D01.

```powershell
npm ci
# Preserve existing local settings.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`. Keep that terminal running. `npm run test:unit` runs tests and exits; it does **not** start the website.

This branch supplies the API foundation. The home page is still the team's original scaffold; the older prototype's UI has not been copied in. Login/ticket pages are separate work.

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
- Output: `src/api/generated/` (all 32 operation functions, types, bundled Axios runtime, contract hash) and `src/mocks/fixtures.generated.json` (nine baseline examples and request-validation schemas).
- Commit the generated source and `public/mockServiceWorker.js`. Do not edit generated files manually. `api:generate` replaces stale generated files; `api:check` regenerates into a temporary directory and checks differences without changing the working files.
- Line endings are normalized for Windows/Linux reproducibility. The contract-hash test detects source changes whenever the unit suite runs. Full generated-file drift is checked by `npm run api:check`.
- Run generation from the full repository. The production Docker build uses the committed generated files; it does not need the parent `docs` directory in its frontend-only build context.

**Known contract annotation:** v1.1 `LoginData.access_token` is both required in a login response and marked `writeOnly`. The generator's read/write splitting is explicitly disabled so the required token is retained. This preserves the declared schema fields without rewriting the team contract. Revisit this setting with member B when the annotation is corrected. A type test protects the token and password fields.

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

Tokens live **only in memory** (`tokenStorage.ts`); page reload requires sign-in again. A 401 for the current bearer token clears it and notifies `onUnauthorized`. The future authentication provider must subscribe to clear user/query state and navigate to login. Failed public logins, 403 responses and stale requests from an older session do not clear a newer token. `logout()` only clears the local token: the contract has no logout or refresh endpoint. Do not invent automatic refresh/retry of writes.

For future S3 uploads, use the returned presigned URL and signed headers with a separate request (for example native `fetch`); never send the API bearer token to S3.

## Mock mode and its limits

In your local `.env`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_USE_MOCKS=true
```

Restart Vite after changing environment variables. The worker starts before React renders. It is enabled only in development with the explicit flag; production never starts or imports the Mock modules. If worker setup fails, the app shows a startup error rather than silently using the real backend.

The baseline supports **USER only**:

| API | Local behavior |
| --- | --- |
| 01 | Contract-shaped health response |
| 08–09 | Register, duplicate email, login and invalid credentials |
| 10–11 | Read/update own profile; reject USER availability changes |
| 12 | Contract reference data |
| 15 | Create own ticket using the deterministic UNASSIGNED/no-eligible-engineer branch |
| 16–17 | Own ticket list/detail, filters, sorting, pagination, and scope-safe 404 |

Fake demo account: `user@example.com` / `MockPass123!`. This is **not** a real backend account or a real JWT. Accounts, tokens and tickets reset on page reload. Request bodies and query parameters are validated against generated contract schemas; additional JSON fields, invalid enum casing and invalid pagination are rejected. The USER Mock strips engineer-only actions from the example ticket.

The other operations intentionally fail locally in Mock mode; they do not fall through to a real server. Attachments/S3, dashboards, comments, engineering/vendor workflows, auto-assignment, SLA timers, password-policy details beyond the schema and production authentication are **not simulated**. Some original success examples represent different roles: example-schema tests are not evidence of full authorization or workflow correctness.

Set `VITE_USE_MOCKS=false` to call the Python backend. Confirm backend routes, credentials and CORS are ready. Production defaults to same-origin `/api/v1`; the team Dockerfile also supplies that value. Never store AWS keys, passwords, bearer tokens or other secrets in `VITE_*` variables: they are public browser configuration.

`public/mockServiceWorker.js` is installed/generated by MSW and must match the locked dependency. If updating MSW, run `npm run mocks:worker` again. It may be copied as a static build asset, but is never registered by the production app.

## Checks before your manual PR

The latest main removed GitHub Actions checks. D01 has not merged that commit in this dependency-only update, so do not rely on the older workflow files still visible on this branch as evidence that the team's PR checks are active. Run these checks locally before your manual PR.

```powershell
npm run check
npm run test:api:browser
```

`check` verifies generated-file drift, TypeScript, Vitest tests, and the production build. It no longer permits a false green result with zero unit tests. The browser check launches its own development server on `127.0.0.1:5181` with Mock enabled and shuts it down afterward. If Chromium is missing, install it once with `npx playwright install chromium`.

- `tests/api/contract.test.ts`: all 32 success examples, generation hash, nine fixtures and important generated types.
- `tests/api/client.test.ts`: actual generated SDK → Axios → MSW requests, token behavior, validation, errors, query parameters and USER isolation.
- `tests/api/errorHandler.test.ts`: HTTP, network, timeout, cancellation and production Mock guard.
- `tests/component/ApiErrorNotice.test.tsx`: accessible message/request ID, retry click, no raw details.
- `tests/api-browser/api-foundation.spec.ts`: two real Chromium/Service Worker checks; not full user-page flows.

The four original `tests/e2e` business scenarios remain skipped placeholders. `npm run test:e2e` is not a completed business-flow acceptance suite yet. No backend integration, Docker deployment or S3 upload is claimed by these Mock tests.

See `D01-HANDOFF.md` for the Chinese change summary and next development steps.

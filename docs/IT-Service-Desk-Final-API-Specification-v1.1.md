# IT Service Desk — Final API Development Specification

> **Team member reference:** Throughout this document, A = BIN LIN; B = Yujuan Gao; C = Andy Wen; D = Yiguang Sun.

## Unified FastAPI / OpenAPI Interface Contract

**Version**: v1.1  
**Date**: 2026-09-01  
**Baseline**: `IT-Service-Desk-Unified-Project-Baseline-v6.0.md`  
**API Count**: 32 (A (BIN LIN)=7, B (Yujuan Gao)=13, C (Andy Wen)=12)  
**Baseline Contract Snapshot**: `IT-Service-Desk-OpenAPI-v1.1.yaml`

**Status**: Ready for FastAPI router, Pydantic model, Swagger, frontend mock and TypeScript client development

> This document freezes all public HTTP contracts. Owners may implement SQLAlchemy tables and internal services/repositories as needed, but must not change the paths, methods, fields, role scopes, state semantics or error codes defined here. Version 1.1 specifies that required response fields must always be present, returning JSON `null` when they have no value or are hidden from the current role, and provides frontend mock examples for all 32 operations. Any change must update this document, the OpenAPI YAML, examples, tests, frontend types and the Trello decision together.

---

> **Repository locations — checked 2026-10-07 against `main` [`379bb53`](https://github.com/infs803-group8/ITSM/tree/379bb531504e78b2b293564b070f8af33b85449c):** This file and the retained OpenAPI snapshot are directly under `docs/`. They describe the original 32-operation baseline. Current integration, client generation and contract tests use the 33-operation [implementation YAML](../backend/contracts/openapi.yaml) and [JSON counterpart](../backend/contracts/openapi.json), which also include API-33 for vendor request history. This directory update does not rewrite the baseline endpoint definitions below.

| Artifact | Current repository path |
|---|---|
| This baseline specification | `docs/IT-Service-Desk-Final-API-Specification-v1.1.md` |
| Retained baseline snapshot | `docs/IT-Service-Desk-OpenAPI-v1.1.yaml` |
| Implementation contract | `backend/contracts/openapi.yaml`, `backend/contracts/openapi.json` |
| Backend JSON exporter | `backend/scripts/export_openapi.py` |
| Frontend generator configuration and script | `frontend/openapi.config.mjs`, `frontend/scripts/generate-api.mjs` |
| Generated SDK, types and contract manifest | `frontend/src/api/generated/` |
| Backend contract tests | `backend/tests/contract/` |
| Frontend contract tests and helpers | `frontend/tests/api/` |

## 1. FastAPI Implementation Standards

```python
@router.post(
    "/tickets",
    response_model=TicketDetailResponse,
    status_code=status.HTTP_201_CREATED,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def create_ticket(
    payload: TicketCreateRequest,
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> TicketDetailResponse:
    ...
```

Common requirements:

- Pydantic v2 request models use `ConfigDict(extra="forbid")` to reject undeclared fields.
- A global handler must convert FastAPI `RequestValidationError` into the `ErrorResponse` defined here, rather than returning FastAPI's default `detail` array.
- Routers handle only HTTP, dependencies and serialisation; services handle permissions, transactions and state transitions; repositories handle database queries.
- All writes must reread and validate data within a transaction; workflow writes and TicketEvent must share the same transaction.
- Responses must not use `response_model_exclude_none=True` to inconsistently remove required fields. Fields listed in OpenAPI `required` must always be present; return JSON `null` when no business value exists or the field is hidden from the current role.

## 2. Public URLs, Headers and Data Formats

| Item | Rule |
|---|---|
| Local Base URL | `http://localhost:8000/api/v1` |
| Final Base URL | `https://<cloudfront-domain>/api/v1` |
| Swagger | `/api/docs` |
| OpenAPI | `/api/openapi.json` |
| Authentication | `Authorization: Bearer <access_token>`, except for API-01/08/09 |
| Request ID | The client may send `X-Request-ID: <uuid>`; otherwise the backend generates it |
| Response Header | Every response returns `X-Request-ID` |
| Content Type | Backend JSON uses `application/json`; S3 PUT uses the headers returned by Presign |
| Time | UTC ISO 8601, e.g. `2026-09-15T03:20:15Z` |
| IDs | Ticket/User/Comment/Event/Vendor use `integer/int64`; Attachment/Upload use UUIDs |
| Pagination | `page=1`, `page_size=20`, maximum 100 |
| Unknown fields | Request bodies reject extra fields |
| Required Response Field | Always return a stable key; use JSON `null` when no value exists or the field is hidden from the current role. Do not alternate between `null` and omission |
| Frontend Example | Every operation in OpenAPI v1.1 includes at least one success example; examples support mock/page development and do not replace the schema |
| Local CORS | The backend allows `http://localhost:5173` by default; the final deployment uses same-origin `/api/*` access through CloudFront |

Success envelope:

```json
{ "data": {} }
```

List envelope:

```json
{ "data": [], "meta": { "page": 1, "page_size": 20, "total": 0, "total_pages": 0 } }
```

Error envelope:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The requested resource was not found.",
    "details": {},
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

### 2.1 Frontend Handover and Mock Usage Rules

Frontend member D (Yiguang Sun) does not need to wait for backend completion before starting development. The formal handover package consists of this document and `IT-Service-Desk-OpenAPI-v1.1.yaml`. Use them in the following order:

1. Generate TypeScript types/API clients from OpenAPI v1.1; do not copy fields manually.
2. Use each operation's success example to create MSW, Prism or local mock responses.
3. Use `Role`, `status`, `display_status` and `available_actions` to control pages and buttons; hiding frontend buttons does not replace backend permission checks.
4. Always read required fields using their fixed keys. Values may be `null`, but do not assume that the backend will omit the key.
5. Attachments must follow API-02 → browser raw PUT to S3 → API-03. Do not treat the S3 PUT as a backend JSON API.
6. Once the backend is running, replace only the base URL; do not redefine TypeScript interfaces.

Examples illustrate typical success scenarios and drive mocks; they do not change schema constraints. Frontend tests must still cover empty lists, `null`, 401, 403, 404, 409, 422 and 503 responses.

## 3. Shared Enums

### Role

```text
USER
ENGINEER_TIER1
ENGINEER_TIER2
EXTERNAL_VENDOR
SERVICE_DESK_MANAGER
```

### Category

```text
NETWORK
HARDWARE
SOFTWARE
ACCOUNT
OTHER
```

### Priority

```text
LOW
MEDIUM
HIGH
URGENT
```

### TicketStatus

```text
UNASSIGNED
ASSIGNED
IN_PROGRESS
PENDING_USER
PENDING_VENDOR
RESOLVED
REOPENED
CLOSED
```

### SlaStatus

```text
ON_TRACK
AT_RISK
OVERDUE
PAUSED
MET
```

### PendingUserReason

```text
INFORMATION_REQUIRED
RESOLUTION_CONFIRMATION
```

### AttachmentVisibility

```text
USER_VISIBLE
INTERNAL_ONLY
VENDOR_SHARED
```

### CommentVisibility

```text
USER_VISIBLE
INTERNAL_ONLY
```

### EventScope

```text
USER_VISIBLE
INTERNAL_ONLY
VENDOR_SCOPE
```

### EventType

```text
TICKET_CREATED
AUTO_ASSIGNED
ASSIGNED
REASSIGNED
HANDLING_STARTED
COMMENT_ADDED
SLA_CYCLE_STARTED
SLA_PAUSED
SLA_AT_RISK
SLA_OVERDUE
SLA_MET
USER_INFO_REQUESTED
USER_RESUMED
VENDOR_REQUESTED
VENDOR_RESPONDED
VENDOR_CANCELLED
RESOLUTION_SUBMITTED
RESOLUTION_CONFIRMED
AUTO_RESOLVED_NO_USER_RESPONSE
RESOLUTION_CONFIRMATION_TIMEOUT
TICKET_REOPENED
TICKET_CLOSED_MANUAL
TICKET_CLOSED_AUTO
ATTACHMENT_ADDED
```

### VendorRequestStatus

```text
ACTIVE
RESPONDED
CANCELLED
```

### AvailableAction

```text
EDIT
COMMENT
UPLOAD_ATTACHMENT
ASSIGN
START
REQUEST_USER_INFO
RESUME
ESCALATE
REQUEST_VENDOR
VENDOR_RESPONSE
RESOLVE
CONFIRM_RESOLUTION
REOPEN
CLOSE
```

### ErrorCode

```text
INVALID_REQUEST
VALIDATION_ERROR
AUTHENTICATION_REQUIRED
INVALID_ACCESS_TOKEN
EMAIL_ALREADY_REGISTERED
INVALID_CREDENTIALS
PASSWORD_POLICY_VIOLATION
DATA_SCOPE_DENIED
RESOURCE_NOT_FOUND
INVALID_STATUS_TRANSITION
ASSIGNEE_NOT_ELIGIBLE
USER_RESPONSE_WINDOW_EXPIRED
USE_RESUME_ACTION
USE_CONFIRM_OR_RESUME_ACTION
USE_VENDOR_RESPONSE_ACTION
ACTIVE_VENDOR_REQUEST_EXISTS
NO_ACTIVE_VENDOR_REQUEST
UPLOAD_NOT_READY
UPLOAD_SESSION_EXPIRED
TICKET_CLOSED
ATTACHMENT_TOO_LARGE
UNSUPPORTED_ATTACHMENT_TYPE
UPLOAD_INTEGRITY_MISMATCH
CLOSE_ACKNOWLEDGEMENT_REQUIRED
STORAGE_UNAVAILABLE
SERVICE_UNAVAILABLE
```

## 4. API Overview

| ID | Owner | Method | Path | Summary |
|---:|---|---|---|---|
| API-01 | A (BIN LIN) | GET | `/health` | Backend health check |
| API-02 | A (BIN LIN) | POST | `/tickets/{id}/attachments/presign` | Create attachment upload session |
| API-03 | A (BIN LIN) | POST | `/tickets/{id}/attachments/complete` | Complete attachment upload |
| API-04 | A (BIN LIN) | GET | `/tickets/{id}/attachments` | List ticket attachments |
| API-05 | A (BIN LIN) | GET | `/tickets/{id}/attachments/{attachment_id}/download` | Generate attachment download URL |
| API-06 | A (BIN LIN) | GET | `/dashboard/summary` | Get dashboard summary |
| API-07 | A (BIN LIN) | GET | `/dashboard/overdue-tickets` | List current/history overdue |
| API-08 | B (Yujuan Gao) | POST | `/auth/register` | Register USER |
| API-09 | B (Yujuan Gao) | POST | `/auth/login` | Login |
| API-10 | B (Yujuan Gao) | GET | `/users/me` | Get profile |
| API-11 | B (Yujuan Gao) | PATCH | `/users/me` | Update profile |
| API-12 | B (Yujuan Gao) | GET | `/reference-data` | Get reference data |
| API-13 | B (Yujuan Gao) | GET | `/users/assignees` | List engineers |
| API-14 | B (Yujuan Gao) | GET | `/vendors` | List vendors |
| API-15 | B (Yujuan Gao) | POST | `/tickets` | Create ticket |
| API-16 | B (Yujuan Gao) | GET | `/tickets` | List tickets |
| API-17 | B (Yujuan Gao) | GET | `/tickets/{id}` | Get ticket detail |
| API-18 | B (Yujuan Gao) | PATCH | `/tickets/{id}` | Update ticket core |
| API-19 | B (Yujuan Gao) | GET | `/tickets/{id}/comments` | List comments |
| API-20 | B (Yujuan Gao) | POST | `/tickets/{id}/comments` | Create ordinary comment |
| API-21 | C (Andy Wen) | POST | `/tickets/{id}/assign` | Assign/reassign |
| API-22 | C (Andy Wen) | POST | `/tickets/{id}/start` | Start handling |
| API-23 | C (Andy Wen) | POST | `/tickets/{id}/request-user-info` | Request user info |
| API-24 | C (Andy Wen) | POST | `/tickets/{id}/resume` | Resume ticket |
| API-25 | C (Andy Wen) | POST | `/tickets/{id}/escalate` | Escalate to Tier 2 |
| API-26 | C (Andy Wen) | POST | `/tickets/{id}/vendor-requests` | Request vendor |
| API-27 | C (Andy Wen) | POST | `/tickets/{id}/vendor-response` | Vendor response |
| API-28 | C (Andy Wen) | POST | `/tickets/{id}/resolve` | Submit resolution |
| API-29 | C (Andy Wen) | POST | `/tickets/{id}/confirm-resolution` | Confirm resolution |
| API-30 | C (Andy Wen) | POST | `/tickets/{id}/reopen` | Reopen ticket |
| API-31 | C (Andy Wen) | POST | `/tickets/{id}/close` | Manual close |
| API-32 | C (Andy Wen) | GET | `/tickets/{id}/events` | List audit events |

---

## 5. Detailed Contracts for the 32 APIs

### API-01 — GET `/health`

**Purpose and Functionality**

- **Use case**: A team member, lecturer or operator wants to check whether the backend is available, for example after deployment or when frontend login fails.
- **User action**: Open `/health` in a browser or testing tool. No login or input is required.
- **Visible result**: When healthy, the service returns `200`, its version and the current time; if the service or database is unavailable, it returns `503`. This helps the frontend developer identify a backend environment issue rather than a problem in the page code.
- **User guidance**: This endpoint confirms only basic backend and database connectivity. It does not mean that all business functions, such as login and attachment uploads, have passed testing.

- **Purpose**: Backend health check. Checks backend version and database readiness; used by ALB and CI/CD smoke tests.
- **Owner**: Member A (BIN LIN)
- **Access**: Public
- **Success**: HTTP 200, Response Model: `HealthResponse`
- **Business Error Codes**: SERVICE_UNAVAILABLE

**Path / Query Parameters**

None.

**Request Body**: None.

**Response Body**: See `HealthResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-02 — POST `/tickets/{id}/attachments/presign`

**Purpose and Functionality**

- **Use case**: A user, engineer or vendor is adding a screenshot, log or other supporting file on the ticket detail page.
- **User action**: Select a file that meets the size and format requirements, choose an allowed visibility level and click "Upload". The frontend calls this endpoint automatically; the user does not interact with S3 or enter a storage address.
- **Visible result**: Once the system approves the upload, the page starts displaying upload progress. If the file type, size, permissions or vendor scope is invalid, an error appears before the actual upload begins.
- **User guidance**: This endpoint only obtains temporary permission for one upload; the file has not yet been formally added to the ticket's attachment list. The permission expires after approximately 15 minutes; select the file again or retry after expiry.

- **Purpose**: Create attachment upload session. Creates PENDING upload session and S3 Presigned PUT; does not receive bytes.
- **Owner**: Member A (BIN LIN)
- **Access**: Scoped authenticated role
- **Success**: HTTP 201, Response Model: `PresignResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, TICKET_CLOSED, NO_ACTIVE_VENDOR_REQUEST, ATTACHMENT_TOO_LARGE, UNSUPPORTED_ATTACHMENT_TYPE

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body: `PresignRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `file_name` | string | Yes | minLength: 1; maxLength: 255 | Base file name. |
| `content_type` | string | Yes | enum: image/png, image/jpeg, application/pdf, text/plain | Expected MIME. |
| `size_bytes` | integer | Yes | min: 1; max: 10485760 | Expected bytes. |
| `visibility` | AttachmentVisibility | Yes |  | Attachment visibility. |

Request example:

```json
{
  "file_name": "router-error.log",
  "content_type": "image/png",
  "size_bytes": 28431,
  "visibility": "USER_VISIBLE"
}
```

**Response Body**: See `PresignResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-03 — POST `/tickets/{id}/attachments/complete`

**Purpose and Functionality**

- **Use case**: The attachment file has finished transferring and must now be formally registered against the current ticket.
- **User action**: No further click is needed; the frontend automatically calls this endpoint to confirm completion when upload progress reaches 100%.
- **Visible result**: Once confirmation succeeds, the file appears in the ticket's attachment list and can be viewed or downloaded according to permissions. If cloud storage has not yet detected the file, the page can retry automatically without creating duplicate attachments.
- **User guidance**: The attachment is fully added only after this endpoint succeeds. If the page shows "Upload complete, but confirmation failed", click Retry; the file does not need to be uploaded again.

- **Purpose**: Complete attachment upload. HeadObject verification and idempotent Attachment/Event creation; body accepts upload_id only.
- **Owner**: Member A (BIN LIN)
- **Access**: Presign creator
- **Success**: HTTP 200, Response Model: `AttachmentResponse`
- **Business Error Codes**: RESOURCE_NOT_FOUND, UPLOAD_NOT_READY, UPLOAD_SESSION_EXPIRED, TICKET_CLOSED, NO_ACTIVE_VENDOR_REQUEST, UPLOAD_INTEGRITY_MISMATCH

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body: `CompleteUploadRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `upload_id` | string(uuid) | Yes |  | Only accepted field. |

Request example:

```json
{
  "upload_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response Body**: See `AttachmentResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-04 — GET `/tickets/{id}/attachments`

**Purpose and Functionality**

- **Use case**: A user opens the "Attachments" section of a ticket detail page to see which files have been uploaded.
- **User action**: Open the attachment section, change pages or refresh the list after uploading a new attachment.
- **Visible result**: The page shows filenames, types, sizes, uploaders and upload times for files the current user may access. Ordinary users, internal engineers and vendors may see different attachments.
- **User guidance**: An attachment missing from the list usually means its visibility does not include the current user. This endpoint lists file information only; permissions are checked again when downloading.

- **Purpose**: List ticket attachments. Role/visibility/vendor-filtered attachment metadata.
- **Owner**: Member A (BIN LIN)
- **Access**: Scoped authenticated role
- **Success**: HTTP 200, Response Model: `AttachmentListResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |
| `page` | query | integer | No | default=1; min: 1 | Page number. |
| `page_size` | query | integer | No | default=20; min: 1; max: 100 | Page size. |
| `visibility` | query | AttachmentVisibility | No |  | Visibility filter. |

**Request Body**: None.

**Response Body**: See `AttachmentListResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-05 — GET `/tickets/{id}/attachments/{attachment_id}/download`

**Purpose and Functionality**

- **Use case**: A user finds a screenshot, log or document in the attachment list and wants to open or save it.
- **User action**: Click "Download" or "View" beside the attachment.
- **Visible result**: After authorisation, the browser starts downloading or opening the file. The page displays an appropriate message if access is denied, the attachment does not exist or the temporary link has expired.
- **User guidance**: The download URL is valid for only about five minutes and should not be bookmarked for long-term use or forwarded. After expiry, return to the ticket page and click Download again to obtain a new URL.

- **Purpose**: Generate attachment download URL. Rechecks access and returns five-minute opaque Presigned GET.
- **Owner**: Member A (BIN LIN)
- **Access**: Scoped authenticated role
- **Success**: HTTP 200, Response Model: `DownloadResponse`
- **Business Error Codes**: RESOURCE_NOT_FOUND, STORAGE_UNAVAILABLE

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |
| `attachment_id` | path | string(uuid) | Yes |  | Attachment UUID. |

**Request Body**: None.

**Response Body**: See `DownloadResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-06 — GET `/dashboard/summary`

**Purpose and Functionality**

- **Use case**: A manager or engineer checks the dashboard after login to quickly see how many tickets need attention.
- **User action**: Open or refresh the dashboard; no manual ticket selection is required.
- **Visible result**: Managers see service-desk-wide ticket totals, counts by state, at-risk counts and overdue counts. Engineers see only their own assigned workload and risk alerts.
- **User guidance**: These cards show aggregate figures rather than complete ticket details. Click a card to open the ticket or overdue list for details.

- **Purpose**: Get dashboard summary. GLOBAL for Manager; MY_ASSIGNED for Tier 1/Tier 2.
- **Owner**: Member A (BIN LIN)
- **Access**: ENGINEER_TIER1, ENGINEER_TIER2, SERVICE_DESK_MANAGER
- **Success**: HTTP 200, Response Model: `DashboardSummaryResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, SERVICE_UNAVAILABLE

**Path / Query Parameters**

None.

**Request Body**: None.

**Response Body**: See `DashboardSummaryResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-07 — GET `/dashboard/overdue-tickets`

**Purpose and Functionality**

- **Use case**: A manager or engineer sees overdue tickets on the dashboard and wants to identify them and check how long they have been overdue.
- **User action**: Click the "Overdue" card, switch between current and historical overdue views, and optionally filter by category or priority.
- **Visible result**: Current mode lists unfinished tickets that have exceeded their SLA; history mode lists past overdue records for review and assignment demonstrations.
- **User guidance**: This page only helps locate and analyse overdue tickets. It does not automatically reassign tickets or change their state; open a record's detail page to take further action.

- **Purpose**: List current/history overdue. Current active overdue cycles or SLA_OVERDUE event history.
- **Owner**: Member A (BIN LIN)
- **Access**: ENGINEER_TIER1, ENGINEER_TIER2, SERVICE_DESK_MANAGER
- **Success**: HTTP 200, Response Model: `OverdueListResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, VALIDATION_ERROR

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `mode` | query | string | No | enum: current, history | View mode. |
| `page` | query | integer | No | default=1; min: 1 | Page number. |
| `page_size` | query | integer | No | default=20; min: 1; max: 100 | Page size. |
| `category` | query | Category | No |  | Category filter. |
| `priority` | query | Priority | No |  | Priority filter. |

**Request Body**: None.

**Response Body**: See `OverdueListResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-08 — POST `/auth/register`

**Purpose and Functionality**

- **Use case**: An ordinary employee without an account needs to report an IT incident or submit a service request.
- **User action**: Enter a name, email address and compliant password on the registration page, then click "Register".
- **Visible result**: If the information is valid and the email is unused, the system creates an ordinary user account. Duplicate emails, invalid formats or non-compliant passwords produce clear correction messages.
- **User guidance**: Self-registration creates requester accounts only. Engineer, manager and vendor accounts must be prepared through the project; roles cannot be selected on the registration page.

- **Purpose**: Register USER. Creates requester USER only.
- **Owner**: Member B (Yujuan Gao)
- **Access**: Public
- **Success**: HTTP 201, Response Model: `UserResponse`
- **Business Error Codes**: EMAIL_ALREADY_REGISTERED, PASSWORD_POLICY_VIOLATION, VALIDATION_ERROR

**Path / Query Parameters**

None.

**Request Body: `RegisterRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `email` | string(email) | Yes | maxLength: 254 | Unique email. |
| `password` | string(password) | Yes | minLength: 8; maxLength: 128 | Password; write-only. |
| `display_name` | string | Yes | minLength: 1; maxLength: 100 | Display name. |

Request example:

```json
{
  "email": "user@example.com",
  "password": "ExamplePass123!",
  "display_name": "Example User"
}
```

**Response Body**: See `UserResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-09 — POST `/auth/login`

**Purpose and Functionality**

- **Use case**: An ordinary user, Tier 1 engineer, Tier 2 engineer, manager or vendor wants to enter the system to perform their work.
- **User action**: Enter an email address and password on the login page, then click "Log in".
- **Visible result**: Successful authentication opens the home page for the user's role. Failed authentication shows the generic message "Incorrect email or password", allowing the user to check and retry.
- **User guidance**: Login sessions expire and require a new login. To avoid disclosing account information, the system does not reveal whether the email is unknown or the password is incorrect.

- **Purpose**: Login. Returns JWT and current profile.
- **Owner**: Member B (Yujuan Gao)
- **Access**: Public
- **Success**: HTTP 200, Response Model: `LoginResponse`
- **Business Error Codes**: INVALID_CREDENTIALS, VALIDATION_ERROR

**Path / Query Parameters**

None.

**Request Body: `LoginRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `email` | string(email) | Yes |  | Registered email. |
| `password` | string(password) | Yes | minLength: 1; maxLength: 128 | Password. |

Request example:

```json
{
  "email": "user@example.com",
  "password": "ExamplePass123!"
}
```

**Response Body**: See `LoginResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-10 — GET `/users/me`

**Purpose and Functionality**

- **Use case**: A user has just logged in or refreshed the page, and the system must identify the current user and determine which menus and functions to show.
- **User action**: No explicit action is needed; the frontend automatically loads the profile when the user enters the system.
- **Visible result**: The top-right corner shows the user's name and role, and only authorised pages are displayed. Engineers also see their availability status; vendors see their organisation.
- **User guidance**: This endpoint shows only the current user's basic profile. It cannot be used to view other people's personal or password information.

- **Purpose**: Get profile. No password hash/internal scheduling data.
- **Owner**: Member B (Yujuan Gao)
- **Access**: Authenticated
- **Success**: HTTP 200, Response Model: `UserResponse`
- **Business Error Codes**: AUTHENTICATION_REQUIRED, INVALID_ACCESS_TOKEN

**Path / Query Parameters**

None.

**Request Body**: None.

**Response Body**: See `UserResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-11 — PATCH `/users/me`

**Purpose and Functionality**

- **Use case**: A user wants to change their display name, or an engineer needs to change whether they accept new tickets while on leave, in a meeting or returning to work.
- **User action**: Edit the display name on the Profile/Settings page. Tier 1 and Tier 2 engineers may also switch between "Available/Unavailable", then save.
- **Visible result**: The page immediately shows the updated profile after saving. Engineers marked unavailable no longer receive new automatic assignments, but retain tickets already assigned to them.
- **User guidance**: Roles, skills, email addresses and vendor organisations cannot be changed here; these are managed centrally through the project configuration.

- **Purpose**: Update profile. Display name; engineers may update availability.
- **Owner**: Member B (Yujuan Gao)
- **Access**: Authenticated
- **Success**: HTTP 200, Response Model: `UserResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, VALIDATION_ERROR

**Path / Query Parameters**

None.

**Request Body: `UpdateProfileRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `display_name` | string | No | minLength: 1; maxLength: 100 | New display name. |
| `is_available` | boolean | No |  | Engineer availability; forbidden for non-engineers. |

Request example:

```json
{}
```

**Response Body**: See `UserResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-12 — GET `/reference-data`

**Purpose and Functionality**

- **Use case**: While creating a ticket, filtering a list or uploading an attachment, a user needs the currently permitted categories, priorities, states and file rules.
- **User action**: Open the relevant page or dropdown; the frontend retrieves the options automatically, with no manual API call required.
- **Visible result**: All pages use consistent Chinese or English labels, selectable values, SLA guidance, and file size/type limits. Each role sees only the options it may use.
- **User guidance**: These are system rules rather than personal data. Users can select options but cannot change the rules themselves on the page.

- **Purpose**: Get reference data. Role-aware enums, timers and attachment limits.
- **Owner**: Member B (Yujuan Gao)
- **Access**: Authenticated
- **Success**: HTTP 200, Response Model: `ReferenceDataResponse`
- **Business Error Codes**: AUTHENTICATION_REQUIRED, INVALID_ACCESS_TOKEN

**Path / Query Parameters**

None.

**Request Body**: None.

**Response Body**: See `ReferenceDataResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-13 — GET `/users/assignees`

**Purpose and Functionality**

- **Use case**: A manager needs to select an engineer for an unassigned or overdue ticket, or a Tier 1 engineer needs to select an appropriate Tier 2 engineer for escalation.
- **User action**: Open the "Assign/Reassign" or "Escalate" dialog and filter engineers by tier, skill category or availability.
- **Visible result**: The page lists engineers meeting the preliminary criteria, with their tiers, skills, availability and current workloads, helping the user select someone with suitable capacity and expertise.
- **User guidance**: Selecting someone from the list does not complete the assignment. The user must confirm, and the system checks availability again at the final step.

- **Purpose**: List engineers. Tier/skill/availability directory for assignment.
- **Owner**: Member B (Yujuan Gao)
- **Access**: ENGINEER_TIER1, ENGINEER_TIER2, SERVICE_DESK_MANAGER
- **Success**: HTTP 200, Response Model: `AssigneeListResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, VALIDATION_ERROR

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `page` | query | integer | No | default=1; min: 1 | Page number. |
| `page_size` | query | integer | No | default=20; min: 1; max: 100 | Page size. |
| `tier` | query | string | No | enum: TIER1, TIER2 | Tier filter. |
| `category` | query | Category | No |  | Skill filter. |
| `is_available` | query | boolean | No |  | Availability filter. |

**Request Body**: None.

**Response Body**: See `AssigneeListResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-14 — GET `/vendors`

**Purpose and Functionality**

- **Use case**: Tier 2 has determined that external vendor assistance is needed and must first find the correct vendor organisation.
- **User action**: Open the "Request Vendor" form and search by name or browse pages to select a vendor.
- **Visible result**: Only active vendor organisations are listed. After choosing one, the user can enter the question to send to the vendor.
- **User guidance**: Selecting a vendor does not immediately send a request. Enter safe request content and submit it to proceed. Vendor staff login information is not shown here.

- **Purpose**: List vendors. Vendor organisations for Tier 2/Manager.
- **Owner**: Member B (Yujuan Gao)
- **Access**: ENGINEER_TIER2, SERVICE_DESK_MANAGER
- **Success**: HTTP 200, Response Model: `VendorListResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, VALIDATION_ERROR

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `page` | query | integer | No | default=1; min: 1 | Page number. |
| `page_size` | query | integer | No | default=20; min: 1; max: 100 | Page size. |
| `search` | query | string | No | maxLength: 100 | Search. |
| `is_active` | query | boolean | No |  | Active filter. |

**Request Body**: None.

**Response Body**: See `VendorListResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-15 — POST `/tickets`

**Purpose and Functionality**

- **Use case**: An ordinary user encounters a computer, network, account or other IT issue and needs to submit a formal service request.
- **User action**: Enter a title, problem description, category and priority on the "Create Ticket" page, then click "Submit". Attachments can be added after the ticket is created.
- **Visible result**: The system generates a unique ticket number and adds the ticket to "My Tickets". If a suitable engineer is available, it appears as assigned; otherwise it appears as "Unassigned". In either case, submission has succeeded, and an unassigned ticket awaits manager action.
- **User guidance**: Requesters cannot specify the engineer, processing state or SLA deadline. Select priority according to the actual impact; the handling time limit starts at submission.

- **Purpose**: Create ticket. Starts cycle 1 and auto assignment; committed status ASSIGNED/UNASSIGNED.
- **Owner**: Member B (Yujuan Gao)
- **Access**: USER
- **Success**: HTTP 201, Response Model: `TicketDetailResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, VALIDATION_ERROR

**Path / Query Parameters**

None.

**Request Body: `TicketCreateRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `title` | string | Yes | minLength: 1; maxLength: 200 | Title. |
| `description` | string | Yes | minLength: 1; maxLength: 5000 | Description. |
| `category` | Category | Yes |  | Ticket category. |
| `priority` | Priority | Yes |  | Ticket priority. |

Request example:

```json
{
  "title": "Office router repeatedly disconnects",
  "description": "The router disconnects several times per hour.",
  "category": "NETWORK",
  "priority": "LOW"
}
```

**Response Body**: See `TicketDetailResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-16 — GET `/tickets`

**Purpose and Functionality**

- **Use case**: Users in different roles need to find tickets to view or handle.
- **User action**: Ordinary users open "My Tickets"; engineers open their work queues; managers view the global list; vendors view tickets associated with their organisation. Filters may include state, category, priority, SLA, assignee or keywords.
- **Visible result**: A paginated table shows summaries such as ticket number, title, state, priority, assignee and timestamps. Each role sees only records it is authorised to access.
- **User guidance**: The list supports quick browsing and does not include complete descriptions, comments or attachments. Click a row to open the full ticket details.

- **Purpose**: List tickets. Role-aware list; Vendor scope uses request history.
- **Owner**: Member B (Yujuan Gao)
- **Access**: Authenticated
- **Success**: HTTP 200, Response Model: `TicketListResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, VALIDATION_ERROR

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `page` | query | integer | No | default=1; min: 1 | Page number. |
| `page_size` | query | integer | No | default=20; min: 1; max: 100 | Page size. |
| `status` | query | TicketStatus | No |  | Status. |
| `category` | query | Category | No |  | Category. |
| `priority` | query | Priority | No |  | Priority. |
| `sla_status` | query | SlaStatus | No |  | SLA. |
| `assignee_id` | query | integer(int64) | No | min: 1 | Assignee; role restricted. |
| `search` | query | string | No | maxLength: 200 | Search. |
| `sort_by` | query | string | No | enum: created_at, updated_at, sla_deadline, priority | Sort field. |
| `sort_order` | query | string | No | enum: asc, desc | Direction. |

**Request Body**: None.

**Response Body**: See `TicketListResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-17 — GET `/tickets/{id}`

**Purpose and Functionality**

- **Use case**: A user selects a ticket from the list to review progress, comments or attachments, or to take the next action.
- **User action**: Open the ticket detail page, or refresh it after starting work, requesting information, submitting a resolution or taking another action.
- **Visible result**: The page shows the title, description, state, assignee, SLA, resolution and action buttons permitted for the current role. Ordinary users see user-facing progress; engineers and managers see internal handling information; vendors see only content specifically provided to them.
- **User guidance**: The same ticket shows different content and buttons to different roles. Unauthorised access is treated as "Ticket not found" to avoid disclosing ticket information.

- **Purpose**: Get ticket detail. Role-aware detail, display status and available actions.
- **Owner**: Member B (Yujuan Gao)
- **Access**: Scoped authenticated role
- **Success**: HTTP 200, Response Model: `TicketDetailResponse`
- **Business Error Codes**: RESOURCE_NOT_FOUND

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body**: None.

**Response Body**: See `TicketDetailResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-18 — PATCH `/tickets/{id}`

**Purpose and Functionality**

- **Use case**: A requester notices an incorrect title, description, category or priority just after submission, or a manager needs to correct basic information on a ticket that is not closed.
- **User action**: Click "Edit" on the ticket detail page, change the permitted fields and save.
- **Visible result**: The detail page shows the updated content and retains a record of who changed it and when. If editing is not allowed, the page explains that the ticket state or permissions do not meet the requirements.
- **User guidance**: Ordinary users may edit only their own unassigned tickets. The edit form cannot directly change the assignee, processing state, SLA, resolution or vendor.

- **Purpose**: Update ticket core. USER own UNASSIGNED; Manager non-CLOSED; no direct status/assignee/SLA changes.
- **Owner**: Member B (Yujuan Gao)
- **Access**: USER owner or SERVICE_DESK_MANAGER
- **Success**: HTTP 200, Response Model: `TicketDetailResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, TICKET_CLOSED, VALIDATION_ERROR

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body: `TicketUpdateRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `title` | string | No | minLength: 1; maxLength: 200 | New title. |
| `description` | string | No | minLength: 1; maxLength: 5000 | New description. |
| `category` | Category | No |  | Ticket category. |
| `priority` | Priority | No |  | Ticket priority. |

Request example:

```json
{}
```

**Response Body**: See `TicketDetailResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-19 — GET `/tickets/{id}/comments`

**Purpose and Functionality**

- **Use case**: A requester, engineer or manager opens the ticket's "Conversation/Comments" section to review earlier communication.
- **User action**: Open the comments section or page down to load older comments.
- **Visible result**: Ordinary users see only user-visible communication; engineers and managers may also see internal notes. Each comment displays its author, timestamp and content.
- **User guidance**: Vendors do not use this ordinary comments area. Internal comments are hidden from requesters, and timeline events are not mixed into the ordinary comment list.

- **Purpose**: List comments. Role/visibility filtered; Vendor denied.
- **Owner**: Member B (Yujuan Gao)
- **Access**: USER, T1, T2, Manager
- **Success**: HTTP 200, Response Model: `CommentListResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |
| `page` | query | integer | No | default=1; min: 1 | Page number. |
| `page_size` | query | integer | No | default=20; min: 1; max: 100 | Page size. |
| `visibility` | query | CommentVisibility | No |  | Visibility. |

**Request Body**: None.

**Response Body**: See `CommentListResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-20 — POST `/tickets/{id}/comments`

**Purpose and Functionality**

- **Use case**: A requester wants to add general information, or an engineer or manager wants to record ordinary communication or internal notes without changing the processing state.
- **User action**: Enter content in the Conversation area, select a permitted visibility level and click "Send".
- **Visible result**: The new comment appears immediately, while the ticket state, assignee and SLA remain unchanged.
- **User guidance**: When the system is waiting for user information or resolution confirmation, use the dedicated "Resume", "Issue Persists" or "Confirm" buttons. Ordinary comments cannot complete these workflows. Closed tickets cannot receive new comments.

- **Purpose**: Create ordinary comment. Creates comment/event; formal waiting-state actors receive guidance errors.
- **Owner**: Member B (Yujuan Gao)
- **Access**: Scoped role; ordinary Vendor comments denied
- **Success**: HTTP 201, Response Model: `CommentResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, USE_RESUME_ACTION, USE_CONFIRM_OR_RESUME_ACTION, USE_VENDOR_RESPONSE_ACTION, TICKET_CLOSED

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body: `CommentCreateRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `message` | string | Yes | minLength: 1; maxLength: 4000 | Message. |
| `visibility` | CommentVisibility | Yes |  | Comment visibility. |

Request example:

```json
{
  "message": "Please provide the requested information.",
  "visibility": "USER_VISIBLE"
}
```

**Response Body**: See `CommentResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-21 — POST `/tickets/{id}/assign`

**Purpose and Functionality**

- **Use case**: A manager needs to assign an unassigned, reopened or eligible overdue ticket to an engineer.
- **User action**: Click "Assign/Reassign" on the ticket or queue, review the candidates, select an engineer and confirm.
- **Visible result**: The ticket shows the new assignee. An unassigned or reopened ticket moves into a state in which work can begin, and the action appears on the timeline.
- **User guidance**: If the selected engineer's tier, skills or availability are unsuitable, the page asks for another selection. Managers cannot change assignees freely in every processing state.

- **Purpose**: Assign/reassign. Strict matrix and engineer eligibility.
- **Owner**: Member C (Andy Wen)
- **Access**: SERVICE_DESK_MANAGER
- **Success**: HTTP 200, Response Model: `TicketActionResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, ASSIGNEE_NOT_ELIGIBLE, TICKET_CLOSED

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body: `AssignmentRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `assignee_id` | integer(int64) | Yes |  | Target engineer. |
| `reason` | string | No | minLength: 1; maxLength: 1000 | Reason. |

Request example:

```json
{
  "assignee_id": 10001
}
```

**Response Body**: See `TicketActionResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-22 — POST `/tickets/{id}/start`

**Purpose and Functionality**

- **Use case**: A Tier 1 or Tier 2 engineer receives an assigned or reopened ticket and is ready to begin investigation.
- **User action**: The current assignee clicks "Start Work" on the ticket detail page.
- **Visible result**: The state changes from "Assigned/Reopened" to "In Progress". The requester and manager can see that work has begun, and the timeline records who started and when.
- **User guidance**: Only the current assignee may start work. Tickets already in progress, waiting or closed cannot be started again, and the existing SLA timer is not reset.

- **Purpose**: Start handling. ASSIGNED/REOPENED to IN_PROGRESS.
- **Owner**: Member C (Andy Wen)
- **Access**: Current assignee
- **Success**: HTTP 200, Response Model: `TicketActionResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, TICKET_CLOSED

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body**: None.

**Response Body**: See `TicketActionResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-23 — POST `/tickets/{id}/request-user-info`

**Purpose and Functionality**

- **Use case**: The current engineer cannot continue investigating without information such as an error screenshot, device number, occurrence time or user test results.
- **User action**: Click "Request User Information", clearly describe what the user needs to provide and submit.
- **Visible result**: The requester sees a prominent "Waiting for your information" message and the engineer's question, with 120 hours to respond. The engineer's view indicates that the ticket is waiting for the user, and the current engineering timer is paused.
- **User guidance**: This is a formal action rather than an ordinary comment. Only the current assignee of an in-progress ticket may initiate it. The requester must use the dedicated reply/resume action to continue processing.

- **Purpose**: Request user info. USER_VISIBLE request; pause cycle; PENDING_USER/INFORMATION_REQUIRED for 120h.
- **Owner**: Member C (Andy Wen)
- **Access**: Current assignee in IN_PROGRESS
- **Success**: HTTP 200, Response Model: `TicketActionResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, TICKET_CLOSED

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body: `RequestUserInfoRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `message` | string | Yes | minLength: 1; maxLength: 4000 | User-visible request. |

Request example:

```json
{
  "message": "Please provide the requested information."
}
```

**Response Body**: See `TicketActionResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-24 — POST `/tickets/{id}/resume`

**Purpose and Functionality**

- **Use case**: A requester is ready to answer an engineer's information request or reports that a proposed resolution has not fixed the issue.
- **User action**: Click "Provide Information/Resume" or "Issue Persists" on the waiting page, enter the details and submit.
- **Visible result**: The reply appears in the conversation, the ticket returns to "In Progress", and the engineer can continue work under a new 48-hour engineering cycle.
- **User guidance**: Submit within the 120-hour response window. After the deadline, the system first applies the prescribed automatic outcome. An ordinary comment alone does not resume processing.

- **Purpose**: Resume ticket. Requester supplies info/issue persists before deadline; new 48h cycle.
- **Owner**: Member C (Andy Wen)
- **Access**: Ticket requester
- **Success**: HTTP 200, Response Model: `TicketActionResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, USER_RESPONSE_WINDOW_EXPIRED, TICKET_CLOSED

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body: `ResumeRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `message` | string | Yes | minLength: 1; maxLength: 4000 | Information or issue-persists explanation. |

Request example:

```json
{
  "message": "Please provide the requested information."
}
```

**Response Body**: See `TicketActionResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-25 — POST `/tickets/{id}/escalate`

**Purpose and Functionality**

- **Use case**: Tier 1 determines that the issue requires higher privileges, specialist skills or deeper investigation and cannot complete it alone.
- **User action**: The current Tier 1 assignee clicks "Escalate to Tier 2", selects a Tier 2 engineer with suitable skills, enters the escalation reason and confirms.
- **Visible result**: The selected Tier 2 engineer becomes the assignee, and the ticket returns to "Assigned" until that engineer starts work. Managers and relevant users can see the reason and handover record on the timeline.
- **User guidance**: Escalation is allowed only to an available Tier 2 engineer with matching skills. It does not recalculate or extend the current SLA deadline, so act early.

- **Purpose**: Escalate to Tier 2. Select eligible Tier 2; preserve cycle/deadline.
- **Owner**: Member C (Andy Wen)
- **Access**: Current Tier 1 assignee in IN_PROGRESS
- **Success**: HTTP 200, Response Model: `TicketActionResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, ASSIGNEE_NOT_ELIGIBLE, TICKET_CLOSED

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body: `EscalateRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `tier2_assignee_id` | integer(int64) | Yes |  | Tier 2 ID. |
| `reason` | string | No | minLength: 1; maxLength: 1000 | Reason. |

Request example:

```json
{
  "tier2_assignee_id": 10001
}
```

**Response Body**: See `TicketActionResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-26 — POST `/tickets/{id}/vendor-requests`

**Purpose and Functionality**

- **Use case**: Tier 2 determines that the issue involves a third-party product or service and needs technical support from a specific vendor.
- **User action**: Click "Request Vendor", select a vendor, write a separate problem description that is safe to share externally and submit.
- **Visible result**: The ticket enters "Waiting for Vendor". The selected vendor can view and answer the request on its page, and internal staff can see which vendor is being awaited.
- **User guidance**: The system does not automatically send the user's original description, internal comments or personal information to the vendor. Tier 2 must write sanitised content. Only one active vendor request may be pending per ticket, and the SLA continues running.

- **Purpose**: Request vendor. Create only ACTIVE request; PENDING_VENDOR; SLA continues.
- **Owner**: Member C (Andy Wen)
- **Access**: Current Tier 2 assignee
- **Success**: HTTP 201, Response Model: `TicketActionResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, ACTIVE_VENDOR_REQUEST_EXISTS, TICKET_CLOSED

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body: `VendorRequestCreate`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `vendor_org_id` | integer(int64) | Yes |  | Vendor organisation ID. |
| `vendor_message` | string | Yes | minLength: 1; maxLength: 4000 | Vendor-safe message. |

Request example:

```json
{
  "vendor_org_id": 10001,
  "vendor_message": "Please investigate the router firmware issue."
}
```

**Response Body**: See `TicketActionResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-27 — POST `/tickets/{id}/vendor-response`

**Purpose and Functionality**

- **Use case**: A vendor logs in, sees a technical support request for its organisation and has prepared diagnostic advice, instructions or a result.
- **User action**: Enter a formal reply on the vendor ticket page, add vendor-visible attachments through the permitted process if needed, and click "Submit Response".
- **Visible result**: The vendor request becomes "Responded". Internal Tier 2 staff can view the reply, and the ticket returns to "In Progress" so work on the user's issue can continue.
- **User guidance**: Vendors may answer only their own organisation's current active requests and cannot view or respond to other vendors' tickets. Ended or previously answered requests cannot be submitted again.

- **Purpose**: Vendor response. Matching Vendor responds to current ACTIVE request; no request ID in body.
- **Owner**: Member C (Andy Wen)
- **Access**: Matching EXTERNAL_VENDOR
- **Success**: HTTP 200, Response Model: `TicketActionResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, NO_ACTIVE_VENDOR_REQUEST, INVALID_STATUS_TRANSITION, TICKET_CLOSED

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body: `VendorResponseRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `message` | string | Yes | minLength: 1; maxLength: 4000 | Vendor response. |

Request example:

```json
{
  "message": "Please provide the requested information."
}
```

**Response Body**: See `TicketActionResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-28 — POST `/tickets/{id}/resolve`

**Purpose and Functionality**

- **Use case**: The current engineer believes the issue is fixed or has supplied an actionable solution and needs the requester to confirm the result.
- **User action**: Click "Resolve", enter user-facing resolution steps, the outcome and a verification method, then submit.
- **Visible result**: The requester sees "Please confirm resolution" and the complete solution, and may confirm success or report that the issue persists. The system allows 120 hours for confirmation.
- **User guidance**: An ordinary internal comment cannot replace the formal resolution, and only the current assignee may submit it. If Tier 2 resolves while waiting for a vendor, the active vendor request ends at the same time.

- **Purpose**: Submit resolution. User-visible resolution; PENDING_USER/RESOLUTION_CONFIRMATION; cancel active Vendor request.
- **Owner**: Member C (Andy Wen)
- **Access**: Current assignee
- **Success**: HTTP 200, Response Model: `TicketActionResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, TICKET_CLOSED

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body: `ResolveRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `resolution_summary` | string | Yes | minLength: 1; maxLength: 5000 | User-visible resolution. |

Request example:

```json
{
  "resolution_summary": "Updated firmware and verified stable connectivity."
}
```

**Response Body**: See `TicketActionResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-29 — POST `/tickets/{id}/confirm-resolution`

**Purpose and Functionality**

- **Use case**: The requester has tested the engineer's solution and confirmed that the issue is gone.
- **User action**: Click "Confirm Resolved" in the resolution section; no additional content is required.
- **Visible result**: The ticket becomes "Resolved", displays the confirmation time and enters a seven-day observation window. The requester may reopen it if the issue recurs during that window.
- **User guidance**: Confirm within the 120-hour window. After expiry, the system automatically marks the ticket resolved according to the rules. If the issue persists, use "Issue Persists" instead of confirming.

- **Purpose**: Confirm resolution. Requester confirms before 120h deadline; RESOLVED and seven-day window.
- **Owner**: Member C (Andy Wen)
- **Access**: Ticket requester
- **Success**: HTTP 200, Response Model: `TicketActionResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, USER_RESPONSE_WINDOW_EXPIRED, TICKET_CLOSED

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body**: None.

**Response Body**: See `TicketActionResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-30 — POST `/tickets/{id}/reopen`

**Purpose and Functionality**

- **Use case**: A ticket is "Resolved", but the same issue recurs or the solution fails to remain effective during the seven-day observation window.
- **User action**: Click "Reopen", describe when the problem returned, its symptoms and the reason for reopening, then submit.
- **Visible result**: The ticket becomes "Reopened" and starts a new handling cycle. The original engineer receives it preferentially if still available; otherwise it becomes unassigned and awaits manager allocation.
- **User guidance**: A reopening reason is required. After seven days, the ticket closes automatically. A closed ticket cannot be reopened with this button; create a new ticket instead.

- **Purpose**: Reopen ticket. Before auto_close_at; new SLA cycle; previous assignee preferred if available.
- **Owner**: Member C (Andy Wen)
- **Access**: Ticket requester
- **Success**: HTTP 200, Response Model: `TicketActionResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, TICKET_CLOSED

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body: `ReopenRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `reason` | string | Yes | minLength: 1; maxLength: 4000 | Why issue persists. |

Request example:

```json
{
  "reason": "The issue is still occurring."
}
```

**Response Body**: See `TicketActionResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-31 — POST `/tickets/{id}/close`

**Purpose and Functionality**

- **Use case**: The requester has confirmed the issue is resolved and wants to end the ticket immediately without retaining the seven-day observation window.
- **User action**: Click "Close Ticket" on a resolved ticket, read the warning that it cannot be reopened after closure, tick the acknowledgement and submit again.
- **Visible result**: The ticket immediately becomes "Closed", leaves the pending work queues, and the timeline records that the requester closed it manually.
- **User guidance**: Closure is irreversible. The system will not proceed without acknowledgement. If the issue recurs after closure, create a new ticket.

- **Purpose**: Manual close. Requires acknowledge=true; CLOSED terminal.
- **Owner**: Member C (Andy Wen)
- **Access**: Ticket requester
- **Success**: HTTP 200, Response Model: `TicketActionResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, CLOSE_ACKNOWLEDGEMENT_REQUIRED, TICKET_CLOSED

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |

**Request Body: `CloseRequest`**

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `acknowledge` | boolean | Yes | const: true | Must be true. |
| `reason` | string | No | minLength: 1; maxLength: 1000 | Optional note. |

Request example:

```json
{
  "acknowledge": true
}
```

**Response Body**: See `TicketActionResponse`; the complete field definitions are in the model dictionary in Section 7.

---

### API-32 — GET `/tickets/{id}/events`

**Purpose and Functionality**

- **Use case**: An authorised user wants to review the steps a ticket has passed through since submission. Managers may also use this to inspect assignment, escalation, overdue handling and closure.
- **User action**: Open "Timeline/History" on the ticket detail page and page down to view older records.
- **Visible result**: The page displays events in chronological order, including creation, assignment, work start, waiting for the user, escalation, vendor collaboration, resolution, reopening and closure, with the actor and time. Each role sees only events it is permitted to access.
- **User guidance**: The timeline is system-generated history that users cannot edit or delete. Full comments and vendor replies remain in their respective sections and are not duplicated on the timeline.

- **Purpose**: List audit events. Append-only role/scope-filtered timeline with minimal metadata.
- **Owner**: Member C (Andy Wen)
- **Access**: Scoped authenticated role
- **Success**: HTTP 200, Response Model: `EventListResponse`
- **Business Error Codes**: DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, VALIDATION_ERROR

**Path / Query Parameters**

| Parameter | Location | Type | Required | Default/Constraints | Description |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | Yes | min: 1 | Ticket ID. |
| `page` | query | integer | No | default=1; min: 1 | Page number. |
| `page_size` | query | integer | No | default=20; min: 1; max: 100 | Page size. |
| `event_type` | query | EventType | No |  | Event type. |
| `scope` | query | EventScope | No |  | Scope; role restricted. |

**Request Body**: None.

**Response Body**: See `EventListResponse`; the complete field definitions are in the model dictionary in Section 7.

---

## 6. Key Business Rules

Section 6 defines **when the system permits or rejects an action and what each role can ultimately see**. Individual API sections primarily describe URLs, request parameters and response parameters; this section establishes the business decision rules that all relevant APIs must follow.

Think of an API as an entrance and the business rules as the traffic rules that apply after entering. Even when the frontend hides a button, the backend must independently check the role, ticket ownership, current state and deadline according to this section; it must not simply trust the frontend.

This section serves the following purposes:

| Audience | Purpose |
|---|---|
| Backend Members A (BIN LIN)/B (Yujuan Gao)/C (Andy Wen) | Apply these rules when implementing permissions, state transitions, SLAs, attachments and comments, ensuring consistent behaviour across modules. |
| Frontend Member D (Yiguang Sun) | Use the user's role, `display_status` and `available_actions` to determine which buttons, guidance and page content to display. |
| Testers | Turn each rule into tests for permitted actions, rejected actions, time boundaries and unauthorised access. |
| PM/Marker | Check that the implementation follows the main business flow, state machine and security requirements. |

The key relationship is:

```text
API definition: which URL the frontend calls and which fields it submits
        +
Business rules: whether the current user and state permit the action
        =
Final outcome: return data on success or a standard business error
```

### 6.1 Role-aware Serialization

**Purpose**: The same ticket returns different content depending on the authenticated user's role and business relationship to it. This controls both access to the ticket and which fields are visible once access is granted. It prevents ordinary users from seeing internal information, vendors from seeing personal information, and users from accessing other people's tickets by guessing ticket IDs.

**End-user examples**:

- Requesters viewing their own tickets can see user-facing states, public comments, resolutions and `USER_VISIBLE` attachments.
- When a ticket is internally `PENDING_VENDOR`, the requester still sees `IN_PROGRESS` and cannot see the vendor's name, request content or response content.
- Tier 2 can view authorised vendor requests; Tier 1 cannot see vendor payloads or `VENDOR_SHARED` attachments.
- Vendors see only sanitised information sent to their own organisation, with no user personal data, original description or internal comments.
- Managers can view tickets globally, but still cannot obtain passwords, credentials or other sensitive information.

**Backend implementation requirements**: Check ticket scope first, then filter fields through a role-aware serializer. Return 404 consistently for unauthorised resources; do not use 403 or an error message to reveal that a ticket exists but is inaccessible.

**Mandatory rules**:

- USER may access only their own tickets. Serialise PENDING_VENDOR as IN_PROGRESS and return no vendor data.
- Tier 1 may access only currently assigned tickets, with no vendor payloads or VENDOR_SHARED attachments.
- Tier 2 may access only currently assigned tickets and may view authorised vendor data.
- Vendors are limited to their own organisation's VendorRequest scope; do not return user personal data or the original description.
- Managers have global scope. Hidden resources consistently return 404, without error messages revealing their existence.

### 6.2 Workflow / Deadline

**Purpose**: Define which actions are allowed in each ticket state, who may perform them and what must happen first once a time boundary is reached. This prevents actions in invalid states and conflicting ticket states caused by concurrent requests.

**End-user examples**:

```text
IN_PROGRESS
    ↓ Engineer requests additional information
PENDING_USER / INFORMATION_REQUIRED
    ↓ Requester replies through API-24 within 120 hours
IN_PROGRESS, with a new 48-hour Engineering Cycle
```

- The Engineering SLA pauses while waiting for the requester, so user waiting time is excluded from engineering handling time.
- The Engineering SLA continues while waiting for a vendor, so Tier 2 must keep monitoring the deadline.
- Tier 1 escalation to Tier 2, manager reassignment or a vendor change does not restart the current cycle or deadline.
- Once a ticket is `CLOSED`, previously authorised information remains readable, but editing, commenting, assignment, reopening and attachment uploads are prohibited.

**Deadline boundary example**: A user may respond only while `now < deadline`. At the instant the 120-hour window ends, the backend must apply the automatic outcome before rejecting the expired user action, even if the frontend has not refreshed. This prevents inconsistent results at the boundary.

**Backend implementation requirements**: Every workflow API must read and lock the latest ticket, check its state, role and deadline, then commit the business objects and TicketEvent together. Frontend buttons improve usability but do not replace backend validation.

**Mandatory rules**:

- User actions are allowed only while `now < deadline`; when `now >= deadline`, apply the automatic outcome before returning a conflict error.
- PENDING_USER pauses the engineering cycle; PENDING_VENDOR continues the current cycle.
- Changes to tier, assignee or vendor do not reset the cycle.
- CLOSED is terminal; reading previously authorised data is allowed, but all business writes are rejected.
- All workflow writes lock the ticket first, followed by VendorRequest/AttachmentUpload; events and business objects share the same transaction.

### 6.3 Attachment

**Purpose**: Define how end users securely upload and download files without routing file bytes through the backend container. Users select files on the ticket page, while the frontend and backend handle temporary S3 authorisation, upload and registration in the background.

**Complete flow for uploading a screenshot**:

```text
1. The user selects error.png in Ticket Detail and clicks Upload
2. The frontend calls API-02 to obtain a temporary URL for the upload
3. The browser uses that URL to PUT the raw file directly to private S3
4. The frontend calls API-03 so the backend can verify and formally register the attachment
5. After API-03 succeeds, the file appears in the attachment list
```

API-02 success means only that uploading is permitted, not that the attachment has been added. The end user sees it on the ticket only after API-03 succeeds. For downloads, clicking Download calls API-05, which rechecks permissions and returns a temporary URL valid for approximately five minutes.

**Benefits**:

- Users do not need to know the bucket, object key or AWS credentials.
- Direct browser-to-S3 access reduces backend container network, memory and CPU usage.
- The backend verifies Size and Content-Type against the actual file in S3 rather than trusting frontend-reported values.
- Repeated Complete calls return the same attachment, preventing duplicate files and events caused by network retries.
- `USER_VISIBLE`, `INTERNAL_ONLY` and `VENDOR_SHARED` ensure that each role can access only the appropriate attachments.

**Mandatory rules**:

- The three-step flow is fixed: API-02 Presign → browser raw PUT to S3 → API-03 Complete.
- The frontend does not submit object_key, vendor_request_id or vendor_org_id.
- API-03 accepts only upload_id and uses the actual Size/Content-Type from HeadObject.
- Repeated Complete calls return the original attachment without creating duplicate attachments/events.
- File limit: 10 MiB; PNG/JPG/PDF/TXT/LOG; PUT TTL: 15 minutes; GET TTL: 5 minutes.

### 6.4 Comment vs Workflow Action

**Purpose**: Distinguish ordinary communication records from formal actions that advance the ticket workflow. Mixing them could cause an ordinary comment to incorrectly resume the SLA, confirm a resolution or end a vendor request.

| End-user Intent | Page Action | API | Changes the Workflow? |
|---|---|---|---|
| Send general information or an internal note | Send Comment | API-20 | No; only adds a comment/event. |
| Reply to an engineer's information request | Provide Information / Resume | API-24 | Yes; returns to `IN_PROGRESS` and starts a new engineering cycle. |
| Report that the resolution did not fix the issue | Issue Persists | API-24 | Yes; returns to `IN_PROGRESS`. |
| Confirm that the issue is resolved | Confirm Resolved | API-29 | Yes; enters `RESOLVED`. |
| Submit a formal vendor response | Submit Vendor Response | API-27 | Yes; the vendor request becomes `RESPONDED` and the ticket returns to `IN_PROGRESS`. |

**End-user example**: When a ticket is `PENDING_USER / INFORMATION_REQUIRED`, sending "Information provided" in the ordinary comment box records text only; it cannot resume the ticket. The frontend should direct the user to the dedicated `Provide Information / Resume` button. If API-20 is called anyway, the backend returns a guidance error instructing the frontend to use API-24.

**Frontend implementation requirements**: Display the correct buttons using `available_actions` from API-17; do not implement every action through a single comment input box.

**Mandatory rules**:

- Ordinary comments do not trigger Resume, Confirm or Vendor Response.
- Users in PENDING_USER use API-24/API-29; API-20 returns the corresponding guidance error.
- Vendors in PENDING_VENDOR use API-27.

## 7. Complete Pydantic/OpenAPI Model Field Dictionary

Section 7 defines **the exact fields in the JSON sent from the frontend to the backend, and the exact shape of the JSON returned to the frontend**. It is the shared frontend/backend data contract and the basis for FastAPI's automatic validation and Swagger documentation.

This section is not a database table design. Database models address data storage; Pydantic/OpenAPI models define what may be accepted and returned through APIs. A database table may contain internal fields such as password hashes and S3 object keys, but these must not appear in public response models.

### 7.0 Purpose and Reading Guide

#### 7.0.1 The Four Model Categories

| Model Category | Data Direction | Purpose | Examples |
|---|---|---|---|
| Request Model | Frontend → Backend | Defines the fields permitted or required for an API call and rejects incorrectly formatted data. | `LoginRequest`, `TicketCreateRequest`, `ResolveRequest` |
| Response Model | Backend → Frontend | Defines the outermost JSON structure returned on success. | `LoginResponse`, `TicketDetailResponse`, `TicketListResponse` |
| DTO | Backend → Frontend, nested within a response | Represents a reusable data object, such as a user summary, ticket detail, attachment or SLA information. | `UserProfile`, `TicketDetail`, `AttachmentItem` |
| Shared Envelope | Standard outer wrapper for all APIs | Gives the frontend a consistent way to read success data, pagination information and errors. | `data`, `meta`, `error` |

For example, the structure of a successful ticket response is:

```text
TicketDetailResponse (Response Model)
└── data: TicketDetail (DTO)
    ├── ticket_id
    ├── title
    ├── status
    ├── assignee: AssigneeSummary (another DTO)
    └── available_actions
```

#### 7.0.2 What Pydantic Does in the Backend

Backend members implement the field tables in this section as Python Pydantic classes and specify request and response models on FastAPI routes. Pydantic automatically performs basic format validation and enforces output constraints.

For example, when creating a ticket through API-15:

```python
class TicketCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    category: Category
    priority: Priority

@router.post("/tickets", response_model=TicketDetailResponse)
def create_ticket(payload: TicketCreateRequest):
    ...
```

Valid frontend submission:

```json
{
  "title": "Cannot connect to office Wi-Fi",
  "description": "The laptop cannot connect after restarting.",
  "category": "NETWORK",
  "priority": "HIGH"
}
```

Pydantic checks:

- Whether all four required fields are present.
- Whether `title` and `description` are empty or exceed their maximum lengths.
- Whether `category` belongs to the `Category` enum.
- Whether `priority` belongs to the `Priority` enum.
- Whether the JSON field types are correct.

If the frontend submits an empty title, uses an undefined `category="PRINTER"`, or sends a number for `priority`, FastAPI rejects the request with a validation error before entering the business service. Developers therefore do not need to repeat the same basic validation in each route.

Pydantic performs structural validation, such as field types, lengths and formats. Business decisions, such as whether the current user owns the ticket or whether the current state permits reopening, must still be implemented in services/policies according to Section 6.

#### 7.0.3 How OpenAPI and Swagger Support Collaboration

FastAPI automatically generates an OpenAPI schema from routes and Pydantic models, and provides a local Swagger UI:

```text
http://localhost:8000/docs
```

Frontend members can use Swagger UI to:

- View all API paths and HTTP methods.
- Inspect request bodies, path parameters and query parameters.
- Check field types, required fields, enums and length limits.
- Enter test data and call the backend directly.
- View success and error response examples.

Whenever backend members change API fields, they must update the Pydantic models, OpenAPI/Swagger and this Markdown document together. The frontend must follow the agreed OpenAPI contract and must not add undefined fields to suit page requirements.

#### 7.0.4 How to Read Each Column in a Field Table

| Column | Meaning | Development Usage |
|---|---|---|
| Field | Exact JSON key, including case and underscores. | Both frontend and backend must use the same name, e.g. `ticket_id`. |
| Type | Permitted data type or referenced DTO/enum. | Determines whether to send a string, integer, boolean, array or nested object. |
| Required | Whether the key must appear in the JSON. | "Yes" means it must be present; "No" means it may be omitted from a request. |
| Constraints | Limits on length, range, format, fixed values or array size. | Pydantic uses these for validation; the frontend may use them for early guidance. |
| Description | The field's business meaning, rather than its UI label. | Helps team members interpret the field consistently. |

JSON representations of common types:

| Model Type Notation | JSON Example | Meaning |
|---|---|---|
| `string` | `"Network problem"` | Ordinary text. |
| `integer(int64)` | `1001` | Integer ID, without quotes. |
| `boolean` | `true` | Boolean value, not the string `"true"`. |
| `string(date-time)` | `"2026-09-01T10:30:00Z"` | ISO 8601 timestamp, usually in UTC. |
| `array<TicketListItem>` | `[{"ticket_id": 1001}]` | A list of objects of the same type. |
| `Category` | `"NETWORK"` | Must use a fixed string defined in the enum. |
| `AssigneeSummary | null` | `null` or `{...}` | An assignee object may be present, or there may be no assignee. |

#### 7.0.5 Required, Optional and null

- `Required = Yes`: the field must appear in the JSON.
- `Required = No`: the field may be omitted entirely, commonly for partial PATCH updates.
- `Type = T | null`: the field may have no business value, in which case `null` is returned or submitted.

For example, `TicketDetail.assignee` has type `AssigneeSummary | null` and `Required = Yes`:

```json
{
  "assignee": null
}
```

The response must contain the `assignee` key, but its value is `null` because the ticket is currently unassigned.

By contrast, `Required = No` for `TicketUpdateRequest.title` means that `title` may be omitted entirely when the user changes only the priority:

```json
{
  "priority": "HIGH"
}
```

The backend must distinguish an omitted field from a field explicitly submitted as null.

#### 7.0.6 Why Shared Envelopes Must Be Consistent

Successful single-object responses consistently use:

```json
{
  "data": {
    "ticket_id": 1001,
    "status": "ASSIGNED"
  }
}
```

Paginated responses consistently use:

```json
{
  "data": [
    {"ticket_id": 1001},
    {"ticket_id": 1002}
  ],
  "meta": {
    "page": 1,
    "page_size": 20,
    "total": 35,
    "total_pages": 2
  }
}
```

Error responses consistently use:

```json
{
  "error": {
    "code": "INVALID_STATUS_TRANSITION",
    "message": "This action is not allowed in the current status",
    "details": {}
  }
}
```

With consistent envelopes, the frontend can use one shared API client to handle `data`, pagination and errors instead of guessing a separate response format for each of the 32 APIs.

#### 7.0.7 How Each Member Uses This Section

| Member | Practical Usage |
|---|---|
| Backend A (BIN LIN)/B (Yujuan Gao)/C (Andy Wen) | Create Pydantic classes for their models, declare request/response models on routes, and return only authorised data from services. |
| Frontend D (Yiguang Sun) | Create TypeScript types/interfaces from OpenAPI, construct requests according to required fields and enums, and parse envelopes consistently. |
| Testers | Test missing required fields, incorrect types, invalid enum values, length boundaries, null and extra fields. |
| API Maintainer | Review whether model changes affect other members; update the contract before notifying the frontend of field changes. |

**Section 6 determines whether an action is currently allowed; Section 7 defines the JSON accepted and returned when that action is performed.**

The complete field definitions for all requests, responses, DTOs and shared envelopes follow. `Required` is governed by the OpenAPI schema. Required fields must always be present; return JSON `null` when there is no current value or the role lacks access, rather than omitting the field in the serializer.

### Role

Type: `string enum`; values: `USER`, `ENGINEER_TIER1`, `ENGINEER_TIER2`, `EXTERNAL_VENDOR`, `SERVICE_DESK_MANAGER`

### Category

Type: `string enum`; values: `NETWORK`, `HARDWARE`, `SOFTWARE`, `ACCOUNT`, `OTHER`

### Priority

Type: `string enum`; values: `LOW`, `MEDIUM`, `HIGH`, `URGENT`

### TicketStatus

Type: `string enum`; values: `UNASSIGNED`, `ASSIGNED`, `IN_PROGRESS`, `PENDING_USER`, `PENDING_VENDOR`, `RESOLVED`, `REOPENED`, `CLOSED`

### SlaStatus

Type: `string enum`; values: `ON_TRACK`, `AT_RISK`, `OVERDUE`, `PAUSED`, `MET`

### PendingUserReason

Type: `string enum`; values: `INFORMATION_REQUIRED`, `RESOLUTION_CONFIRMATION`

### AttachmentVisibility

Type: `string enum`; values: `USER_VISIBLE`, `INTERNAL_ONLY`, `VENDOR_SHARED`

### CommentVisibility

Type: `string enum`; values: `USER_VISIBLE`, `INTERNAL_ONLY`

### EventScope

Type: `string enum`; values: `USER_VISIBLE`, `INTERNAL_ONLY`, `VENDOR_SCOPE`

### EventType

Type: `string enum`; values: `TICKET_CREATED`, `AUTO_ASSIGNED`, `ASSIGNED`, `REASSIGNED`, `HANDLING_STARTED`, `COMMENT_ADDED`, `SLA_CYCLE_STARTED`, `SLA_PAUSED`, `SLA_AT_RISK`, `SLA_OVERDUE`, `SLA_MET`, `USER_INFO_REQUESTED`, `USER_RESUMED`, `VENDOR_REQUESTED`, `VENDOR_RESPONDED`, `VENDOR_CANCELLED`, `RESOLUTION_SUBMITTED`, `RESOLUTION_CONFIRMED`, `AUTO_RESOLVED_NO_USER_RESPONSE`, `RESOLUTION_CONFIRMATION_TIMEOUT`, `TICKET_REOPENED`, `TICKET_CLOSED_MANUAL`, `TICKET_CLOSED_AUTO`, `ATTACHMENT_ADDED`

### VendorRequestStatus

Type: `string enum`; values: `ACTIVE`, `RESPONDED`, `CANCELLED`

### AvailableAction

Type: `string enum`; values: `EDIT`, `COMMENT`, `UPLOAD_ATTACHMENT`, `ASSIGN`, `START`, `REQUEST_USER_INFO`, `RESUME`, `ESCALATE`, `REQUEST_VENDOR`, `VENDOR_RESPONSE`, `RESOLVE`, `CONFIRM_RESOLUTION`, `REOPEN`, `CLOSE`

### ErrorCode

Type: `string enum`; values: `INVALID_REQUEST`, `VALIDATION_ERROR`, `AUTHENTICATION_REQUIRED`, `INVALID_ACCESS_TOKEN`, `EMAIL_ALREADY_REGISTERED`, `INVALID_CREDENTIALS`, `PASSWORD_POLICY_VIOLATION`, `DATA_SCOPE_DENIED`, `RESOURCE_NOT_FOUND`, `INVALID_STATUS_TRANSITION`, `ASSIGNEE_NOT_ELIGIBLE`, `USER_RESPONSE_WINDOW_EXPIRED`, `USE_RESUME_ACTION`, `USE_CONFIRM_OR_RESUME_ACTION`, `USE_VENDOR_RESPONSE_ACTION`, `ACTIVE_VENDOR_REQUEST_EXISTS`, `NO_ACTIVE_VENDOR_REQUEST`, `UPLOAD_NOT_READY`, `UPLOAD_SESSION_EXPIRED`, `TICKET_CLOSED`, `ATTACHMENT_TOO_LARGE`, `UNSUPPORTED_ATTACHMENT_TYPE`, `UPLOAD_INTEGRITY_MISMATCH`, `CLOSE_ACKNOWLEDGEMENT_REQUIRED`, `STORAGE_UNAVAILABLE`, `SERVICE_UNAVAILABLE`

### ErrorBody

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `code` | ErrorCode | Yes |  | Stable application error code. |
| `message` | string | Yes |  | Safe error message. |
| `details` | map<string, any> | Yes |  | Safe details; no secrets/stack traces. |
| `request_id` | string(uuid) | Yes |  | Correlation ID. |

### ErrorResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `error` | ErrorBody | Yes |  |  |

### PaginationMeta

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `page` | integer | Yes | min: 1 | Current page. |
| `page_size` | integer | Yes | min: 1; max: 100 | Page size. |
| `total` | integer | Yes | min: 0 | Total records. |
| `total_pages` | integer | Yes | min: 0 | Total pages. |

### ActorSummary

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `user_id` | integer(int64) | Yes |  | User ID. |
| `display_name` | string | Yes |  | Safe display name. |
| `role` | Role | Yes |  | Authenticated actor role. |

### RequesterSummary

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `user_id` | integer(int64) | Yes |  | Requester ID. |
| `display_name` | string | Yes |  | Requester display name. |

### AssigneeSummary

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `user_id` | integer(int64) | Yes |  | Engineer ID. |
| `display_name` | string | Yes |  | Engineer display name. |
| `tier` | string | Yes | enum: TIER1, TIER2 | Engineer tier. |
| `skills` | array<Category> | Yes |  | Skill categories. |
| `is_available` | boolean | Yes |  | Availability. |
| `active_load` | integer | Yes | min: 0 | Current active load. |

### VendorOrganisation

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `vendor_org_id` | integer(int64) | Yes |  | Vendor organisation ID. |
| `name` | string | Yes | minLength: 1; maxLength: 200 | Organisation name. |
| `is_active` | boolean | Yes |  | May receive new requests. |

### UserProfile

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `user_id` | integer(int64) | Yes |  | User ID. |
| `email` | string(email) | Yes |  | Login email. |
| `display_name` | string | Yes | minLength: 1; maxLength: 100 | Display name. |
| `role` | Role | Yes |  | Authenticated actor role. |
| `is_available` | boolean | null | Yes |  |  |
| `vendor_org` | VendorOrganisation | null | Yes |  |  |
| `created_at` | string(date-time) | Yes |  | Account creation time. |

### UserResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | UserProfile | Yes |  |  |

### RegisterRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `email` | string(email) | Yes | maxLength: 254 | Unique email. |
| `password` | string(password) | Yes | minLength: 8; maxLength: 128 | Password; write-only. |
| `display_name` | string | Yes | minLength: 1; maxLength: 100 | Display name. |

### LoginRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `email` | string(email) | Yes |  | Registered email. |
| `password` | string(password) | Yes | minLength: 1; maxLength: 128 | Password. |

### LoginData

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `access_token` | string | Yes |  | JWT. |
| `token_type` | string | Yes | enum: bearer | Token type. |
| `expires_in` | integer | Yes | min: 1 | Lifetime seconds. |
| `user` | UserProfile | Yes |  |  |

### LoginResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | LoginData | Yes |  |  |

### UpdateProfileRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `display_name` | string | No | minLength: 1; maxLength: 100 | New display name. |
| `is_available` | boolean | No |  | Engineer availability; forbidden for non-engineers. |

### AttachmentTypeRule

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `extension` | string | Yes |  | Lowercase extension. |
| `content_type` | string | Yes |  | Required MIME. |

### AttachmentConfig

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `max_size_bytes` | integer | Yes | const: 10485760 | Max bytes. |
| `upload_url_ttl_seconds` | integer | Yes | const: 900 | PUT TTL. |
| `download_url_ttl_seconds` | integer | Yes | const: 300 | GET TTL. |
| `allowed_types` | array<AttachmentTypeRule> | Yes |  | Allowed pairs. |

### TimerConfig

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `engineering_sla_hours` | integer | Yes | const: 48 | SLA hours. |
| `at_risk_percent` | integer | Yes | const: 80 | AT_RISK percentage. |
| `user_response_hours` | integer | Yes | const: 120 | User response hours. |
| `resolved_window_hours` | integer | Yes | const: 168 | Resolved window hours. |

### ReferenceData

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `categories` | array<Category> | Yes |  | Categories. |
| `priorities` | array<Priority> | Yes |  | Priorities. |
| `ticket_statuses` | array<TicketStatus> | Yes |  | Role-visible statuses. |
| `comment_visibilities` | array<CommentVisibility> | Yes |  | Allowed comment visibility. |
| `attachment_visibilities` | array<AttachmentVisibility> | Yes |  | Allowed attachment visibility. |
| `attachment` | AttachmentConfig | Yes |  |  |
| `timers` | TimerConfig | Yes |  |  |

### ReferenceDataResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | ReferenceData | Yes |  |  |

### AssigneeListResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | array<AssigneeSummary> | Yes |  | Engineers. |
| `meta` | PaginationMeta | Yes |  |  |

### VendorListResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | array<VendorOrganisation> | Yes |  | Vendors. |
| `meta` | PaginationMeta | Yes |  |  |

### SlaView

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `cycle_no` | integer | Yes | min: 1 | Current cycle. |
| `status` | SlaStatus | Yes |  | Engineering SLA status. |
| `started_at` | string(date-time) | null | Yes |  |  |
| `deadline` | string(date-time) | null | Yes |  |  |

### PendingUserView

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `reason` | PendingUserReason | Yes |  | Why the ticket waits for USER. |
| `deadline` | string(date-time) | Yes |  | User deadline. |

### ResolutionView

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `summary` | string | Yes | minLength: 1; maxLength: 5000 | User-visible resolution. |
| `type` | string \| null | Yes | enum: USER_CONFIRMED, AUTO_NO_USER_RESPONSE, AUTO_CONFIRMATION_TIMEOUT | null in PENDING_USER/RESOLUTION_CONFIRMATION; populated after formally entering RESOLVED. |
| `resolved_at` | string(date-time) \| null | Yes |  | null in PENDING_USER/RESOLUTION_CONFIRMATION; the time the ticket formally entered RESOLVED. |
| `auto_close_at` | string(date-time) \| null | Yes |  | null in PENDING_USER/RESOLUTION_CONFIRMATION; resolved_at + 7 days after formally entering RESOLVED. |

`resolution` is returned immediately after the engineer calls API-28 so the requester can view the pending `summary`; the three completion fields are all `null` at this point. They become non-null only after API-29 confirmation or an automatic outcome.

### ClosureView

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `type` | string | Yes | enum: MANUAL_USER, AUTO_AFTER_7_DAYS | Closure type. |
| `closed_at` | string(date-time) | Yes |  | Closed time. |

### VendorRequestView

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `vendor_request_id` | integer(int64) | Yes |  | Request ID. |
| `vendor_org` | VendorOrganisation | Yes |  |  |
| `status` | VendorRequestStatus | Yes |  | Vendor request status. |
| `vendor_message` | string | Yes | maxLength: 4000 | Vendor-safe message. |
| `created_at` | string(date-time) | Yes |  | Created. |
| `responded_at` | string(date-time) | null | Yes |  |  |

### TicketSummary

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `ticket_id` | integer(int64) | Yes |  | Ticket ID. |
| `title` | string | Yes | minLength: 1; maxLength: 200 | Title. |
| `category` | Category | Yes |  | Ticket category. |
| `priority` | Priority | Yes |  | Ticket priority. |
| `status` | TicketStatus | Yes |  | Role-visible lifecycle status; USER receives IN_PROGRESS instead of internal PENDING_VENDOR. |
| `display_status` | string | Yes |  | Role-aware status. |
| `assignee` | AssigneeSummary | null | Yes |  |  |
| `sla` | SlaView | null | Yes |  |  |
| `available_actions` | array<AvailableAction> | Yes |  | Available actions. |
| `created_at` | string(date-time) | Yes |  | Created. |
| `updated_at` | string(date-time) | Yes |  | Updated. |

### TicketDetail

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `ticket_id` | integer(int64) | Yes |  | Ticket ID. |
| `title` | string | Yes | minLength: 1; maxLength: 200 | Title. |
| `description` | string | null | Yes |  |  |
| `category` | Category | Yes |  | Ticket category. |
| `priority` | Priority | Yes |  | Ticket priority. |
| `status` | TicketStatus | Yes |  | Role-visible lifecycle status; USER receives IN_PROGRESS instead of internal PENDING_VENDOR. |
| `display_status` | string | Yes |  | Role-aware status. |
| `requester` | RequesterSummary | null | Yes |  |  |
| `assignee` | AssigneeSummary | null | Yes |  |  |
| `sla` | SlaView | null | Yes |  |  |
| `pending_user` | PendingUserView | null | Yes |  |  |
| `resolution` | ResolutionView | null | Yes |  |  |
| `closure` | ClosureView | null | Yes |  |  |
| `vendor_request` | VendorRequestView | null | Yes |  |  |
| `available_actions` | array<AvailableAction> | Yes |  | Available actions. |
| `created_at` | string(date-time) | Yes |  | Created. |
| `updated_at` | string(date-time) | Yes |  | Updated. |

### TicketCreateRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `title` | string | Yes | minLength: 1; maxLength: 200 | Title. |
| `description` | string | Yes | minLength: 1; maxLength: 5000 | Description. |
| `category` | Category | Yes |  | Ticket category. |
| `priority` | Priority | Yes |  | Ticket priority. |

### TicketUpdateRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `title` | string | No | minLength: 1; maxLength: 200 | New title. |
| `description` | string | No | minLength: 1; maxLength: 5000 | New description. |
| `category` | Category | No |  | Ticket category. |
| `priority` | Priority | No |  | Ticket priority. |

### TicketDetailResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | TicketDetail | Yes |  | Role-aware unavailable fields are present with JSON null. |

### TicketListResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | array<TicketSummary> | Yes |  | Tickets. |
| `meta` | PaginationMeta | Yes |  |  |

### Comment

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `comment_id` | integer(int64) | Yes |  | Comment ID. |
| `ticket_id` | integer(int64) | Yes |  | Ticket ID. |
| `author` | ActorSummary | Yes |  |  |
| `message` | string | Yes | minLength: 1; maxLength: 4000 | Message. |
| `visibility` | CommentVisibility | Yes |  | Comment visibility. |
| `created_at` | string(date-time) | Yes |  | Created. |

### CommentCreateRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `message` | string | Yes | minLength: 1; maxLength: 4000 | Message. |
| `visibility` | CommentVisibility | Yes |  | Comment visibility. |

### CommentResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | Comment | Yes |  |  |

### CommentListResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | array<Comment> | Yes |  | Comments. |
| `meta` | PaginationMeta | Yes |  |  |

### AssignmentRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `assignee_id` | integer(int64) | Yes |  | Target engineer. |
| `reason` | string | No | minLength: 1; maxLength: 1000 | Reason. |

### RequestUserInfoRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `message` | string | Yes | minLength: 1; maxLength: 4000 | User-visible request. |

### ResumeRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `message` | string | Yes | minLength: 1; maxLength: 4000 | Information or issue-persists explanation. |

### EscalateRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `tier2_assignee_id` | integer(int64) | Yes |  | Tier 2 ID. |
| `reason` | string | No | minLength: 1; maxLength: 1000 | Reason. |

### VendorRequestCreate

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `vendor_org_id` | integer(int64) | Yes |  | Vendor organisation ID. |
| `vendor_message` | string | Yes | minLength: 1; maxLength: 4000 | Vendor-safe message. |

### VendorResponseRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `message` | string | Yes | minLength: 1; maxLength: 4000 | Vendor response. |

### ResolveRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `resolution_summary` | string | Yes | minLength: 1; maxLength: 5000 | User-visible resolution. |

### ReopenRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `reason` | string | Yes | minLength: 1; maxLength: 4000 | Why issue persists. |

### CloseRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `acknowledge` | boolean | Yes | const: true | Must be true. |
| `reason` | string | No | minLength: 1; maxLength: 1000 | Optional note. |

### VendorResponseView

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `vendor_response_id` | integer(int64) | Yes |  | Response ID. |
| `vendor_request_id` | integer(int64) | Yes |  | Request ID. |
| `message` | string | Yes | maxLength: 4000 | Response. |
| `created_at` | string(date-time) | Yes |  | Created. |

### TicketActionData

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `action` | AvailableAction | Yes |  | Action currently available to actor. |
| `ticket` | TicketDetail | Yes |  | Role-aware unavailable fields are present with JSON null. |
| `event_id` | integer(int64) | Yes |  | Audit event ID. |
| `comment_id` | integer(int64) | null | Yes |  |  |
| `vendor_request` | VendorRequestView | null | Yes |  |  |
| `vendor_response` | VendorResponseView | null | Yes |  |  |

### TicketActionResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | TicketActionData | Yes |  |  |

### Attachment

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `attachment_id` | string(uuid) | Yes |  | Attachment UUID. |
| `ticket_id` | integer(int64) | Yes |  | Ticket ID. |
| `file_name` | string | Yes | minLength: 1; maxLength: 255 | File name. |
| `content_type` | string | Yes | enum: image/png, image/jpeg, application/pdf, text/plain | Verified MIME. |
| `size_bytes` | integer | Yes | min: 1; max: 10485760 | Verified bytes. |
| `visibility` | AttachmentVisibility | Yes |  | Attachment visibility. |
| `created_at` | string(date-time) | Yes |  | Created. |

### PresignRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `file_name` | string | Yes | minLength: 1; maxLength: 255 | Base file name. |
| `content_type` | string | Yes | enum: image/png, image/jpeg, application/pdf, text/plain | Expected MIME. |
| `size_bytes` | integer | Yes | min: 1; max: 10485760 | Expected bytes. |
| `visibility` | AttachmentVisibility | Yes |  | Attachment visibility. |

### PresignData

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `upload_id` | string(uuid) | Yes |  | Upload UUID. |
| `upload_url` | string(uri) | Yes |  | Opaque PUT URL. |
| `method` | string | Yes | enum: PUT | Method. |
| `signed_headers` | map<string, any> | Yes |  | Send unchanged to S3. |
| `expires_at` | string(date-time) | Yes |  | Expiry. |
| `max_size_bytes` | integer | Yes | const: 10485760 | Max bytes. |

### PresignResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | PresignData | Yes |  |  |

### CompleteUploadRequest

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `upload_id` | string(uuid) | Yes |  | Only accepted field. |

### AttachmentResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | Attachment | Yes |  |  |

### AttachmentListResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | array<Attachment> | Yes |  | Attachments. |
| `meta` | PaginationMeta | Yes |  |  |

### DownloadData

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `attachment_id` | string(uuid) | Yes |  | Attachment UUID. |
| `file_name` | string | Yes |  | File name. |
| `content_type` | string | Yes |  | MIME. |
| `download_url` | string(uri) | Yes |  | Opaque GET URL. |
| `expires_at` | string(date-time) | Yes |  | Expiry. |

### DownloadResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | DownloadData | Yes |  |  |

### HealthData

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `status` | string | Yes | enum: ok | State. |
| `service` | string | Yes |  | Service. |
| `version` | string | Yes |  | Git SHA/release. |
| `timestamp` | string(date-time) | Yes |  | Current UTC. |
| `checks` | object | Yes |  |  |

### HealthResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | HealthData | Yes |  |  |

### DashboardCounts

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `total_active` | integer | Yes | min: 0 | Active total. |
| `unassigned` | integer | Yes | min: 0 | UNASSIGNED. |
| `assigned` | integer | Yes | min: 0 | ASSIGNED. |
| `in_progress` | integer | Yes | min: 0 | IN_PROGRESS. |
| `pending_user` | integer | Yes | min: 0 | PENDING_USER. |
| `pending_vendor` | integer | Yes | min: 0 | PENDING_VENDOR. |
| `resolved` | integer | Yes | min: 0 | RESOLVED. |
| `reopened` | integer | Yes | min: 0 | REOPENED. |
| `closed` | integer | Yes | min: 0 | CLOSED. |

### DashboardSummaryData

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `scope` | string | Yes | enum: GLOBAL, MY_ASSIGNED | Role-derived scope. |
| `generated_at` | string(date-time) | Yes |  | Snapshot. |
| `counts` | DashboardCounts | Yes |  |  |
| `sla` | object | Yes |  |  |
| `action_required` | object | Yes |  |  |

### DashboardSummaryResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | DashboardSummaryData | Yes |  |  |

### OverdueTicket

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `ticket_id` | integer(int64) | Yes |  | Ticket ID. |
| `title` | string | Yes |  | Title. |
| `category` | Category | Yes |  | Ticket category. |
| `priority` | Priority | Yes |  | Ticket priority. |
| `status` | TicketStatus | Yes |  | Role-visible lifecycle status; USER receives IN_PROGRESS instead of internal PENDING_VENDOR. |
| `display_status` | string | Yes |  | Role-aware status. |
| `assignee` | AssigneeSummary | null | Yes |  |  |
| `sla_cycle_no` | integer | Yes | min: 1 | Cycle. |
| `sla_deadline` | string(date-time) | Yes |  | Deadline. |
| `overdue_at` | string(date-time) | Yes |  | Overdue event. |
| `is_current` | boolean | Yes |  | Still current. |

### OverdueMeta

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `page` | integer | Yes | min: 1 | Page. |
| `page_size` | integer | Yes | min: 1; max: 100 | Size. |
| `total` | integer | Yes | min: 0 | Total. |
| `total_pages` | integer | Yes | min: 0 | Pages. |
| `mode` | string | Yes | enum: current, history | Mode. |

### OverdueListResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | array<OverdueTicket> | Yes |  | Overdue items. |
| `meta` | OverdueMeta | Yes |  |  |

### TicketEvent

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `event_id` | integer(int64) | Yes |  | Event ID. |
| `ticket_id` | integer(int64) | Yes |  | Ticket ID. |
| `event_type` | EventType | Yes |  | Stable event type. |
| `scope` | EventScope | Yes |  | Audit-event scope. |
| `actor` | ActorSummary | null | Yes |  |  |
| `cycle_no` | integer | null | Yes |  |  |
| `occurred_at` | string(date-time) | Yes |  | Event time. |
| `metadata` | map<string, any> | Yes |  | Role-filtered minimal metadata. |

### EventListResponse

| Field | Type | Required | Constraints | Description |
|---|---|---:|---|---|
| `data` | array<TicketEvent> | Yes |  | Events. |
| `meta` | PaginationMeta | Yes |  |  |

## 8. Development Delivery Rules

- Each API owner submits the router, Pydantic schemas, service, repository, unit/contract tests and OpenAPI changes in the same PR.
- D (Yiguang Sun) generates TypeScript types and mocks only from merged OpenAPI YAML/JSON.
- CI must verify that the running FastAPI `/api/openapi.json` has no path, method or schema drift from this contract.
- Any change to requests, responses or error codes requires review by the affected members among A (BIN LIN)/B (Yujuan Gao)/C (Andy Wen)/D (Yiguang Sun).
- A successful Swagger call does not establish completion; tests must cover roles, resource hiding through 404, state boundaries, transactions, idempotency and error paths.

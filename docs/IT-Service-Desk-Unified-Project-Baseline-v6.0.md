# IT Service Desk and Incident Ticketing System

> **Team member reference:** Throughout this document, A = BIN LIN; B = Yujuan Gao; C = Andy Wen; D = Yiguang Sun.

## Unified Project Development Baseline

**Course**: INFS803 Cloud Computing  
**Assignment**: Option B - Cloud Web Application Development and Deployment  
**Version**: v6.0  
**Date**: 2026-09-01  
**Due**: 2026-10-16  
**Status**: Unified v6.0 process baseline; current repository locations are recorded below

> **Repository layout update — 2026-10-07:** Sections 7.5–7.6 and the file references in this document were checked against GitHub `main` at [`379bb53`](https://github.com/infs803-group8/ITSM/tree/379bb531504e78b2b293564b070f8af33b85449c). The original 32-operation API inventory is retained as the v6.0 process baseline. The current 33-operation implementation contract, including vendor request history, is [`backend/contracts/openapi.yaml`](../backend/contracts/openapi.yaml), with its [JSON counterpart](../backend/contracts/openapi.json). Use those files for client generation and contract tests.

> This document is the current baseline for development, testing, integration, deployment and reporting. Earlier documents are historical references only; this document takes precedence over conflicting diagrams, API descriptions or chat records. Version 6.0 retains the business roles, main flow, state machine, responsibilities and 32 APIs from v5.0, while correcting the database and frontend contracts: all environments use the complete `service_desk` database; `backend/database/schema.sql` is the sole executable schema contract and SQLAlchemy models must match it; required fields in OpenAPI v1.1 are always present, returning `null` when they have no business value or are hidden from the current role; and all 32 APIs provide examples suitable for frontend mocks.

---

## 1. Scope and Current Decisions

### 1.1 Mandatory Assignment Requirements

- Use a three-tier architecture comprising a client, backend and cloud database.
- Deploy both client and backend to the cloud and provide publicly accessible URLs.
- Allow the marker to call the backend REST API directly, bypassing the frontend.
- Provide at least 10 REST APIs, including at least three POST endpoints; list all endpoints and URLs in the report.
- Use a cloud database and cloud object storage for files.
- Collaborate through a cloud Git repository without rewriting Git history.
- Keep frontend and backend URLs accessible from submission until marking is complete.
- Include member contributions, the project plan, architecture, cloud implementation, user manual, API list, presentation link, Trello/worklog evidence and AI usage declaration in the report.

### 1.2 Technology and Architecture Decisions

| Area | Current Decision |
|---|---|
| Frontend | React, TypeScript, Vite, Ant Design, React Router, Axios |
| Backend | Python, FastAPI, Uvicorn, SQLAlchemy, PyMySQL |
| Database | Use `service_desk` as the database name throughout; A (BIN LIN)/B (Yujuan Gao)/C (Andy Wen) each use an independent local MySQL 8.4 instance during feature development; use Amazon RDS for MySQL 8.4 for the final environment |
| Database Initialisation | `backend/database/schema.sql` is the sole executable schema contract; run the same file on empty local and RDS databases to create all 19 tables; SQLAlchemy models must match field by field; CI verifies schema drift |
| File Storage | Private Amazon S3; browsers use Presigned PUT, and the backend verifies uploads with `HeadObject` |
| Compute | Amazon ECS on AWS Fargate; separate ECS services for frontend and backend |
| Public Entry | CloudFront default HTTPS domain → internet-facing ALB; route `/api/*` to the backend and all other paths to the frontend |
| Background Jobs | EventBridge Scheduler launches short-lived ECS tasks; the SLA and attachment cleanup jobs run separately |
| Registry / Logs | Amazon ECR, CloudWatch Logs |
| Secrets / AWS Auth | AWS Secrets Manager stores DB/JWT secrets; GitHub Actions uses OIDC AssumeRole without storing long-term AWS keys |
| CI/CD | Manually dispatched GitHub Actions in `.github/workflows/backend.yml` and `.github/workflows/frontend.yml`, using `.github/actions/manual-ecs/action.yml`; release scripts and environment configuration are under `infrastructure/` |
| Infrastructure as Code | Terraform; `dev-storage` creates only the development S3 resources, while `final` creates the final AWS infrastructure |
| Repository | GitHub monorepo; three Backend members and one Frontend member |
| Project Manager | Member C (Andy Wen); coordinates work and checks evidence, while each owner remains responsible for updating tasks and completing tests |

### 1.2.1 Current Contract Documents and Precedence

| Area | Repository path(s) | Governs |
|---|---|---|
| Business flows, roles, responsibilities and milestones | `docs/IT-Service-Desk-Unified-Project-Baseline-v6.0.md` | Original v6.0 process baseline; sections 7.5–7.6 describe the current repository layout and ownership. |
| Original HTTP API specification | `docs/IT-Service-Desk-Final-API-Specification-v1.1.md` and `docs/IT-Service-Desk-OpenAPI-v1.1.yaml` | The retained 32-operation baseline specification and snapshot. |
| Current implementation API contract | `backend/contracts/openapi.yaml` and `backend/contracts/openapi.json` | The 33-operation contract used by the current implementation, frontend generation and contract tests. |
| Database field descriptions | `docs/IT-Service-Desk-Database-Final-Design-v1.1.md` | Business meaning, relationships and fields of the 19 tables. |
| Executable database schema | `backend/database/schema.sql` | Sole executable schema contract for local and RDS databases; derived from the original `IT-Service-Desk-MySQL-Schema-v1.0.sql` baseline. |

Use the current implementation contract for API integration and the canonical SQL for the executable database schema. The original 32-operation process documents do not supersede the later API-33 addition. All four process files are directly under `docs/`; the former documentation subdirectories are no longer present.

### 1.3 MVP Constants

| Item | Value |
|---|---|
| Categories | NETWORK, HARDWARE, SOFTWARE, ACCOUNT, OTHER |
| Priorities | LOW, MEDIUM, HIGH, URGENT |
| Engineering SLA | Initially 48 continuous hours for every priority; AT_RISK begins at 80%, or 38h24m |
| User Response Window | Five calendar days (120 continuous hours) |
| RESOLVED Window | Seven calendar days; automatically CLOSED on expiry |
| Attachment Limit | 10 MB per file; PNG, JPG, PDF, TXT, LOG |
| Upload URL TTL | 15 minutes |
| Time Format | UTC ISO 8601 |
| Notifications | Yellow/red indicators in dashboards/lists; the MVP does not implement email, SMS, SNS or push notifications |

---

## 2. Roles and Data Visibility

### 2.1 Roles

| Role | Main Permissions |
|---|---|
| USER | Manage their own tickets; comment, upload, provide information and confirm resolutions; reopen or manually close within the RESOLVED window |
| ENGINEER_TIER1 | Handle assigned tickets; request information, submit resolutions and escalate to Tier 2 |
| ENGINEER_TIER2 | Handle Tier 2 tickets; collaborate with vendors; always remain responsible for submitting the final resolution to the user |
| EXTERNAL_VENDOR | Access only their organisation's vendor scope; respond and upload `VENDOR_SHARED` attachments while a request is active |
| SERVICE_DESK_MANAGER | View the global dashboard; handle UNASSIGNED, OVERDUE and reassignment according to the rules |

Public registration creates USER accounts only. Tier 1, Tier 2, vendor and manager accounts are created through controlled seed/administration processes. Hiding frontend buttons is only a usability measure; the backend must validate role, resource scope, current state and `available_actions`.

### 2.2 Role × Data Visibility

| Role | Ticket / User Data | Comments | Attachments | SLA / Assignee | Vendor / Events |
|---|---|---|---|---|---|
| User | User-facing schema and current `resolution_summary` for their own tickets; their own profile only | USER_VISIBLE only | USER_VISIBLE only | Current user-facing SLA, deadline and assignee display name | USER_VISIBLE events only; vendor data and PENDING_VENDOR are completely hidden |
| Tier 1 | Currently assigned tickets; limited user contact information | USER_VISIBLE, INTERNAL_ONLY | USER_VISIBLE, INTERNAL_ONLY | Current and historical | Internal timeline, excluding vendor payloads |
| Tier 2 | Currently assigned tickets; limited user contact information | USER_VISIBLE, INTERNAL_ONLY | All three visibility types | Current and historical | Full timeline and vendor data within the authorised scope |
| Vendor | `ticket_id`, title, category, priority and their organisation's `vendor_message`; no user personal data/description | No ordinary comment access | VENDOR_SHARED for their organisation only | Hidden | Only their organisation's active/historical vendor threads and VENDOR_SCOPE events |
| Manager | All internal data | All | All | All | Complete audit timeline |

Key rules:

- PENDING_VENDOR is an internal ticket state visible to Tier 2/managers. Users see `display_status=IN_PROGRESS` and "Tier 2 Engineer is working"; vendors see only ACTIVE/RESPONDED/CANCELLED for their own VendorRequest and `available_actions`.
- Vendor scope is authorised by `VendorRequest.vendor_org_id = JWT vendor_org_id`. Historical requests retain read access to the organisation's own threads, events and VENDOR_SHARED attachments, but not subsequent internal handling or other vendors' data.
- Vendors may call API-27, upload VENDOR_SHARED attachments or receive the VENDOR_RESPONSE action only when their organisation has the ticket's sole active VendorRequest.
- Tier 2 writes API-26's `vendor_message` separately. The frontend warns against including user names, email addresses or user IDs. The backend must not automatically copy the ticket description, profile, comments, resolution or event payload. The MVP does not promise automatic detection of sensitive text manually entered by Tier 2.
- Comment visibility is USER_VISIBLE or INTERNAL_ONLY. API-23 information requests, API-24 user replies and API-28 `resolution_summary` are USER_VISIBLE. Ordinary comments do not trigger Resume, Confirm Resolution or Vendor Response. Users calling API-20 in PENDING_USER must be directed to API-24/API-29; vendors calling API-20 in PENDING_VENDOR must be directed to API-27. Other authorised ordinary comments create only comments/events, without changing state or timers.
- Attachment visibility is USER_VISIBLE, INTERNAL_ONLY or VENDOR_SHARED. The backend must bind VENDOR_SHARED to the current active `vendor_request_id` and `vendor_org_id`.
- TicketEvent scope is USER_VISIBLE, INTERNAL_ONLY or VENDOR_SCOPE. `COMMENT_ADDED` inherits the associated comment's visibility and stores only `comment_id`. Lists filter out unauthorised data; requests for hidden resources by ID consistently return 404 `RESOURCE_NOT_FOUND`.
- No response may return password hashes, JWTs, reset tokens, MFA secrets, AWS credentials or database credentials.

---

## 3. Core Data Model

### 3.1 Business Objects

| Object | Owner | Key Fields / Constraints |
|---|---|---|
| User | B (Yujuan Gao) | role, is_available, skills, vendor_org_id, last_assigned_at |
| Ticket | B (Yujuan Gao) | user_id, title, description, category, priority, status, assignee_id; `sla_cycle_no/status/started_at/deadline`; `pending_user_reason/deadline`; `resolution_summary/type/resolved_at/auto_close_at`; `closure_type/closed_at` |
| Comment | B (Yujuan Gao) | ticket_id, author_id, message, visibility; formal workflow comments are created by C (Andy Wen)'s service through B (Yujuan Gao)'s repository |
| AttachmentUpload | A (BIN LIN) | `upload_id`, ticket_id, creator_id, object_key, original file attributes, visibility, vendor binding, status, expires_at |
| Attachment | A (BIN LIN) | attachment_id, `upload_id` unique, ticket_id, object_key, verified_size/content_type, visibility, Vendor Binding |
| VendorRequest / VendorResponse | C (Andy Wen) | At most one ACTIVE request per ticket at a time; requests bind vendor_org_id and `vendor_message` |
| TicketEvent | C (Andy Wen) | Append-only; event_type, actor, scope, cycle and necessary metadata; no copying of complete comments |
| AssignmentControl | C (Andy Wen) | Singleton row; serialises the brief candidate-selection phase of initial automatic assignment |

Current workflow fields remain in the Ticket table; B (Yujuan Gao) maintains the model file and C (Andy Wen) defines the semantics. A (BIN LIN)/B (Yujuan Gao)/C (Andy Wen) each maintain their domain's SQLAlchemy models. B (Yujuan Gao) maintains `model_registry.py` and coordinates cross-domain foreign keys and full schema review. During feature development, schema changes must first update the models, then be verified by deleting and rebuilding each member's empty local database; manual table changes in MySQL Workbench alone are not allowed. If the final RDS schema must change after schema freeze, use a separate, reviewed SQL patch and record its execution results in the runbook.

### 3.2 AttachmentUpload: The Missing Upload Object

`AttachmentUpload` is the persistent upload session between Presign and Attachment. Without it, API-03 cannot reliably prove that the object_key, file attributes, visibility, vendor binding and uploader originated from API-02.

Minimum fields:

| Field | Rule |
|---|---|
| upload_id | UUID; the sole identifier used by the client for the subsequent Complete call |
| ticket_id / creator_id | Fixed bindings to the ticket and the actor who initiated Presign |
| object_key | Backend-generated and unique, e.g. `{environment}/pending/{ticket_id}/{upload_id}` |
| file_name | Display only; API-03 does not allow it to be overridden |
| expected_content_type / expected_size | Stored after API-02 validation; compared against S3 HeadObject by API-03 |
| visibility | Set and stored by API-02 according to the role |
| vendor_request_id / vendor_org_id | VENDOR_SHARED only; the backend binds them from the current active request |
| status | PENDING, COMPLETED, EXPIRED, ABORTED |
| expires_at / completed_at | URL expiry and completion time |
| attachment_id | Links the final attachment after COMPLETED; unique |

Upload flow:

1. API-02 locks and rereads the ticket, rejects CLOSED, and validates role, file type/size, visibility and the active VendorRequest.
2. The backend creates `AttachmentUpload(status=PENDING)`, generates an unpredictable object_key, then returns `upload_id`, the Presigned PUT URL, required signed headers and `expires_at`. The frontend does not submit object_key or vendor binding.
3. The browser PUTs directly to private S3; a successful upload does not automatically turn the S3 object into an attachment.
4. The browser calls API-03 with only `upload_id`. The backend first reads the session and performs S3 `HeadObject`, then locks the ticket followed by AttachmentUpload in a transaction, using the shared lock order, and revalidates session state, ownership, deadline, ticket state and vendor binding.
5. If the actual size/content type differs from the session, mark it ABORTED and return `UPLOAD_INTEGRITY_MISMATCH`; if the object is missing, return `UPLOAD_NOT_READY`; if the session has expired, return `UPLOAD_SESSION_EXPIRED`.
6. On successful validation, the backend creates the attachment using only session and HeadObject values, sets Session=COMPLETED, records an `ATTACHMENT_ADDED` event and commits everything in one transaction. The unique constraint on `Attachment.upload_id` prevents duplicate registration.
7. Repeating API-03 for the same COMPLETED upload_id idempotently returns the original attachment without adding metadata or events. Requests for that upload_id by other users return 404.
8. If the ticket becomes CLOSED after Presign, API-03 marks the session ABORTED and returns `TICKET_CLOSED`, without creating an attachment/event. ABORTED is a technical cleanup state, not a business write to the closed ticket.
9. EventBridge Scheduler launches the `attachment_cleanup` ECS task every 30 minutes. It marks expired PENDING sessions as EXPIRED and deletes orphaned S3 objects belonging to EXPIRED/ABORTED sessions. It must never delete COMPLETED objects.

Minimum acceptance criteria: a valid upload creates exactly one attachment; tampering with file_name, visibility or vendor binding has no effect; repeated Complete calls are idempotent; tests cover expiry, oversized files, type mismatches, another user's upload_id, closure after Presign and cleanup races.

---

## 4. Workflow, SLA and Concurrency

### 4.1 Lifecycle States

| Status | Meaning |
|---|---|
| NEW | Exists only momentarily within the API-15 creation transaction; must become ASSIGNED or UNASSIGNED before commit |
| UNASSIGNED | No eligible automatic assignment candidate |
| ASSIGNED | Assigned, but work has not started |
| IN_PROGRESS | An engineer is handling the ticket |
| PENDING_USER | Waiting for the user; `pending_user_reason` distinguishes the two workflows |
| PENDING_VENDOR | Internal collaboration between Tier 2 and a vendor; the user still sees IN_PROGRESS |
| RESOLVED | Resolution confirmed, or no user response for five days; retains a seven-day Reopen/Manual Close window |
| REOPENED | The user reopened the ticket within the RESOLVED window; a new Engineering SLA cycle starts immediately |
| CLOSED | Terminal state; read-only, with all business writes rejected |

~~~mermaid
stateDiagram-v2
    [*] --> ASSIGNED: API-15 auto assign
    [*] --> UNASSIGNED: no Tier 1 candidate
    UNASSIGNED --> ASSIGNED: Manager assign
    ASSIGNED --> IN_PROGRESS: Start
    REOPENED --> IN_PROGRESS: Original/new assignee Start
    IN_PROGRESS --> ASSIGNED: Escalate Tier 2 / overdue reassign
    IN_PROGRESS --> PENDING_USER: Request information
    PENDING_USER --> IN_PROGRESS: User Resume / issue persists
    IN_PROGRESS --> PENDING_VENDOR: Tier 2 request Vendor
    PENDING_VENDOR --> IN_PROGRESS: Vendor response
    IN_PROGRESS --> PENDING_USER: Submit resolution
    PENDING_VENDOR --> PENDING_USER: Tier 2 resolves without Vendor
    PENDING_USER --> RESOLVED: Confirm or 5-day timeout
    RESOLVED --> REOPENED: Reopen before auto_close_at
    RESOLVED --> CLOSED: Manual Close or 7-day Auto Close
    CLOSED --> [*]
~~~

### 4.2 Engineering SLA and User Timers

- Each Engineering SLA cycle lasts 48 continuous hours. UNASSIGNED, ASSIGNED, IN_PROGRESS, PENDING_VENDOR and REOPENED continue the current cycle.
- Tier 1→Tier 2 escalation, manager reassignment and vendor requests/responses do not reset the cycle.
- At 80%, record an AT_RISK event and display yellow; at 48 hours, record an OVERDUE event and display red. AT_RISK/OVERDUE are SLA statuses, not lifecycle states.
- Request User Info: enter PENDING_USER + INFORMATION_REQUIRED, end the current cycle as PAUSED and start a 120h user timer. Resume before the deadline starts a new 48h cycle; timeout produces `AUTO_NO_USER_RESPONSE` and enters RESOLVED.
- Submit Resolution: enter PENDING_USER + RESOLUTION_CONFIRMATION, fix the cycle outcome as MET/OVERDUE at submission and start a 120h timer. User confirmation enters RESOLVED; Issue Persists through API-24 returns to IN_PROGRESS and starts a new cycle; timeout produces `AUTO_CONFIRMATION_TIMEOUT`.
- Each entry into RESOLVED sets `auto_close_at=resolved_at+7 days`. Before the boundary, users may reopen or manually close after acknowledging irreversibility; the system closes automatically on expiry.
- `AUTO_NO_USER_RESPONSE` records the user-visible system explanation "Automatically resolved because no additional information was received within five days". `AUTO_CONFIRMATION_TIMEOUT` retains the engineer's original `resolution_summary` and adds the reason for automatic confirmation.
- The boundary is consistent: user actions are allowed only while `now < deadline`; `now >= deadline` applies the automatic outcome. API-24/API-29 and the SLA job share the same deadline enforcement.
- Historical cycles, resolutions and closures are appended to TicketEvent; a new cycle does not overwrite history.

### 4.3 Main Transitions

| Current / Condition | Action | Result | Actor |
|---|---|---|---|
| UNASSIGNED | Assign | ASSIGNED | Manager |
| ASSIGNED / REOPENED with assignee | Start | IN_PROGRESS | Assignee |
| IN_PROGRESS Tier 1 | Escalate | ASSIGNED to the selected Tier 2; preserve the cycle | Tier 1 |
| IN_PROGRESS | Request User Info | PENDING_USER/INFORMATION_REQUIRED; PAUSED | Assignee |
| PENDING_USER before deadline | Resume / Issue Persists | IN_PROGRESS; new cycle | User |
| PENDING_USER at/after deadline | Auto Resolve | RESOLVED; set auto_close_at | System/lazy enforcement |
| IN_PROGRESS Tier 2, no Active Request | Request Vendor | PENDING_VENDOR; create the sole ACTIVE request | Tier 2 |
| PENDING_VENDOR + matching Active Request | Vendor Response | IN_PROGRESS; Request=RESPONDED | Vendor |
| IN_PROGRESS | Submit Resolution | PENDING_USER/RESOLUTION_CONFIRMATION | Assignee |
| PENDING_VENDOR | Submit Resolution | Active Request=CANCELLED; PENDING_USER/RESOLUTION_CONFIRMATION | Tier 2 |
| RESOLUTION_CONFIRMATION before deadline | Confirm | RESOLVED | User |
| RESOLVED before auto_close_at | Reopen | REOPENED; new cycle; prefer the original assignee | User |
| RESOLVED before auto_close_at | Manual Close | CLOSED; MANUAL_USER | User |
| RESOLVED at/after auto_close_at | Auto Close | CLOSED; AUTO_AFTER_7_DAYS | System |

### 4.4 Initial Auto Assignment

API-15 considers only Tier 1 engineers with `is_available=true` and a skill matching the category. `active_load` counts only that engineer's tickets in ASSIGNED, IN_PROGRESS, PENDING_VENDOR or REOPENED. Selection uses the stable ordering `active_load ASC`, `last_assigned_at ASC` (NULL first), then `user_id ASC`. If no candidate is available, Ticket=UNASSIGNED.

The creation transaction first locks the singleton `AssignmentControl` row, then evaluates candidates, updates the ticket and `last_assigned_at`, and records an assignment event. Concurrent creations therefore see the previous result sequentially, instead of simultaneously favouring the same least-loaded engineer. The lock protects only the brief selection process and does not surround external calls.

### 4.5 API-21 Assign/Reassign Matrix

| Current State | Preconditions | Target | Result / Preserved Data |
|---|---|---|---|
| UNASSIGNED, not OVERDUE | assignee null | Tier 1 or Tier 2 | ASSIGNED; preserve the cycle started at creation |
| UNASSIGNED, OVERDUE | assignee null | Tier 2 | ASSIGNED; preserve the deadline/OVERDUE status |
| ASSIGNED/IN_PROGRESS, OVERDUE | new assignee differs | Tier 2 | ASSIGNED; preserve the deadline/OVERDUE status |
| PENDING_USER | Valid reason/deadline | Current Tier 1 may move to T1/T2; current Tier 2 may move only to T2 | Preserve PENDING_USER and the timer |
| PENDING_VENDOR, OVERDUE | Sole active request | Tier 2 | Preserve PENDING_VENDOR, request, vendor and deadline |
| REOPENED | assignee null; original assignee unavailable | Tier 1 or Tier 2 | ASSIGNED; preserve the reopen cycle |

Other combinations return 409 `INVALID_STATUS_TRANSITION`; CLOSED returns `TICKET_CLOSED`. The target engineer must be available and suitably qualified. Managers cannot arbitrarily change assignees in every state.

### 4.6 Vendor, Resolution, Reopen and CLOSED

- Each ticket may have at most one ACTIVE VendorRequest at a time. A database unique guard must ensure that only one concurrent API-26 call succeeds.
- API-27 does not accept `vendor_request_id` and handles only the sole current active request. Tier 2 may call API-28 without waiting for the vendor; the active request then becomes CANCELLED atomically.
- Historical vendor read access is retained by organisation, but only an active request grants response and upload permissions.
- Reopen prefers the assignee from the most recent RESOLVED state, whether Tier 1 or Tier 2. If that assignee is disabled/unavailable, set `assignee_id=null` and await manager action through API-21; do not default to Tier 1.
- CLOSED is the terminal, business-read-only state for the entire ticket resource. Ticket editing, commenting, Presign/Complete, Assign/Reassign, workflow actions and repeated Close are prohibited; reading previously authorised data remains allowed.
- Ordinary comments cannot replace API-24/API-27/API-29. Users in PENDING_USER and vendors in PENDING_VENDOR who call API-20 receive the corresponding action guidance error, with no comment/event written. Ordinary comments by other authorised roles do not change the workflow.
- At the 120h boundary, API-24/API-29 apply Auto Resolve before returning `USER_RESPONSE_WINDOW_EXPIRED`; at the seven-day boundary, API-30/API-31 apply Auto Close before returning `TICKET_CLOSED`. Scheduled jobs and these lazy checks use the same deadline service.

### 4.7 Transactions, Concurrency and Auditing

Workflow writes, the SLA job, API-18/API-20 and attachment Presign/Complete all reread and validate data before writing. The shared workflow order is:

1. Begin a transaction and lock the ticket using `SELECT ... FOR UPDATE`; lock VendorRequest/AttachmentUpload next if needed.
2. Revalidate role, assignee, reason, deadline, vendor organisation and action against the latest state.
3. Update the ticket and related business objects.
4. Append TicketEvent within the same transaction; roll back everything if event creation fails.
5. Return success after commit. Failed requests do not create failure events.

Row locks guarantee serial execution and revalidation, not that only the first request can succeed. A later action may succeed if it remains valid in the latest state; otherwise return 409. Auto Resolve, Auto Close, Vendor Response, Reopen and Manual Close must be idempotent or protected by unique constraints.

Required audit events cover Create/Auto Assignment, Assign/Reassign, Start, Comment Added, Cycle Start/PAUSED/AT_RISK/OVERDUE/MET, User Info Request/Resume, Vendor Request/Response/Cancel, Resolution Submit/Confirm/Timeout, Reopen, Manual/Auto Close and Attachment Added. TicketEvent is append-only, with no update/delete API. Cycle events use the `(ticket_id, cycle_no, event_type)` unique guard so job reruns do not duplicate AT_RISK/OVERDUE events.

---

## 5. Backend API Contract

### 5.1 Common Conventions and Errors

| Item | Convention |
|---|---|
| Local Base URL | `http://localhost:8000/api/v1` |
| Final Base URL | `https://<cloudfront-domain>/api/v1` |
| Swagger / OpenAPI | `/api/docs`, `/api/openapi.json` |
| Authentication | `Authorization: Bearer <access_token>` |
| Pagination | page starts at 1; page_size defaults to 20, maximum 100 |
| Success | `{ "data": ... }`; lists also include `meta` |
| Error | `{ "error": { "code", "message", "details", "request_id" } }` |
| Required/Null | Response fields listed in OpenAPI `required` must always be present; return JSON `null` when there is no current value or the field is hidden from the role. Do not inconsistently omit fields between requests |
| Frontend Mock | Each OpenAPI v1.1 operation includes at least one success example; generate frontend mocks and TypeScript types only from the merged contract |
| Local CORS | The backend allows the configured local frontend origin, defaulting to `http://localhost:5173`; the final deployment uses same-origin `/api/*` access through CloudFront |

| HTTP / Code | Meaning |
|---|---|
| 403 DATA_SCOPE_DENIED | The role is not permitted to use this data category/endpoint |
| 404 RESOURCE_NOT_FOUND | Missing or hidden; do not distinguish between them |
| 409 INVALID_STATUS_TRANSITION | The latest state does not permit the action |
| 409 USER_RESPONSE_WINDOW_EXPIRED | Auto Resolve has just been applied or was already applied; the frontend refreshes to RESOLVED |
| 409 USE_RESUME_ACTION / USE_CONFIRM_OR_RESUME_ACTION / USE_VENDOR_RESPONSE_ACTION | An ordinary comment is blocked because a formal workflow action is required |
| 409 ACTIVE_VENDOR_REQUEST_EXISTS / NO_ACTIVE_VENDOR_REQUEST | VendorRequest conflict |
| 409 UPLOAD_NOT_READY / UPLOAD_SESSION_EXPIRED | The S3 object cannot yet be verified, or the upload session has expired |
| 409 TICKET_CLOSED | Business write rejected because the ticket is CLOSED or lazy Auto Close has just been applied |
| 413 ATTACHMENT_TOO_LARGE | Exceeds 10 MB |
| 422 UNSUPPORTED_ATTACHMENT_TYPE / UPLOAD_INTEGRITY_MISMATCH | Unsupported file type or mismatched actual attributes |
| 422 CLOSE_ACKNOWLEDGEMENT_REQUIRED | Manual Close lacks acknowledgement that closure is irreversible |

### 5.2 API Inventory and Ownership by Functional Module

Numbering does not indicate call order. APIs are grouped by domain owner and functional module to reduce cross-member overlap: A (BIN LIN) owns API-01–07, B (Yujuan Gao) owns API-08–20, and C (Andy Wen) owns API-21–32.

| ID | Module | Method / Endpoint | Access | Core Rule | Owner |
|---:|---|---|---|---|---|
| 01 | System | GET `/health` | Public | Health/version/database | A (BIN LIN) |
| 02 | Attachment | POST `/tickets/{id}/attachments/presign` | Scoped Role | Create a PENDING AttachmentUpload; return upload_id and URL | A (BIN LIN) |
| 03 | Attachment | POST `/tickets/{id}/attachments/complete` | Presign Creator | Body contains only upload_id; verify with HeadObject; create the attachment idempotently | A (BIN LIN) |
| 04 | Attachment | GET `/tickets/{id}/attachments` | Scoped Role | Visibility/Organisation Filter | A (BIN LIN) |
| 05 | Attachment | GET `/tickets/{id}/attachments/{attachment_id}/download` | Scoped Role | Short-lived Presigned GET; hidden resources return 404 | A (BIN LIN) |
| 06 | Dashboard | GET `/dashboard/summary` | T1/T2/Manager | Counts, AT_RISK/OVERDUE, reopened_unassigned | A (BIN LIN) |
| 07 | Dashboard | GET `/dashboard/overdue-tickets` | T1/T2/Manager | current/history; history comes from TicketEvent | A (BIN LIN) |
| 08 | Auth | POST `/auth/register` | Public | Create USER accounts only | B (Yujuan Gao) |
| 09 | Auth | POST `/auth/login` | Public | JWT Login | B (Yujuan Gao) |
| 10 | User Profile | GET `/users/me` | Login | Do not return internal scheduling fields | B (Yujuan Gao) |
| 11 | User Profile | PATCH `/users/me` | Login | Profile fields only; engineers may change availability | B (Yujuan Gao) |
| 12 | Reference & Directory | GET `/reference-data` | Login | Role-aware states, SLA/timer settings and attachment limits | B (Yujuan Gao) |
| 13 | Reference & Directory | GET `/users/assignees` | T1/T2/Manager | Tier/skill/availability filters | B (Yujuan Gao) |
| 14 | Reference & Directory | GET `/vendors` | T2/Manager | Vendor Organisations | B (Yujuan Gao) |
| 15 | Ticket Core | POST `/tickets` | User | Create the ticket, start a cycle and call C (Andy Wen)'s initial assignment service; only ASSIGNED/UNASSIGNED after commit | B (Yujuan Gao) |
| 16 | Ticket Core | GET `/tickets` | Login | Role-aware lists/filters; vendor scope is based on VendorRequest history | B (Yujuan Gao) |
| 17 | Ticket Core | GET `/tickets/{id}` | Scoped Role | Role-aware Detail, display_status, available_actions | B (Yujuan Gao) |
| 18 | Ticket Core | PATCH `/tickets/{id}` | User/Manager | Users: own UNASSIGNED tickets only; managers: non-CLOSED tickets only | B (Yujuan Gao) |
| 19 | Comment | GET `/tickets/{id}/comments` | User/T1/T2/Manager | Visibility filtering; vendors rejected | B (Yujuan Gao) |
| 20 | Comment | POST `/tickets/{id}/comments` | Scoped Role | Ordinary comments; actors expected to provide formal replies in waiting states receive action guidance | B (Yujuan Gao) |
| 21 | Assignment & Handling | POST `/tickets/{id}/assign` | Manager | Strictly follow the matrix in Section 4.5 | C (Andy Wen) |
| 22 | Assignment & Handling | POST `/tickets/{id}/start` | Assignee | ASSIGNED/REOPENED → IN_PROGRESS | C (Andy Wen) |
| 23 | User Interaction | POST `/tickets/{id}/request-user-info` | Assignee | USER_VISIBLE request; PENDING_USER/INFORMATION_REQUIRED | C (Andy Wen) |
| 24 | User Interaction | POST `/tickets/{id}/resume` | User | Formal information reply/Issue Persists; deadline enforcement | C (Andy Wen) |
| 25 | Escalation | POST `/tickets/{id}/escalate` | Tier 1 | Select Tier 2; preserve the cycle | C (Andy Wen) |
| 26 | Vendor | POST `/tickets/{id}/vendor-requests` | Tier 2 | vendor_org_id + vendor_message; only one active request | C (Andy Wen) |
| 27 | Vendor | POST `/tickets/{id}/vendor-response` | Matching Vendor | Do not submit vendor_request_id; Active → RESPONDED | C (Andy Wen) |
| 28 | Resolution & Closure | POST `/tickets/{id}/resolve` | Assignee | User-visible resolution; enter the confirmation stage | C (Andy Wen) |
| 29 | Resolution & Closure | POST `/tickets/{id}/confirm-resolution` | User | Confirm the resolution; deadline enforcement | C (Andy Wen) |
| 30 | Resolution & Closure | POST `/tickets/{id}/reopen` | User | Within the RESOLVED window; prefer the original assignee; new cycle | C (Andy Wen) |
| 31 | Resolution & Closure | POST `/tickets/{id}/close` | User | Within the RESOLVED window; acknowledgement required; terminal CLOSED state | C (Andy Wen) |
| 32 | Audit | GET `/tickets/{id}/events` | Scoped Role | Role/Scope-aware Timeline | C (Andy Wen) |

There are 32 public APIs: A (BIN LIN)=7, B (Yujuan Gao)=13, C (Andy Wen)=12. Background jobs, RBAC, serializers and the assignment service are internal components, not additional public APIs.

Each API owner must submit the router/service/repository, schemas, unit/contract tests and OpenAPI changes in the same PR. D (Yiguang Sun) depends only on the merged OpenAPI contract.

---

## 6. Cloud, Development and Deployment

### 6.1 Final AWS Architecture

~~~mermaid
flowchart LR
    U[Browser / Marker] --> CF[CloudFront HTTPS]
    CF --> ALB[Internet-facing ALB]
    ALB -->|/api/*| BE[Backend ECS Service]
    ALB -->|other paths| FE[Frontend ECS Service]
    BE --> RDS[(Private RDS MySQL)]
    BE --> S3[(Private S3)]
    BE --> SM[Secrets Manager]
    U -->|Presigned PUT/GET| S3
    SCH[EventBridge Scheduler] --> SLA[SLA ECS Task]
    SCH --> CLEAN[Attachment Cleanup ECS Task]
    SLA --> RDS
    CLEAN --> RDS
    CLEAN --> S3
    SLA --> SM
    CLEAN --> SM
    GH[GitHub Actions] --> ECR[ECR]
    ECR --> FE
    ECR --> BE
    FE --> CW[CloudWatch Logs]
    BE --> CW
    SLA --> CW
    CLEAN --> CW
~~~

- CloudFront uses the default `*.cloudfront.net` certificate to provide HTTPS to viewers; caching is disabled for `/api/*`. Without a custom domain, the MVP uses an HTTP origin from CloudFront to the ALB, with the CloudFront origin-facing prefix list and an origin verification header restricting bypass access. Switch to an HTTPS origin after obtaining a valid ACM domain certificate. The ALB is not the final public URL listed in the report.
- Backend/frontend ECS services deploy independently, initially with `desiredCount=1`. Background jobs do not run inside web processes, avoiding duplicate execution during scaling or restarts.
- `sla_monitor` checks AT_RISK, OVERDUE, pending user deadlines and automatic closure every five minutes; `attachment_cleanup` handles expired upload sessions and orphaned objects every 30 minutes. Both may be safely rerun.
- Final RDS is private and accessible only from backend/scheduled-task security groups. Keep S3 Block Public Access, default encryption and the CORS allowlist enabled.
- To reduce MVP cost, the ALB and ECS tasks use public subnets. ECS tasks may have public IPs for outbound access to AWS services, but their security groups accept application-port traffic only from the ALB security group; scheduled tasks expose no inbound access. RDS resides in private DB subnets without a public IP.
- ECS task roles access only the required S3 prefixes, logs and secrets. GitHub deploys through OIDC; the frontend/browser holds no AWS access keys. Presigned URLs permit access to only one object_key with a short TTL.

### 6.2 Local Development and Development-stage AWS Boundaries

- A (BIN LIN), B (Yujuan Gao) and C (Andy Wen) each run an independent local MySQL 8.4 instance, using database name `service_desk`, character set `utf8mb4` and UTC. Their instances, ports and credentials are isolated; feature branches must not share a database schema.
- After pulling `main`, each member runs the same `backend/database/schema.sql` on their empty MySQL instance, creating all 19 tables, reference data, foreign keys, unique/CHECK constraints and audit triggers in one run. No member may create only their own tables.
- `backend/database/schema.sql` is the sole executable schema contract; `IT-Service-Desk-Database-Final-Design-v1.1.md` explains the fields. SQLAlchemy models are application mappings and must exactly match the SQL contract, without independently adding, deleting or changing columns.
- `python -m app.db.bootstrap` only confirms the target is empty, executes the versioned canonical SQL, records the schema version and runs verification. It must not use `Base.metadata.create_all()` to generate a separate schema.
- Development data is not a long-term asset. To verify schema changes, rerun the complete SQL on an empty local instance; do not combine A (BIN LIN)/B (Yujuan Gao)/C (Andy Wen)'s personal SQL dumps into the final schema.
- Do not create or continuously run AWS RDS, ECS, ALB, CloudFront, EventBridge Scheduler, CloudWatch application logs or Secrets Manager during feature development.
- Development-stage AWS retains only one private S3 bucket, using the `development/` prefix, Block Public Access, default encryption, short-lived presigned URLs and least privilege. A (BIN LIN) owns real S3 integration tests; ordinary unit tests use mocks/stubs to avoid interference and unnecessary request charges.
- D (Yiguang Sun) develops with TypeScript types/mocks generated from OpenAPI v1.1 and the agreed examples, then integrates with A (BIN LIN)/B (Yujuan Gao)/C (Andy Wen)'s local backend URLs. D (Yiguang Sun) does not connect to MySQL/S3 or hold database/AWS credentials.
- Post-merge backend integration tests first run on a designated member's fresh, empty local MySQL database. Test only `main`; do not run unmerged feature branches in a shared environment.
- The canonical SQL inserts non-sensitive roles, categories, priorities, states, timers, attachment types and singleton control rows. `seed.py` must idempotently verify/complete the same reference data. `seed_demo.py` is for local test accounts only and must never run on final RDS. No seed may contain real personal data or secrets.

### 6.3 Final Database Bootstrap, Release Order and Rollback

1. Complete schema freeze at M4. CI executes `backend/database/schema.sql` on a fresh, empty MySQL 8.4 database and verifies 19 tables, 35 foreign keys, key unique/CHECK constraints, two audit triggers, reference data, SQLAlchemy mappings, API tests and the Docker build. Generate immutable backend/frontend image tags using the commit SHA.
2. A (BIN LIN) creates the final AWS infrastructure: empty private RDS, final private S3, ECR, ECS, ALB, CloudFront, secrets, logs and scheduler. RDS also uses database name `service_desk`.
3. A (BIN LIN) launches a one-off database bootstrap ECS task using the same backend image and runs `python -m app.db.bootstrap` to apply the same canonical SQL to empty RDS, followed by idempotent `python -m app.db.seed` to verify reference data. B (Yujuan Gao) checks task logs, schema version, tables, indexes, foreign keys, CHECK constraints, triggers and schema drift results. Do not automatically create tables whenever a backend web container starts.
4. A (BIN LIN) deploys the backend task definition, waits for health checks and passes direct API smoke tests.
5. A (BIN LIN)/D (Yiguang Sun) deploy the frontend task definition and perform CloudFront invalidation as needed.
6. C (Andy Wen) verifies the SLA scheduled task; A (BIN LIN) verifies the attachment cleanup task; D (Yiguang Sun) runs the Playwright critical path.
7. After all gates pass, B (Yujuan Gao) uses `mysqldump --no-data` to export the actual release test database and compares its structure against the canonical `backend/database/schema.sql`. Store the comparison results and dump in `backend/database/release/` as assignment evidence. A (BIN LIN) records the release tag, URLs, bootstrap log and cloud test evidence in the runbook; C (Andy Wen) links them to Trello.

If initial final bootstrap fails before production data exists, correct the canonical SQL, database design, SQLAlchemy models and tests, then recreate an empty database and verify again. A (BIN LIN)/B (Yujuan Gao)/C (Andy Wen) must not import separate personal SQL dumps into RDS. Once final RDS contains data, take a snapshot before applying any team-reviewed, versioned SQL patch. Roll back failed backend/frontend applications to their previous task definitions independently. Do not manually repair the final database with `create_all()` or MySQL Workbench merely to make tests pass.

### 6.4 Cost and Operational Boundaries

- Feature development retains only one private development S3 bucket, without AWS RDS or compute. The complete RDS/CloudFront/ALB/ECS/Scheduler environment is created and operated from M5 onwards.
- Frontend/backend initially use desiredCount=1; scheduled tasks exit after execution.
- AWS Budgets provides alerts, not a hard spending cap. Review ongoing RDS, ALB, ECS, public IPv4, logs and traffic charges weekly.
- After submission, retain public URLs, RDS, S3 and logs until marking is complete. Once notified, archive evidence and delete chargeable resources according to the runbook.

---

## 7. Team Responsibilities and Interface Boundaries

### 7.1 Member Ownership Map

| Member | Main Domains and Deliverables | Public APIs | Exclusions / Boundaries |
|---|---|---:|---|
| A (BIN LIN) | Platform, AttachmentUpload/Attachment, dashboard, AWS, CI/CD and runbook; storage/cloud tests | 01–07 (7) | Does not implement ticket workflows, user/auth or frontend pages |
| B (Yujuan Gao) | Auth/user, ticket core, comments, reference data and access scope; core tests; Database Schema Coordinator, maintaining the model registry and reviewing bootstrap/seed | 08–20 (13) | Does not write A (BIN LIN)/C (Andy Wen)'s domain models or act as the whole team's test lead |
| C (Andy Wen) | Assignment, workflow, vendor, SLA, TicketEvent/audit and background SLA task; workflow tests; project coordination | 21–32 (12) | Does not maintain attachment storage, the frontend or the AWS release pipeline |
| D (Yiguang Sun) | All frontend pages, typed API client, frontend container/Nginx and component/E2E/manual tests | No backend APIs | No direct database/S3 access; holds no cloud/database credentials |

Each owner independently delivers their models/services/APIs, schema changes, tests, OpenAPI updates and necessary documentation. Coordinators manage sequencing, review and tracking rather than implementing another owner's domain.

### 7.2 Fixed Cross-domain Contracts

To reduce waiting between members, freeze the following Python interfaces and OpenAPI schemas at M1. Implementations may be replaced later, but consumers must not read another domain's internal tables:

| Provider | Consumer | Contract | Frozen Definition |
|---|---|---|---|
| B (Yujuan Gao) | A (BIN LIN)/C (Andy Wen) | `TicketAccessPolicy` | actor, ticket_id → view/write scope; hidden resources consistently return 404 |
| C (Andy Wen) | B (Yujuan Gao) | `InitialAssignmentService` | New ticket → assignee/status/first SLA cycle; return UNASSIGNED if assignment fails |
| C (Andy Wen) | B (Yujuan Gao)/D (Yiguang Sun) | `WorkflowReadModel` | `display_status`, SLA colour, `available_actions` |
| A (BIN LIN) | D (Yiguang Sun) | Attachment API 02–05 | Upload session, signed headers and the frontend's three-step upload flow |
| Domain Owners | D (Yiguang Sun) | Versioned OpenAPI | Request/Response/Error Code; Mock Example |

B (Yujuan Gao) maintains the base fields in `tickets`; C (Andy Wen)'s workflow/SLA fields are frozen together at M1. If cross-domain fields are needed later, the field owner submits a separate schema PR updating their SQLAlchemy model, tests and relevant contracts. B (Yujuan Gao) reviews `model_registry.py`, foreign keys, constraints and empty-database bootstrap. Necessary changes after final schema freeze require a separate versioned SQL patch that must not run without review.

### 7.3 Collaboration and Review Rules

- Feature branch → pull request with local check evidence → review by at least one non-author → merge. The current GitHub Actions release workflows are manually dispatched from `main`; pushes and pull requests do not trigger them automatically. Direct pushes to `main` and history rewriting are prohibited.
- The monorepo contains only five top-level workspaces: `frontend/`, `backend/`, `infrastructure/`, `docs/` and `.github/`. Branch names follow `<type>/WBS-<member>-<number>-<slug>`, with one short-lived branch per Trello task.
- The domain owner retains final responsibility for correctness. Reviewers focus on contracts, permissions, database schemas and regression risks rather than taking over implementation.
- A (BIN LIN) is Release Coordinator; B (Yujuan Gao) is Database Schema Coordinator; C (Andy Wen) is Project Coordinator; D (Yiguang Sun) is Frontend/E2E Coordinator. These four coordination roles do not replace one another.
- For cross-domain PRs, merge the provider contract/test fixture before the consumer. Shared interface changes must update OpenAPI and affected tests together.
- Every Trello card must include its owner, acceptance criteria, dependencies, test evidence and PR/commit. Mark it Done only when the evidence is complete.

### 7.4 Project Coordination and Evidence

- Trello uses the fixed columns Backlog, Ready, In Progress, Code Review, Integration Test, Blocked and Done. Owners update their own cards; C (Andy Wen) maintains priorities, dependencies and milestones without writing work records on behalf of members.
- Hold at least one planning session, one API/integration sync and one runnable demo each week. C (Andy Wen) records decisions, blockers, owners and due dates; each domain owner presents their own test evidence.
- Each member's weekly worklog records at least the date, time spent, task, result, commit/PR, test/screenshot, blocker and next action. The report cites only traceable evidence.
- If a delay of more than two days is expected, the owner escalates to C (Andy Wen) that day. C (Andy Wen) coordinates reprioritisation or removal of non-essential scope. Feature additions/removals and state/API/architecture changes require team agreement; C (Andy Wen) cannot change scope unilaterally.

### 7.5 Current Git Monorepo Structure

The repository has five main workspaces: `backend/`, `frontend/`, `infrastructure/`, `docs/` and `.github/`. The root contains project-wide configuration and documentation. Organise code by domain, without personal code directories.

This tree was generated from all 440 files tracked on GitHub `main` at [`379bb53`](https://github.com/infs803-group8/ITSM/tree/379bb531504e78b2b293564b070f8af33b85449c), checked on 2026-10-07. It includes tracked placeholders and evidence files. Local-only folders such as `.git/`, `.venv/`, `node_modules/`, caches and build outputs are excluded. A listed path records its presence in Git, not completion of the functionality it describes.

~~~text
ITSM/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug-report.md
│   │   └── feature-request.md
│   ├── actions/
│   │   └── manual-ecs/
│   │       └── action.yml
│   ├── workflows/
│   │   ├── backend.yml
│   │   └── frontend.yml
│   ├── CODEOWNERS
│   └── PULL_REQUEST_TEMPLATE.md
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── dependencies.py
│   │   │   ├── exception_handlers.py
│   │   │   ├── request_id.py
│   │   │   └── router.py
│   │   ├── common/
│   │   │   ├── __init__.py
│   │   │   ├── pagination.py
│   │   │   ├── request_context.py
│   │   │   ├── responses.py
│   │   │   └── validators.py
│   │   ├── contracts/  # Internal Python interfaces shared by backend domains
│   │   │   ├── __init__.py
│   │   │   ├── initial_assignment.py
│   │   │   ├── ticket_access_policy.py
│   │   │   ├── vendor_binding.py
│   │   │   └── workflow_read_model.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── clock.py
│   │   │   ├── config.py
│   │   │   ├── constants.py
│   │   │   ├── enums.py
│   │   │   ├── errors.py
│   │   │   ├── logging.py
│   │   │   └── security.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── bootstrap.py
│   │   │   ├── model_registry.py
│   │   │   ├── seed.py
│   │   │   ├── seed_demo.py
│   │   │   ├── session.py
│   │   │   └── verify_schema.py
│   │   ├── domains/
│   │   │   ├── assignment/  # C (Andy Wen): assignment
│   │   │   │   ├── __init__.py
│   │   │   │   ├── model.py
│   │   │   │   ├── ranking.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── router.py
│   │   │   │   ├── schema.py
│   │   │   │   └── service.py
│   │   │   ├── attachments/  # A (BIN LIN): attachments
│   │   │   │   ├── __init__.py
│   │   │   │   ├── access_policy.py
│   │   │   │   ├── cleanup_job.py
│   │   │   │   ├── model.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── router.py
│   │   │   │   ├── schema.py
│   │   │   │   └── service.py
│   │   │   ├── audit/  # C (Andy Wen): audit events
│   │   │   │   ├── __init__.py
│   │   │   │   ├── access_policy.py
│   │   │   │   ├── model.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── router.py
│   │   │   │   ├── schema.py
│   │   │   │   └── service.py
│   │   │   ├── auth/  # B (Yujuan Gao): authentication
│   │   │   │   ├── __init__.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── router.py
│   │   │   │   ├── schema.py
│   │   │   │   └── service.py
│   │   │   ├── comments/  # B (Yujuan Gao): comments
│   │   │   │   ├── __init__.py
│   │   │   │   ├── model.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── router.py
│   │   │   │   ├── schema.py
│   │   │   │   └── service.py
│   │   │   ├── dashboard/  # A (BIN LIN): dashboards
│   │   │   │   ├── __init__.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── router.py
│   │   │   │   ├── schema.py
│   │   │   │   └── service.py
│   │   │   ├── platform/  # A (BIN LIN): platform
│   │   │   │   ├── __init__.py
│   │   │   │   ├── router.py
│   │   │   │   ├── schema.py
│   │   │   │   └── service.py
│   │   │   ├── reference_data/  # B (Yujuan Gao): reference data
│   │   │   │   ├── __init__.py
│   │   │   │   ├── model.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── router.py
│   │   │   │   ├── schema.py
│   │   │   │   └── service.py
│   │   │   ├── sla/  # C (Andy Wen): SLA and deadlines
│   │   │   │   ├── __init__.py
│   │   │   │   ├── cycle.py
│   │   │   │   ├── monitor_job.py
│   │   │   │   ├── repository.py
│   │   │   │   └── service.py
│   │   │   ├── tickets/  # B (Yujuan Gao): tickets
│   │   │   │   ├── __init__.py
│   │   │   │   ├── access_policy.py
│   │   │   │   ├── detail_assembler.py
│   │   │   │   ├── model.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── router.py
│   │   │   │   ├── schema.py
│   │   │   │   └── service.py
│   │   │   ├── users/  # B (Yujuan Gao): users
│   │   │   │   ├── __init__.py
│   │   │   │   ├── model.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── router.py
│   │   │   │   ├── schema.py
│   │   │   │   └── service.py
│   │   │   ├── vendor_workflow/  # C (Andy Wen): vendor collaboration and history
│   │   │   │   ├── __init__.py
│   │   │   │   ├── history.py
│   │   │   │   ├── model.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── router.py
│   │   │   │   ├── schema.py
│   │   │   │   └── service.py
│   │   │   ├── workflow/  # C (Andy Wen): ticket workflow
│   │   │   │   ├── __init__.py
│   │   │   │   ├── action_engine.py
│   │   │   │   ├── comment_gateway.py
│   │   │   │   ├── deadline_service.py
│   │   │   │   ├── error_mapping.py
│   │   │   │   ├── read_model.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── router.py
│   │   │   │   ├── schema.py
│   │   │   │   ├── serializer.py
│   │   │   │   ├── service.py
│   │   │   │   ├── state_machine.py
│   │   │   │   └── ticket_creation.py
│   │   │   └── __init__.py
│   │   ├── integrations/
│   │   │   ├── s3/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── client.py
│   │   │   │   ├── object_verification.py
│   │   │   │   └── presigned_urls.py
│   │   │   └── __init__.py
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── openapi_export.py
│   ├── contracts/  # Current 33-operation OpenAPI contract for generation and tests
│   │   ├── openapi.json
│   │   └── openapi.yaml
│   ├── database/
│   │   ├── patches/
│   │   │   └── README.md
│   │   ├── release/
│   │   │   ├── README.md
│   │   │   ├── schema-dump.sql
│   │   │   └── schema-verification.txt
│   │   ├── README.md
│   │   └── schema.sql
│   ├── scripts/
│   │   ├── export_openapi.py
│   │   ├── export_schema.ps1
│   │   ├── local_reset_database.ps1
│   │   └── run_mysql_integration.py
│   ├── tests/
│   │   ├── contract/
│   │   │   ├── .gitkeep
│   │   │   ├── __init__.py
│   │   │   ├── test_member_a_openapi.py
│   │   │   ├── test_member_b_auth_openapi.py
│   │   │   └── test_member_b_core_openapi.py
│   │   ├── database/
│   │   │   ├── test_empty_database_bootstrap.py
│   │   │   ├── test_schema_constraints.py
│   │   │   └── test_seed_idempotency.py
│   │   ├── factories/
│   │   │   └── .gitkeep
│   │   ├── fixtures/
│   │   │   └── .gitkeep
│   │   ├── integration/
│   │   │   ├── .gitkeep
│   │   │   ├── __init__.py
│   │   │   ├── test_audit_mysql.py
│   │   │   ├── test_create_assignment.py
│   │   │   ├── test_member_a_mysql.py
│   │   │   ├── test_member_b_mysql.py
│   │   │   ├── test_sla_job_recovery.py
│   │   │   ├── test_vendor_history_mysql.py
│   │   │   └── test_workflow_escalate_mysql.py
│   │   ├── smoke/
│   │   │   └── .gitkeep
│   │   ├── unit/
│   │   │   ├── api/
│   │   │   │   ├── __init__.py
│   │   │   │   └── test_exception_handlers.py
│   │   │   ├── assignment/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── __init__.py
│   │   │   │   ├── test_assign_ticket_service.py
│   │   │   │   ├── test_ranking.py
│   │   │   │   └── test_service.py
│   │   │   ├── attachments/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── __init__.py
│   │   │   │   ├── test_access_policy.py
│   │   │   │   ├── test_cleanup.py
│   │   │   │   ├── test_model_mapping.py
│   │   │   │   ├── test_s3_custom_domain.py
│   │   │   │   └── test_service.py
│   │   │   ├── audit/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── __init__.py
│   │   │   │   ├── test_access_policy.py
│   │   │   │   ├── test_model_mapping.py
│   │   │   │   └── test_service.py
│   │   │   ├── auth/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── __init__.py
│   │   │   │   ├── test_schema.py
│   │   │   │   ├── test_security.py
│   │   │   │   └── test_service.py
│   │   │   ├── comments/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── __init__.py
│   │   │   │   └── test_schema.py
│   │   │   ├── dashboard/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── __init__.py
│   │   │   │   └── test_service.py
│   │   │   ├── platform/
│   │   │   │   ├── __init__.py
│   │   │   │   └── test_health.py
│   │   │   ├── reference_data/
│   │   │   │   ├── .gitkeep
│   │   │   │   └── test_service.py
│   │   │   ├── sla/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── __init__.py
│   │   │   │   ├── test_cycle.py
│   │   │   │   ├── test_monitor_job.py
│   │   │   │   ├── test_service.py
│   │   │   │   └── test_threshold_scan_service.py
│   │   │   ├── tickets/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── __init__.py
│   │   │   │   ├── test_detail_assembler.py
│   │   │   │   ├── test_detail_assembler_visibility.py
│   │   │   │   ├── test_schema.py
│   │   │   │   ├── test_service_actions.py
│   │   │   │   └── test_vendor_history_route.py
│   │   │   ├── users/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── __init__.py
│   │   │   │   ├── test_model_mapping.py
│   │   │   │   ├── test_schema.py
│   │   │   │   └── test_service.py
│   │   │   ├── vendor_workflow/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── __init__.py
│   │   │   │   ├── test_history.py
│   │   │   │   ├── test_request_vendor_service.py
│   │   │   │   └── test_vendor_response_service.py
│   │   │   ├── workflow/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── __init__.py
│   │   │   │   ├── test_action_routes.py
│   │   │   │   ├── test_action_service.py
│   │   │   │   ├── test_confirm_resolution_service.py
│   │   │   │   ├── test_deadline_service.py
│   │   │   │   ├── test_error_mapping.py
│   │   │   │   ├── test_escalate_service.py
│   │   │   │   ├── test_manual_close_service.py
│   │   │   │   ├── test_read_model_serializer.py
│   │   │   │   ├── test_reopen_service.py
│   │   │   │   ├── test_request_user_info_service.py
│   │   │   │   ├── test_resume_service.py
│   │   │   │   ├── test_state_machine.py
│   │   │   │   └── test_submit_resolution_service.py
│   │   │   └── __init__.py
│   │   ├── __init__.py
│   │   └── conftest.py
│   ├── .dockerignore
│   ├── .env.example
│   ├── Dockerfile
│   ├── README.md
│   ├── pyproject.toml
│   ├── requirements-dev.txt
│   └── requirements.txt
├── docs/  # Three Markdown process documents and one baseline OpenAPI snapshot
│   ├── IT-Service-Desk-Database-Final-Design-v1.1.md
│   ├── IT-Service-Desk-Final-API-Specification-v1.1.md
│   ├── IT-Service-Desk-OpenAPI-v1.1.yaml
│   └── IT-Service-Desk-Unified-Project-Baseline-v6.0.md
├── frontend/  # D (Yiguang Sun): frontend and frontend tests
│   ├── docs/
│   │   └── evidence/
│   │       ├── d02-login-desktop.png
│   │       ├── d02-profile-desktop.png
│   │       ├── d02-register-desktop.png
│   │       ├── d03-attachments.png
│   │       ├── d03-create-ticket.png
│   │       ├── d03-dashboard.png
│   │       ├── d03-engineer-workspace.png
│   │       ├── d03-overdue.png
│   │       ├── d03-ticket-detail.png
│   │       ├── d03-ticket-list.png
│   │       ├── d03-vendor-workspace.png
│   │       └── d04-vendor-history.png
│   ├── public/
│   │   ├── .gitkeep
│   │   ├── mock-download.txt
│   │   └── mockServiceWorker.js
│   ├── scripts/
│   │   └── generate-api.mjs
│   ├── src/
│   │   ├── api/
│   │   │   ├── generated/  # Generated output; do not edit manually
│   │   │   │   ├── client/
│   │   │   │   │   ├── client.gen.ts
│   │   │   │   │   ├── index.ts
│   │   │   │   │   ├── types.gen.ts
│   │   │   │   │   └── utils.gen.ts
│   │   │   │   ├── core/
│   │   │   │   │   ├── auth.gen.ts
│   │   │   │   │   ├── bodySerializer.gen.ts
│   │   │   │   │   ├── params.gen.ts
│   │   │   │   │   ├── pathSerializer.gen.ts
│   │   │   │   │   ├── queryKeySerializer.gen.ts
│   │   │   │   │   ├── serverSentEvents.gen.ts
│   │   │   │   │   ├── types.gen.ts
│   │   │   │   │   └── utils.gen.ts
│   │   │   │   ├── client.gen.ts
│   │   │   │   ├── contract-manifest.json
│   │   │   │   ├── index.ts
│   │   │   │   ├── sdk.gen.ts
│   │   │   │   └── types.gen.ts
│   │   │   ├── attachmentTransfer.ts
│   │   │   ├── auth.ts
│   │   │   ├── config.ts
│   │   │   ├── errorHandler.ts
│   │   │   ├── httpClient.ts
│   │   │   ├── tokenStorage.ts
│   │   │   └── types.ts
│   │   ├── app/
│   │   │   ├── providers.tsx
│   │   │   ├── roleRoutes.tsx
│   │   │   └── router.tsx
│   │   ├── components/
│   │   │   ├── feedback/
│   │   │   │   └── .gitkeep
│   │   │   ├── forms/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── PasswordInput.tsx
│   │   │   │   └── rules.ts
│   │   │   ├── layout/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── AppLayout.tsx
│   │   │   │   ├── AuthShell.tsx
│   │   │   │   └── Brand.tsx
│   │   │   ├── tables/
│   │   │   │   └── .gitkeep
│   │   │   └── ApiErrorNotice.tsx
│   │   ├── features/
│   │   │   ├── attachments/
│   │   │   │   └── .gitkeep
│   │   │   ├── audit/
│   │   │   │   └── .gitkeep
│   │   │   ├── auth/
│   │   │   │   ├── .gitkeep
│   │   │   │   ├── AuthProvider.tsx
│   │   │   │   ├── DevDemoAccount.tsx
│   │   │   │   ├── LoginPage.tsx
│   │   │   │   ├── RegisterPage.tsx
│   │   │   │   └── roleLabels.ts
│   │   │   ├── comments/
│   │   │   │   └── .gitkeep
│   │   │   ├── dashboard/
│   │   │   │   └── .gitkeep
│   │   │   ├── profile/
│   │   │   │   ├── .gitkeep
│   │   │   │   └── ProfilePage.tsx
│   │   │   ├── tickets/
│   │   │   │   └── .gitkeep
│   │   │   ├── vendor/
│   │   │   │   └── .gitkeep
│   │   │   ├── workflow/
│   │   │   │   └── .gitkeep
│   │   │   └── workspace/
│   │   │       ├── AttachmentsPanel.tsx
│   │   │       ├── CommentsPanel.tsx
│   │   │       ├── DashboardPage.tsx
│   │   │       ├── TicketDetailPage.tsx
│   │   │       ├── TicketForm.tsx
│   │   │       ├── TicketListPage.tsx
│   │   │       ├── VendorHistoryPanel.tsx
│   │   │       ├── WorkflowPanel.tsx
│   │   │       └── shared.tsx
│   │   ├── hooks/
│   │   │   └── .gitkeep
│   │   ├── mocks/
│   │   │   ├── fixtures/
│   │   │   │   └── .gitkeep
│   │   │   ├── browser.ts
│   │   │   ├── fixtures.generated.json
│   │   │   ├── handlers.ts
│   │   │   ├── state.ts
│   │   │   ├── validation.ts
│   │   │   ├── workspace-fixtures.generated.json
│   │   │   ├── workspaceHandlers.ts
│   │   │   └── workspaceModel.ts
│   │   ├── styles/
│   │   │   ├── global.css
│   │   │   └── theme.ts
│   │   ├── types/
│   │   │   └── .gitkeep
│   │   ├── utils/
│   │   │   └── .gitkeep
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── vite-env.d.ts
│   ├── tests/
│   │   ├── accessibility/
│   │   │   └── .gitkeep
│   │   ├── api/
│   │   │   ├── client.test.ts
│   │   │   ├── contract.test.ts
│   │   │   ├── contract.ts
│   │   │   ├── errorHandler.test.ts
│   │   │   └── workspace.test.ts
│   │   ├── api-browser/
│   │   │   └── api-foundation.spec.ts
│   │   ├── auth-browser/
│   │   │   └── auth-pages.spec.ts
│   │   ├── component/
│   │   │   ├── .gitkeep
│   │   │   ├── ApiErrorNotice.test.tsx
│   │   │   ├── auth-pages.test.tsx
│   │   │   └── workspace.test.tsx
│   │   ├── e2e/
│   │   │   ├── attachment-flow.spec.ts
│   │   │   ├── engineer-workflow.spec.ts
│   │   │   ├── helpers.ts
│   │   │   ├── manager-flow.spec.ts
│   │   │   ├── user-ticket-flow.spec.ts
│   │   │   └── vendor-flow.spec.ts
│   │   ├── fixtures/
│   │   │   └── debug.log
│   │   └── setup.ts
│   ├── .dockerignore
│   ├── .env.example
│   ├── .nvmrc
│   ├── D01-HANDOFF.md
│   ├── D02-HANDOFF.md
│   ├── D03-HANDOFF.md
│   ├── D04-HANDOFF.md
│   ├── Dockerfile
│   ├── PR51-REVIEW-FIXES.md
│   ├── README.md
│   ├── index.html
│   ├── nginx.conf
│   ├── openapi.config.mjs
│   ├── package-lock.json
│   ├── package.json
│   ├── playwright.api.config.ts
│   ├── playwright.auth.config.ts
│   ├── playwright.config.ts
│   ├── tsconfig.json
│   └── vite.config.ts
├── infrastructure/  # A (BIN LIN): infrastructure and release tooling
│   ├── ecs/
│   │   └── task-definitions/
│   │       └── README.md
│   ├── environments/
│   │   └── production.json
│   ├── policies/
│   │   ├── developer-s3-policy.json
│   │   ├── ecs-task-role.json
│   │   ├── github-actions-release.json
│   │   └── github-actions-trust.json
│   ├── scripts/
│   │   ├── cleanup-aws-resources.ps1
│   │   ├── deploy-backend.ps1
│   │   ├── deploy-final.ps1
│   │   ├── deploy-frontend.ps1
│   │   ├── deploy.py
│   │   ├── release.py
│   │   ├── run-database-bootstrap.ps1
│   │   ├── run-smoke-tests.ps1
│   │   └── setup_github_oidc.py
│   ├── terraform/
│   │   ├── dev-storage/
│   │   │   ├── main.tf
│   │   │   ├── outputs.tf
│   │   │   ├── terraform.tfvars.example
│   │   │   ├── variables.tf
│   │   │   └── versions.tf
│   │   └── final/
│   │       ├── tests/
│   │       │   └── release.tftest.hcl
│   │       ├── alb.tf
│   │       ├── budget.tf
│   │       ├── cloudfront.tf
│   │       ├── cloudwatch.tf
│   │       ├── ecr.tf
│   │       ├── ecs.tf
│   │       ├── iam.tf
│   │       ├── locals.tf
│   │       ├── network.tf
│   │       ├── outputs.tf
│   │       ├── providers.tf
│   │       ├── rds.tf
│   │       ├── s3.tf
│   │       ├── scheduler.tf
│   │       ├── secrets_manager.tf
│   │       ├── security_groups.tf
│   │       ├── tasks.tf  # Executable ECS task definitions
│   │       ├── terraform.tfvars.example
│   │       ├── variables.tf
│   │       └── versions.tf
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test-smoke.ps1
│   │   ├── test_deploy.py
│   │   └── test_release.py
│   ├── README.md
│   ├── pyproject.toml
│   └── requirements-release.txt
├── .editorconfig
├── .gitattributes
├── .gitignore
├── CONTRIBUTING.md
├── README.md
└── docker-compose.local.yml
~~~

`backend/app/contracts/` contains internal Python interfaces; `backend/contracts/` contains the public OpenAPI YAML/JSON consumed by generation and tests. Frontend screenshots remain under `frontend/docs/evidence/`; the root `docs/` contains only the four process documents shown above.

The executable ECS task definitions are in `infrastructure/terraform/final/tasks.tf`. `infrastructure/ecs/task-definitions/README.md` points to that source; the former JSON templates are no longer tracked. Current release tooling uses `infrastructure/scripts/release.py`, `deploy.py`, `environments/production.json` and `requirements-release.txt`. GitHub OIDC setup uses `scripts/setup_github_oidc.py` and the two `policies/github-actions-*.json` files, all under `infrastructure/`.

### 7.6 Directory Ownership and Shared File Control

Paths in this table are relative to the repository root. Review ownership follows [`.github/CODEOWNERS`](../.github/CODEOWNERS); coordination responsibilities do not replace those rules.

| Path / File | Owner / Rule |
|---|---|
| `backend/app/domains/platform/`, `backend/app/domains/attachments/`, `backend/app/domains/dashboard/`, `backend/app/integrations/s3/` | A (BIN LIN): platform, attachments and dashboards. |
| `infrastructure/`, `docker-compose.local.yml` | A (BIN LIN): AWS infrastructure, release tooling and local MySQL setup. |
| `backend/app/domains/auth/`, `backend/app/domains/users/`, `backend/app/domains/reference_data/`, `backend/app/domains/tickets/`, `backend/app/domains/comments/` | B (Yujuan Gao): authentication and core ticket data. |
| `backend/app/db/`, `backend/database/` | Shared A (BIN LIN)/B (Yujuan Gao)/C (Andy Wen) review; B coordinates schema and model alignment. |
| `backend/app/domains/assignment/`, `backend/app/domains/workflow/`, `backend/app/domains/vendor_workflow/`, `backend/app/domains/audit/`, `backend/app/domains/sla/` | C (Andy Wen): assignment, workflows, vendor collaboration, auditing and SLA. |
| `docs/` | Shared A (BIN LIN)/B (Yujuan Gao)/C (Andy Wen)/D (Yiguang Sun) review of the retained process documents. Project coordination and Trello remain C's responsibility; the former project-management documentation directory has been removed. |
| `docs/IT-Service-Desk-Database-Final-Design-v1.1.md` | Shared A (BIN LIN)/B (Yujuan Gao)/C (Andy Wen) review, as specified by the more specific CODEOWNERS rule. |
| `frontend/` | D (Yiguang Sun): pages, frontend container and frontend tests. |
| `backend/app/api/router.py`, `backend/app/db/model_registry.py` | Shared backend ownership; B coordinates router and model registrations. |
| `backend/contracts/openapi.yaml`, `backend/contracts/openapi.json` | Shared A (BIN LIN)/B (Yujuan Gao)/C (Andy Wen)/D (Yiguang Sun) contract review. API owners update the implementation contract and affected tests together. |
| `backend/scripts/export_openapi.py` | Writes `backend/contracts/openapi.json`; `--contract-only` converts the approved YAML, while the default mode exports the runtime FastAPI schema. Do not hand-edit generated JSON. |
| `frontend/openapi.config.mjs`, `frontend/scripts/generate-api.mjs`, `frontend/src/api/generated/` | D (Yiguang Sun): generation reads `backend/contracts/openapi.yaml`; generated SDK, types and manifest are committed, not manually edited. |
| `.github/workflows/backend.yml`, `.github/workflows/frontend.yml`, `.github/actions/manual-ecs/action.yml` | Shared A (BIN LIN)/C (Andy Wen) review under the `.github/` CODEOWNERS rule. These are the current manually dispatched release workflows and their common action. |

The current CODEOWNERS entries use the actual GitHub usernames: A (BIN LIN) is `@BIN-LIN-AUT2026`, B (Yujuan Gao) is `@Nicole-Gao2026`, C (Andy Wen) is `@andywen-aut`, and D (Yiguang Sun) is `@Yiguang-Sun`.

### 7.7 Database and Local Runtime File Rules

- `backend/database/schema.sql`: the sole executable schema contract; creates the shared `service_desk` database, all 19 tables, reference data, constraints, indexes and triggers; for empty databases only.
- `backend/app/db/bootstrap.py`: verifies that the target database is empty, applies the canonical `schema.sql` and records execution results; must not use `Base.metadata.create_all()` to generate a different schema.
- `backend/app/db/seed.py`: idempotently verifies/completes the final reference data defined by the canonical SQL; must not insert test passwords or personal data.
- `backend/app/db/seed_demo.py`: local demo accounts and data only; must not run in the final environment.
- `backend/app/db/verify_schema.py`: checks the schema version, 19 tables, key indexes, 35 foreign keys, unique/CHECK constraints, two audit triggers, reference data and SQLAlchemy mapping drift.
- `backend/database/release/schema-dump.sql`: generated with `mysqldump --no-data` from the tested release database, solely for comparison with canonical SQL and assignment evidence; not an alternative schema source.
- `backend/database/release/schema-verification.txt`: stores the comparison between canonical SQL and the actual release schema.
- `backend/database/patches/`: contains only reviewed, versioned SQL patches created after schema freeze.
- `docker-compose.local.yml`: starts only local MySQL; debug the backend directly in PyCharm and run the frontend locally with Vite.
- `.env`, AWS keys, database passwords, JWT secrets and Terraform state/variable values must never enter Git. Commit only `.env.example` and `terraform.tfvars.example`.

### 7.8 Branches, PRs and Conflict Avoidance

- Branch names follow `<type>/WBS-<member>-<number>-<slug>`, for example `feature/WBS-A15-s3-presigned-upload`, `feature/WBS-B09-create-ticket`, `feature/WBS-C23-tier2-escalation` and `feature/WBS-D12-ticket-detail-page`.
- One Trello card corresponds to one short-lived branch and one clearly scoped PR; do not create long-lived personal branches.
- Domain owners change only their own domains. For cross-domain changes, submit the provider contract/fixture before the consumer.
- Before changing shared files, record the dependency on the Trello card and let the maintainer merge it. All four members must not simultaneously edit `router.py`, `model_registry.py` or generated OpenAPI directly.
- PRs must include a feature description, changed files, API/schema impact, test results, OpenAPI status, evidence and the Trello card link. Merge with a merge commit after review by at least one non-author.
- Direct commits, rebasing, force pushes and other history rewriting on `main` are prohibited. Delete short-lived branches after merging.

---

## 8. Development, Testing and Integration Gates

### 8.1 Definition of Done

A feature is Done only when all of the following hold: implementation is merged; role/state/deadline validation is complete; unit/contract tests pass; OpenAPI and examples are updated; canonical SQL, database design and SQLAlchemy mappings show no drift; empty-database bootstrap/seed remains reproducible; no secrets/personal data are included; error paths and audit events are verified; and necessary screenshots/command outputs are linked to Trello.

### 8.2 Test Ownership

| Layer | Owner | Minimum Coverage |
|---|---|---|
| Backend Unit/Service | Each API owner | Success, 403/404, invalid states, deadline boundaries and idempotency |
| Database/Schema | Each domain model owner; B (Yujuan Gao) coordinates | Empty MySQL bootstrap, seed idempotency, foreign keys/unique constraints/indexes and schema verification; patch plan after freeze |
| Contract/API | Each API owner | OpenAPI schema, authentication, error codes and direct calls by the marker |
| Workflow/SLA/Concurrency | C (Andy Wen) | Frozen clock; 48h/80%/120h/7d boundaries; revalidation after row locks; job reruns |
| Attachment/Storage | A (BIN LIN) | Presign, HeadObject, Mismatch, Expiry, Idempotent Complete, Cleanup Race, CLOSED |
| Frontend Component/Accessibility | D (Yiguang Sun) | Role Routes, Loading/Empty/Error, Status Mapping, Close Warning |
| E2E/Manual | D (Yiguang Sun) organises; scenario owners provide data | User→T1→T2/Vendor→Resolution→Reopen/Close; attachments; permission isolation |
| Cloud Smoke/Operations | A (BIN LIN) | Public URLs, Health, Logs, Scheduler, Restart/Rollback |

Attachment cleanup must lock the upload session and reread its state first. Delete only EXPIRED/ABORTED objects, never COMPLETED objects. SLA/closure jobs and API boundary tests use the same clock/deadline service to prevent divergence between two rule sets.

### 8.3 CI, Integration and Release Gates

| Gate | Required Checks |
|---|---|
| PR CI | Backend lint/unit/contract/empty-database-bootstrap checks; Frontend lint/type/component/build; Secret Scan; Docker Build |
| Merge to main | OpenAPI compatibility; fresh local MySQL bootstrap; API integration tests; seed idempotency |
| Cloud Candidate | Backend/Frontend Images, Database Bootstrap Task, Health/Smoke, S3 Upload, Scheduler Dry Run |
| Final Release | Critical E2E, role visibility, direct API tests, CloudWatch evidence, rollback information and public URLs |

Do not manually repair data in shared local testing or final environments merely to make tests pass. When an issue is found, update the canonical SQL, database design, SQLAlchemy mappings, bootstrap, seed, necessary SQL patches or application code as appropriate, then redeploy from a traceable version so the environment remains reproducible.

---

## 9. Milestones and Dependencies

| Milestone | Dates | Objective | Exit Evidence |
|---|---|---|---|
| M0 Baseline Freeze | 20–23 Aug | Agree on v4, owners, workflow and AttachmentUpload | This document + changelog + Trello |
| M1 Contract/Skeleton | 24–30 Aug | Repository, CI, OpenAPI, models, cross-domain interfaces and mocks | CI green; OpenAPI usable by D (Yiguang Sun) |
| M2 Core Vertical Slice | 31 Aug–6 Sep | Auth, tickets, assignment, comments and the first frontend flow | Users can create and view assigned tickets |
| M3 Workflow/Storage | 7–13 Sep | T1/T2/Vendor/SLA, AttachmentUpload, Audit | API Integration Tests Green |
| M4 Frontend Integration | 14–20 Sep | Pages for each role, dashboard, attachments and error handling | Local critical-path E2E |
| M5 Cloud Integration | 21–27 Sep | Final RDS/S3/ECR/ECS/ALB/CloudFront/Scheduler; Database Bootstrap | Public URLs + Bootstrap/Cloud Smoke |
| M6 Hardening | 28 Sep–4 Oct | Permissions, concurrency, deadlines, failure/rollback and cost | Regression/E2E green |
| M7 Evidence/Report | 5–11 Oct | Report, API List, Work Log, Screenshots, Demo | Draft Review + Evidence Index |
| M8 Submission Buffer | 12–15 Oct | Freeze, final verification and submission package | Complete submission checklist |

There are only three key dependencies: M1 contracts and model skeletons precede parallel development; M4 schema freeze and the backend candidate image precede final RDS bootstrap/backend deployment; and the backend/OpenAPI candidate precedes final E2E. The presentation date follows Canvas/class announcements and is currently TBC.

---

## 10. MVP Acceptance and Submission Evidence

### 10.1 Business Acceptance

- Users can create, view, add information to, confirm, reopen and close their own tickets; CLOSED tickets cannot be written to or reopened.
- Tier 1 can handle tickets, request information, resolve or escalate; Tier 2 can collaborate with vendors and remains ultimately responsible to the user.
- The 48h Engineering SLA, 80% warning, five-day user timer and seven-day closure window produce consistent results in APIs and jobs.
- Managers act only according to the assignment matrix; vendors access only their organisation's vendor threads/shared data.
- Lifecycle, SLA, comment, vendor and attachment operations all produce immutable audit events with the correct scope.

### 10.2 Technical Acceptance

- The marker can use the frontend through a public HTTPS URL and directly call the public backend API/OpenAPI.
- The client, backend and cloud database form three distinct tiers; RDS/S3 remain private and use least privilege.
- Persistent upload sessions bind attachments to the ticket, creator, visibility and object; Complete uses HeadObject as the authoritative source and is idempotent.
- All 32 public APIs can be listed and tested, including 17 POST endpoints, meeting the assignment minimum.
- Git history, pull requests, Trello, CI, cloud logs and API/E2E results demonstrate individual contributions and team integration.

### 10.3 Final Deliverables

- Report PDF: planning, responsibilities/worklog, architecture/cloud implementation, manual, API list, tests/evidence and URLs.
- Source Repository: Frontend/Backend, SQLAlchemy Models, Canonical `backend/database/schema.sql`, Database Bootstrap/Seed, Release Schema Verification, Tests, Docker/IaC or Deployment Config, README/Runbook.
- Evidence index: each requirement → screenshot/log/test/commit/Trello link.
- Public frontend URL, backend base URL and Swagger URL; test account and role documentation must not include real passwords in the repository.

---

## 11. Decision Index and References

### 11.1 Consolidated Decisions

| ID | Decision |
|---|---|
| D01 | FastAPI + React/TypeScript + MySQL + S3; separate frontend/backend containers |
| D02 | Separate user-facing and internal states; show PENDING_VENDOR to users as IN_PROGRESS |
| D03 | 48h engineering cycle; start a new cycle only after a user action; tier/vendor/reassignment changes do not reset it |
| D04 | Both PENDING_USER reasons share a five-day timer; RESOLVED allows Reopen/Manual Close for seven days; CLOSED is terminal |
| D05 | At most one active VendorRequest per ticket; Tier 2 may cancel the wait and resolve directly |
| D06 | AttachmentUpload is the persistent session between Presign and Attachment; Complete verifies with HeadObject and is idempotent |
| D07 | Workflow and TicketEvent commit atomically; revalidate against the latest state after acquiring row locks |
| D08 | CloudFront HTTPS → ALB → ECS; private RDS/S3; browsers use only presigned S3 URLs |
| D09 | SLA and attachment cleanup use separate EventBridge-scheduled ECS tasks |
| D10 | Domain owners deliver their implementation, SQLAlchemy models/schema, tests and OpenAPI; coordinators must not become single points of delay |
| D11 | Run a one-off database bootstrap/seed task on empty final RDS, then deploy the backend, followed by the frontend, scheduler and E2E |
| D12 | A (BIN LIN)/B (Yujuan Gao)/C (Andy Wen) each use local MySQL during feature development; AWS retains only one private development S3 bucket, without development-stage RDS/compute |
| D13 | Git uses a monorepo with five workspaces; organise code by domain, assign maintainers to shared files, and use one short-lived branch per Trello task |

### 11.2 References

- `INFS803 Cloud Computing 2026 S2 Assignment-2.pdf` (original course assignment).
- AWS CloudFront Developer Guide: Application Load Balancer origins; HTTPS viewer/origin settings.
- Amazon ECS Developer Guide: running scheduled tasks with EventBridge Scheduler.
- Amazon S3 API Reference: HeadObject.
- Major v3→v4 changes are documented in `IT-Service-Desk-Unified-Project-Baseline-v3-to-v4-Changelog.md`. The main v4→v5 changes were removing Alembic, eliminating development-stage integration RDS, and adopting local MySQL and development S3. The main v5→v6 changes are the common database name `service_desk`, the complete 19-table schema in every environment, canonical SQL as the sole executable schema contract, stable keys plus `null` for required response fields, and frontend mock examples for all 32 APIs in OpenAPI v1.1. Earlier decisions/discussion details remain in historical versions and are not repeated here.

---

**Baseline Rule**: Development starts after M0. Any change to states, SLAs, role scopes, API contracts, data models or ownership boundaries requires a team change decision and updates to this document, OpenAPI, tests and Trello. Informal chat conclusions alone cannot override this baseline.

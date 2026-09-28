# IT Service Desk — Final API Development Specification

## FastAPI / OpenAPI 统一接口合同

**版本**：v1.1  
**日期**：2026-09-01  
**基线**：`IT-Service-Desk-Unified-Project-Baseline-v6.0.md`  
**接口数量**：33（A=7、B=14、C=12）
**机器可读合同**：`IT-Service-Desk-OpenAPI-v1.1.yaml`  
**状态**：可直接用于 FastAPI Router、Pydantic Model、Swagger、Frontend Mock 和 TypeScript Client 开发

> 本文冻结所有公共 HTTP 合同。SQLAlchemy Table、内部 Service/Repository 可以按 Owner 实现，但不得改变本文的 Path、Method、字段、Role Scope、状态语义或错误码。v1.1 明确 Required Response Field 始终存在，无值或对当前 Role 不可见时返回 JSON `null`，并为全部 33 个 Operation 提供 Frontend Mock Example。变更必须同时修改本文、OpenAPI YAML、Examples、Tests、Frontend Types 和 Trello Decision。

---

## 1. FastAPI 实现标准

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

统一要求：

- Pydantic v2 Request Model 使用 `ConfigDict(extra="forbid")`，拒绝未声明字段。
- FastAPI `RequestValidationError` 必须由全局 Handler 转换为本文 `ErrorResponse`，不直接返回 FastAPI 默认 `detail` 数组。
- Router 只做 HTTP/Dependency/Serialization；权限、事务和状态转换放 Service；Database Query 放 Repository。
- 所有写操作在事务内重新读取并验证；Workflow 写入和 TicketEvent 同一事务。
- Response 不使用 `response_model_exclude_none=True` 随机删除 Required Field。OpenAPI `required` 中的字段必须始终存在；没有业务值或对当前 Role 不可见时返回 JSON `null`。

## 2. 公共 URL、Header 与数据格式

| 项目 | 规则 |
|---|---|
| Local Base URL | `http://localhost:8000/api/v1` |
| Final Base URL | `https://<cloudfront-domain>/api/v1` |
| Swagger | `/api/docs` |
| OpenAPI | `/api/openapi.json` |
| Authentication | `Authorization: Bearer <access_token>`；API-01/08/09 除外 |
| Request ID | Client 可传 `X-Request-ID: <uuid>`；否则 Backend 生成 |
| Response Header | 所有 Response 返回 `X-Request-ID` |
| Content Type | Backend JSON 使用 `application/json`；S3 PUT 使用 Presign 返回 Header |
| Time | UTC ISO 8601，例如 `2026-09-15T03:20:15Z` |
| IDs | Ticket/User/Comment/Event/Vendor 使用 `integer/int64`；Attachment/Upload 使用 UUID |
| Pagination | `page=1`，`page_size=20`，最大 100 |
| Unknown fields | Request Body 拒绝额外字段 |
| Required Response Field | 始终返回稳定 Key；无值或当前 Role 不可见时为 JSON `null`，不得在 `null` 和省略之间变化 |
| Frontend Example | OpenAPI v1.1 每个 Operation 至少包含一个成功 Example；Example 是 Mock/页面开发输入，不代替 Schema |
| Local CORS | Backend 默认允许 `http://localhost:5173`；Final 通过 CloudFront 同 Origin `/api/*` 访问 |

成功 Envelope：

```json
{ "data": {} }
```

列表 Envelope：

```json
{ "data": [], "meta": { "page": 1, "page_size": 20, "total": 0, "total_pages": 0 } }
```

错误 Envelope：

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

### 2.1 Frontend 正式交付和 Mock 使用规则

Frontend 成员 D 不需要等待 Backend 完成后才开始开发。正式交付包由本文和 `IT-Service-Desk-OpenAPI-v1.1.yaml` 组成，使用顺序如下：

1. 从 OpenAPI v1.1 生成 TypeScript Types/API Client，不手工复制字段。
2. 使用每个 Operation 的成功 Example 建立 MSW、Prism 或本地 Mock Response。
3. 使用 `Role`、`status`、`display_status` 和 `available_actions` 控制页面与按钮；Frontend 隐藏按钮不能代替 Backend 权限校验。
4. Required Field 始终按固定 Key 读取；值可能为 `null`，但不得假设 Backend 会省略该 Key。
5. Attachment 必须执行 API-02 → Browser Raw PUT S3 → API-03，不把 S3 PUT 当作 Backend JSON API。
6. Backend 可运行后只替换 Base URL，不重新定义 TypeScript Interface。

Examples 用于展示典型成功场景和驱动 Mock，不改变 Schema 约束。Frontend 测试仍需覆盖空列表、`null`、401、403、404、409、422 和 503 等情况。

## 3. 公共枚举

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

## 4. API 总览

| ID | Owner | Method | Path | Summary |
|---:|---|---|---|---|
| API-01 | A | GET | `/health` | Backend health check |
| API-02 | A | POST | `/tickets/{id}/attachments/presign` | Create attachment upload session |
| API-03 | A | POST | `/tickets/{id}/attachments/complete` | Complete attachment upload |
| API-04 | A | GET | `/tickets/{id}/attachments` | List ticket attachments |
| API-05 | A | GET | `/tickets/{id}/attachments/{attachment_id}/download` | Generate attachment download URL |
| API-06 | A | GET | `/dashboard/summary` | Get dashboard summary |
| API-07 | A | GET | `/dashboard/overdue-tickets` | List current/history overdue |
| API-08 | B | POST | `/auth/register` | Register USER |
| API-09 | B | POST | `/auth/login` | Login |
| API-10 | B | GET | `/users/me` | Get profile |
| API-11 | B | PATCH | `/users/me` | Update profile |
| API-12 | B | GET | `/reference-data` | Get reference data |
| API-13 | B | GET | `/users/assignees` | List engineers |
| API-14 | B | GET | `/vendors` | List vendors |
| API-15 | B | POST | `/tickets` | Create ticket |
| API-16 | B | GET | `/tickets` | List tickets |
| API-17 | B | GET | `/tickets/{id}` | Get ticket detail |
| API-18 | B | PATCH | `/tickets/{id}` | Update ticket core |
| API-19 | B | GET | `/tickets/{id}/comments` | List comments |
| API-20 | B | POST | `/tickets/{id}/comments` | Create ordinary comment |
| API-21 | C | POST | `/tickets/{id}/assign` | Assign/reassign |
| API-22 | C | POST | `/tickets/{id}/start` | Start handling |
| API-23 | C | POST | `/tickets/{id}/request-user-info` | Request user info |
| API-24 | C | POST | `/tickets/{id}/resume` | Resume ticket |
| API-25 | C | POST | `/tickets/{id}/escalate` | Escalate to Tier 2 |
| API-26 | C | POST | `/tickets/{id}/vendor-requests` | Request vendor |
| API-27 | C | POST | `/tickets/{id}/vendor-response` | Vendor response |
| API-28 | C | POST | `/tickets/{id}/resolve` | Submit resolution |
| API-29 | C | POST | `/tickets/{id}/confirm-resolution` | Confirm resolution |
| API-30 | C | POST | `/tickets/{id}/reopen` | Reopen ticket |
| API-31 | C | POST | `/tickets/{id}/close` | Manual close |
| API-32 | C | GET | `/tickets/{id}/events` | List audit events |
| API-33 | B/C | GET | `/tickets/{id}/vendor-requests` | List vendor request history |

---

## 5. 33 个接口详细合同

### API-01 — GET `/health`

**具体作用与功能**

- **使用场景**：组员、教师或运维人员想确认“后端服务现在能不能用”，例如部署完成后或前端无法登录时进行检查。
- **用户操作**：在浏览器或测试工具中访问 `/health`，不需要登录，也不需要填写任何内容。
- **用户看到的结果**：服务正常时看到 `200`、服务版本和当前时间；服务或数据库不可用时看到 `503`。前端成员可据此判断问题来自后端环境，而不是自己的页面代码。
- **对用户的提示**：这个接口只表示后端和数据库的基本连接正常，不代表登录、上传附件等全部业务功能都已经测试通过。

- **作用**：Backend health check。Checks backend version and database readiness; used by ALB and deployment smoke tests.
- **Owner**：成员 A
- **Access**：Public
- **成功**：HTTP 200，Response Model：`HealthResponse`
- **业务错误码**：SERVICE_UNAVAILABLE

**Path / Query 参数**

无。

**Request Body**：无。

**Response Body**：见 `HealthResponse`；全部字段见第 7 节 Model 字典。

---

### API-02 — POST `/tickets/{id}/attachments/presign`

**具体作用与功能**

- **使用场景**：用户、工程师或供应商正在工单详情页添加截图、日志或其他证明文件。
- **用户操作**：选择一个符合大小和格式要求的文件，设置允许的可见范围，然后点击“上传”。前端会自动调用本接口，用户不需要接触 S3 或填写存储地址。
- **用户看到的结果**：系统同意上传后，页面立即开始显示文件上传进度；如果文件类型、大小、权限或供应商范围不符合要求，页面会在真正上传前给出错误提示。
- **对用户的提示**：本接口只是取得一次性的临时上传许可，文件此时还没有正式出现在工单附件列表中；临时许可约 15 分钟后失效，失效后重新选择或重试即可。

- **作用**：Create attachment upload session。Creates PENDING upload session and S3 Presigned PUT; does not receive bytes.
- **Owner**：成员 A
- **Access**：Scoped authenticated role
- **成功**：HTTP 201，Response Model：`PresignResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, TICKET_CLOSED, NO_ACTIVE_VENDOR_REQUEST, ATTACHMENT_TOO_LARGE, UNSUPPORTED_ATTACHMENT_TYPE

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body：`PresignRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `file_name` | string | 是 | minLength: 1; maxLength: 255 | Base file name. |
| `content_type` | string | 是 | enum: image/png, image/jpeg, application/pdf, text/plain | Expected MIME. |
| `size_bytes` | integer | 是 | min: 1; max: 10485760 | Expected bytes. |
| `visibility` | AttachmentVisibility | 是 |  | Attachment visibility. |

请求示例：

```json
{
  "file_name": "router-error.log",
  "content_type": "image/png",
  "size_bytes": 28431,
  "visibility": "USER_VISIBLE"
}
```

**Response Body**：见 `PresignResponse`；全部字段见第 7 节 Model 字典。

---

### API-03 — POST `/tickets/{id}/attachments/complete`

**具体作用与功能**

- **使用场景**：附件文件已经传输完成，系统需要把它正式登记到当前工单中。
- **用户操作**：用户无需再次点击按钮；前端在文件进度达到 100% 后自动调用本接口完成确认。
- **用户看到的结果**：确认成功后，文件出现在工单的附件列表中，并可以按权限查看或下载；如果云端暂时还没有识别到文件，页面可以自动重试，而不会产生重复附件。
- **对用户的提示**：只有本接口成功后才算真正完成附件添加。若页面显示“上传完成但确认失败”，用户可点击重试，不需要重新上传文件。

- **作用**：Complete attachment upload。HeadObject verification and idempotent Attachment/Event creation; body accepts upload_id only.
- **Owner**：成员 A
- **Access**：Presign creator
- **成功**：HTTP 200，Response Model：`AttachmentResponse`
- **业务错误码**：RESOURCE_NOT_FOUND, UPLOAD_NOT_READY, UPLOAD_SESSION_EXPIRED, TICKET_CLOSED, NO_ACTIVE_VENDOR_REQUEST, UPLOAD_INTEGRITY_MISMATCH

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body：`CompleteUploadRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `upload_id` | string(uuid) | 是 |  | Only accepted field. |

请求示例：

```json
{
  "upload_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response Body**：见 `AttachmentResponse`；全部字段见第 7 节 Model 字典。

---

### API-04 — GET `/tickets/{id}/attachments`

**具体作用与功能**

- **使用场景**：用户打开工单详情页的“附件”区域，想查看该工单已经上传了哪些文件。
- **用户操作**：进入附件区域、切换分页，或完成新附件上传后刷新列表。
- **用户看到的结果**：页面显示自己有权查看的文件名、类型、大小、上传者和上传时间；普通用户、内部工程师和供应商看到的附件可能不同。
- **对用户的提示**：列表中看不到某个附件通常表示该附件的可见范围不包含当前用户；本接口只列出文件信息，点击下载时还会再次检查权限。

- **作用**：List ticket attachments。Role/visibility/vendor-filtered attachment metadata.
- **Owner**：成员 A
- **Access**：Scoped authenticated role
- **成功**：HTTP 200，Response Model：`AttachmentListResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |
| `page` | query | integer | 否 | default=1; min: 1 | Page number. |
| `page_size` | query | integer | 否 | default=20; min: 1; max: 100 | Page size. |
| `visibility` | query | AttachmentVisibility | 否 |  | Visibility filter. |

**Request Body**：无。

**Response Body**：见 `AttachmentListResponse`；全部字段见第 7 节 Model 字典。

---

### API-05 — GET `/tickets/{id}/attachments/{attachment_id}/download`

**具体作用与功能**

- **使用场景**：用户在工单附件列表中找到需要的截图、日志或文档并准备打开或保存。
- **用户操作**：点击附件旁边的“下载”或“查看”按钮。
- **用户看到的结果**：权限通过后浏览器立即开始下载或打开文件；没有权限、附件不存在或临时链接失效时，页面显示对应提示。
- **对用户的提示**：下载地址只有约 5 分钟有效，不能长期收藏或转发；过期后回到工单页面再次点击下载即可获得新地址。

- **作用**：Generate attachment download URL。Rechecks access and returns five-minute opaque Presigned GET.
- **Owner**：成员 A
- **Access**：Scoped authenticated role
- **成功**：HTTP 200，Response Model：`DownloadResponse`
- **业务错误码**：RESOURCE_NOT_FOUND, STORAGE_UNAVAILABLE

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |
| `attachment_id` | path | string(uuid) | 是 |  | Attachment UUID. |

**Request Body**：无。

**Response Body**：见 `DownloadResponse`；全部字段见第 7 节 Model 字典。

---

### API-06 — GET `/dashboard/summary`

**具体作用与功能**

- **使用场景**：经理或工程师登录后先查看 Dashboard，快速了解现在有多少工单需要处理。
- **用户操作**：打开或刷新 Dashboard，无需手工选择工单。
- **用户看到的结果**：经理看到整个服务台的工单总量、各状态数量、即将超时和已经超时的数量；工程师只看到分配给自己的工作量和风险提醒。
- **对用户的提示**：这些卡片是汇总数字，不包含每张工单的完整内容；用户可点击相应卡片，再进入工单列表或超时列表查看明细。

- **作用**：Get dashboard summary。GLOBAL for Manager; MY_ASSIGNED for Tier 1/Tier 2.
- **Owner**：成员 A
- **Access**：ENGINEER_TIER1, ENGINEER_TIER2, SERVICE_DESK_MANAGER
- **成功**：HTTP 200，Response Model：`DashboardSummaryResponse`
- **业务错误码**：DATA_SCOPE_DENIED, SERVICE_UNAVAILABLE

**Path / Query 参数**

无。

**Request Body**：无。

**Response Body**：见 `DashboardSummaryResponse`；全部字段见第 7 节 Model 字典。

---

### API-07 — GET `/dashboard/overdue-tickets`

**具体作用与功能**

- **使用场景**：经理或工程师看到 Dashboard 上存在超时工单，想知道具体是哪几张以及超时多久。
- **用户操作**：点击“Overdue”卡片，在当前超时和历史超时之间切换，并可按类别或优先级筛选。
- **用户看到的结果**：当前模式列出仍未处理完且已经超过 SLA 的工单；历史模式列出曾经发生过超时的记录，便于复盘和作业展示。
- **对用户的提示**：这个页面只用于查找和分析超时情况，不会自动改派或改变工单状态；点击某条记录后才能进入详情页继续处理。

- **作用**：List current/history overdue。Current active overdue cycles or SLA_OVERDUE event history.
- **Owner**：成员 A
- **Access**：ENGINEER_TIER1, ENGINEER_TIER2, SERVICE_DESK_MANAGER
- **成功**：HTTP 200，Response Model：`OverdueListResponse`
- **业务错误码**：DATA_SCOPE_DENIED, VALIDATION_ERROR

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `mode` | query | string | 否 | enum: current, history | View mode. |
| `page` | query | integer | 否 | default=1; min: 1 | Page number. |
| `page_size` | query | integer | 否 | default=20; min: 1; max: 100 | Page size. |
| `category` | query | Category | 否 |  | Category filter. |
| `priority` | query | Priority | 否 |  | Priority filter. |

**Request Body**：无。

**Response Body**：见 `OverdueListResponse`；全部字段见第 7 节 Model 字典。

---

### API-08 — POST `/auth/register`

**具体作用与功能**

- **使用场景**：还没有账号的普通员工需要提交 IT 故障或服务请求。
- **用户操作**：在注册页填写姓名、邮箱和符合要求的密码，然后点击“注册”。
- **用户看到的结果**：信息有效且邮箱未被使用时，系统创建普通用户账号；邮箱重复、格式错误或密码不符合规则时，页面明确提示用户修改。
- **对用户的提示**：自助注册只能获得普通请求者账号；工程师、经理和供应商账号需要由项目预先准备，不能在注册页自行选择角色。

- **作用**：Register USER。Creates requester USER only.
- **Owner**：成员 B
- **Access**：Public
- **成功**：HTTP 201，Response Model：`UserResponse`
- **业务错误码**：EMAIL_ALREADY_REGISTERED, PASSWORD_POLICY_VIOLATION, VALIDATION_ERROR

**Path / Query 参数**

无。

**Request Body：`RegisterRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `email` | string(email) | 是 | maxLength: 254 | Unique email. |
| `password` | string(password) | 是 | minLength: 8; maxLength: 128 | Password; write-only. |
| `display_name` | string | 是 | minLength: 1; maxLength: 100 | Display name. |

请求示例：

```json
{
  "email": "user@example.com",
  "password": "ExamplePass123!",
  "display_name": "Example User"
}
```

**Response Body**：见 `UserResponse`；全部字段见第 7 节 Model 字典。

---

### API-09 — POST `/auth/login`

**具体作用与功能**

- **使用场景**：普通用户、Tier 1、Tier 2、经理或供应商准备进入系统处理各自的工作。
- **用户操作**：在登录页输入邮箱和密码并点击“登录”。
- **用户看到的结果**：验证成功后进入与自己角色匹配的首页；验证失败时看到统一的“邮箱或密码错误”提示，可检查后重新输入。
- **对用户的提示**：登录状态有有效期，过期后需要重新登录；系统不会提示到底是邮箱不存在还是密码错误，以避免泄露账号信息。

- **作用**：Login。Returns JWT and current profile.
- **Owner**：成员 B
- **Access**：Public
- **成功**：HTTP 200，Response Model：`LoginResponse`
- **业务错误码**：INVALID_CREDENTIALS, VALIDATION_ERROR

**Path / Query 参数**

无。

**Request Body：`LoginRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `email` | string(email) | 是 |  | Registered email. |
| `password` | string(password) | 是 | minLength: 1; maxLength: 128 | Password. |

请求示例：

```json
{
  "email": "user@example.com",
  "password": "ExamplePass123!"
}
```

**Response Body**：见 `LoginResponse`；全部字段见第 7 节 Model 字典。

---

### API-10 — GET `/users/me`

**具体作用与功能**

- **使用场景**：用户刚登录或刷新页面，系统需要确认“当前是谁”以及应该显示哪些菜单和功能。
- **用户操作**：用户不需要主动操作；前端会在进入系统时自动读取个人资料。
- **用户看到的结果**：页面右上角显示自己的姓名和角色，并只显示有权限使用的页面；工程师还能看到自己的接单状态，供应商能看到所属组织。
- **对用户的提示**：这里只能查看当前登录者自己的基本资料，不能用来查看其他人的个人信息或密码信息。

- **作用**：Get profile。No password hash/internal scheduling data.
- **Owner**：成员 B
- **Access**：Authenticated
- **成功**：HTTP 200，Response Model：`UserResponse`
- **业务错误码**：AUTHENTICATION_REQUIRED, INVALID_ACCESS_TOKEN

**Path / Query 参数**

无。

**Request Body**：无。

**Response Body**：见 `UserResponse`；全部字段见第 7 节 Model 字典。

---

### API-11 — PATCH `/users/me`

**具体作用与功能**

- **使用场景**：用户想修改系统中显示的姓名；工程师暂时休假、开会或恢复工作时，需要调整是否接受新工单。
- **用户操作**：在 Profile/Settings 页面修改显示名称；Tier 1 或 Tier 2 还可以切换“Available/Unavailable”，然后保存。
- **用户看到的结果**：保存成功后页面立即显示最新资料；工程师设为不可用后，不再被自动分配新的工单，但已经分配的工单仍然保留。
- **对用户的提示**：用户不能在这里修改角色、技能、邮箱或供应商组织；这些信息由项目配置统一管理。

- **作用**：Update profile。Display name; engineers may update availability.
- **Owner**：成员 B
- **Access**：Authenticated
- **成功**：HTTP 200，Response Model：`UserResponse`
- **业务错误码**：DATA_SCOPE_DENIED, VALIDATION_ERROR

**Path / Query 参数**

无。

**Request Body：`UpdateProfileRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `display_name` | string | 否 | minLength: 1; maxLength: 100 | New display name. |
| `is_available` | boolean | 否 |  | Engineer availability; forbidden for non-engineers. |

请求示例：

```json
{}
```

**Response Body**：见 `UserResponse`；全部字段见第 7 节 Model 字典。

---

### API-12 — GET `/reference-data`

**具体作用与功能**

- **使用场景**：用户填写新工单、筛选列表或上传附件时，需要看到系统当前允许选择的类别、优先级、状态和文件规则。
- **用户操作**：用户打开相关页面或下拉框，前端自动读取这些选项，不需要手工调用接口。
- **用户看到的结果**：所有页面使用相同的中文或英文标签、可选值、SLA 提示、文件大小和类型限制；不同角色只看到自己可以使用的选项。
- **对用户的提示**：这些内容是系统规则而不是个人数据，用户只能选择，不能在页面上修改规则本身。

- **作用**：Get reference data。Role-aware enums, timers and attachment limits.
- **Owner**：成员 B
- **Access**：Authenticated
- **成功**：HTTP 200，Response Model：`ReferenceDataResponse`
- **业务错误码**：AUTHENTICATION_REQUIRED, INVALID_ACCESS_TOKEN

**Path / Query 参数**

无。

**Request Body**：无。

**Response Body**：见 `ReferenceDataResponse`；全部字段见第 7 节 Model 字典。

---

### API-13 — GET `/users/assignees`

**具体作用与功能**

- **使用场景**：经理要给未分配或超时工单选择工程师，或者 Tier 1 要选择合适的 Tier 2 进行升级。
- **用户操作**：打开“Assign/Reassign”或“Escalate”窗口，并按层级、技能类别或是否可接单筛选人员。
- **用户看到的结果**：页面列出符合初步条件的工程师、层级、技能、可用状态和当前工作量，帮助用户选择负载和能力更合适的人。
- **对用户的提示**：在名单中选中某人并不等于已经分配；用户还需要点击确认，系统会在最后一步再次检查该人员是否仍然可用。

- **作用**：List engineers。Tier/skill/availability directory for assignment.
- **Owner**：成员 B
- **Access**：ENGINEER_TIER1, ENGINEER_TIER2, SERVICE_DESK_MANAGER
- **成功**：HTTP 200，Response Model：`AssigneeListResponse`
- **业务错误码**：DATA_SCOPE_DENIED, VALIDATION_ERROR

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `page` | query | integer | 否 | default=1; min: 1 | Page number. |
| `page_size` | query | integer | 否 | default=20; min: 1; max: 100 | Page size. |
| `tier` | query | string | 否 | enum: TIER1, TIER2 | Tier filter. |
| `category` | query | Category | 否 |  | Skill filter. |
| `is_available` | query | boolean | 否 |  | Availability filter. |

**Request Body**：无。

**Response Body**：见 `AssigneeListResponse`；全部字段见第 7 节 Model 字典。

---

### API-14 — GET `/vendors`

**具体作用与功能**

- **使用场景**：Tier 2 处理工单时确认需要外部供应商协助，需要先找到正确的供应商组织。
- **用户操作**：打开“Request Vendor”表单，通过名称搜索或翻页选择供应商。
- **用户看到的结果**：页面只列出当前有效的供应商组织，用户选择其中一个后可继续填写要发送给供应商的问题。
- **对用户的提示**：选择供应商不会立即发送请求；必须继续填写安全的请求内容并点击提交。这里也不会显示供应商人员的登录信息。

- **作用**：List vendors。Vendor organisations for Tier 2/Manager.
- **Owner**：成员 B
- **Access**：ENGINEER_TIER2, SERVICE_DESK_MANAGER
- **成功**：HTTP 200，Response Model：`VendorListResponse`
- **业务错误码**：DATA_SCOPE_DENIED, VALIDATION_ERROR

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `page` | query | integer | 否 | default=1; min: 1 | Page number. |
| `page_size` | query | integer | 否 | default=20; min: 1; max: 100 | Page size. |
| `search` | query | string | 否 | maxLength: 100 | Search. |
| `is_active` | query | boolean | 否 |  | Active filter. |

**Request Body**：无。

**Response Body**：见 `VendorListResponse`；全部字段见第 7 节 Model 字典。

---

### API-15 — POST `/tickets`

**具体作用与功能**

- **使用场景**：普通用户遇到电脑、网络、账号或其他 IT 问题，需要正式提交服务请求。
- **用户操作**：在“Create Ticket”页面填写标题、问题描述、类别和优先级，确认后点击“Submit”；附件可在工单创建成功后继续添加。
- **用户看到的结果**：系统生成唯一工单编号并进入“My Tickets”。如果有合适工程师，页面显示已分配；暂时没有合适人员时显示“Unassigned”，工单仍已成功提交并等待经理处理。
- **对用户的提示**：请求者不能自己指定工程师、处理状态或 SLA 截止时间；优先级应按实际影响选择，系统会从提交时开始计算处理时限。

- **作用**：Create ticket。Starts cycle 1 and auto assignment; committed status ASSIGNED/UNASSIGNED.
- **Owner**：成员 B
- **Access**：USER
- **成功**：HTTP 201，Response Model：`TicketDetailResponse`
- **业务错误码**：DATA_SCOPE_DENIED, VALIDATION_ERROR

**Path / Query 参数**

无。

**Request Body：`TicketCreateRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `title` | string | 是 | minLength: 1; maxLength: 200 | Title. |
| `description` | string | 是 | minLength: 1; maxLength: 5000 | Description. |
| `category` | Category | 是 |  | Ticket category. |
| `priority` | Priority | 是 |  | Ticket priority. |

请求示例：

```json
{
  "title": "Office router repeatedly disconnects",
  "description": "The router disconnects several times per hour.",
  "category": "NETWORK",
  "priority": "LOW"
}
```

**Response Body**：见 `TicketDetailResponse`；全部字段见第 7 节 Model 字典。

---

### API-16 — GET `/tickets`

**具体作用与功能**

- **使用场景**：不同角色需要在列表中找到自己要查看或处理的工单。
- **用户操作**：普通用户打开“My Tickets”；工程师打开自己的工作队列；经理查看全局列表；供应商查看与本组织有关的工单，并可使用状态、类别、优先级、SLA、负责人或关键字筛选。
- **用户看到的结果**：页面以分页表格显示工单编号、标题、状态、优先级、负责人和时间等摘要；每个角色只会看到自己有权访问的记录。
- **对用户的提示**：列表只提供快速浏览信息，不显示完整描述、留言和附件；点击某一行后进入工单详情页查看完整内容。

- **作用**：List tickets。Role-aware list; Vendor scope uses request history.
- **Owner**：成员 B
- **Access**：Authenticated
- **成功**：HTTP 200，Response Model：`TicketListResponse`
- **业务错误码**：DATA_SCOPE_DENIED, VALIDATION_ERROR

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `page` | query | integer | 否 | default=1; min: 1 | Page number. |
| `page_size` | query | integer | 否 | default=20; min: 1; max: 100 | Page size. |
| `status` | query | TicketStatus | 否 |  | Status. |
| `category` | query | Category | 否 |  | Category. |
| `priority` | query | Priority | 否 |  | Priority. |
| `sla_status` | query | SlaStatus | 否 |  | SLA. |
| `assignee_id` | query | integer(int64) | 否 | min: 1 | Assignee; role restricted. |
| `search` | query | string | 否 | maxLength: 200 | Search. |
| `sort_by` | query | string | 否 | enum: created_at, updated_at, sla_deadline, priority | Sort field. |
| `sort_order` | query | string | 否 | enum: asc, desc | Direction. |

**Request Body**：无。

**Response Body**：见 `TicketListResponse`；全部字段见第 7 节 Model 字典。

---

### API-17 — GET `/tickets/{id}`

**具体作用与功能**

- **使用场景**：用户从工单列表点击某一张工单，准备查看进展、留言、附件或执行下一步操作。
- **用户操作**：打开工单详情页，或在完成开始处理、请求信息、解决等操作后刷新页面。
- **用户看到的结果**：页面显示当前角色有权查看的标题、描述、状态、负责人、SLA、解决方案和可执行按钮。普通用户看到面向用户的进度，工程师和经理看到内部处理信息，供应商只看到专门提供给供应商的内容。
- **对用户的提示**：同一张工单对不同角色显示的内容和按钮不同；没有访问权限时系统按“工单不存在”处理，避免泄露工单信息。

- **作用**：Get ticket detail。Role-aware detail, display status and available actions.
- **Owner**：成员 B
- **Access**：Scoped authenticated role
- **成功**：HTTP 200，Response Model：`TicketDetailResponse`
- **业务错误码**：RESOURCE_NOT_FOUND

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body**：无。

**Response Body**：见 `TicketDetailResponse`；全部字段见第 7 节 Model 字典。

---

### API-18 — PATCH `/tickets/{id}`

**具体作用与功能**

- **使用场景**：请求者刚提交工单后发现标题、描述、类别或优先级填写错误；经理也可能需要纠正尚未关闭工单的基本信息。
- **用户操作**：在工单详情页点击“Edit”，修改允许的字段并保存。
- **用户看到的结果**：保存成功后详情页显示更新后的内容，并保留谁在什么时间修改过的记录；不允许修改时页面说明工单状态或权限不符合要求。
- **对用户的提示**：普通用户只能编辑自己的未分配工单；负责人、处理状态、SLA、解决方案和供应商不能通过编辑表单直接更改。

- **作用**：Update ticket core。USER own UNASSIGNED; Manager non-CLOSED; no direct status/assignee/SLA changes.
- **Owner**：成员 B
- **Access**：USER owner or SERVICE_DESK_MANAGER
- **成功**：HTTP 200，Response Model：`TicketDetailResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, TICKET_CLOSED, VALIDATION_ERROR

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body：`TicketUpdateRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `title` | string | 否 | minLength: 1; maxLength: 200 | New title. |
| `description` | string | 否 | minLength: 1; maxLength: 5000 | New description. |
| `category` | Category | 否 |  | Ticket category. |
| `priority` | Priority | 否 |  | Ticket priority. |

请求示例：

```json
{}
```

**Response Body**：见 `TicketDetailResponse`；全部字段见第 7 节 Model 字典。

---

### API-19 — GET `/tickets/{id}/comments`

**具体作用与功能**

- **使用场景**：请求者、工程师或经理打开工单的“Conversation/Comments”区域，查看双方之前说过什么。
- **用户操作**：进入留言区域或向下翻页加载更早的留言。
- **用户看到的结果**：普通用户只看到允许用户查看的沟通内容；工程师和经理还可以看到内部备注。每条留言显示作者、时间和内容。
- **对用户的提示**：供应商不使用这个普通留言区；被标记为内部的留言不会展示给请求者，事件时间线也不会混入普通留言列表。

- **作用**：List comments。Role/visibility filtered; Vendor denied.
- **Owner**：成员 B
- **Access**：USER, T1, T2, Manager
- **成功**：HTTP 200，Response Model：`CommentListResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |
| `page` | query | integer | 否 | default=1; min: 1 | Page number. |
| `page_size` | query | integer | 否 | default=20; min: 1; max: 100 | Page size. |
| `visibility` | query | CommentVisibility | 否 |  | Visibility. |

**Request Body**：无。

**Response Body**：见 `CommentListResponse`；全部字段见第 7 节 Model 字典。

---

### API-20 — POST `/tickets/{id}/comments`

**具体作用与功能**

- **使用场景**：请求者想补充一般说明，或者工程师、经理想记录不需要改变处理状态的普通沟通和内部备注。
- **用户操作**：在 Conversation 区输入内容，选择允许的可见范围，然后点击“Send”。
- **用户看到的结果**：新留言立即出现在对话中，但工单状态、负责人和 SLA 不会因此改变。
- **对用户的提示**：当系统正在等待用户补充信息或确认解决方案时，必须使用页面上的“Resume”“Issue Persists”或“Confirm”按钮；普通留言不能完成这些流程。已关闭工单不能再留言。

- **作用**：Create ordinary comment。Creates comment/event; formal waiting-state actors receive guidance errors.
- **Owner**：成员 B
- **Access**：Scoped role; ordinary Vendor comments denied
- **成功**：HTTP 201，Response Model：`CommentResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, USE_RESUME_ACTION, USE_CONFIRM_OR_RESUME_ACTION, USE_VENDOR_RESPONSE_ACTION, TICKET_CLOSED

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body：`CommentCreateRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `message` | string | 是 | minLength: 1; maxLength: 4000 | Message. |
| `visibility` | CommentVisibility | 是 |  | Comment visibility. |

请求示例：

```json
{
  "message": "Please provide the requested information.",
  "visibility": "USER_VISIBLE"
}
```

**Response Body**：见 `CommentResponse`；全部字段见第 7 节 Model 字典。

---

### API-21 — POST `/tickets/{id}/assign`

**具体作用与功能**

- **使用场景**：经理需要把未分配、重新打开或允许改派的超时工单交给某位工程师处理。
- **用户操作**：在工单或队列中点击“Assign/Reassign”，查看候选人员，选择一位工程师并确认。
- **用户看到的结果**：成功后工单显示新的负责人；未分配或重开工单会进入可开始处理的状态，操作也会出现在时间线中。
- **对用户的提示**：如果所选工程师层级、技能或可用状态不符合要求，页面会要求重新选择；并非所有处理状态都允许经理随时换人。

- **作用**：Assign/reassign。Strict matrix and engineer eligibility.
- **Owner**：成员 C
- **Access**：SERVICE_DESK_MANAGER
- **成功**：HTTP 200，Response Model：`TicketActionResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, ASSIGNEE_NOT_ELIGIBLE, TICKET_CLOSED

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body：`AssignmentRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `assignee_id` | integer(int64) | 是 |  | Target engineer. |
| `reason` | string | 否 | minLength: 1; maxLength: 1000 | Reason. |

请求示例：

```json
{
  "assignee_id": 10001
}
```

**Response Body**：见 `TicketActionResponse`；全部字段见第 7 节 Model 字典。

---

### API-22 — POST `/tickets/{id}/start`

**具体作用与功能**

- **使用场景**：Tier 1 或 Tier 2 接到一张已分配或重新打开的工单，准备正式开始排查。
- **用户操作**：当前负责人在工单详情页点击“Start Work”。
- **用户看到的结果**：工单状态从“Assigned/Reopened”变为“In Progress”，请求者和经理能看到处理已经开始，时间线记录开始处理的人员和时间。
- **对用户的提示**：只有当前负责人能点击开始；已经处理中、等待中或已关闭的工单不能重复开始，原有 SLA 计时不会被重置。

- **作用**：Start handling。ASSIGNED/REOPENED to IN_PROGRESS.
- **Owner**：成员 C
- **Access**：Current assignee
- **成功**：HTTP 200，Response Model：`TicketActionResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, TICKET_CLOSED

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body**：无。

**Response Body**：见 `TicketActionResponse`；全部字段见第 7 节 Model 字典。

---

### API-23 — POST `/tickets/{id}/request-user-info`

**具体作用与功能**

- **使用场景**：当前工程师无法继续排查，例如还需要报错截图、设备编号、发生时间或用户测试结果。
- **用户操作**：工程师点击“Request User Information”，清楚写明需要用户提供什么，然后提交。
- **用户看到的结果**：请求者在工单页面看到醒目的“Waiting for your information”和工程师的问题，并获得 120 小时回复期限；工程师侧显示正在等待用户，当前工程处理计时暂停。
- **对用户的提示**：这不是普通留言。工程师只有在正在处理且自己是当前负责人时才能发起；请求者需要使用专门的回复/恢复操作让工单继续处理。

- **作用**：Request user info。USER_VISIBLE request; pause cycle; PENDING_USER/INFORMATION_REQUIRED for 120h.
- **Owner**：成员 C
- **Access**：Current assignee in IN_PROGRESS
- **成功**：HTTP 200，Response Model：`TicketActionResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, TICKET_CLOSED

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body：`RequestUserInfoRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `message` | string | 是 | minLength: 1; maxLength: 4000 | User-visible request. |

请求示例：

```json
{
  "message": "Please provide the requested information."
}
```

**Response Body**：见 `TicketActionResponse`；全部字段见第 7 节 Model 字典。

---

### API-24 — POST `/tickets/{id}/resume`

**具体作用与功能**

- **使用场景**：请求者收到工程师的补充信息请求后准备回复，或者收到解决方案后发现问题仍然存在。
- **用户操作**：在等待页面点击“Provide Information/Resume”或“Issue Persists”，填写具体补充内容后提交。
- **用户看到的结果**：回复出现在沟通区，工单重新进入“In Progress”，工程师收到可以继续处理的工单，并开始新的 48 小时工程处理周期。
- **对用户的提示**：必须在 120 小时回复窗口内完成；超过期限后系统会先执行规定的自动结果。仅发送普通留言不会恢复工单处理。

- **作用**：Resume ticket。Requester supplies info/issue persists before deadline; new 48h cycle.
- **Owner**：成员 C
- **Access**：Ticket requester
- **成功**：HTTP 200，Response Model：`TicketActionResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, USER_RESPONSE_WINDOW_EXPIRED, TICKET_CLOSED

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body：`ResumeRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `message` | string | 是 | minLength: 1; maxLength: 4000 | Information or issue-persists explanation. |

请求示例：

```json
{
  "message": "Please provide the requested information."
}
```

**Response Body**：见 `TicketActionResponse`；全部字段见第 7 节 Model 字典。

---

### API-25 — POST `/tickets/{id}/escalate`

**具体作用与功能**

- **使用场景**：Tier 1 判断问题需要更高级权限、专业技能或更深入排查，自己无法继续完成。
- **用户操作**：当前 Tier 1 负责人点击“Escalate to Tier 2”，选择符合技能的 Tier 2，并填写升级原因后确认。
- **用户看到的结果**：工单负责人变为所选 Tier 2，状态回到“Assigned”等待新负责人开始；经理和相关人员可在时间线看到升级原因和交接记录。
- **对用户的提示**：只能升级给当前可用且技能匹配的 Tier 2；升级不会重新计算或延长当前 SLA 截止时间，因此应尽早操作。

- **作用**：Escalate to Tier 2。Select eligible Tier 2; preserve cycle/deadline.
- **Owner**：成员 C
- **Access**：Current Tier 1 assignee in IN_PROGRESS
- **成功**：HTTP 200，Response Model：`TicketActionResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, ASSIGNEE_NOT_ELIGIBLE, TICKET_CLOSED

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body：`EscalateRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `tier2_assignee_id` | integer(int64) | 是 |  | Tier 2 ID. |
| `reason` | string | 否 | minLength: 1; maxLength: 1000 | Reason. |

请求示例：

```json
{
  "tier2_assignee_id": 10001
}
```

**Response Body**：见 `TicketActionResponse`；全部字段见第 7 节 Model 字典。

---

### API-26 — POST `/tickets/{id}/vendor-requests`

**具体作用与功能**

- **使用场景**：Tier 2 确认问题涉及第三方产品或服务，需要指定供应商提供技术支持。
- **用户操作**：点击“Request Vendor”，选择供应商，并重新填写一段可以安全提供给外部人员的问题说明后提交。
- **用户看到的结果**：工单进入“Waiting for Vendor”，所选供应商能在自己的页面看到请求并回复；内部人员能看到当前正在等待哪家供应商。
- **对用户的提示**：系统不会自动把用户原始描述、内部留言或个人信息发送给供应商，Tier 2 必须自行编写脱敏内容；同一工单同时只能等待一个有效供应商请求，且 SLA 仍继续计时。

- **作用**：Request vendor。Create only ACTIVE request; PENDING_VENDOR; SLA continues.
- **Owner**：成员 C
- **Access**：Current Tier 2 assignee
- **成功**：HTTP 201，Response Model：`TicketActionResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, ACTIVE_VENDOR_REQUEST_EXISTS, TICKET_CLOSED

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body：`VendorRequestCreate`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `vendor_org_id` | integer(int64) | 是 |  | Vendor organisation ID. |
| `vendor_message` | string | 是 | minLength: 1; maxLength: 4000 | Vendor-safe message. |

请求示例：

```json
{
  "vendor_org_id": 10001,
  "vendor_message": "Please investigate the router firmware issue."
}
```

**Response Body**：见 `TicketActionResponse`；全部字段见第 7 节 Model 字典。

---

### API-27 — POST `/tickets/{id}/vendor-response`

**具体作用与功能**

- **使用场景**：供应商登录后看到本组织收到的技术支持请求，并已经准备好诊断建议、操作步骤或处理结果。
- **用户操作**：在供应商工单页填写正式回复，必要时按允许的方式添加供应商可见附件，然后点击“Submit Response”。
- **用户看到的结果**：回复提交成功后，该供应商请求显示“Responded”；内部 Tier 2 能看到回复，工单恢复为“In Progress”以便继续处理用户问题。
- **对用户的提示**：供应商只能回复本组织当前有效的请求，不能查看或回复其他供应商的工单；已结束或已经回复的旧请求不能重复提交。

- **作用**：Vendor response。Matching Vendor responds to current ACTIVE request; no request ID in body.
- **Owner**：成员 C
- **Access**：Matching EXTERNAL_VENDOR
- **成功**：HTTP 200，Response Model：`TicketActionResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, NO_ACTIVE_VENDOR_REQUEST, INVALID_STATUS_TRANSITION, TICKET_CLOSED

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body：`VendorResponseRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `message` | string | 是 | minLength: 1; maxLength: 4000 | Vendor response. |

请求示例：

```json
{
  "message": "Please provide the requested information."
}
```

**Response Body**：见 `TicketActionResponse`；全部字段见第 7 节 Model 字典。

---

### API-28 — POST `/tickets/{id}/resolve`

**具体作用与功能**

- **使用场景**：当前工程师认为问题已经解决或已经提供了可执行的解决办法，需要请求者确认实际效果。
- **用户操作**：工程师点击“Resolve”，填写面向请求者的解决步骤、处理结果和验证方法，然后提交。
- **用户看到的结果**：请求者看到“Please confirm resolution”和完整解决方案，可选择确认已解决或说明问题仍存在；系统给请求者 120 小时确认时间。
- **对用户的提示**：普通内部留言不能代替正式解决方案；只有当前负责人能提交。若 Tier 2 在等待供应商时决定直接解决，当前供应商请求会同时结束。

- **作用**：Submit resolution。User-visible resolution; PENDING_USER/RESOLUTION_CONFIRMATION; cancel active Vendor request.
- **Owner**：成员 C
- **Access**：Current assignee
- **成功**：HTTP 200，Response Model：`TicketActionResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, TICKET_CLOSED

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body：`ResolveRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `resolution_summary` | string | 是 | minLength: 1; maxLength: 5000 | User-visible resolution. |

请求示例：

```json
{
  "resolution_summary": "Updated firmware and verified stable connectivity."
}
```

**Response Body**：见 `TicketActionResponse`；全部字段见第 7 节 Model 字典。

---

### API-29 — POST `/tickets/{id}/confirm-resolution`

**具体作用与功能**

- **使用场景**：请求者按照工程师提供的方案进行验证，确认问题已经消失。
- **用户操作**：在工单的解决方案区域点击“Confirm Resolved”，无需再填写内容。
- **用户看到的结果**：工单变为“Resolved”，页面显示确认时间，并进入 7 天观察期；如果问题在观察期内再次发生，请求者仍可选择重新打开。
- **对用户的提示**：需要在 120 小时确认窗口内操作；超过期限后系统会按规则自动标记解决。若问题仍存在，不要点击确认，应使用“Issue Persists”。

- **作用**：Confirm resolution。Requester confirms before 120h deadline; RESOLVED and seven-day window.
- **Owner**：成员 C
- **Access**：Ticket requester
- **成功**：HTTP 200，Response Model：`TicketActionResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, USER_RESPONSE_WINDOW_EXPIRED, TICKET_CLOSED

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body**：无。

**Response Body**：见 `TicketActionResponse`；全部字段见第 7 节 Model 字典。

---

### API-30 — POST `/tickets/{id}/reopen`

**具体作用与功能**

- **使用场景**：工单已经显示“Resolved”，但请求者在 7 天观察期内发现相同问题再次出现或解决方案没有持续生效。
- **用户操作**：点击“Reopen”，填写问题再次发生的时间、现象和原因说明后提交。
- **用户看到的结果**：工单变为“Reopened”并开始新的处理周期；原工程师仍可用时优先交还给原工程师，否则进入未分配状态等待经理安排。
- **对用户的提示**：必须填写重新打开原因；超过 7 天后工单会自动关闭，已关闭工单不能再通过本按钮重开，需要新建一张工单。

- **作用**：Reopen ticket。Before auto_close_at; new SLA cycle; previous assignee preferred if available.
- **Owner**：成员 C
- **Access**：Ticket requester
- **成功**：HTTP 200，Response Model：`TicketActionResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, TICKET_CLOSED

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body：`ReopenRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `reason` | string | 是 | minLength: 1; maxLength: 4000 | Why issue persists. |

请求示例：

```json
{
  "reason": "The issue is still occurring."
}
```

**Response Body**：见 `TicketActionResponse`；全部字段见第 7 节 Model 字典。

---

### API-31 — POST `/tickets/{id}/close`

**具体作用与功能**

- **使用场景**：请求者已经确认问题解决，并且不需要保留 7 天观察期，想立即结束工单。
- **用户操作**：在已解决工单中点击“Close Ticket”，阅读“关闭后不能重新打开”的提示，勾选确认后再次提交。
- **用户看到的结果**：工单立即变为“Closed”，不再出现在待处理队列中，时间线记录由请求者主动关闭。
- **对用户的提示**：关闭是不可撤销操作；没有勾选确认时系统不会执行。关闭后如果问题再次出现，只能创建新工单。

- **作用**：Manual close。Requires acknowledge=true; CLOSED terminal.
- **Owner**：成员 C
- **Access**：Ticket requester
- **成功**：HTTP 200，Response Model：`TicketActionResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, INVALID_STATUS_TRANSITION, CLOSE_ACKNOWLEDGEMENT_REQUIRED, TICKET_CLOSED

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body：`CloseRequest`**

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `acknowledge` | boolean | 是 | const: true | Must be true. |
| `reason` | string | 否 | minLength: 1; maxLength: 1000 | Optional note. |

请求示例：

```json
{
  "acknowledge": true
}
```

**Response Body**：见 `TicketActionResponse`；全部字段见第 7 节 Model 字典。

---

### API-32 — GET `/tickets/{id}/events`

**具体作用与功能**

- **使用场景**：获授权用户想了解一张工单从提交到现在经历了哪些步骤；经理还可用它检查分配、升级、超时和关闭过程。
- **用户操作**：在工单详情页打开“Timeline/History”，向下翻页查看更早记录。
- **用户看到的结果**：页面按时间顺序显示创建、分配、开始处理、等待用户、升级、供应商协作、解决、重开和关闭等事件，以及执行人和时间；不同角色只看到允许公开给自己的事件。
- **对用户的提示**：时间线是系统生成的历史记录，用户不能修改或删除；留言正文和供应商回复仍在各自区域查看，不会在时间线中完整重复显示。

- **作用**：List audit events。Append-only role/scope-filtered timeline with minimal metadata.
- **Owner**：成员 C
- **Access**：Scoped authenticated role
- **成功**：HTTP 200，Response Model：`EventListResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, VALIDATION_ERROR

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |
| `page` | query | integer | 否 | default=1; min: 1 | Page number. |
| `page_size` | query | integer | 否 | default=20; min: 1; max: 100 | Page size. |
| `event_type` | query | EventType | 否 |  | Event type. |
| `scope` | query | EventScope | 否 |  | Scope; role restricted. |

**Request Body**：无。

**Response Body**：见 `EventListResponse`；全部字段见第 7 节 Model 字典。

---

### API-33 — GET `/tickets/{id}/vendor-requests`

**具体作用与功能**

- **使用场景**：Tier 2、Manager 或匹配的供应商重新打开工单后，读取此前持久化的供应商请求与正式回复。
- **用户看到的结果**：请求按创建时间从旧到新返回；已回复请求包含 `response`，未回复或已取消请求的 `response` 为 `null`。
- **权限**：Tier 2 和 Manager 可读取其可见工单的全部供应商历史；Vendor 只能读取本组织历史；USER 和 Tier 1 返回 `403 DATA_SCOPE_DENIED`；不可见或不存在的工单返回 404。
- **安全要求**：响应不包含内部请求人或回复人字段，审计 metadata 不复制请求或回复正文。

- **Owner**：成员 B/C
- **成功**：HTTP 200，Response Model：`VendorRequestHistoryResponse`
- **业务错误码**：DATA_SCOPE_DENIED, RESOURCE_NOT_FOUND, VALIDATION_ERROR, SERVICE_UNAVAILABLE

**Path / Query 参数**

| 参数 | 位置 | 类型 | Required | Default/约束 | 说明 |
|---|---|---|---:|---|---|
| `id` | path | integer(int64) | 是 | min: 1 | Ticket ID. |

**Request Body**：无。

**Response Body**：见 `VendorRequestHistoryResponse`；`data` 不分页，按 `created_at`、`vendor_request_id` 升序。

---

## 6. 关键业务规则

第 6 节规定的是：**系统在什么情况下允许或拒绝某个操作，以及不同角色最终能够看到什么**。单个 API 章节主要说明 URL、请求参数和响应参数；本节则是所有相关 API 都必须共同遵守的业务判断标准。

可以把单个 API 理解为“可以进入哪个入口”，把关键业务规则理解为“进入入口后必须遵守的交通规则”。即使 Frontend 隐藏了某个按钮，Backend 仍然必须按照本节重新检查角色、工单归属、当前状态和 Deadline，不能只相信 Frontend。

本节的具体作用如下：

| 使用者 | 具体用途 |
|---|---|
| Backend 成员 A/B/C | 编写权限检查、状态转换、SLA、附件和留言逻辑时使用，确保不同模块执行同一套规则。 |
| Frontend 成员 D | 根据用户角色、`display_status` 和 `available_actions` 决定显示哪些按钮、提示和页面内容。 |
| 测试人员 | 把每条规则转换为允许场景、拒绝场景、边界时间和越权访问测试。 |
| PM/Marker | 检查实现是否与主业务流程、状态机和安全要求一致。 |

最重要的关系是：

```text
API 定义：前端调用哪个地址、提交哪些字段
        +
关键业务规则：当前用户和当前状态是否允许执行
        =
最终结果：成功返回数据，或者返回统一业务错误
```

### 6.1 Role-aware Serialization

**具体作用**：同一张 Ticket 会根据当前登录用户的角色和业务关系返回不同内容。它既控制“能不能访问这张工单”，也控制“允许访问后具体能看到哪些字段”。这样可以防止普通用户看到内部信息、供应商看到个人信息，或者用户通过猜测 Ticket ID 访问他人的工单。

**最终使用者示例**：

- Requester 打开自己的 Ticket，可以看到面向用户的状态、公开留言、解决方案和 `USER_VISIBLE` 附件。
- Ticket 实际处于 `PENDING_VENDOR` 时，Requester 仍看到 `IN_PROGRESS`，不会看到供应商名称、请求内容或回复内容。
- Tier 2 可以看到已授权的 Vendor Request；Tier 1 不能看到 Vendor Payload 或 `VENDOR_SHARED` 附件。
- Vendor 只看到发给自己 Organisation 的脱敏信息，不能看到 User Personal Data、原始 Description 和内部留言。
- Manager 可以查看全局 Ticket，但仍不能取得密码、Credential 等敏感信息。

**Backend 实现要求**：先判断 Ticket Scope，再使用 Role-aware Serializer 过滤字段。没有权限的资源统一返回 404，不能通过 403 或错误信息告诉调用者“这张工单存在但你无权查看”。

**必须遵守的规则**：

- USER 只能访问自己的 Ticket，且 PENDING_VENDOR 序列化为 IN_PROGRESS，不返回 Vendor 数据。
- Tier 1 仅当前分配 Ticket；看不到 Vendor Payload/VENDOR_SHARED。
- Tier 2 仅当前分配 Ticket；可以查看授权 Vendor 数据。
- Vendor 仅本 Organisation 的 VendorRequest Scope，不返回 User Personal Data/description。
- Manager 全局。隐藏资源统一 404，不通过错误消息泄露存在性。

### 6.2 Workflow / Deadline

**具体作用**：规定 Ticket 在每种状态下可以执行什么操作、由谁执行，以及超过时间边界后系统应该先发生什么。它防止用户在错误状态点击按钮，也防止并发请求把 Ticket 改成互相矛盾的状态。

**最终使用者示例**：

```text
IN_PROGRESS
    ↓ Engineer 请求补充信息
PENDING_USER / INFORMATION_REQUIRED
    ↓ Requester 在 120 小时内调用 API-24 回复
IN_PROGRESS，并开始新的 48 小时 Engineering Cycle
```

- 在等待 Requester 回复时，Engineering SLA 暂停，避免把用户等待时间计算到工程师处理时间中。
- 在等待 Vendor 回复时，Engineering SLA 继续运行，因此 Tier 2 需要持续关注 Deadline。
- Tier 1 升级给 Tier 2、Manager 改派人员或 Vendor 改变时，当前 Cycle 和 Deadline 不重新开始。
- Ticket 进入 `CLOSED` 后只能读取已有授权信息，不能再编辑、留言、分配、重开或上传附件。

**Deadline 边界示例**：用户只有在 `now < deadline` 时才能回复。达到 120 小时的瞬间，即使 Frontend 页面还没有刷新，Backend 也必须先执行自动结果，再拒绝已经过期的用户操作，防止边界时间出现两种不同结果。

**Backend 实现要求**：每个 Workflow API 都要先读取并锁定最新 Ticket，再判断状态、角色和 Deadline，最后把业务对象与 TicketEvent 一起提交。Frontend 显示的按钮只能改善用户体验，不能替代 Backend 校验。

**必须遵守的规则**：

- `now < deadline` 才允许 User Action；`now >= deadline` 先执行自动结果再返回冲突错误。
- PENDING_USER 暂停 Engineering Cycle；PENDING_VENDOR 继续当前 Cycle。
- Tier/Assignee/Vendor 变化不重置 Cycle。
- CLOSED 是终态；读取已有授权数据允许，所有业务写操作拒绝。
- 所有 Workflow 写入先锁 Ticket，再锁 VendorRequest/AttachmentUpload；Event 与业务对象同事务。

### 6.3 Attachment

**具体作用**：规定最终用户如何安全上传和下载文件，同时避免文件先经过 Backend Container。用户只需要在 Ticket 页面选择文件，Frontend 和 Backend 在后台完成 S3 临时授权、上传和登记。

**用户上传一张截图时的完整过程**：

```text
1. 用户在 Ticket Detail 选择 error.png 并点击 Upload
2. Frontend 调用 API-02，取得一次性临时上传地址
3. Browser 使用该地址把原始文件直接 PUT 到 Private S3
4. Frontend 调用 API-03，通知 Backend 检查并正式登记附件
5. API-03 成功后，文件出现在 Attachment List
```

API-02 成功只表示“允许上传”，并不表示附件已经添加完成；只有 API-03 成功后，最终用户才能在工单中看到附件。下载时，用户点击 Download，API-05 会再次检查权限并返回约 5 分钟有效的临时地址。

**具体价值**：

- 用户不需要知道 Bucket、Object Key 或 AWS Credential。
- Browser 直接连接 S3，减少 Backend Container 的网络、内存和 CPU 使用。
- Backend 根据 S3 中的真实文件检查 Size 和 Content-Type，不能相信 Frontend 自报的数据。
- 重复调用 Complete 返回同一个 Attachment，避免网络重试产生重复文件和重复 Event。
- `USER_VISIBLE`、`INTERNAL_ONLY`、`VENDOR_SHARED` 确保不同角色只能看到对应附件。

**必须遵守的规则**：

- 固定三步：API-02 Presign → Browser Raw PUT S3 → API-03 Complete。
- Frontend 不提交 object_key、vendor_request_id、vendor_org_id。
- API-03 只接受 upload_id，以 HeadObject 的实际 Size/Content-Type 为准。
- 重复 Complete 返回原 Attachment，不重复 Attachment/Event。
- 文件限制 10 MiB；PNG/JPG/PDF/TXT/LOG；PUT TTL 15 分钟；GET TTL 5 分钟。

### 6.4 Comment vs Workflow Action

**具体作用**：区分“只增加一条沟通记录”和“需要推动 Ticket 状态变化的正式操作”。如果两者混在一起，用户发送普通留言可能错误地恢复 SLA、确认解决方案或结束 Vendor Request。

| 最终使用者的目的 | 页面操作 | API | 是否改变 Workflow |
|---|---|---|---|
| 发送普通补充说明或内部备注 | Send Comment | API-20 | 否；只增加 Comment/Event。 |
| 回复 Engineer 的资料请求 | Provide Information / Resume | API-24 | 是；返回 `IN_PROGRESS` 并启动新 Engineering Cycle。 |
| 表示解决方案没有解决问题 | Issue Persists | API-24 | 是；返回 `IN_PROGRESS`。 |
| 确认问题已经解决 | Confirm Resolved | API-29 | 是；进入 `RESOLVED`。 |
| Vendor 提交正式回复 | Submit Vendor Response | API-27 | 是；Vendor Request 变为 `RESPONDED`，Ticket 返回 `IN_PROGRESS`。 |

**最终使用者示例**：Ticket 正在 `PENDING_USER / INFORMATION_REQUIRED` 时，Requester 在普通留言框发送“信息已补充”，只会留下文字，不能恢复 Ticket。Frontend 应引导用户点击专门的 `Provide Information / Resume` 按钮；如果仍调用 API-20，Backend 返回 Guidance Error，告诉 Frontend 应改用 API-24。

**Frontend 实现要求**：根据 API-17 返回的 `available_actions` 显示正确按钮，不要把所有动作都做成一个 Comment 输入框。

**必须遵守的规则**：

- 普通 Comment 不触发 Resume、Confirm、Vendor Response。
- PENDING_USER 的 User 使用 API-24/API-29；API-20 返回对应 Guidance Error。
- PENDING_VENDOR 的 Vendor 使用 API-27。

## 7. Pydantic/OpenAPI Model 全字段字典

第 7 节规定的是：**Frontend 发送给 Backend 的 JSON 具体包含哪些字段，以及 Backend 返回给 Frontend 的 JSON 具体长什么样**。它是前后端共同遵守的数据合同，也是 FastAPI 进行自动校验和生成 Swagger 文档的依据。

这部分不是 Database Table 设计。Database Model 关注数据如何存储；Pydantic/OpenAPI Model 关注数据通过 API 传输时允许进入和返回哪些内容。一个 Database Table 可能有密码 Hash、S3 Object Key 等内部字段，但这些字段不应该出现在对外 Response Model 中。

### 7.0 本节的具体作用和阅读方法

#### 7.0.1 四类 Model 分别是什么

| Model 类型 | 数据方向 | 具体作用 | 示例 |
|---|---|---|---|
| Request Model | Frontend → Backend | 规定调用接口时允许或必须提交哪些字段，并拒绝格式错误的数据。 | `LoginRequest`、`TicketCreateRequest`、`ResolveRequest` |
| Response Model | Backend → Frontend | 规定接口成功后返回的最外层 JSON 结构。 | `LoginResponse`、`TicketDetailResponse`、`TicketListResponse` |
| DTO | Backend → Frontend，作为 Response 的内部对象 | 表示一个可重复使用的数据对象，例如用户摘要、工单详情、附件或 SLA 信息。 | `UserProfile`、`TicketDetail`、`AttachmentItem` |
| 公共 Envelope | 所有接口的统一最外层包装 | 让 Frontend 使用固定方式读取成功数据、分页信息和错误信息。 | `data`、`meta`、`error` |

例如成功取得一张 Ticket 时，结构可以理解为：

```text
TicketDetailResponse（Response Model）
└── data: TicketDetail（DTO）
    ├── ticket_id
    ├── title
    ├── status
    ├── assignee: AssigneeSummary（另一个 DTO）
    └── available_actions
```

#### 7.0.2 Pydantic 在 Backend 中做什么

Backend 成员会把本节的字段表编写成 Python Pydantic Class，并在 FastAPI Route 中指定 Request 和 Response Model。Pydantic 会自动完成基础格式校验和输出约束。

以 API-15 创建 Ticket 为例：

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

Frontend 正确提交：

```json
{
  "title": "Cannot connect to office Wi-Fi",
  "description": "The laptop cannot connect after restarting.",
  "category": "NETWORK",
  "priority": "HIGH"
}
```

Pydantic 会检查：

- 四个 Required 字段是否都存在。
- `title` 和 `description` 是否为空或超过最大长度。
- `category` 是否属于 `Category` Enum。
- `priority` 是否属于 `Priority` Enum。
- JSON 字段类型是否正确。

如果 Frontend 提交空标题、使用不存在的 `category="PRINTER"`，或者把 `priority` 发送成数字，FastAPI 会在进入业务 Service 前拒绝请求并返回 Validation Error。这样每个开发成员不需要在 Route 中重复编写同样的基础校验。

Pydantic 只能完成字段类型、长度、格式等结构校验。诸如“当前用户是否是 Ticket Owner”“当前状态是否允许 Reopen”等业务判断，仍必须按照第 6 节在 Service/Policy 中实现。

#### 7.0.3 OpenAPI 和 Swagger 在协作中做什么

FastAPI 会根据 Route 和 Pydantic Model 自动生成 OpenAPI Schema，并在本地提供 Swagger UI：

```text
http://localhost:8000/docs
```

Frontend 成员可以在 Swagger UI 中：

- 查看全部 API Path 和 HTTP Method。
- 查看 Request Body、Path Parameter 和 Query Parameter。
- 查看字段类型、Required、Enum 和长度限制。
- 填入测试数据并直接调用 Backend。
- 查看成功 Response 和 Error Response 示例。

Backend 成员修改 API 字段时，必须同时更新 Pydantic Model、OpenAPI/Swagger 和本 Markdown 文档。Frontend 应以确认后的 OpenAPI Contract 为准，不应根据页面需要自行增加未定义字段。

#### 7.0.4 字段表每一列怎么读

| 列名 | 具体含义 | 开发时怎么使用 |
|---|---|---|
| 字段 | JSON 中使用的准确 Key，大小写和下划线必须一致。 | Frontend 和 Backend 都必须使用相同名称，例如 `ticket_id`。 |
| 类型 | 允许的数据类型或引用的 DTO/Enum。 | 决定发送字符串、整数、布尔值、数组或嵌套对象。 |
| Required | JSON 中是否必须出现这个 Key。 | “是”表示必须存在；“否”表示请求时可以省略。 |
| 约束 | 长度、范围、格式、固定值或数组大小限制。 | Pydantic 用于校验，Frontend 可用于提前显示提示。 |
| 说明 | 字段在业务中的含义，而不是页面显示名称。 | 帮助成员避免对同一字段作出不同解释。 |

常见类型的实际 JSON 表现：

| Model 类型写法 | JSON 示例 | 含义 |
|---|---|---|
| `string` | `"Network problem"` | 普通文本。 |
| `integer(int64)` | `1001` | 整数 ID，不加引号。 |
| `boolean` | `true` | 布尔值，不是字符串 `"true"`。 |
| `string(date-time)` | `"2026-09-01T10:30:00Z"` | ISO 8601 时间，通常使用 UTC。 |
| `array<TicketListItem>` | `[{"ticket_id": 1001}]` | 多个相同类型对象组成的列表。 |
| `Category` | `"NETWORK"` | 必须使用 Enum 中定义的固定字符串。 |
| `AssigneeSummary | null` | `null` 或 `{...}` | 可能存在对象，也可能没有负责人。 |

#### 7.0.5 Required、Optional 和 null 的区别

- `Required = 是`：JSON 中必须有这个字段。
- `Required = 否`：调用时可以完全省略这个字段，常用于 PATCH 部分更新。
- `类型 = T | null`：字段允许没有业务值，此时返回或提交 `null`。

例如 `TicketDetail.assignee` 的类型为 `AssigneeSummary | null` 且 `Required = 是`：

```json
{
  "assignee": null
}
```

表示 Response 中必须有 `assignee` 这个 Key，但当前 Ticket 尚未分配，所以值为 `null`。

而 `TicketUpdateRequest.title` 的 `Required = 否` 表示用户只修改 Priority 时，可以完全不发送 `title`：

```json
{
  "priority": "HIGH"
}
```

Backend 不能把“字段未提交”和“字段明确提交为 null”当成同一件事。

#### 7.0.6 公共 Envelope 为什么需要统一

成功的单对象 Response 统一使用：

```json
{
  "data": {
    "ticket_id": 1001,
    "status": "ASSIGNED"
  }
}
```

分页 Response 统一使用：

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

错误 Response 统一使用：

```json
{
  "error": {
    "code": "INVALID_STATUS_TRANSITION",
    "message": "This action is not allowed in the current status",
    "details": {}
  }
}
```

统一 Envelope 后，Frontend 可以使用一个公共 API Client 处理 `data`、分页和错误，不需要为 33 个 API 分别猜测不同的返回格式。

#### 7.0.7 各成员如何使用这一节

| 成员 | 实际使用方式 |
|---|---|
| Backend A/B/C | 根据自己负责的 Model 建立 Pydantic Class；Route 声明 Request/Response Model；Service 只返回经过授权的数据。 |
| Frontend D | 根据 OpenAPI 建立 TypeScript Type/Interface；按照 Required 和 Enum 构造请求；统一解析 Envelope。 |
| 测试人员 | 测试缺少 Required 字段、错误类型、非法 Enum、长度边界、null 和额外字段等情况。 |
| API Maintainer | 审查 Model 变更是否影响其他成员；字段发生变化时先更新 Contract，再通知 Frontend。 |

一句话总结：**第 6 节规定“这个操作现在能不能做”，第 7 节规定“做这个操作时收什么 JSON、返回什么 JSON”。**

以下为所有 Request、Response、DTO 和公共 Envelope 的完整字段定义。`Required` 以 OpenAPI Schema 为准；Required Field 始终存在，当前无值或 Role 无权查看时返回 JSON `null`，不得由 Serializer 省略。

### Role

类型：`string enum`；值：`USER`、`ENGINEER_TIER1`、`ENGINEER_TIER2`、`EXTERNAL_VENDOR`、`SERVICE_DESK_MANAGER`

### Category

类型：`string enum`；值：`NETWORK`、`HARDWARE`、`SOFTWARE`、`ACCOUNT`、`OTHER`

### Priority

类型：`string enum`；值：`LOW`、`MEDIUM`、`HIGH`、`URGENT`

### TicketStatus

类型：`string enum`；值：`UNASSIGNED`、`ASSIGNED`、`IN_PROGRESS`、`PENDING_USER`、`PENDING_VENDOR`、`RESOLVED`、`REOPENED`、`CLOSED`

### SlaStatus

类型：`string enum`；值：`ON_TRACK`、`AT_RISK`、`OVERDUE`、`PAUSED`、`MET`

### PendingUserReason

类型：`string enum`；值：`INFORMATION_REQUIRED`、`RESOLUTION_CONFIRMATION`

### AttachmentVisibility

类型：`string enum`；值：`USER_VISIBLE`、`INTERNAL_ONLY`、`VENDOR_SHARED`

### CommentVisibility

类型：`string enum`；值：`USER_VISIBLE`、`INTERNAL_ONLY`

### EventScope

类型：`string enum`；值：`USER_VISIBLE`、`INTERNAL_ONLY`、`VENDOR_SCOPE`

### EventType

类型：`string enum`；值：`TICKET_CREATED`、`AUTO_ASSIGNED`、`ASSIGNED`、`REASSIGNED`、`HANDLING_STARTED`、`COMMENT_ADDED`、`SLA_CYCLE_STARTED`、`SLA_PAUSED`、`SLA_AT_RISK`、`SLA_OVERDUE`、`SLA_MET`、`USER_INFO_REQUESTED`、`USER_RESUMED`、`VENDOR_REQUESTED`、`VENDOR_RESPONDED`、`VENDOR_CANCELLED`、`RESOLUTION_SUBMITTED`、`RESOLUTION_CONFIRMED`、`AUTO_RESOLVED_NO_USER_RESPONSE`、`RESOLUTION_CONFIRMATION_TIMEOUT`、`TICKET_REOPENED`、`TICKET_CLOSED_MANUAL`、`TICKET_CLOSED_AUTO`、`ATTACHMENT_ADDED`

### VendorRequestStatus

类型：`string enum`；值：`ACTIVE`、`RESPONDED`、`CANCELLED`

### AvailableAction

类型：`string enum`；值：`EDIT`、`COMMENT`、`UPLOAD_ATTACHMENT`、`ASSIGN`、`START`、`REQUEST_USER_INFO`、`RESUME`、`ESCALATE`、`REQUEST_VENDOR`、`VENDOR_RESPONSE`、`RESOLVE`、`CONFIRM_RESOLUTION`、`REOPEN`、`CLOSE`

### ErrorCode

类型：`string enum`；值：`INVALID_REQUEST`、`VALIDATION_ERROR`、`AUTHENTICATION_REQUIRED`、`INVALID_ACCESS_TOKEN`、`EMAIL_ALREADY_REGISTERED`、`INVALID_CREDENTIALS`、`PASSWORD_POLICY_VIOLATION`、`DATA_SCOPE_DENIED`、`RESOURCE_NOT_FOUND`、`INVALID_STATUS_TRANSITION`、`ASSIGNEE_NOT_ELIGIBLE`、`USER_RESPONSE_WINDOW_EXPIRED`、`USE_RESUME_ACTION`、`USE_CONFIRM_OR_RESUME_ACTION`、`USE_VENDOR_RESPONSE_ACTION`、`ACTIVE_VENDOR_REQUEST_EXISTS`、`NO_ACTIVE_VENDOR_REQUEST`、`UPLOAD_NOT_READY`、`UPLOAD_SESSION_EXPIRED`、`TICKET_CLOSED`、`ATTACHMENT_TOO_LARGE`、`UNSUPPORTED_ATTACHMENT_TYPE`、`UPLOAD_INTEGRITY_MISMATCH`、`CLOSE_ACKNOWLEDGEMENT_REQUIRED`、`STORAGE_UNAVAILABLE`、`SERVICE_UNAVAILABLE`

### ErrorBody

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `code` | ErrorCode | 是 |  | Stable application error code. |
| `message` | string | 是 |  | Safe error message. |
| `details` | map<string, any> | 是 |  | Safe details; no secrets/stack traces. |
| `request_id` | string(uuid) | 是 |  | Correlation ID. |

### ErrorResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `error` | ErrorBody | 是 |  |  |

### PaginationMeta

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `page` | integer | 是 | min: 1 | Current page. |
| `page_size` | integer | 是 | min: 1; max: 100 | Page size. |
| `total` | integer | 是 | min: 0 | Total records. |
| `total_pages` | integer | 是 | min: 0 | Total pages. |

### ActorSummary

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `user_id` | integer(int64) | 是 |  | User ID. |
| `display_name` | string | 是 |  | Safe display name. |
| `role` | Role | 是 |  | Authenticated actor role. |

### RequesterSummary

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `user_id` | integer(int64) | 是 |  | Requester ID. |
| `display_name` | string | 是 |  | Requester display name. |

### AssigneeSummary

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `user_id` | integer(int64) | 是 |  | Engineer ID. |
| `display_name` | string | 是 |  | Engineer display name. |
| `tier` | string | 是 | enum: TIER1, TIER2 | Engineer tier. |
| `skills` | array<Category> | 是 |  | Skill categories. |
| `is_available` | boolean | 是 |  | Availability. |
| `active_load` | integer | 是 | min: 0 | Current active load. |

### VendorOrganisation

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `vendor_org_id` | integer(int64) | 是 |  | Vendor organisation ID. |
| `name` | string | 是 | minLength: 1; maxLength: 200 | Organisation name. |
| `is_active` | boolean | 是 |  | May receive new requests. |

### UserProfile

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `user_id` | integer(int64) | 是 |  | User ID. |
| `email` | string(email) | 是 |  | Login email. |
| `display_name` | string | 是 | minLength: 1; maxLength: 100 | Display name. |
| `role` | Role | 是 |  | Authenticated actor role. |
| `is_available` | boolean | null | 是 |  |  |
| `vendor_org` | VendorOrganisation | null | 是 |  |  |
| `created_at` | string(date-time) | 是 |  | Account creation time. |

### UserResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | UserProfile | 是 |  |  |

### RegisterRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `email` | string(email) | 是 | maxLength: 254 | Unique email. |
| `password` | string(password) | 是 | minLength: 8; maxLength: 128 | Password; write-only. |
| `display_name` | string | 是 | minLength: 1; maxLength: 100 | Display name. |

### LoginRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `email` | string(email) | 是 |  | Registered email. |
| `password` | string(password) | 是 | minLength: 1; maxLength: 128 | Password. |

### LoginData

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `access_token` | string | 是 |  | JWT. |
| `token_type` | string | 是 | enum: bearer | Token type. |
| `expires_in` | integer | 是 | min: 1 | Lifetime seconds. |
| `user` | UserProfile | 是 |  |  |

### LoginResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | LoginData | 是 |  |  |

### UpdateProfileRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `display_name` | string | 否 | minLength: 1; maxLength: 100 | New display name. |
| `is_available` | boolean | 否 |  | Engineer availability; forbidden for non-engineers. |

### AttachmentTypeRule

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `extension` | string | 是 |  | Lowercase extension. |
| `content_type` | string | 是 |  | Required MIME. |

### AttachmentConfig

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `max_size_bytes` | integer | 是 | const: 10485760 | Max bytes. |
| `upload_url_ttl_seconds` | integer | 是 | const: 900 | PUT TTL. |
| `download_url_ttl_seconds` | integer | 是 | const: 300 | GET TTL. |
| `allowed_types` | array<AttachmentTypeRule> | 是 |  | Allowed pairs. |

### TimerConfig

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `engineering_sla_hours` | integer | 是 | const: 48 | SLA hours. |
| `at_risk_percent` | integer | 是 | const: 80 | AT_RISK percentage. |
| `user_response_hours` | integer | 是 | const: 120 | User response hours. |
| `resolved_window_hours` | integer | 是 | const: 168 | Resolved window hours. |

### ReferenceData

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `categories` | array<Category> | 是 |  | Categories. |
| `priorities` | array<Priority> | 是 |  | Priorities. |
| `ticket_statuses` | array<TicketStatus> | 是 |  | Role-visible statuses. |
| `comment_visibilities` | array<CommentVisibility> | 是 |  | Allowed comment visibility. |
| `attachment_visibilities` | array<AttachmentVisibility> | 是 |  | Allowed attachment visibility. |
| `attachment` | AttachmentConfig | 是 |  |  |
| `timers` | TimerConfig | 是 |  |  |

### ReferenceDataResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | ReferenceData | 是 |  |  |

### AssigneeListResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | array<AssigneeSummary> | 是 |  | Engineers. |
| `meta` | PaginationMeta | 是 |  |  |

### VendorListResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | array<VendorOrganisation> | 是 |  | Vendors. |
| `meta` | PaginationMeta | 是 |  |  |

### SlaView

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `cycle_no` | integer | 是 | min: 1 | Current cycle. |
| `status` | SlaStatus | 是 |  | Engineering SLA status. |
| `started_at` | string(date-time) | null | 是 |  |  |
| `deadline` | string(date-time) | null | 是 |  |  |

### PendingUserView

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `reason` | PendingUserReason | 是 |  | Why the ticket waits for USER. |
| `deadline` | string(date-time) | 是 |  | User deadline. |

### ResolutionView

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `summary` | string | 是 | minLength: 1; maxLength: 5000 | User-visible resolution. |
| `type` | string \| null | 是 | enum: USER_CONFIRMED, AUTO_NO_USER_RESPONSE, AUTO_CONFIRMATION_TIMEOUT | PENDING_USER/RESOLUTION_CONFIRMATION 时为 null；正式 RESOLVED 后有值。 |
| `resolved_at` | string(date-time) \| null | 是 |  | PENDING_USER/RESOLUTION_CONFIRMATION 时为 null；正式 RESOLVED 时间。 |
| `auto_close_at` | string(date-time) \| null | 是 |  | PENDING_USER/RESOLUTION_CONFIRMATION 时为 null；正式 RESOLVED 后为 resolved_at + 7 days。 |

`resolution` 在 Engineer 调用 API-28 后立即返回，用于 Requester 查看待确认的 `summary`；此时三个完成字段固定为 `null`。API-29 确认或自动结果执行后，这三个字段才变为非 null。

### ClosureView

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `type` | string | 是 | enum: MANUAL_USER, AUTO_AFTER_7_DAYS | Closure type. |
| `closed_at` | string(date-time) | 是 |  | Closed time. |

### VendorRequestView

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `vendor_request_id` | integer(int64) | 是 |  | Request ID. |
| `vendor_org` | VendorOrganisation | 是 |  |  |
| `status` | VendorRequestStatus | 是 |  | Vendor request status. |
| `vendor_message` | string | 是 | maxLength: 4000 | Vendor-safe message. |
| `created_at` | string(date-time) | 是 |  | Created. |
| `responded_at` | string(date-time) | null | 是 |  |  |

### TicketSummary

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `ticket_id` | integer(int64) | 是 |  | Ticket ID. |
| `title` | string | 是 | minLength: 1; maxLength: 200 | Title. |
| `category` | Category | 是 |  | Ticket category. |
| `priority` | Priority | 是 |  | Ticket priority. |
| `status` | TicketStatus | 是 |  | Role-visible lifecycle status; USER receives IN_PROGRESS instead of internal PENDING_VENDOR. |
| `display_status` | string | 是 |  | Role-aware status. |
| `assignee` | AssigneeSummary | null | 是 |  |  |
| `sla` | SlaView | null | 是 |  |  |
| `available_actions` | array<AvailableAction> | 是 |  | Available actions. |
| `created_at` | string(date-time) | 是 |  | Created. |
| `updated_at` | string(date-time) | 是 |  | Updated. |

### TicketDetail

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `ticket_id` | integer(int64) | 是 |  | Ticket ID. |
| `title` | string | 是 | minLength: 1; maxLength: 200 | Title. |
| `description` | string | null | 是 |  |  |
| `category` | Category | 是 |  | Ticket category. |
| `priority` | Priority | 是 |  | Ticket priority. |
| `status` | TicketStatus | 是 |  | Role-visible lifecycle status; USER receives IN_PROGRESS instead of internal PENDING_VENDOR. |
| `display_status` | string | 是 |  | Role-aware status. |
| `requester` | RequesterSummary | null | 是 |  |  |
| `assignee` | AssigneeSummary | null | 是 |  |  |
| `sla` | SlaView | null | 是 |  |  |
| `pending_user` | PendingUserView | null | 是 |  |  |
| `resolution` | ResolutionView | null | 是 |  |  |
| `closure` | ClosureView | null | 是 |  |  |
| `vendor_request` | VendorRequestView | null | 是 |  |  |
| `available_actions` | array<AvailableAction> | 是 |  | Available actions. |
| `created_at` | string(date-time) | 是 |  | Created. |
| `updated_at` | string(date-time) | 是 |  | Updated. |

### TicketCreateRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `title` | string | 是 | minLength: 1; maxLength: 200 | Title. |
| `description` | string | 是 | minLength: 1; maxLength: 5000 | Description. |
| `category` | Category | 是 |  | Ticket category. |
| `priority` | Priority | 是 |  | Ticket priority. |

### TicketUpdateRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `title` | string | 否 | minLength: 1; maxLength: 200 | New title. |
| `description` | string | 否 | minLength: 1; maxLength: 5000 | New description. |
| `category` | Category | 否 |  | Ticket category. |
| `priority` | Priority | 否 |  | Ticket priority. |

### TicketDetailResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | TicketDetail | 是 |  | Role-aware unavailable fields are present with JSON null. |

### TicketListResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | array<TicketSummary> | 是 |  | Tickets. |
| `meta` | PaginationMeta | 是 |  |  |

### Comment

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `comment_id` | integer(int64) | 是 |  | Comment ID. |
| `ticket_id` | integer(int64) | 是 |  | Ticket ID. |
| `author` | ActorSummary | 是 |  |  |
| `message` | string | 是 | minLength: 1; maxLength: 4000 | Message. |
| `visibility` | CommentVisibility | 是 |  | Comment visibility. |
| `created_at` | string(date-time) | 是 |  | Created. |

### CommentCreateRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `message` | string | 是 | minLength: 1; maxLength: 4000 | Message. |
| `visibility` | CommentVisibility | 是 |  | Comment visibility. |

### CommentResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | Comment | 是 |  |  |

### CommentListResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | array<Comment> | 是 |  | Comments. |
| `meta` | PaginationMeta | 是 |  |  |

### AssignmentRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `assignee_id` | integer(int64) | 是 |  | Target engineer. |
| `reason` | string | 否 | minLength: 1; maxLength: 1000 | Reason. |

### RequestUserInfoRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `message` | string | 是 | minLength: 1; maxLength: 4000 | User-visible request. |

### ResumeRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `message` | string | 是 | minLength: 1; maxLength: 4000 | Information or issue-persists explanation. |

### EscalateRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `tier2_assignee_id` | integer(int64) | 是 |  | Tier 2 ID. |
| `reason` | string | 否 | minLength: 1; maxLength: 1000 | Reason. |

### VendorRequestCreate

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `vendor_org_id` | integer(int64) | 是 |  | Vendor organisation ID. |
| `vendor_message` | string | 是 | minLength: 1; maxLength: 4000 | Vendor-safe message. |

### VendorResponseRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `message` | string | 是 | minLength: 1; maxLength: 4000 | Vendor response. |

### ResolveRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `resolution_summary` | string | 是 | minLength: 1; maxLength: 5000 | User-visible resolution. |

### ReopenRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `reason` | string | 是 | minLength: 1; maxLength: 4000 | Why issue persists. |

### CloseRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `acknowledge` | boolean | 是 | const: true | Must be true. |
| `reason` | string | 否 | minLength: 1; maxLength: 1000 | Optional note. |

### VendorResponseView

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `vendor_response_id` | integer(int64) | 是 |  | Response ID. |
| `vendor_request_id` | integer(int64) | 是 |  | Request ID. |
| `message` | string | 是 | maxLength: 4000 | Response. |
| `created_at` | string(date-time) | 是 |  | Created. |

### VendorRequestHistoryView

包含 `VendorRequestView` 的全部字段，并增加：

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `response` | VendorResponseView \| null | 是 |  | 已回复时为持久化回复；ACTIVE/CANCELLED 或尚未回复时为 null。 |

### VendorRequestHistoryResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | array<VendorRequestHistoryView> | 是 | 不分页；按 created_at、vendor_request_id 升序 | 当前角色获授权读取的供应商历史。 |

### TicketActionData

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `action` | AvailableAction | 是 |  | Action currently available to actor. |
| `ticket` | TicketDetail | 是 |  | Role-aware unavailable fields are present with JSON null. |
| `event_id` | integer(int64) | 是 |  | Audit event ID. |
| `comment_id` | integer(int64) | null | 是 |  |  |
| `vendor_request` | VendorRequestView | null | 是 |  |  |
| `vendor_response` | VendorResponseView | null | 是 |  |  |

### TicketActionResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | TicketActionData | 是 |  |  |

### Attachment

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `attachment_id` | string(uuid) | 是 |  | Attachment UUID. |
| `ticket_id` | integer(int64) | 是 |  | Ticket ID. |
| `file_name` | string | 是 | minLength: 1; maxLength: 255 | File name. |
| `content_type` | string | 是 | enum: image/png, image/jpeg, application/pdf, text/plain | Verified MIME. |
| `size_bytes` | integer | 是 | min: 1; max: 10485760 | Verified bytes. |
| `visibility` | AttachmentVisibility | 是 |  | Attachment visibility. |
| `created_at` | string(date-time) | 是 |  | Created. |

### PresignRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `file_name` | string | 是 | minLength: 1; maxLength: 255 | Base file name. |
| `content_type` | string | 是 | enum: image/png, image/jpeg, application/pdf, text/plain | Expected MIME. |
| `size_bytes` | integer | 是 | min: 1; max: 10485760 | Expected bytes. |
| `visibility` | AttachmentVisibility | 是 |  | Attachment visibility. |

### PresignData

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `upload_id` | string(uuid) | 是 |  | Upload UUID. |
| `upload_url` | string(uri) | 是 |  | Opaque PUT URL. |
| `method` | string | 是 | enum: PUT | Method. |
| `signed_headers` | map<string, any> | 是 |  | Send unchanged to S3. |
| `expires_at` | string(date-time) | 是 |  | Expiry. |
| `max_size_bytes` | integer | 是 | const: 10485760 | Max bytes. |

### PresignResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | PresignData | 是 |  |  |

### CompleteUploadRequest

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `upload_id` | string(uuid) | 是 |  | Only accepted field. |

### AttachmentResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | Attachment | 是 |  |  |

### AttachmentListResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | array<Attachment> | 是 |  | Attachments. |
| `meta` | PaginationMeta | 是 |  |  |

### DownloadData

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `attachment_id` | string(uuid) | 是 |  | Attachment UUID. |
| `file_name` | string | 是 |  | File name. |
| `content_type` | string | 是 |  | MIME. |
| `download_url` | string(uri) | 是 |  | Opaque GET URL. |
| `expires_at` | string(date-time) | 是 |  | Expiry. |

### DownloadResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | DownloadData | 是 |  |  |

### HealthData

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `status` | string | 是 | enum: ok | State. |
| `service` | string | 是 |  | Service. |
| `version` | string | 是 |  | Git SHA/release. |
| `timestamp` | string(date-time) | 是 |  | Current UTC. |
| `checks` | object | 是 |  |  |

### HealthResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | HealthData | 是 |  |  |

### DashboardCounts

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `total_active` | integer | 是 | min: 0 | Active total. |
| `unassigned` | integer | 是 | min: 0 | UNASSIGNED. |
| `assigned` | integer | 是 | min: 0 | ASSIGNED. |
| `in_progress` | integer | 是 | min: 0 | IN_PROGRESS. |
| `pending_user` | integer | 是 | min: 0 | PENDING_USER. |
| `pending_vendor` | integer | 是 | min: 0 | PENDING_VENDOR. |
| `resolved` | integer | 是 | min: 0 | RESOLVED. |
| `reopened` | integer | 是 | min: 0 | REOPENED. |
| `closed` | integer | 是 | min: 0 | CLOSED. |

### DashboardSummaryData

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `scope` | string | 是 | enum: GLOBAL, MY_ASSIGNED | Role-derived scope. |
| `generated_at` | string(date-time) | 是 |  | Snapshot. |
| `counts` | DashboardCounts | 是 |  |  |
| `sla` | object | 是 |  |  |
| `action_required` | object | 是 |  |  |

### DashboardSummaryResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | DashboardSummaryData | 是 |  |  |

### OverdueTicket

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `ticket_id` | integer(int64) | 是 |  | Ticket ID. |
| `title` | string | 是 |  | Title. |
| `category` | Category | 是 |  | Ticket category. |
| `priority` | Priority | 是 |  | Ticket priority. |
| `status` | TicketStatus | 是 |  | Role-visible lifecycle status; USER receives IN_PROGRESS instead of internal PENDING_VENDOR. |
| `display_status` | string | 是 |  | Role-aware status. |
| `assignee` | AssigneeSummary | null | 是 |  |  |
| `sla_cycle_no` | integer | 是 | min: 1 | Cycle. |
| `sla_deadline` | string(date-time) | 是 |  | Deadline. |
| `overdue_at` | string(date-time) | 是 |  | Overdue event. |
| `is_current` | boolean | 是 |  | Still current. |

### OverdueMeta

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `page` | integer | 是 | min: 1 | Page. |
| `page_size` | integer | 是 | min: 1; max: 100 | Size. |
| `total` | integer | 是 | min: 0 | Total. |
| `total_pages` | integer | 是 | min: 0 | Pages. |
| `mode` | string | 是 | enum: current, history | Mode. |

### OverdueListResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | array<OverdueTicket> | 是 |  | Overdue items. |
| `meta` | OverdueMeta | 是 |  |  |

### TicketEvent

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `event_id` | integer(int64) | 是 |  | Event ID. |
| `ticket_id` | integer(int64) | 是 |  | Ticket ID. |
| `event_type` | EventType | 是 |  | Stable event type. |
| `scope` | EventScope | 是 |  | Audit-event scope. |
| `actor` | ActorSummary | null | 是 |  |  |
| `cycle_no` | integer | null | 是 |  |  |
| `occurred_at` | string(date-time) | 是 |  | Event time. |
| `metadata` | map<string, any> | 是 |  | Role-filtered minimal metadata. |

### EventListResponse

| 字段 | 类型 | Required | 约束 | 说明 |
|---|---|---:|---|---|
| `data` | array<TicketEvent> | 是 |  | Events. |
| `meta` | PaginationMeta | 是 |  |  |

## 8. 开发交付规则

- 每个 API Owner 在同一 PR 提交 Router、Pydantic Schema、Service、Repository、Unit/Contract Tests 和 OpenAPI Change。
- D 只依赖已合并的 OpenAPI YAML/JSON 生成 TypeScript Types 和 Mock。
- 本地验证必须确认运行中 FastAPI `/api/openapi.json` 与本合同不存在 Path/Method/Schema 漂移。
- Request/Response 或 Error Code 的任何变化需要 A/B/C/D 受影响成员 Review。
- Swagger 能调用并不代表完成；Role、404 隐藏、状态边界、事务、幂等和错误路径必须有测试。

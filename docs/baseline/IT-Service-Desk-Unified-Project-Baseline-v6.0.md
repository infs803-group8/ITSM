# IT Service Desk and Incident Ticketing System

## 统一项目开发基线

**课程**：INFS803 Cloud Computing  
**Assignment**：Option B - Cloud Web Application Development and Deployment  
**版本**：v6.0  
**日期**：2026-09-01  
**Due**：2026-10-16  
**状态**：当前统一基线

> 本文件是开发、测试、集成、部署和报告的当前基准。旧版文档仅作为历史；若旧图、旧 API 描述或聊天记录与本文冲突，以本文为准。v6.0 保留 v5.0 的业务角色、主流程、状态机、分工和 32 个 API，并修正 Database 与 Frontend Contract：所有环境统一使用完整 `service_desk` Database；`backend/database/schema.sql` 是唯一可执行 Schema Contract，SQLAlchemy Models 必须与其一致；OpenAPI v1.1 的 Required 字段始终存在，无业务值或对当前 Role 不可见时返回 `null`；32 个 API 均提供可用于 Frontend Mock 的 Example。

---

## 1. 范围与当前决定

### 1.1 Assignment 必须满足

- 使用 Client、Backend、Cloud Database 三层架构。
- Client 和 Backend 均部署到云端，并提供可公开访问的 URL。
- Marker 可绕过 Frontend 直接调用 Backend REST API。
- 至少 10 个 REST API，其中至少 3 个 POST；报告列出全部接口和 URL。
- 使用 Cloud Database；文件存储使用 Cloud Object Storage。
- 使用 Cloud Git Repository 协作，不重写 Git 历史。
- 从提交到评分完成期间，Frontend 和 Backend URL 持续可访问。
- 报告包含成员贡献、项目计划、架构、云实现、User Manual、API List、Presentation Link、Trello/Worklog Evidence 和 AI Usage Declaration。

### 1.2 技术和架构决定

| 范围 | 当前决定 |
|---|---|
| Frontend | React、TypeScript、Vite、Ant Design、React Router、Axios |
| Backend | Python、FastAPI、Uvicorn、SQLAlchemy、PyMySQL |
| Database | Database Name 统一为 `service_desk`；Feature 阶段 A/B/C 各自使用独立本地 MySQL 8.4 Instance；Final 阶段使用 Amazon RDS for MySQL 8.4 |
| Database Initialisation | `backend/database/schema.sql` 是唯一可执行 Schema Contract；本地和 RDS 空库执行同一文件创建完整 19 张表；SQLAlchemy Models 必须逐字段匹配；本地执行 Schema Drift Verification |
| File Storage | Private Amazon S3；Browser 使用 Presigned PUT，Backend 使用 `HeadObject` 验证 |
| Compute | Amazon ECS on AWS Fargate；Frontend、Backend 使用独立 ECS Services |
| Public Entry | CloudFront 默认 HTTPS Domain → Internet-facing ALB；`/api/*` 转 Backend，其余路径转 Frontend |
| Background Jobs | EventBridge Scheduler 启动短期 ECS Tasks；SLA Job 与 Attachment Cleanup Job 分开运行 |
| Registry / Logs | Amazon ECR、CloudWatch Logs |
| Secrets / AWS Auth | AWS Secrets Manager 保存 DB/JWT Secret；手动部署使用本地配置的授权 AWS 身份，凭证不进入 Git |
| Deployment | 手动部署；部署配置、Task Definition 和 Runbook 进入 Git |
| Infrastructure as Code | Terraform；`dev-storage` 只创建开发 S3，`final` 创建最终 AWS Infrastructure |
| Repository | GitHub Monorepo；3 人 Backend、1 人 Frontend |
| Project Manager | 成员 C；负责协调与证据检查，不代替各 Owner 更新任务或完成测试 |

### 1.2.1 当前合同文件和优先级

| 范围 | 唯一当前文件 | 决定内容 |
|---|---|---|
| 业务流程、角色、分工、里程碑、部署 | `IT-Service-Desk-Unified-Project-Baseline-v6.0.md` | 项目总基线。 |
| HTTP API | `IT-Service-Desk-Final-API-Specification-v1.1.md` + `IT-Service-Desk-OpenAPI-v1.1.yaml` | Path、Method、Auth、Request、Response、Error、Example；机器读取以 OpenAPI 为准。 |
| Database 字段解释 | `IT-Service-Desk-Database-Final-Design-v1.1.md` | 19 张表的业务含义、关系和字段说明。 |
| Database 可执行结构 | `backend/database/schema.sql`，内容冻结自 `IT-Service-Desk-MySQL-Schema-v1.0.sql` | 唯一可执行 Schema Contract；本地和 RDS 使用同一文件。 |

同一范围出现冲突时以上表为准；不得用旧版 v5.0、聊天记录、个人 SQL Dump 或 Frontend 临时字段覆盖当前合同。

### 1.3 MVP 常量

| 项目 | 值 |
|---|---|
| Categories | NETWORK、HARDWARE、SOFTWARE、ACCOUNT、OTHER |
| Priorities | LOW、MEDIUM、HIGH、URGENT |
| Engineering SLA | 所有 Priority 暂用 48 个连续小时；80% 即 38h24m 为 AT_RISK |
| User Response Window | 5 个自然日（连续 120 小时） |
| RESOLVED Window | 7 个自然日；到期自动 CLOSED |
| Attachment Limit | 单文件 10 MB；PNG、JPG、PDF、TXT、LOG |
| Upload URL TTL | 15 分钟 |
| Time Format | UTC ISO 8601 |
| Notifications | Dashboard/List 标黄或标红；MVP 不实现 Email、SMS、SNS 或 Push |

---

## 2. 角色与数据可见性

### 2.1 角色

| Role | 主要权限 |
|---|---|
| USER | 管理自己的 Ticket；留言、上传、补充信息、确认方案；在 RESOLVED 窗口内 Reopen 或手工 Close |
| ENGINEER_TIER1 | 处理分配给自己的 Ticket；请求信息、提交方案、升级 Tier 2 |
| ENGINEER_TIER2 | 处理 Tier 2 Ticket；与 Vendor 协作；始终负责向 User 提交最终方案 |
| EXTERNAL_VENDOR | 只访问本 Organisation 的 Vendor Scope；Active Request 时回复和上传 `VENDOR_SHARED` |
| SERVICE_DESK_MANAGER | 查看全局 Dashboard；按规则处理 UNASSIGNED、OVERDUE 和 Reassign |

Public Register 只能创建 USER。Tier 1、Tier 2、Vendor 和 Manager 由受控 Seed/管理流程创建。Frontend 隐藏按钮只是体验优化；Backend 必须验证 Role、资源范围、当前状态和 `available_actions`。

### 2.2 Role × Data Visibility

| Role | Ticket / User Data | Comments | Attachments | SLA / Assignee | Vendor / Events |
|---|---|---|---|---|---|
| User | 自己 Ticket 的 User-facing Schema、当前 `resolution_summary`；仅自己的 Profile | 仅 USER_VISIBLE | 仅 USER_VISIBLE | 当前 User-facing SLA、Deadline、Assignee 显示名 | 仅 USER_VISIBLE Events；完全隐藏 Vendor 数据和 PENDING_VENDOR |
| Tier 1 | 当前分配 Ticket；有限 User 联系信息 | USER_VISIBLE、INTERNAL_ONLY | USER_VISIBLE、INTERNAL_ONLY | 当前及历史 | Internal Timeline，但排除 Vendor Payload |
| Tier 2 | 当前分配 Ticket；有限 User 联系信息 | USER_VISIBLE、INTERNAL_ONLY | 全部三类 | 当前及历史 | 完整授权范围内的 Timeline 和 Vendor Data |
| Vendor | `ticket_id`、title、category、priority、本 Organisation 的 `vendor_message`；无 User Personal Data/description | 无普通 Comment 权限 | 仅本 Organisation 的 VENDOR_SHARED | 不可见 | 仅本 Organisation 的 Active/Historical Vendor Thread 和 VENDOR_SCOPE Events |
| Manager | 全部 Internal Data | 全部 | 全部 | 全部 | 完整 Audit Timeline |

关键规则：

- PENDING_VENDOR 是 Tier 2/Manager 可见的 Ticket 内部状态。User 看到 `display_status=IN_PROGRESS` 和 “Tier 2 Engineer is working”；Vendor 只看到自己 VendorRequest 的 ACTIVE/RESPONDED/CANCELLED 和 `available_actions`。
- Vendor Scope 以 `VendorRequest.vendor_org_id = JWT vendor_org_id` 为授权依据。历史 Request 允许继续读取本 Organisation 的 Thread、Events 和 VENDOR_SHARED，但不允许读取后续内部处理或其他 Vendor 数据。
- Vendor 只有在本 Organisation 存在唯一 Active VendorRequest 时才能调用 API-27、上传 VENDOR_SHARED，或取得 VENDOR_RESPONSE Action。
- API-26 的 `vendor_message` 由 Tier 2 单独填写。Frontend 提醒不要包含 User 姓名、邮箱、User ID；Backend 不得自动复制 Ticket description、Profile、Comments、Resolution 或 Event Payload。MVP 不承诺自动检测 Tier 2 手工输入的敏感文本。
- Comment visibility 为 USER_VISIBLE 或 INTERNAL_ONLY。API-23 的信息请求、API-24 的 User 回复和 API-28 的 `resolution_summary` 均为 USER_VISIBLE；普通 Comment 不触发 Resume、Confirm Resolution 或 Vendor Response。PENDING_USER 中 User 调用 API-20 必须转向 API-24/API-29；PENDING_VENDOR 中 Vendor 调用 API-20 必须转向 API-27；其他获授权的普通留言只写 Comment/Event，不改变状态或 Timer。
- Attachment visibility 为 USER_VISIBLE、INTERNAL_ONLY 或 VENDOR_SHARED。VENDOR_SHARED 必须由 Backend 绑定当前 Active `vendor_request_id` 和 `vendor_org_id`。
- TicketEvent scope 为 USER_VISIBLE、INTERNAL_ONLY 或 VENDOR_SCOPE。`COMMENT_ADDED` 继承对应 Comment 的 visibility 并只保存 `comment_id`；List 直接过滤无权数据；按 ID 请求隐藏资源统一返回 404 `RESOURCE_NOT_FOUND`。
- 任何 Response 均不得返回 Password Hash、JWT、Reset Token、MFA Secret、AWS Credential 或 Database Credential。

---

## 3. 核心数据模型

### 3.1 业务对象

| Object | Owner | 关键字段 / 约束 |
|---|---|---|
| User | B | role、is_available、skills、vendor_org_id、last_assigned_at |
| Ticket | B | user_id、title、description、category、priority、status、assignee_id；`sla_cycle_no/status/started_at/deadline`；`pending_user_reason/deadline`；`resolution_summary/type/resolved_at/auto_close_at`；`closure_type/closed_at` |
| Comment | B | ticket_id、author_id、message、visibility；正式 Workflow Comment 由 C 的 Service 通过 B 的 Repository 创建 |
| AttachmentUpload | A | `upload_id`、ticket_id、creator_id、object_key、原始文件属性、visibility、Vendor Binding、status、expires_at |
| Attachment | A | attachment_id、`upload_id` unique、ticket_id、object_key、verified_size/content_type、visibility、Vendor Binding |
| VendorRequest / VendorResponse | C | 每 Ticket 同时最多一个 ACTIVE；Request 绑定 vendor_org_id 和 `vendor_message` |
| TicketEvent | C | Append-only；event_type、actor、scope、cycle、必要 Metadata；不复制完整 Comment |
| AssignmentControl | C | Singleton Row；串行化 Initial Auto Assignment 的短暂候选选择 |

Ticket 当前工作流字段保留在 Ticket 表，由 B 维护 Model 文件、C 定义语义。A/B/C 分别维护自己 Domain 的 SQLAlchemy Model，B 维护 `model_registry.py` 并协调跨域外键和完整 Schema Review。Feature 阶段的结构变化必须先修改 Model，再删除并重建各自本地空库验证；不得只在 MySQL Workbench 手工改表。Schema Freeze 后如必须变更 Final RDS，使用独立、经 Review 的 SQL Patch，并在 Runbook 记录执行结果。

### 3.2 AttachmentUpload：附件上传缺失对象

`AttachmentUpload` 是 Presign 与 Attachment 之间的持久化 Upload Session。没有它，API-03 无法可信地证明 object_key、文件属性、Visibility、Vendor Binding 和上传者确实来自 API-02。

最低字段：

| Field | 规则 |
|---|---|
| upload_id | UUID；Client 后续 Complete 的唯一标识 |
| ticket_id / creator_id | 固定绑定 Ticket 和 Presign 发起人 |
| object_key | Backend 生成且 Unique，例如 `{environment}/pending/{ticket_id}/{upload_id}` |
| file_name | 仅用于显示；API-03 不接受覆盖 |
| expected_content_type / expected_size | API-02 校验后保存；API-03 与 S3 HeadObject 比较 |
| visibility | API-02 按 Role 固定保存 |
| vendor_request_id / vendor_org_id | 仅 VENDOR_SHARED；Backend 从当前 Active Request 绑定 |
| status | PENDING、COMPLETED、EXPIRED、ABORTED |
| expires_at / completed_at | URL 有效期和完成时间 |
| attachment_id | COMPLETED 后关联最终 Attachment；Unique |

上传流程：

1. API-02 锁定并重新读取 Ticket，拒绝 CLOSED，校验 Role、file type/size、Visibility 和 Active VendorRequest。
2. Backend 创建 `AttachmentUpload(status=PENDING)`，生成不可预测 object_key，再返回 `upload_id`、Presigned PUT URL、必须携带的 signed headers 和 `expires_at`。Frontend 不提交 object_key 或 Vendor Binding。
3. Browser 直接 PUT 到 Private S3；S3 Object 不因上传成功自动成为 Attachment。
4. Browser 调用 API-03，只提交 `upload_id`。Backend 先读取 Session 并执行 S3 `HeadObject`，随后在事务中按统一顺序锁定 Ticket、再锁定 AttachmentUpload，并重新验证状态、Owner、Deadline、Ticket Status 和 Vendor Binding。
5. actual size/content type 与 Session 不匹配时，标记 ABORTED 并返回 `UPLOAD_INTEGRITY_MISMATCH`；Object 不存在返回 `UPLOAD_NOT_READY`；Session 过期返回 `UPLOAD_SESSION_EXPIRED`。
6. 校验成功时，Backend 只使用 Session 和 HeadObject 的值创建 Attachment，设置 Session=COMPLETED、写 `ATTACHMENT_ADDED` Event，并在同一事务提交。`Attachment.upload_id` Unique 防止重复登记。
7. 对已 COMPLETED 的同一 upload_id 重复调用 API-03 时，幂等返回原 Attachment，不新增 Metadata 或 Event。其他用户请求该 upload_id 返回 404。
8. Presign 后 Ticket 若进入 CLOSED，API-03 将 Session 标记 ABORTED 并返回 `TICKET_CLOSED`；不得创建 Attachment/Event。ABORTED 是技术清理状态，不是对 CLOSED Ticket 的业务写入。
9. `attachment_cleanup` 每 30 分钟由 EventBridge Scheduler 启动 ECS Task：把过期 PENDING 标为 EXPIRED，并删除 EXPIRED/ABORTED Session 对应的孤立 S3 Object。COMPLETED Object 绝不由该任务删除。

最低验收：合法上传只生成一个 Attachment；篡改 file_name/visibility/vendor binding 无效；重复 Complete 幂等；过期、超大、类型不匹配、他人 upload_id、Presign 后 Close 和 Cleanup Race 均有测试。

---

## 4. Workflow、SLA 与并发

### 4.1 生命周期状态

| Status | 含义 |
|---|---|
| NEW | 仅在 API-15 创建事务内瞬时存在；提交前必须转 ASSIGNED 或 UNASSIGNED |
| UNASSIGNED | 无合格自动分配候选人 |
| ASSIGNED | 已分配、尚未 Start |
| IN_PROGRESS | 工程师处理中 |
| PENDING_USER | 等待 User；由 `pending_user_reason` 区分两类流程 |
| PENDING_VENDOR | Tier 2 与 Vendor 的内部协作；User 仍看到 IN_PROGRESS |
| RESOLVED | 方案已确认或 User 5 天未回复；保留 7 天 Reopen/Manual Close Window |
| REOPENED | User 在 RESOLVED 窗口内重开；立即启动新 Engineering SLA Cycle |
| CLOSED | 终态；所有业务写操作只读拒绝 |

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

### 4.2 Engineering SLA 和 User Timers

- 每个 Engineering SLA Cycle 为 48 连续小时。UNASSIGNED、ASSIGNED、IN_PROGRESS、PENDING_VENDOR、REOPENED 继续当前 Cycle。
- Tier 1→Tier 2、Manager Reassign、Vendor Request/Response 均不重置 Cycle。
- 80% 时写 AT_RISK Event 并标黄；48 小时时写 OVERDUE Event 并标红。AT_RISK/OVERDUE 是 SLA 状态，不是生命周期状态。
- Request User Info：进入 PENDING_USER + INFORMATION_REQUIRED，当前 Cycle 结束为 PAUSED，启动 120h User Timer。期限内 Resume 启动新 48h Cycle；超时为 `AUTO_NO_USER_RESPONSE` 并进入 RESOLVED。
- Submit Resolution：进入 PENDING_USER + RESOLUTION_CONFIRMATION，按提交时刻固化 Cycle=MET/OVERDUE，启动 120h Timer。User Confirm 进入 RESOLVED；Issue Persists 通过 API-24 回 IN_PROGRESS 并启动新 Cycle；超时为 `AUTO_CONFIRMATION_TIMEOUT`。
- 每次进入 RESOLVED 设置 `auto_close_at=resolved_at+7 days`。User 可在边界前 Reopen 或确认不可逆后 Manual Close；到期由 System Auto Close。
- `AUTO_NO_USER_RESPONSE` 写入 User-visible 系统说明“因 5 天未收到补充而自动解决”；`AUTO_CONFIRMATION_TIMEOUT` 保留工程师原 `resolution_summary`，并补充自动确认原因。
- 边界统一为 `now < deadline` 才允许用户动作；`now >= deadline` 执行自动结果。API-24/API-29 与 SLA Job 复用同一 Deadline Enforcement。
- 历史 Cycle、Resolution 和 Closure 只追加到 TicketEvent；新 Cycle 不覆盖历史。

### 4.3 主要转换

| Current / Condition | Action | Result | Actor |
|---|---|---|---|
| UNASSIGNED | Assign | ASSIGNED | Manager |
| ASSIGNED / REOPENED with assignee | Start | IN_PROGRESS | Assignee |
| IN_PROGRESS Tier 1 | Escalate | ASSIGNED to selected Tier 2；保留 Cycle | Tier 1 |
| IN_PROGRESS | Request User Info | PENDING_USER/INFORMATION_REQUIRED；PAUSED | Assignee |
| PENDING_USER before deadline | Resume / Issue Persists | IN_PROGRESS；新 Cycle | User |
| PENDING_USER at/after deadline | Auto Resolve | RESOLVED；设置 auto_close_at | System/lazy enforcement |
| IN_PROGRESS Tier 2, no Active Request | Request Vendor | PENDING_VENDOR；创建唯一 ACTIVE Request | Tier 2 |
| PENDING_VENDOR + matching Active Request | Vendor Response | IN_PROGRESS；Request=RESPONDED | Vendor |
| IN_PROGRESS | Submit Resolution | PENDING_USER/RESOLUTION_CONFIRMATION | Assignee |
| PENDING_VENDOR | Submit Resolution | Active Request=CANCELLED；PENDING_USER/RESOLUTION_CONFIRMATION | Tier 2 |
| RESOLUTION_CONFIRMATION before deadline | Confirm | RESOLVED | User |
| RESOLVED before auto_close_at | Reopen | REOPENED；新 Cycle；优先原 Assignee | User |
| RESOLVED before auto_close_at | Manual Close | CLOSED；MANUAL_USER | User |
| RESOLVED at/after auto_close_at | Auto Close | CLOSED；AUTO_AFTER_7_DAYS | System |

### 4.4 Initial Auto Assignment

API-15 只考虑 `is_available=true` 且 skill 匹配 category 的 Tier 1。`active_load` 只统计该工程师处于 ASSIGNED、IN_PROGRESS、PENDING_VENDOR 或 REOPENED 的 Ticket；按 `active_load ASC`、`last_assigned_at ASC`（NULL 最先）、`user_id ASC` 稳定选择。无候选时 Ticket=UNASSIGNED。

创建事务先锁定唯一 `AssignmentControl` Row，再计算候选、更新 Ticket/`last_assigned_at` 并写 Assignment Event；因此并发创建会串行看见上一次结果，不会同时偏向同一个“最少工作量”工程师。此锁只保护短暂选择过程，不包围外部调用。

### 4.5 API-21 Assign/Reassign Matrix

| Current State | Preconditions | Target | Result / Preserved Data |
|---|---|---|---|
| UNASSIGNED, not OVERDUE | assignee null | Tier 1 or Tier 2 | ASSIGNED；保留创建时 Cycle |
| UNASSIGNED, OVERDUE | assignee null | Tier 2 | ASSIGNED；保留 Deadline/OVERDUE |
| ASSIGNED/IN_PROGRESS, OVERDUE | new assignee differs | Tier 2 | ASSIGNED；保留 Deadline/OVERDUE |
| PENDING_USER | 有有效 Reason/Deadline | 当前 Tier 1 可 T1/T2；当前 Tier 2 只可 T2 | 保持 PENDING_USER 和 Timer |
| PENDING_VENDOR, OVERDUE | 唯一 Active Request | Tier 2 | 保持 PENDING_VENDOR、Request、Vendor、Deadline |
| REOPENED | assignee null，原 Assignee 不可用 | Tier 1 or Tier 2 | ASSIGNED；保留 Reopen Cycle |

其他组合返回 409 `INVALID_STATUS_TRANSITION`；CLOSED 返回 `TICKET_CLOSED`。目标工程师必须可用且资格匹配。Manager 不能在任意状态随意更改 Assignee。

### 4.6 Vendor、Resolution、Reopen 和 CLOSED

- 每 Ticket 同时最多一个 ACTIVE VendorRequest；Database Unique Guard 必须保证并发 API-26 只有一个成功。
- API-27 不接受 `vendor_request_id`，只处理当前唯一 Active Request。Tier 2 可不等待 Vendor，直接 API-28；此时 Active Request 原子变为 CANCELLED。
- Vendor 历史读取按 Organisation 保留，但只有 Active Request 产生回复和上传权限。
- Reopen 优先使用最近一次 RESOLVED 时的 Assignee（可能 Tier 1 或 Tier 2）。若已禁用/不可用，则 `assignee_id=null`，等待 Manager API-21；不得默认 Tier 1。
- CLOSED 是整个 Ticket Resource 的业务只读终态：禁止 Ticket Edit、Comment、Presign/Complete、Assign/Reassign、Workflow 和重复 Close；读取已有授权数据仍允许。
- 普通 Comment 不可替代 API-24/API-27/API-29。PENDING_USER 的 User、PENDING_VENDOR 的 Vendor 调用 API-20 时返回对应 Action Guidance Error，不写 Comment/Event；其他有权角色的普通 Comment 不改变 Workflow。
- API-24/API-29 在 120h 边界先执行 Auto Resolve，再返回 `USER_RESPONSE_WINDOW_EXPIRED`；API-30/API-31 在 7d 边界先执行 Auto Close，再返回 `TICKET_CLOSED`。Scheduled Job 与这些 lazy checks 调用同一 Deadline Service。

### 4.7 事务、并发与审计

Workflow 写操作、SLA Job、API-18/API-20、Attachment Presign/Complete 均在写入前重新读取并验证。Workflow 的统一顺序：

1. 开启事务并 `SELECT ... FOR UPDATE` 锁定 Ticket；需要时再锁定 VendorRequest/AttachmentUpload。
2. 按最新状态重新验证 Role、Assignee、Reason、Deadline、Vendor Organisation 和 Action。
3. 更新 Ticket 和相关业务对象。
4. 同一事务追加 TicketEvent；Event 失败则整体回滚。
5. Commit 后返回成功。失败请求不写失败 Event。

Row Lock 只保证串行与重新验证，不保证“只有第一个请求能成功”。后到动作若在最新状态仍合法，可以成功；否则返回 409。Auto Resolve、Auto Close、Vendor Response、Reopen 和 Manual Close 均须幂等或由唯一约束保护。

必须审计：Create/Auto Assignment、Assign/Reassign、Start、Comment Added、Cycle Start/PAUSED/AT_RISK/OVERDUE/MET、User Info Request/Resume、Vendor Request/Response/Cancel、Resolution Submit/Confirm/Timeout、Reopen、Manual/Auto Close、Attachment Added。TicketEvent 只追加，不提供修改/删除 API；Cycle Event 使用 `(ticket_id, cycle_no, event_type)` Unique Guard，保证 Job 重跑不重复写 AT_RISK/OVERDUE。

---

## 5. Backend API 合同

### 5.1 通用约定与错误

| 项目 | 约定 |
|---|---|
| Local Base URL | `http://localhost:8000/api/v1` |
| Final Base URL | `https://<cloudfront-domain>/api/v1` |
| Swagger / OpenAPI | `/api/docs`、`/api/openapi.json` |
| Authentication | `Authorization: Bearer <access_token>` |
| Pagination | page 从 1；page_size 默认 20、最大 100 |
| Success | `{ "data": ... }`；List 另含 `meta` |
| Error | `{ "error": { "code", "message", "details", "request_id" } }` |
| Required/Null | OpenAPI `required` 中的 Response Field 必须始终存在；当前无值或当前 Role 不可见时返回 JSON `null`，不得在不同请求中随机省略 |
| Frontend Mock | OpenAPI v1.1 每个 Operation 至少包含一个成功 Example；Frontend Mock 和 TypeScript Types 只从已合并 Contract 生成 |
| Local CORS | Backend 允许配置中的本地 Frontend Origin，默认 `http://localhost:5173`；Final 通过 CloudFront 同 Origin `/api/*` 访问 |

| HTTP / Code | 语义 |
|---|---|
| 403 DATA_SCOPE_DENIED | 角色无权使用该数据类别/Endpoint |
| 404 RESOURCE_NOT_FOUND | 不存在或不可见；不得区分 |
| 409 INVALID_STATUS_TRANSITION | 最新状态不允许动作 |
| 409 USER_RESPONSE_WINDOW_EXPIRED | 已执行/已存在 Auto Resolve；Frontend 刷新为 RESOLVED |
| 409 USE_RESUME_ACTION / USE_CONFIRM_OR_RESUME_ACTION / USE_VENDOR_RESPONSE_ACTION | 普通 Comment 被正式 Workflow Action 拦截 |
| 409 ACTIVE_VENDOR_REQUEST_EXISTS / NO_ACTIVE_VENDOR_REQUEST | VendorRequest 冲突 |
| 409 UPLOAD_NOT_READY / UPLOAD_SESSION_EXPIRED | S3 Object 尚未可验证或 Upload Session 过期 |
| 409 TICKET_CLOSED | CLOSED 或 lazy Auto Close 后拒绝业务写操作 |
| 413 ATTACHMENT_TOO_LARGE | 超过 10 MB |
| 422 UNSUPPORTED_ATTACHMENT_TYPE / UPLOAD_INTEGRITY_MISMATCH | 文件类型或实际属性不匹配 |
| 422 CLOSE_ACKNOWLEDGEMENT_REQUIRED | Manual Close 缺少不可逆确认 |

### 5.2 按功能模块排序的 API 清单与 Owner

编号不表示调用先后；按 Domain Owner 和功能模块排列，减少跨成员交叉：A 为 API-01–07，B 为 API-08–20，C 为 API-21–32。

| ID | Module | Method / Endpoint | Access | 核心规则 | Owner |
|---:|---|---|---|---|---|
| 01 | System | GET `/health` | Public | Health/version/database | A |
| 02 | Attachment | POST `/tickets/{id}/attachments/presign` | Scoped Role | 创建 PENDING AttachmentUpload；返回 upload_id 和 URL | A |
| 03 | Attachment | POST `/tickets/{id}/attachments/complete` | Presign Creator | Body 仅 upload_id；HeadObject 校验；幂等创建 Attachment | A |
| 04 | Attachment | GET `/tickets/{id}/attachments` | Scoped Role | Visibility/Organisation Filter | A |
| 05 | Attachment | GET `/tickets/{id}/attachments/{attachment_id}/download` | Scoped Role | 短期 Presigned GET；隐藏资源 404 | A |
| 06 | Dashboard | GET `/dashboard/summary` | T1/T2/Manager | Counts、AT_RISK/OVERDUE、reopened_unassigned | A |
| 07 | Dashboard | GET `/dashboard/overdue-tickets` | T1/T2/Manager | current/history；History 来自 TicketEvent | A |
| 08 | Auth | POST `/auth/register` | Public | 只能创建 USER | B |
| 09 | Auth | POST `/auth/login` | Public | JWT Login | B |
| 10 | User Profile | GET `/users/me` | Login | 不返回内部调度字段 | B |
| 11 | User Profile | PATCH `/users/me` | Login | 仅允许 Profile；工程师可改 availability | B |
| 12 | Reference & Directory | GET `/reference-data` | Login | Role-aware Status、SLA/Timer、附件限制 | B |
| 13 | Reference & Directory | GET `/users/assignees` | T1/T2/Manager | Tier/skill/availability filters | B |
| 14 | Reference & Directory | GET `/vendors` | T2/Manager | Vendor Organisations | B |
| 15 | Ticket Core | POST `/tickets` | User | 创建、启动 Cycle、调用 C 的 Initial Assignment；提交后只为 ASSIGNED/UNASSIGNED | B |
| 16 | Ticket Core | GET `/tickets` | Login | Role-aware List/Filters；Vendor 用 VendorRequest history 建 Scope | B |
| 17 | Ticket Core | GET `/tickets/{id}` | Scoped Role | Role-aware Detail、display_status、available_actions | B |
| 18 | Ticket Core | PATCH `/tickets/{id}` | User/Manager | User 仅自己的 UNASSIGNED；Manager 仅非 CLOSED | B |
| 19 | Comment | GET `/tickets/{id}/comments` | User/T1/T2/Manager | Visibility Filter；Vendor 拒绝 | B |
| 20 | Comment | POST `/tickets/{id}/comments` | Scoped Role | 普通 Comment；等待状态中的正式回复 Actor 返回 Action Guidance | B |
| 21 | Assignment & Handling | POST `/tickets/{id}/assign` | Manager | 严格使用第 4.5 节 Matrix | C |
| 22 | Assignment & Handling | POST `/tickets/{id}/start` | Assignee | ASSIGNED/REOPENED → IN_PROGRESS | C |
| 23 | User Interaction | POST `/tickets/{id}/request-user-info` | Assignee | USER_VISIBLE request；PENDING_USER/INFORMATION_REQUIRED | C |
| 24 | User Interaction | POST `/tickets/{id}/resume` | User | 正式补充/Issue Persists；Deadline Enforcement | C |
| 25 | Escalation | POST `/tickets/{id}/escalate` | Tier 1 | 指定 Tier 2；保留 Cycle | C |
| 26 | Vendor | POST `/tickets/{id}/vendor-requests` | Tier 2 | vendor_org_id + vendor_message；唯一 Active | C |
| 27 | Vendor | POST `/tickets/{id}/vendor-response` | Matching Vendor | 不传 vendor_request_id；Active → RESPONDED | C |
| 28 | Resolution & Closure | POST `/tickets/{id}/resolve` | Assignee | User-visible Resolution；进入确认阶段 | C |
| 29 | Resolution & Closure | POST `/tickets/{id}/confirm-resolution` | User | 确认方案；Deadline Enforcement | C |
| 30 | Resolution & Closure | POST `/tickets/{id}/reopen` | User | RESOLVED 窗口内；原 Assignee 优先；新 Cycle | C |
| 31 | Resolution & Closure | POST `/tickets/{id}/close` | User | RESOLVED 窗口内，必须 acknowledge；终态 CLOSED | C |
| 32 | Audit | GET `/tickets/{id}/events` | Scoped Role | Role/Scope-aware Timeline | C |

公开 API 共 32 个：A=7、B=13、C=12。Background Jobs、RBAC、Serializer 和 Assignment Service 是内部组件，不新增公共 API。

每个 API Owner 必须在同一 PR 提交 Router/Service/Repository、Schema、Unit/Contract Tests 和 OpenAPI Change；D 只依赖已合并的 OpenAPI Contract。

---

## 6. Cloud、开发与部署

### 6.1 最终 AWS 架构

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
    MANUAL[Manual deployment] --> ECR[ECR]
    ECR --> FE
    ECR --> BE
    FE --> CW[CloudWatch Logs]
    BE --> CW
    SLA --> CW
    CLEAN --> CW
~~~

- CloudFront 使用默认 `*.cloudfront.net` Certificate，为 Viewer 提供 HTTPS；`/api/*` 禁止缓存。无自有 Domain 的 MVP 使用 CloudFront→ALB HTTP Origin，并以 CloudFront origin-facing Prefix List + Origin Verify Header 限制绕过；若取得有效 ACM Domain Certificate，再切为 HTTPS Origin。ALB 不作为报告中的最终公开 URL。
- Backend/Frontend ECS Services 可独立部署，初始 `desiredCount=1`。Background Jobs 不在 Web Process 内运行，避免扩容或重启时重复执行。
- `sla_monitor` 每 5 分钟检查 AT_RISK、OVERDUE、Pending User Deadline 和 Auto Close；`attachment_cleanup` 每 30 分钟处理过期 Upload Session 和 Orphan Object。两者均可安全重跑。
- RDS 最终为 Private，只允许 Backend/Scheduled Task Security Groups。S3 Block Public Access、默认加密和 CORS Allowlist 保持开启。
- 为降低 MVP 成本，ALB 和 ECS Tasks 使用 Public Subnets；ECS 可有 Public IP 供出站访问 AWS Services，但 Security Group 只接受 ALB SG 的应用端口，Scheduled Tasks 不开放入站。RDS 位于 Private DB Subnets 且不分配 Public IP。
- ECS Task Role 只访问所需 S3 Prefix、Logs 和 Secrets；使用授权 AWS 身份手动部署，Frontend/Browser 不持有 AWS Access Key。Presigned URL 只允许单个 object_key 和短 TTL。

### 6.2 本地开发与开发期 AWS 边界

- A、B、C 各自在本机运行独立 MySQL 8.4 Instance，Database 名称统一为 `service_desk`、字符集 `utf8mb4`、时区 UTC；三人的 Instance/Port/Credential 相互隔离，不得让 Feature Branch 共享同一个 Database Schema。
- 每人拉取 `main` 后，在自己的空 MySQL Instance 执行同一份 `backend/database/schema.sql`，一次创建完整 19 张表、Reference Data、Foreign Key、Unique/CHECK Constraint 和 Audit Trigger；任何成员不得只创建自己负责的表。
- `backend/database/schema.sql` 是唯一可执行 Schema Contract；`IT-Service-Desk-Database-Final-Design-v1.1.md` 是字段解释；SQLAlchemy Models 是 Application Mapping，必须与 SQL Contract 完全一致，不得独立新增、删除或改变 Column。
- `python -m app.db.bootstrap` 只负责确认目标为空、执行已版本化的 Canonical SQL、记录 Schema Version 并运行 Verification；不得再使用 `Base.metadata.create_all()` 生成另一套结构。
- 开发数据不作为长期资产。需要验证 Schema Change 时，在自己的空本地 Instance 重新执行完整 SQL；不得把 A/B/C 的个人 SQL Dump 拼接为 Final Schema。
- Feature 阶段不创建或持续运行 AWS RDS、ECS、ALB、CloudFront、EventBridge Scheduler、CloudWatch Application Logs 或 Secrets Manager。
- 开发期 AWS 只保留一个 Private S3 Bucket，使用 `development/` Prefix、Block Public Access、默认加密、短期 Presigned URL 和最小权限。A 负责真实 S3 Integration Test；普通 Unit Test 使用 Mock/Stub，避免互相污染和不必要请求费用。
- D 使用 OpenAPI v1.1 和确认后的 Examples 生成 TypeScript Types/Mock 开发，再连接 A/B/C 各自本地 Backend URL 联调；D 不连接 MySQL/S3，也不持有 Database 或 AWS Credential。
- 合并后的 Backend Integration Test 先在指定成员的全新本地 MySQL 空库执行；只测试 `main`，不得用共享环境运行未合并 Feature Branch。
- Canonical SQL 写入非敏感 Role、Category、Priority、Status、Timer、Attachment Type 和 Singleton Control Row；`seed.py` 必须幂等验证/补齐相同 Reference Data；`seed_demo.py` 只用于本地测试账号，禁止在 Final RDS 执行。任何 Seed 不得包含真实个人资料或 Secret。

### 6.3 Final Database Bootstrap、发布顺序与回滚

1. M4 完成 Schema Freeze；本地验证在全新 MySQL 8.4 空库实际执行 `backend/database/schema.sql`，验证 19 张表、35 个 Foreign Key、关键 Unique/CHECK、两个 Audit Trigger、Reference Data、SQLAlchemy Mapping、API Tests 和 Docker Build，并生成 immutable Backend/Frontend Image Tag（commit SHA）。
2. A 创建 Final AWS Infrastructure，包括 Empty Private RDS、Final Private S3、ECR、ECS、ALB、CloudFront、Secrets、Logs 和 Scheduler；RDS Database Name 同样使用 `service_desk`。
3. A 使用相同 Backend Image 启动一次性 Database Bootstrap ECS Task，执行 `python -m app.db.bootstrap`，由该 Task 对 Empty RDS 应用同一份 Canonical SQL；随后执行幂等 `python -m app.db.seed` 验证 Reference Data。B 核对 Task Log、Schema Version、表、索引、外键、CHECK、Trigger 和 Schema Drift 结果。禁止在每个 Backend Web Container 启动时自动建表。
4. A 部署 Backend Task Definition，等待 Health Check，通过 Direct API Smoke Tests。
5. A/D 部署 Frontend Task Definition 并按需执行 CloudFront Invalidation。
6. C 验证 SLA Scheduled Task，A 验证 Attachment Cleanup Task；D 运行 Playwright Critical Path。
7. 所有 Gate 通过后，B 使用 `mysqldump --no-data` 导出实际 Release Test Database，并与 Canonical `backend/database/schema.sql` 做结构比较；比较结果和 Dump 放入 `backend/database/release/` 作为 Assignment Evidence。A 把 Release Tag、URLs、Bootstrap Log 和 Cloud Test Evidence 写入 Runbook，C 链接到 Trello。

首次 Final Bootstrap 失败且尚无正式数据时，修正 Canonical SQL、Database Design、SQLAlchemy Models 和 Tests 后重新创建空 Database 并再次验证；不得让 A/B/C 分别向 RDS 导入各自 SQL Dump。Final RDS 已有数据后，结构变化必须先 Snapshot，再执行经团队 Review 的版本化 SQL Patch。Backend/Frontend Application 失败分别回滚上一 Task Definition；不得通过 `create_all()` 或 MySQL Workbench 手工修 Final Database 来“让测试通过”。

### 6.4 成本和运行边界

- Feature 阶段只保留一个开发 Private S3 Bucket；不运行 AWS RDS 或 Compute。完整 RDS/CloudFront/ALB/ECS/Scheduler 环境从 M5 开始创建和运行。
- Frontend/Backend 初始 desiredCount=1；Scheduled Tasks 运行后退出。
- AWS Budget 是告警，不是硬性费用上限。每周检查 RDS、ALB、ECS、Public IPv4、Logs 和流量等持续费用。
- 提交后保持 Public URLs、RDS、S3 和 Logs 到评分完成；收到通知后按 Runbook 归档证据并删除收费资源。

---

## 7. 小组分工与接口边界

### 7.1 成员 Owner Map

| 成员 | 主责域与交付物 | 公共 API | 不负责 / 边界 |
|---|---|---:|---|
| A | Platform、AttachmentUpload/Attachment、Dashboard、AWS、Runbook；Storage/Cloud Tests | 01–07（7） | 不实现 Ticket Workflow、User/Auth 或 Frontend 页面 |
| B | Auth/User、Ticket Core、Comment、Reference Data、Access Scope；Core Tests；Database Schema Coordinator，维护 Model Registry/Bootstrap/Seed Review | 08–20（13） | 不替 A/C 编写 Domain Model；不兼任全组 Test Lead |
| C | Assignment、Workflow、Vendor、SLA、TicketEvent/Audit、Background SLA Task；Workflow Tests；Project Coordination | 21–32（12） | 不维护 Attachment Storage、Frontend 或 AWS Release Scripts |
| D | 全部 Frontend 页面、Typed API Client、Frontend Container/Nginx、Component/E2E/Manual Tests | 无 Backend API | 不直接访问 Database/S3，不持有 Cloud/Database Credential |

每个 Owner 独立交付自己的 Model/Service/API、Schema Change、Tests、OpenAPI 和必要文档。协调角色只负责顺序、Review 和追踪，不替代 Domain Owner 实现。

### 7.2 固定的跨域合同

为减少互相等待，M1 冻结以下 Python Interface 和 OpenAPI Schema；实现可以随后替换，但调用方不得读取对方内部 Table：

| Provider | Consumer | Contract | 冻结内容 |
|---|---|---|---|
| B | A/C | `TicketAccessPolicy` | actor、ticket_id → view/write scope；隐藏资源统一 404 |
| C | B | `InitialAssignmentService` | 新 Ticket → assignee/status/首个 SLA Cycle；失败返回 UNASSIGNED |
| C | B/D | `WorkflowReadModel` | `display_status`、SLA colour、`available_actions` |
| A | D | Attachment API 02–05 | Upload Session、signed headers、前端三步上传行为 |
| Domain Owners | D | Versioned OpenAPI | Request/Response/Error Code；Mock Example |

`tickets` 基础字段由 B 维护；C 的 workflow/SLA 字段在 M1 一次冻结。之后需要跨域字段时，字段 Owner 提交独立 Schema PR，修改自己的 SQLAlchemy Model、Tests 和必要合同；B Review `model_registry.py`、外键、约束和空库 Bootstrap。Final Schema Freeze 后的必要变化另建版本化 SQL Patch，未经 Review 不得执行。

### 7.3 协作与 Review 规则

- Feature Branch → Pull Request → 本地测试证据 → 至少一名非作者 Review → Merge；禁止直接推送 `main` 或重写历史。
- Monorepo 只保留 `frontend/`、`backend/`、`infrastructure/`、`docs/`、`.github/` 五个顶层工作区；Branch 使用 `<type>/WBS-<member>-<number>-<slug>`，一个 Trello Task 对应一个短期 Branch。
- Domain Owner 对正确性最终负责；Reviewer 重点检查合同、权限、Database Schema 和回归风险，而不是接管实现。
- A 是 Release Coordinator；B 是 Database Schema Coordinator；C 是 Project Coordinator；D 是 Frontend/E2E Coordinator。四个协调角色互不替代。
- 跨域 PR 先合并 Provider Contract/Test Fixture，再合并 Consumer；共享接口变更必须同时更新 OpenAPI 和受影响 Tests。
- Trello Card 必须写 Owner、Acceptance Criteria、Dependency、Test Evidence、PR/Commit；只有 Evidence 完整才可 Done。

### 7.4 Project Coordination 与证据

- Trello 固定使用 Backlog、Ready、In Progress、Code Review、Integration Test、Blocked、Done。卡片由 Owner 自己更新；C 维护优先级、依赖和里程碑，不替成员补写工作记录。
- 每周至少一次 Planning、一次 API/Integration Sync 和一次可运行 Demo；C 记录 Decision、Blocker、Owner、Due Date，各 Domain Owner 展示自己的 Test Evidence。
- 每人每周 Worklog 最少记录 Date、Time Spent、Task、Result、Commit/PR、Test/Screenshot、Blocker、Next Action。Report 只引用可追溯证据。
- 预计延迟超过 2 天时 Owner 当日升级给 C；C 组织重新排序或缩减非必要范围。任何功能增删、状态/API/架构变化必须团队确认，C 不能单方面改变 Scope。

### 7.5 最终 Git Monorepo 目录（v6.0）

Repository 只保留 `backend/`、`frontend/`、`infrastructure/`、`docs/`、`.github/` 五个主要工作区；Root 只放全项目配置。代码按 Domain 划分，不创建 `member-a-code/` 等个人目录。

~~~text
it-service-desk/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug-report.md
│   │   └── feature-request.md
│   ├── CODEOWNERS
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── dependabot.yml
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── router.py
│   │   │   ├── dependencies.py
│   │   │   └── exception_handlers.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   ├── constants.py
│   │   │   ├── enums.py
│   │   │   ├── errors.py
│   │   │   ├── clock.py
│   │   │   └── logging.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   ├── model_registry.py
│   │   │   ├── bootstrap.py
│   │   │   ├── seed.py
│   │   │   ├── seed_demo.py
│   │   │   └── verify_schema.py
│   │   ├── contracts/
│   │   │   ├── ticket_access_policy.py
│   │   │   ├── initial_assignment.py
│   │   │   └── workflow_read_model.py
│   │   ├── common/
│   │   │   ├── pagination.py
│   │   │   ├── responses.py
│   │   │   ├── request_context.py
│   │   │   └── validators.py
│   │   ├── domains/
│   │   │   ├── platform/                  # A：API-01
│   │   │   │   ├── router.py
│   │   │   │   ├── schema.py
│   │   │   │   └── service.py
│   │   │   ├── attachments/               # A：API-02～05
│   │   │   │   ├── model.py
│   │   │   │   ├── schema.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── service.py
│   │   │   │   ├── router.py
│   │   │   │   ├── access_policy.py
│   │   │   │   └── cleanup_job.py
│   │   │   ├── dashboard/                 # A：API-06～07
│   │   │   │   ├── schema.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── service.py
│   │   │   │   └── router.py
│   │   │   ├── auth/                      # B：API-08～09
│   │   │   │   ├── schema.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── service.py
│   │   │   │   └── router.py
│   │   │   ├── users/                     # B：API-10～11
│   │   │   │   ├── model.py
│   │   │   │   ├── schema.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── service.py
│   │   │   │   └── router.py
│   │   │   ├── reference_data/            # B：API-12～14
│   │   │   │   ├── model.py
│   │   │   │   ├── schema.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── service.py
│   │   │   │   └── router.py
│   │   │   ├── tickets/                   # B：API-15～18
│   │   │   │   ├── model.py
│   │   │   │   ├── schema.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── service.py
│   │   │   │   ├── router.py
│   │   │   │   └── access_policy.py
│   │   │   ├── comments/                  # B：API-19～20
│   │   │   │   ├── model.py
│   │   │   │   ├── schema.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── service.py
│   │   │   │   └── router.py
│   │   │   ├── assignment/                # C：API-21
│   │   │   │   ├── model.py
│   │   │   │   ├── schema.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── service.py
│   │   │   │   └── router.py
│   │   │   ├── workflow/                  # C：API-22～25、28～31
│   │   │   │   ├── schema.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── service.py
│   │   │   │   ├── router.py
│   │   │   │   ├── state_machine.py
│   │   │   │   └── deadline_service.py
│   │   │   ├── vendor_workflow/           # C：API-26～27
│   │   │   │   ├── model.py
│   │   │   │   ├── schema.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── service.py
│   │   │   │   └── router.py
│   │   │   ├── audit/                     # C：API-32
│   │   │   │   ├── model.py
│   │   │   │   ├── schema.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── service.py
│   │   │   │   └── router.py
│   │   │   └── sla/                       # C：Background Job
│   │   │       ├── service.py
│   │   │       └── monitor_job.py
│   │   ├── integrations/
│   │   │   └── s3/
│   │   │       ├── client.py
│   │   │       ├── presigned_urls.py
│   │   │       └── object_verification.py
│   │   └── openapi_export.py
│   ├── database/
│   │   ├── schema.sql
│   │   ├── release/
│   │   │   ├── README.md
│   │   │   ├── schema-dump.sql
│   │   │   └── schema-verification.txt
│   │   ├── patches/
│   │   │   └── README.md
│   │   └── README.md
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── factories/
│   │   ├── fixtures/
│   │   ├── unit/
│   │   │   ├── platform/
│   │   │   ├── attachments/
│   │   │   ├── dashboard/
│   │   │   ├── auth/
│   │   │   ├── users/
│   │   │   ├── reference_data/
│   │   │   ├── tickets/
│   │   │   ├── comments/
│   │   │   ├── assignment/
│   │   │   ├── workflow/
│   │   │   ├── vendor_workflow/
│   │   │   ├── audit/
│   │   │   └── sla/
│   │   ├── contract/
│   │   ├── database/
│   │   │   ├── test_empty_database_bootstrap.py
│   │   │   ├── test_seed_idempotency.py
│   │   │   └── test_schema_constraints.py
│   │   ├── integration/
│   │   └── smoke/
│   ├── scripts/
│   │   ├── export_openapi.py
│   │   ├── export_schema.ps1
│   │   └── local_reset_database.ps1
│   ├── .dockerignore
│   ├── .env.example
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── README.md
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── app/
│   │   │   ├── router.tsx
│   │   │   ├── providers.tsx
│   │   │   └── roleRoutes.tsx
│   │   ├── api/
│   │   │   ├── httpClient.ts
│   │   │   ├── errorHandler.ts
│   │   │   └── generated/                 # D 生成，禁止手工修改
│   │   │       ├── client.ts
│   │   │       └── types.ts
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   ├── feedback/
│   │   │   ├── forms/
│   │   │   └── tables/
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   ├── profile/
│   │   │   ├── dashboard/
│   │   │   ├── tickets/
│   │   │   ├── comments/
│   │   │   ├── attachments/
│   │   │   ├── workflow/
│   │   │   ├── vendor/
│   │   │   └── audit/
│   │   ├── hooks/
│   │   ├── mocks/
│   │   │   ├── browser.ts
│   │   │   ├── handlers.ts
│   │   │   └── fixtures/
│   │   ├── styles/
│   │   ├── types/
│   │   └── utils/
│   ├── tests/
│   │   ├── component/
│   │   ├── accessibility/
│   │   └── e2e/
│   │       ├── user-ticket-flow.spec.ts
│   │       ├── engineer-workflow.spec.ts
│   │       ├── vendor-flow.spec.ts
│   │       └── attachment-flow.spec.ts
│   ├── .dockerignore
│   ├── .env.example
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── playwright.config.ts
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── README.md
├── infrastructure/
│   ├── terraform/
│   │   ├── dev-storage/
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   ├── outputs.tf
│   │   │   └── terraform.tfvars.example
│   │   └── final/
│   │       ├── versions.tf
│   │       ├── providers.tf
│   │       ├── variables.tf
│   │       ├── locals.tf
│   │       ├── network.tf
│   │       ├── security_groups.tf
│   │       ├── s3.tf
│   │       ├── rds.tf
│   │       ├── ecr.tf
│   │       ├── ecs.tf
│   │       ├── alb.tf
│   │       ├── cloudfront.tf
│   │       ├── iam.tf
│   │       ├── secrets_manager.tf
│   │       ├── scheduler.tf
│   │       ├── cloudwatch.tf
│   │       ├── budget.tf
│   │       ├── outputs.tf
│   │       └── terraform.tfvars.example
│   ├── ecs/task-definitions/
│   │   ├── backend.json.tpl
│   │   ├── frontend.json.tpl
│   │   ├── database-bootstrap.json.tpl
│   │   ├── sla-monitor.json.tpl
│   │   └── attachment-cleanup.json.tpl
│   ├── scripts/
│   │   ├── deploy-final.ps1
│   │   ├── run-database-bootstrap.ps1
│   │   ├── deploy-backend.ps1
│   │   ├── deploy-frontend.ps1
│   │   ├── run-smoke-tests.ps1
│   │   └── cleanup-aws-resources.ps1
│   ├── policies/
│   │   ├── ecs-task-role.json
│   │   └── developer-s3-policy.json
│   └── README.md
├── docs/
│   ├── baseline/
│   │   ├── IT-Service-Desk-Unified-Project-Baseline-v6.0.md
│   │   ├── v4.0-to-v5.0-changelog.md
│   │   └── IT-Service-Desk-v5.0-to-v6.0-Corrections.md
│   ├── architecture/
│   │   ├── business-flow.md
│   │   ├── state-machine.md
│   │   ├── system-architecture.md
│   │   ├── aws-architecture.md
│   │   └── database-er-diagram.md
│   ├── api/
│   │   ├── api-list.md
│   │   ├── error-codes.md
│   │   ├── mock-examples.md
│   │   └── openapi.json
│   ├── database/
│   │   ├── database-design.md
│   │   ├── local-mysql-setup.md
│   │   ├── database-bootstrap-runbook.md
│   │   └── schema-freeze-record.md
│   ├── development/
│   │   ├── local-development-guide.md
│   │   ├── git-workflow.md
│   │   ├── coding-standards.md
│   │   ├── testing-strategy.md
│   │   └── definition-of-done.md
│   ├── deployment/
│   │   ├── aws-deployment-runbook.md
│   │   ├── rollback-runbook.md
│   │   ├── cost-tracking.md
│   │   └── resource-cleanup-runbook.md
│   ├── project-management/
│   │   ├── member-allocation.md
│   │   ├── milestones.md
│   │   ├── product-backlog.md
│   │   ├── decision-log.md
│   │   ├── risk-register.md
│   │   └── meetings/YYYY-MM-DD-meeting-minutes.md
│   ├── evidence/
│   │   ├── member-a/
│   │   ├── member-b/
│   │   ├── member-c/
│   │   ├── member-d/
│   │   ├── api-tests/
│   │   ├── aws/
│   │   └── trello/
│   ├── report/
│   │   ├── final-report.md
│   │   ├── member-contributions.md
│   │   ├── user-manual.md
│   │   └── ai-usage-declaration.md
│   └── presentation/
│       ├── presentation-script.md
│       ├── demo-script.md
│       ├── slide-outline.md
│       └── video-link.md
├── .editorconfig
├── .gitattributes
├── .gitignore
├── CONTRIBUTING.md
├── docker-compose.local.yml
└── README.md
~~~

### 7.6 目录 Owner 与共享文件控制

| 路径 / 文件 | Owner / 规则 |
|---|---|
| `backend/domains/platform`、`attachments`、`dashboard`、`integrations/s3` | A |
| `infrastructure/`、AWS、Cloud Smoke、Release | A |
| `backend/domains/auth`、`users`、`reference_data`、`tickets`、`comments` | B |
| `backend/app/db/`、`backend/database/release/` | B 协调；各 Domain Owner 仍负责自己 Model 正确性 |
| `backend/domains/assignment`、`workflow`、`vendor_workflow`、`audit`、`sla` | C |
| `docs/project-management/`、Trello Backlog、里程碑、会议纪要和风险 | C |
| `frontend/`、Frontend Container、Component/E2E/Manual Tests | D |
| `backend/app/api/router.py` | B 合并 Domain Router Registration |
| `backend/app/db/model_registry.py` | B 合并 Model Registration |
| `docs/api/openapi.json` | 从 FastAPI 生成，禁止手工编辑；API Owner 随 PR 更新 |
| `frontend/src/api/generated/` | D 从已合并 OpenAPI 生成，禁止手工编辑 |

`CODEOWNERS` 中的 A/B/C/D 只是本文角色名称；实际建立 Repository 时必须替换为四位成员的真实 GitHub Username，否则 GitHub 不会自动请求 Review。

### 7.7 Database 与本地运行文件规则

- `backend/database/schema.sql`：唯一可执行 Schema Contract；创建统一 `service_desk`、完整 19 张表、Reference Data、约束、索引和 Trigger；只能用于 Empty Database。
- `backend/app/db/bootstrap.py`：验证目标 Database 为空并应用 Canonical `schema.sql`，记录执行结果；不得使用 `Base.metadata.create_all()` 生成不同结构。
- `backend/app/db/seed.py`：幂等验证/补齐 Canonical SQL 定义的 Final Reference Data；不得写测试密码或个人资料。
- `backend/app/db/seed_demo.py`：仅本地演示账号和数据，Final 禁止执行。
- `backend/app/db/verify_schema.py`：核对 Schema Version、19 张表、关键索引、35 个 Foreign Key、Unique/CHECK、两个 Audit Trigger、Reference Data 和 SQLAlchemy Mapping Drift。
- `backend/database/release/schema-dump.sql`：由通过测试的 Release Database 使用 `mysqldump --no-data` 生成，只用于和 Canonical SQL 比较及作业证据，不作为另一份结构来源。
- `backend/database/release/schema-verification.txt`：保存 Canonical SQL 与实际 Release Schema 的比较结果。
- `backend/database/patches/`：只放 Schema Freeze 后经 Review 的版本化 SQL Patch。
- `docker-compose.local.yml`：只启动本地 MySQL；Backend 在 PyCharm 直接 Debug，Frontend 通过 Vite 本地运行。
- `.env`、AWS Key、Database Password、JWT Secret、Terraform State/Variable Values 均不得进入 Git；Repository 只提交 `.env.example` 和 `terraform.tfvars.example`。

### 7.8 Branch、PR 与冲突避免

- Branch 使用 `<type>/WBS-<member>-<number>-<slug>`，例如 `feature/WBS-A15-s3-presigned-upload`、`feature/WBS-B09-create-ticket`、`feature/WBS-C23-tier2-escalation`、`feature/WBS-D12-ticket-detail-page`。
- 一个 Trello Card 对应一个短期 Branch 和一个清晰 PR；不得创建长期个人 Branch。
- Domain Owner 只修改自己的 Domain；跨域变化先提交 Provider Contract/Fixture，再提交 Consumer。
- 修改共享文件前在 Trello Card 标记 Dependency，并由维护人合并；不要四个人同时直接编辑 `router.py`、`model_registry.py` 或生成的 OpenAPI。
- PR 必须包括功能说明、修改文件、API/Schema 影响、测试结果、OpenAPI 状态、Evidence 和 Trello Card Link；至少一名非作者 Review 后以 Merge Commit 合并。
- `main` 禁止直接提交、rebase、force push 或其他 History Rewrite。合并后删除短期 Branch。

---

## 8. 开发、测试与集成 Gate

### 8.1 Definition of Done

一个 Feature 只有同时满足以下条件才可 Done：实现已合并；Role/Status/Deadline Validation 完成；Unit/Contract Tests 通过；OpenAPI 与 Examples 已更新；Canonical SQL、Database Design 和 SQLAlchemy Mapping 无 Drift；空库 Bootstrap/Seed 仍可重建；无 Secret/个人数据；错误路径和审计 Event 有验证；必要的 Screenshot/Command Output 已链接到 Trello。

### 8.2 Test Ownership

| 层级 | Owner | 最低范围 |
|---|---|---|
| Backend Unit/Service | 各 API Owner | 正常、403/404、非法状态、Deadline Boundary、幂等 |
| Database/Schema | 各 Domain Model Owner；B 协调 | Empty MySQL Bootstrap、Seed Idempotency、Foreign Key/Unique/Index、Schema Verification；Freeze 后 Patch Plan |
| Contract/API | 各 API Owner | OpenAPI Schema、Auth、错误码、Marker 直接调用 |
| Workflow/SLA/Concurrency | C | Frozen Clock；48h/80%/120h/7d 边界；Row Lock 重验；Job 重跑 |
| Attachment/Storage | A | Presign、HeadObject、Mismatch、Expiry、Idempotent Complete、Cleanup Race、CLOSED |
| Frontend Component/Accessibility | D | Role Routes、Loading/Empty/Error、Status Mapping、Close Warning |
| E2E/Manual | D 组织；场景 Owner 提供数据 | User→T1→T2/Vendor→Resolution→Reopen/Close；Attachment；权限隔离 |
| Cloud Smoke/Operations | A | Public URLs、Health、Logs、Scheduler、Restart/Rollback |

Attachment Cleanup 必须先锁定 Upload Session 并重新读取状态；只删除 EXPIRED/ABORTED Object，绝不删除 COMPLETED Object。SLA/Close Job 和 API 的 Boundary Tests 使用同一 Clock/Deadline Service，防止两套规则漂移。

### 8.3 本地验证、Integration 和 Release Gates

| Gate | 必须通过 |
|---|---|
| PR 本地验证 | Backend lint/unit/contract/empty-database-bootstrap checks；Frontend lint/type/component/build；Secret Scan；Docker Build |
| Merge to main | OpenAPI Compatible；全新本地 MySQL Bootstrap；API Integration Tests；Seed Idempotent |
| Cloud Candidate | Backend/Frontend Images、Database Bootstrap Task、Health/Smoke、S3 Upload、Scheduler Dry Run |
| Final Release | Critical E2E、Role Visibility、Direct API Test、CloudWatch Evidence、Rollback 信息、公开 URLs |

不得在本地共享测试或 Final 环境手工修数据来“让测试通过”。发现问题后同时更新 Canonical SQL、Database Design、SQLAlchemy Mapping、Bootstrap、Seed、必要 SQL Patch 或 Application Code，再从可追溯版本重新部署，保证环境可重建。

---

## 9. 里程碑与依赖

| Milestone | 日期 | 目标 | Exit Evidence |
|---|---|---|---|
| M0 Baseline Freeze | 20–23 Aug | v4、Owner、Workflow、AttachmentUpload 达成一致 | 本文 + Changelog + Trello |
| M1 Contract/Skeleton | 24–30 Aug | Repo、本地测试、OpenAPI、Models、跨域 Interface、Mock | 本地测试通过；OpenAPI 可供 D 使用 |
| M2 Core Vertical Slice | 31 Aug–6 Sep | Auth、Ticket、Assignment、Comment、首个 Frontend Flow | User 可创建并查看已分配 Ticket |
| M3 Workflow/Storage | 7–13 Sep | T1/T2/Vendor/SLA、AttachmentUpload、Audit | API Integration Tests Green |
| M4 Frontend Integration | 14–20 Sep | 各 Role 页面、Dashboard、附件、错误处理 | Critical Path 本地 E2E |
| M5 Cloud Integration | 21–27 Sep | Final RDS/S3/ECR/ECS/ALB/CloudFront/Scheduler；Database Bootstrap | Public URLs + Bootstrap/Cloud Smoke |
| M6 Hardening | 28 Sep–4 Oct | 权限、并发、Deadline、故障/回滚、成本 | Regression/E2E Green |
| M7 Evidence/Report | 5–11 Oct | Report、API List、Work Log、Screenshots、Demo | Draft Review + Evidence Index |
| M8 Submission Buffer | 12–15 Oct | Freeze、最终验证、提交包 | Submission Checklist 完整 |

关键依赖只有三条：M1 合同和 Model Skeleton 先于并行开发；M4 Schema Freeze 与 Backend Candidate Image 先于 Final RDS Bootstrap/Backend Deployment；Backend/OpenAPI Candidate 先于最终 E2E。Presentation 日期以 Canvas/课堂通知为准，当前记为 TBC。

---

## 10. MVP 验收与提交证据

### 10.1 业务验收

- User 可创建、查看、补充、确认/重开/关闭自己的 Ticket；CLOSED 不可再写或 Reopen。
- Tier 1 可处理、请求信息、解决或升级；Tier 2 可处理 Vendor 协作并对 User 最终负责。
- 48h Engineering SLA、80% Warning、5d User Timer、7d Close Window 在 API 与 Job 中结果一致。
- Manager 只能按 Assign Matrix 操作；Vendor 只能访问本 Organisation 的 Vendor Thread/Shared Data。
- Lifecycle、SLA、Comments、Vendor、Attachment 均产生正确 Scope 的不可变 Audit Events。

### 10.2 技术验收

- Marker 可通过公开 HTTPS URL 使用 Frontend，也可直接调用公开 Backend API/OpenAPI。
- Client、Backend、Cloud Database 三层成立；RDS/S3 私有且使用最小权限。
- 附件由持久化 Upload Session 绑定 Ticket/Creator/Visibility/Object；Complete 以 HeadObject 为准且幂等。
- 32 个公共 API 全部可列示和测试，其中 17 个 POST，满足 Assignment 下限。
- Git History、Pull Requests、Trello、本地测试证据、Cloud Logs、API/E2E Results 能证明个人贡献和团队集成。

### 10.3 最终交付清单

- Report PDF：Planning、分工/Work Log、Architecture/Cloud Implementation、Manual、API List、Test/Evidence、URLs。
- Source Repository：Frontend/Backend、SQLAlchemy Models、Canonical `backend/database/schema.sql`、Database Bootstrap/Seed、Release Schema Verification、Tests、Docker/IaC or Deployment Config、README/Runbook。
- Evidence Index：每个 Requirement → Screenshot/Log/Test/Commit/Trello Link。
- 公共 Frontend URL、Backend Base URL、Swagger URL；测试账号和角色说明不包含真实密码于 Repository。

---

## 11. 决定索引与参考

### 11.1 Consolidated Decisions

| ID | 决定 |
|---|---|
| D01 | FastAPI + React/TypeScript + MySQL + S3；Frontend/Backend 独立 Container |
| D02 | User-facing Status 与内部 Status 分离；PENDING_VENDOR 对 User 显示 IN_PROGRESS |
| D03 | Engineering 48h Cycle；User Action 后才新开 Cycle；Tier/Vendor/Reassign 不重置 |
| D04 | PENDING_USER 两种 Reason 共用 5d Timer；RESOLVED 7d 可 Reopen/Manual Close；CLOSED 终态 |
| D05 | 每 Ticket 最多一个 Active VendorRequest；Tier 2 可取消等待并直接解决 |
| D06 | AttachmentUpload 是 Presign 与 Attachment 之间的持久化 Session；Complete HeadObject 校验且幂等 |
| D07 | Workflow/TicketEvent 原子提交；Row Lock 后按最新状态重验 |
| D08 | CloudFront HTTPS → ALB → ECS；Private RDS/S3；Browser 只用 Presigned S3 URL |
| D09 | SLA 与 Attachment Cleanup 使用独立 EventBridge Scheduled ECS Tasks |
| D10 | Domain Owner 自带实现、SQLAlchemy Model/Schema、Tests、OpenAPI；协调角色不成为单点瓶颈 |
| D11 | Final Empty RDS 运行一次 Database Bootstrap/Seed Task 后部署 Backend，再部署 Frontend、Scheduler 和 E2E |
| D12 | Feature 阶段 A/B/C 各自本地 MySQL；AWS 只保留一个开发 Private S3，不创建开发期 RDS/Compute |
| D13 | Git 使用五工作区 Monorepo；代码按 Domain、共享文件指定 Maintainer、一个 Trello Task 对应一个短期 Branch |

### 11.2 参考

- `INFS803 Cloud Computing 2026 S2 Assignment-2.pdf`（课程 Assignment 原文）。
- AWS CloudFront Developer Guide：Application Load Balancer Origin；HTTPS Viewer/Origin 设置。
- Amazon ECS Developer Guide：EventBridge Scheduler 运行 Scheduled Task。
- Amazon S3 API Reference：HeadObject。
- 重大 v3→v4 变化见 `IT-Service-Desk-Unified-Project-Baseline-v3-to-v4-Changelog.md`。v4→v5 的重点是：移除 Alembic、取消开发期 Integration RDS、采用本地 MySQL 和开发 S3。v5→v6 的重点是：统一 Database Name 为 `service_desk`；所有环境使用完整 19 表结构；Canonical SQL 成为唯一可执行 Schema Contract；Required Response Field 使用稳定 Key + `null`；OpenAPI v1.1 为 32 个 API 提供 Frontend Mock Example。旧 Decision/讨论细节保留在历史版本，不在本基线重复。

---

**Baseline Rule**：从 M0 后开始开发。任何 State、SLA、Role Scope、API Contract、Data Model 或 Owner Boundary 的改变，必须通过团队 Change Decision 更新本文、OpenAPI、Tests 和 Trello；聊天口头结论不能单独覆盖本基线。

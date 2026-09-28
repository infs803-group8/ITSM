# 决策与依赖台账（Decision Log）

**维护人**：成员 C（协调角色，不代表最终团队决定）
**产物定位**：对应项目管理文档 C002；记录 Q01–Q10 的技术方案草稿。
**重要说明**：本文件中标注"草案"的内容是 AI 依据 S1–S8 现有合同文档给出的技术建议，**尚未经过 A/B/D 或 Andy 本人确认**，不能当作团队已达成的最终决定。标注"可直接执行"的内容属于 C 域内部实现选择，不改变对外合同，因此不必等待团队会议。

记录格式：`Q-ID / 日期 / 参与 Owner / 确定行为 / 受影响文件与任务 / Review/PR / 测试预期 / 状态`

---

## Q01 — S3/域名/Terraform 现状与 S1 基线不一致

- **日期**：2026-09-05（草拟）
- **参与 Owner**：A（提供现状）、C（登记差异）
- **问题**：`S3-BCD-handover.md` 显示实际已用共用桶 + 自定义域名 `s3.infs803-group8.com` + CloudFront，且 30 天生命周期规则已禁用；`Unified-Project-Baseline-v6.0` 第 6 节仍写开发期前缀方案和独立 Terraform `dev-storage`/`final` 配置，两者未同步，且 S7 注明 Terraform state 未导入。
- **确定行为（草案）**：C 域（Assignment/Workflow/Vendor/SLA/Audit）不直接调用 S3、不硬编码桶名或域名，因此本差异不阻塞 C 的任何任务。建议 A 尽快把 S7 记录的真实资源现状回写 `Unified-Project-Baseline-v6.0` §6 与 Terraform 配置，并在合并 Terraform apply 前统一到共用桶方案。
- **受影响任务**：C043（附件权限联调）、C051（Review Final 云环境）、C056（云端 E2E）——这三项只需要 A 确认最终域名/桶名是否已经在基线文档中更新，不涉及 C 自己的代码改动。
- **Review/PR**：待 A 提交 Baseline/Terraform 同步 PR。
- **测试预期**：无需 C 新增测试；C053/C056 的云端联调用当时的真实 URL 即可，不写死域名。
- **状态**：待 A 确认（不阻塞 C 当前开发）。

---

## Q02 — API-27/API-30 等 Success Example 向 Vendor 泄露越权字段

- **日期**：2026-09-05（草拟）
- **参与 Owner**：C（主责，API-21–32 Owner）、B（TicketDetail 归属）、D（消费方确认）
- **问题核实**：已在 `IT-Service-Desk-OpenAPI-v1.1.yaml` 核对，API-27（Vendor Response）成功响应 `TicketActionResponse.data.ticket` 直接复用 `TicketDetail`，其字段 `description`、`requester`、`assignee`、`sla`、`pending_user`、`resolution`、`closure` 均已在 Schema 中标为可空（`X | null`），但当前 Example（yaml 第 1572 行附近）填充了完整内部字段（description 原文、assignee 技能负载、sla 周期），没有体现"Vendor 视角应为 null"的要求。这与 6.1 节 Role-aware Serialization 规则冲突。
- **确定行为（草案）**：
  1. 统一原则：任何返回 `TicketDetail`（无论是 API-17 直接返回，还是嵌入在 API-21–31 的 `TicketActionResponse.ticket` 里）都必须经过与 API-17 相同的 Role-aware Serializer，不因为是"写操作的返回值"而跳过角色过滤。
  2. Vendor 角色下：`ticket.description`、`ticket.requester`、`ticket.assignee`、`ticket.sla`、`ticket.pending_user`、`ticket.resolution`、`ticket.closure` 一律置 `null`；`ticket.vendor_request`/`vendor_response` 仅保留本组织当前或历史范围内的内容。
  3. B/C/D 已确认：Vendor 的 `ticket.status` 与 `display_status` 均使用同一角色感知三态映射，只返回 `CLOSED`、本组织存在 ACTIVE Request 时的 `PENDING_VENDOR`，或其他情况下的 `IN_PROGRESS`；不得返回 `ASSIGNED`、`REOPENED`、`RESOLVED` 等内部生命周期状态。`vendor_request.status` 继续返回 ACTIVE/RESPONDED/CANCELLED。
  4. 修正 OpenAPI 中相关接口的 Success Example，按各自真实调用角色展示，而不是统一按 Vendor 视角或复用 Manager/Tier2 视角的满字段示例：API-27（Vendor Response，调用者为本组织持有 Active Request 的 Vendor）按 Vendor 视角，上述字段应为 null；API-26（Request Vendor，调用者为当前受派的 Tier2）按 Tier2 视角；API-30（Reopen，调用者为工单 requester）按 requester 视角。三者调用角色不同，不能统一改成 Vendor 的空字段版本。（2026-09-15 修正：此前版本误将三者统一描述为 Vendor 可达接口。）
  5. 新增 Contract Test：以 Vendor Actor 调用 API-27，断言返回体中上述字段确为 `null`（对应测试矩阵 T-AUTH-03）。
- **受影响任务**：C030（API-27 实现）、C038（合同核验）、C047（Vendor 隔离联调）。
- **Review/PR**：C030 的 PR 需要包含新增的 Vendor 越权字段 Contract Test；B/D 需 Review 是否接受 `ticket.status` 的处理方式。
- **测试预期**：`test_api27_vendor_scope.py` 之类，断言 7 个字段为 null，且 `vendor_request`/`vendor_response` 只含本组织数据。
- **状态**：已由 B/C/D 确认；Vendor `ticket.status` 三态映射已进入实现与回归测试。

---

## Q03 — Vendor 历史 Thread 的持久化读取方式

- **日期**：2026-09-05（2026-09-28 确认）
- **参与 Owner**：C（主责）、B（跨域字段）、D（前端读取方式）
- **问题**：`Unified-Project-Baseline-v6.0` 要求 Vendor/Tier2 能持续读取历史 VendorRequest 的 Thread 和回复，但 OpenAPI 里 `TicketDetail.vendor_request` 只嵌入"当前"单个 VendorRequestView，`VendorResponseView` 只出现在动作响应（API-27 成功回包）里，没有独立的"历史列表"读接口。如果没有专门接口，前端只能依赖浏览器临时缓存动作响应或把完整正文塞进 `TicketEvent.metadata`——后者违反 C012.05"不复制完整供应商正文"的规则。
- **确定行为**：
  1. 新增一个只读接口 `GET /tickets/{id}/vendor-requests`（Tier2/Manager 返回全部历史；Vendor 只返回本组织范围内的记录），每条记录包含 `VendorRequestView` + 关联的 `VendorResponseView`（如果已回复）。
  2. `TicketEvent`（VENDOR_REQUESTED/VENDOR_RESPONDED/VENDOR_CANCELLED）的 `metadata` 只保留 `vendor_request_id` 引用，不复制正文；前端时间线点击事件后跳转调用上述新接口按 ID 查看正文。
  3. 团队已批准 Change Decision：公共接口由 32 个变为 33 个，并同步更新 `Unified-Project-Baseline-v6.0` §5.2、API list、OpenAPI 和相关测试。课程不限制接口总数，无需另行取得教师批准。
- **备选方案（未采纳，仅记录）**：把 `TicketDetail.vendor_request` 从单对象改为数组，返回全部历史 VendorRequestView（含各自 Response）。优点是不新增接口数量；缺点是让"当前详情"接口承载历史列表语义，且需要改动更多现有 Consumer（D 的详情页组件）。
- **受影响任务**：C015（事件时间线）、C030（Vendor Response）、C047（Vendor 隔离联调）、C048（本地集成 Gate）。
- **Review/PR**：C 在 PR #52 提供持久化读取和组织隔离；B 提供 tickets 路由、工单范围检查、公共模型和 OpenAPI；D 在合同合并后重新生成客户端并接入页面。
- **测试预期**：T-VEN-05（历史正文可读、组织隔离）。
- **状态**：**已决定并实施**。采用独立只读接口；不把历史数组塞入 `TicketDetail.vendor_request`，也不把正文复制到审计 metadata。

---

## Q04 — EventType 缺少 `TICKET_UPDATED` 与专属 `ESCALATED`

- **日期**：2026-09-05（草拟）
- **参与 Owner**：C（Escalation 部分可自主决定）、B（API-18 编辑部分需确认）
- **问题核实**：已在 OpenAPI 逐条核对 `EventType` 枚举，共 24 项：`TICKET_CREATED, AUTO_ASSIGNED, ASSIGNED, REASSIGNED, HANDLING_STARTED, COMMENT_ADDED, SLA_CYCLE_STARTED, SLA_PAUSED, SLA_AT_RISK, SLA_OVERDUE, SLA_MET, USER_INFO_REQUESTED, USER_RESUMED, VENDOR_REQUESTED, VENDOR_RESPONDED, VENDOR_CANCELLED, RESOLUTION_SUBMITTED, RESOLUTION_CONFIRMED, AUTO_RESOLVED_NO_USER_RESPONSE, RESOLUTION_CONFIRMATION_TIMEOUT, TICKET_REOPENED, TICKET_CLOSED_MANUAL, TICKET_CLOSED_AUTO, ATTACHMENT_ADDED`。确实没有 `TICKET_UPDATED`，也没有区分"普通改派"与"Tier1→Tier2 升级"的专属类型（两者都只能用 `REASSIGNED`）。
- **确定行为（草案）**：
  1. **Escalation（C 自己的 API-25，可直接执行）**：复用现有 `REASSIGNED` 类型，不新增枚举、不改 SQL CHECK；在 `metadata` 中写 `{"reason": "ESCALATION", "from_tier": "TIER1", "to_tier": "TIER2"}` 加以区分。这样审计时间线仍能通过 metadata 识别"这是升级"而不是普通改派，且不需要动 SQL/OpenAPI 枚举，风险最低。
  2. **API-18 编辑（B 的域）**：现有 24 个类型里没有能表达"用户编辑了 Ticket 标题/描述/分类/优先级"的类型。建议新增 `TICKET_EDITED`，需要同步修改 OpenAPI `EventType` 枚举 + `S5` 的 SQL CHECK 约束 + 相关测试。这是公共合同变更，由 B 提交、C Review（因为 C 维护事件映射表），不由 C 单方面决定。
- **受影响任务**：C012（事件映射表）、C028（Escalation 实现）、C042（与B联调）。
- **Review/PR**：Escalation 方案可随 C028 PR 直接落地；`TICKET_EDITED` 新增需 B 发起独立 Schema/OpenAPI PR，C Review。
- **测试预期**：T-EVT-05（API-18 编辑审计）；Escalation 对应 C028 的单元测试断言 metadata 内容。
- **状态**：Escalation 部分**可直接执行**；`TICKET_EDITED` 新增**待 B 确认**。

---

## Q05 — Auto Resolve/Auto Close 的事务提交与时间戳策略

- **日期**：2026-09-05（草拟）
- **参与 Owner**：C（Workflow/SLA 主责）、B（Deadline 边界的通用约定）
- **问题**：文档要求"过期先自动处理，再返回 409"，但没固定：(a) 自动处理提交后、当次 HTTP 请求算不算失败并回滚；(b) 多天停机后补跑时，`resolved_at`/`closed_at` 该用处理时刻还是原 Deadline 时刻。
- **确定行为（草案）**：
  1. **事务边界**：懒惰检查（API-24/29/30/31）在同一个数据库事务内完成"重新验证已过期 → 提交自动结果（状态+TicketEvent）→ COMMIT"，提交成功后，再判断这次用户请求本身是否还能执行原动作；如果不能（因为状态已经变了），返回结构化 409（`USER_RESPONSE_WINDOW_EXPIRED` 等），**不回滚刚刚已经提交的自动结果**。也就是"自动结果的提交"和"用户这次请求的失败响应"是两个独立的结果：前者已经落库成功，后者只是告知调用方"你来晚了"。
  2. **时间戳策略**：`resolved_at`/`closed_at`/SLA 事件时间统一使用**处理时刻**（Job 实际运行或懒惰检查触发的 UTC 时间），不使用理论上的原始 Deadline 时刻，避免记录一个系统实际没有观测到的时间点。原始 Deadline 仍保留在 Ticket 字段和 Event metadata 中作为审计对照，多天停机补跑时在 metadata 加 `"detected_late": true` 便于事后说明。
  3. **幂等保障**：Job 与懒惰检查共用同一个 Deadline Service，两者均在事务中锁定 Ticket，并按锁后最新状态与截止时间重新判断是否仍需执行；已完成的转换不重复执行，也不重复追加成功事件。`(ticket_id, cycle_no, event_type)` 的数据库 Unique Guard 仅覆盖 `SLA_CYCLE_STARTED`、`SLA_PAUSED`、`SLA_AT_RISK`、`SLA_OVERDUE`、`SLA_MET` 五类需要非空 `cycle_no` 的 SLA 事件；Auto Resolve/Auto Close 事件该列为 `null`，不受此 Unique Guard 保护，其幂等性完全依赖 Ticket 行锁、状态重验与业务变更和事件的原子提交，不能归因于现有 SLA Unique Guard。如需为 Resolve/Close 增加数据库层面的独立唯一保护，需提出单独的 Schema 变更，并验证合法后续 Cycle 不会被误拦截。（2026-09-15 修正：此前版本错将该 Unique Guard 描述为同时保护 Auto Resolve/Close。）
- **受影响任务**：C018、C019、C020、C037。
- **Review/PR**：建议 B 一起 Review（因为涉及 API-24/29/30/31 的公共响应约定），但不改变 Ticket 表结构，不属于公共合同变更，C 可先按此实现再一并 Review。
- **测试预期**：T-TIME-05/06、T-RACE-01、T-JOB-05。
- **状态**：草案已具体，**可先按此实现**，随 C018/C019 PR 一并请 B Review 确认无异议。

---

## Q06 — `AssigneeSummary` 对 User 角色暴露内部调度字段

- **日期**：2026-09-05（草拟）
- **参与 Owner**：C（提出）、B（TicketDetail/tickets 路由归属）、D（前端类型影响）
- **问题核实**：已核对 OpenAPI，`AssigneeSummary` 的 `tier/skills/is_available/active_load` 全部是 Required 且非 nullable 字段；`TicketDetail.assignee` 类型是 `AssigneeSummary | null`（可以整体为 null，但不能只隐藏其中几个子字段）。这意味着只要 Ticket 有负责人，User 角色调用 API-17/所有 Workflow 写操作都会连带看到工程师的技能列表、可用状态和当前负载——这些是内部排班信息，baseline 里只说 User 需要"负责人显示名"。
- **确定行为（草案，需团队决定采纳哪一种）**：
  - **方案A（推荐，需改 OpenAPI）**：新增一个精简类型 `AssigneeDisplay {user_id, display_name}`，`TicketDetail.assignee` 按角色返回：User 角色返回 `AssigneeDisplay`，Tier1/Tier2/Manager 返回完整 `AssigneeSummary`。需要在 OpenAPI 中把该字段类型声明为两者的 oneOf，或者拆成两个字段名（如 `assignee_display` 面向所有角色 + `assignee_detail` 仅内部角色可见，Required 但对 User 为 null）。这是公共合同变更，需团队 Change Decision，同步改 D 的前端类型生成。
  - **方案B（不推荐，作为兜底）**：不改 OpenAPI，User 角色下 `active_load` 填 0、`is_available` 填 `true`、`skills` 填该 Ticket 的 `category` 单元素列表，作为约定占位值。缺点是向 Frontend/Marker 返回了看似真实、实际是伪造的数据，容易被误认为真实字段，不建议作为最终方案，仅在团队时间不足时作为临时妥协。
- **受影响任务**：C021（WorkflowReadModel）、C038（合同核验）、C045（交付 D 的场景说明）。
- **Review/PR**：需 B（改 tickets Schema）+ D（前端类型）共同确认方案A是否可行；C021 的实现需要等这个决定。
- **测试预期**：T-READ-01（各角色读取详情，Required Key 稳定、无越权字段）。
- **状态**：**需团队尽快决定方案A/B**——这会影响 C021 和 D 的前端类型生成节奏，建议列为本周决策优先级最高的一项。

---

## Q07 — `CloseRequest.acknowledge` 用 `const: true` 但需要专属错误码

- **日期**：2026-09-05（草拟）
- **参与 Owner**：C（API-31 Owner，可自行决定）
- **问题核实**：已核对 OpenAPI，`CloseRequest.acknowledge` 定义为 `type: boolean, const: true, required`。按标准 JSON Schema/Pydantic 校验语义，如果请求缺少该字段、传 `false` 或传其他类型，会在到达业务逻辑之前就被框架级请求校验拦截，产生通用 `422 VALIDATION_ERROR`，而不是合同里为 API-31 专门定义的 `422 CLOSE_ACKNOWLEDGEMENT_REQUIRED`。
- **确定行为（草案，2026-09-15 修正后按此实现）**：API-31 继续要求 `acknowledge` 为必填的 JSON boolean，且值必须为 `true`；后端必须严格校验原始输入类型（使用 `StrictBool` 或等价机制），不能把字符串（如 `"true"`）或数字（如 `1`）隐式转换为确认。在字段校验与请求校验异常处理路径中，显式把 `acknowledge` 缺失或为 `false` 映射为结构化 `422 CLOSE_ACKNOWLEDGEMENT_REQUIRED`（而不是框架级通用 `422 VALIDATION_ERROR`）；非布尔输入及其他字段错误仍走既有请求校验规则，该转换只限定在 API-31 相关字段，不改变其他接口的错误处理路径。实现和导出的 OpenAPI 必须同时保留严格布尔、必填、`const: true` 语义。（此前版本建议把字段放宽为普通 `bool` 再由 Service 层判断 `is True`：经核实，普通必填 `bool` 仍会在缺失时被框架校验拦截为通用错误码，且会把 `"true"`/`1` 这类非布尔输入误判为已确认，因此不采用该方案。）
- **受影响任务**：C034（API-31 实现）。
- **Review/PR**：随 C034 PR 提交，请任意一名非作者 Reviewer 确认测试覆盖 T-CLOSE-01（缺失/false/true 三种输入）。
- **测试预期**：T-CLOSE-01。
- **状态**：技术方案已修正为严格校验版本，**可按此实现**，随 C034 PR 提交 T-CLOSE-01 的测试证据供 Review。

---

## Q08 — 旧文档/课程模板残留的版本与路径表述（MySQL 版本、`/docs` 入口等）

- **日期**：2026-09-05（草拟）
- **参与 Owner**：C（执行时遵循，无需团队决策）
- **问题**：`成员C开发项目管理.md` 中指出 S4 提到本地可用 MySQL 8.0/8.4，S2 教学示例段落出现 `/docs`、`.log` 配 `image/png` 等课程模板残留写法，与 Baseline v6.0 的正式决定不完全一致。
- **确定行为**：这不是团队尚未决定的真分歧，而是旧文档没跟上最新 Baseline。C 在所有本地命令、README 草稿、测试脚本、文档引用中一律按 `Unified-Project-Baseline-v6.0` 执行：本地和 RDS 统一用 **MySQL 8.4**；`backend/database/schema.sql` 是唯一可执行结构来源；Swagger/OpenAPI 入口固定为 `/api/docs`、`/api/openapi.json`（不是课程 PDF 示例里的 `/docs`）。
- **受影响任务**：C004、C005、C038。
- **Review/PR**：无需新增 PR，仅在后续文档中标注引用来源为 Baseline v6.0，避免其他成员被旧文档误导。
- **测试预期**：无。
- **状态**：**无冲突，直接按 Baseline 执行**。

---

## Q09 — SLA Job 补偿场景的事件语义（跳过 80%、OVERDUE 后请求信息、改派备注）

- **日期**：2026-09-05（草拟）
- **参与 Owner**：C（SLA/Workflow 主责，可先行实现，建议 A/B Review）
- **确定行为（草案）**：
  1. **跳过 80% 直接发现 OVERDUE**：Job 在同一次运行内**补写 `SLA_AT_RISK` 事件**（时间戳=本次 Job 实际运行时刻，不是理论 80% 时刻），紧接着在同一次运行中写 `SLA_OVERDUE` 事件（AT_RISK 先于 OVERDUE 落库），保证时间线语义完整、不出现"直接 OVERDUE 却没有 AT_RISK 记录"的空洞历史；`(ticket_id, cycle_no, event_type)` 的 Unique Guard 保证同一 Cycle 不会被再次补写。
  2. **已 OVERDUE 后请求信息**：当前 Cycle 的历史 `SLA_OVERDUE` 事件保留不变（不删除、不覆盖）；`tickets.sla_status_code` 转为 `PAUSED`（这是"当前"状态字段，与历史 Event 互不冲突）；Resume 后开始的新 Cycle 从 `ON_TRACK` 重新计时，不继承上一 Cycle 的 OVERDUE 标记。
  3. **改派/重开的原因记录**：Manager Reassign 的可选 `reason` 写入 `REASSIGNED` 事件的 `metadata`（不新建 Comment，避免与正式 Workflow Comment 混淆）；Reopen 的必填 `reason` 作为一条 `visibility=USER_VISIBLE` 的 Workflow Comment（`comment_type=WORKFLOW, workflow_action=REOPEN`）落库，同一事务内写入 `COMMENT_ADDED` 事件，由其 `comment_id` 列字段关联该 Comment；另写 `TICKET_REOPENED` 事件，该事件的 `comment_id` 列字段保持为 `null`（`chk_ticket_events_comment_type` 约束要求非 `COMMENT_ADDED` 类型的 `comment_id` 必须为空），在其 `metadata` 中保存该 Comment 的 `comment_id` 作为最小引用，不复制正文；Ticket 状态变更、Comment 写入与两条事件在同一事务原子提交，任一写入失败整体回滚。如需让 `TICKET_REOPENED` 的 `comment_id` 列直接持有引用，需先提出并经审核的 Canonical Schema 变更，当前 Schema 下不可直接执行。（2026-09-15 修正：此前版本让 `TICKET_REOPENED` 事件直接引用 `comment_id`，会被 `chk_ticket_events_comment_type` CHECK 约束拒绝，已用 SQLite 内存表验证插入被拒。）
- **受影响任务**：C012、C017、C024、C026、C033、C035。
- **Review/PR**：随对应任务 PR 提交，建议 A（SLA Task 运行方）、B（Comment 归属）各 Review 一次确认无异议。
- **测试预期**：T-SLA-07、T-TIME-05、T-WF-09。
- **状态**：草案已具体，**建议按此先行实现**，PR 描述中链接本条目供 Review。

---

## Q10 — S7 明文凭据与正式账号发放流程缺失

- **日期**：2026-09-05（草拟）
- **参与 Owner**：A（凭据处置）、B（受控角色账号创建）、C（记录角色/证据引用，不接触凭据）
- **确定行为**：
  1. C 侧行动（可直接执行）：本文件及 C 后续产出的任何文档、`TicketEvent.metadata`、日志、测试 Fixture、PR 描述**一律不复制** `S3-BCD-handover.md` 中的 Access Key/Secret Key/密码；C010 的测试数据工厂使用本地生成的假密码或团队后续提供的受控 Seed 账号，Final 环境不执行 `seed_demo`。
  2. **风险提示（已同步写入 risk-register.md）**：`S3-BCD-handover.md` 中的 AWS Access Key/Secret Key 是明文长期凭据，目前保存在本地 Markdown 文件中（不受 `.gitignore` 保护，一旦被加入 Git 历史即永久留存）。建议尽快请 A 轮换该密钥、改用短期凭据或 Secrets Manager，并确认该文件不会被提交到仓库。
  3. 正式（非 USER）账号发放流程：目前文档中没有写明 Tier1/Tier2/Manager/Vendor 账号具体由谁、通过什么方式创建，需要 B（Auth/User 域 Owner）明确一个受控流程（例如只能通过种子脚本或数据库直接插入，不开放注册）。
- **受影响任务**：C001、C010、C051、C056、C061。
- **Review/PR**：待 A/B 确认处理方式和账号发放流程。
- **测试预期**：C010 的测试数据工厂不依赖真实凭据即可通过。
- **状态**：C 侧行动**已可执行**；凭据轮换与账号发放流程**待 A/B 确认**。

---

## Q11 — Audit 事件权限矩阵（Role × EventScope），供 PR #21 引用

- **日期**：2026-09-15（新增，回应 PR #21/#22 审核意见）
- **参与 Owner**：C（提出并维护实现）、A/B/D（待确认）
- **背景**：PR #21（API-32 Audit 事件域）的代码注释与 PR 描述此前将 Role × EventScope 权限规则指向 Q02，但 Q02 实际讨论的是 API-27 等接口向 Vendor 返回 TicketDetail 时的字段脱敏，并未记录 Audit 事件的读取权限矩阵，引用不足以作为该权限实现的决策记录。现补记该矩阵。
- **确定行为（草案，待确认）**：

| Role | Ticket 读取范围 | 允许的 EventScope |
|---|---|---|
| USER | 自己提交的工单 | USER_VISIBLE |
| ENGINEER_TIER1 | 当前分配给自己的工单 | USER_VISIBLE、INTERNAL_ONLY |
| ENGINEER_TIER2 | 当前分配给自己的工单 | USER_VISIBLE、INTERNAL_ONLY、VENDOR_SCOPE |
| EXTERNAL_VENDOR | 本组织具有 Active 或 Historical VendorRequest 的工单 | 仅本组织 VENDOR_SCOPE |
| SERVICE_DESK_MANAGER | 全部工单 | 三类 Scope |

  显式请求无权 Scope 返回 `403 DATA_SCOPE_DENIED`；请求隐藏或不存在的工单返回 `404`；Vendor 对历史 Request 的读取权与回复/上传等写入权分别判断（历史可读，写入仍要求 Active）。
- **受影响任务**：C032（Audit 域实现，对应 PR #21）。
- **Review/PR**：待 A/B/D 确认；确认前，PR #21 保持 Draft，代码注释与 PR 描述均改为指向本条目。
- **测试预期**：随 PR #21 补充的 MySQL 专项测试一并验证（角色隔离、Vendor 历史读取、403/404 边界、分页与事务）。
- **状态**：**待 A/B/D 确认**（本条目由 C 依据现有代码整理，不代表团队已批准）。

---

## 汇总：本周需要团队尽快确认的事项（按影响排序）

1. **Q06**（AssigneeSummary 是否需要按角色瘦身）——直接卡住 C021 和 D 的前端类型生成。
2. **Q03 已解决**：采用 `GET /tickets/{id}/vendor-requests`，C/B/D 按确认分工实施。
3. **Q02** 中 `ticket.status` 对 Vendor 是否可见——影响 C030 的 Contract Test 具体断言。
4. **Q04** 中 `TICKET_UPDATED` 是否新增枚举——影响 B 的 API-18 和 C 的事件映射表定稿。
5. **Q10** 凭据轮换与账号发放流程——不阻塞开发，但存在真实安全风险，建议尽快处理。

6. **Q11**（Audit 事件权限矩阵）——PR #21 的合并前置条件，需 A/B/D 确认后 PR #21 才能转正式复审。

其余（Q01、Q05、Q07、Q08、Q09）C 可以按修正后的草案直接推进，不必等待团队会议。

---

## PR 追踪

| 分支 | PR | CI 状态 | 备注 |
|---|---|---|---|
| `chore/WBS-C00-decision-log-risk-register` | #22 (draft) | 未知/待补 | 本文件与 risk-register.md 的初版；2026-09-15 收到审核意见（Q09/Q07/Q05 三处 P2 技术描述已按建议修正，见上文各条目内的修正说明），待复审 |
| `feature/WBS-C21-audit-domain` | #21 (draft) | 全部通过（Backend CI/test、Docker Build x2、OpenAPI Contract Check，2026-09-13） | Audit 域（API-32）实现；2026-09-15 收到审核意见：暂无阻塞性代码缺陷，但需补齐 Q11 权限矩阵确认、新增 MySQL 专项测试、更新验证记录后再申请复审 |

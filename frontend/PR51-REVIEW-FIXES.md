# PR #51 R1–R4 本地修复与 R3 协调说明

> 后续状态：本文件记录的是 PR #51 审核时的缺口。PR #53 已在 main 增加 API-33；D04 已重新生成客户端并接入持久化 Vendor 历史读取。当前实现与验证见 [D04-HANDOFF.md](D04-HANDOFF.md)。

日期：2026-09-28。分支：`feature/WBS-D03-ticket-workspace`。
审核基准：`499767e1021dcc3b51cc1272ddc1ff9cc51c8a0e`。
本轮仅修改 `frontend/`，未修改 backend、OpenAPI、数据库、依赖或锁文件。修复先在本地完成并报告；用户随后确认将这些修改提交至现有 PR #51。最终提交 SHA 以该 PR 的修复提交为准。

## 本地修复范围

| 项目 | 改动位置 | 处理结果 |
| --- | --- | --- |
| R1 | `src/api/attachmentTransfer.ts`、`AttachmentsPanel.tsx` | 单次解析参考数据白名单中的扩展名/MIME；仅在 File.type 为空时补齐。校验与 API-02 共用结果，保留拒绝规则和原始 signed-header PUT |
| R2 | `src/features/workspace/shared.tsx`、附件/评论/工单/工作流表单 | 下载使用独立读取助手，防重复、错误、卸载保护不变且不影响查询。写入范围收窄，失败恢复仍活跃的被取消读取，成功刷新受影响数据 |
| R3（D） | `src/mocks/workspaceHandlers.ts`、API/浏览器测试、README、D03-HANDOFF | 移除回复事件中虚构的正文 metadata，按当前后端返回 `{}`。测试区分提交成功、状态/事件变化与缺失的持久化读取 |
| R4 | `src/features/workspace/WorkflowPanel.tsx` | CLOSE 1,000，REOPEN 4,000，输入与提交双层校验，保留关闭理由选填和重开非空规则 |

回归测试位置：

- `tests/component/workspace.test.tsx`：空 MIME 与拒绝边界、延迟参考数据期间下载成功/失败、防重复下载、卸载拒绝迟到结果、写入范围及失败后的读取恢复、关闭/重开长度边界。
- `tests/e2e/attachment-flow.spec.ts` + `tests/fixtures/debug.log`：从真实磁盘路径选文件，不注入 MIME，检查空 File.type、presign text/plain、signed-header 原始 PUT、不带 API Bearer、完成顺序。
- `tests/api/workspace.test.ts` + `tests/e2e/vendor-flow.spec.ts`：API-27 即时返回回复，API-32 metadata 不含正文，Tier 2 重进只能看到事件，不能据此宣称正文读取完成。

## 可转发给 B/C：R3 / Q03 需要完成什么

PR #51 R3 核查到一个已有的读取缺口，而不是回复没有保存：

1. `backend/app/domains/vendor_workflow/service.py` 的 `VendorResponseService.respond()` 已调用 repository 保存回复，但追加 `VENDOR_RESPONDED` 事件时未传正文 metadata。
2. `backend/app/domains/audit/service.py` 只返回存储的 metadata；空值为 `{}`，不会补回复正文。
3. API-27 写入响应有 `vendor_response.message`；但 API-17 的 `TicketDetail.vendor_request` 没有回复正文，API-32 也读不到正文。工程师之后重新打开工单或换会话，无法取得已保存回复及历史讨论。

请 **C 主责、B 配合**，按 `docs/project-management/decision-log.md` 的 Q03 推进：

- 先由团队确认读取合同。Q03 的 `GET /tickets/{id}/vendor-requests` 只是草案，不能直接当作已批准接口；也可评估对现有详情字段的改造，但需要明确决定。若新增接口，要同步 API 总数、OpenAPI、项目基线和决策记录。
- 合同需明确：请求/回复关联 ID、正文、时间、未回复时的空值、历史顺序/分页，以及 ACTIVE/RESPONDED/CANCELLED 请求的读取规则；给出成功及无权限示例。
- C 实现数据库持久化读取与供应商组织隔离；B 配合 tickets 路由注册、详情跨域字段/序列化和合同对齐。保持已有工单权限范围，不因历史读取扩大工单访问权限。
- 授权 Tier 2 / Manager 可读其工单权限范围内的历史；Vendor 仅本组织当前/历史记录；USER 和 Tier 1 不得读到供应商协作正文，也不能通过猜 ID 越权读取其他组织。
- 后端验收：回复写入后，授权 Tier 2 离开再进入、重新登录或另一个授权会话仍可读取正文；覆盖历史多请求、多组织隔离、无回复、关闭/取消等状态及无权限情形。提交相应合同/集成测试。
- **不要把完整正文复制进审计 metadata，也不要用前端缓存 API-27 的回包代替持久化读取。**

D 已修正 Mock、测试与完成情况说明。待上述合同及实现落地，D 再重新生成客户端、添加回复/历史读取页面并完成真实联调。当前 Q03 仍未完成，不能把“提交回复测试通过”当成“供应商讨论功能全部完成”。

## 验证结果

2026-09-28 本地验证：

- `npm run check`：生成文件一致性、TypeScript、129 项单元/组件测试、生产构建全部通过（原 117 项，新增 12 项；另有原测试补强）。
- `npm run test:api:browser`：3 项通过。
- `npm run test:auth:e2e`：6 项通过。
- `npm run test:e2e`：7 项通过，包括真实磁盘 `.log` 的空 MIME 上传，以及关闭/重开生命周期。
- 关闭 1,000 / 重开 4,000 字符的合法请求通过原有合同校验 Mock，断言实际状态转为 CLOSED / REOPENED；超限在 HTTP 前拦截。
- `git diff --check`：通过。所有修改及新增文件均在 `frontend/`；验证时尚未提交，修复基于 `499767e`。
- 浏览器测试刷新了 6 张 `docs/evidence/d03-*.png` 证据图；已检查真实 `.log` 上传成功截图。
- 构建仍有原有的非阻塞大包警告：主 JS 721.67 kB / gzip 233.69 kB；未提高阈值隐藏提示。

真实 Python / MySQL / S3 联调不在本轮完成声明内；对象字节下载、CORS、签名过期、后端授权仍需与相应成员联调。

## PR #51 英文修复说明参考

### Trello / WBS task

D03 — service desk workspace; PR #51 review follow-up (R1–R4).

### What changed

- Resolve empty file MIME from reference data and reuse it for presign; retain signed-header raw uploads.
- Separate download reads from writes; scope cache cancellation and resume interrupted active reads.
- Match vendor audit Mock payloads to the backend and remove misleading reply-read assertions.
- Align close/reopen text limits with the contract and add boundary regressions.

### Evidence

- [x] Tests pass: 129 unit/component, 3 API-browser, 6 account-browser and 7 business-browser tests; generation, typecheck and build pass.
- [ ] API changes include tests and OpenAPI updates — N/A, no contract changes.
- [x] UI changes include screenshots (`docs/evidence/d03-*.png`).
- [ ] Schema changes update schema.sql and database documentation — N/A, no schema changes.
- [x] No secrets or .env files are included.

### Reviewer notes

Persisted vendor reply/history reading remains incomplete pending Q03 (C lead, B contract/routing coordination, D frontend consumer). API-27 submission and state transitions are tested separately; no complete vendor discussion flow or real Python/MySQL/S3 integration is claimed.

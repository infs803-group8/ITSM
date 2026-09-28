# D04 Vendor 历史读取交接

## 分支与范围

- 分支：`feature/WBS-D04-vendor-history`，从已合并 PR #51/#52/#53 的 main `6fcde23` 创建。
- 只修改 `frontend/`；未修改 backend、OpenAPI、数据库、依赖或锁文件。
- 本轮不提交、不推送、不创建 PR，等待用户确认。

## 完成内容

1. 以最新 `docs/api/openapi.yaml` 重新运行固定版本生成器，正式 SDK 从 32 个 operation 更新为 33 个，并生成 `api33ListVendorRequestHistory`、`VendorRequestHistoryView/Response` 和对应合同 fixture/hash。
2. 工单详情新增 **Vendor history** 标签页，直接调用 `GET /tickets/{id}/vendor-requests`，显示按时间顺序保存的请求、组织、状态、正文及可空回复。
3. 权限入口与合同一致：Tier 2 / Manager 可以读取可见工单的全部历史；Vendor 仅看到本组织；USER / Tier 1 不显示标签页也不发 API-33 请求。
4. Vendor 回复表单仍通过 API-27 写入，但页面不保存或展示该临时回包。成功后使工单查询失效并重新读取 API-33；退出登录会清空缓存，重新登录后再次读取 API-33；页面的 **Refresh ticket** 会同时刷新详情与当前打开的历史。
5. API-32 Activity 继续只显示审计事件，metadata 保持 `{}`，不复制完整 Vendor 回复正文。
6. Mock 新增多组织历史、已回复/未回复/已取消数据；请求 Vendor、Vendor 回复和提交方案取消请求时同步持久化历史状态，以便本地页面演示和回归。

## 主要文件

- `src/api/generated/`、`src/mocks/workspace-fixtures.generated.json`：API-33 正式生成结果。
- `src/features/workspace/VendorHistoryPanel.tsx`：持久化历史页面。
- `src/features/workspace/TicketDetailPage.tsx`、`WorkflowPanel.tsx`、`styles/global.css`：角色入口、回复上下文和桌面样式。
- `src/mocks/state.ts`、`workspaceModel.ts`、`workspaceHandlers.ts`、`handlers.ts`：API-33 Mock、组织隔离和状态持久化。
- `tests/api/contract.test.ts`、`workspace.test.ts`：33 项合同、权限、组织隔离、写后读取。
- `tests/component/workspace.test.tsx`：授权入口、错误重试、未授权角色不发请求。
- `tests/e2e/vendor-flow.spec.ts`：Vendor 提交后 API-33 重读、重新登录仍可读、Tier 2 全历史及 Activity 不泄露正文。

## 仍需真实环境验证

- 使用真实 Python/MySQL 账号验证 API-33 的跨会话持久化、历史顺序、多组织隔离和 403/404 行为。
- 云端验证 CORS、鉴权过期、同源 `/api/v1` 路由及 Vendor 附件/S3 联调。
- 本地 Mock 会在整个页面刷新时重置；浏览器自动化以“退出后重新登录”验证新的会话重新请求 API-33，数据库跨进程持久化必须由真实后端联调确认。

## 验证记录

2026-09-28：

- `npm run check`：API 生成一致性、TypeScript、**134 项单元/组件测试**和生产构建通过。
- `npm run test:api:browser`：3 项通过。
- `npm run test:auth:e2e`：6 项通过。
- `npm run test:e2e`：7 项通过，其中 Vendor 流程覆盖 API-33 写后重读、重新登录、Tier 2 全历史、Vendor 组织隔离及审计 metadata 不承载正文。
- `git diff --check`：通过；改动范围仅 `frontend/`。
- 新截图：`docs/evidence/d04-vendor-history.png`。其他 D03 证据图随完整浏览器测试重新生成。
- 生产构建成功，保留原有非阻塞大包提示：主 JavaScript 约 723 kB / gzip 234 kB。
- 检查时发现并已修复一个额外问题：顶部 **Refresh ticket** 原本只刷新 API-17；现在会刷新整个工单查询子树，包括当前打开的 API-33 历史。
- 没有发现新的前端阻塞问题；尚未运行真实 Python/MySQL/S3 或云端部署联调。

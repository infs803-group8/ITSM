# D03 业务页面交接

## 分支与边界

- 从已经合并 D02 / PR #50 的最新 main `01fad63` 创建 `feature/WBS-D03-ticket-workspace`。
- main 已含资料页并发修复 `515723b`，不需要重复 cherry-pick。
- 本轮只修改 `frontend/`，不修改后端、数据库、OpenAPI、依赖或锁文件。
- 保持黄 / 黑 / 白桌面主题；没有增加手机专用布局。
- 完成后保留本地修改供用户审核；本轮不自动提交、推送、创建 PR 或合并 main。

## 页面与功能

| 入口 / 文件 | 本次完成 |
| --- | --- |
| `/tickets` · `src/features/workspace/TicketListPage.tsx` | 角色范围内的工单 / Vendor 请求列表；搜索、状态、分类、优先级、SLA、管理员 assignee_id 筛选；排序、分页、空数据、失败重试 |
| `/tickets/new` · `TicketForm.tsx` | USER 创建；标题 / 描述 / 分类 / 优先级；长度及空白校验；创建成功进入详情 |
| `/tickets/:id` · `TicketDetailPage.tsx` | 描述、角色可见状态、负责人、SLA、等待原因与截止时间、方案、关闭信息、Vendor 请求；稳定读取 null；只读终态 |
| 同一详情页 · `TicketForm.tsx` | EDIT 动作可见时编辑；仅提交改变的核心字段，不直接改状态、负责人、SLA |
| 同一详情页 · `WorkflowPanel.tsx` | API-21–31：分配 / 改派、开始、请求补充、恢复、升级、请求 Vendor、Vendor 回复、提交方案、确认、重开、关闭；分页选择合格工程师及 Vendor |
| 同一详情页 · `CommentsPanel.tsx` | 评论列表、分页、按 reference data 选择可见范围、评论提交；无普通 Vendor 评论入口；提醒评论不代替工作流操作 |
| 同一详情页 · `AttachmentsPanel.tsx` | 附件列表 / 分页 / 按需下载；类型 / 大小校验、上传进度、确认失败重试；过期上传要求重新开始 |
| 同一详情页 · Activity | API-32 角色范围内的事件时间线；系统事件、周期、时间、服务端返回的简单 metadata |
| `/dashboard` · `DashboardPage.tsx` | Tier 1 / Tier 2 / Manager 的 scope、状态数量、SLA 风险和逾期、重开未分配数量；人工刷新 |
| `/overdue` · `DashboardPage.tsx` | current/history 逾期视图、分类 / 优先级筛选、分页、详情链接 |
| `src/app/router.tsx` / `components/layout/AppLayout.tsx` | 角色路由守卫、侧栏入口、当前页面标题；未登录保护沿用 D02 |
| `src/styles/global.css` | 表格、表单、工作流操作区、风险标签、桌面看板；键盘 Skip link 保持可用 |

登录仍先进入个人资料，左侧可进入业务页面。没有增加合同之外的密码重置、角色管理、删除工单、删除附件或通知推送页面。

## 关键规则

1. UI 只按服务端 `available_actions` 展示工作流按钮；不在页面用状态推导权限。显示服务端 `display_status`，Vendor 不展示请求人、description、内部评论、负责人或 SLA。
2. Tier 1 升级成功后直接离开详情并移除详情缓存；详情 403/404 返回列表和中性提示，不清空有效登录。详情查询离页不保留缓存。
3. 409 冲突不自动重放写请求；工作流表单提示重新读取当前工单。422 保留填写内容；401 沿用 D02 清理会话和缓存。
4. `shared.tsx` 的写入锁在异步等待前生效；写入前后取消工作区读取，成功后标记缓存失效，页面重新读取；组件卸载后取消请求且不接收迟到结果。
5. 关闭操作有明确不可逆警告和必选确认框，发送 `acknowledge: true`。请求 Vendor 提示不得输入 User 姓名、邮箱、ID 等个人信息。
6. `src/api/attachmentTransfer.ts` 使用独立 XHR：API-02 → 原始 PUT（原 signed headers，不加 API Bearer Token）→ API-03（仅 upload_id）。只有确认成功才显示完成。确认失败保留 session，不重复上传字节。
7. 上传允许格式取 API-12 的 reference data，不把文档示例中的有限格式当作完整后端限制。

## Mock 与生成

- `scripts/generate-api.mjs` 新增 `src/mocks/workspace-fixtures.generated.json`，由仓库 OpenAPI 生成 32 个 operation 示例和验证 schema。`api:check` 同时校验新增文件。
- 原 9 个基础 fixture、正式生成客户端、合同哈希和 OpenAPI 均未修改。
- `src/mocks/workspaceHandlers.ts` / `workspaceModel.ts` / `state.ts` 提供多角色页面演示和状态流转；原 `handlers.ts` 扩展角色范围。
- 开发登录页的 Demo role 可选择 USER / Tier 1 / Tier 2 / Vendor / Manager。此选项只填入测试账号，不是正式角色切换功能；生产应用不导入此入口。
- 假账号：`user@example.com`、`tier1@example.com`、`tier2@example.com`、`vendor@example.com`、`manager@example.com`，统一假密码 `MockPass123!`。注册仍只创建 USER。
- 刷新浏览器会清空内存 Token 和 Mock 数据。跨角色演示时请在页面内 Sign out 后换账号登录，不要刷新。
- 示例包含请求人工单 5001、Vendor 协作工单 6001、逾期工单 6002。后两者不属于示例 USER，USER 不能查看。
- Mock 下载跳到 `public/mock-download.txt`，明确显示占位说明；不会声称下载了原始上传文件。真实后端模式使用 API-05 返回的下载 URL。

Mock 不模拟 MySQL 事务锁、真正自动分配、定时 SLA Job、多组织历史 Vendor 权限、完整上传 session 过期 / 清理 / 完整性安全保证。这些仍由后端实现与测试，本轮不能代替真实服务验收。

## 验证命令

在 `ITSM/frontend` 运行：

```powershell
npm run check
npm run test:api:browser
npm run test:auth:e2e
npm run test:e2e
```

- `check`：生成一致性、TypeScript、单元 / 组件测试、生产构建。
- 原 API 浏览器回归：3 条；原账户页面回归：6 条。
- D03 新业务浏览器回归：7 条，原 4 个 skip 占位已替换，另加 Manager 场景。页面测试运行 Chromium，1440×1000；工单列表 / 详情和原账户测试也含 1280×800。
- 新接口测试通过生成 SDK → Axios → MSW，验证响应结构及权限 / 工作流；32 个新 fixture 对照仓库原合同，非手写 DTO。
- 组件场景覆盖加载 / 空数据 / 503 重试 / request ID、null、Vendor 隐藏字段和不请求普通评论、401、403/404 清缓存跳离、409 冲突、422 保留评论、上传确认失败后不重复 PUT、写入锁 / 取消 / 卸载保护。
- 本轮实际最终结果见下方“最终验证记录”；不将 Mock 测试等同于 Python / MySQL / AWS 验收。

## 本地查看

1. 在本分支 `frontend` 内运行 `npm run dev`，保持终端运行。
2. `.env` 使用 `VITE_USE_MOCKS=true`；已有文件不要覆盖。修改后重启开发服务。
3. 打开终端地址（通常 `http://localhost:5173`），选择 Demo role → Use demo account → Sign in，再点左侧菜单。
4. 用 USER 新建未分配工单；页面内退出并切换 Manager 分配；再切工程师处理；切回 USER 补充 / 确认。现有 5001 可直接测试 Tier 1 升级；6001 可直接测试 Vendor 回复。
5. 接真后端时设置 `VITE_USE_MOCKS=false`，核对 API Base URL、CORS 和团队测试账号；不要将凭据放入代码或 VITE 变量。

## 截图

`docs/evidence/d03-*.png`：工单列表、创建、详情、工程师操作、Vendor 工作区、附件、管理看板、逾期列表。账户回归还更新了带业务侧栏 / 开发角色选择器的 D02 截图。

## 本轮之外的发布验收

- 真实 Python / MySQL / S3 联调（包含对象字节下载、过期链接、CORS 与多角色真实权限）。
- Docker / Nginx / AWS 部署和公开 HTTPS 环境验收。
- 后端定时任务、真实 SLA 时间边界、多 Vendor 历史权限及数据库并发不是本前端 Mock 的完成声明。
- 最终用户手册、团队报告及人工 PR 审核仍需结合真实部署结果。

## 最终验证记录

2026-09-28：

- `npm run check`：通过。生成文件一致，TypeScript 通过，**117 项单元 / 组件测试通过**，生产构建成功。
- `npm run test:api:browser`：**3 项通过**。
- `npm run test:auth:e2e`：**6 项通过**。
- `npm run test:e2e`：**7 项通过**；无跳过的业务占位测试。
- `git diff --check`：通过；修改范围仅 `frontend/`。
- 生产 JavaScript 检查未包含假密码 `MockPass123!`、Tier 1 假账号、开发角色入口文案或 Mock Vendor 名称。
- 桌面截图已生成并检查；没有部署或声称进行真实服务联调。
- 构建保留一项非阻塞体积警告：主 JavaScript 约 **721 kB / gzip 233 kB**，延续 D02 的大包提示。没有提高阈值来隐藏它；后续可单独做按路由拆包。

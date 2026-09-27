# D02 登录、注册和个人资料页交接

## 工作位置与范围

- 仓库：`ITSM`，不是旧的独立 `INFS803/frontend` 原型。
- 分支：`feature/WBS-D02-auth-pages`，从已经合并 D01 的 main `6bdcdf8` 创建。
- 所有实现改动均在 `frontend/`；后端、数据库、OpenAPI 和生成客户端不变。
- 按用户后续授权，D02 与 PR #49 反馈修复一并提交审核；是否合并 main 由团队另行决定。
- 按最新要求只做桌面网页端，不做手机专用布局或手机验收。保留普通桌面窗口缩小时的排版调整。

## 具体完成内容

| 功能 | 文件 | 完成内容 |
| --- | --- | --- |
| 登录 | `src/features/auth/LoginPage.tsx` | 邮箱/密码校验、密码显示切换、防重复提交、错误与请求编号、成功进入个人资料页；调用 API-09 |
| 注册 | `src/features/auth/RegisterPage.tsx` | 显示名称、邮箱、密码及确认密码；调用 API-08，成功返回登录并回填邮箱；不传确认密码或角色，不自动登录 |
| 个人资料 | `src/features/profile/ProfilePage.tsx` | API-10 查询、API-11 更新；仅发送改动字段；加载、错误重试、保存成功、取消修改 |
| 角色差异 | `src/features/auth/roleLabels.ts`、个人资料页 | 邮箱/角色/供应商组织只读；仅 Tier 1/2 工程师可修改 `is_available`；普通注册只创建 USER |
| 会话管理 | `src/features/auth/AuthProvider.tsx` | 登录用户状态、退出、401 过期提示、账户查询缓存清理、旧请求隔离；Token 仍仅在内存，刷新需要重新登录 |
| 页面访问控制 | `src/app/roleRoutes.tsx`、`router.tsx` | 未登录不能进入个人资料；已登录不再进入登录/注册页；可复用角色白名单守卫；403/404 页面 |
| 公共布局 | `src/components/layout/` | 品牌栏、登录外框、深色侧栏、顶部栏、退出入口；不放尚未实现的工单假入口 |
| 公共表单 | `src/components/forms/` | 共用名称/邮箱/密码规则；可用键盘操作的密码显示按钮 |
| 主题 | `src/styles/theme.ts`、`global.css` | Ant Design 统一黄色主按钮、黑色结构区、白色内容区、小圆角、清晰边框；无渐变和大面积阴影 |
| 开发演示入口 | `src/features/auth/DevDemoAccount.tsx` | 仅开发 Mock 模式显示“Use demo account”；生产构建不包含该组件或假账号密码 |
| 依赖与入口 | `package.json`、`package-lock.json`、`src/app/providers.tsx` | 固定新增 Ant Design 6.6.5、图标库 6.3.4，接入主题和会话；保留现有依赖版本 |
| 请求取消 | `src/api/auth.ts` | 登录增加可选 AbortSignal，离开页面时取消；不把迟到的登录结果写回 Token |

`/` 会进入个人资料路由，未登录时转到 `/login`。登录页面没有“记住我”、找回密码或虚构的 Token 刷新功能，因为当前合同没有这些接口。

前端角色守卫只控制页面访问和操作展示，不能替代后端权限验证。工程师/供应商的 UI 组件测试使用测试专用角色数据，未把 D01 的共享 USER Mock 擅自扩展成完整多角色后端。

## 如何在本地查看

在 `ITSM/frontend` 的终端运行：

```powershell
npm ci
# 如已有 .env，不要覆盖已有配置。
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
npm run dev
```

打开终端显示的地址，通常是 `http://localhost:5173`，保持终端运行。`npm run test:unit` 只是运行测试，不会持续启动网站。

本地 `.env` 设 `VITE_USE_MOCKS=true` 后重启开发服务，登录页点击 **Use demo account → Sign in**。演示账号仍是 `user@example.com` / `MockPass123!`，不是实际后端账号。Mock 中注册的账户和修改的数据在刷新后重置。

需要接 Python 后端时，把 `VITE_USE_MOCKS=false`，确认 `VITE_API_BASE_URL`、后端服务及 CORS，再使用后端真实的测试账户。页面已经调用正式生成客户端，但本次没有声称完成实际数据库联调。

## 测试与验证

2026-09-27 合并本地 PR #49 反馈修复后重新验证：生成一致性、TypeScript、**91 项单元/组件测试**、**6 项桌面页面测试**、**3 项 API 浏览器测试**及生产构建全部通过。此前同日 D02 的 `npm ci`、完整和仅生产依赖安全审计均通过，审计为 **0 项已知告警**；本次反馈修复没有再改依赖。现有直接依赖版本未升级，已安装的直接依赖与锁文件一致。

中断期间损坏的本地依赖和 MSW worker 已通过锁文件安装恢复；`public/mockServiceWorker.js` 最终与 main 相同，不作为 D02 修改提交。生产 JavaScript 检查未发现演示账号密码或 Mock 演示入口。

```powershell
npm run check
npm run test:api:browser
npm run test:auth:e2e
npm audit
npm audit --omit=dev
```

- `check`：32 个生成 API / 9 个基础 Mock 的一致性、TypeScript、单元/组件测试、生产构建。
- 新增组件测试：`tests/component/auth-pages.test.tsx`，18 项；覆盖表单校验、错误凭据、重复注册、注册字段限制、资料更新/取消、两级工程师开关、供应商只读资料、请求失败重试、401 清理、角色限制、会话恢复、退出后迟到请求和离页取消登录。
- 新增浏览器测试：`tests/auth-browser/auth-pages.spec.ts`，6 项；覆盖真实页面注册/登录/修改资料/退出/返回保护、错误提示、刷新清除会话、桌面视口与键盘操作、404 返回。
- API 浏览器测试：原有 2 项保留，另新增 1 项 PR #49 USER 权限回归，共 3 项；没有删除原本的接口断言。
- 原有工单、工程师、供应商、附件业务 E2E 仍是 4 个跳过的占位测试；不能把它们算作通过。
- 桌面验收视口：1440×1000 和 1280×800，Chromium。未声称验证手机或所有浏览器。

桌面截图（由浏览器测试生成，使用假数据）：

- [登录页](docs/evidence/d02-login-desktop.png)
- [注册页](docs/evidence/d02-register-desktop.png)
- [个人资料页](docs/evidence/d02-profile-desktop.png)

## 一并提交的 D01 / PR #49 反馈修复

依据《ITSM-PR49-成员D修复意见-2026-09-25.md》，在当前 D02 分支追加修复，不单独推送或创建 PR。先运行两个新回归用例，两者均失败并复现审核差异，再应用修复并通过全量验证。

| 文件 | 本次追加修改 |
| --- | --- |
| `src/mocks/handlers.ts` | API-12 克隆共享 fixture 后，为 USER 排除 `PENDING_VENDOR`，评论及附件可见性均严格限制为 `["USER_VISIBLE"]`；保留其他合法状态、基础设置及原 fixture。API-16 在查询格式校验后拒绝 USER 的 `PENDING_VENDOR` 筛选，返回统一 `403 DATA_SCOPE_DENIED` 和请求编号 |
| `tests/api/client.test.ts` | 新增 4 项 SDK → Axios → MSW 回归：USER 选项和 fixture 不变；403 错误实例/请求编号/Token 保留/不触发注销；先认证及格式校验；所有合法状态筛选正常。原分页与用户隔离用例继续保留并通过 |
| `tests/api-browser/api-foundation.spec.ts` | 新增 1 项真实浏览器 Service Worker 回归，验证上述角色选项、权限错误以及错误后的正常请求和登录状态 |
| `README.md`、本文件 | 更新 Mock 限制、修复说明及实际测试数量 |

本次没有修改后端、OpenAPI、生成客户端或 `fixtures.generated.json`，没有扩展完整工程师/供应商/附件/SLA Mock 工作流。91 项测试和 9 项浏览器测试是当前 D02 加本次修复的实际结果，不是沿用审核文档的旧数量。生产构建仍只有下文记录的非阻塞体积提示。

## 后续工作，不属于本次已完成范围

1. 工单列表、创建和详情页；后续接入评论、附件、工程师/供应商工作流、管理看板。
2. 按 `available_actions` 展示操作；Tier 1 升级成功后离开详情、清理缓存，详情 404 按不可访问处理。这是后续工单页任务，D02 不冒充已完成。
3. 使用团队实际 Python 服务/数据库验证账户接口，尤其工程师权限、供应商信息、CORS 和会话失效。
4. 完整业务 E2E、Docker/AWS/S3 联调以及最终报告证据仍需后续推进。

生产构建当前有一个非阻塞的体积提示：主 JavaScript 约 663 kB（gzip 约 219 kB），来自 React、Ant Design 与接口/状态基础。没有为隐藏提示而提高告警阈值；后续加入业务页面时可统一做按路由拆包。这不是版本冲突或构建失败。

界面组件参考：[Ant Design Form](https://ant.design/components/form/)、[主题配置](https://ant.design/docs/react/customize-theme/)。

# D01 前端接口基础交接

## 本次范围

工作位置：团队仓库 `ITSM/frontend`，当前分支 `feature/WBS-D01-openapi-client`。

本次只修改前端。`backend`、`docs/api/openapi.yaml`、`.github`、基础设施和旧的独立 `INFS803/frontend` 均不修改。不执行 commit、push 或创建 PR，由你检查后手动提交。

## 哪里修改、添加了什么

| 位置（相对于此 frontend） | 内容 |
| --- | --- |
| `package.json`、`package-lock.json` | 固定生成器为 0.99.0；安装依赖；添加生成、检查、浏览器测试命令；取消“没有测试也算通过” |
| `openapi.config.mjs`、`scripts/generate-api.mjs` | 只读取仓库 OpenAPI；可重复生成；检查生成结果是否过时；规范 Windows/Linux 换行 |
| `src/api/generated/` | 32 个正式接口函数、请求/响应类型、客户端运行代码和合同指纹；原空白 `client.ts` 被工具标准输出 `client.gen.ts` 等文件替代 |
| `src/api/types.ts` | 统一转出生成类型，不再维护手写简化版错误合同 |
| `src/api/config.ts`、`httpClient.ts` | API 地址、请求超时、Bearer Token、请求编号、401 会话失效通知 |
| `src/api/tokenStorage.ts`、`auth.ts` | 内存 Token、登录保存 Token、退出清除 Token；不虚构合同不存在的刷新/退出接口 |
| `src/api/errorHandler.ts`、`src/components/ApiErrorNotice.tsx` | 统一错误对象和可复用错误提示组件，支持请求编号和重试按钮 |
| `src/mocks/fixtures.generated.json` | 从合同提取九个基础 Mock 示例及请求校验规则；自动生成，不手改 |
| `src/mocks/handlers.ts`、`state.ts`、`validation.ts` | USER 的注册、登录、个人信息、基础选项、创建/查询工单；校验字段、分页、权限和错误返回 |
| `src/main.tsx`、`.env.example`、`public/mockServiceWorker.js` | 本地 Mock 开关；等待 Mock 就绪后加载页面；生产环境禁止启用 Mock |
| `tests/api/`、`tests/component/ApiErrorNotice.test.tsx`、`vite.config.ts` | 真实断言的合同、客户端、错误处理和组件测试 |
| `tests/api-browser/`、`playwright.api.config.ts`、`tsconfig.json` | 独立端口的 Chromium Mock 冒烟检查及配置类型检查 |
| `README.md`、本文件 | 运行方法、调用例子、范围限制、手动 PR 前检查 |

## 接下来你可以怎么写

1. 在此团队仓库的前端继续开发；旧原型保留作参考，暂时不要整包覆盖新仓库。
2. 页面/功能代码写到 `src/features`、`src/components` 等对应位置；调用 `src/api/generated/sdk.gen.ts`，直接使用生成类型。
3. 下一步把登录页面和认证 Provider 接到 `login()`、`logout()`、`onUnauthorized()`；会话失效时清除用户信息/查询缓存并跳回登录页。
4. 接工单列表、创建和详情页面；在对应测试中加实际操作及断言。基础 Mock 仅 USER，工程师/主管/Vendor 等需按后续任务扩展。
5. 后端接口到齐后关闭 Mock，执行真实 Python 后端联调；Mock 通过不等于后端联调通过。

## 先理解这些边界

- 这次完成的是接口基础，不是登录、工单页面的全部业务。首页保留团队原始占位页，旧原型的黄黑主题没有在这里迁移。
- 正式 SDK 覆盖 32 个接口；基础 Mock 只接 API-01、08–12、15–17 九个。其余请求本地失败，不会偷偷调用后端。
- Mock 可注册额外 USER 并验证各自工单隔离；模拟账号/密码只是开发内存数据，不能当作生产认证方案。
- Token 仅在内存里，刷新页面后需重新登录。没有真实 JWT 校验、刷新 Token 或服务端退出。
- 工单创建采用“没有合适工程师 → UNASSIGNED”的固定分支；没有重写后端的分配、SLA 或定时逻辑。
- 原有四个业务 Playwright 文件仍为跳过的占位测试；新增两个浏览器测试验证接口基础，不代表四角色全流程完成。
- 尚未进行真实后端、S3 和 Docker 部署验证。

## 需要团队知晓的合同问题

`LoginData.access_token` 在 v1.1 中既为登录响应必填字段，又标记了 `writeOnly`。默认生成会删除返回类型中的 Token。本次在前端生成配置关闭 read/write 拆分，保留合同显式字段，附测试保护；没有改 OpenAPI。后续请与 B 成员确认该注解，再决定是否恢复生成器默认行为。

## 本地验证和手动 PR

本次本地验证结果（2026-09-09）：

- 生成文件一致性检查、TypeScript 检查、生产构建通过。
- 66 项 Vitest 测试通过：合同 36 项、客户端/Mock 15 项、错误/开关 13 项、组件 2 项。
- 2 项 Chromium 浏览器 Mock 冒烟检查通过；冷缓存启动也通过。
- `git diff --check` 通过；修改和新增路径全部在团队仓库 `frontend/`。
- 生产 JavaScript 产物中未发现本次 Mock 账号、假 Token 标记或 Mock 启动模块；静态 MSW worker 文件存在不代表生产会启用它。

在此文件所在的 `frontend` 目录运行：

```powershell
npm ci
npm run check
npm run test:api:browser
```

开发页面：没有 `.env` 时复制 `.env.example` 为 `.env`（已有则只检查其中配置，不覆盖），再运行 `npm run dev`。测试执行完退出是正常的；想打开网页必须保持开发服务器运行。

GitHub Desktop 手动提交前，确认当前仓库是 `ITSM`、分支是 `feature/WBS-D01-openapi-client`，Changed files 全部在 `frontend/`。生成源码和 `package-lock.json` 要提交；`node_modules`、`dist`、`.env`、测试报告不要提交。检查完再自行 commit、push、创建 PR；不要直接提交到 `main`。

# D01 前端接口基础交接

## 本次范围

工作位置：团队仓库 `ITSM/frontend`，当前分支 `feature/WBS-D01-openapi-client`。

D01 自己的实现改动只在前端。本次按你的授权把 main `6736508` 合入 D01，因此包含团队在后端、OpenAPI、`.github` 和基础设施的既有更新，但没有自行改写这些文件，也没有修改旧的独立 `INFS803/frontend`。同步工作保存为本地合并提交，不推送、不创建 PR；main 分支指针保持不变。

## 2026-09-24：同步 main 与最新合同（当前状态）

以 D01 `1db9797` 为起点，合入本地 main `6736508`。该 main 包含工作流 P1 修复以及 B/C 共用 TicketDetail 组装器的更新。采用合并提交保留双方历史，没有 rebase、强推或直接提交到 main。

| 位置 | 本次处理 |
| --- | --- |
| `package.json`、`package-lock.json` | 解决两处文件冲突；保留已验证的 D01 完整依赖集合、main 的共享版本和安全覆盖规则；未重新升级工具版本 |
| `openapi.config.mjs` | 删除旧 `readWrite: false` 兼容开关，恢复生成器默认读写处理 |
| `src/api/generated/` | 根据 main 合同重新生成 SDK、类型、类型导出和合同指纹；Token 仍是响应必填字段，登录/注册密码进入生成的 Writable 请求类型 |
| `src/api/types.ts`、`auth.ts`、`src/mocks/handlers.ts` | 输入类型直接从生成操作的 `body` 派生，保留登录/注册密码字段；不手写重复的 DTO |
| `tests/api/contract.test.ts` | 新增 Token 可读/必填、升级后空动作两项断言；补登录/注册写入类型断言 |
| `tests/api/client.test.ts` | 新增测试专用升级成功 → GET 404 场景，验证空动作、错误信息和 Token 保留；不把它冒充完整工程师 Mock |
| `README.md`、本文件 | 更新 Token 问题已解决、CI 已移除、同步结果和详情页后续要求 |

两项后端合同修改的处理结果：

1. `LoginData.access_token.writeOnly` 已由后端删除。前端不再需要全局禁用读写拆分；密码的 `writeOnly` 是正确标记，因此使用 `src/api/types.ts` 中从 SDK 派生的输入别名。
2. `API25Success` 的 `available_actions` 已变为 `[]`。合同指纹已更新，并有明确断言防止回退；后续 Tier 1 详情页必须在升级成功后离开详情页，清理旧详情缓存并刷新列表，再次 GET 404 时显示无访问权限/不可用提示并返回列表。不要注销登录，也不要在全局拦截器中对所有 404 跳转。D01 仅验证接口层行为，尚未实现页面跳转。

合并后本地验证：

- `npm ci`、完整依赖树检查成功；无 Node engine 或 peer dependency 冲突。
- 共享的 16 项直接依赖仍与 main 一致；本机 Node 22.23.3、npm 10.9.9 未再次变更。
- `npm run check`：32 个接口、9 个基础 Mock 生成一致性检查、TypeScript、**69 项**单元/组件测试和生产构建通过。
- `npm run test:api:browser`：**2 项**浏览器测试通过。
- `npm audit` 与 `npm audit --omit=dev`：均为 **0 项已知告警**。
- 同步后的后端 **403 项**单元/合同测试通过（使用已有隔离 Python 环境）；有一条测试库弃用提醒，没有测试失败。
- 未执行真实 MySQL、S3、AWS 或部署验证；Mock 测试不等于页面与真实后端的业务验收。

下面保留此前依赖对齐与安全修复的历史记录；当前同步状态以上述结果为准。

## 2026-09-24：仅对齐 main 依赖与本机环境

此前按你的选择，仅对齐依赖，没有把整个 main 合入 D01。当时参考 main `5ff9efb`，后端、OpenAPI、GitHub Actions 文件未随该阶段同步；这不是本次完成后的分支状态。

- `package.json`、`package-lock.json`：共享直接依赖的声明范围与 main 一致，实际安装的 16 项共享直接依赖版本也逐项核对一致。主要工具为 Vite 8.2.2、React 插件 6.1.1、Vitest 5.0.1、jsdom 30.0.1、jest-dom 7.0.1。
- 保留 D01 的生成器 0.99.0、Ajv、YAML、Token/错误处理、Mock 和完整检查脚本，没有退回 main 的空白接口基础或允许零测试通过的配置。
- D01 额外声明的 `@types/node` 从 22.10.0 调整为兼容 Vite 8 的 22.19.0。它是开发时的类型包，不是 Node 本体。
- 本机系统级 Node 已从 22.19.0 升级到官方 22.23.3，随安装包带入 npm 10.9.9；官网安装包 SHA256 与 Windows 签名均已验证。该系统安装也会被电脑上其他使用同一路径的项目使用。
- 新增 `.nvmrc` 记录选用的 Node 版本，并收紧 `engines.node` 到新版 jsdom/Vitest 支持的范围。Windows MSI 安装无需使用 nvm；`.nvmrc` 是团队环境版本记录，不会自行下载 Node。
- `README.md` 更新 Node、依赖复现和本地检查说明；`tests/api/contract.test.ts` 只修改了一条测试的名称，移除依赖旧 CI 状态的表述，断言不变。

版本对齐阶段的实际验证（后续安全修复见下一节）：

- 新环境下 `npm ci` 成功，无依赖冲突及 Node engine 警告；`npm ls --depth=0` 通过。
- `npm run check` 通过：32 个接口/9 个 Mock 的生成一致性检查、TypeScript、66 项单元/组件测试、Vite 8 生产构建。
- `npm run test:api:browser` 的 2 项浏览器测试通过；现有 MSW worker 与安装的 MSW 版本一致。
- 本次没有改 API 合同，生成源码也没有变化。以后真正合并 main 的合同变动时，再重新生成。
- main 原始锁文件的 `npm audit` 为 0 项告警；D01 的生产依赖检查 `npm audit --omit=dev` 也是 0 项告警。
- 当时 D01 完整开发依赖审计有 6 项包级告警（4 high、2 moderate），来自生成器依赖链中的 js-yaml 4.2.0，以及 D01 固定的 Ajv 8.17.1、yaml 2.8.1。4 项 high 包级计数包含同一 js-yaml 问题向上游的传播，不表示有 4 个独立的浏览器运行时漏洞。当前 Ajv 未启用公告所述的 `$data` 选项，但这不等于可以忽略依赖更新。
- 版本对齐阶段没有运行 `npm audit fix`，也没有降级固定生成器。这些告警现已在下面的独立安全修复中处理；仍不要对未经审查的外部 YAML 运行生成器。

现在关闭并重新打开 VS Code 终端，运行 `node -v`、`npm -v`，应分别显示 `v22.23.3`、`10.9.9`。开发方式仍是 `npm run dev`，后续还原依赖仍使用 `npm ci`。

上述依赖对齐与下述安全修复后来已保存到 D01 的 `1db9797` 提交。本机 Node 安装不属于 Git 提交内容。

## 2026-09-24：开发依赖安全告警修复（历史记录）

该阶段仅在前端做了以下修复，没有合并 main、修改后端或改动 OpenAPI：

| 文件 | 本次修复 |
| --- | --- |
| `package.json` | Ajv 8.17.1 → 8.20.0；yaml 2.8.1 → 2.9.1；对 `@hey-api/json-schema-ref-parser@1.4.4` 添加仅针对 js-yaml 的 4.3.2 覆盖规则 |
| `package-lock.json` | 记录三个修复版本、下载地址和完整性信息，供 `npm ci` 复现 |
| `README.md`、本文件 | 说明覆盖规则的原因、移除条件和验证结果 |

生成器仍固定为 `@hey-api/openapi-ts@0.99.0`。查询时其最新版本以及最新 parser 仍固定依赖有告警的 js-yaml 4.2.0，因此没有盲目升级或降级生成器，而是对该依赖链进行小范围覆盖。这不是忽略告警，而是实际安装修复版本。未来上游 parser 修复后，应重新检查这条带版本限制的规则并移除不再需要的覆盖，然后重跑下列验证。

本次重新验证结果：

- `npm ci` 成功；248 个本机已安装包的版本均与锁文件一致。
- `npm ls --all --json` 成功，无缺失或无效依赖；与 main 共用的 16 项直接依赖锁定版本仍一致。
- 完整 `npm audit`：**0 项已知告警**（修复前为 6）；`npm audit --omit=dev` 也是 0。该结果对应本次查询的安全数据库，不代表以后无需再审计。
- `npm run check` 通过：32 个接口、9 个 Mock 的生成一致性；TypeScript；66 项单元/组件测试；生产构建。
- `npm run test:api:browser`：2 项浏览器测试通过。
- API 生成源码、Mock 生成文件及合同内容均未变化；没有使用 `npm audit fix --force`。

该阶段修改后来已保存至 `1db9797`。它相对旧 D01 的较大锁文件差异同时包含工具版本对齐，不全是三个安全修复包造成的。

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

## Token 合同问题已解决

旧合同曾把 `LoginData.access_token` 同时标成响应必填和 `writeOnly`。最新 main 已修复此注解，D01 本次已恢复默认生成行为并重新生成。Token 可读性、密码请求字段和操作类型均有回归保护；不再需要等待 B 确认旧问题。

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

本次同步已保存为本地合并提交。准备 PR 时，确认当前仓库是 `ITSM`、分支是 `feature/WBS-D01-openapi-client`，PR 的 base 是 `main`；D01 相对 main 的实现差异应全部在 `frontend/`。合并提交历史中包含 main 的后端变化是正常的，不应把它误认为 D01 自行修改了后端。生成源码和 `package-lock.json` 要提交；`node_modules`、`dist`、`.env`、测试报告不要提交。是否推送和创建 PR，等待你另行确认；不要直接提交到 `main`。

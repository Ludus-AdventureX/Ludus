# 22. 合同生成与安全实施方案

## 文档状态

- 状态：canonical / accepted
- 生效日期：2026-07-21（星期二）
- 关联变更：`docs/contract-changes/CCR-20260721-003.md`

本文件是 `06-data-model.md` 与 `10-api-and-events.md` 的实施桥梁，定义 Python 运行时 schema、OpenAPI、TypeScript 生成物、认证 session、CSRF、BYOK、SSRF、限流和文件处理的唯一实施合同。它不创建第二套领域语义；冲突时先修订 06/10 和 CCR，再重新生成。

## 单一合同链

```text
06-data-model.md / 10-api-and-events.md
        ↓ Contract Lead 实现
FastAPI + Pydantic 2 schemas
        ↓ scripts/export_openapi.py
packages/contracts/openapi.json
        ↓ openapi-typescript
packages/contracts/src/types.gen.ts
        ↓ openapi-fetch typed client
apps/web/lib/api/client.ts
```

权威层级：

1. `06-data-model.md`：领域语义、状态、不可变性、作用域；
2. `10-api-and-events.md`：HTTP/SSE 路径、错误码、信封与幂等；
3. Pydantic schema：唯一运行时 wire schema，由 Contract Lead 维护；
4. `openapi.json` 与 `types.gen.ts`：只读生成物；
5. Web hooks/view model：只能组合生成类型，不得重新声明同义 DTO。

## 目标文件

```text
decision-lab/
├── .gitignore
├── packages/contracts/
│   ├── package.json
│   ├── openapi.json
│   ├── src/types.gen.ts
│   └── src/index.ts
├── scripts/export_openapi.py
├── scripts/generate_contracts.ps1
├── scripts/verify_contracts.py
├── scripts/scan_secrets.ps1
├── services/api/app/**/schemas.py
├── services/api/app/security/
│   ├── csrf.py
│   ├── safe_http.py
│   ├── rate_limits.py
│   ├── content.py
│   └── headers.py
└── apps/web/lib/api/
    ├── client.ts
    ├── errors.ts
    └── queryKeys.ts
```

## 固定工具与命令

- OpenAPI 在不连接外部 Provider 的条件下离线导出并稳定排序。
- TypeScript 使用 lockfile 固定的 `openapi-typescript` 生成。
- 请求客户端只使用 `openapi-fetch`；禁止第二个自动 client generator。
- SSE 的 `AnalysisEvent` 从生成类型导入，解析器只负责 framing、重连和 `Last-Event-ID`。

```powershell
uv run --project services/api python scripts/export_openapi.py
pnpm --dir packages/contracts generate
powershell -ExecutionPolicy Bypass -File scripts/generate_contracts.ps1 -Check
```

`-Check` 必须在临时目录重新生成并比较；有差异返回非零。CI、集成门和发布检查均执行。

## Contract change request

任何字段、状态、错误码、API、事件或 schema 变化必须从 `templates/contract-change-request.md` 创建 CCR，至少包含业务原因、受影响合同、兼容性、迁移、fixture、生成物、测试、回滚和接受结论。未接受的 CCR 不得通过兼容层、fixture 或别名绕过。

## 生成物 ownership

- Contract Lead：Pydantic schema、OpenAPI 导出、生成配置、迁移合并；
- Web/UX：typed hooks、query keys、UI view model；不得修改生成物；
- 其他 owner：只能消费生成类型；缺口提交 CCR；
- QA/Release：执行 drift、安全和 schema 检查，不直接修 canonical source。

## UserSession 与 Workspace 授权

- JWT 只保存 `sub/session_id/iat/exp` 等最小 claim；`session_id` 必须解析到 `UserSession`。
- 每次请求验证 session 未撤销、未过期且 tokenVersion 有效；logout 原子设置 `revokedAt` 后清 Cookie。
- Workspace 权限每次从 `WorkspaceMembership` 读取；role 只为 `owner | member`，capability 只为 `contribute | review | sign | manage_connectors`。
- owner 默认拥有全部 capability；member 只拥有显式授予项。
- sign 命令在签署事务内再次验证活动 session、membership 与 `sign`，不能只依赖路由前置检查。
- 未授权跨 Workspace 资源统一返回 404；认证失败使用 401，已认证但缺 capability 使用 403。

## CSRF 合同

`GET /api/auth/csrf` 必须生成随机 token，同时设置同源可读 CSRF cookie 并在 body 返回 token。Cookie 会话的所有 mutation（包括 register/login/logout）必须同时满足：

- `Origin` 精确匹配 `WEB_ORIGIN`；没有 Origin 时校验同源 `Referer`；
- CSRF cookie 与 `X-CSRF-Token` 做常量时间比较；
- token 与 session 生命周期解耦，但 logout/高风险认证变化后轮换；
- 上传、连接器、Charter、Run、图、Signoff、Decision 和 Review 均适用；
- 失败返回 `CSRF_VALIDATION_FAILED`，不泄露比较细节。

`SameSite=Lax`、CORS 和 JSON Content-Type 只是纵深防御，不能替代 CSRF。非浏览器 Bearer 调用使用独立认证依赖，不与 Cookie 分支混淆。

## BYOK 密钥加密与轮换

P0 锁定 AES-256-GCM，不允许“任意库默认加密”或可替换算法漂移：

- `CONNECTOR_MASTER_KEY` 的活动版本必须提供 32 字节随机 key material；配置只保存 key reference/version，不进入数据库和日志。
- 每次加密生成独立随机 96-bit nonce；禁止重复 nonce。
- AAD 规范化为 `workspaceId + connectorId + provider + credentialSchemaVersion`，防止密文跨对象搬移。
- 数据库保存 ciphertext、authentication tag、nonce、masterKeyVersion、credentialMask、createdAt/rotatedAt；不保存明文。
- 解密前先验证 Workspace/Connector/Provider 与 AAD 一致；认证失败统一返回不可区分错误。
- Key 更新生成新密文与审计事件；旧密文不进入响应、SSE、fixture 或日志。

主密钥轮换流程：

1. 注册新 master key version，旧版本临时保持 read-only 解密；
2. 后台按 Workspace/connector 小批量解密并用新版本重新加密；
3. 每条记录写 re-encryption audit，不记录明文或原 ciphertext；
4. 全量校验成功后禁止旧版本新增加密；
5. 观察窗口结束后在外部 secret manager 停用旧 key；失败批次可重试，不静默丢 credential。

## SSRF、DNS pinning 与远程内容

任何服务器端 URL 请求在首次请求和每次重定向后都必须：

- 只允许 `https`；明确的本地开发 Provider endpoint 可由非生产配置允许 `http`；
- 拒绝 userinfo、IP 字面量绕过、非常规端口、过长 host/URL 和超长重定向链；
- 解析 A/AAAA，阻断 loopback、link-local、private、multicast、unspecified、保留地址、ULA 和云 metadata；
- 将本次连接 pin 到已验证 IP；不得验证 hostname 后再让 HTTP 客户端重新解析到其他地址；
- 连接 pinned IP 时保留原始 hostname 作为 TLS SNI 与 HTTP Host，并验证证书属于原始 hostname；禁止为了 pinning 关闭证书验证；
- 重定向后重新规范化 URL、重新解析/校验/pin，不能继承前一 host 的信任；
- 设置 connect/read/total wall-clock、响应体、流式字节数、解压后大小和内容类型上限；
- 基础抓取只消费已审核搜索结果或固定 Provider endpoint；用户不能提交任意 crawl URL。

DNS rebinding 测试必须覆盖“第一次为公网、第二次为私网”、CNAME 链、IPv4-mapped IPv6、redirect 到 metadata 和 Host/SNI 错配。失败返回 `UNSAFE_REMOTE_URL`；审计只保存规范化 host、原因码、目标 IP 分类和 request hash，不保存敏感 query/credential。

## Postgres-backed 限流与成本保护

P0 限流状态必须由 Postgres 提供，禁止仅使用单进程内存计数器；Web/API/Worker 多进程或重启后语义必须一致。

至少实现：

- 登录：IP + 规范化账号双维滑动窗口；
- mutation：user + Workspace burst；
- 每个 Case 最多一条活动 formal AnalysisRun 的部分唯一约束；
- model/connector 调用数、来源数、token/费用和 wall-clock budget；
- Signoff nonce 轮换和签署尝试限制；
- 原子 `INSERT ... ON CONFLICT`/行锁或等价数据库计数，不依赖先读后写；
- 过期 bucket 可批量归档/清理，但清理失败不得放宽限流。

超限返回 `REQUEST_RATE_LIMITED` 或 connector budget 错误，并只返回安全的 `retryAfter`。provider 自身 429 与 Ludus 本地限流必须能区分。

## 上传、TXT/Markdown 与内容清洗

P0 允许 PDF、TXT、Markdown：

- PDF：扩展名、MIME、`%PDF-` 文件签名、大小、页数、解压/对象复杂度和解析结果联合校验；
- TXT/Markdown：没有可靠 magic bytes，不得宣称用 magic bytes 验证；要求扩展名/MIME 合理、UTF-8 或 UTF-8 BOM 可解码、拒绝 NUL 与高比例控制字符、限制总字节/最长行/文本比例；
- 文件名只作显示，服务端 UUID 决定存储路径；拒绝路径分隔符、控制字符、双扩展混淆；
- 原文先进入 RawArtifact，解析输出保留 hash/版本并标记 `UNTRUSTED_EVIDENCE`；
- Markdown 解析禁用原始 HTML 或使用严格 allowlist sanitizer；HTML 报告统一转义用户/模型内容；
- ArtifactStore 路径必须 Workspace-scoped，下载始终重新授权。

## 响应头与日志

P0 至少配置 CSP、`X-Content-Type-Options: nosniff`、Referrer-Policy、Permissions-Policy、frame 限制、HSTS（生产 HTTPS）和安全缓存策略。日志使用字段 allowlist；禁止记录 Cookie、Authorization、CSRF token、BYOK、Signoff nonce、完整远程 query 和未清洗正文。

## Git 与 secret 门

根 `.gitignore` 必须在第一次 `git add .` 前存在，并至少忽略：

```text
.env
.env.*
!.env.example
*.pem
*.key
*.p12
*.pfx
.auth/
auth.json
node_modules/
.venv/
__pycache__/
.next/
playwright-report/
test-results/
artifacts/
```

CI 和发布前运行 secret scan，覆盖 Git tracked files、构建上下文、日志和 fixture。发现真实 secret 时停止重复输出，轮换后再继续；不能只从最新提交删除而保留在历史/构建产物中。

## 自动化验收

必须新增并通过：

- OpenAPI regenerate clean diff、06/10/26 shape drift；
- Web 构建中禁止手写 API response DTO；
- session revocation、tokenVersion、跨 Workspace 和 capability tests；
- CSRF 缺失、错误、跨 Origin、login CSRF 和正常请求；
- AES-GCM nonce/AAD/tag、错误 key version、rotation 与脱敏；
- SSRF localhost/RFC1918/IPv6/metadata/DNS rebinding/redirect/Host/SNI；
- Postgres 跨进程限流、重启一致性和原子竞争；
- PDF 伪装、TXT/Markdown 编码/NUL/控制字符、压缩炸弹、路径穿越；
- 安全头、HTML/Markdown 清洗与日志 secret scan。

## 完成定义

- Web 只消费生成 types/client；
- `generate_contracts.ps1 -Check` clean；
- schema/API 变更有 accepted CCR；
- UserSession/WorkspaceMembership/sign capability 由代码执行；
- AES-256-GCM、DNS pinning、Postgres 限流和文本上传策略有实现与负例；
- `.gitignore` 在首次 staging 前生效，secret scan 无真实泄露；
- Agent manifest 的 Task scope 与本合同和详细计划一致。

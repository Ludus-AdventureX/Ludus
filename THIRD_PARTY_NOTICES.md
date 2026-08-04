# THIRD_PARTY_NOTICES.md

本文件是 Ludus（decision-lab）的第三方材料发布清单，依据 `docs/product-plan/21-existing-asset-reuse-and-conversion.md` 的逐文件转换账本与 `LICENSING.md` 第 4 节 Gate 2 建立。

本文件记录**来源与许可**，不是把参考项目变成运行时依赖的手段。Ludus 生产运行时只读取自身代码、数据库、已发布 `method-packs` 和经授权的外部输入；三个参考目录不得被复制进镜像、fixture 或部署卷。

本仓库自身代码按根目录 `LICENSE`（PolyForm Noncommercial 1.0.0）授权；第三方材料不因进入本仓库而改变其自身许可。

---

## 1. Hermes Agent（MIT）

- **来源目录**：`hermes-agent-hermes-hermes-a8a19433/`（工作区参考副本）
- **本地版本**：v0.6.0（`pyproject.toml`；仓库含 RELEASE_v0.2.0 至 RELEASE_v0.6.0 记录）
- **许可**：MIT License，Copyright (c) 2025 Nous Research（源仓库 `LICENSE`）
- **转换方式**（按 21 号文档逐文件判定）：
  - **Extract & adapt**（保留 MIT 署名、记录精确函数来源、补齐 Ludus 契约测试）：
    - `tools/registry.py` → `services/api/app/agents/tool_registry.py`（`ToolEntry`、注册/定义/缓存、统一 dispatch 的纯机制）
    - `agent/skill_utils.py` → `services/api/app/methods/source_validator.py`、`loader.py`（`yaml_load`、`parse_frontmatter` 等纯解析函数）
    - `tools/mcp_tool.py` 的纯函数 → `services/api/app/agents/tool_schema.py`、`connectors/registry.py`（`_build_safe_env`、`_sanitize_error`、schema 规范化等经测试纯函数）
  - **Reimplement from verified behavior**（不复制源码，按已核验行为在 Ludus 架构中重写）：
    - `tools/delegate_tool.py` → `services/api/app/agents/runner.py`、`context.py`、`budget.py`
    - `agent/context_compressor.py` → `services/api/app/agents/context.py`
    - `tools/mixture_of_agents_tool.py` → 仅借鉴并行研究与失败隔离模式，不复制实现
  - **Do not use**：`run_agent.py`、CLI、Gateway、`hermes_state.py`（通用单体循环与 SQLite 会话不进入 Ludus）
- **发布要求**：任何实质代码复用必须随发布物保留完整 MIT 文本与来源署名；本仓库目标文件中已保留 `Behavior reimplementation (not a source copy) of the Hermes ...` 等来源注释。

## 2. Open WebUI 0.10.2（多许可）

- **来源目录**：`open-webui-0.10.2/`（工作区参考副本）
- **本地版本**：0.10.2（`package.json`）
- **许可**：多许可边界（源仓库 `LICENSE`、`LICENSE_NOTICE`、`LICENSE_HISTORY` 三个文件）：
  - `LICENSE_NOTICE`：仓库按贡献日期与来源分属多许可；commit `a76068d69cd59568b920dfab85dc573dbbb8f131` 之前的代码按 MIT（见 LICENSE_HISTORY）
  - `LICENSE_HISTORY`：commit `60d84a3aae9802339705826e9095e272e3c83623` 之前创建的材料：Copyright (c) 2023-2025 Timothy Jaeryang Baek，All rights reserved（Open WebUI License，含品牌限制）
  - `LICENSE`：Open WebUI License（Copyright (c) 2023- Open WebUI Inc. [Created by Timothy Jaeryang Baek]），含品牌使用限制
- **转换方式**：因单个本地文件的提交归属未逐文件证明，P0 统一按最严格边界 **Reimplement from verified behavior**，不复制 Svelte、样式、图标、文案、品牌或 MCP client：
  - `src/lib/components/chat/Chat.svelte` → `apps/web/components/chat/MessageList.tsx`、`analysis/AnalysisProgress.tsx`
  - `src/lib/components/common/ToolCallDisplay.svelte` → `apps/web/components/analysis/ToolCallDisplay.tsx`
  - `src/lib/components/chat/Messages/Citations.svelte` → `apps/web/components/quality/EvidenceDrawer.tsx`、`analysis/ReportSectionViewer.tsx`
  - `src/lib/components/chat/Messages/ResponseMessage/TaskList.svelte` → `apps/web/components/analysis/AgentTaskList.tsx`
  - `backend/open_webui/events.py` → `services/api/app/analyses/schemas.py`、`repository.py`、`routes.py`
  - `backend/open_webui/utils/mcp/client.py` → 仅 P1 参考（生命周期/超时/断开行为），P0 禁止远程 MCP
- **发布要求**：任何源码复制必须先完成提交级 provenance 与法律复核；本计划默认禁止复制。`THIRD_PARTY_NOTICES.md` 记录版本与三个许可文件。

## 3. `探讨`（产品方控制的内部来源）

- **来源目录**：`探讨/`（工作区参考副本，产品方控制的内部工作区）
- **许可状态**：根目录未发现统一 `LICENSE`；视为产品方控制的内部来源，不能从子目录第三方许可证推断整个目录许可
- **转换方式**：仅在所有权已确认的范围内 **Extract & adapt**（方法内容编译进 `ways/hardtech-market-direction/1.1.0/**`）；运行框架机制按 21 号文档映射到 `services/api/app/**` 与 `apps/web/**`
- **来源记录**：`ways/hardtech-market-direction/1.1.0/SOURCES.md` 记录 Skill 路径、frontmatter 版本与编译贡献；`CAPABILITY-MAP.md` 记录 31 个 Skill 的全量处置（13 直接编译 / 7 合同吸收 / 8 延后 / 1 仅参考 / 2 禁用）
- **排除项**：`探讨/.env`、`探讨/auth.json` MUST NOT 被读取、复制、打包、记录、提交或写入 fixture；不进入本清单的发布范围

## 4. 依赖树

运行时依赖（Python：`services/api/pyproject.toml`；Node：`package.json`、`apps/web/package.json`、`packages/contracts/package.json`）各自的许可证以各包发布元数据为准，随包管理器锁文件分发。本清单不逐包复制许可证文本。

### 4.1 Vendored 运行时资产

- `apps/web/app/xyflow.css` — 逐字节 vendored 自 `@xyflow/react@12.11.2`（MIT License，xyflow GmbH）的 `dist/style.css`。用途：因果沙盘/因子沙盘图形画布的基础样式，由 `apps/web/app/layout.tsx` 单点引入；组件不直接 import node_modules CSS 路径（该路径破坏 vitest 的 PostCSS 链）。锁定版本与 `pnpm-lock.yaml` 中 `@xyflow/react` 一致；升级该依赖时必须同步替换本文件并更新此条目。

## 5. CI 与发布扫描要求

- CI 应扫描镜像和产物，确保不存在 `open-webui-0.10.2/`、`hermes-agent-hermes-hermes-a8a19433/`、`探讨/.env`、`探讨/auth.json` 或参考目录源码。
- 生产镜像、fixture、日志和 Git staged files 不得包含三个参考目录、`.env`、`auth.json`、原始密钥或 Open WebUI 品牌资产。
- 任何新的第三方材料进入仓库前，必须先在此文件登记来源、版本、许可证与精确使用位置。

## 6. 维护与复核

- 本文件与 `docs/product-plan/21-existing-asset-reuse-and-conversion.md`、`LICENSING.md` 保持同步；许可策略变更必须同时更新本文件。
- 公开发布前由产品方完成本清单复核（Gate 2 收口）。

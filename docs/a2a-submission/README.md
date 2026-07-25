# Ludus Five-Lens Research Agent — PandaAI 赛道提交说明

> AdventureX 2026 · Build the Next AI Trader · 方向⑤ Multi-Agent Workflow

## 提交信息速查

| 提交项 | 内容 |
|---|---|
| Agent 名称 | Ludus Five-Lens Research Agent |
| 简介 | 五重战略透镜 AI 投研团队：自然语言任务 → 多 Agent 协作 → 可追溯投研报告 |
| 团队信息 | （填写：团队名 / 成员 / 联系方式） |
| Agent Card URL | `https://<你的域名>/.well-known/agent-card.json`（部署后填入实际域名） |
| 服务地址与鉴权 | `POST https://<你的域名>/a2a`，A2A JSON-RPC；公开端点无需鉴权 |
| 底座模型 | DeepSeek（官方提供的 API Token，OpenAI 兼容端点） |
| 数据 Skills | panda_data SDK：get_stock_daily / get_index_daily / get_factor / get_fina_reports / get_trade_cal |
| 投研 Skills | five_lens_research / market_data_analysis / risk_premortem（Agent Card 内声明） |
| 开源仓库 | （填写：GitHub 仓库链接，或邮件提交至 code@pandaai.online） |
| 示例任务 | 见 `examples.md`（3 个示例任务 + 预期输出） |

## 一句话介绍

一支由 **Planner、Data Agent、五个战略透镜 Agent（Porter / Counterparty / Pre-Mortem / Scenario / Meadows）、Critic 行为门控、Report Agent** 组成的 AI 投研团队：接收一句自然语言投研任务，自主取数、按固定装配顺序完成五重视角分析，产出全程可追溯、带强制风险提示的结构化投研报告。

## 为什么与众不同

- **不是聊天，是流水线**：每个 Lens 有已发布的行为契约（例如 Pre-Mortem 必须给出"三视角 × 至少五个失败原因 × 前三大风险的预防/应急/检测指标"），模型输出必须通过确定性行为门控校验，未通过将被降级（degraded）并在报告中如实披露——**模型不能糊弄门控**。
- **证据纪律**：所有市场数据经 Data Agent 规范化为带 `evidenceId` 的证据条目，Lens 只能引用账本内的证据 ID，报告可逐条回溯数据来源。
- **对抗性视角**：Counterparty Lens 分析对手盘反应矩阵，Pre-Mortem Lens 假定决策已失败进行归因预演——这两个"红队" Lens 是常规投研 Agent 缺失的。

## 使用场景

| 场景 | 典型任务 | 主力 Lens |
|---|---|---|
| 个股投研审查 | "分析某股未来两年的竞争格局与下行风险，增持还是回避？" | Porter + Counterparty |
| 指数/行业情景推演 | "对某指数做 12 个月情景推演，给出可监控的早期信号" | Scenario |
| 持仓风险预演 | "假设 18 个月后这个持仓决策彻底失败了，最可能的原因是什么？" | Pre-Mortem |
| 系统性归因 | "某赛道为什么卷不动了？干预点在哪？" | Meadows |
| 完整决策审查 | 以上任意组合——五 Lens 全量串行，一次任务产出完整报告 | 全部 |

适用边界：本 Agent 定位为**投研决策审查**，不是高频信号生成器、不是回测引擎、不输出价格预测；产出物是带证据引用、可被人类审阅推翻的结构化分析。

## 架构

```
自然语言任务 (A2A message/send)
        │
   ┌────▼────┐
   │ Planner │ 决策问题框定：≥2 个互斥选项 / 时间窗 / 数据需求
   └────┬────┘
   ┌────▼────────┐
   │ Data Agent  │ PandaAI 数据 Skills → 规范化证据账本 (evidenceIds)
   └────┬────────┘
        │  canonical 装配顺序（严格串行，上游产出注入下游）
   ┌────▼─────────────────────────────────────────────┐
   │ Porter → Counterparty → Pre-Mortem → Scenario →  │
   │ Meadows        （每个 Lens：模型调用 → 行为门控   │
   │                  → 失败回喂 findings 重试一次     │
   │                  → 仍失败则 degraded 并继续）     │
   └────┬─────────────────────────────────────────────┘
   ┌────▼────────┐
   │ Report Agent│ 执行摘要 + 五 Lens 明细 + 数据来源 + 强制风险提示
   └─────────────┘
```

- 底座模型：DeepSeek（`MODEL_*` 环境变量，OpenAI 兼容端点，structured JSON 输出）。
- 预算护栏：`A2A_TASK_BUDGET_SECONDS`（默认 900s）+ 模型调用次数硬上限；超时跳过剩余 Lens 返回部分报告，**总响应时间恒 < 20 分钟**。
- 过程可解释：每个阶段开始/结束通过 A2A `TaskStatusUpdate` 实时推送（支持 `message/stream` SSE）。

## A2A 接入信息

| 项目 | 值 |
|---|---|
| Agent Card | `{A2A_PUBLIC_URL}/.well-known/agent-card.json` |
| JSON-RPC 端点 | `POST {A2A_PUBLIC_URL}/a2a` |
| 协议方法 | `message/send`、`message/stream`（SSE）、`tasks/get`、`tasks/cancel` |
| 输入/输出 | `text/plain`（自然语言任务 → Markdown 报告 artifact） |
| 鉴权 | 公开只读端点，无需鉴权（Agent 自身不暴露任何平台数据写路径） |
| streaming | true |

## Skills 清单

**Agent 对外 Skills（Agent Card 中声明）**

| skill | 说明 |
|---|---|
| `five_lens_research` | 完整五 Lens 多智能体投研工作流 |
| `market_data_analysis` | PandaAI 数据获取 + 证据化引用 |
| `risk_premortem` | 对抗性失败预演与风险清单 |

**调用的 PandaAI 数据 Skills**

官方 `panda_data` Python SDK（`init_token` 鉴权）：行情 `get_stock_daily`、指数 `get_index_daily`、回测因子 `get_factor`、财务季报 `get_fina_reports`、交易日历 `get_trade_cal`。类型到 getter 的映射集中在 `app/a2a/panda_client.py` 的 `SdkPandaClient._call_sdk`；另保留通用 REST 客户端作为备选接入路径。

## 结果展示

**过程展示（评审可见的实时状态流）**：任务执行中，平台通过 `message/stream` 或轮询 `tasks/get` 可看到逐阶段状态更新：

```
working: [Planner] 解析任务，拟定研究计划
working: [Data Agent] 获取 PandaAI 数据（3 项请求）
working: [Lens] Porter Five Forces — 竞争格局：分析中
working: [Lens] Porter Five Forces — 竞争格局：ok
...（五个 Lens 依次推进）
working: [Report Agent] 汇总五 Lens 结论，生成投研报告
completed: 分析完成：5/5 个 Lens 通过行为门控，总耗时 342 秒。完整报告见任务产物。
```

**最终产物**：一个 Markdown artifact（`five-lens-research-report.md`），固定结构如下：

```
# 五 Lens 投研分析报告
任务 / 决策问题 / 时间窗 / 候选选项（optionIds）
## 执行摘要                ← Report Agent 综合五 Lens 的中文摘要
**倾向性结论**             ← 指名偏好选项 + 附带触发条件
**关键风险**               ← ≤ 3 条
## Porter Five Forces — 竞争格局        ← 结构化 JSON（逐力量评分 + evidenceIds）
## Counterparty Response Matrix — 对手盘反应
## Pre-Mortem — 失败预演
## Scenario Planning — 情景推演
## Meadows Leverage Points — 系统杠杆点
## 数据来源                ← 证据条数统计（live/fixture 区分）
## 风险提示与免责声明        ← 每份报告强制附加
```

各 Lens 章节若未通过行为门控则显示 `⚠️ degraded` 及具体 findings；预算耗尽则显示 `⏱️ skipped`。具体报告内容样例见 `examples.md`。

## 代码结构（全部为最小侵入新增）

```
services/api/app/a2a/
├── config.py             # A2A_* / PANDAAI_* 环境变量（A2A_ENABLED 总开关，默认关闭）
├── agent_card.py         # Agent Card 构建
├── panda_client.py       # PandaAI 数据客户端（官方 panda_data SDK + REST 备选 + 离线 fixture）
├── deepseek_provider.py  # DeepSeek OpenAI 兼容 ModelProvider 实现
├── pipeline.py           # Planner→Data→五Lens→Report 进程内编排器
├── executor.py           # A2A AgentExecutor（官方 a2a-sdk）
└── mount.py              # 挂载函数：A2A_ENABLED=false 时零路由，可随时切回
```

复用（零改动）的既有引擎面：`app/strategic_lenses/`（五 Lens 实现与注册表）、`app/agents/`（WorkerRunner、BudgetLedger、ModelProvider 协议）、`method-packs/hardtech-market-direction@1.1.0`（Lens prompts 与 schema）。

## 合规声明

- 每份报告结尾强制附加"风险提示与免责声明"段落：不构成投资建议、数据可能延迟或缺失、degraded/skipped 部分置信度降低、实际投资请咨询持牌机构。
- 未通过行为门控的 Lens 输出不进入下游分析，并在报告中显式披露。
- 仅通过 PandaAI 官方数据接口取数，不绕过平台权限；主办方数据不用于比赛之外用途。

## 本地验证

```powershell
cd services/api
uv run pytest tests/a2a -q     # 7 个离线测试：pipeline / 门控降级 / 协议往返 / SDK 客户端
uv run ruff check app/a2a tests/a2a
```

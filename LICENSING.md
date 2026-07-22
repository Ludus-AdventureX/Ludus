# Ludus Licensing and Commercialization Policy

**Effective date:** 2026-07-22  
**Repository:** `xiayuzizhuo666/Ludus`  
**Current distribution status:** Private repository; no public software license granted.

> 本文件是项目内部的许可与商业化决策记录，不构成针对任何司法辖区的法律意见。公开发布、融资、接受外部贡献或签署商业许可前，应由具备资质的律师复核。

## 1. 当前法律状态

1. 本仓库当前必须保持 **Private**。
2. 仓库根目录当前不放置 `LICENSE` 文件；除第三方组件各自已有的许可外，Ludus 自有代码、文档、方法、Prompt、数据和资产均按 **All Rights Reserved** 管理。
3. 未获得权利人的书面授权，任何人不得复制、修改、分发、再许可、托管或将本项目用于商业服务。
4. “源码可见”“可访问 GitHub 仓库”或“允许内部协作”不等于开源，也不自动授予使用权。
5. 当前阶段不得把 Ludus 描述为已采用 MIT、Apache-2.0、AGPL-3.0 或 BSL 1.1；这些仅是未来完成边界拆分后的候选许可。

版权声明见 [`COPYRIGHT`](COPYRIGHT)。

## 2. 商业化原则

Ludus 采用“**核心私有 + 可选择性开放外围能力**”的 Open Core 候选策略。核心竞争力在未完成知识产权边界审计前保持私有；开放的目的应是降低集成成本、建立生态和提高可信度，而不是公开可直接复制的决策方法与运行机制。

### 2.1 默认保持 Proprietary 的核心

以下内容默认不得进入公开仓库或开放许可范围：

- `ways/**` 中的自有方法内容、方法编译结果、质量门、诊断问题和专有评估逻辑；
- 决策引擎、方法路由、评分与置信度聚合、V1–V9 验证逻辑、abstain 策略；
- Agent 编排、角色隔离、预算与恢复策略、内部 Tool Registry 策略；
- 因果图推断、模拟、敏感性分析、收敛与推荐生成的专有实现；
- 系统 Prompt、评估语料、golden fixtures、红队样本、调优数据和未公开研究材料；
- 商业连接器、运维策略、反滥用策略、客户配置和任何秘密或客户数据；
- 能够实质性复现上述核心能力的架构说明、参数、权重、规则表或派生资产。

第三方许可要求优先于本策略；第三方代码不得被错误标记为 Ludus Proprietary。

### 2.2 可候选开放的外围层

只有完成路径级边界审计并获得产品方书面批准后，才可考虑：

| 候选范围 | 候选许可 | 使用意图 |
|---|---|---|
| SDK、API client、插件接口、协议类型、非核心示例 | Apache-2.0 | 鼓励集成与生态采用；不得包含可复现核心算法的实现或秘密 |
| 经拆分的社区版 Web/API shell | AGPL-3.0-only + 单独商业许可 | 允许社区使用和修改，同时对网络服务修改版本施加对应源码义务；商业客户可另购商业许可 |
| 希望源码可见但限制竞争性生产使用的选定服务器模块 | BSL 1.1 + 明确 Additional Use Grant、Change Date、Change License | 作为 Source Available 方案；不得宣传为 OSI Open Source |
| 核心决策技术 | Proprietary commercial license | 托管服务、企业部署、OEM、方法包授权和支持服务 |

Apache-2.0、AGPL-3.0-only 与 BSL 1.1 不能仅靠在同一仓库中写一句说明来形成安全边界。正式采用前必须按目录或独立仓库拆分，明确版权归属、组合方式、分发物和依赖兼容性。

## 3. 双许可与贡献治理

若未来采用 AGPL 社区版 + 商业双许可：

1. 商业许可只能覆盖 Ludus 有权重新许可的代码。
2. 在接受外部贡献前，必须决定使用 CLA、版权转让协议或仅接受带明确再许可授权的贡献。
3. 未解决贡献者版权链时，不得承诺对社区贡献提供专有商业再许可。
4. 社区版与商业版的文件边界、构建产物和依赖必须可审计，不得依靠口头约定。

## 4. 公开发布前的强制 Gate

任何仓库、包、镜像、演示源码或方法资产改为公开前，必须全部完成：

1. **IP boundary audit**：逐路径标记 `public`、`source-available`、`proprietary`、`third-party`。
2. **来源与许可审计**：建立 `THIRD_PARTY_NOTICES.md`，记录上游版本、commit、文件/函数来源、许可证与修改情况。
3. **资产授权审计**：确认 `look/`、`探讨` 转换内容、字体、图标、图片、示例数据和演示素材的权利。
4. **专利与商业秘密审查**：在披露前判断是否需要申请专利，避免把尚未保护的可专利细节或商业秘密公开。
5. **商标与主体确认**：确认 “Ludus” 名称、Logo、域名及最终版权主体；将 `COPYRIGHT` 中的账号标识替换为真实个人或公司法定名称。
6. **贡献治理**：冻结 DCO/CLA、贡献者许可和商业再许可政策。
7. **安全发布审计**：完成 secret scan、历史记录扫描、客户数据检查、生成物和容器检查；仅删除当前文件不能消除 Git 历史泄漏。
8. **产品方书面批准**：明确批准具体路径、具体版本和具体许可证后，才可创建或修改根 `LICENSE`、SPDX header 或公开发布配置。

## 5. 仓库执行规则

- 任何开发者或 Agent 都不得擅自添加 MIT、Apache-2.0、AGPL-3.0、BSL 1.1 或其他根许可证。
- 不得未经产品方确认把仓库切换为 Public，或向公开 remote、公开包仓库、公开镜像仓库推送核心内容。
- 当前私有 GitHub `origin` 可用于受控协作，但首次 push 前仍需确认远程可见性并完成敏感信息扫描。
- 新文件默认继承本仓库的 All Rights Reserved 状态；第三方文件必须保留其原始版权与许可文本。
- 许可策略变更必须同时更新本文件、`README.md`、`AGENTS.md`、相关发布文档和分发物。

## 6. 官方参考

- No License / 默认版权说明：https://choosealicense.com/no-permission/
- OSI Approved Licenses：https://opensource.org/licenses
- Apache License 2.0：https://www.apache.org/licenses/LICENSE-2.0
- GNU AGPL v3：https://www.gnu.org/licenses/agpl-3.0.html
- Business Source License 1.1：https://mariadb.com/bsl11/

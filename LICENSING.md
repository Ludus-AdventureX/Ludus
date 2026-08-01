# Ludus Licensing and Commercialization Policy

**Effective date:** 2026-08-01
**Repository:** `Ludus-AdventureX/Ludus`
**Current distribution status:** Public repository — Source Available under PolyForm Noncommercial 1.0.0; commercial use requires a separate written license.

> 本文件是项目内部的许可与商业化决策记录，不构成针对任何司法辖区的法律意见。公开发布、融资、接受外部贡献或签署商业许可前，应由具备资质的律师复核。

## 1. 当前法律状态

1. 自 2026-08-01 起，经产品方批准，Ludus 自有内容（代码、文档、方法、Prompt、数据与资产）按 **PolyForm Noncommercial License 1.0.0** 对外提供，覆盖整个 `decision-lab` 仓库；本仓库已公开（Public）。根目录放置官方许可全文（[`LICENSE`](LICENSE)，SPDX: `PolyForm-Noncommercial-1.0.0`）。
2. 任何人可为**非商业目的**使用、复制、修改、分发本软件：包括个人学习、研究、实验与测试、教学、慈善与宗教用途，以及慈善组织、教育机构、公共研究机构、公共安全/健康组织、环保组织与政府机构的使用。
3. **任何商业目的的使用均被禁止**，包括但不限于：将软件或其衍生作品用于销售、收费托管服务、OEM、为第三方创收提供服务，或用于商业产品/服务的开发。商业使用必须与权利人另行签署书面商业许可。
4. PolyForm Noncommercial 1.0.0 是 **Source Available（源码可得）** 许可，**不是 OSI 认证的开源许可证**；本项目不得被描述为 Open Source 或"开源"。
5. 不得把本项目描述为已采用 MIT、Apache-2.0、AGPL-3.0、GPL、BSL 1.1 或其他公开许可；这些不是当前许可。
6. 分发者必须确保其收到的任一部分软件在继续分发时，接收者同时获得本许可条款或其官方 URL，以及 `Required Notice` 行（见 `LICENSE` 的 Notices 条款与 `COPYRIGHT`）。

版权与许可声明见 [`COPYRIGHT`](COPYRIGHT)。

## 2. 商业化原则

Ludus 采用"**非商业公开 + 商业许可**"双轨结构：

- **非商业侧（PolyForm Noncommercial 1.0.0）**：完整仓库对外公开，任何人与组织可为学习、研究、教学、评估等非商业目的自由使用与修改，以建立可信度、降低集成成本并接受社区检视；非商业条款防止竞争对手直接复制核心技术用于商业牟利。
- **商业侧（书面商业许可）**：面向托管服务、企业私有部署、OEM、方法包授权和支持服务。商业许可授权商业用途并可按需附加条款（支持、SLA、定制、保密），价格与条款以书面协议为准。

### 2.1 非商业条款下的核心资产

`ways/**` 自有方法、决策/评分/质量门、Agent 编排、因果模拟策略、系统 Prompt、eval corpus、golden fixtures 等核心资产随仓库公开供学习与研究，但仍受 PolyForm Noncommercial 条款约束：

- 不得用于任何商业目的，不得单独打包进入商业产品或服务；
- 不得以其为基础构建并对外销售/收费的衍生服务；
- 对上述资产的商业使用（无论直接或经衍生）必须另行签署商业许可。

### 2.2 原 Open Core 分层策略

原"核心私有 + 可选择性开放外围能力"的 Open Core 分层策略自本版本起停用。如未来需要恢复分层、改用其他许可（如 AGPL 社区版、BSL 或全开源），必须重新走第 4 节 Gate 流程并获得产品方书面批准后更新本文件。

## 3. 贡献治理

双轨结构要求 Ludus 对全部自有代码保有再许可权：

1. 商业许可只能覆盖 Ludus 有权重新许可的代码。
2. 在接受外部贡献前，必须落地 CLA（贡献者许可协议）或版权转让协议，确保贡献可以同时以 PolyForm Noncommercial 条款和商业条款分发。
3. 未解决贡献者版权链时，不得承诺对社区贡献提供商业再许可。
4. 第三方依赖保持其各自许可证；引入新依赖前必须核对许可兼容性与再分发义务（PolyForm Noncommercial 只约束 Ludus 自有内容，不改变第三方许可）。

## 4. 公开发布前的强制 Gate

许可文本已确定，但仓库、包、镜像或演示源码改为公开可见前，仍必须全部完成：

1. **IP boundary audit**：逐路径标记 `public`、`source-available`、`proprietary`、`third-party`，确认无不适合公开的内容。
2. **来源与许可审计**：建立 `THIRD_PARTY_NOTICES.md`，记录上游版本、commit、文件/函数来源、许可证与修改情况；确认与 PolyForm Noncommercial 的分发义务兼容。
3. **资产授权审计**：确认 `look/`、`探讨` 转换内容、字体、图标、图片、示例数据和演示素材的权利。
4. **专利与商业秘密审查**：披露前判断是否需要申请专利；公开即构成披露，避免把未保护的可专利细节或商业秘密公开。
5. **商标与主体确认**：确认 "Ludus" 名称、Logo、域名及最终版权主体；将 `COPYRIGHT` 中的账号标识替换为真实个人或公司法定名称。商标不随 PolyForm Noncommercial 授权。
6. **贡献治理**：冻结 CLA/DCO 与商业再许可政策（见第 3 节）。
7. **安全发布审计**：完成 secret scan、历史记录扫描、客户数据检查、生成物和容器检查；仅删除当前文件不能消除 Git 历史泄漏。
8. **产品方书面批准**：明确批准具体路径、具体版本和具体许可后，才可切换仓库可见性或向公开 remote、registry、镜像仓库推送。

## 5. 仓库执行规则

- 根 `LICENSE` 为 PolyForm Noncommercial 1.0.0 官方全文，不得擅自替换或修改其文本；许可策略再变更仍须产品方书面批准。
- 新增 Ludus 自有源文件建议携带 SPDX 标头：`SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0`。
- 第三方文件必须保留其原始版权与许可文本，不得错误标记为 Ludus 自有。
- 仓库切换为 Public、向公开 remote/registry/镜像推送前，必须完成第 4 节全部 Gate 并经产品方确认。
- 许可策略变更必须同时更新本文件、`LICENSE`、`COPYRIGHT`、`README.md`、`AGENTS.md`、相关发布文档和分发物。

## 6. 官方参考

- PolyForm Noncommercial License 1.0.0 官方文本：https://polyformproject.org/licenses/noncommercial/1.0.0
- SPDX `PolyForm-Noncommercial-1.0.0`：https://spdx.org/licenses/PolyForm-Noncommercial-1.0.0.html
- PolyForm Project：https://polyformproject.org
- OSI Approved Licenses（本项目不属于）：https://opensource.org/licenses
- No License / 默认版权说明：https://choosealicense.com/no-permission/

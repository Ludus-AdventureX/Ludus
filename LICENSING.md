# Ludus Licensing and Commercialization Policy

**Effective date:** 2026-07-26  
**Repository:** `xiayuzizhuo666/Ludus`  
**Current distribution status:** Dual-licensed — AGPL-3.0-only (open source) + commercial license.

> 本文件是项目内部的许可与商业化决策记录，不构成针对任何司法辖区的法律意见。公开发布、融资、接受外部贡献或签署商业许可前，应由具备资质的律师复核。

## 1. 当前法律状态

1. 自 2026-07-26 起，经产品方批准，本仓库正式采用 **AGPL-3.0-only + 商业双许可（dual licensing）** 结构，覆盖整个 `decision-lab` 仓库。
2. 仓库根目录放置官方 **GNU Affero General Public License v3** 全文（[`LICENSE`](LICENSE)，SPDX: `AGPL-3.0-only`）。除第三方组件各自已有的许可外，Ludus 自有代码、文档、方法、Prompt、数据和资产均按 AGPL-3.0-only 授权。
3. 任何人可在遵守 AGPL-3.0-only 条款的前提下使用、修改、分发本项目，包括：基于本项目提供网络服务时，必须向该服务的用户提供对应修改版本的完整源码（AGPL §13）。
4. 不愿或不能履行 AGPL 源码义务的组织（如需闭源集成、私有化修改、OEM），可向权利人另行获取**商业许可**，条款以书面协议为准。
5. AGPL-3.0-only 是 OSI 认证的开源许可证，本项目可以且应当被描述为 Open Source。

版权与双许可声明见 [`COPYRIGHT`](COPYRIGHT)。

## 2. 双许可商业化原则

Ludus 采用 **AGPL 社区版 + 商业许可** 的双许可策略（参考 MongoDB 早期、Grafana、Mastodon 模式）：

- **AGPL-3.0-only 社区侧**：完整功能对社区开放，任何基于 Ludus 提供网络服务的修改版本必须开源其修改，从而防止竞争对手闭源白嫖核心决策技术。
- **商业许可侧**：面向托管服务、企业私有部署、OEM、方法包授权和支持服务。商业许可解除 AGPL 的 copyleft 义务，按书面协议单独定价。

原"核心私有 + 外围开放"的 Open Core 分层策略自本版本起停用；如未来需要恢复分层，必须重新走第 4 节的 Gate 流程并更新本文件。

## 3. 贡献治理

双许可结构要求 Ludus 对全部自有代码保有再许可权：

1. 商业许可只能覆盖 Ludus 有权重新许可的代码。
2. 在接受外部贡献前，必须落地 CLA（贡献者许可协议）或版权转让协议，确保贡献可以同时以 AGPL 和商业条款分发。
3. 未解决贡献者版权链时，不得承诺对社区贡献提供专有商业再许可。
4. 第三方依赖必须与 AGPL-3.0-only 兼容；引入新依赖前必须核对许可兼容性，GPL 不兼容的依赖不得进入分发物。

## 4. 公开发布前的强制 Gate

许可证已确定，但任何仓库、包、镜像或演示源码改为公开可见前，仍必须全部完成：

1. **来源与许可审计**：建立 `THIRD_PARTY_NOTICES.md`，记录上游版本、commit、文件/函数来源、许可证与修改情况，并确认与 AGPL-3.0-only 的兼容性。
2. **资产授权审计**：确认 `look/`、`探讨` 转换内容、字体、图标、图片、示例数据和演示素材的权利。
3. **专利与商业秘密审查**：在披露前判断是否需要申请专利；AGPL 发布即构成公开披露。
4. **商标与主体确认**：确认 "Ludus" 名称、Logo、域名及最终版权主体；将 `COPYRIGHT` 中的账号标识替换为真实个人或公司法定名称。商标不随 AGPL 授权。
5. **贡献治理**：冻结 CLA/DCO 与商业再许可政策（见第 3 节）。
6. **安全发布审计**：完成 secret scan、历史记录扫描、客户数据检查、生成物和容器检查；仅删除当前文件不能消除 Git 历史泄漏。

## 5. 仓库执行规则

- 根 `LICENSE` 为 AGPL-3.0-only 官方全文，不得擅自替换为其他许可证或修改其文本；许可策略再变更仍须产品方书面批准。
- 新增 Ludus 自有源文件建议携带 SPDX 标头：`SPDX-License-Identifier: AGPL-3.0-only`。
- 第三方文件必须保留其原始版权与许可文本，不得错误标记为 Ludus 自有。
- 仓库切换为 Public、向公开 remote/registry/镜像推送前，必须完成第 4 节全部 Gate 并经产品方确认。
- 许可策略变更必须同时更新本文件、`LICENSE`、`COPYRIGHT`、`README.md`、`AGENTS.md`、相关发布文档和分发物。

## 6. 官方参考

- GNU AGPL v3 官方文本：https://www.gnu.org/licenses/agpl-3.0.html
- SPDX AGPL-3.0-only：https://spdx.org/licenses/AGPL-3.0-only.html
- OSI Approved Licenses：https://opensource.org/licenses
- GNU 双许可说明（Selling Exceptions）：https://www.gnu.org/philosophy/selling-exceptions.html
- choosealicense.com AGPL-3.0：https://choosealicense.com/licenses/agpl-3.0/

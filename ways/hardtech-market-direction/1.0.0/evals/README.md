# Method Eval Suite

本目录验证方法行为，不固定模型措辞，也不预设项目成功概率。每个 eval 只声明路由、必须发现的结构、阻断条件、透镜行为和建议翻转纪律。

| Eval | 类型 | 主要验证 |
|---|---|---|
| `spherical-robot.json` | P0 金路径 | exact/full、五透镜、采购周期翻转、8/10 沙盘 |
| `bci-platform-seed.json` | legacy parity A | 种子期资源下，多线平台扩张因现金/团队/采购周期触发硬门；应收窄最小楔子 |
| `bci-platform-angel.json` | legacy parity B | 资源扩张后必须重新分析而非继承种子期结论；允许条件化分阶段组合，但禁止无门控的三线并行 |
| `partial-missing-decision-contract.json` | 负向路由 | 缺期限、现金窗口和材料授权时返回 partial，不启动 Worker/lens |
| `unsupported-marketing-optimization.json` | 负向路由 | 无硬科技、研发/交付和切换成本约束的投放优化返回 unsupported |

## Parity 判定

BCI 双轨 eval 来源于同一去标识化战略问题在两种资源前提下的既有分析。通过标准不是逐字复现旧报告，而是同时满足：

1. 相同策略在资源约束显著变化时重新计算硬门和优先级。
2. 种子期不得用市场规模救回超出现金窗口和组织容量的三线扩张。
3. 天使期不得机械沿用种子期“只能单线”的结论，也不得把更多资金自动解释为三线同时全面建设。
4. 两个版本都保留需求、采购、交付、安全、现金、供应链和可逆性条件。
5. 反方发现必须改变正文、阈值、退出条件、质量画像或沙盘。

## 负向路由判定

- `partial` 和 `unsupported` 均不得创建 Charter、Run、正式报告、五透镜 stage output/artifact 或正式沙盘。
- Router 只能返回已发布目录中存在的方法 ID/version；负向 eval 不允许用通用 Prompt 冒充正式方法。
- 用户仍可继续日常问答或运行明确标注为非正式的 quick 分析。

# 24. Ludus 前端视觉主题与 Look V7 接入合同

## 文档状态

- 状态：canonical / accepted
- 生效日期：2026-07-21（星期二）
- 关联变更：`docs/contract-changes/CCR-20260721-003.md`
- 设计源：`E:\Temp\xiayu\Documents\adventure-x\look`
- 关联前端规格：`11-frontend-spec.md`

本文取代旧 V5.2 Paper/Graphite 平行主题合同。`look/` 的十主题、Decision Spine、empty view、Project Drawer、关键 dialog/drawer 和交互密度是最终视觉基线；旧 V5/V5.2/V6 文档只保留历史参考，不得覆盖 V7。

`look/` 是静态设计原型，不是生产依赖。生产实现必须记录一次性设计快照、转换 token 和组件，并由生成 API client 驱动数据。

## 1. 产品视觉主张

Ludus 是“安静、可审计、由人承担后果的决策札记”，不是营销仪表盘、Agent 控制台或通用聊天皮肤。

视觉必须同时表达三类责任：

- **Human / Commitment**：人的确认、覆盖、承诺与签署；
- **Analysis / Evidence**：系统分析、证据、模型、关系线与工具状态；
- **Unknown / Fragile**：未知、假设、阈值、约束、冲突与翻转条件。

三类语义不能只靠颜色表达；标签、图形、位置和文本必须共同说明。任何主题都不得改变责任、状态、权限或数据含义。

## 2. Look V7 信息结构

Decision Spine 精确为：

1. 问题 `workspace`
2. 证据 `analysis`
3. 判断 `report`
4. 推演 `sandbox`
5. 决定 `decision`

Review 是 dialog/drawer，Case 选择是 Project Drawer，无 Case 时使用 `empty` view。视觉实现不得恢复旧“四页 + Decision drawer”、独立 Review 主页面或模板墙。

## 3. 十个公开主题

公开 theme ID、显示名和顺序必须精确一致：

| 顺序 | ID | 中文名 | 英文名 |
|---:|---|---|---|
| 1 | `ink` | 水墨黑白 | Ink Wash |
| 2 | `ledger` | 墨纸酒红 | Quiet Ledger |
| 3 | `vermilion` | 宣纸朱红 | Xuan Cinnabar |
| 4 | `red` | 莫兰迪红 | Dusty Red |
| 5 | `orange` | 莫兰迪橙 | Quiet Terracotta |
| 6 | `yellow` | 莫兰迪黄 | Dry Ochre |
| 7 | `green` | 莫兰迪绿 | Muted Sage |
| 8 | `cyan` | 莫兰迪青 | Mist Cyan |
| 9 | `blue` | 莫兰迪蓝 | Slate Blue |
| 10 | `purple` | 莫兰迪紫 | Dusty Violet |

默认主题是 `ink`。主题选择可保存在生产自己的版本化 storage key 中，但不得沿用原型全局状态实现。非法 ID 回退 `ink`，同时保留可读提示；主题切换不触发 API mutation、分析、推演或签署。

`vermilion` 的公开 secondary 固定为 Deep Indigo。原型的 `secondary=warm|pine` 只属于设计比较，不是第十一/十二个主题，不进入生产持久化合同。

## 4. Semantic token 合同

生产 CSS 至少建立以下语义层，不得让组件直接引用原型文件中的任意十六进制值：

```css
:root {
  --ludus-paper-base: ...;
  --ludus-paper-sheet: ...;
  --ludus-paper-wash: ...;
  --ludus-rule: ...;
  --ludus-rule-strong: ...;

  --ludus-ink: ...;
  --ludus-ink-muted: ...;
  --ludus-ink-quiet: ...;

  --ludus-human: ...;
  --ludus-human-strong: ...;
  --ludus-human-wash: ...;
  --ludus-on-human: ...;

  --ludus-analysis: ...;
  --ludus-analysis-strong: ...;
  --ludus-analysis-wash: ...;

  --ludus-unknown: ...;
  --ludus-unknown-wash: ...;
  --ludus-danger: ...;

  --ludus-night-base: ...;
  --ludus-night-sheet: ...;
  --ludus-night-card: ...;
  --ludus-night-text: ...;
  --ludus-night-muted: ...;
}
```

转换层可以保留 `look/themes.css` 的源变量名用于生成脚本输入，但运行时组件只能消费 `--ludus-*` semantic token 或由其派生的 component token。新增主题必须通过 CCR、对比度和三责任语义测试。

## 5. Component token 与层级

组件层至少提供：

- `--surface-app`、`--surface-sheet`、`--surface-raised`、`--surface-night`；
- `--text-primary`、`--text-secondary`、`--text-quiet`、`--text-inverse`；
- `--border-subtle`、`--border-strong`、`--focus-ring`；
- `--action-human`、`--action-analysis`、`--state-unknown`、`--state-danger`；
- `--shadow-drawer`、`--shadow-dialog`；
- `--graph-human-line`、`--graph-analysis-line`、`--graph-unknown-line`。

Human 色只用于需要人的确认、承诺、签署或显式覆盖的动作；普通导航、系统运行和证据动作不得涂成 Human。Analysis 色用于系统分析、证据和关系；Unknown 用于未解决风险、阈值和不稳定条件。成功/错误/来源模式使用独立状态标识，不能挪用 Human/Analysis/Unknown。

## 6. 排版与密度

- 正文优先系统中文无衬线；标题可使用稳定、可授权的衬线字体回退栈。
- 数据、版本、坐标、hash 和状态使用等宽字体。
- 页面保持纸页、规则线和编辑札记感，但不得牺牲正文可读性。
- 禁止营销式超大 Hero、装饰光球、霓虹渐变、模板卡片墙、无意义 KPI 大字和过度圆角。
- 关键决定、signoff 与未知风险通过层级和留白强调，不靠动画制造权威感。

## 7. 五工作区视觉职责

### 问题

使用 Paper/Sheet 环境，突出人的问题、Ledger、候选与档案。AI 建议默认显示为 analysis/unknown 候选，未经确认不得呈现为正式 Human 内容。

### 证据

证据质量、来源模式、Agent/Tool 状态和引用链使用 Analysis 语义。Evidence Drawer 必须保持来源、quote、locator、相反证据和质量信息的可读层级。

### 判断

先显示条件化建议和最脆弱前提，再显示完整报告。系统 abstain 使用 Unknown/Warning 结构，而不是红色错误或隐藏推荐区域。

### 推演

默认压力测试使用当前公开主题的 paper surface；只有按需展开的完整因果模型进入 graph-focused Night Desk surface。`Paper` 与 `Night Desk` 在这里是 surface 角色，不是公开 theme ID，也不恢复旧 Paper/Graphite 双主题。Night Desk 不是“高级功能装饰”，必须保留文字摘要、键盘导航和颜色以外的关系区分。

### 决定

SignoffPayload、payloadHash、签署声明和不可变历史使用最清晰的 Human/Commitment 层级。系统建议仍保持 Analysis；人的 selected option 和签名才转为 Human。不得把“系统推荐”按钮设计成默认同意。

## 8. Dialog、Drawer 与焦点

Project、Theme、Dossier、Evidence 可使用 drawer；Charter、Review 和 Signoff confirmation 可使用 dialog。所有覆盖层必须：

- 有可访问名称和 `aria-modal`；
- 打开时移动焦点，关闭时回到原触发器；
- 支持 Escape 和可见关闭按钮；
- focus trap，不让背景元素继续 Tab；
- 在移动端成为单列或底部 sheet 时保留同样语义；
- 不因主题变化丢失打开状态或领域输入。

## 9. 响应式、运动与可访问性

- 验收视口：1440×900、1024×768、390×844。
- 触控目标至少 44×44 CSS px。
- 正文、按钮、focus、状态和图形关键线满足 WCAG AA；自动化扫描之外必须做键盘人工验收。
- 支持 `prefers-reduced-motion`；导航、drawer 和主题过渡在 reduced 模式下关闭非必要动画。
- 图与色块必须有文字/图形替代；source mode、Human/Analysis/Unknown 和 pass/warn/block 不能只靠色相。

## 10. 静态原型到生产的转换

正式工程添加：

```text
design/
├── look-source-manifest.json
├── tokens/
│   ├── themes.generated.css
│   ├── semantic.css
│   └── components.css
└── look-component-map.md
```

转换规则：

1. `look/themes.css` → 生成的 theme token；
2. `look/styles.css` → 人工拆分的 semantic/layout/component 样式，不整文件复制；
3. `look/index.html` → React/Next.js 组件结构；
4. `look/app.js` → 交互测试规格，禁止作为生产 script、iframe 或运行时依赖；
5. 原型静态数据 → 测试 fixture；生产数据只来自生成 API client；
6. 原型 Playwright/Axe 行为 → 生产 E2E；
7. 每次重新导入都更新 manifest hash，并由设计/前端 owner 审阅差异。

`look-source-manifest.json` 至少包含：

```json
{
  "source": "../look",
  "lookVersionText": "Ludus Prototype / Xuan Cinnabar Deep Indigo Secondary / Updated: 2026-07-19",
  "importedAt": "2026-07-21",
  "files": ["VERSION", "README.md", "index.html", "themes.css", "styles.css", "app.js"],
  "bundleSha256": "c5d5d65bf62efdd14e4e3e13d1c70b92f9d6b4cdd4dbd2f652107d84d1a55e98"
}
```

哈希算法与 `11-frontend-spec.md` 一致。`look/HEAD` 记录 Logo/图标工作，不参与设计快照 readiness 或合同验证。

## 11. 主题测试

必须自动验证：

- 主题 ID 精确等于十项且默认 `ink`；
- 每个主题在五工作区、empty、Project Drawer、Review dialog 和 graph-focused Night Desk surface 均能渲染；
- Human/Analysis/Unknown 语义不随主题交换；
- 主题选择键盘方向键、Home、End、Escape、focus return 可用；
- 非法主题回退；旧原型分享参数只在明确迁移层转换，不扩散到领域模型；
- 主题切换不发起分析、Simulation 或 signoff mutation；
- 生产构建不包含 `look/app.js` 或对 `look/` 的运行时网络/文件依赖。

## 12. 完成定义

- V7 十主题与五工作区成为唯一活动视觉/IA 合同；
- 旧 V5.2、Paper/Graphite/氧化铜描述不再作为开发依据；
- 设计 manifest、token 生成、组件映射和 E2E 均存在；
- 三责任语义、abstain、来源模式和签署责任在十主题中都清楚可见；
- 三视口、键盘、focus、对比度和 reduced motion 通过验收；
- Look 静态原型没有进入生产运行时。

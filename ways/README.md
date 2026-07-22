# Ludus Ways

`ways/` 是 Ludus 方法论的可审阅源目录，不是运行时动态加载目录。这里保存人可读、可测试、可版本化的方法定义；未来的发布编译器将通过校验的版本编译到 `method-packs/`，运行时只读取已发布、内容寻址且不可变的产物。

## 生命周期

1. 在 `ways/<method-id>/<semver>/` 编写 manifest、诊断问题、质量门、Prompt、schema 和 eval。
2. 校验 YAML、JSON Schema、eval、路径边界、Worker/工具白名单和来源版本。
3. 对规范化后的包内容计算 SHA-256；哈希范围包含包内所有常规文件，但排除 manifest 中待回填的 `release.content_hash` 字段。
4. 将完全相同的内容发布到 `method-packs/<method-id>/<semver>/`，回填内容哈希并把运行时状态置为 `published`。
5. Charter 和 AnalysisRun 同时冻结方法 ID、语义化版本和内容哈希。运行期间不热重载。

## 版本与哈希原则

- 已发布版本不可原地修改。任何语义或行为变化都发布新 SemVer 版本。
- Prompt、schema、质量阈值、预算、工具权限、eval 或来源清单变化至少触发补丁版本；不兼容输入/输出或路由边界变化触发主版本。
- 哈希基于 UTF-8、LF 换行、按相对 POSIX 路径字典序排列后的文件字节；编译器不得把时间戳、绝对路径或密钥写入哈希输入。
- 同一 ID/版本出现不同哈希时必须拒绝加载，而不是覆盖历史包。
- `ways` 中的 `release_candidate` 只表示源包通过人工编译，不能进入正式 Router；只有 `method-packs` 中状态为 `published` 且哈希复算一致的包可执行。

P0 仅维护 `hardtech-market-direction@1.0.0`。`ways` 不承载聊天平台协议、旧技能的临时文件布局或任意技能组合器。

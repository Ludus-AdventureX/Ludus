# VPS 部署说明（A2A 层）

## 前提

- VPS 上已用 `services/api/Dockerfile` 构建并运行后端（现状不变）。
- 已配置 `MODEL_API_KEY` 等 `MODEL_*` 环境变量（DeepSeek，现状不变）。

## 开启 A2A（只增环境变量 + 重建镜像）

1. **重建镜像**（拉取包含 `app/a2a/` 的最新代码后，Dockerfile 无需修改）：

   ```bash
   docker build -t decision-lab-api:a2a services/api
   ```

2. **挂载 method-packs（推荐）**：镜像默认只 COPY `app/`，Lens 使用内置金融化
   fallback prompts 也能运行；挂载已发布 method-pack 可启用完整的 canonical prompts：

   ```bash
   -v /path/to/repo/method-packs:/app/method-packs:ro \
   -e A2A_METHOD_PACK_ROOT=/app/method-packs
   ```

3. **注入 A2A 环境变量**（PandaAI 数据走官方 `panda_data` SDK，凭证为
   官网账号：86+注册手机号 / 官网密码）：

   ```bash
   -e A2A_ENABLED=true \
   -e A2A_PUBLIC_URL=https://<你的公网域名> \
   -e A2A_TASK_BUDGET_SECONDS=900 \
   -e PANDAAI_USERNAME=86<注册手机号> \
   -e PANDAAI_PASSWORD=<PandaAI 官网密码>
   ```

4. **反向代理**：将以下两条路径透传到容器 8000 端口（SSE 需要禁用缓冲）：

   - `GET  /.well-known/agent-card.json`
   - `POST /a2a`（`message/stream` 为 SSE：`proxy_buffering off; proxy_read_timeout 1200s;`）

5. **验收**：

   ```bash
   curl https://<域名>/.well-known/agent-card.json          # 200 + 完整卡片
   curl -X POST https://<域名>/a2a -H "Content-Type: application/json" -d '{
     "jsonrpc":"2.0","id":"smoke-1","method":"message/send",
     "params":{"message":{"kind":"message","role":"user","messageId":"m-smoke-1",
       "parts":[{"kind":"text","text":"分析宁德时代未来两年的竞争格局与下行风险"}]}}}'
   ```

## 切回（关闭 A2A）

去掉 `A2A_ENABLED`（或设为 `false`）后重启容器即可：不挂载任何 A2A 路由，
`/.well-known/agent-card.json` 与 `/a2a` 均为 404，服务行为与改造前完全一致。
无数据库迁移、无状态残留（任务存储在内存中）。

## 注意事项

- PandaAI 凭证未配置时 Agent 仍可运行，但报告会声明“未获取到外部市场
  数据”；凭证错误（init_token 失败）会让任务显式失败而非静默降级，
  上线前先用一个示例任务验证。
- 镜像需重新 build 以安装新依赖（a2a-sdk、panda_data、pandas，已写入
  uv.lock）。
- 任务存储为进程内存（InMemoryTaskStore）：容器重启会丢失进行中的任务，
  评审期间避免在任务执行时重启。
- 评审期保活：建议配置 `docker run --restart unless-stopped` 与外部拨测
  （每 5 分钟 GET agent-card）。

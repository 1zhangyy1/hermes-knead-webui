# Hermes Runtime Notes

日期：2026-05-18

更新：2026-06-05

当前生产仓库已把官方 Hermes Agent 作为一等 runtime 放在
`runtimes/hermes-agent`。`vendor/` 只保留本地参考 checkout，不再作为生产
启动路径。

## 1. 目标

Phase 0 的目标是验证：

- Hermes Agent 可以作为完全复用的底层 Agent Runtime。
- 我们可以在不打扰用户全局 Hermes 服务的情况下，在本项目内启动隔离 runtime。
- `:8642` gateway API 和 `:9119` dashboard API 可以被 Host Shell 调用。
- `/v1/runs` 和 SSE events 这条链路适合后续 Evolution Task。

## 2. 本地隔离运行方式

本次没有改动全局 `~/.hermes` 的配置，而是在项目内使用：

```text
HERMES_HOME=/Users/nuomiji/Documents/zyyai/max/nextaichat/.hermes-home
```

Hermes Agent 源码和 venv 位于：

```text
/Users/nuomiji/Documents/zyyai/max/nextaichat/runtimes/hermes-agent
```

安装依赖：

```sh
cd /Users/nuomiji/Documents/zyyai/max/nextaichat/runtimes/hermes-agent
uv venv .venv --python 3.11
uv pip install -e ".[web,messaging]"
```

启动 gateway：

```sh
cd /Users/nuomiji/Documents/zyyai/max/nextaichat/runtimes/hermes-agent
HERMES_HOME=/Users/nuomiji/Documents/zyyai/max/nextaichat/.hermes-home \
API_SERVER_ENABLED=true \
API_SERVER_HOST=127.0.0.1 \
API_SERVER_PORT=8642 \
./.venv/bin/hermes gateway run
```

启动 dashboard：

```sh
cd /Users/nuomiji/Documents/zyyai/max/nextaichat/runtimes/hermes-agent
HERMES_HOME=/Users/nuomiji/Documents/zyyai/max/nextaichat/.hermes-home \
./.venv/bin/hermes dashboard --no-open
```

## 3. Smoke Script

新增脚本：

```text
/Users/nuomiji/Documents/zyyai/max/nextaichat/scripts/hermes-smoke.mjs
```

运行：

```sh
cd /Users/nuomiji/Documents/zyyai/max/nextaichat
HERMES_API_URL=http://127.0.0.1:8642 \
HERMES_DASHBOARD_URL=http://127.0.0.1:9119 \
node scripts/hermes-smoke.mjs
```

只验证 runtime 接口层：

```sh
HERMES_API_URL=http://127.0.0.1:8642 \
HERMES_DASHBOARD_URL=http://127.0.0.1:9119 \
HERMES_SMOKE_SKIP_AGENT_RUNS=1 \
node scripts/hermes-smoke.mjs
```

## 4. 验证结果

隔离 runtime 启动成功。

通过的接口：

- `GET http://127.0.0.1:8642/health`
- `GET http://127.0.0.1:8642/v1/capabilities`
- `GET http://127.0.0.1:9119/api/status`

`/v1/capabilities` 返回的关键能力包括：

- `chat_completions`
- `chat_completions_streaming`
- `responses_api`
- `responses_streaming`
- `run_submission`
- `run_status`
- `run_events_sse`
- `run_stop`
- `run_approval_response`
- `tool_progress_events`
- `approval_events`

这确认了 Hermes Agent 可以直接作为我们 Host Shell 的底层 runtime。

## 5. 当前阻塞

第一轮在隔离 `HERMES_HOME` 下没有配置模型 provider/API key，因此真正模型调用失败：

```text
No inference provider configured. Run 'hermes model' to choose a provider and model,
or set an API key (OPENROUTER_API_KEY, OPENAI_API_KEY, etc.) in ~/.hermes/.env.
```

这不是接口层问题，而是隔离 runtime 缺少模型配置。随后已给项目隔离 `.hermes-home/.env` 配置 OpenRouter key，并设置：

```text
provider = openrouter
model = anthropic/claude-sonnet-4-6
```

当前状态：

- runtime API 层已验证。
- dashboard API 层已验证。
- `/v1/responses` 已完成真实 inference，返回 `hermes smoke ok`。
- `/v1/runs` 已完成真实 inference，并通过 SSE 返回 `message.delta` 与完成事件。

完整 smoke 结果：

```text
PASS gateway /health
PASS gateway /v1/capabilities
PASS dashboard /api/status
PASS responses API
PASS runs API + SSE events

All 5 checks passed.
```

## 6. 下一步

已完成 Host Shell 第一轮接入：

1. 初始化 `apps/host-shell`，使用 Vite + React + TypeScript。
2. 抽出 `packages/hermes-client`，Host Shell 通过 client 访问 Hermes，不再在 UI 组件内直接手写底层 fetch。
3. Host Shell 通过 `/hermes/*` 代理连接 gateway，通过 `/hermes-dashboard/*` 代理连接 dashboard。
3. 已修复 dashboard 代理被 `/hermes` 前缀截胡的问题。
4. 已修复浏览器 POST `/v1/runs` 时 Hermes 因 `Origin` header 返回 `403 Forbidden` 的问题：Vite proxy 会剥离浏览器 `Origin`。
5. Agent side panel 已通过 Hermes `/v1/runs` 创建任务，并用 browser `EventSource` 读取 `/v1/runs/{run_id}/events`。
6. UI 已验证真实闭环：Prompt -> Hermes run -> SSE output -> PPT Outline/Slide 自动更新。
7. 抽出 `packages/space-runtime` 和 `spaces/ppt-studio/space.json`，开始把 Space 作为 manifest 驱动的子应用单位。
8. `spaces/ppt-studio` 已拆为独立 workspace package，Host Shell 通过 package import 装载它。
9. `spaces/meta-chat` 已重构为 `通用 Agent` 主入口，直接复用 upstream Hermes UI 的完整 chat / files / skills / logs 体验。
10. Host Shell 已收敛为 Codex-like 三栏：左侧 Space 导航，中间 Hermes Agent，右侧 Space Growth Lens。
11. `PPT Studio` 已加入安全版 Evolution MVP：Hermes 可参与生成提案，用户可预览、应用、回滚 Space 运行态变体。

当前 WebUI 运行方式：

```sh
cd /Users/nuomiji/Documents/zyyai/max/nextaichat
pnpm dev
```

当前地址：

```text
http://127.0.0.1:8788
```

注意：项目脚本 `pnpm dev` 会让 WebUI 使用 `.hermes-home` 的本地状态和
`runtimes/hermes-agent` 的官方 runtime 代码，因此本地聊天、工具、技能和
agent loop 都归到当前仓库的生产 runtime 边界。

建议下一步：

1. 增加 `packages/space-sdk`，定义 Space 与母体通信的最小 API。
2. 让 Space Growth Lens 读取真实 Hermes 会话，而不是使用手动 `Analyze` 原型状态。
3. 把 Evolution Proposal 从运行态变体升级为真实代码 diff 和 preview build。
4. 增加 approval / rollback 的代码级产品流。

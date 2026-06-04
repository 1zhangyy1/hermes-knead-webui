# AI Space Platform 实施计划

日期：2026-05-18

> 2026-05-23 更新：本文记录了早期 `AI Space Platform / Space-first` 实施设想，其中多处实现状态和产品入口已经过时。当前第一版执行以 [当前产品认知：自进化工作台](docs/PRODUCT_DIRECTION_CURRENT.md) 为准：**先做极简空工作台 Chat；新对话是入口；普通对话是默认工作台；专属工作台从任务中沉淀出来。**

## 1. 当前决策

### 当前实现状态

已启动第一版母体应用：

- `apps/host-shell` 已初始化为 Vite + React + TypeScript 应用。
- `packages/hermes-client` 已抽出，封装 Gateway、Dashboard、Runs 和 SSE/EventSource 事件流。
- `packages/space-runtime` 已抽出，定义 `SpaceManifest` / `SpaceCatalogItem` 等基础 Space 协议。
- `spaces/meta-chat` 已重构为系统主入口：直接展示 Hermes UI 聊天，去掉 Mother Chat / debug console 双入口，降低首屏复杂度。
- `spaces/ppt-studio/space.json` 已成为第一个真实 Space manifest。
- `spaces/ppt-studio` 已成为独立 workspace package，PPT Studio UI 和 Hermes 交互已从 Host Shell 主文件中拆出。
- 首页已改为更接近 Codex 的层级：左侧有新对话、搜索、插件、自动化、置顶、项目、会话历史；中间是项目级新对话 composer；Space 只作为项目下长出来的专属应用。
- `PPT Studio` 已有 Outline、Slide、Brand Kit、Speaker Notes、Evolution 建议区和 Hermes Agent side panel。
- `PPT Studio` 已跑通安全版 Evolution MVP：生成进化提案、预览 Investor Mode、应用到本地持久状态、回滚恢复。
- Host Shell 已能同时探测 Hermes Gateway 和 Dashboard 状态。
- `通用 Agent` 已能通过内嵌 Hermes UI 完成真实对话。
- `通用 Agent` 已加入第一版 `Space Growth Lens`，跑通 `Analyze -> Proposal -> Preview/Create` 的产品闭环。
- `PPT 工作台` 可以从原型状态创建为专属空间，创建状态持久化到 localStorage。
- Agent side panel 已能调用 Hermes `/v1/runs`，通过 SSE/EventSource 接收输出，并把 slide outline 映射回 UI。
- 真实浏览器验证通过：输入短提示后，Hermes 输出被映射为 `Mother App / Space Runtime / Evolution Loop` 三页。
- 当前 Space 导航已经从硬编码数组迁移到 `space-catalog`，PPT 的 Agent instructions 来自 manifest。
- 当前 Host Shell 只负责 Space 导航、runtime 状态和 Space 装载；PPT Studio 自己负责自己的工作台状态和 Agent side panel。

当前 MVP 跑通范围：

```text
Host Shell -> Space Registry -> PPT Studio
PPT Studio -> Hermes run -> SSE output -> deck outline update
PPT Studio -> Evolution Proposal -> Preview -> Apply -> local persistence -> Rollback
Host Shell -> Project Home -> Composer / connectors / project context
Host Shell -> Project Sidebar -> conversations / plugins / automations / spaces
Host Shell -> 通用 Agent Space -> embedded Hermes UI -> Hermes UI /api/chat/* -> AIAgent
Host Shell -> Project Home -> Grow PPT 工作台 -> 专属空间
```

当前还不是代码级自进化：`Apply` 先改运行态和 localStorage，不直接写磁盘代码。下一阶段要把 Evolution Proposal 接到真实 diff、preview build、approval、apply/rollback。

当前本地运行地址：

```text
http://127.0.0.1:5173/
```

当前 Hermes runtime：

```text
Gateway:   http://127.0.0.1:8642
Dashboard: http://127.0.0.1:9119
Raw Hermes UI: http://127.0.0.1:3333/hermes-ui.html
```

注意：当前正式聊天入口是 `通用 Agent` 内嵌的 Hermes UI。Hermes UI 复用 `serve_lite.py` direct server，运行在 `:3333`，现在通过 `HERMES_HOME=.hermes-home` 和 `HERMES_AGENT_DIR=vendor/hermes-agent` 连接项目隔离 runtime 与模型配置。

### Hermes Agent 完全复用

Hermes Agent 不只是参考项目，而是我们的底层 Agent Runtime / Agent OS。

我们不重写：

- agent loop
- memory
- skills
- tools
- gateway
- approvals
- cron
- MCP
- terminal backends
- model provider abstraction

我们做的是 Hermes 外面的产品层：

```text
AI Space Host Shell
  - Space 首页
  - 场景化工作台
  - Agent side panel
  - Space Runtime
  - Evolution UX
  - preview / apply / rollback

        ↓ HTTP / SSE / approval

Hermes Agent
  - :8642 gateway API
  - :9119 dashboard API
  - AIAgent
  - tools / skills / memory / MCP / cron
```

### Web-first

第一版先做 Web / PWA，后面再包 Tauri 或 Electron。

原因：

- Space 本质上是可运行、可预览、可版本化的 Web 子应用。
- Web 更适合 iframe sandbox、preview build、版本切换、marketplace。
- Desktop 可以后置作为分发壳，本体仍然是 Web Host。

### 当前产品原则：New-chat-first, Workbench-growing

首页应该先是一个极简新对话，不是 Space Home，也不是工作台市场。

核心心智：

> 用户先从普通对话工作台开始做事；当任务过程中出现可复用的界面和流程，再保存成下一次更好用的专属工作台。

第一版不做：

- Space Home
- 工作台市场
- 连接器中心
- 技能中心
- 自动化中心
- 复杂项目层级

第一版只保留：

```text
左侧：新对话 / 历史 / 工作台 / 设置
中间：Chat
右侧：材料 / 结果
```

## 2. 可复用项目定位

### `vendor/hermes-agent`

完全复用为底层 runtime。

关键接口：

- `POST /v1/responses`：适合普通对话和实时工具流。
- `POST /v1/runs`：适合长任务、空间进化任务。
- `GET /v1/runs/{run_id}/events`：SSE 监听任务事件。
- `POST /v1/runs/{run_id}/approval`：处理高风险操作审批。
- `POST /v1/runs/{run_id}/stop`：中断任务。
- `GET /v1/capabilities`：探测能力。
- `GET /health`：探活。

Hermes dashboard 默认 `:9119`，提供 config、sessions、skills、jobs 等管理 API。

### `vendor/hermes-workspace`

不作为最终产品直接 fork，但高度参考。

它已经证明：

- 可以零 fork 连接 vanilla Hermes Agent。
- Web 外壳可以同时连接 `:8642` gateway 和 `:9119` dashboard。
- React/Vite/TanStack 的前端形态可行。
- Electron/PWA 都有现成经验。
- `/v1/responses` streaming 可以渲染 live tool calls。

适合借鉴/复制的模块思路：

- gateway capability probe
- connection settings
- SSE stream parser
- tool event rendering
- sessions / memory / skills / jobs API client
- terminal/file browser 思路

不照搬的地方：

- 首页和导航不能继续是 command center。
- 不做以 chat 为中心的产品骨架。
- 不把 swarm / operations / conductor 作为第一阶段重点。

### `vendor/hermes-agent-self-evolution`

作为长期 Evolution Engine 参考。

它的重点是优化 Hermes 自身技能、prompt、tool description、代码。我们的第一阶段不做 GEPA / DSPy 级别的优化，但要借鉴它的原则：

- 离线生成候选改动。
- 用测试和约束 gate。
- 生成 diff 和指标。
- human review 后再应用。
- 所有进化都可回滚。

## 3. 推荐工程结构

建议在当前仓库中建立自己的产品代码，不直接混进 `vendor/`。

```text
nextaichat/
  AI_SPACE_PRODUCT_MEMO.md
  RESEARCH_NOTES.md
  IMPLEMENTATION_PLAN.md

  vendor/
    hermes-agent/
    hermes-workspace/
    hermes-agent-self-evolution/

  apps/
    host-shell/
      src/
        routes/
        components/
        server/
        lib/
      package.json

  packages/
    hermes-client/
      src/
        index.ts

    space-sdk/
      src/
        index.ts
        permissions.ts
        post-message.ts

    space-runtime/
      src/
        index.ts

  spaces/
    ppt-studio/
      package.json
      space.json
      src/
        index.tsx

  evolution/
    prompts/
      space-evolution.md
    scripts/
      create-evolution-task.ts
      run-preview.ts
      apply-version.ts
```

## 4. 核心模块设计

### 4.1 Host Shell

Host Shell 是稳定母体。

负责：

- Space 列表
- Space 路由
- Agent side panel
- Hermes 连接状态
- Space 权限
- evolution proposal
- preview / apply / rollback
- 版本历史

第一版页面：

```text
/                 Space Home
/spaces/ppt       PPT Studio
/spaces/ppt/preview/:version
/evolution/:taskId
/settings/hermes
```

### 4.2 Hermes Client

独立封装 Hermes API，避免 UI 组件直接散落 `fetch`。

当前已先做一个单文件版本：

```text
packages/hermes-client/src/index.ts
```

已包含：

```ts
hermes.gateway.health()
hermes.gateway.capabilities()
hermes.dashboard.status()
hermes.runs.create()
hermes.runs.streamEvents()
```

后续扩展为：

```ts
hermes.gateway.health()
hermes.gateway.capabilities()
hermes.responses.stream()
hermes.runs.create()
hermes.runs.events()
hermes.runs.approve()
hermes.runs.stop()
hermes.dashboard.status()
hermes.dashboard.skills()
hermes.dashboard.sessions()
```

对话用 `/v1/responses`，长任务用 `/v1/runs`。

### 4.3 Space Manifest

每个 Space 都有一个 manifest。

当前第一个真实 manifest：

```text
spaces/ppt-studio/space.json
```

示例结构：

```json
{
  "id": "ppt-studio",
  "name": "PPT Studio",
  "type": "productivity.presentation",
  "entry": "src/App.tsx",
  "agent": {
    "defaultInstructions": "You are helping the user create and evolve presentation workflows.",
    "memoryScope": "space:ppt-studio",
    "skills": ["presentation-planning", "slide-critique", "brand-kit"]
  },
  "permissions": {
    "files": "workspace",
    "network": "limited",
    "shell": "approval-required"
  }
}
```

### 4.4 Space SDK

Generated Space 不能直接访问核心系统，只能通过 Space SDK。

第一版 SDK 能力：

```ts
space.agent.run(task)
space.agent.stream(message)
space.files.pick()
space.files.read(fileId)
space.files.write(fileId, content)
space.memory.get(key)
space.memory.set(key, value)
space.evolution.propose(changeRequest)
space.permissions.request(scope)
```

后续如果 Space 运行在 iframe 中，SDK 通过 `postMessage` 和 Host 通信。

### 4.5 Space Runtime

第一阶段建议分两层：

1. 官方内置 Space：作为普通 React route 运行。
2. AI 生成/用户生成 Space：作为 iframe sandbox 运行。

这样能兼顾开发速度和安全边界。

PPT Studio v0 可以先作为内置 route，不急着一开始就全部 iframe 化。

### 4.6 Evolution Engine

Evolution Engine 不是训练模型，而是让 Hermes Agent 修改 Space 代码，并通过预览和审批生效。

基本流程：

```text
用户在 Space 中完成任务
  ↓
Host 生成 evolution proposal
  ↓
用户点击“预览升级”
  ↓
Host 调 Hermes /v1/runs
  ↓
Hermes 在限定目录内修改 Space 代码
  ↓
Host 运行 lint/build/test
  ↓
Host 启动 preview
  ↓
用户查看 diff + preview
  ↓
用户 apply 或 discard
  ↓
apply 后生成版本记录
```

关键边界：

- 第一阶段只允许改 `spaces/*` 和 `packages/space-sdk` 的少量声明文件。
- 不允许改 `apps/host-shell` 核心权限、认证、billing、Hermes client。
- 每次 evolution 都在单独 git branch 或 worktree 中运行。
- 没有通过 build/test 的版本不能 apply。

## 5. MVP 范围

MVP 只验证一个闭环：

> 用户在 PPT Studio 完成一次任务后，系统能让 Hermes Agent 提议并生成一个可预览、可回滚的 Space 改进。

### MVP 包含

- Hermes 连接设置
- Space Home
- 手写 PPT Studio v0
- Agent side panel
- `/v1/responses` 对话流
- `/v1/runs` 长任务流
- evolution task 页面
- 代码 diff 展示
- preview build
- apply / rollback

### MVP 不包含

- Marketplace
- 多用户协作
- 支付
- 企业权限
- 真正任意 Space 生成
- GEPA/DSPy 自动优化
- 完整 Companion World
- 完整桌面 App

## 6. 第一版 PPT Studio

PPT Studio v0 的目标不是做完整 PowerPoint，而是证明场景化界面能召唤更具体需求。

第一版模块：

```text
Outline
Slides
Brand Kit
Speaker Notes
Agent Panel
Export Stub
Evolution Suggestions
```

第一版数据可以先用本地 JSON / Zustand 状态，不急着接复杂数据库。

示例交互：

1. 用户输入：“我要做一份融资路演 PPT。”
2. Hermes 生成 deck outline。
3. PPT Studio 显示 outline 和 slide list。
4. 用户继续让 Agent 优化某页。
5. 任务结束后，系统提示：

   > 我发现你在做 Pitch Deck。要不要把 PPT Studio 升级成 Pitch Deck Studio，新增投资人 Q&A、竞品页生成器和指标页模板？

6. 用户点击预览。
7. Hermes 修改 `spaces/ppt-studio/*`。
8. Host 展示新版本 preview。
9. 用户 apply。

## 7. 阶段计划

### Phase 0：环境跑通和验证

目标：确认 Hermes 本地服务、workspace 参考项目、API 事件流都能跑。

任务：

- 安装并运行 `vendor/hermes-agent`
- 启动 `hermes gateway run`
- 启动 `hermes dashboard`
- 验证 `curl http://127.0.0.1:8642/health`
- 验证 `curl http://127.0.0.1:9119/api/status`
- 跑一次 `/v1/responses` stream
- 跑一次 `/v1/runs` + SSE events
- 研究并记录 `hermes-workspace` 的 responses stream client

产出：

- `docs/HERMES_RUNTIME_NOTES.md`
- 本地 `.env.example`
- `scripts/hermes-smoke.mjs`

建议 smoke script 覆盖：

```text
1. GET  /health
2. GET  /v1/capabilities
3. POST /v1/responses      stream=false
4. POST /v1/runs
5. GET  /v1/runs/{run_id}/events
6. GET  /api/status        dashboard
```

这会成为之后 Host Shell 接 Hermes 前的基线测试。

### Phase 1：Host Shell 骨架

目标：做出极简空工作台 Chat 外壳。

任务：

- 初始化 `apps/host-shell`
- 建立新对话首页
- 建立普通对话工作台
- 建立右侧材料/结果面板
- 暂时隐藏连接器、技能、自动化等复杂入口
- 建立 settings / Hermes connection 页面
- 封装 `packages/hermes-client`
- 显示 gateway/dashboard health
- 接入基础 Chat

验收：

- 打开首页看到“今天想让 AI 帮你做什么？”和输入框。
- 点击新对话进入普通对话工作台。
- Chat 可用，右侧可以承载材料和结果。
- Hermes 不在线时有清楚的连接引导。

### Phase 2：PPT Studio v0

目标：用手写 Space 证明场景化 UI。

任务：

- Outline panel
- Slide list panel
- Slide detail panel
- Brand Kit panel
- Speaker Notes panel
- Agent 生成 outline 并写回 Space 状态
- Agent 根据当前 slide 上下文回答

验收：

- 用户能从一句需求生成 deck outline。
- 用户能围绕某页 slide 继续对话。
- UI 明显不是普通聊天框。

### Phase 3：Evolution v0

目标：让 Hermes 修改 Space 代码，并通过 preview/apply 生效。

任务：

- 新增 evolution proposal model
- 新增 evolution task 页面
- 用 `/v1/runs` 发起改造任务
- 限定 Hermes 修改 `spaces/ppt-studio/*`
- 生成 diff summary
- 跑 lint/build
- 启动 preview
- 用户 apply/discard
- apply 后创建版本记录

验收：

- Hermes 能新增一个小功能，例如 `Investor Q&A` 面板。
- 用户能看到 diff 和 preview。
- 用户 apply 后新功能出现在 PPT Studio。
- 用户能 rollback。

### Phase 4：Space Runtime 安全边界

目标：让 generated Space 和 Host 有清晰边界。

任务：

- 定义 `space.json`
- 定义 Space SDK
- iframe sandbox prototype
- postMessage bridge
- permission broker
- 禁止 generated Space 直接访问 Host secrets

验收：

- 一个 generated demo Space 可以在 iframe 中运行。
- 它只能通过 Space SDK 调用 Host 能力。

### Phase 5：多 Space 和桌面壳

目标：在 PPT 跑通后扩展。

候选：

- Research Lab
- Companion World
- Creator Studio

桌面：

- PWA 优先。
- Tauri/Electron 后置。
- 可以参考 `hermes-workspace/electron`。

## 8. 第一周任务建议

第一周不要急着做完整产品，先把技术闭环钉住。

建议任务：

1. 跑通 Hermes Agent 本地服务。
2. 跑通 `hermes-workspace`，确认它如何连接 `:8642` 和 `:9119`。
3. 写一个最小 `hermes-client` 脚本：

   - health
   - capabilities
   - responses stream
   - runs + events

4. 初始化 Host Shell。
5. 做 Space Home 静态页。
6. 做 PPT Studio 静态 UI。
7. 在 PPT Studio 里接一个最小 Agent side panel。

一周结束时要能 demo：

```text
打开我们的 Web
  -> 进入 PPT Studio
  -> 输入一句话
  -> Hermes 流式返回
  -> UI 把结果显示在 PPT 工作台中
```

## 9. 关键风险和对应策略

### 风险：变成 Hermes Workspace 换皮

策略：首页和核心导航必须足够简单：新对话是入口，普通对话是默认工作台。差异化不靠堆功能，而靠任务中长出界面、保存为工作台、自进化。

### 风险：一开始就做任意代码生成，失控

策略：第一阶段只允许 Hermes 修改 `spaces/ppt-studio/*`，不碰 Host Core。

### 风险：Hermes API 事件不够产品化

策略：先封装 `packages/hermes-client`，在我们自己的事件模型里标准化。

### 风险：preview/apply 做重了

策略：第一版可以用 git commit + local preview，不做复杂多租户。

### 风险：PPT Studio 交付物太复杂

策略：第一版不生成真正 `.pptx`，先生成结构化 deck 和页面内容。后续再接 PPTX export。

## 10. 下一步最具体行动

建议下一步直接做 Phase 0：

```text
1. 安装/运行 Hermes Agent
2. 验证 :8642 gateway
3. 验证 :9119 dashboard
4. 写 Hermes API smoke script
5. 再初始化 host-shell
```

Phase 0 过了之后，再正式进入产品代码开发。

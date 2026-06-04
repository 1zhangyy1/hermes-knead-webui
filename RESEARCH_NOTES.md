# AI Space Platform 调研笔记

日期：2026-05-18

> 2026-05-23 更新：本文保留调研材料，但早期结论中 “Space-first / 首页应该是 Space” 已废弃。当前以 [当前产品认知：自进化工作台](docs/PRODUCT_DIRECTION_CURRENT.md) 为准：**新对话是入口，普通对话是默认工作台；专属工作台从对话任务中沉淀出来。**

## 1. 结论先行

当前没有一个成熟开源项目可以直接作为“自进化工作台”完整复用。

更合理的路线是：

> Hermes Agent 完全复用为底层 Agent Runtime；我们自建极简产品外壳，第一版先做好空工作台 Chat，再让任务界面和专属工作台逐步长出来。

我们的产品范式是：

```text
Self-evolving Workbench
用户从新对话进入普通对话工作台
  -> Agent 完成任务
  -> 任务中出现材料、结果和临时界面
  -> 用户保存可复用流程和界面
  -> 用户预览并批准
  -> 工作台进化
  -> 下次使用更顺手
```

这和主流项目的差异：

```text
Open WebUI / LibreChat / LobeChat：Chat shell
AnythingLLM：RAG + workspace + agent productivity
Dify / Flowise：workflow / LLM app builder
Dyad / Lovable / Bolt：prompt-to-app builder
Hermes Agent：self-improving agent runtime
```

我们要做的是另一层：

```text
Hermes Agent 当完整底层 Agent Runtime / Agent OS
Web Host Shell 当稳定母体
AI Spaces 当场景化子应用
Evolution Engine 当自我改造机制
Sandbox / Version / Review 当治理层
```

## 2. Web 还是 App

建议：先做 Web-first，再用 Tauri 或 Electron 包成桌面 App。

原因：

1. AI Spaces 本质上更像 Web 子应用。

   每个 Space 都可以是一个独立 React/Vue/Svelte bundle，通过 iframe、micro frontend、sandbox origin 运行。Web 天然适合动态预览、版本切换、分享、市场和远程更新。

2. 自进化代码更容易在 Web 里验证。

   Agent 修改 Space 代码后，可以直接启动 preview、跑构建、跑 Playwright、截图对比、展示 diff。桌面端第一阶段会多出安装包、签名、更新、系统权限等复杂度。

3. Marketplace 更适合从 Web 开始。

   如果未来用户可以分享、复制、出售 Space，Web 分发路径更自然。

4. 桌面能力可以后置补上。

   当需要本地文件、通知、系统托盘、快捷键、后台任务、长期运行 Agent 时，再用 Tauri/Electron 做外壳。桌面壳内部仍然加载同一套 Web Host。

推荐形态：

```text
Phase 1: Web / PWA
Phase 2: Web + Hermes Agent sidecar
Phase 3: Tauri/Electron desktop wrapper
```

短期不要做纯原生 App。那会过早锁死 UI 迭代和 generated Space 的运行方式。

## 3. 成熟项目地图

### 3.1 Hermes Agent

项目：[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)

定位：自进化 Agent runtime。

官方 README 的核心表述是：Hermes 是 self-improving AI agent，有 built-in learning loop，会从经验创建 skills，在使用中改进 skills，持久化知识，搜索历史对话，并跨 session 建立用户模型。

直接复用：

- Agent loop
- skills system
- memory
- tools / toolsets
- MCP integration
- cron / scheduled tasks
- messaging gateway
- provider abstraction
- CLI / remote agent infrastructure
- OpenAI-compatible API server
- `/v1/runs` async run API
- `/v1/runs/{run_id}/events` SSE event stream
- `/v1/runs/{run_id}/approval` approval API
- `/v1/runs/{run_id}/stop` stop API

不从 Hermes 复用：

- 最终产品 UI
- AI Space Host Shell
- generated UI runtime
- Space Marketplace
- preview / approve / rollback 的产品化流程

判断：

> Hermes Agent 完全复用为我们的底层 Agent Runtime / Agent OS，但不是最终产品外壳。

### 3.2 Open WebUI

项目：[open-webui/open-webui](https://github.com/open-webui/open-webui)  
功能文档：[Open WebUI Features](https://docs.openwebui.com/features/)

定位：成熟的 self-hosted AI interface / Chat shell。

值得关注的能力：

- 多模型聊天
- 文件上传、RAG、知识库
- memory
- automations
- task management
- notes / channels
- open terminal
- file browser
- website preview
- Python tools / functions
- pipelines
- MCP / OpenAPI extensibility
- multi-user / permissions

优点：

- 成熟度高
- 功能很全
- 已经有 terminal、website preview、tool/function workspace
- 有多用户和权限基础

问题：

- 产品心智仍然是“聊天中心”。
- 要改成 AI Space 平台会比较重。
- 代码和架构已经很大，fork 后容易被原产品范式牵着走。
- 当前许可包含 Open WebUI License / branding 条款，需要认真评估商业产品风险。

判断：

> 可以参考它的 Chat、Tools、Terminal、Preview、Permissions，但不建议直接作为我们长期产品基座。

如果只是快速 demo，可以 fork；如果要做有强产品身份的长期产品，建议自建 Host Shell。

### 3.3 AnythingLLM

项目：[Mintplex-Labs/anything-llm](https://github.com/Mintplex-Labs/anything-llm)

定位：all-in-one AI productivity / private ChatGPT / workspace + docs + agents。

值得关注的能力：

- Desktop app
- workspace
- docs / RAG
- AI agents inside workspace
- no-code AI agent builder
- MCP compatibility
- multi-user Docker version
- developer API
- Vite + React frontend、Node Express server、collector

优点：

- 有 workspace 心智，比纯 ChatGPT clone 更接近我们的空间概念。
- 有桌面版和本地优先体验。
- 用户对“workspace + agent + docs”的理解成本低。

问题：

- 重点仍然是文档/RAG/生产力助手。
- Space 不是可被 Agent 改代码的子应用。
- UI 没有围绕“场景空间自我进化”设计。

判断：

> 适合参考 workspace、desktop、本地优先、agent skill 配置，但不建议整体 fork。

### 3.4 Dyad

项目：[dyad-sh/dyad](https://github.com/dyad-sh/dyad)

定位：local open-source AI app builder，明确对标 Lovable / v0 / Bolt。

适合复用/参考：

- AI 生成前端代码
- 本地 preview
- 修改代码后的迭代修复
- app builder 的工程流程
- 生成项目的依赖管理和运行方式

不适合复用：

- 产品范式
- 用户目标
- 主交互闭环

关键差异：

```text
Dyad / Lovable
  用户目标：我要造一个 app
  交付物：一个外部应用
  体验：prompt -> generate -> preview -> deploy

我们的产品
  用户目标：我要完成工作/获得陪伴/解决问题
  交付物：一个持续进化的 AI Space
  体验：use -> adapt -> evolve -> reuse
```

判断：

> Dyad 不能当产品蓝本，但很适合研究 generated UI preview / AI coding loop。

### 3.5 LibreChat / LobeChat

项目：

- [danny-avila/LibreChat](https://github.com/danny-avila/LibreChat)
- [lobehub/lobe-chat](https://github.com/lobehub/lobe-chat)

定位：成熟 ChatGPT clone / AI chat framework。

适合参考：

- 多模型接入
- Chat UI 体验
- agents / presets
- artifacts
- MCP / plugin marketplace
- auth / deployment

问题：

- 强 chat-centric。
- Space 维度弱。
- Agent 改自身应用代码不是主线。

判断：

> 适合参考局部 UI 和插件生态，不适合做母体。

### 3.6 Dify

项目：[langgenius/dify](https://github.com/langgenius/dify)  
官网：[dify.ai](https://dify.ai/)

定位：production-ready agentic workflow builder / LLM app development platform。

适合参考：

- workflow builder
- RAG pipeline
- model provider management
- observability
- app publishing
- marketplace
- enterprise deployment

问题：

- 范式是“构建 AI 应用/工作流”，不是“用户使用过程中 Space 自我进化”。
- 系统很重，直接改容易变成另一个 workflow builder。

判断：

> 适合参考 workflow、应用发布、市场、企业治理，不适合做第一版产品外壳。

## 4. 为什么不建议整体 fork

整体 fork 的风险不是技术，而是产品方向。

如果 fork Chat shell，产品会自然滑向：

```text
更好的聊天框
更多工具
更多插件
更多知识库
```

如果 fork app builder，产品会自然滑向：

```text
帮用户生成外部 app
prompt-to-app
preview / deploy
```

如果 fork workflow builder，产品会自然滑向：

```text
节点编排
RAG pipeline
企业自动化
```

这些都不是我们的核心。

我们的核心是：

> 用户完成具体任务后，Agent 把这次协作沉淀成下一次可直接使用的软件空间。

所以推荐策略是：

```text
自建 Host Shell
完全复用 Hermes Agent Runtime
参考 Dyad 的 generated UI preview
参考 Open WebUI / AnythingLLM 的 tools、workspace、permissions
参考 Dify 的 workflow / marketplace / observability
```

## 5. 推荐技术架构

### 5.1 第一版架构

```text
Next.js / React Host Shell
  - Home
  - Space list
  - Space router
  - Agent panel
  - Preview / Apply / Rollback UI

Hermes Agent Runtime
  - memory
  - skills
  - tools
  - model providers
  - task execution

Space Runtime
  - generated React apps
  - iframe sandbox
  - shared Space SDK
  - capability broker

Version System
  - git branch or snapshot per Space
  - diff
  - preview build
  - rollback

Persistence
  - Postgres / SQLite for metadata
  - object storage for generated bundles and assets
  - vector store later if needed
```

### 5.2 关键模块

#### Host Shell

稳定母体，不轻易被 Agent 修改。

负责：

- 登录
- 用户
- Space 列表
- 权限
- 文件
- 模型配置
- billing
- audit log
- runtime registry
- Space version registry

#### AI Space

每个 Space 是一个场景子应用。

包含：

- UI bundle
- agent config
- tools
- memory scope
- workflow
- permissions
- version history

#### Space SDK

所有 generated Space 不能直接访问核心系统，只能通过 SDK 调用能力。

示例：

```ts
space.files.pick()
space.files.read(fileId)
space.agent.run(task)
space.deck.create(input)
space.memory.get(key)
space.actions.requestPermission(scope)
```

#### Capability Broker

Host 统一处理所有高风险能力。

例如：

- 文件读写
- 网络请求
- 邮件发送
- 支付
- 用户数据访问
- 系统命令
- 模型调用

#### Evolution Engine

让 Agent 修改 Space 的代码，而不是裸改 Host Core。

流程：

```text
Create evolution task
  -> checkout current Space version
  -> Agent edits generated Space code
  -> install/build/test
  -> launch preview
  -> screenshot / smoke test
  -> summarize change
  -> ask user to approve
  -> apply version or discard
```

## 6. MVP 推荐

第一场景仍然建议选 PPT Studio。

原因：

- 用户需求具体
- UI 差异明显
- 交付物明确
- 反复修改频繁
- 很容易体现“下一次变简单”
- 适合做 template / marketplace

MVP 不需要一上来让 Agent 生成完整 Space。可以分三步：

```text
Step 1: 手写 PPT Studio v0
  - outline
  - slides
  - brand kit
  - speaker notes
  - chat/agent panel

Step 2: 接 Hermes
  - 让 Agent 能读当前 Space 状态
  - 能生成 deck outline
  - 能改 slides 数据
  - 能保存 workflow / memory / skill

Step 3: 允许 Agent 修改 spaces/ppt-studio/*
  - 新增一个小面板
  - 新增一个 workflow
  - 新增一个 action button
  - 通过 preview/apply 生效
```

第一版要验证的不是“能不能生成任意 app”，而是：

> 用户做完一次 PPT 后，系统能否把这个流程沉淀成更适合下次使用的 PPT 工作台。

## 7. 推荐路线图

### Phase 0: 调研和技术验证

- 跑通 Hermes Agent
- 理解 Hermes skills / memory / tools / MCP
- 研究 Dyad 的 generated app preview 流程
- 确定 Host Shell 技术栈
- 确定 iframe sandbox / preview 方案

### Phase 1: Web Host Shell

- Space list
- Space router
- Agent side panel
- Space metadata
- 基础权限模型
- 手写 PPT Studio

### Phase 2: Hermes Agent 完全复用

- Hermes Agent 作为 sidecar service
- Host 调 Hermes 执行任务
- Space 状态作为上下文注入给 Hermes
- Hermes 结果回写 Space
- 不重写 Hermes 的 agent loop、memory、skills、tools、gateway、approval、cron、MCP

### Phase 3: Space Evolution

- Agent 修改 `spaces/ppt-studio/*`
- preview build
- diff summary
- smoke test
- user approve
- version apply / rollback

### Phase 4: 多 Space

- Research Lab
- Companion World
- Creator Studio
- 每个 Space 有独立 agent config / memory scope / tools

### Phase 5: Desktop

- Tauri/Electron wrapper
- local file access
- background agent
- local notification
- tray
- local model / local Hermes sidecar

### Phase 6: Marketplace

- Space publish
- duplicate/fork
- ratings
- remix
- paid templates

## 8. 风险点

### 8.1 被普通 Chat 产品带偏

风险不是“首页有聊天框”，而是“只有聊天框，没有任务状态、材料、结果和可演化任务界面”。

当前判断：首页应该是 `新对话 / 普通对话工作台`，不是 Space 列表。差异化来自对话过程中长出的任务界面，以及后续保存和自进化。

### 8.2 被 App Builder 带偏

如果核心流程变成 prompt-to-app，我们会变成 Dyad/Lovable。

我们的核心必须是 use-to-evolve。

### 8.3 Agent 改代码风险

必须有：

- sandbox
- permission broker
- preview
- tests
- diff summary
- user approval
- rollback

### 8.4 过早做 marketplace

没有强 Space 之前做市场，会变成空货架。

### 8.5 过早做太多空间

早期先把一个空间做深，不要把 10 个空间都做浅。

## 9. 当前推荐决策

### 是否基于 Hermes

是。Hermes Agent 完全复用，作为底层 Agent Runtime / Agent OS。

不要把 Hermes UI 当最终产品。

### 是否 fork 现成 Web UI

不建议长期 fork。

可以短期参考或拆模块，但 Host Shell 建议自建。

### Web 还是 App

先 Web。

App 作为后续分发壳。

### 第一场景

PPT Studio。

### 第一版最小闭环

```text
用户在 PPT Studio 做一次任务
  -> Hermes 完成任务
  -> Hermes 建议升级 PPT Studio
  -> Agent 修改 spaces/ppt-studio/*
  -> 生成 preview
  -> 用户 approve
  -> 新版本生效
```

## 10. 一句话结论

不要找一个项目来“套壳”。我们要做的产品外壳本身就是创新部分。

最稳的路线是：

> 自建 Web Host Shell，完全复用 Hermes Agent Runtime，参考 Dyad 的代码预览链路，吸收 Open WebUI / AnythingLLM 的工具与权限经验，先用 PPT Studio 跑通 use-to-evolve 闭环。

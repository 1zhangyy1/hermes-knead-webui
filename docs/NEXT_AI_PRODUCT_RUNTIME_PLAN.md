# Next AI 产品运行时完整 Plan

日期：2026-06-04
状态：执行版。本文以代码走查结果为准，作为后续实现和验收主线。

## 1. 当前产品判断

Next AI 不是普通 AI 助手列表，也不是工作台管理器，更不是 Lovable 式外部 app builder。

当前正确心智：

```text
Next AI 是一个 AI 产品母体。
用户可以选择、创建、使用和进化很多 AI 产品。
每个 AI 产品都有自己的聊天入口、任务历史、能力配置、workspace 和可按需长出的产品界面。
```

最小正确体验：

```text
选择一个 AI 产品
-> 说一句任务
-> Chat 始终在场
-> 任务需要结构时，AI 产品在自己的 workspace 里写出产品界面
-> 右侧 preview 展示这个产品界面
-> 用户继续聊天，要求它完成任务或改进自己的界面
-> 系统能恢复上一版
```

用户不需要理解：

- workspace
- manifest
- version directory
- hidden prompt
- app builder
- workbench manager
- block schema

用户只需要理解：

```text
我选中了一个 AI 产品。
我跟它聊天。
它会把自己变得越来越适合这类任务。
```

## 2. 必须守住的职责边界

### 2.1 母体 shell 负责

这些是 Next AI 稳定写死的核心能力：

- AI 产品库和当前产品选择。
- 新建 AI 产品入口。
- Chat、composer、session、队列、工具调用卡片。
- product workspace 创建、绑定和校验。
- product context 注入。
- 产品 preview iframe。
- preview 四态：empty、generating、ready、failed。
- snapshot、rollback、retry。
- 产品级 skills/tools 入口。
- 错误、失败、权限、恢复等基础状态。

### 2.2 Hermes Agent 负责

这些不应该由母体 shell 提前写死，而应该由当前 AI 产品自己长出来：

- PPT 产品的主题、受众、页数、风格、大纲、页面缩略、讲稿区。
- 图片产品的提示词、风格、比例、参考图、历史图。
- 研究产品的资料卡片、来源、引用、结论、待验证问题。
- 数据产品的字段、表格、筛选、图表、洞察、导出。

母体提供运行环境，Agent 写业务 UI。这样才能覆盖很多 AI 产品，而不是每个产品都靠前端硬编码。

### 2.3 block 的边界

block 适合稳定核心交互：

- Chat message。
- Tool call / thinking card。
- Approval / error / retry。
- Product preview state。
- Snapshot / rollback 状态卡。
- 文件上传、任务状态、权限确认。

block 不适合承包所有产品业务 UI。

原因：

```text
PPT、图片、研究、数据的好用界面差异很大。
如果都由我们写 block，系统会退回硬编码工作台。
真正本质的机制是：AI 产品能在自己的 workspace 里写文件，preview 能显示，用户能继续要求它改。
```

MVP 决策：

```text
母体核心交互用稳定 block。
产品业务界面让 Hermes Agent 写 index.html/style.css/app.js。
后续再把常用控件沉淀成可选 SDK，而不是一开始就限制 Agent。
```

## 3. 代码走查事实

### 3.1 后端产品注册表已成立

文件：`vendor/hermes-webui/api/products.py`

已经具备：

- `GET /api/products` 产品列表。
- `POST /api/products/create` 创建产品。
- `POST /api/products/update` 更新产品。
- `POST /api/products/delete` 删除产品。
- 自动创建 `spaces/products/<product_id>`。
- 自动写 `product.json`、`README.md`、seed `index.html`。
- 产品字段：`ui_status`、`last_session_id`、`sessions`、`skills`、`tools`、`versions`。
- 内置产品 `ppt-designer`。
- 内置产品删除保护。
- `product_file_status()` 可判断 entry 是否存在、是否 seed、是否 generated。
- snapshot、versions、rollback 能力。

已补齐：

- 产品资产版本化已覆盖产品目录中的小型 UI 资产；rollback 会恢复快照文件，并移除当前版本新增的受管理资产。

### 3.2 产品上下文已由后端注入

文件：`vendor/hermes-webui/api/product_context.py`

已经具备：

- 前端发送结构化字段：`product_id`、`product_scope`、`product_intent`。
- 后端读取产品对象，生成 ephemeral product prompt。
- 支持 scope：`product_usage`、`product_init`、`product_builder`。
- 后端有兜底 intent classifier，明显涉及界面、布局、流程、以后、默认、字段、按钮、面板，以及“参考资料栏 / 模板选择放上面 / 页数选择”等自然 UI 说法时进入 `product_builder`。
- `product_init` 要求 Agent 直接创建第一版产品界面。
- `product_builder` 要求 Agent 修改产品 workspace 文件。
- `product_usage` 默认完成任务，不强制改 UI。
- 空界面或失败界面的产品会优先进入 `product_init`，不再只对 PPT 做特殊处理。
- 运行中 `/steer` accepted 路径会携带结构化 product context；当 steer 文本是 UI 生成/改造意图时，后端会把 product runtime 契约注入给当前 agent。
- 明确禁止 product runtime 输出旧 `next-ai-workbench` JSON。

### 3.3 Session 能绑定产品 workspace

文件：`vendor/hermes-webui/static/sessions.js`

已经具备：

- `newSession(options)` 支持 `workspace`、`productId`、`productScope`、`productIntent`。
- 新 session request body 会带 `product_id/product_scope/product_intent`。
- session 本地对象会保存 `product_id/product_scope/product_intent`。
- 加载历史 session 时可以根据 `session.product_id` 恢复当前产品。

后端：

- `/api/session/new` 会校验产品 workspace 和 session workspace 一致。
- `/api/chat/start` 会再次解析 workspace 并校验 product context。

### 3.4 前端 product context 主路径已接上

文件：`vendor/hermes-webui/static/messages.js`

已经具备：

- 主 `send()` 路径发送结构化 product context。
- 用户可见消息不再拼 `[Next AI 产品定义]`。
- `_sendInProgress` queue、busy queue、busy interrupt、chat/start conflict queue、goal continuation、pending steer leftover 已补齐 product context。

仍待补：

- 后续拆文件时需要保留这些路径，避免重构时漏回去。

### 3.5 运行时已开始拆分

文件：`vendor/hermes-webui/static/product-shell-runtime.js`

已经具备：

- AI 产品选择、首页、任务列表和通用 workbench shell。
- 后端产品 hydrate 入口。
- 产品创建入口。
- active product preview shell。
- 产品 rollback。
- PPT 内置产品绑定。
- 旧 workbench 主路径已移除：不再从 Chat 自动提案、自动打开、保存默认界面。

已拆出：

- `static/product-store.js`：产品 hydrate、后端产品合并、默认 skills/tools、产品能力弹窗。
- `static/product-runtime.js`：product context、product_init、产品 preview 刷新、preview 四态、轮询。
- `static/product-evolution.js`：产品界面 rollback。

当前问题：

- 旧 `/api/workbenches*`、`panels.js` Workbenches 面板、`static/workbench-legacy.js` 已删除。
- 前端已删除历史 `next-ai-workbench` 标签清洗和 proposal 特殊渲染，不再为旧协议保留展示兼容。
- 可见主路径里的“工作界面/任务界面”已收敛为“产品界面”；代码内部仍有少量历史 DOM id/class 命名壳，按需再改。

结论：

短期主路径已经拆出 store/runtime/evolution/legacy，下一步进入 PPT 产品 UI 走查：

```text
spaces/products/ppt-designer/
```

### 3.6 PPT 设计师已成为第一个标准产品样例

产品目录：`spaces/products/ppt-designer/`

已经具备：

- `index.html`
- `style.css`
- `app.js`
- `product.json`
- `README.md`

当前状态：

- `ppt-designer` 是内置 backend product。
- `AI_OBJECTS.ppt` 不再携带旧推荐工作台字段。
- 如果产品界面仍为空或失败，首次产品消息会触发 `product_init`。
- 真实 Hermes Agent turn 已写出第一版 PPT 产品 UI。
- `/api/products/ppt-designer/preview` 可渲染。

仍待补：

- PPT UI 视觉和交互还需要继续用真实任务走查打磨。

## 4. 产品数据模型

MVP 产品对象：

```json
{
  "id": "ppt-designer",
  "kind": "ppt",
  "title": "PPT 设计师",
  "desc": "把想法、资料和要求变成清晰好看的演示文稿。",
  "placeholder": "描述你想做的 PPT，或上传资料...",
  "source_prompt": "内置 AI 产品：PPT 设计师。",
  "product_type": "ppt",
  "workspace_path": "/.../spaces/products/ppt-designer",
  "preview_entry": "index.html",
  "preview_url": "/api/products/ppt-designer/preview",
  "ui_status": "empty | generating | ready | failed",
  "last_session_id": "",
  "sessions": [],
  "skills": ["presentations"],
  "tools": [],
  "versions": [],
  "builtin": true
}
```

产品目录：

```text
spaces/products/<product_id>/
  product.json
  README.md
  index.html
  style.css
  app.js
  versions/
  skills/
  memory/
```

Session 关系：

```text
AI Product
  -> Task Session A
  -> Task Session B
  -> Task Session C

每个 Task Session:
  session.product_id = product.id
  session.workspace = product.workspace_path
  session.product_scope = product_usage | product_init | product_builder
```

## 5. 三条核心用户流程

### Flow A：打开产品并开始任务

```text
用户点击 PPT 设计师
-> 中间显示 PPT 设计师主页
-> 用户输入：帮我做一个介绍 Codex 的 PPT
-> newSession 绑定 ppt-designer workspace
-> /api/chat/start 带 product_id
-> 如果产品 UI 还是 seed，scope = product_init
-> 否则 scope = product_usage
-> Agent 正常完成任务
-> 需要结构化界面时，Agent 写或改产品 UI 文件
-> 右侧 preview 刷新
```

用户不需要知道 workspace、scope、manifest。

### Flow B：新建 AI 产品

```text
用户输入：我想新建一个生图图片产品
-> 前端生成 draft 名称和职责
-> 用户确认
-> POST /api/products/create
-> 后端创建产品对象和 workspace
-> 前端选中这个产品
-> 自动 newSession(product_init)
-> 自动发送原始创建需求
-> Agent 写第一版 index.html/style.css/app.js
-> ui_status: empty -> generating -> ready
-> 右侧 preview 显示 Agent 写出的产品界面
-> 用户继续普通聊天
```

这条链路必须做到：

```text
新建产品描述 -> 生成一个 AI 产品 -> 继续普通聊天 -> 边聊边生成产品界面
```

不能只生成名字。

### Flow C：改进产品界面

```text
用户说：以后讲稿区放右边
-> intent 判为 product_builder
-> 开始前 snapshot 当前 UI 文件
-> Agent 修改产品 workspace 文件
-> preview 显示新版
-> 用户可以恢复上一版
```

MVP 不做复杂 diff。能恢复上一版就足够支撑“自进化可控”。

## 6. 已完成阶段

### P0：product context 全路径

已完成：

- `currentAssistantProductContextForMessage(text, options)`。
- `withCurrentProductContext(payload, text, options)`。
- 主发送、排队发送、busy queue、busy interrupt、conflict queue、goal continuation、pending steer leftover 接入 product context。
- `/queue`、`/interrupt`、`/steer` fallback queue 接入 product context。
- queue drain 会恢复 `product_scope/product_intent`。
- 加载 session 时优先用 `session.product_id` 恢复产品。
- 后端 `infer_product_scope()` 兜底判断 builder intent。

验收状态：

- 静态检查通过。
- 后端 classifier 验证通过。
- 临时产品 API 验证通过。

### P1：snapshot/rollback 最小闭环

已完成：

- `snapshot_product(product_id, reason)`。
- `list_product_versions(product_id)`。
- `rollback_product(product_id, version_id)`。
- snapshot 只复制 `index.html/style.css/app.js/product.json`。
- `product_builder` 和二次 `product_init` 开始前自动 snapshot。
- `GET /api/products/<id>/versions`。
- `POST /api/products/<id>/snapshot`。
- `POST /api/products/<id>/rollback`。
- preview UI 有轻量恢复入口。

验收状态：

- 临时产品 v1 snapshot -> 手动 v2 -> rollback -> 磁盘恢复 v1 已验证。
- 删除临时产品时 `removed_files` 与实际磁盘删除一致。

### P2：PPT 设计师迁入标准 product workspace

已完成：

- 后端自动确保内置 `ppt-designer`。
- `spaces/products/ppt-designer/` 已创建。
- 前端 hydrate 后仍只显示一个 `PPT 设计师`。
- 内置产品删除受保护。
- `AI_OBJECTS.ppt` 不再推荐旧工作台。
- 当前对象有 product preview 时，不再追加旧“打开 PPT 工作界面吗？”提案。
- product prompt 有 PPT UI guidance。
- product runtime 禁止输出 `next-ai-workbench` JSON。

### P2.5：真实 Agent 生成 PPT 产品 UI

已完成：

- 创建真实产品 session 并触发 `product_init`。
- Hermes Agent 写入：
  - `spaces/products/ppt-designer/index.html`
  - `spaces/products/ppt-designer/style.css`
  - `spaces/products/ppt-designer/app.js`
- 产品状态 finalize 为 `ready`。
- `entry_generated=true`。
- 直接 preview 可访问并渲染。
- 主应用右侧 iframe 已挂载 product preview。

## 7. 下一阶段完整执行计划

### P3：首屏和顶部收束

目标：

让用户第一次打开页面就理解：这是 AI 产品库，选一个产品，开始任务。

要改：

- `vendor/hermes-webui/static/index.html`
- `vendor/hermes-webui/static/style.css`
- `vendor/hermes-webui/static/product-shell-runtime.js`
- `vendor/hermes-webui/static/i18n.js`

具体 Todo：

- [x] 默认隐藏 `.agent-shell-advanced`，保留 DOM。
- [x] 左侧主入口只保留：新任务、AI 产品、最近任务、设置。
- [x] 左侧产品列表只显示：通用 AI、PPT 设计师、研究分析师、数据分析师、用户创建产品、+ 新建 AI 产品。
- [x] 顶部只显示当前产品名。
- [x] 进入任务后，任务名作为弱副标题显示。
- [x] 隐藏首页解释型三段卡片，保留名称、职责、输入框、推荐任务。
- [x] preview toolbar 对 product preview 只保留：产品界面名、状态、收起、恢复上一版。
- [x] 创建、删除、恢复、改造文案在可见主路径统一为“AI 产品”和“产品界面”。
- [x] 不在首屏出现 skills、workspace、logs、kanban、profiles、legacy workbench controls。

验收：

- [x] 打开 `http://localhost:8788/` 后，不看到 manifest、workbench、logs、skills 等复杂概念。
- [x] 浏览器检查 `.agent-shell-advanced` 可见数量为 0。
- [x] 用户 3 秒内能说清：选一个 AI 产品，然后输入任务。
- [x] Chat 始终是中间主入口。
- [x] 右侧 preview 出现时，不抢走 Chat 的控制权。
- [x] 浏览器 tab 标题收束为当前产品名 + Next AI，例如 `PPT 设计师 — Next AI`。

本轮执行状态：

- [x] `index.html`：左侧创建入口改为 `新建 AI 产品`，静态设置标签改为 `设置`。
- [x] `product-shell-runtime.js`：product preview 文案缩短为 `产品界面 / 已生成，可继续聊天要求它调整`。
- [x] `product-shell-runtime.js`：product preview 的恢复入口改为直接按钮，避免旧 `更多` 菜单心智。
- [x] `boot.js`、`ui.js`、`sessions.js`：legacy `Hermes` 默认标题收束为 `Next AI`。
- [x] 验证：`node --check` 通过 `boot.js/ui.js/sessions.js/product-shell-runtime.js/messages.js/commands.js`。
- [x] 验证：`python3 -m py_compile` 通过 `products.py/product_context.py/routes.py/streaming.py`。
- [x] 验证：浏览器首屏截图确认左侧、主页、preview 都是 AI 产品语义。

### P4：新建产品链路硬化

目标：

保证“新建产品描述 -> 自动生成产品界面 -> 继续普通聊天”稳定成立。

要改：

- `vendor/hermes-webui/static/product-shell-runtime.js`
- `vendor/hermes-webui/static/messages.js`
- `vendor/hermes-webui/static/sessions.js`
- `vendor/hermes-webui/api/products.py`
- `vendor/hermes-webui/api/routes.py`
- `vendor/hermes-webui/api/streaming.py`

具体 Todo：

- [x] 新建产品后如果自动初始化失败，产品主页和 preview 都显示重试入口。
- [x] 创建产品时不要只靠规则命名，先用职责短语抽取生成更自然的产品名；后续可再升级为 Agent/model 命名。
- [x] 自动初始化消息要保持用户可见自然，技术要求只走后端 product prompt。
- [x] product_init stream 结束后主动刷新 `/api/products/<id>/status`。
- [x] 如果 Agent 没写非 seed `index.html`，明确进入 failed 并显示下一步。
- [x] 新建产品成功后最近任务里显示自然任务名，不显示 session id。

验收：

- 输入“我想新建一个生图图片产品”。
- 左侧出现“图片生成器”或更自然名称。
- 中间进入该产品聊天。
- 右侧 empty -> generating -> ready。
- 刷新页面后产品仍存在。
- 删除产品后刷新不残留。

本轮执行状态：

- [x] `product-shell-runtime.js`：产品主页根据 `uiStatus` 展示 empty/generating/failed 的下一步，failed 时提供 `重新生成界面`。
- [x] `product-shell-runtime.js`：自动初始化缺少运行时或输入框时会落到 failed，并刷新产品主页和 preview。
- [x] `product-shell-runtime.js`：手动生成/重试失败时同步 failed 状态，但不清空当前聊天上下文。
- [x] `messages.js`：product_init/product_builder stream done 后立即刷新 preview status，并追加一次短延迟刷新。
- [x] 验证：`node --check` 通过 `product-shell-runtime.js/messages.js`。
- [x] 验证：`python3 -m py_compile` 通过 `products.py/product_context.py/routes.py/streaming.py`。
- [x] 验证：临时 failed 产品 `P4 重试测试` 在产品主页和 preview 都显示 `重新生成界面`，验证后已删除。
- [x] `product-shell-runtime.js`：新增职责短语抽取命名，验证 `旅行规划师 / 简历优化师 / 内容文案师 / 客服处理师` 等自然名称。
- [x] `product-shell-runtime.js`、`sessions.js`、`routes.py`：product_init 传递并持久化 `product_task_title`，初始化任务显示为 `生成{产品名}界面`。
- [x] 验证：临时产品 `p4-title-smoke` 的 `/api/session/new` 返回 `sessionTitle: 生成旅行规划师界面`，验证后已删除临时产品和临时会话。
- [x] P4 剩余项已清空。

### P5：Chat 内产品改造状态卡

目标：

用户说“以后这样”时，能自然理解这是在改当前 AI 产品，不是普通任务回复。

要改：

- `vendor/hermes-webui/static/messages.js`
- `vendor/hermes-webui/static/product-shell-runtime.js`
- `vendor/hermes-webui/static/index.html`
- `vendor/hermes-webui/static/style.css`

具体 Todo：

- [x] product_builder turn 开始时，在 Chat 中显示轻量状态卡：`正在改这个 AI 产品的界面`。
- [x] stream done 后状态卡更新：`已生成新版产品界面`。
- [x] 如果有 snapshot，状态卡显示 `可恢复上一版`。
- [x] failed 时显示 `重新生成界面`。
- [x] 状态卡只解释当前动作，不展示代码 diff。

验收：

- 用户说“以后讲稿区放右边”。
- Chat 中能看到系统正在改产品界面。
- 右侧 preview 刷新。
- 用户能恢复上一版。

本轮执行状态：

- [x] `messages.js`：product_builder 发送后插入 running 状态卡，并保存在 INFLIGHT，支持刷新恢复。
- [x] `messages.js`：stream done 后等待 product preview status 刷新，再显示 done/failed 状态卡。
- [x] `messages.js`：apperror/connection lost 路径会把 running 卡替换为 failed 卡。
- [x] `ui.js`、`style.css`：status-card 支持轻量动作按钮，支持 `重新生成界面` 和 `恢复上一版`。
- [x] `product-shell-runtime.js`：暴露当前 product preview 的只读状态，供 Chat 状态卡判断 `failed/canRollback`。
- [x] 验证：`node --check` 通过 `messages.js/product-shell-runtime.js/sessions.js/ui.js`。
- [x] 验证：浏览器 reload 后主页面正常加载。
- [x] 验证：源码级渲染测试确认 done 卡包含 `恢复上一版`，failed 卡包含 `重新生成界面`。
- [x] 真实 Agent 回归：实际发送 `next time put speaker notes panel on the right`，确认 product_builder 运行卡出现，并在完成后显示 `产品界面 / PPT 设计师 / 可恢复上一版 / 恢复上一版`。

### P6：产品级 skills/tools

目标：

每个 AI 产品可以有自己的能力，但不把技能市场放到首屏。

要改：

- `vendor/hermes-webui/api/products.py`
- `vendor/hermes-webui/api/product_context.py`
- `vendor/hermes-webui/static/product-shell-runtime.js`
- `vendor/hermes-webui/static/index.html`
- `vendor/hermes-webui/static/style.css`

具体 Todo：

- [x] 产品 manifest 保留 `skills`、`tools`。
- [x] product context prompt 注入 enabled skills/tools。
- [x] 产品设置里加“产品能力”区域。
- [x] 内置 PPT 产品默认建议 `presentations`、`office`。
- [x] 图片产品默认建议 `imagegen`。
- [x] 研究产品默认建议 browser/web research。
- [x] 数据产品默认建议 spreadsheets。
- [x] 新建产品时 Agent 可以建议需要哪些能力，但不强制用户配置。

验收：

- PPT 产品可以带 PPT 相关能力。
- 图片产品可以带生图相关能力。
- 首屏仍保持简单。

本轮执行状态：

- [x] `products.py`：新增按产品类型推断默认能力，PPT 默认 `presentations/office + skills/file/terminal/code_execution`。
- [x] `products.py`：`product.json` manifest 写入 `skills/tools`。
- [x] `product_context.py`：ephemeral prompt 注入 enabled product capabilities。
- [x] `product-shell-runtime.js`：新建产品时带上默认 `skills/tools`，并支持保存当前产品能力。
- [x] `index.html`、`style.css`：右侧产品界面 `更多 -> 产品能力` 弹层。
- [x] `sessions.js` / `routes.py`：产品 `tools` 会转成真实 Hermes `enabled_toolsets` 并保存到 session，streaming 创建 Agent 时会使用这组工具。
- [x] 验证：临时图片产品默认得到 `imagegen + skills/file/image_gen`，manifest 写入成功，并已删除临时产品。
- [x] 验证：PPT 产品能力弹层默认勾选 `presentations/office + skills/file/terminal/code_execution`，保存后后端状态保持一致。
- [x] 验证：API 临时创建 PPT 产品 session 时，旧 `officecli` 会转成 `skills/file/terminal/code_execution` 写入 `enabled_toolsets`；临时 session 和产品记录残留已清理。
- [x] 验证：`node --check` 和 `python3 -m py_compile` 通过。

### P7：拆分 runtime 文件

目标：

避免 `product-shell-runtime.js` 继续成为概念混杂的中心。

建议拆分：

```text
static/product-store.js
  后端产品列表、active product、hydrate、create、update、delete。

static/product-runtime.js
  product session、product context、preview refresh、ui_status。

static/product-evolution.js
  rollback。产品生成和改造走正常 Chat + product_init/product_builder。
```

具体 Todo：

- [x] 先搬纯函数，不改行为。
- [x] 保留旧全局函数名 wrapper，避免打断现有调用。
- [x] 每拆一块跑 `node --check`。
- [x] 每拆一块做浏览器 smoke。
- [x] 删除未再调用的旧 `buildCurrentAssistantAgentInstruction()`。
- [x] 删除旧 workbench 主路径，不保留前端兼容开关。

验收：

- 新增产品逻辑不再需要读完整 `product-shell-runtime.js`。
- 旧 workbench 不再污染 product runtime。

本轮执行状态：

- [x] 新增 `static/product-store.js`，迁出后端产品合并、默认能力、产品能力弹窗和保存逻辑。
- [x] 新增 `static/product-runtime.js`，迁出 product context、product_init、preview 刷新和产品 preview 四态。
- [x] 新增 `static/product-evolution.js`，只保留产品 rollback。
- [x] `index.html` 不再加载旧 Workbenches 面板，也不再加载 `static/workbench-legacy.js`。
- [x] `messages.js` 不再触发旧 workbench proposal、evolution request 或 iframe live-sync。
- [x] `product-shell-runtime.js` 删除旧 default/recommended workbench、自动打开、保存为默认、旧 iframe postMessage 主路径。
- [x] `panels.js` / `index.html` / `style.css` 删除旧 Workbenches panel 入口、详情区和样式选择器。
- [x] `routes.py` 删除旧 `/api/workbenches*` GET/POST 路由和 preview server。
- [x] 删除 `api/workbenches.py` 与 `static/workbench-legacy.js`。
- [x] `streaming.py` 不再给非产品会话注入旧 `next-ai-workbench` JSON 指令。
- [x] 产品预览轮询状态从主 runtime 移到 `product-runtime.js`。
- [x] 删除未再调用的旧隐藏指令生成函数；产品上下文继续只走后端 ephemeral prompt。
- [x] 脚本加载顺序更新：`product-store -> workbench-runtime -> product-runtime -> product-evolution -> panels`。
- [x] 验证：`node --check` 通过 `product-shell-runtime.js/product-store.js/product-runtime.js/product-evolution.js/messages.js/sessions.js/ui.js`。
- [x] 浏览器 smoke：页面无 console error；当前 PPT 产品 preview 仍显示；`更多 -> 产品能力` 可打开；PPT 默认能力保持 `presentations/office + skills/file/terminal/code_execution`。

### P8：PPT 产品 UI 设计走查

目标：

让第一个证明产品真正可用，不只是能渲染。

要改：

- `spaces/products/ppt-designer/index.html`
- `spaces/products/ppt-designer/style.css`
- `spaces/products/ppt-designer/app.js`

具体 Todo：

- [x] 检查首屏信息是否像一个 PPT 产品，而不是 landing page。
- [x] 确保主题、受众、页数、风格、大纲、页面缩略、讲稿区都可见且层级清楚。
- [x] 支持从 Chat 要求改 UI 后，右侧界面自然变化。
- [x] 不过度装饰，保持工作工具感。
- [x] 桌面浏览器截图检查文字不溢出。
- [x] 控制台无 JS error。

验收：

- 用户说“做一个介绍 Codex 的 PPT”时，界面像一个能工作的 AI PPT 产品。
- 用户说“讲稿放右边”，产品 UI 能被改造并恢复。

本轮执行状态：

- [x] `ppt-designer/index.html`：收紧标题和按钮文案，去掉“长期复用界面”等技术感表达。
- [x] `ppt-designer/style.css`：从深色装饰 demo 改为白色、克制、工具型 UI；去掉渐变背景、玻璃感、大圆角和装饰阴影。
- [x] `ppt-designer/style.css`：中等宽度下参数区两列展示，PPT 工作区保持“大纲 / 页面 / 讲稿”三列；884px 预览无横向溢出。
- [x] `ppt-designer/app.js`：紧凑视图按钮在“隐藏参数 / 显示参数”之间切换。
- [x] 验证：`node --check spaces/products/ppt-designer/app.js` 通过。
- [x] 浏览器 smoke：`/api/products/ppt-designer/preview` 无 console error；重新生成大纲、隐藏/显示参数可用；讲稿区位于右侧。

### P9：母体 shell 状态文案第一轮

目标：

把当前产品界面、生成、改造、恢复相关状态从技术实现语言收成用户能理解的产品语言。

具体 Todo：

- [x] 产品 preview empty/generating/failed 文案不再暴露“目录里写”“Chat”等技术表达。
- [x] 产品界面操作按钮收敛为“重新生成界面 / 恢复上一版 / 产品能力 / 新窗口”。
- [x] 当前产品界面 note 使用“继续对话调整”，而不是“继续聊天调整”。
- [x] 新建产品流程里“AI 会在产品目录里写出第一版界面”改为“创建后会自动生成第一版界面”。

本轮执行状态：

- [x] `product-runtime.js`：生成中、失败、空状态文案减技术感。
- [x] `product-shell-runtime.js`、`index.html`：产品界面操作按钮和 note 文案统一。
- [x] 验证：`node --check` 通过 `product-shell-runtime.js/product-runtime.js`。
- [x] 浏览器 smoke：主应用无 console error；当前产品界面显示“重新生成界面 / 恢复上一版 / 产品能力 / 新窗口”。

### P10：清理旧工作台逻辑 + 真实新建产品 E2E

目标：

把代码主心智从“AI 助手 + 推荐工作台”收束为“AI 产品 + 自己生成/改造产品界面”，同时验证新建产品主链路没有被清理破坏。

#### P10.1 旧逻辑清理规则

MVP 不做旧 workbench 兼容开关，也不为旧消息/旧状态块保留特殊显示兼容。清理按两类处理：

```text
A. 默认产品主路径用不到的：直接删除或停止加载。
B. 只是暂时的 DOM/CSS 命名壳、且当前只承载产品 preview 的：等主链路稳定后统一改名。
```

第一轮已确认：

- `recommendedWorkbench*` 曾经用于“助手推荐工作台”，但当前 `_assistantWorkbenchRecommendationFromText()` 永远返回空值。
- 新建 AI 产品不应该再走“推荐工作台”分支；它应该直接创建 product workspace，然后自动触发 `product_init`。
- 调整 AI 产品工作方式不应该顺手清空/绑定旧 workbench preference。
- `ppt-studio` 不能再进入新产品创建和新产品进化主链路。

本轮执行状态：

- [x] `product-shell-runtime.js`：删除空的 `_assistantWorkbenchRecommendationFromText()`。
- [x] `product-shell-runtime.js`：新建产品 draft 不再写 `recommendedWorkbenchId/name/reason`。
- [x] `product-shell-runtime.js`：自定义 AI 产品注册不再把旧 `recommendedWorkbench*` 挂回 `AI_OBJECTS`。
- [x] `product-shell-runtime.js`：工作方式快照 / 恢复不再保存旧 `recommendedWorkbench*` 字段。
- [x] `product-shell-runtime.js`：创建产品弹窗固定显示“产品界面：创建后自动生成”。
- [x] `product-shell-runtime.js`：工作方式预览固定显示“产品界面：按任务需要生成或调整”。
- [x] `product-shell-runtime.js`：从内置产品派生专属产品时不再尝试绑定旧推荐工作台。
- [x] `product-shell-runtime.js`：恢复工作方式不再因为没有推荐工作台而收起当前界面。
- [x] `index.html`：不再加载 `static/workbench-legacy.js`。
- [x] `index.html`：产品界面菜单删除“下次也用 / 不再沿用 / 详情 / 应用改进 / 放弃改进”。
- [x] `messages.js`：删除旧 `_maybeAppendWorkbenchProposal()`、`maybeRequestWorkbenchEvolutionFromText()` 调用、旧 transcript live-sync 调用。
- [x] `messages.js` / `ui.js`：删除旧 `next-ai-workbench` 隐藏状态块清洗，普通回复不再为旧协议做特殊处理。
- [x] `product-shell-runtime.js`：删除 `_assistantDefaultWorkbench*`、`_assistantRecommendedWorkbench*`、`_assistantWorkbenchIsUserSaved()`。
- [x] `product-shell-runtime.js`：删除 `_maybeAutoOpenAssistantDefaultWorkbench()`。
- [x] `product-shell-runtime.js`：删除 `activateWorkbenchInChat()`、`_loadWorkbenchItem()` 和 `/api/workbenches` 前端主路径。
- [x] `product-shell-runtime.js`：删除 `saveActiveWorkbenchAsDefault()`、`clearActiveWorkbenchDefault()`、旧 iframe `next-ai-workbench` message listener。
- [x] `sessions.js`：任务列表摘要不再显示“常用/推荐工作界面”。
- [x] `ui.js`：历史旧 workbench proposal 卡片不再渲染可点击按钮。
- [x] `product-evolution.js`：只保留产品界面 rollback。
- [x] `index.html` / `panels.js` / `style.css`：删除旧 Workbenches 面板入口、详情 view、panel loader、proposal 样式和旧 PPT workbench 样式。
- [x] `routes.py` / `api/workbenches.py`：删除旧 `/api/workbenches*` 路由和模块。
- [x] `streaming.py` / `product_context.py`：删除旧 `_NEXT_AI_WORKBENCH_STATE_PROMPT`，普通 WebUI 会话不再诱导模型输出隐藏状态块；产品 runtime 只要求写文件。
- [x] 验证：`node --check` 通过 `messages.js/product-shell-runtime.js/product-evolution.js/product-runtime.js/product-store.js/sessions.js/ui.js`。
- [x] 浏览器 smoke：`http://localhost:8788/` 无 console error；`workbench-legacy.js` 未加载；Workbenches panel/nav DOM 不存在；产品界面菜单只剩“重新生成界面 / 恢复上一版界面 / 产品能力 / 新窗口”。

#### P10.2 仍待清理

这些不进入默认产品主路径，但下一步可以继续删：

- [x] 删除 `static/workbench-legacy.js` 文件。
- [x] 清理 `panels.js` 的 Workbenches panel 和 `/api/workbenches*` 入口。
- [x] 删除 `ui.js` / `messages.js` 中旧 `next-ai-workbench` 标签清洗和旧 proposal 渲染分支。
- [x] 把 `_activeWorkbench` 主运行时状态/函数改成 product preview 语义，减少“workbench”残留。

#### P10.3 真实 E2E smoke Todo

验证目标：

```text
新建产品描述
-> 生成 AI 产品名称和 manifest
-> 自动创建 product workspace
-> 自动开启 product_init session
-> Agent 写出 index.html/style.css/app.js
-> preview 从 empty/generating 进入 ready
-> 继续对话可触发 product_builder
-> rollback 可恢复上一版
-> 删除临时产品后不残留
```

具体步骤：

- [x] 用一个临时描述创建产品。本轮通过“新建融资路演产品”建议项创建 `融资路演 PPT 设计师`。
- [x] 验证左侧出现新 AI 产品，且不是只生成一个名字：左侧显示 `融资路演 PPT 设计师 / 界面生成中`，随后变为 `已有产品界面`。
- [x] 验证产品目录出现在 `spaces/products/<product_id>/`。
- [x] 验证 `product.json` 写入 `skills/tools/ui_status`，API 返回 `preview_url`。
- [x] 等待 product_init 完成，确认 `entry_generated=true`。
- [x] 打开 preview，确认无 console error、页面不是 seed。生成文件包括 `index.html / style.css / app.js / product.json`。
- [x] 继续发一句产品界面调整要求，确认进入 `product_builder`。本轮 API E2E 使用 `e2e-smoke-deck-1780499613`，要求“把讲稿区固定在右侧常驻，同时在页面预览区旁边增加参考资料栏”。
- [x] 验证生成新版本并可 rollback。builder 开始前创建 `versions/v-20260603T152016Z`；builder 后 `index.html/style.css` hash 改变并出现参考资料栏；rollback 后 `index.html/style.css/app.js` 与 builder 前 hash 完全一致，versions 清空。
- [x] 删除临时产品和临时 session，确认后端产品列表只剩 `ppt-designer`，产品目录清干净，页面左栏无残留。

验收标准：

- 新建产品不会停在“只有助手名字”的状态。
- 用户继续普通聊天即可让产品生成或改自己的界面。
- 清理旧 workbench 推荐逻辑后，PPT 设计师和新建产品链路都仍然可运行。

### P11 / P12：产品预览语义和可见文案收敛

目标：

不额外设计新功能，只把 MVP 主路径的代码心智和可见文案从旧 workbench/任务界面收束到“AI 产品 / 产品界面”。

本轮执行状态：

- [x] `product-shell-runtime.js` / `product-runtime.js` / `product-store.js` / `product-evolution.js`：`_activeWorkbench` 主运行时状态和相关函数改为 product preview 语义。
- [x] 删除无用的 `_activeProductPreviewVersion` 占位。
- [x] `index.html`：右侧产品预览标题 id 改为 `activeProductPreviewName`，修复标题更新目标不一致。
- [x] `index.html` / `product-shell-runtime.js`：首页、空状态、任务状态、创建产品弹层、进化确认弹层中的“工作界面/任务界面”统一为“产品界面”。
- [x] 保留“工作方式”文案，因为它指 AI 产品的行为配置，不是旧 workbench。
- [x] 保留少量 `activeWorkbench*` DOM id/class 壳，不做无意义大搬家；只在影响功能或用户理解时改。

验证：

- [x] `rg`：可见主路径不再出现“工作界面 / 任务界面”；仅产品 UI 命令过滤正则保留旧词用于识别历史任务标题。
- [x] `node --check` 通过 `product-shell-runtime.js/product-runtime.js/product-store.js/product-evolution.js/ui.js/messages.js/sessions.js/panels.js`。
- [x] `python3 -m py_compile` 通过 `product_context.py/products.py/routes.py/streaming.py`。
- [x] 浏览器 smoke：`http://localhost:8788/` 可见区域没有“工作界面/任务界面/工作台”；PPT 产品菜单显示“重新生成界面 / 恢复上一版界面 / 产品能力 / 新窗口”；无 console error。

### P13：新建产品后的自然聊天体验

目标：

不增加复杂创建器，让“新建 AI 产品 -> 自动生成产品界面 -> 继续普通聊天改造”更像一条自然对话，而不是跳进技术流程。

本轮执行状态：

- [x] `messages.js`：`product_init` 首次生成也复用产品 UI 状态卡。
- [x] `product_init` 运行中卡片文案改为“正在生成这个 AI 产品的第一版界面”，区别于 `product_builder` 的“正在改界面”。
- [x] `product_init` 完成卡片文案改为“第一版产品界面已生成”，并且不展示“恢复上一版”，避免用户恢复到 seed 初始页。
- [x] `product_builder` 状态卡保留“正在改 / 新版已生成 / 可恢复上一版”语义。
- [x] `messages.js`：`product_init` 取消、断流或应用错误时，会把产品 `ui_status` 落到 `failed`，避免左侧一直显示“界面生成中”。
- [x] `product_init` 失败态只提供“重新生成界面”，不提供 rollback；因为第一版还没生成成功时，上一版只是 seed，不是用户真正可恢复的产品界面。
- [x] `product-runtime.js` / `product_context.py`：扩展 `product_builder` 意图识别，覆盖“加一个参考资料栏 / 把模板选择放上面 / 增加页数选择”等用户自然说法，同时普通任务仍保持 `product_usage`。
- [x] `product-runtime.js`：手动“重新生成界面”按是否已有真实产品界面决定 scope；empty/failed/seed 走 `product_init`，ready 后再走 `product_builder`。
- [x] `commands.js` / `streaming.py`：运行中 steer accepted 路径也带 product context；如果 steer 文本是在改产品界面，后端会把 `product_builder` runtime 契约附给 agent.steer，而不是只发送纯文本。

验证：

- [x] `node --check` 通过 `messages.js/product-shell-runtime.js/product-runtime.js/product-store.js/product-evolution.js/sessions.js/ui.js`。
- [x] `python3 -m py_compile` 通过 `product_context.py/products.py/routes.py/streaming.py`。
- [x] 前后端 scope smoke：`加一个参考资料栏 / 把模板选择放上面 / 增加页数选择` 进入 `product_builder`；`帮我做一份介绍 Codex 的 PPT / 总结一下这份材料` 保持 `product_usage`。
- [x] 前端 runtime smoke：失败产品在已有 session 下点击“重新生成界面”仍会发出 `product_init`，不会误判为 `product_builder`。
- [x] 前端 steer smoke：运行中 steer 文本 `加一个参考资料栏` 会发送 `/api/chat/steer` body：`product_id=ppt-designer`、`product_scope=product_builder`、`product_intent=加一个参考资料栏`。
- [x] 后端 steer smoke：fake running agent 收到的 steer 文本包含 `Next AI product runtime`、`Runtime scope: product_builder` 和原始 steer 文本。
- [x] 浏览器 smoke：创建临时产品 `P13 状态卡测试产品`，触发首次生成后，聊天正文出现“正在生成这个 AI 产品的第一版界面 / 正在生成第一版界面”；无 console error。
- [x] 浏览器 smoke：创建临时产品 `P13 取消态测试产品`，触发首次生成后立即取消；左侧状态从“界面生成中”回到“可重新生成”，产品接口返回 `ui_status=failed`、`entry_generated=false`，聊天状态卡显示“第一版产品界面生成失败 / 重新生成界面”；无 console error。
- [x] 浏览器 smoke：刷新 `http://localhost:8788/` 后，PPT 产品和产品界面仍可见，旧 Workbenches/工作台文案不出现，无 console error。
- [x] 清理临时产品、临时 session 和产品目录，刷新后左侧产品库无测试产品残留。

### P14：继续清理旧 workbench 文案残留

目标：

不做大规模 DOM/class 重命名，先清理用户可能看到的旧产品心智。内部 `workbench*` 壳只在影响维护或用户理解时再改。

本轮执行状态：

- [x] `i18n.js`：`workbenches_title` 英文/中文值从“工作界面”收敛为“产品界面”。
- [x] `i18n.js`：英文 empty subtitle 从 “dedicated workbench” 改为 AI product / product UI 心智。
- [x] `i18n.js`：中文 empty subtitle 从“通用 AI / 专属工作界面”改为“AI 产品 / 它自己的产品界面”。

验证：

- [x] `node --check` 通过 `i18n.js/product-runtime.js/product-shell-runtime.js/messages.js`。
- [x] `rg`：`vendor/hermes-webui/static` 中不再出现可见旧文案 `工作界面 / dedicated workbench / Workbenches`；仅内部命名壳和历史任务标题识别正则保留旧词。
- [x] 浏览器 smoke：刷新 `http://localhost:8788/` 后，页面不出现“工作界面 / dedicated workbench / Workbenches”，仍显示产品界面，无 console error。

### P15：后端产品成为唯一正式自定义产品来源

目标：

不做额外兼容层。MVP 里用户能看到和使用的自定义 AI 产品必须有后端 product、产品目录和 `productId`；旧 localStorage-only custom assistant 直接退出正式主路径。

本轮执行状态：

- [x] `product-shell-runtime.js`：`_customAssistantsRead/_customAssistantsWrite/_registerCustomAssistant` 只接受 product-backed 自定义产品。
- [x] `product-shell-runtime.js`：新建 AI 产品必须走 `/api/products/create`，拿到 `productId` 后才进入产品库，并自动触发第一版产品界面生成。
- [x] `product-shell-runtime.js`：从内置产品派生专属产品时也走 `/api/products/create`，并继承对应产品类型的默认 skills/tools。
- [x] `product-shell-runtime.js`：重命名、调整工作方式、回滚工作方式都写回 `/api/products/update`，不再只改浏览器本地状态。
- [x] `product-store.js`：hydrate 时只合并后端产品，不再做 localStorage-only 产品迁移或兼容展示。
- [x] `product-shell-runtime.js`：启动时删除旧 `next-ai-custom-assistants` key，产品列表不再从浏览器本地缓存恢复。
- [x] `manifest.json`：PWA 描述从旧 workbench 心智改为 chat-first AI product shell。

验证：

- [x] `node --check` 通过 `product-shell-runtime.js/product-store.js/sessions.js`。
- [x] `python3 -m py_compile` 通过 `products.py/routes.py/product_context.py`。
- [x] `rg`：旧 localStorage migration/import 计划和实现已清掉；正式自定义产品路径只保留 product-backed 对象。
- [x] Node VM smoke：旧 localStorage 假产品不会进入内存；hydrate 后只解析 `/api/products` 返回的产品。

### P16：产品任务必须持久绑定 product session

目标：

用户在 AI 产品主页发第一句话，或点击“生成/重新生成界面”时，创建出来的任务必须是这个 AI 产品的任务：session payload、session 文件、产品 registry 和 Agent workspace 要指向同一个 product。

本轮执行状态：

- [x] `product-store.js`：新增 `currentAssistantProductSessionDefaults()`，统一暴露当前产品的 `productId/workspace/enabledToolsets`。
- [x] `sessions.js`：`newSession()` 默认使用当前产品 defaults；产品主页新任务不再只带 workspace/toolsets，而会带 `product_id/product_scope`。
- [x] `product-runtime.js`：手动生成/重新生成产品界面时，如果当前 session 不属于该产品，会先创建产品 session，避免复用旧 session 写错 workspace。
- [x] `models.py`：`Session` 正式持久化并通过 `compact()` 返回 `product_id/product_scope/product_intent`。

验证：

- [x] `node --check` 通过 `product-store.js/sessions.js/product-runtime.js/product-shell-runtime.js`。
- [x] `python3 -m py_compile` 通过 `models.py/products.py/routes.py/product_context.py`。
- [x] API smoke：`POST /api/session/new` 带 `product_id=ppt-designer` 后，重新 `GET /api/session` 仍返回 `product_id/product_scope/product_intent`，workspace 和 toolsets 正确；临时 session 已删除。
- [x] 浏览器 smoke：刷新 `http://localhost:8788/` 后 AI 产品库、PPT 设计师和产品界面正常，无旧 Workbenches/工作界面/任务界面可见文案，无 console error。

### P17：产品生成终态必须一致

目标：

MVP 不再做额外兼容。产品界面生成/改造只有三种可理解状态：`generating / ready / failed`。成功必须来自产品目录里真的生成了非 seed 入口文件；取消、报错、连接失败都必须从 `generating` 收口到 `failed`，不能刷新后继续假装还在生成。

本轮执行状态：

- [x] `products.py`：`finalize_product_generation(..., failed=True)` 永远写入 `failed`，不再因为目录里已经有旧入口文件而误判 ready。
- [x] `streaming.py`：所有 SSE `cancel` 分支统一先 finalize 产品 turn 为 failed，再发取消事件。
- [x] `messages.js`：前端失败持久化从仅处理 `product_init` 扩展到 `product_init/product_builder`，后续“边聊边改产品界面”失败也会同步产品状态。

验证：

- [x] `python3 -m py_compile` 通过 `streaming.py/products.py/routes.py/models.py`。
- [x] `node --check` 通过 `messages.js/product-runtime.js/product-store.js`。
- [x] API smoke：临时产品 seed 入口 finalize 为 `failed`；写入真实 `index.html` 后成功 finalize 为 `ready`；带 `failed=true` finalize 即使已有入口也保持 `failed`；临时产品和目录已删除。
- [x] 浏览器 smoke：刷新 `http://localhost:8788/` 后左侧产品列表、PPT 设计师、产品界面正常，无旧工作台可见文案，无 console error。

### P18：当前 turn 的 product scope 不能被旧 session 状态覆盖

目标：

用户继续普通聊天时，当前这一句的 product scope 必须成为前端和后端的一致事实。尤其是 `product_builder`：如果这一句明确要求改产品界面，Chat 状态卡、preview 刷新和 session 本地状态都应该按本轮 `product_builder` 处理，而不是继续读取上一轮的 `product_usage`。

本轮执行状态：

- [x] `messages.js`：新增 `_applyProductContextToCurrentSession()`，发送前把本轮 `product_id/product_scope/product_intent` 同步到当前 `S.session`。
- [x] `messages.js`：stream done 后优先使用本轮 `productUiStatusContext.productScope`，避免旧 session scope 影响 done/failed 状态卡和 preview 刷新。

验证：

- [x] `node --check` 通过 `messages.js/product-runtime.js/sessions.js`。
- [x] `python3 -m py_compile` 通过 `product_context.py/routes.py/streaming.py/products.py/models.py`。
- [x] Node VM scope smoke：PPT 空界面普通任务 -> `product_init`；PPT 已生成普通任务 -> `product_usage`；“以后讲稿区放右边” -> `product_builder`。
- [x] Node VM message smoke：本轮 `product_builder` context 会同步到 `S.session.product_scope`，状态卡 context 也使用 `product_builder`。
- [x] HTTP smoke：`http://127.0.0.1:8788/` 返回 Next AI 页面并加载 `messages.js/product-runtime.js`。
- [ ] 浏览器视觉 smoke：本轮 in-app Browser 连接在导航阶段超时，下一轮需要重连后补做。

### P19：产品界面 rollback 必须包含资产文件

目标：

AI 产品界面不是永远只有 `index.html/style.css/app.js`。Agent 可能会写图片、JSON、字体、参考素材等小型资产。如果 rollback 只恢复核心文件，产品界面可能回到上一版 HTML，却仍引用当前版资产，用户会觉得“恢复上一版”不可信。

本轮执行状态：

- [x] `products.py`：新增安全的产品 UI 快照文件收集，递归纳入产品目录内的小型普通文件。
- [x] `products.py`：排除 `versions/`、`node_modules/`、`.git/`、隐藏文件、`README.md` 和过大文件，避免把运行目录或大文件塞进版本。
- [x] `products.py`：rollback 时恢复快照内文件，并删除当前版本中新出现但快照里没有的受管理 UI 资产。

验证：

- [x] `python3 -m py_compile` 通过 `products.py/routes.py/product_context.py/streaming.py/models.py`。
- [x] 直接函数 smoke：临时产品 `assets/a.txt` 被快照；修改资产并新增 `assets/new.txt` 后 rollback，`assets/a.txt` 恢复旧内容，`assets/new.txt` 被移除；临时产品目录已删除。
- [x] HTTP API smoke：通过 `/api/products/<id>/snapshot` 和 `/rollback` 验证同样资产恢复/新增资产清理；临时产品目录和 registry 记录已删除。
- [x] `http://127.0.0.1:8788/api/products` 正常返回产品列表；`8788` 后台服务已重启加载新代码。

### P20：rollback 清理不能误动版本快照目录

目标：

rollback 可以清理当前产品根目录里新增的受管理空目录，但不能整理或删除 `versions/<id>/...` 里的任何目录。版本目录是只读快照，不属于当前运行态。

本轮执行状态：

- [x] `products.py`：新增 `_has_excluded_snapshot_dir()`，统一判断路径是否处于 `versions/node_modules/.git/__pycache__` 等排除目录下。
- [x] `products.py`：`_remove_empty_dirs()` 跳过任何位于排除目录内的子路径，避免 rollback 后误动版本快照内部空目录。

验证：

- [x] 直接函数 smoke：rollback 后当前根目录的 `runtime-empty/` 被清理，但 `versions/<id>/empty-subdir/` 保持存在。
- [x] `python3 -m py_compile` 通过 `products.py/routes.py/product_context.py/streaming.py/models.py`。
- [x] 临时产品目录和 registry 记录已删除；`8788` 后台服务已重启加载新代码。

### P21：产品列表只认后端注册表

目标：

继续压缩 MVP 数据来源。AI 产品本体不能同时存在于后端 registry 和浏览器本地 custom assistant 缓存里，否则新建、删除、刷新和继续聊天都会出现“到底谁是事实”的混乱。

本轮执行状态：

- [x] `product-shell-runtime.js`：删除 `NEXT_AI_CUSTOM_ASSISTANTS_KEY` 常量和 localStorage 读写逻辑。
- [x] `product-shell-runtime.js`：`_customAssistantsRead/_customAssistantsWrite` 改为只维护当前页面内存中的后端产品镜像。
- [x] `product-shell-runtime.js`：启动时直接移除旧 `next-ai-custom-assistants`，不做迁移、不做兼容展示。
- [x] `product-store.js`：hydrate 删除旧缓存兼容分支，只按 `/api/products` 返回值增删当前自定义产品。

验证：

- [x] `node --check` 通过 `product-shell-runtime.js/product-store.js/product-runtime.js/messages.js`。
- [x] `python3 -m py_compile` 通过 `products.py/routes.py/product_context.py/streaming.py/models.py`。
- [x] Node VM smoke：旧 localStorage 假产品不会进入产品列表；hydrate 后只解析后端产品；init 会删除旧 key。
- [x] `GET /api/products` 正常返回后端产品注册表。

### P22：删除自定义产品时清理产品目录

目标：

自定义 AI 产品被删除后，不应该只从 registry 消失而把 `spaces/products/<id>` 留成孤儿目录。MVP 不保留这种兼容和残留，除非显式要求保留文件。

本轮执行状态：

- [x] `products.py`：`delete_product()` 默认 `remove_files=True`。
- [x] `routes.py`：`/api/products/delete` 未传 `remove_files` 时默认删除产品目录；只有显式 `remove_files:false` 才保留文件。
- [x] 删除边界仍限制在 `spaces/products/<id>` 且目录名必须等于产品 id；内置产品继续跳过删除。

验证：

- [x] API smoke：创建临时产品 `custom-smoke-product` 后删除，返回 `removed_files=true`。
- [x] 磁盘 smoke：`spaces/products/custom-smoke-product` 删除后不存在。
- [x] Registry smoke：`GET /api/products` 不再返回临时产品。

### P23：新建产品链路文案收束到“确认后立即生成”

目标：

新建 AI 产品不是逛市场、看模板或先保存一个助手名字。用户描述产品后，系统生成名称和职责，用户确认，然后立即创建产品并自动开始第一次产品界面生成任务。

本轮执行状态：

- [x] `product-shell-runtime.js`：新建产品首页文案从旧试用心智改成“确认后创建，并自动开始生成第一版界面”。
- [x] `product-shell-runtime.js`：创建确认弹窗文案从旧预览/派生心智收束为“创建 AI 产品 / 创建专属 AI 产品”。
- [x] `index.html`：静态兜底文案同步为“创建后自动开始第一次任务并生成产品界面”。

验证：

- [x] `node --check` 通过 `product-shell-runtime.js/product-store.js/product-runtime.js/messages.js`。
- [x] `rg`：可见静态代码里不再出现旧试用/预览式创建心智。
- [x] Node VM smoke：描述“生成图片海报的 AI 产品”会推断为 `image` 产品，调用 `/api/products/create`，并触发 `_startProductInitializationTask()`。

### P24：内置产品派生文案收束为“专属产品”

目标：

从内置产品派生一个新 AI 产品时，不再暗示这是助手分身，而是表达为产品库里的专属产品。

本轮执行状态：

- [x] `product-shell-runtime.js`：自定义重名兜底统一为 `${base} 专属版`。
- [x] `product-shell-runtime.js`：从内置产品派生时的 fallback title 统一为 `${baseObject.title} 专属版`。
- [x] `product-shell-runtime.js`：已存在派生产品的 toast 统一为“已打开专属产品”。

验证：

- [x] `node --check` 通过 `product-shell-runtime.js/product-store.js/product-runtime.js/messages.js`。
- [x] `rg`：`static` 可见主路径里不再出现旧派生文案。
- [x] Node VM smoke：内置 PPT 产品派生 draft 使用“专属产品/专属版”心智。

### P25：产品界面生成/改造优先于职责调整

目标：

用户在 AI 产品里说“生成界面 / 改界面 / 以后某个 UI 固定这样”时，应该优先进入 `product_init/product_builder`，让 Agent 写或改产品 workspace 文件；不能被旧的“调整工作方式”逻辑截走。命中已有但界面为空或失败的产品时，也不能只打开产品对象就停住。

本轮执行状态：

- [x] `messages.js`：发送前先用 `currentAssistantProductContextForMessage(..., {consumePending:false})` 预判当前消息的产品 scope。
- [x] `messages.js`：当 scope 为 `product_init/product_builder` 时跳过 `maybeRequestAssistantEvolutionFromText()`，由产品运行时接管。
- [x] `product-shell-runtime.js`：新增已有产品空/失败界面检测，只对 `empty/failed` 状态触发首次生成。
- [x] `product-shell-runtime.js`：新建产品命中同名已有产品时，如果界面为空或失败，会自动触发 `_startProductInitializationTask()`。
- [x] `product-shell-runtime.js`：从内置产品派生命中已有专属产品时，如果界面为空或失败，也会自动触发首次生成。

验证：

- [x] `node --check` 通过 `messages.js/product-shell-runtime.js/product-runtime.js/product-store.js`。
- [x] `python3 -m py_compile` 通过 `products.py/routes.py/product_context.py/streaming.py/models.py`。
- [x] Node VM smoke：`以后做 PPT 时讲稿区放右边` 被识别为 `product_builder`。
- [x] Node VM smoke：已有空产品会触发初始化，已有 ready 产品不会重复触发。

### P26：产品 tools 成为 product session 的后端默认能力

目标：

产品自己的 `tools` 不能只靠前端转发。创建 product session 时，只要请求带了 `product_id`，后端就应该能从产品 registry 读出 `tools` 并落到 `session.enabled_toolsets`，确保 Agent 写/改产品界面时真的有对应工具。

本轮执行状态：

- [x] `routes.py`：`/api/session/new` 在解析出 product context 后，如果请求没有显式传入 `enabled_toolsets`，会从 `product_ctx["tools"]` 解析并写入 `s.enabled_toolsets`。
- [x] 保留显式请求优先级：前端传入 `enabled_toolsets` 时不覆盖；未传时使用产品默认 tools。

验证：

- [x] `python3 -m py_compile` 通过 `routes.py/products.py/product_context.py/streaming.py/models.py`。
- [x] API smoke：创建临时 PPT 产品，不传 `enabled_toolsets` 调用 `/api/session/new`，返回 session 的 `workspace` 匹配产品目录，`product_scope=product_init`，`enabled_toolsets=["skills","file","terminal","code_execution"]`。
- [x] 清理 smoke：临时产品 registry、产品目录和临时 session 均无残留。

### P27：Chat 运行入口可从 product session 恢复 product context

目标：

继续普通聊天时，后端不能完全依赖前端每次都传 `product_id`。如果当前 session 已经绑定了 AI 产品，`/api/chat/start` 和同步 `/api/chat` 应该能从 session 恢复 product context，继续注入产品运行时提示、workspace 和 tools。

本轮执行状态：

- [x] `product_context.py`：新增共享 `product_context_request_body()`，在请求缺少 `product_id` 但 session 带有 `product_id` 时补回 product context request body。
- [x] 首个空 session 的 `product_init/product_builder` scope 会保留；已有历史消息后默认回到 `product_usage`，再由当前消息自然识别 `product_builder`。
- [x] `/api/chat/start` 使用恢复后的 product body 调用 `product_context_from_request()`。
- [x] 同步 `/api/chat` 入口也使用同一恢复逻辑。

验证：

- [x] `python3 -m py_compile` 通过 `routes.py/products.py/product_context.py/streaming.py/models.py`。
- [x] Python smoke：无 `product_id` 请求 + 空 product session 会恢复为 `product_init`，intent 使用 session 创建意图。
- [x] Python smoke：无 `product_id` 请求 + 已有历史 product session，发送“以后做 PPT 时讲稿区放右边”会恢复 product context，并由分类器识别为 `product_builder`。
- [x] 清理 smoke：临时产品 registry 和产品目录无残留。

### P28：运行中 steer 可从 product session 恢复 product context

目标：

产品生成/改造过程中，用户继续输入“把这里改一下 / 加一个栏 / 默认放右边”时，后端 steer 入口也应该保持 AI 产品上下文。不能因为前端漏传 `product_id`，让运行中的 Agent 只收到普通文本。

本轮执行状态：

- [x] `product_context.py`：把 P27 的 request body 恢复逻辑抽成共享 `product_context_request_body()`。
- [x] `routes.py`：`/api/chat/start` 和同步 `/api/chat` 改用共享 helper。
- [x] `streaming.py`：`/api/chat/steer` 在解析 product context 前也会先从 session 恢复 product fields。
- [x] 共享 helper 同时处理 steer 的 `text` 字段：如果请求有 `product_id` 但缺少 `product_intent/message`，也会用当前文本补齐 intent。

验证：

- [x] `python3 -m py_compile` 通过 `routes.py/products.py/product_context.py/streaming.py/models.py`。
- [x] Python smoke：steer body 只有 `session_id/text`、没有 `product_id` 时，会从 product session 恢复 `product_id`，并识别“加一个参考资料栏，并把讲稿区固定在右侧”为 `product_builder`。
- [x] Python smoke：steer body 有 `product_id` 但没有 `product_intent/message` 时，也会用 `text` 补 intent 并识别为 `product_builder`。
- [x] 清理 smoke：临时产品 registry 和产品目录无残留。

### P29：产品 status 接口按文件事实保守自愈

目标：

产品界面是否 ready 不能只依赖 stream finalize 成功写回 registry。`/api/products/<id>/status` 本身应该能根据产品目录里的 `preview_entry` 判断状态，避免界面已经生成但 registry 还卡在 `empty/generating`。

本轮执行状态：

- [x] `products.py`：`product_file_status()` 在入口文件存在且不是 seed 时，如果 `ui_status` 仍是 `empty/generating`，自动写回 `ready`。
- [x] `products.py`：如果 registry 是 `ready` 但入口文件不存在或仍是 seed，自动写回 `failed`。
- [x] 保守处理：已经明确 `failed` 的产品不会因为入口非 seed 自动翻回 `ready`，避免把取消/失败留下的半成品误展示成完成态。

验证：

- [x] `python3 -m py_compile` 通过 `products.py/routes.py/product_context.py/streaming.py/models.py`。
- [x] Python smoke：临时产品 seed 初始状态保持 `empty`；写入非 seed 入口且 registry 为 `generating` 后，status 自愈为 `ready`；入口退回 seed 且 registry 为 `ready` 后，status 自愈为 `failed`。
- [x] HTTP smoke：`/api/products/ppt-designer/status` 返回 `ui_status=ready`，主产品状态正常。
- [x] 清理 smoke：临时产品 registry 和产品目录无残留。

### P30：首次 product_init 可见消息不再重复创建描述

目标：

新建产品确认后，系统自动开始第一次产品界面生成。聊天里可见的首轮消息不应该再次展示“我想创建一个……”的创建描述，而应该表达当前动作：开始生成第一版产品界面；原始创建需求继续作为 `product_intent` 传给 Agent。

本轮执行状态：

- [x] `product-runtime.js`：新增 `_assistantProductInitUserMessage()`，生成“开始生成「产品名」的第一版产品界面。”。
- [x] `_startProductInitializationTask()` 保留 `productIntent/sourcePrompt` 和 `_nextAiPendingProductIntent`，但输入框可见消息改为产品界面生成动作句。

验证：

- [x] `node --check` 通过 `product-runtime.js/messages.js/product-shell-runtime.js/product-store.js`。
- [x] Node VM smoke：自动初始化会调用 `send()`，可见输入为“开始生成「融资路演 PPT 产品」的第一版产品界面。”，同时 `productIntent` 和 pending product intent 保留原始创建需求。

### P31：删除旧助手职责进化分支

目标：

MVP 只保留一条自进化主链路：用户通过聊天提出要求，当前 AI 产品进入 `product_builder`，Agent 修改产品 workspace 文件并刷新产品界面。旧的“调整工作方式 / 工作方式预览 / 职责回滚”会和产品界面生成机制并行，造成用户不知道自己是在改产品、改助手，还是新建专属产品，因此直接删除。

本轮执行状态：

- [x] `messages.js`：删除发送前的 `maybeRequestAssistantEvolutionFromText()` 拦截，普通消息不再被旧职责进化流程截走。
- [x] `product-shell-runtime.js`：删除职责进化 intent、内置产品派生、工作方式预览、职责快照和职责回滚逻辑。
- [x] `product-shell-runtime.js` / `product-store.js`：删除本地产品对象里的旧 `evolutionHistory` 残留。
- [x] `index.html` / `style.css`：删除旧“调整工作方式 / 最近进化 / 工作方式预览”按钮、弹窗和死 CSS。
- [x] 新建产品确认文案收束为“确认名称；创建后自动开始第一次任务并生成产品界面”。

验证：

- [x] `node --check` 通过 `messages.js/product-shell-runtime.js/product-store.js/product-runtime.js/product-evolution.js`。
- [x] `python3 -m py_compile` 通过 `products.py/product_context.py/routes.py/streaming.py/models.py`。
- [x] 静态搜索确认旧职责进化关键词和函数不再存在。
- [x] HTTP smoke：`http://localhost:8788/` 能返回新版 HTML，页面只保留新建产品确认和产品能力弹窗，不再包含 `assistantEvolution`。

### P32：空产品首轮统一生成产品界面 + 删除隐藏高级导航

目标：

不要过度设计，也不要把旧入口藏在 CSS 里。MVP 的默认规则应该很直接：当前 AI 产品有 workspace 且产品界面为空或失败时，下一条产品会话先进入 `product_init`，让 Agent 写出第一版产品界面；产品界面已有后，普通任务保持 `product_usage`，明确要求 UI/流程/默认项时才进入 `product_builder`。

本轮执行状态：

- [x] `product-runtime.js`：删除 PPT-only 初始化判断，空/失败产品统一进入 `product_init`。
- [x] `product_context.py`：后端兜底同样把空/失败产品的 `product_usage/product_builder` 提升为 `product_init`，避免前端漏传时退回普通聊天。
- [x] `index.html`：删除默认 shell 里隐藏的旧高级导航按钮、侧栏 panel、主区 detail view、Kanban 弹窗和 Dashboard 设置块，不再保留 tasks/kanban/skills/memory/workspaces/profiles/todos/insights/logs/dashboard 等旧入口 DOM。
- [x] `style.css`：删除旧高级 shell、旧多主视图切换、旧 Insights/Kanban/Logs 样式块；主视图只保留 Chat 默认和 Settings。
- [x] `panels.js/ui.js`：`switchPanel()` 收束为只接受 `chat/settings`，旧 panel 调用不会再触发旧 API 或旧主视图；删除 Dashboard 设置和 Todo 面板刷新残留。
- [x] `product-shell-runtime.js/style.css/index.html`：旧 `assistant-evolution-*` 命名改成 `product-dialog-*`，避免继续把 AI 产品误读为助手职责进化。

验证：

- [x] `node --check` 通过 `product-runtime.js/product-shell-runtime.js/messages.js/product-store.js/product-evolution.js/ui.js/panels.js/boot.js`。
- [x] `python3 -m py_compile` 通过 `product_context.py/products.py/routes.py/streaming.py/models.py`。
- [x] 静态搜索确认 `agent-shell-advanced`、旧高级 panel/view DOM、旧职责演化、旧 workbench 协议关键词和旧 `showing-*` panel 分支不再出现在 MVP 主文件。
- [x] Node VM smoke：空自定义生图产品普通任务 -> `product_init`；ready 产品普通任务 -> `product_usage`；ready 产品 UI 调整要求 -> `product_builder`；failed 产品普通任务 -> `product_init`。
- [x] Python backend smoke：空/失败产品请求被提升为 `product_init`；ready 产品普通请求保持 `product_usage`；ready 产品 UI 调整请求进入 `product_builder`。
- [x] HTTP smoke：`http://localhost:8788/` 只返回 AI 产品 / 产品界面相关文案，没有旧高级入口、旧职责演化或旧 Kanban/Insights/Logs 主视图命中。

### P33：非 PPT 产品创建主链路 smoke

目标：

P10.3 已经证明 PPT 产品 E2E 可以跑通。P32 之后需要补一条非 PPT 证据，确认“AI 产品”不是又被 PPT 特例绑死：用户创建生图/研究/数据类产品时，系统应该生成真实 product、真实 workspace、正确能力提示，并在前端创建成功后自动进入产品界面初始化。

本轮执行状态：

- [x] Live API smoke：通过 `/api/products/create` 创建临时 `image` 产品 `e2e-image-product-1780524698`。
- [x] 验证临时产品不是 PPT 特例：`product_type=image`，后端自动建议 `skills=["imagegen"]`、`tools=["skills","file","image_gen"]`。
- [x] 验证真实 workspace：`spaces/products/<id>/` 存在，包含 seed `index.html` 和 `product.json`，API status 返回 `ui_status=empty`、`entry_generated=false`。
- [x] 验证删除清理：`/api/products/delete` 后 registry 不再包含该产品，临时 workspace 已删除。
- [x] Frontend VM smoke：`createProductFromPrompt("我想创建一个帮我生成海报和封面的 AI 产品")` 会推断 `product_type=image`，提交 image capability，并调用 `_startProductInitializationTask(savedDraft, prompt)`。

当前结论：

非 PPT 产品不再停在“只生成一个名字”。创建阶段已经能生成 product + workspace + manifest + capability，并且前端会自动接上 `product_init`。下一步如果要证明 Agent 写出的非 PPT UI 质量，需要真实模型流式 E2E；这属于验证主链路，不要再新增新的产品概念。

### P34：按 MVP 删除不可达旧面板逻辑

目标：

不把旧能力藏在代码里等待“以后可能用”。当前 MVP 只有 Chat、AI 产品库、Settings、产品 preview 和产品运行时。Cron、Kanban、Logs、Insights、Skills、Memory、Workspaces、Profiles、Dashboard 这些旧面板不在默认产品主链路里，继续留在 `panels.js` 会让维护者误以为产品仍是传统 Hermes 多面板工具。

本轮执行状态：

- [x] `panels.js`：删除不可达的 Cron、Kanban、Logs、Insights、Skills、Memory、Workspaces、Profiles 等旧面板函数和顶部状态变量。
- [x] `panels.js`：只保留标题栏同步、Chat/Settings 切换、拖拽上传和 Settings 表单逻辑。
- [x] `index.html` / `panels.js`：删除 Settings 里的 `/insights` 使用同步开关和保存逻辑。
- [x] `ui.js` / `style.css`：删除 Hermes Dashboard 状态探测、打开函数和样式残留。
- [x] `ui.js`：删除新建文件夹后“添加为 space”的旧提示，避免把用户带回 workspace/space 心智。
- [x] `i18n.js`：删除旧 Kanban/Dashboard/Insights/Logs/Sync insights 相关翻译键。

验证：

- [x] `node --check` 通过 `panels.js/ui.js/i18n.js/product-shell-runtime.js/product-runtime.js/product-store.js/product-evolution.js/messages.js/sessions.js/boot.js/commands.js`。
- [x] `python3 -m py_compile` 通过 `products.py/product_context.py/routes.py/streaming.py/models.py`。
- [x] 静态搜索确认 MVP 主文件不再命中 `Kanban / Dashboard / Workbenches / next-ai-workbench / settingsSyncInsights / sync_to_insights / loadKanban / loadInsights / loadWorkspacesPanel` 等旧入口。
- [x] HTTP smoke：`http://localhost:8788/` 正常返回，只出现 AI 产品 / 产品界面 / 新建 AI 产品等 MVP 语义。

### P35：非 PPT 产品真实流式 product_init E2E

目标：

证明“新建产品描述 -> 生成 AI 产品 -> 继续普通聊天 -> 边聊边生成产品界面”不是前端假状态，也不是 PPT 特例。临时 image 产品必须通过真实 `/api/chat/start` + `/api/chat/stream` 让 Agent 写出非 seed `index.html/style.css/app.js`，并由后端 finalize 为 `ready`。

本轮执行状态：

- [x] 第一次真实流式 E2E 启动成功，Agent 收到 product runtime，上线 `openai-codex / gpt-5.5` run，并调用了 `write_file` 三次；但 210 秒超时被测试脚本取消，journal 终态是 `interrupted-by-user`。这个失败不是创建产品失败，也不是后端崩溃，而是测试超时过短。
- [x] 第二次真实流式 E2E 将超时放宽到 360 秒，临时 image 产品 `e2e-stream-image-0526514696` 成功完成 `stream_end`。
- [x] Agent 真实工具链包括 `skill_view/search_files/read_file/write_file`，并写出 `index.html/style.css/app.js`。
- [x] 产品 status 从 `ui_status=generating`、`entry_is_seed=true` 变为 `ui_status=ready`、`entry_is_seed=false`、`entry_generated=true`。
- [x] 入口文件 hash 改变，`index.html` 标题为“海报与封面图片生成器”，不是 seed 页面。
- [x] 临时 session、临时产品和临时 workspace 已删除，`GET /api/products` 只剩内置 `ppt-designer`。

验证结果：

```text
terminalEvent: stream_end
entry_generated: true
entry_is_seed: false
ui_status: ready
files: README.md / app.js / index.html / product.json / style.css
```

结论：

非 PPT 产品已经能真实长出自己的产品界面。当前暴露的问题不是机制不成立，而是首次 `product_init` 偏慢：这次从创建到 ready 约 5 分半。下一步不要扩概念，要优化 `product_init` 的最小写文件路径和用户等待态。

### P36：收紧 product_init 最小写文件策略 + product_usage 不误改验证

目标：

不改产品概念，只让 MVP 主链路更稳：`product_init` 应该更快进入写文件，不要先做广泛 repo 探索；ready 产品的普通 `product_usage` 应该回答用户任务，不应该无故重写产品界面文件。

本轮执行状态：

- [x] `product_context.py`：`product_init` scope guidance 新增速度约束，要求在必要 skill loading 后优先写 `index.html/style.css/app.js`。
- [x] `product_context.py`：明确 `product_init` 第一版不要广泛搜索无关文件、不要生成图片、不要跑 build，除非用户明确要求。
- [x] `product_context.py`：`product_usage` scope guidance 明确普通任务不要编辑产品 preview UI 文件，只有用户明确要求改界面/流程时才改。
- [x] 重启 `8788` 本地 WebUI，确保 Python prompt 变更加载。
- [x] 真实流式 E2E 创建临时 image 产品 `e2e-fast-image-0527379135`，`product_init` 成功 `stream_end` 并写出 `index.html/style.css/app.js`。
- [x] `product_init` 总耗时从上一轮约 5 分半降到 80.8 秒，首次 `write_file` 出现在 72 秒。
- [x] 同一 ready 产品继续发送普通 `product_usage` 请求“帮我想 3 个儿童节海报主题...”，14.6 秒完成。
- [x] `product_usage` 没有 `write_file` 工具事件；`index.html/style.css/app.js` 三个 hash 前后完全一致。
- [x] 临时产品、临时 session 和临时 workspace 已删除，`GET /api/products` 只剩内置 `ppt-designer`。

验证结果：

```text
product_init:
  terminalEvent: stream_end
  duration: 80.8s
  firstWriteFile: 72.0s
  ui_status: ready
  entry_generated: true
  files: README.md / app.js / index.html / product.json / style.css

product_usage:
  terminalEvent: stream_end
  duration: 14.6s
  firstWriteFile: null
  hashesUnchanged: true
```

结论：

MVP 主机制现在更可信：非 PPT 新产品可以真实长出产品界面，ready 后普通聊天不会把产品 UI 当成默认输出继续乱改。下一步继续压首次写文件时间，重点是减少必要 skill loading 之后的犹豫，而不是新增工作台概念。

### P37：删除旧后端兼容残留

目标：

继续按 MVP 收束，不为旧看板、旧洞察同步、旧 workbench 入口保留兼容壳。Next AI 当前只保留 AI 产品主链路：产品列表、产品会话、产品 preview、Agent 写产品界面、snapshot/rollback。

本轮执行状态：

- [x] `routes.py`：删除 `/api/kanban/*` 旧路由分支，不再返回旧兼容 404 文案。
- [x] `routes.py` / `streaming.py`：删除旧 `sync_to_insights` 使用同步逻辑。
- [x] `config.py`：删除 `sync_to_insights` 默认配置和 bool key。
- [x] 删除 `api/kanban_bridge.py` 和 `api/state_sync.py`。
- [x] `gateway_watcher.py`：删除指向旧 `state_sync.py` 的注释引用。
- [x] 旧 `static/workbench-runtime.js` 改名为 `static/product-shell-runtime.js`，主页脚本入口同步更新。
- [x] `index.html` / `style.css` / `product-shell-runtime.js` / `product-runtime.js`：把当前产品界面相关 `workbench` class/id/局部命名收束为 `product`。
- [x] 静态搜索确认 `api/` 和 `static/` 主路径不再命中 `/api/kanban`、`sync_to_insights`、`state_sync`、`kanban_bridge`、`Kanban`、`Dashboard`、`Workbenches` 等旧入口。

验证结果：

```text
python3 -m py_compile:
  product_context.py / products.py / routes.py / streaming.py / models.py / config.py / gateway_watcher.py passed

node --check:
  product-shell-runtime.js / product-runtime.js / product-store.js / product-evolution.js / messages.js / sessions.js / ui.js / panels.js / i18n.js passed

rg old backend/static terms:
  no matches

HTTP:
  GET / -> loads static/product-shell-runtime.js
  GET /static/workbench-runtime.js -> 404
  GET /api/kanban -> 404
```

结论：

旧后端残留已经从主运行时删除。后面不再回头兼容旧 workbench/kanban/insights 协议，除非它直接服务“AI 产品自己生成和改造界面”的 MVP 主链路。

### P38：继续压 product_init 犹豫 + 生成等待态更明确

目标：

不新增功能，只让 MVP 主链路更自然：用户新建 AI 产品后，应清楚知道 Agent 正在生成第一版产品界面；Agent 收到的 `product_init` 指令应更倾向于先写出真实可用的 `index.html/style.css/app.js`，而不是先解释、规划或做可选探索。

本轮执行状态：

- [x] `product_context.py`：`product_init` scope guidance 改为“必要 skill loading 后立即写 `index.html/style.css/app.js`”。
- [x] `product_context.py`：明确创建请求已经给出产品方向时，不要先追问细节；用可编辑默认值先做第一版。
- [x] `product_context.py`：明确首版 UI 文件出现前，不做无关 repo 搜索、生成图片、跑构建或过度视觉打磨，除非用户明确要求。
- [x] `product-runtime.js`：首次生成的自动消息改成“先做一个简单可用的版本”。
- [x] `product-runtime.js`：右侧 preview 的 generating 状态改为“正在生成第一版产品界面”，并说明正在写 `index.html/style.css/app.js`。
- [x] `product-shell-runtime.js`：聊天区顶部任务进度在 `product_init` 时显示“正在生成第一版产品界面”，而不是普通“正在处理这次任务”。
- [x] 固定验证矩阵改为当前 `product-shell-runtime.js` 文件名。
- [x] 重启 `8788` 本地 WebUI，确保 Python prompt 变更加载。

验证结果：

```text
node --check:
  product-shell-runtime.js / product-runtime.js / messages.js / sessions.js / ui.js / commands.js passed

python3 -m py_compile:
  product_context.py / products.py / routes.py / streaming.py passed

HTTP:
  GET /health -> ok
  GET / -> loads static/product-shell-runtime.js
  GET /static/workbench-runtime.js -> 404
  GET /api/kanban -> 404

source checks:
  product_init prompt includes immediate index.html/style.css/app.js write instruction
  generating UI copy includes “正在生成第一版产品界面”
```

结论：

这一步没有声称真实 Agent 首次写文件时间已经达标，只是进一步减少 `product_init` 的犹豫空间，并让用户等待时更明白系统正在做什么。下一步需要用真实流式 E2E 复测首次 `write_file` 时间和最终 ready 状态。

### P39：真实 E2E 复测 product_init 模型可靠性

目标：

不要靠想象判断 MVP 是否成立，用真实流式 Agent 跑一遍“新建产品 -> 自动生成产品界面 -> ready 后普通聊天不误改 UI”。

执行结果：

- [x] 默认模型 `openai-codex / gpt-5.5` 真实 E2E 未生成 UI：`product_init` 运行 286.2 秒，`write_file` 次数为 0，tool event 为 0，产品状态进入 `failed`。
- [x] 失败根因不是产品 runtime 崩溃，也不是文件系统失败，而是 provider 连续 90 秒无响应并超时；日志显示 `No response from provider for 90s (non-streaming, model: gpt-5.5)`。
- [x] 显式使用更快模型 `openai-codex / gpt-5.4-mini` 真实 E2E 成功：`product_init` 48.6 秒完成，首次 `write_file` 出现在 36.1 秒，写出 `index.html / style.css / app.js` 并进入 `ready`。
- [x] 同一个 ready 产品继续普通 `product_usage`：6.7 秒完成，`write_file` 次数为 0，`index.html / style.css / app.js` hash 全部不变。
- [x] 临时产品和临时 session 已清理，服务健康检查显示 `sessions: 0`、`active_streams: 0`、`active_runs: 0`。

验证证据：

```text
default model:
  model: openai-codex / gpt-5.5
  product_init duration: 286.2s
  first write_file: null
  write_file events: 0
  final ui_status: failed
  root cause: provider timeout, no model response for 90s

fast model:
  model: openai-codex / gpt-5.4-mini
  product_init duration: 48.6s
  first write_file: 36.1s
  write_file events: 6
  final ui_status: ready
  generated files: index.html / style.css / app.js

product_usage after ready:
  duration: 6.7s
  write_file events: 0
  UI file hashes unchanged: true
```

结论：

MVP 机制成立：AI 产品可以从普通 chat 长出自己的产品界面，并且 ready 后普通聊天不会默认乱改 UI。当前默认路径的阻塞是模型可靠性：默认 `gpt-5.5` 首轮生成可能无响应超时。下一步不要加新概念，先把默认首轮生成的失败原因、重试路径和可选更快模型策略处理清楚。

### P40：继续删除旧 Insights 残留

目标：

按 MVP 主线收干净代码。旧 Insights 面板、使用分析接口和同步开关不再服务“AI 产品自己生成和改造界面”，不继续保留兼容。

改动：

- [x] `routes.py`：删除旧 `/api/insights` 路由和 `_handle_insights` 使用统计聚合逻辑。
- [x] `config.py`：把 `sync_to_insights` 加入 legacy drop key，磁盘旧设置不会再通过 `/api/settings` 暴露，也不会被继续持久化。
- [x] `i18n.js`：批量删除未被调用的 `insights_*` 翻译键。
- [x] `style.css`：删除旧 `insights-card` 专属类，保留通用 system health 样式。
- [x] 重启 `8788` 本地 WebUI，确保 Python 路由和 settings 过滤生效。

验证结果：

```text
python3 -m py_compile:
  config.py / routes.py / product_context.py / products.py / streaming.py passed

node --check:
  i18n.js / product-shell-runtime.js / product-runtime.js / messages.js passed

HTTP:
  GET /health -> ok
  GET /api/settings -> no sync_to_insights
  GET /api/insights -> 404
  GET /api/products -> only current product registry
  GET / -> loads static/product-shell-runtime.js
```

结论：

旧 Insights 主路径已经从代码、接口和可见设置响应里移除。后面如果需要产品级分析，也应该由某个 AI 产品自己生成自己的分析界面，而不是恢复旧全局 Insights 面板。

### P41：默认 product_init 失败原因进入产品状态

目标：

默认 `product_init` 遇到模型无响应或 provider 超时时，不静默切模型，也不让用户只看到泛泛的“生成失败”。失败原因要挂到 AI 产品本身，让聊天卡、右侧产品界面 failed 态、产品主页都能解释清楚，并保留自然重试入口。

改动：

- [x] `products.py`：产品 registry 增加 `ui_error_type` / `ui_error_message`；`generating` / `ready` 会清掉旧失败原因。
- [x] `streaming.py`：`no_response`、异常兜底等失败出口会在发送前端错误事件前 finalize 产品失败原因。
- [x] `routes.py`：`/api/products/finalize` 支持写入失败原因；产品 session 绑定时 `product_init` / `product_builder` 都会进入 `generating`。
- [x] `product-store.js` / `product-runtime.js`：前端产品对象和右侧 preview 同步失败原因。
- [x] `messages.js`：产品 UI 失败卡显示原因；`no_response` 会显示“模型这次没有返回内容，可能是 provider 超时或限流。”
- [x] `product-shell-runtime.js`：产品主页和右侧顶部状态在 failed 时优先展示产品失败原因。

验证结果：

```text
python3 -m py_compile:
  products.py / routes.py / streaming.py / product_context.py / config.py passed

node --check:
  product-store.js / product-runtime.js / product-shell-runtime.js / messages.js passed

HTTP:
  GET /health -> ok
  POST /api/products/create -> temp product created
  POST /api/products/update failed + ui_error_* -> persisted
  GET /api/products/<id>/status -> failed reason visible
  POST /api/products/update generating -> ui_error_* cleared
  POST /api/products/delete -> temp product removed
```

结论：

默认首轮生成失败现在能解释清楚：用户知道是模型/provider 没返回，而不是“AI 产品”概念失效。这里仍然没有静默切模型；下一步再用真实流式 E2E 复测默认路径和快速模型路径。

### P42：真实 E2E 复测默认/快速路径 + 否定式意图修复

目标：

继续用真实流式 Agent 验证 MVP 主链路，而不是只做接口假设：默认模型、快速模型、ready 后普通使用都要走一遍。

执行结果：

- [x] 默认路径 `openai-codex / gpt-5.5` 这次成功生成产品界面：`product_init` 106.1 秒完成，首次 `write_file` 出现在 95.3 秒，最终 `ui_status=ready`。
- [x] 默认路径生成了 `index.html / style.css / app.js`，并写入了 `README.md`；最终没有 `ui_error_type / ui_error_message`。
- [x] 快速路径 `openai-codex / gpt-5.4-mini` 成功生成产品界面：`product_init` 43.4 秒完成，首次 `write_file` 出现在 37.1 秒，最终 `ui_status=ready`。
- [x] 快速路径 ready 后继续普通 `product_usage`：6.1 秒完成，tool event 为 0，`write_file` 为 0，`index.html / style.css / app.js` hash 全部不变。
- [x] E2E 过程中发现一个意图分类问题：普通使用文案里写“不要改产品界面”时，旧逻辑会因为命中“改/产品界面”误判为 `product_builder`。虽然这次没有误写文件，但 scope 不干净。
- [x] `product_context.py` / `product-runtime.js`：增加否定式 UI 意图判断，例如“不要改产品界面 / 不用调整 UI / 不改界面”保持 `product_usage`，明确“以后把字段固定在右侧 / 把上传区移到左侧”仍然是 `product_builder`。

验证结果：

```text
default product_init:
  model: openai-codex / gpt-5.5
  duration: 106.1s
  first write_file: 95.3s
  write_file events: 8
  final ui_status: ready
  generated files: index.html / style.css / app.js

mini product_init:
  model: openai-codex / gpt-5.4-mini
  duration: 43.4s
  first write_file: 37.1s
  write_file events: 6
  final ui_status: ready

mini product_usage after ready:
  duration: 6.1s
  tool events: 0
  write_file events: 0
  UI file hashes unchanged: true

scope negation smoke:
  ready product + "不要改产品界面" -> product_usage
  empty product + same text -> product_init
  "以后把负责人字段固定在右侧" -> product_builder

cleanup:
  temp products removed
  temp sessions removed
  /api/products -> only ppt-designer
```

结论：

MVP 主链路现在更稳：默认模型这次也能生成产品 UI，快速模型仍然更快，ready 后普通使用不会误改 UI 文件。意图分类也更贴近产品定义：只有用户真的要改产品界面/流程时才进入 builder；否定式“不改界面”不会误触发。

### P43：首屏可见走查与未落地预设清理

目标：

```text
MVP 首屏不要展示还没有真实 product workspace 的“预设产品”。
用户看到的应该是：
  通用 AI：普通 Chat。
  PPT 设计师：真实内置 AI 产品，有产品界面。
  新建 AI 产品：用户说一句，然后创建并生成。
```

本轮判断：

```text
“研究分析师 / 数据分析师”如果作为左侧内置入口出现，但后端 /api/products 里没有对应真实产品，
用户会误以为它们已经是可用 AI 产品。

MVP 下这属于超前和混乱，不应该保留在首屏。
研究、数据仍可以作为“新建 AI 产品”的类型推断和默认能力建议存在；
但它们必须由用户创建后，作为真实 product-backed 产品出现在列表里。
```

已处理：

- [x] 删除 `index.html` 左侧产品列表中的 `研究分析师`、`数据分析师` 静态入口。
- [x] 删除 `AI_OBJECTS` 中 `research`、`data` 两个非 product-backed 内置对象。
- [x] 修正历史 session 归类：如果 legacy 推断出不存在的产品 kind，不再让任务绑定到不可见入口，而是回到 `通用 AI`。
- [x] 保留新建产品的 research/data 类型识别和默认能力推断。

验证：

```text
浏览器走查：
  左侧产品列表：通用 AI / PPT 设计师 / 新建 AI 产品
  旧可见命中：Dashboard / Kanban / Insights / Workbenches / 工作台 / Hermes / 研究分析师 / 数据分析师 -> 0
  PPT 设计师：右侧显示 Agent 写出的产品界面
  新建 AI 产品：进入创建页，文案说明“确认后创建并生成第一版界面”
  通用 AI：普通 Chat，右侧产品界面隐藏

静态检查：
  node --check vendor/hermes-webui/static/product-shell-runtime.js
  node --check vendor/hermes-webui/static/product-store.js vendor/hermes-webui/static/product-runtime.js vendor/hermes-webui/static/messages.js

搜索检查：
  左侧 research/data 静态入口和对象标题已不存在

API 检查：
  GET /health -> ok
  GET /api/products -> only ppt-designer, ui_status=ready
```

结论：

```text
首屏现在更贴近 MVP：
不是一堆“助手预设”，而是一个 AI 产品母体。
真实可用的产品才出现在产品库；未创建的方向从“新建 AI 产品”长出来。
```

## 8. 固定验证矩阵

### 8.1 后端静态检查

```bash
python3 -m py_compile vendor/hermes-webui/api/products.py vendor/hermes-webui/api/product_context.py vendor/hermes-webui/api/routes.py vendor/hermes-webui/api/streaming.py
```

### 8.2 前端静态检查

```bash
node --check vendor/hermes-webui/static/product-shell-runtime.js
node --check vendor/hermes-webui/static/product-store.js
node --check vendor/hermes-webui/static/product-runtime.js
node --check vendor/hermes-webui/static/messages.js
node --check vendor/hermes-webui/static/sessions.js
node --check vendor/hermes-webui/static/ui.js
node --check vendor/hermes-webui/static/commands.js
```

### 8.3 API smoke

```text
GET /api/products
POST /api/products/create
GET /api/products/<id>/status
GET /api/products/<id>/preview
GET /api/products/<id>/style.css
GET /api/products/<id>/app.js
POST /api/products/<id>/rollback
POST /api/products/delete
```

### 8.4 Browser smoke

```text
打开 http://localhost:8788/
确认首屏只表达 AI 产品库
选择 PPT 设计师
确认右侧是 product preview
新建临时产品
确认 empty/generating/ready/failed 状态清楚
删除临时产品
刷新确认不残留
```

### 8.5 Agent smoke

```text
product_init:
  新建产品后会写 index.html/style.css/app.js。

product_usage:
  普通任务不会无故重写界面。

product_builder:
  用户明确要求改界面或以后这样时，会 snapshot 并改产品 UI。
```

### 8.6 PPT smoke

```text
选择 PPT 设计师。
输入：做一个介绍 Codex 的 PPT。
确认右侧出现 PPT 产品界面。
输入：以后讲稿区放右边。
确认界面被修改。
点击恢复上一版界面。
确认 preview 回到上一版。
```

## 9. 暂时不做

这些会把第一版拉复杂，先明确不做：

- 完整 app builder。
- 拖拽 UI 编辑器。
- 复杂 diff viewer。
- 产品市场。
- 技能市场首屏。
- 把 PPT、图片、研究、数据全部写成前端硬编码 block。
- 移动端深度优化。
- 一次性重构完整 Hermes WebUI。
- 预置十几个产品类型。
- 继续兼容旧 workbench 主路径、旧 hidden block、旧推荐工作台协议。

## 10. 下一步最精确开工顺序

当前 P0、P1、P2、P2.5、P3、P4、P5、P6、P7、P8、P9 第一轮已完成；P10.1/P10.2 已完成旧 workbench 主路径、兼容清洗和非默认入口删除；P10.3 已验证新建产品、product_init 写文件、product_builder 改界面、snapshot/rollback 和临时清理；P11/P12 已完成主运行时语义和可见文案收敛；P13 已补齐 `product_init` 聊天状态卡、首次生成取消/失败态、自然 UI 改造意图识别、失败重试 scope 和运行中 steer 的 product context；P14 已清理 i18n 里用户可能看到的旧 workbench 文案；P15 已把正式自定义产品收束为后端 product-backed 路径；P16 已补齐产品任务的 session 持久绑定；P17 已补齐产品生成 ready/failed/cancel 的终态一致性；P18 已补齐当前 turn product scope 与本地 session 的一致性；P19 已补齐产品界面资产级 snapshot/rollback；P20 已保护版本快照目录不被 rollback 清理误动；P21 已删除旧 localStorage 产品缓存数据源；P22 已让删除自定义产品默认清理产品目录；P23 已把新建产品文案收束到“确认后立即生成”；P24 已把内置产品派生文案收束为“专属产品”；P25 已让产品界面生成/改造优先于旧职责调整逻辑；P26 已让产品 tools 成为 product session 的后端默认能力；P27 已让 Chat 运行入口可从 product session 恢复 product context；P28 已让运行中 steer 可从 product session 恢复 product context；P29 已让产品 status 接口按文件事实保守自愈；P30 已让首次 product_init 可见消息不再重复创建描述；P31 已删除旧助手职责进化分支；P32 已让空/失败产品首轮统一进入 `product_init`，删除隐藏高级导航入口，并把 shell 切换/旧 CSS 收束到 Chat + Settings；P33 已补齐非 PPT 产品创建和自动初始化前端 smoke；P34 已直接删除不可达旧面板逻辑和 Dashboard/Insights 残留；P35 已证明非 PPT 产品能通过真实流式 Agent 写出自己的产品界面；P36 已把 `product_init` 从约 5 分半压到 80.8 秒，并验证 ready 产品普通 `product_usage` 不会误改 UI；P37 已删除旧后端兼容残留；P38 已继续收紧 `product_init` 首次写文件指令，并让等待态明确显示“正在生成第一版产品界面”；P39 已证明 `gpt-5.4-mini` 可以跑通 MVP 主链路，同时确认默认 `gpt-5.5` 当前存在首轮无响应超时风险；P40 已继续删除旧 Insights 接口、设置 key、翻译和专属样式；P41 已让默认 `product_init` 失败原因进入产品状态和可见 failed 态；P42 已真实复测默认/快速模型主链路，并修复否定式 UI 意图误判；P43 已完成首屏可见走查，并删除未落地的研究/数据预设产品入口。接下来按这个顺序开工：

```text
1. 跑一次真实“新建 AI 产品 -> 自动生成第一版产品界面 -> 普通聊天不误改界面”的完整链路。
2. 针对 PPT 产品跑一次真实“生成 PPT / 普通聊天 / 明确改界面”主链路。
3. 继续删除只服务旧 Hermes WebUI、但不服务 MVP AI 产品链路的可见复杂入口。
```

下一步不要再扩功能，先沿 MVP 主链路走查。原因：

```text
产品运行时边界已经基本收干净。
可见主路径已经统一为 AI 产品 / 产品界面。
下一步不该继续抛光表面，而该让“新建产品 -> 自动生成产品界面 -> 继续普通聊天改造”更自然。
```

P3 完成后，Next AI 的第一屏已经收束为：

```text
左侧：AI 产品库 + 最近任务。
中间：当前 AI 产品的 Chat。
右侧：当前 AI 产品自己生成的产品界面。
```

这就是后续所有功能的地基。

# Engineering Health TODO

更新日期：2026-06-18

本文只处理代码结构、可读性、可维护性和渐进式 TypeScript 化，不定义新的产品模型。
产品模型仍以 `docs/PRODUCT_MODEL_CONTRACT.md` 为准。

## 0. 当前判断

项目的产品抽象已经比较清楚：`products/<id>/product.json` 是产品事实来源，前端把后端产品 hydrate 成可选 AI object，运行时通过 `product_scope` 区分使用、初始化和调整。

主要工程问题不在概念层，而在实现层：

- 前端仍是多个大型 `defer` 脚本按顺序挂全局函数。
- `routes.py` 和 `streaming.py` 仍承担过多后端胶水和业务。
- `assistant` / `product` 双词汇仍在前端大量混用。
- 产品逻辑、session 逻辑、DOM 渲染、SSE、toolsets、preview bridge 互相穿插。
- 测试覆盖后端较强，前端模块级测试不足。

目标不是重写，而是建立边界，让每次修改有明确落点。

第二轮阅读后更明确的判断：

- 产品主线本身是清楚的：product registry -> frontend AI object -> session product binding -> product context -> streaming runtime prompt -> product finalize/status。
- 现在最危险的不是“没有架构”，而是“架构靠巨型文件里的隐式全局函数维持”。
- 第一批治理应优先修可见风险：access preset/toolsets 语义、`product_init` 状态文案、product turn finalize 所在位置。
- TS 可以作为新模块的约束工具，但不应该作为一次性重写策略。

## 1. 治理原则

- 不做全量重写。每一步保持现有 UI 和 API 行为可用。
- 先拆纯逻辑，再拆 DOM，再考虑 TS。
- 先给旧全局 API 套兼容层，再逐步迁移调用方。
- 每个阶段都必须有可运行验证：`pnpm verify`，相关 pytest，以及必要的浏览器冒烟。
- 单文件目标：普通模块 300-800 行；复杂核心模块最多约 1200 行。
- 新代码禁止继续扩大 `ui.js`、`messages.js`、`routes.py`、`streaming.py`。

## 2. 第一阶段：冻结结构继续变大

### 2.1 建立代码体量守门

文件：

- `apps/webui/static/ui.js`
- `apps/webui/static/messages.js`
- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/product-runtime.js`
- `apps/webui/api/routes.py`
- `apps/webui/api/streaming.py`

TODO：

- 新增一个简单检查脚本，统计关键文件行数。
- 允许当前基线超限，但禁止这些文件继续显著增长。
- 在 `pnpm verify` 或本地检查里输出警告。

验收：

- 能看到当前巨型文件清单和行数。
- 后续新增产品逻辑时有明确提醒，不再默认塞进巨型文件。

### 2.2 标注大型文件责任区

TODO：

- 在每个巨型文件顶部补一段维护说明。
- 写清楚“新代码应该放到哪里”，例如 product 逻辑去 `product-*` 模块，route handler 去新文件。
- 不移动代码，只补说明。

验收：

- 新人打开文件能知道这是 legacy aggregation file。
- 后续重构不会迷路。

### 2.3 明确前端启动阶段

来源：

- `apps/webui/static/boot.js`
- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/sessions.js`

TODO：

- 写清楚当前 boot 顺序：
  - defer script order。
  - `product-shell-runtime.js` DOMContentLoaded self-start。
  - `boot.js` settings/profile/model/workspace/onboarding。
  - product hydrate。
  - saved/url session restore。
  - preview/task UI sync。
- 把产品 hydrate 从“DOMContentLoaded 自启动 + boot 并行跑”逐步变成显式 boot phase。
- 先不改行为，可以先加小注释或 `bootProducts()` / `productsHydrated` 兼容函数。
- 明确 BFCache restore 是否需要重新等待 products hydrated。
- 第一阶段可以不阻塞首屏，但必须暴露可等待状态：
  - `window.productsHydrated` promise。
  - `window.productsHydrateError` 或 product hydrate fallback state。
  - `products:hydrated` custom event。
- `boot.js` 恢复 saved/url session 时，至少能选择：
  - 等待 products hydrated 后再 `loadSession()`。
  - 或先 `loadSession()`，但用同一个 product reconciliation step 收敛，不把逻辑散在多个函数。
- BFCache `pageshow` 走同一个 product reconciliation step，不再只靠 `loadSession()` 内部分支补救。
- `applyBotName()` 调 `syncAssistantTaskUi()` 前后可能早于 product hydrate；需要明确这是 fallback sync，不是最终 product state。

验收：

- 新人能知道 saved product session 是在哪里恢复的。
- 产品 hydrate、session restore、preview refresh 的顺序不再靠读多个全局文件推断。
- product-bound saved session 在 products hydrate 慢于 session restore 时不闪到 general。
- BFCache 恢复 product-bound session 时最终产品、task list、preview 一致。
- 启动失败路径下 session list、AI shelf、empty state 都有明确 fallback。

## 3. 第二阶段：前端产品线模块化试点

这是最适合先拆的区域，因为产品逻辑是当前业务核心，而且已有比较明确的模型。

### 3.1 拆出 product model 纯逻辑

来源：

- `apps/webui/static/product-store.js`
- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/product-runtime.js`

目标文件：

- `apps/webui/static/product-model.js`

内容：

- `normalizeProductLayout`
- `productLayout`
- `usesProductCanvas`
- `hasGeneratedProductCanvas`
- `effectiveProductLayout`
- `canvasLabel`
- `normalizeToolsets`
- `uniqueCapabilityList`
- `defaultCapabilitiesForProduct`
- `isBuiltinGeneralProduct`

要求：

- 不直接读写 DOM。
- 不直接读写 `window`。
- 输入 object，输出 plain value。
- 明确写入 canvas availability 规则：
  - `chat_only` 默认不显示 canvas。
  - `chat_only` 已有 generated canvas 时可提升为 `chat_left_canvas_right`。
  - `general` 永不就地长 canvas。
  - `uiStatus=generating` 可以临时显示 workspace 状态。
- 前端 toolset alias 必须和后端 `PRODUCT_TOOLSET_ALIASES` 用 fixture 对齐。

兼容方式：

- 老的 `_assistantUsesProductCanvas` 等函数先保留。
- 老函数内部调用新模块函数。

验收：

- 产品布局判断行为不变。
- `product-store.js` 行数下降。
- 可以为纯函数补轻量 JS 测试或静态断言。
- 前后端对同一组 layout/tool/capability fixture 输出一致。

### 3.2 拆出 product adapter

目标文件：

- `apps/webui/static/product-adapter.js`

内容：

- 后端 product -> 前端 AI object。
- snake_case / camelCase 翻译。
- builtin copy 归一化。
- product session default toolsets。
- ready/generating/empty/failed 到 canvas availability 的映射。
- preview URL、workspace path、canvas label、skills/tools 的单点转换。

要求：

- 明确把 `assistant` 作为兼容层命名，而不是核心模型命名。
- 新代码用 `product` 命名，旧导出可以继续叫 `currentAssistantProductSessionDefaults`。

验收：

- `_productToCustomAssistant` 从 `product-store.js` 移走。
- `product-store.js` 只保留 hydrate、保存和能力面板胶水。
- custom product、builtin product、chat_only product、missing preview product 都有 adapter fixture。

### 3.3 拆出 product context client

目标文件：

- `apps/webui/static/product-context-client.js`

内容：

- 当前产品对象解析。
- `product_usage` / `product_init` / `product_builder` scope 生成。
- pending scope / pending intent 的读写。
- `withCurrentProductContext`。

要求：

- 把 `window._nextAiPendingProductScope` 这类隐式状态封装成小 API。
- 外部调用不再直接读写 `_nextAiPendingProductScope`。

验收：

- `messages.js` 仍能通过一个函数拿到 product context。
- `product-runtime.js` 中 pending state 直接操作减少。

### 3.4 拆出 product preview bridge

目标文件：

- `apps/webui/static/product-bridge-host.js`

内容：

- iframe postMessage 监听。
- `NextAI.chat.send` host 侧处理。
- product canvas state get/set/remove/clear。
- pending bridge request map。
- agent reply/error 回传。
- `nextai:product:download` URL 校验。
- host ready / ack / reply / state / error / agent broadcast 的统一发包。
- pending request 以 `requestId` 为第一匹配维度，session id 只作为路由上下文，避免同一 session 内多个 canvas request 串线。
- host timeout 时主动给 iframe 发 `nextai:host:error`，不要只删除 pending。
- 当前复核：
  - SDK pending 已经以 requestId 为 key。
  - host pending 仍以 sessionId 为 key，requestId 只放在 pending value。
  - host timeout 当前只 delete pending，不主动 post error。
  - `notifyProductCanvasAgentReply()` fallback 到唯一 pending 的行为可用但模糊，requestId primary 后应移除或收窄。

要求：

- bridge 和 preview UI 状态分离。
- host bridge 不负责打开/关闭 UI，只负责消息协议。
- 不再由 bridge 直接读写 `#msg`、`S`、`window._nextAiPendingHiddenAgentInstruction`；通过一个注入的 chat transport 发送。
- canvas send 的隐藏上下文不要再拼到用户 message 字符串里，改为结构化字段。
- host reply 至少支持 `{content, message, raw}`，并明确 assets / image_url 的传递规则。
- 当前 SDK `NextAI.chat.send()` 返回 `{content, raw}`，但 host `nextai:host:reply` 只携带 `content`；需要让 host reply 和 SDK return shape 对齐。
- 图片/文件/结构化产物统一放在 `assets[]` / `files[]` / `data`，旧的 `raw.image_url` 只能作为兼容字段，不允许新产品继续猜 `res.image_url`。
- `nextai:host:ack` 语义保持不变：只表示 host 收到请求，不 resolve `NextAI.chat.send()` promise。
- download URL 必须限制到当前 product 的 preview/assets/output 路径，不接受任意外部 URL 或跨 product URL。
- download allowlist 不要只写在前端 host JS 里；应复用后端 product asset resolver 或同一份规则说明。
- product preview HTML/SVG 的 route 响应策略要和 bridge download contract 对齐，避免 iframe 内安全、直接打开 URL 不安全。
- `NextAI.state` 的 host 存储策略要写清楚：当前是宿主 localStorage，不等价于后端产品事实状态。
- SDK fallback state 是 iframe localStorage，host state 是宿主 localStorage；两者 scope/持久化边界必须写进 contract。

验收：

- `product-runtime.js` 不再同时负责 scope、preview、bridge、polling。
- bridge 协议可以单独阅读。
- AI Otome 画像生成能从 typed reply 中拿到图片 URL，不需要猜 `res.image_url` 还是 `res.raw.image_url`。
- iframe 传入非当前产品 preview/assets 的 download URL 时被拒绝。
- iframe bridge timeout、host timeout、SSE error 三种失败会走同一套 error contract。
- 同一 session 内并发两个 canvas request 不会互相覆盖 pending request。
- ack 事件可以用于 UI 显示“已发送”，但不会被产品 app 误认为“已完成”。

### 3.5 拆出 product preview controller

目标文件：

- `apps/webui/static/product-preview-controller.js`

内容：

- preview URL 刷新。
- status polling。
- `_activeProductPreview` 的读写封装。
- reload / close / open external window。

要求：

- `_activeProductPreview` 不再作为裸全局变量被多个文件直接改。
- 提供 `getActiveProductPreview()` / `setActiveProductPreview()` / `clearActiveProductPreview()`。

验收：

- `product-shell-runtime.js` 对 preview state 的直接读写明显减少。
- 关闭 chat-only 产品时 preview 状态不会散落清理。

### 3.6 合并或改名 product evolution

来源：

- `apps/webui/static/product-evolution.js`

TODO：

- 当前文件只有 rollback action，不承担 evolution 模型。
- 合并进 `product-preview-controller.js`，或改名为 `product-recovery-actions.js`。
- rollback 文案从“产品界面”调整为更通用的 “workspace / version”，避免和 chat_only 产品概念冲突。
- rollback action 依赖 `_activeProductPreview`，后续应改为 preview controller API。

验收：

- 版本恢复入口仍可用。
- 文件名和职责一致，不再暗示这里有完整演化系统。
- snapshot 失败时不会展示误导性的 rollback 操作。

### 3.7 拆出 productize suggestion

来源：

- `apps/webui/static/ui.js`
- `apps/webui/api/product_context.py`

目标文件：

- `apps/webui/static/productize-suggestion.js`

TODO：

- 把 `NEXT_AI_SUGGEST_PRODUCT` marker 的 strip/parse/render/click 从 `ui.js` 拆出。
- click 时保留 marker 中的 `title/type/prompt`，不要只传 prompt。
- 当前状态：`_parseProductSuggestMarker()` 返回 `title/prompt/type`，但按钮只写 `data-product-prompt`，`_onProductSuggestClick()` 只传 prompt。
- 增加一个确认/编辑层，让用户能改 title/type 后再创建 draft。
- 明确 marker 只属于 chat_only usage，不属于 canvas usage 或 builder。
- `createProductFromPrompt()` 支持 object payload：
  - `{title, prompt, type}`。
  - 继续兼容 string prompt。
- `/api/product-drafts/create` 支持接收 suggested/product type：
  - `interactive`
  - `ppt`
  - `image`
  - `research`
  - `data`
- draft manifest 不应永远固定：
  - `product_type: custom`
  - `ui_mode: chat_only`
  - `product_layout: chat_only`
  - empty `skills/tools`
- Creator draft instruction 要能看到 marker title/type，避免 agent 重新猜一次产品方向。

验收：

- UI parse/render/click 有测试。
- 流式未闭合 marker 不会露给用户。
- productize 创建 draft 时保留 title/type。
- interactive/ppt/image/research/data marker 能生成对应 draft defaults。

### 3.8 拆出 product session owner

来源：

- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/sessions.js`

目标文件：

- `apps/webui/static/product-session-owner.js`

内容：

- session -> product/assistant kind 的归属判断。
- localStorage assignment 读写。
- legacy title/message heuristic。
- product-bound session 的 hydrate fallback。
- task list filtering。

要求：

- 新 session 优先使用 `session.product_id`，assignment 只作为旧数据兼容。
- `assistantTaskBelongsToCurrentAssistant()` 和 `assistantKindForLoadedSession()` 使用同一套优先级。
- 无效 assignment 自动清理，但不能覆盖 session 自带 product id。
- legacy heuristic 只用于没有 product id、没有 assignment 的老会话。

验收：

- product-bound session 在 task list 和 loaded session 中归属一致。
- hydrate 慢于 session restore 时，最终能切回正确 product。
- 切换/删除 custom product 后 assignment 清理有测试。

### 3.9 抽出 product shell state reducer

来源：

- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/style.css`

目标文件：

- `apps/webui/static/product-shell-state.js`

内容：

- 从当前 product、hasTask、active preview、layout、adjust/chat panel state 计算 UI 状态。
- 输出 body dataset 和关键区域 visibility，不直接操作 DOM。

要求：

- `syncAssistantTaskUi()` 先调用 pure reducer，再执行 DOM patch。
- 覆盖 `chat_only`、`chat_left_canvas_right`、`canvas_full`、adjust、manual chat panel 的状态组合。

验收：

- `syncAssistantTaskUi()` 的分支明显减少。
- body dataset 状态组合有快照测试。
- CSS layout 状态和 JS reducer 输出能一一对应。

### 3.10 抽出 product boot coordinator

来源：

- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/boot.js`
- `apps/webui/static/sessions.js`

目标文件：

- `apps/webui/static/product-boot-coordinator.js`

内容：

- 产品默认对象注册。
- backend products hydrate。
- products hydrated promise/event。
- product-bound session restore reconciliation。
- BFCache restore reconciliation。
- hydrate failure fallback。

要求：

- `initNextAiAssistants()` 不再是不可等待的 DOMContentLoaded 自启动黑盒。
- `boot.js` 可以明确等待或订阅 product hydration。
- `loadSession()` 不需要多次散落调用 `syncAssistantForLoadedSession()` 来补救每个阶段。
- product selection、task list filtering、preview refresh 共用同一个 reconciliation 函数。

验收：

- hydrate 慢于 session restore 的场景有测试。
- BFCache 恢复 product-bound session 的场景有测试。
- 新建 product 后 hydrate/select/preview refresh 顺序可追踪。
- 产品 hydrate 失败时有明确 fallback，不会静默停在 General AI。

## 4. 第三阶段：前端 UI 层减肥

### 4.1 拆 product shell view

来源：

- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/panels.js`

目标文件：

- `apps/webui/static/product-shell-view.js`
- `apps/webui/static/product-list-view.js`
- `apps/webui/static/product-task-header.js`
- `apps/webui/static/product-app-chrome.js`

拆分：

- AI/product 列表渲染。
- home/landing 面板渲染。
- task header 和 preview chip。
- adjust/use 模式按钮。
- app titlebar 所需的 product chrome state：
  - `main`
  - `sub`
  - `documentTitle`

要求：

- `panels.js` 不直接理解产品 task/title 细节，只调用稳定的 app chrome adapter。
- 缺少 product shell adapter 时，`panels.js` 保持 chat/settings fallback。
- `assistantChromeTitleState()` 作为 legacy alias 保留一段时间，但新代码命名应转为 `productChromeTitleState()`。

验收：

- `product-shell-runtime.js` 降到约 1000 行以内。
- view 文件只做 DOM，不负责产品业务判断。
- app titlebar 在 AI shelf、active task、settings panel、read-only session 下都有测试。

### 4.2 拆 access presets

来源：

- `apps/webui/static/ui.js`

目标文件：

- `apps/webui/static/access-presets.js`

内容：

- Default / Files / Full Access / Custom 判断。
- session toolsets chip。
- product default toolsets 恢复。
- unknown/custom toolsets 显示为 Custom，不再默认当成 Files。
- 明确区分 “inherit product default” 和 “clear session override”。

验收：

- `ui.js` 不再承载 product/toolsets 业务。
- `['skills', 'image_gen']` 不会被误判为 Files。
- 点击 Default 不会把产品默认工具丢掉。

### 4.3 拆 message send controller

来源：

- `apps/webui/static/messages.js`

目标文件：

- `apps/webui/static/messages/send-controller.js`
- `apps/webui/static/messages/stream-controller.js`
- `apps/webui/static/messages/product-status-cards.js`

拆分：

- `send()` 只做流程编排。
- 当前实读确认 `send()` 仍同时承担：
  - re-entrant queue guard。
  - Create AI special-case。
  - busy queue/interrupt/steer routing。
  - slash command execution。
  - upload。
  - optimistic user message / session row。
  - product status running card。
  - `/api/chat/start` payload build。
  - active-stream conflict queue。
  - SSE attach。
- SSE event 处理独立。
- SSE `done` 当前同时承担：
  - session/message replacement。
  - usage delta。
  - tool call finalization。
  - bridge reply + agent broadcast。
  - Creator draft publish.
  - product preview refresh。
  - product status done/failed card。
  - goal continuation queue。
  - notification。
- 产品初始化/调整状态卡独立。
- hidden product instruction 改成请求体结构化字段，不再拼到 `message` 文本里。
- Creator draft instruction 和 product canvas bridge instruction 现在都走 `_nextAiPendingHiddenAgentInstruction`；需要统一成结构化 `hidden_instructions[]` 或 `internal_context` 字段。
- 已确认后端风险链路：
  - `/api/chat/start` 直接读取 `body.message` 为 `msg`。
  - `_prepare_chat_start_session_for_stream()` 会把 `msg` 写入 `pending_user_message`，eager 模式还会 checkpoint 到 `messages`。
  - turn journal `submitted.content` 写入同一个 `msg`。
  - `_run_agent_streaming()` 使用同一个 `msg_text` 作为 `persist_user_message`。
  - cancel / crash recovery 会从 `pending_user_message` 恢复 user turn。
  - 所以 hidden instruction 一旦拼进 `message`，就可能进入 journal、title、recovery、context merge。
- `/api/chat/start` payload 应拆成：
  - `message`: 用户可见原文。
  - `internal_context`: bridge/creator/product control context。
  - `product_context`: product_id/scope/intent。
- 后端负责把 `internal_context` 注入 ephemeral/system prompt，不把它当 user message 保存；现有 `_webui_ephemeral_system_prompt()` 是正确注入口。
- queue/conflict/retry 路径必须保存和恢复 structured internal context，而不是拼接后的 `msgText`。
- queue drain 直接恢复完整 product context，包括 `product_id`，不依赖当前 product selection 间接推断。
- `_restoreSettledSession()` 补齐 done path 中和产品有关的 preview refresh / bridge reply / status card 行为，或者明确它只负责恢复 transcript。
- `productUiStatusContext` 的创建、INFLIGHT 持久化、done/error/cancel/restore 消费收敛成一个 product turn status controller。
- bridge reply、preview refresh、product status card 不再散落在 SSE done handler 中。
- `setBusy(false)` 不再直接 drain queue；它只表达 UI busy state，queue drain 交给 queue controller。
- 抽 `buildChatTurnRequest()`：
  - visible message。
  - display user message。
  - attachments。
  - product context。
  - internal context。
  - model/provider/profile。
- 抽 `sendChatTurnRequest(request)`：
  - 不读 DOM。
  - 不读 `_nextAiPending*` 全局。
  - 只负责 `/api/chat/start`、INFLIGHT setup、SSE attach。
- 抽 `productTurnCompletionController`：
  - done / error / cancel / restore 都调用同一组接口。
  - status card、preview refresh、Creator publish 在这里收口。
- 抽 `bridgeReplyController`：
  - 从 assistant message 生成 typed bridge reply。
  - 与 agent broadcast 分离。
- 建议拆出的后端 helper：
  - `normalize_chat_start_payload(body, session)`：输出 visible message、attachments、product_context、internal_context。
  - `build_internal_context_prompt(internal_context)`：把 Creator / canvas bridge 内部上下文转成 ephemeral prompt。
- `_start_chat_stream_for_session()` / `_run_agent_streaming()` 先兼容增加 `internal_context=None`，只用于 ephemeral prompt，不用于 `persist_user_message`。

验收：

- `messages.js` 中 product 相关代码迁出。
- SSE live row、error、product bridge reply 的关系能单独读懂。
- `send()` 主体明显缩短，且不再直接拼 hidden instruction 到 `msgText`。
- `/api/chat/start` payload 由 request builder 生成，可单测。
- queued product turn 在 hydrate/selection 竞态下仍发送到原始 product_id。
- SSE done、apperror、cancel、connection restore 四条路径的 product UI 状态一致。
- durable inflight 恢复后，product init/build running card 和后续 done/failed card 一致。
- `_restoreSettledSession()` 不会静默丢失产品 preview refresh 或状态卡。
- bridge/creator hidden instruction 不会进入 visible transcript，也不会被 session title / product intent / queue text 当作用户内容。
- 单测覆盖：
  - `message="hello"` + `internal_context` 时，`pending_user_message` / journal / `persist_user_message` 都只看到 `"hello"`。
  - agent `ephemeral_system_prompt` 包含 internal context。
  - eager save、cancel、recovery 都不会把 internal context 合成 user turn。

### 4.4 建立 product app SDK/contract

来源：

- `apps/webui/static/product-bridge-sdk.js`
- `apps/webui/static/product-runtime.js`
- `products/ai-otome/app.js`
- `products/ppt-designer/app.js`

目标文件：

- `apps/webui/static/product-bridge-sdk.js` 先保留兼容。
- 新增 `docs/PRODUCT_APP_SDK_CONTRACT.md` 或并入 `docs/PRODUCT_MODEL_CONTRACT.md`。

内容：

- `NextAI.chat.send` request/response。
- `NextAI.state.get/set/remove` scope、timeout、fallback 规则。
- `nextai:agent` broadcast event。
- `nextai:product:download` 下载协议。
- `nextai:host:ready` / `nextai:host:ack` / `nextai:host:reply` / `nextai:host:error` / `nextai:host:state` / `nextai:host:agent_message` event shape。
- source/window guard：
  - iframe SDK 只接受 parent 发来的 `source:'nextai-host'`。
  - host 只接受 active iframe contentWindow 发来的 `source:'nextai-product-canvas'`。
  - product iframe 当前 sandbox 是 `allow-scripts allow-forms`，没有 `allow-same-origin`，所以 origin 字符串不是可靠校验源。
- workspace `state.json` 作为 AI -> GUI 通道的推荐约定。
- 产品 app 启动优先级：
  - defaults 立即 paint。
  - session state 作为用户交互状态。
  - workspace `state.json` 作为 agent 写出的 GUI 事实。
  - demo/seed 数据只在显式 demo 模式生效。
- `nextai:host:ack` 只表示 host 已接收，不表示 agent 已完成；SDK timeout 从 send 到 reply 全程生效。
- host state 和 iframe fallback state 的边界：fallback 只兜底交互，不可作为跨 session 事实来源。
- typed response 字段：
  - 普通文本：`content`。
  - 结构化内容：`raw` 或明确的 `data` 字段。
  - 图片/文件产物：统一 `assets[]` 或 `files[]`，不要让产品 app 猜 `image_url` / `content_url`。
- 产品 app 首屏规则：
  - 先 paint 默认状态。
  - bridge state 使用短 timeout。
  - workspace `state.json` 可覆盖默认状态，但不能被 demo 数据覆盖。

验收：

- AI Otome 和 PPT Designer 的 bridge 用法能用同一份 contract 解释。
- state get timeout 策略统一，不需要产品 app 各自写 race。
- image response、structured response、download response 有明确字段。
- 产品 app 里不得直接依赖未记录字段，例如裸 `res.image_url`；兼容字段也必须由 SDK 文档声明。
- PPT Designer 不会在正常启动路径中用 demo deck 覆盖 session state 或 `state.json`。
- AI Otome 不会在 first paint 前无限等待 host state。

### 4.5 清理产品 app demo 残留

来源：

- `products/ppt-designer/app.js`

TODO：

- 把 `HEYTEA_DECK` 从默认启动路径移走。
- 改成 `?demo=heytea`、`demo/heytea.json` 或单独示例入口。
- 正常启动顺序应是：默认状态 -> session state -> workspace `state.json`，不能再被内置 demo 覆盖。
- 清理 `products/ppt-designer/state.json` 的 demo 数据定位：
  - 如果是示例，移动到 demo seed。
  - 如果是当前用户工作产物，避免作为默认模板被新会话继承。

验收：

- 普通打开 PPT Designer 不会强制显示喜茶 deck。
- 用户 session state 和 workspace `state.json` 不会被 demo 数据覆盖。
- 刷新页面后仍显示上一次保存/生成的真实 deck。

## 5. 第四阶段：后端 routes.py 拆分

当前 `server.py` 已经是薄壳，应该保留。真正要拆的是 `api/routes.py`。

### 5.1 建立 route registry

目标：

- 保留 `handle_get` / `handle_post` 入口。
- 增加内部 registry 或分发 map。
- 每组 API 迁移到独立模块。

建议目录：

- `apps/webui/api/routes_auth.py`
- `apps/webui/api/routes_sessions.py`
- `apps/webui/api/routes_chat.py`
- `apps/webui/api/routes_products.py`
- `apps/webui/api/routes_files.py`
- `apps/webui/api/routes_workspaces.py`
- `apps/webui/api/routes_models.py`
- `apps/webui/api/routes_system.py`
- `apps/webui/api/routes_skills.py`
- `apps/webui/api/routes_crons.py`

验收：

- `handle_get` / `handle_post` 先只委托，不改行为。
- 每迁移一组跑对应 pytest。

### 5.2 先迁 product routes

来源：

- `/api/products`
- `/api/product-drafts/create`
- `/api/products/draft/create`
- `/api/products/create`
- `/api/products/update`
- `/api/products/delete`
- `/api/products/finalize`
- `/api/products/<id>/status`
- `/api/products/<id>/versions`
- `/api/products/<id>/snapshot`
- `/api/products/<id>/rollback`
- product preview route
- product asset route

目标文件：

- `apps/webui/api/routes_products.py`

原因：

- 产品 registry 已经在 `api/products.py`，路由层容易抽。
- 和当前工程健康目标最相关。

验收：

- 产品 API 行为不变。
- `test_product_*` 通过。
- `routes.py` product 分支减少。
- product preview/asset 路径覆盖默认 index、嵌套文件、路径逃逸、缺文件、`Cache-Control: no-store`。
- product preview HTML 直接打开时也有 CSP sandbox，不只依赖 iframe sandbox。
- SVG / dangerous MIME 有明确 inline/download 策略，不能默认裸 inline。
- draft create 两个兼容入口都覆盖。
- `/api/products/<id>/status` 仍然 reconcile-on-access。
- `/api/products/<id>/preview` 和 `/api/products/<id>/<asset>` 使用同一个 asset resolver。
- `_serve_product_preview` / `_serve_product_asset` 合并成单一产品 asset handler。

### 5.3 再迁 session routes

来源：

- `/api/session/new`
- `/api/session/update`
- `/api/session/delete`
- `/api/session/toolsets`
- `/api/session/rename`
- `/api/session/branch`
- `/api/session/duplicate`
- `/api/session/status`
- `/api/sessions`
- `/api/sessions/search`

目标文件：

- `apps/webui/api/routes_sessions.py`

注意：

- session 和 chat start 现在耦合较深，先迁 CRUD，不急着迁 chat。

验收：

- session 相关测试通过。
- chat start 暂时仍可留在 `routes.py`。

## 6. 第五阶段：后端 streaming.py 拆分

### 6.1 拆 provider error handling

目标文件：

- `apps/webui/api/streaming/provider_errors.py`

内容：

- quota / auth / provider error 分类。
- error payload。
- provider hint。

验收：

- provider error 相关测试通过。
- `streaming.py` 顶部辅助函数减少。

### 6.2 拆 title generation

目标文件：

- `apps/webui/api/streaming/title_generation.py`

内容：

- title prompt。
- aux title。
- fallback title。
- title refresh background job。

验收：

- title 相关 tests 通过。

### 6.3 拆 message sanitizer/context builder

目标文件：

- `apps/webui/api/streaming/message_context.py`

内容：

- `_sanitize_messages_for_api`
- image part 处理。
- context compression marker。
- current user turn 合并/去重。

验收：

- compression、tool metadata、message merge 相关测试通过。

### 6.4 拆 agent runner

目标文件：

- `apps/webui/api/streaming/agent_runner.py`

内容：

- `_run_agent_streaming` 主体。
- agent import/cache/env 设置。
- product_context 注入。
- runtime adapter 调用。

验收：

- `streaming.py` 变成 SSE channel + public handlers。
- agent runner 可以独立阅读。

### 6.5 拆 product turn lifecycle

目标文件：

- `apps/webui/api/product_turns.py`
- `apps/webui/api/product_prompt_builder.py`

内容：

- product runtime prompt 构建：
  - product identity header。
  - init/build/use scope guidance。
  - chat_only adjustment guard。
  - PPT Designer canvas contract。
  - chat_only productize marker protocol。
- product init/build turn finalize。
- product steer context 恢复。
- failed/successful product status 统一落点。
- done/error/cancel/finally 四条路径的统一 finalize guard。
- build/init turn 前 snapshot，turn 后 finalize 的顺序约束。
- new session 和 chat start 的 product binding/session metadata/toolsets 共享 helper。

验收：

- `streaming.py` 不直接 import `finalize_product_generation`。
- `streaming.py` 的 done/error/cancel 分支只调用一个小 helper。
- `routes.py` 不再重复 new session / chat start 的 product binding 逻辑。
- “产品卡在 generating” 类问题可以只查 product lifecycle 模块。
- `product_ephemeral_prompt()` 从 monolith 变成几个小 builder，PPT/productize 特例有明确 owner。
- tests 覆盖：
  - success done -> `finalize_product_generation(failed=False)`。
  - provider error -> failed + error type/message。
  - cancel -> failed。
  - finally fallback 不会覆盖已成功 finalize 的 turn。
  - product_usage turn 不触发 UI finalize。
  - build/init start -> snapshot before run + record generating。
  - chat_only init/build -> 不标 generating UI。

## 7. 第六阶段：TypeScript 渐进迁移

不要直接重写全部前端。先让新模块可以用 TS 写。

### 7.1 引入 Vite/tsc 最小构建

目标：

- 新建 `apps/webui/static/src/`。
- 新 TS 模块编译到 `apps/webui/static/dist/`。
- 老 HTML 先只加载一个兼容 bundle。

建议配置：

- `tsconfig.json`
- `vite.config.ts` 或直接 `tsc`
- `pnpm typecheck`

验收：

- 构建产物可被现有 `index.html` 加载。
- 不影响旧 JS。

### 7.2 先 TS 化纯逻辑

优先顺序：

1. `product-model.ts`
2. `product-adapter.ts`
3. `product-context-client.ts`
4. `access-presets.ts`

要求：

- 定义 `Product`, `ProductLayout`, `ProductScope`, `Toolset`, `FrontendProductObject`。
- 不急着 TS 化 DOM 大文件。

验收：

- 类型能覆盖 product 字段转换。
- snake_case / camelCase 适配有明确边界。

### 7.3 再 TS 化 bridge 协议

目标：

- `product-bridge-types.ts`
- `product-bridge-host.ts`
- `product-bridge-sdk.ts`

验收：

- `nextai:product:send`、`nextai:product:state`、`nextai:product:download`、host reply/error、host agent broadcast 都有类型。
- 产品 iframe SDK 和 host 协议字段一致。
- AI Otome / PPT Designer 可以只依赖 typed SDK，不再猜 response 字段。
- typed reply 明确 `content`、`message`、`raw`、`assets`、`image_url` 的兼容策略。
- hidden product instruction 变成单独字段，不再靠文本 sentinel。

## 8. 第七阶段：命名统一

这一步必须在 product 模型稳定、模块边界稳定后做。

TODO：

- 新模块统一用 `product` 命名。
- 旧函数保留兼容导出一段时间。
- 分批替换 `_assistantXxx`：
  - model 层先替。
  - store/adapter 再替。
  - DOM view 最后替。
- 最后删除旧 alias。

验收：

- 新代码不再新增 `assistant` 命名，除非指聊天 role。
- `assistant` 只表示 OpenAI message role 或 legacy compatibility。

## 9. 第八阶段：测试补强

### 9.1 前端纯逻辑测试

覆盖：

- layout normalization。
- toolsets normalization。
- 前后端 `PRODUCT_TOOLSET_ALIASES` fixture parity。
- 默认 capabilities fixture parity。
- `general` 永不就地长 canvas。
- generated canvas promotion。
- access preset classification。
- custom/product toolsets 如 `['skills', 'image_gen']` 不被标成 Files。
- product session 的 Default/inherit 语义不丢默认工具。
- product -> frontend object adapter。
  - snake_case/camelCase 字段转换。
  - ready preview 判断。
  - generating/failed/empty canvas availability。
  - builtin copy override。
- product context scope generation。
- productize marker：
  - strip 完整 marker。
  - strip 流式未闭合 marker。
  - parse `title/prompt/type`。
  - 只在最后一条非 live assistant message 渲染按钮。
  - click 保留 `title/type/prompt`。
  - `createProductFromPrompt({title,prompt,type})` payload 传给 draft API。
  - draft manifest 根据 type 设置合理 `product_type/ui_mode/product_layout/skills/tools` defaults。
- product session ownership：
  - loaded session 优先 `product_id`。
  - task list filtering 优先 `product_id`。
  - invalid assignment 自动清理。
  - legacy heuristic 只服务旧会话。
  - hydrate 慢于 session restore 时最终切回 product。
- product message turn state：
  - `currentAssistantProductContextForMessage()` 生成 `product_id/scope/intent/explicit`。
  - `send()` 把 product context 合并进 `/api/chat/start` payload。
  - `_applyProductContextToCurrentSession()` 写当前 session metadata。
  - `productUiStatusContext` 被写入 INFLIGHT 和 durable inflight state。
  - `loadSession()` 能恢复 durable `productUiStatusContext` 并 reattach stream。
  - queue drain 保留 `product_id/product_scope/product_intent`。
  - `_restoreSettledSession()` 的 product status 行为和 done path 对齐。
- product shell body dataset state derivation：
  - `nextAiView`
  - `nextAiProductLayout`
  - `nextAiCanvas`
  - `nextAiProductAdjust`
  - `nextAiChatPanel`
  - `nextAiDirectory`
- product boot and app chrome：
  - `productsHydrated` promise/event exists。
  - hydrate slow + saved product session restore fast 最终 select 正确 product。
  - BFCache restore 会重新 reconcile product session。
  - `assistantChromeTitleState()` / future `productChromeTitleState()` 返回 `main/sub/documentTitle`。
  - `panels.js` 在 adapter 缺失时 fallback 到普通 chat/settings title。
- product script order：
  - `messages.js`
  - `product-store.js`
  - `product-shell-runtime.js`
  - `product-runtime.js`
  - `product-evolution.js`
  - `panels.js`
  - `onboarding.js`
  - `boot.js`
- product DOM contract：
  - active product surface / iframe / state card。
  - product chat header / status chips。
  - assistant directory / home。
  - product dialogs。
- product CSS ownership guard：
  - 允许重复 selector 的 override section 必须显式列名。
  - `.ai-object-item`、`.product-chat-header`、`.product-task-chip`、`.assistant-home`、`.active-product-surface` 先进入 duplicate audit。

### 9.2 bridge 协议测试

覆盖：

- canvas send -> host ack。
- agent reply -> canvas reply。
- state get/set/remove/clear。
- bad request error。
- download request。
- state host timeout fallback。
- host agent broadcast。
- 并发两个 pending request 时 reply 不串线。
- host reply 带 `raw.image_url` 时 SDK 能按约定暴露给产品 app。
- host reply 带 `assets[]/files[]/data` 时 SDK 能按约定暴露给产品 app。
- `nextai:host:ack` 不 resolve `NextAI.chat.send`，只触发 ack event。
- host pending timeout 会给 iframe 返回 error，SDK pending 被 reject。
- 非当前 iframe window 的 message 被拒绝。
- 非允许范围的 download URL 被拒绝。
- download allowlist 覆盖同 product nested `assets/` / `outputs/`、跨 product、外部 URL、`javascript:`、`data:`。
- direct product preview HTML 响应有 CSP sandbox，SVG 不裸 inline。
- hidden instruction 不出现在可见消息文本里，也不污染普通 user message 字段。

当前测试缺口：

- 没有直接加载/执行 `product-bridge-sdk.js` 的测试。
- 没有 host bridge pending map 行为测试。
- 没有 download URL allowlist 测试。
- 没有 shipped product 静态测试禁止裸 `res.image_url` / `res.content_url`。
- 没有 shipped product 静态测试禁止默认启动无条件 `applyDeckState(HEYTEA_DECK)`。

建议测试入口：

- `tests/test_product_bridge_sdk_js_behaviour.py`
  - Node/vm 加载真实 `static/product-bridge-sdk.js`。
  - mock `window.parent.postMessage`、`window.addEventListener`、storage。
  - 覆盖 ack 不 resolve、reply resolve、error reject、ready/agent event、source guard、state fallback。
- `tests/test_product_bridge_host_js_behaviour.py`
  - Node/vm 加载真实 `static/product-runtime.js`。
  - mock `$('activeProductFrame')`、`S`、`send()`、`fetch()`、`document`。
  - 覆盖 pending requestId 不串线、host timeout 主动 error、download allowlist。
- 本轮临时验证已经证明这些行为能被 Node/vm 捕捉：
  - SDK ack 不 settle，reply 后 resolve。
  - SDK state host timeout fallback 到 iframe localStorage。
  - host download 当前会 fetch 任意外部 URL。
  - host pending 当前同 session 两个 request 会让后一个覆盖前一个。

### 9.2.1 frontend product turn lifecycle tests

覆盖：

- `send()` build/init turn：
  - 生成 running status card。
  - `INFLIGHT[activeSid].productUiStatusContext` 存在。
  - durable inflight state 保存 `productUiStatusContext`。
  - `/api/chat/start` payload 带完整 product context。
- SSE `done`：
  - 刷新 product preview。
  - init/build 追加 done 或 failed status card。
  - builder turn 有 rollback 时展示 rollback action。
- bridge reply 和 agent broadcast 只在有 assistant content 时触发。

### 9.2.2 productize marker frontend behaviour tests

覆盖：

- `_stripProductSuggestMarker()`：
  - 完整 marker 从可见正文移除。
  - 流式未闭合 marker 从可见正文移除。
- `_parseProductSuggestMarker()`：
  - 解析 `title/prompt/type`。
  - 非 JSON / 无 prompt 时返回 null。
- render/click：
  - 按钮 DOM 保留 `data-product-prompt`、`data-product-title`、`data-product-type`。
  - `_onProductSuggestClick()` 调 `createProductFromPrompt({title,prompt,type})`。
  - string prompt 兼容路径仍可用。

当前缺口：

- 现有后端 prompt 测试只覆盖 `NEXT_AI_SUGGEST_PRODUCT` 是否出现在 chat_only usage prompt。
- 前端 `_parseProductSuggestMarker()` 已返回 title/type，但渲染和 click 只保留 prompt。
- 还没有 Node/vm 行为测试覆盖这个 UI protocol。

建议测试方式：

- 新建 `tests/test_productize_marker_js_behaviour.py`。
- 用 Node extract `static/ui.js` 中的三个函数：
  - `_stripProductSuggestMarker`
  - `_parseProductSuggestMarker`
  - `_onProductSuggestClick`
- mock button `getAttribute()` 和全局 `createProductFromPrompt()`。

### 9.2.3 frontend JS test helper hygiene

问题：

- 多个前端静态测试用固定字符窗口，例如 `idx:idx+800`、`send_idx:send_idx+3000`。
- 函数体增长后，真实逻辑还在，但测试会因为窗口不够而失败。
- `test_1062_busy_input_modes.py` 已经出现这种漂移。
- Node/vm 行为测试也需要固定 locale/mock 前提：
  - `test_reasoning_chip_js_behaviour.py` 当前断言英文 label/title。
  - 实际 `ui.js` 返回中文 label/title，导致 9 个行为测试失败。
  - 这类测试应 mock `t()` / locale，或断言稳定状态而不是当前展示语言。

TODO：

- 在相关测试文件内或 `tests/helpers` 抽一个 source helper：
  - `extract_js_function_body(source, name)`。
  - 用 brace matching 取完整函数体。
- 优先把 busy input / messages send / commands 这类长函数测试迁掉。
- 对纯函数或可 mock 的 runtime，优先使用 Node/vm 行为测试。
- Node/vm driver 要显式声明全局前提：
  - `window`
  - `document`
  - `t()` / locale
  - storage
  - timers
  - network/fetch

验收：

- 不再用固定 `+800/+3000/+5000` 来判断大型函数里的核心逻辑。
- 测试失败能指向真实行为变化，而不是函数长度增长。
- 行为测试不因 locale 文案切换而失败，除非测试目标就是文案本身。
- SSE `apperror` / `cancel` / connection lost：
  - 标记产品 UI failed。
  - 追加 failed status card。
  - 通知 canvas error。
- `_restoreSettledSession()`：
  - 若 inflight 中有 product context，恢复后补齐 preview refresh 和最终状态卡，或有明确测试证明此路径只负责 transcript。
- queue：
  - busy queue entry 保存 `product_id/product_scope/product_intent`。
  - merge queued messages 保留第一条 product context。
  - drain 时恢复完整 product context，不因当前选中产品变化而串线。

### 9.3 后端路由拆分回归测试

覆盖：

- product CRUD。
- product preview/asset serving。
- product versions/snapshot/rollback。
- product draft create/preview/promote/cancel。
- session new/update/toolsets。
- chat start with product context。
- chat start build/init lifecycle：
  - session 写 product_id/product_scope/product_intent/product_line。
  - 无显式 toolsets 时应用 product tools。
  - build/init 前 snapshot。
  - 非 chat_only build/init 标记 generating。
- product workspace guard。
- product prompt injection：
  - build line 注入 builder prompt。
  - use line 注入 readonly prompt。
  - product_usage 不 finalize UI。

### 9.4 浏览器冒烟

至少覆盖：

- 打开 General AI，正常聊天。
- 创建一个新 AI 产品。
- chat-only 产品不显示错误的界面生成状态。
- canvas 产品可以打开 preview。
- canvas 内 `window.NextAI.chat.send` 能回到宿主。
- Access preset 不丢 product tools。

### 9.5 当前 product 测试基线

已验证：

- `.venv311/bin/python -m pytest tests/test_product_scope_lines.py tests/test_product_ui_status.py tests/test_product_drafts.py tests/test_knead_product_skill.py`
- 当前结果：65 collected，65 passed。
- `apps/webui/tests/test_product_drafts.py` 当前是未追踪文件，已覆盖：
  - draft create 不进入正式 products registry。
  - `draft_status: "ready"` 时 publish/register。
  - `draft_status: "clarifying"` 且 `if_ready` 时不 publish。
- suggestion label 截断规则当前与测试一致：实现用 `prompt[:24]`，测试期望 `"Write about React Server"`。

### 9.6 Queue / turn journal 测试基线

已验证：

- `.venv311/bin/python -m pytest tests/test_issue660.py tests/test_1062_busy_input_modes.py tests/test_turn_journal.py tests/test_turn_journal_lifecycle.py tests/test_turn_journal_callsite.py`
- 当前结果：52 collected，49 passed，3 failed。
- 失败项都在 `tests/test_1062_busy_input_modes.py`：
  - `test_slash_commands_clear_pending_files`
  - `test_send_reads_busy_input_mode`
  - `test_send_calls_cancel_stream_on_interrupt`
- 直接原因不是对应逻辑缺失，而是静态测试用固定字符窗口截取源码：
  - `cmdQueue` 的 `renderTray()` 在源码中存在，但落在测试 `idx:idx+800` 窗口后面。
  - `messages.js` 的 `_busyInputMode` / `cancelStream` 也存在，但因为 `send()` 变长，落在测试窗口后面。
- TODO：把这些测试改成括号/函数体级提取，或改成 jsdom/行为测试，避免巨型函数稍微变长就误报。

本机测试入口现状：

- `python` 不存在。
- 系统 `python3` 无 pytest。
- `apps/webui/.venv` 无 pytest。
- `apps/webui/.venv311` 可运行当前产品测试。

TODO：

- 在 README/TESTING 或本工程 TODO 里明确本地标准测试入口。
- 后续新增 product 前端静态测试时，优先用 `.venv311/bin/python -m pytest ...` 验证。

### 9.7 旧 split module 测试漂移修复

问题：

- 额外运行 `tests/test_sprint9.py` 时，当前有 2 个失败。
- 失败点：
  - `test_panels_js_served` 期待 `panels.js` 定义 `async function loadCrons(`。
  - `test_all_functions_present_across_modules` 期待 `loadCrons/loadSkills/loadMemory` 等旧函数仍存在于旧 split modules。
- 当前源码搜索只看到 `panels.js` 调用 `loadCrons()`，但没有找到 `loadCrons/loadSkills/loadMemory` 的函数定义。
- 这说明测试和当前代码边界已经漂移；也可能暴露了面板入口调用未定义全局函数的问题。

TODO：

- 先确认 cron/skills/memory 面板的真实入口：
  - 是否被移到其他脚本。
  - 是否被后端页面或插件替代。
  - 是否是死入口。
- 若仍是产品功能：
  - 恢复或迁移 `loadCrons/loadSkills/loadMemory` 的定义。
  - `panels.js` 调用处改为新 adapter。
- 若已废弃：
  - 移除 `panels.js` 死调用。
  - 更新 `test_sprint9.py`，不要继续锁旧函数名。
- 顺手把 `test_sprint9.py` 扩展为 product script order 测试，避免旧测试只覆盖非产品脚本。

验收：

- `test_sprint9.py` 全绿。
- 面板入口没有调用未定义全局函数。
- 旧 split module 测试从“锁旧函数名”转成“锁稳定用户入口和脚本顺序”。

## 10. 第九阶段：本轮新增的产品契约 TODO

### 10.1 产品 DOM 契约显式化

问题：

- `index.html` 里产品壳靠全局 id、class、inline onclick、script order 被多个 JS 文件共享。
- 这些依赖现在没有文档/测试，属于隐式 API。
- 现有 `test_sprint9.py` 只覆盖旧 split modules：
  - `ui.js`
  - `workspace.js`
  - `sessions.js`
  - `messages.js`
  - `panels.js`
  - `boot.js`
- 它没有覆盖 product 脚本组，因此 product shell 的实际加载顺序仍未被测试锁住。

TODO：

- 新增 `docs/PRODUCT_DOM_CONTRACT.md`，列出产品壳必需 DOM id：
  - AI shelf/session list。
  - product chat header/status chips。
  - assistant home。
  - messages/task progress。
  - active product surface/iframe/preview state。
  - access dropdown。
  - create/capabilities dialogs。
- 第一批必需 id 测试：
  - `productModeTitle`
  - `productCrumbRoot`
  - `taskHeaderChatStatus`
  - `taskHeaderProductStatus`
  - `taskHeaderAdjustToggle`
  - `assistantHome`
  - `assistantTaskContextStrip`
  - `assistantTaskProgress`
  - `productChatBody`
  - `paneResizer`
  - `activeProductSurface`
  - `activeProductFrame`
  - `productPreviewState`
  - `assistantCreateOverlay`
  - `productCapabilitiesOverlay`
- 新增静态测试：
  - 必需 id 存在。
  - product 相关脚本顺序不被打乱。
  - bridge SDK 不应从 host shell script order 中误删。
  - `product-evolution.js` 在 rollback inline onclick 迁出前必须存在。
  - `panels.js` 晚于 product shell，早于 `boot.js`，确保 app chrome adapter 可用。
- 明确 product shell script order：
  - `ui.js`
  - `workspace.js`
  - `terminal.js`
  - `sessions.js`
  - `commands.js`
  - `messages.js`
  - `product-store.js`
  - `product-shell-runtime.js`
  - `product-runtime.js`
  - `product-evolution.js`
  - `panels.js`
  - `onboarding.js`
  - `boot.js`
- 把 product 相关 inline onclick 汇总成清单，后续迁到 product host controller。
  - `toggleCurrentProductAdjustMode`
  - `setCurrentProductAdjustMode`
  - `deactivateProductPreviewInChat`
  - `toggleActiveProductPreviewMenu`
  - `requestCurrentProductUiGeneration`
  - `rollbackCurrentProductUiVersion`
  - `openCurrentProductCapabilities`
  - `closeCurrentProductCapabilities`
  - `saveCurrentProductCapabilities`
  - `openActiveProductPreviewWindow`

验收：

- 删除/改名关键 DOM id 会有测试失败。
- 调整脚本顺序会有测试失败。
- 新增产品 host 行为时能知道应该挂在哪个 DOM contract 上。

### 10.2 产品 CSS 分区

问题：

- 同一产品组件的样式分散在多个区域，靠后续覆盖生效。
- `style.css` 当前既包含通用 app 样式，又包含 product dialog、product sidebar、active canvas、layout state、access dropdown。
- 已确认的覆盖层：
  - 628-682：product dialog / capabilities。
  - 979-1182：active product preview、canvas_full、adjust mode。
  - 1407-1430：access/toolsets dropdown。
  - 4102-4435：Next AI shell 基础主题和 AI object list。
  - 4662-5034：product chat header、task chips、task context/progress。
  - 5040-5334：assistant home / create screen。
  - 5590-5990：composer、product-context strip、chat_left_canvas_right 两栏。
  - 6040-6325：第二轮 sidebar / icon 色板覆盖。
  - 6391-6814：Aura sidebar pass，再次覆盖 list/header/chip/home。
  - 6970-6997：末尾 mobile override。

TODO：

- 先做状态表和 selector ownership，不急着移动文件：
  - `body[data-next-ai-view="assistant"]`
  - `body[data-next-ai-view="task"]`
  - `data-next-ai-product-layout="chat_only"`
  - `data-next-ai-product-layout="chat_left_canvas_right"`
  - `data-next-ai-product-layout="canvas_full"`
  - `data-next-ai-canvas="open|closed"`
  - `data-next-ai-product-adjust="open|closed"`
  - `data-next-ai-chat-panel="open|closed"`
- 再做第一轮无行为移动，拆出或至少分段标注：
  - `product-dialog.css`
  - `product-sidebar.css`
  - `product-shell.css`
  - `product-active-preview.css`
  - `product-layout.css`
  - `product-access.css`
- 建立 selector duplicate audit，重点看：
  - `.product-chat-header`
  - `.product-task-chip`
  - `.ai-object-item`
  - `.assistant-home`
  - `.active-product-surface`
- 把 body data 状态整理成 layout state table。
- 给 CSS 分区加快照/静态测试：
  - product shell 关键 selector 不能消失。
  - product layout 关键 `body[data-next-ai-*]` 组合不能消失。
  - 后续 override section 必须有注释标题，避免无意新增第三/第四层覆盖。

验收：

- 修改 product chat header 不需要跨 4 个区域查覆盖。
- `chat_left_canvas_right`、`canvas_full` 的状态组合有明确表格。
- 移动 CSS 后视觉冒烟通过。
- selector duplicate audit 从“意外重复”变成“声明过的 override”。

### 10.3 `knead-product` 契约和真实产品一致

问题：

- skill 文档契约比较清楚，但真实产品还没有完全被测试锁住。
- `ai-otome` 可能阻塞 first paint 等待 `NextAI.state.get`。
- `ppt-designer` 默认启动无条件应用 `HEYTEA_DECK`，会覆盖真实用户 state。
- `ai-otome` 生图逻辑期待 `res.image_url` / `res.content_url`，但 SDK 当前返回 `{ content, raw }`，宿主 reply 也没有明确图片字段。
- `ai-otome` 普通聊天只依赖 `res.content`，这条路径和当前 SDK 兼容；不兼容主要集中在 image/file typed response。
- `ppt-designer` 的 AI->GUI 主通道方向正确：优先 `state.json`，fallback 解析 agent message；问题是最后被 demo deck 覆盖。
- `products/general/about.html` 是未追踪、未被 `preview_entry` 引用的独立页面；需要决定它是临时文件、文档页，还是误放入 chat_only 产品目录。
- `doc-site-generators.md` 是截至 2025 的研究 memo，不能当作 2026 当前版本事实直接使用。

TODO：

- 给 shipped products 加静态/冒烟测试：
  - `product-bridge-sdk.js` 在 `app.js` 前加载。
  - 产品 app 不直接 `fetch('/api/chat')` 或直接调模型 API。
  - `canvas_full` 产品首屏先 paint，再异步恢复 state。
  - `chat_left_canvas_right` 产品优先读取 `state.json`，但不覆盖用户保存状态。
  - `chat_only` 产品的 `preview_entry` 不引用多余 canvas surface。
  - product app 不依赖未定义的 bridge response 字段。
  - `ai-otome` 不再读取裸 `res.image_url` / `res.content_url`，只读 documented `assets/files/data/raw`。
  - `ppt-designer` 正常启动路径不能无条件 `applyDeckState(HEYTEA_DECK)`。
- 修 `ai-otome` state restore：默认先 render，再用短 timeout 恢复 bridge state。
- 修 `ai-otome` portrait generation response：
  - 先由 host/SDK 明确 image/file response shape。
  - 产品 app 只依赖 documented 字段。
- 清理 `ppt-designer` 的 `HEYTEA_DECK` 默认覆盖：
  - demo 数据只能在显式 `?demo=` 或专用 seed action 下生效。
  - 默认启动顺序应是 defaults -> saved session -> `state.json`，不能再强制覆盖。
  - `state.json` 应该赢过 session state，因为它是 agent 本轮写出的 GUI 事实；demo 永远不能赢过二者。
- 处理 `products/general/about.html`：
  - 如果不是产品 surface，移出产品 workspace 或标注为 docs/示例。
  - 如果要作为页面，调整 `product_layout` / `preview_entry` / 文案，避免和 chat_only 语义冲突。
- 给 `doc-site-generators.md` 加 freshness 标注：
  - 只作为历史调研。
  - 真正用于选型前必须刷新官方版本/文档。

验收：

- skill 说的 hard rules 能被测试验证。
- 两个 shipped products 可以作为新产品模板参考，而不是例外。
- 产品 app 首屏在 bridge 慢/失败时仍能显示默认界面。
- AI Otome 生图返回字段、PPT Designer 下载字段都有契约测试。
- `NextAI.chat.send` 的 typed response contract 被产品 app 静态检查覆盖，避免新增产品继续猜字段。

### 10.4 product draft 生命周期

问题：

- 已有 `create_product_draft()` 草稿测试，说明产品创建已分成 draft 和 registered product。
- 这条生命周期还没有在工程 TODO 中被单独管理。
- 当前后端已有 `publish_product_draft()` 和 `/api/product-drafts/publish`。
- 前端已有 `publishCreatorDraftIfReady()`，会在 Creator turn done 后尝试发布。
- 当前 publish readiness gate 只认 `draft_status`：
  - ready：`ready` / `publish` / `published` / `final`。
  - not ready：`clarifying` / `draft` / `working` / `needs_input` / `not_ready`。
  - 没有 ready status 时，即使 manifest title/layout 已改、`index.html` 已存在，也会返回 `not_ready`。
- 但 draft create 阶段仍固定 `product_type=custom`、`ui_mode=chat_only`、`product_layout=chat_only`，没有承接 productize marker 的 `type`。
- productize marker 当前包含 `title/prompt/type`，但前端点击创建时主要传 `prompt`，draft create 没有保存 marker type/title 作为 initial metadata。
- 还缺 cancel/delete/cleanup，也没有 draft preview/asset 服务。

TODO：

- 梳理并拆分 draft API：
  - create draft。
  - preview draft。
  - publish/register draft。
  - cancel/delete draft。
  - cleanup stale draft。
- 路径隔离：
  - draft workspace 不能进入正式产品列表。
  - draft preview 不能越权访问正式 products。
  - promote 时校验 manifest 和 workspace 文件。
- 失败恢复：
  - 生成失败保留 draft 供用户继续调整。
  - 用户取消时清理临时 workspace。
- readiness contract：
  - Creator 完成可发布版本时必须写 `draft_status: "ready"`。
  - 需要把这一条写入 Creator internal context / knead-product skill / product draft schema。
  - publish API 可以保留 `force`，但 `if_ready` 必须只依赖明确 ready signal。
  - 测试要覆盖未 ready 不发布、ready 才 publish、force 绕过 ready gate。
- productize metadata：
  - marker parser 产出的 `title/type/prompt` 要完整传入 draft create。
  - 当前 `_parseProductSuggestMarker()` 已返回 `title/prompt/type`，但渲染按钮只保留 `data-product-prompt`，click handler 只传 prompt。
  - `createProductFromPrompt()` 需要支持 object payload；string prompt 继续兼容。
  - draft manifest 可保存 `creation_hint` 或 `initial_metadata`，但最终 product schema 仍以 Creator 修改后的 `product.json` 为准。
  - `type` 映射到 `product_type` / 初始 skills/tools/layout hint 时要有白名单，不能让任意字符串进入 manifest。
  - Creator internal instruction 改走 `internal_context`，包含 draft_id、workspace_path、manifest_path、original_user_request、initial_metadata。
- Creator instruction 去歧义：
  - 当前已经要求 `draft_status="ready"` 后 host 发布，这是正确方向。
  - 但同时说 “still a draft until the user chooses to publish it”，和 done 后 `publishCreatorDraftIfReady()` 自动 publish ready draft 有语义冲突。
  - 如果保留自动 publish，就把文案改成“until the host publishes a ready draft”。
  - 如果改成用户显式确认 publish，就要移除 done 后自动 publish，改展示确认 UI。
- 前端 publish 流程测试：
  - stream done 后只在 draft workspace 调 `/api/product-drafts/publish`。
  - ready draft 会注册并 open。
  - clarifying draft 不发布、不误报创建成功。
  - `.knead-published.json` 已存在时打开 existing product。

验收：

- `list_products()` 永远不返回 draft。
- draft promote 后才进入正式 products registry。
- draft 预览、asset serving、路径逃逸都有测试。
- promote 前会校验 `product.json`，拒绝空 title、路径逃逸 preview entry、非法 layout/toolset。
- cancel/cleanup 不会删除正式 `products/` 下的产品 workspace。
- productize marker 的 `type` 能影响 draft manifest defaults，并在 publish 后保留。
- Creator turn 未写 ready status 时，`if_ready` publish 不应发布。
- Creator instruction 文案和实际自动 publish 行为一致。
- marker button 不丢 `title/type`。
- Creator turn 写 `draft_status: "ready"` 后，`if_ready` publish 应发布。
- draft publish suggestion normalization 的 label 截断规则要统一：
  - 当前实现 `_normalize_draft_suggestions()` 用 `prompt[:24]`。
  - 当前未追踪测试 `test_product_drafts.py` 已按 `"Write about React Server"` 覆盖这个行为。
  - 仍需要把 label 最大长度写进 schema/contract，避免后续实现和测试再次漂移。

### 10.5 `api/products.py` 服务拆分

问题：

- `api/products.py` 目前同时负责 builtins、registry、workspace 注册、seed/manifest、draft、status、snapshot/rollback、preview asset。
- 其中 `ui_status` 逻辑比较成熟，但被放在同一个大模块里，后续继续加产品能力会越来越难读。
- `product_file_status()` 会触发 builtins ensure，而 `preview_product_file()` 直接 `_read_state()`，初始化路径不完全一致。
- snapshot/rollback 的实现有安全意识，但目前缺少针对 include/exclude、manifest patch、rollback 删除 managed file 的测试。
- `update_product()` 同时修改 registry、补 seed files、写 manifest；副作用边界不够显式。
- `finalize_product_generation()` 的 narrow manifest patch 是正确方向，但需要测试确保不会从 workspace manifest 回写任意字段。

TODO：

- 先补测试，再拆模块：
  - status 矩阵已有，保留。
  - 新增 preview asset 测试：默认 index、嵌套 asset、路径逃逸、内置产品直连 preview、缺文件。
  - 新增 preview response 测试：HTML 有 CSP sandbox，SVG/dangerous MIME 不裸 inline，`Cache-Control: no-store` 保留。
  - 新增 snapshot/rollback 测试：跳过 seed、复制小文件、排除 versions/node_modules/隐藏文件、大文件、rollback 删除 snapshot 不含的 managed file。
  - 新增 manifest patch 测试：只允许窄字段从 workspace `product.json` 回写。
  - 新增 finalize 测试：builder turn 写 `product.json` 后，status/layout/skills/tools 按白名单回写。
  - 新增 direct preview 测试：未先访问 `/api/products` 时，built-in product preview 仍能找到 workspace。
- 拆分目标：
  - `product_registry.py`：state 读写、builtins ensure、create/update/delete、workspace register。
  - `product_manifest.py`：seed files、manifest write/read、workspace manifest patch。
  - `product_status.py`：`_resolve_ui_status`、entry generated、finalize、reconcile。
  - `product_versions.py`：snapshot、rollback、version dirs。
  - `product_drafts.py`：draft create/promote/cancel/cleanup。
  - `product_assets.py`：file status、preview path resolve、asset serving helpers。
- 修一致性：
  - `preview_product_file()` 也应走 `get_product()` 或显式 ensure builtins。
  - product preview route 的 path match 要从“包含 `/preview`”改成严格 segment match。
  - product HTML/SVG response policy 不要落后于 `/api/file/raw` 的 dangerous MIME 规则。
  - preview/asset 可选择在进入前 reconcile，或明确只由 status endpoint 管理状态。
  - `update_product()` 的 “更新 registry + 补 seed files + 写 manifest” 副作用要拆成可测试步骤。
  - snapshot 失败时前端 rollback UI 不应展示可恢复状态。
- 保留现有好边界：
  - `product_file_status()` 仍是 pure read。
  - `reconcile_product_status()` 仍是显式 writer。
  - `finalize_product_generation()` 仍是生成结束 writer。

验收：

- `api/products.py` 变成兼容 facade 或被拆到多个小模块。
- 每个小模块有单独测试。
- 直接打开 `/api/products/<builtin>/preview` 不依赖先访问 `/api/products`。
- 直接打开 `/api/products/<id>/preview` 不会在 WebUI 同源下裸执行产品 HTML。
- product SVG 默认不会作为可执行同源内容 inline。
- rollback 不会误删 runtime/version/generated 大文件。
- builder turn 前 snapshot 成功/失败的 UI 语义明确。

### 10.6 `product_context.py` 状态一致性

问题：

- `product_context_from_request()` 使用 registry 中的 stored `ui_status` 判断是否自动切到 `product_init`。
- 如果 stored status 与磁盘事实不一致，比如 stored `ready` 但入口文件已丢，或 stored `generating` 已超时，scope 判断可能不准。
- 当前调用点在 new session / chat start / sync chat / steer 前，没有统一看到进入 product context 前 reconcile。
- `product_ephemeral_prompt()` 同时承担 identity、build/use 指令、PPT 特例、productize marker，已经接近 prompt monolith。
- steer 的 product prompt 是直接拼进 steer text，和普通 start 的 ephemeral prompt 注入路径不一致。

TODO：

- 进入 product context 前统一做产品状态 reconcile，或让 `product_context_from_request()` 使用 derived file status。
- 增加测试：
  - stored `ready` 但 entry missing 时，非显式 usage 的 canvas 产品应进入 init/build 修复线。
  - stored `generating` 超时后应不继续误认为正在生成。
  - 显式 usage 仍然保持 usage，不被自动 init 覆盖。
  - build/use workspace guard 行为不变。
- 拆 prompt builder：
  - `build_product_identity_prompt(context)`。
  - `build_product_scope_guidance(context)`。
  - `build_product_builder_prompt(context)`。
  - `build_product_use_prompt(context)`。
  - `build_productize_marker_prompt(context)`。
  - `build_ppt_designer_canvas_prompt(context)`。
- 把 PPT Designer canvas contract 和产品 app / skill 文档对齐，避免三处文字漂移。
- 明确 steer product context 的注入方式：
  - 要么通过 agent 原生 steer metadata/ephemeral update。
  - 要么保留文本拼接但标注为兼容路径并测试。
- 收敛 capability/tool label：
  - `CAPABILITY_LABELS`
  - 前端 access label。
  - `PRODUCT_TOOLSET_ALIASES`

验收：

- scope 判断不依赖 stale stored status。
- product context 相关测试能覆盖 status drift。
- 工具/能力 label 不再三处分叉。
- prompt builder 可以单独测试，不需要 snapshot 整个超长 prompt。

### 10.7 前端产品模型事实源收敛

问题：

- `product-store.js` 复制了后端 `PRODUCT_TOOLSET_ALIASES`、默认 capability、layout normalize。
- `.agents/skills/knead-product`、`products/*/product.json`、前端 adapter、后端 normalize 之间没有同一个 schema 文档。
- 新增一个 tool/layout 时，需要同时猜多个位置。

TODO：

- 建立 `docs/PRODUCT_SCHEMA.md`：
  - product manifest 字段。
  - snake_case 后端字段和 camelCase 前端字段映射。
  - `ui_mode` / `product_layout` 枚举。
  - toolset/capability 枚举和 alias。
  - `ui_status` 状态机。
  - canvas availability 规则：
    - `chat_left_canvas_right` / `canvas_full` 默认可显示 canvas。
    - `chat_only` 默认不显示 canvas。
    - `chat_only` 如果已有 generated canvas，可提升到 `chat_left_canvas_right`。
    - `general` 永不就地长 canvas，只能通过 productize 创建独立产品。
- 抽前端纯逻辑：
  - `product-model.js`：layout/tool/status normalize。
  - `product-adapter.js`：backend product -> frontend object。
  - `product-capabilities.js`：能力 label、默认 toolset。
- 后端保留 Python 版本，但用测试对齐 schema fixtures。

验收：

- 前后端对同一组 product fixture 得出同样 layout/toolsets/canvas 可用性。
- 新增 layout/tool 只需要更新 schema + 一处模型逻辑。
- `product-store.js` 不再包含大段硬编码规则。

### 10.8 产品壳启动和 layout 状态机

问题：

- `initNextAiAssistants()` 先 render 静态 shelf，再异步 hydrate backend products。
- product-bound session 如果 hydrate 还没回来，会先落到 general，再异步切回 product。
- `syncAssistantTaskUi()` 通过多个 `body.dataset` 字段表达页面状态，但没有状态表。
- loaded session 选择产品优先 `product_id`，task list filtering 仍主要依赖 assignment / legacy heuristic。
- `boot.js` 的 async IIFE 和 `product-shell-runtime.js` 的 DOMContentLoaded self-start 并行运行，当前顺序要靠脚本加载和多个补救分支推断。

TODO：

- 建立启动时序文档和测试：
  - defer script order。
  - defaults registered。
  - backend products hydrated。
  - saved/current session restored。
  - product-bound session selects product kind。
  - first preview refresh。
  - BFCache restore。
- 明确 `body.dataset` 状态表：
  - `nextAiView`
  - `nextAiProductLayout`
  - `nextAiCanvas`
  - `nextAiProductAdjust`
  - `nextAiChatPanel`
  - `nextAiDirectory`
- 给 `syncAssistantTaskUi()` 抽出纯 reducer：
  - 输入：assistant object、hasTask、usesProductCanvas、active preview、manual chat panel、adjust state。
  - 输出：body dataset、home/messages/surface visibility、header chip state。
- 给 session ownership 抽出单一优先级：
  - `session.product_id`。
  - `session.next_ai_assistant_kind` / localStorage assignment。
  - legacy title/message heuristic。
  - general fallback。
- 让 task list filtering 和 loaded session selection 使用同一套 ownership 函数。
- 需要覆盖的状态组合：
  - AI shelf：`nextAiView=assistant`，home 显示，messages/surface 隐藏。
  - chat_only task：`nextAiView=task`，`nextAiProductLayout=chat_only`，`nextAiCanvas=closed`。
  - chat_left_canvas_right task 无 preview：canvas closed。
  - chat_left_canvas_right task 有 preview：canvas open，chat panel 默认 open。
  - chat_left_canvas_right 手动关 chat panel：manual closed 后保持 closed。
  - canvas_full use mode：canvas open 时隐藏 messages/composer。
  - canvas_full adjust：adjust open 时左侧聊天/composer 重新出现。
  - 切换 AI：清 `nextAiProductAdjust`、`nextAiChatPanel`、`nextAiChatPanelManual`。
- 把 product selection / session restore / preview refresh 拆成可等待阶段，至少暴露一个 `products:hydrated` 事件或 promise。

验收：

- 加载 product-bound session 不会短暂显示错误产品。
- product-bound session 在左侧 task list 和打开后的产品选择一致。
- layout state 组合有测试快照。
- 新产品 hydrate 失败时，UI 有明确 fallback，不会静默停在错误状态。
- product hydrate 慢、session restore 快的场景有测试或浏览器冒烟记录。

### 10.9 chat turn contract / internal context

问题：

- 当前 `message` 字段同时承担：
  - 用户可见文本。
  - Creator draft 内部指令。
  - product canvas bridge 内部指令。
  - pending/recovery 锚点。
  - turn journal 内容。
  - agent `persist_user_message`。
  - session provisional title 来源。
- 前端 optimistic transcript 使用可见 `text`，后端真实 pending 使用拼接后的 `msgText`，导致 UI 和 server transcript 语义可能分叉。
- `product_context.py` 已有结构化方向和 ephemeral prompt 注入口，但 hidden instruction 分支没有复用这条路。

TODO：

- 定义 chat turn request contract：
  - `message`: 用户可见原文。
  - `attachments`: 用户附件。
  - `product_context`: product_id/scope/intent/task_title。
  - `internal_context`: 非用户可见内部上下文，支持多个来源。
- internal context 建议结构：
  - `{kind:"creator_draft", draft_id, workspace_path, manifest_path, original_user_request, initial_metadata}`。
  - `{kind:"product_canvas_bridge", request_id, mode, character, history, product_id, product_scope}`。
- 后端处理：
  - `message` 只进入 pending/messages/journal/title/recovery。
  - `internal_context` 只进入 `_webui_ephemeral_system_prompt()`。
  - 失败、cancel、recover、self-heal、retry 不能把 internal context materialize 为 user turn。
- 前端处理：
  - `_nextAiPendingHiddenAgentInstruction` 改为 `_nextAiPendingInternalContext`。
  - queue item 保存 `text + internal_context + product_context`，不保存拼接后文本。
  - conflict queue / busy queue / drain queue 统一走同一个 serializer。
- Queue/drain 复核补充：
  - `queueSessionMessage()` 当前可以保存任意 payload 字段，但 `setBusy(false)` drain 只恢复 text/files/model/product_scope/product_intent。
  - drain 没有显式恢复 `product_id`，下一次 `send()` 仍依赖当前 assistant/session 推导。
  - `/api/chat/start` 409 conflict path 当前 queue 的是 `msgText`，而不是 visible `text`；如果 `msgText` 已拼 hidden instruction，会把 hidden instruction 存进 queued text。
  - refresh restore (`sessions.js`) 只把第一条 queued `text` 放回 composer，然后删除 sessionStorage，files/model/product/internal context 都会丢。
- 迁移策略：
  - 后端短期兼容旧 `hidden_instructions` 字符串数组。
  - 前端先改 Creator 和 canvas bridge 两个来源。
  - 保留 sentinel stripping 作为兼容显示保护，但新路径不再依赖它。

验收：

- hidden instruction 不出现在 `pending_user_message`、`messages[].content`、turn journal submitted content、session title。
- agent prompt 仍能收到 Creator / canvas bridge 的内部约束。
- queue 后重发和直接发送表现一致。
- `/api/chat/start` 的测试能模拟 eager save、deferred save、cancel、recovery、self-heal retry。
- product context 的 `product_intent` 始终来自用户原文或显式 field，而不是内部指令。
- 409 conflict 后 queued item 的 `text` 仍是用户原文，不包含 internal context。
- 刷新恢复后，queued product/internal context 不丢，或者明确让用户取消/重发而不是静默转成普通消息。

### 10.10 queued turn request contract

问题：

- `SESSION_QUEUES` 是 session-scoped，方向正确。
- `queueSessionMessage()` 能保存任意 payload 字段，并写入 sessionStorage，方向也正确。
- 但 drain/restore 不是按完整 request 发送，而是把部分字段还原到 composer/global state 后再调用 `send()`。
- `setBusy(false)` drain 只恢复：
  - `sendText || text`
  - `product_scope`
  - `product_intent`
  - files
  - model/provider
- `product_id` 没有作为 drain 的显式 source of truth。
- refresh restore 只把第一条 `text` 放进 composer，然后删除 queue storage。
- queue merge 会合并 text，但只保留第一条 product metadata；不同 product/internal context 的 queue 被 merge 会语义丢失。
- 409 conflict path 当前把 `msgText` 入队，可能包含 hidden instruction。
- queue chip inline edit 只改 `text`；隐藏 metadata 会留在 entry 里，但 UI 不提示用户哪些 context 会被保留或丢弃。
- `setBusy(false)` 名义上是 UI 状态切换，实际还会自动 drain 并调用 `send()`，职责边界不清。
- refresh restore 会删除整个 `hermes-queue-<sid>` storage；如果有多条 queued request，只展示第一条 text，其余 request 和上下文都会丢失。

TODO：

- 抽出 queued turn request model：
  - `message`
  - `attachments`
  - `model`
  - `model_provider`
  - `profile`
  - `product_context`
  - `internal_context`
  - `_queued_at`
- `queueSessionMessage()` 只接受规范化后的 queued turn，或内部调用 `normalizeQueuedTurn(payload)`。
- drain 时不要把 request 分散到 composer/global pending 字段；应直接用 queued turn 构造 `/api/chat/start` payload。
- `setBusy(false)` 改成只发 idle signal 或调用 `onTurnBecameIdle(sessionId)`；queue controller 决定是否 drain。
- 如果仍需要 composer UX，composer 只展示 `message`，并持有隐藏的 `_pendingQueuedTurn`。
- refresh restore：
  - 重新 hydrate 到 `SESSION_QUEUES` 并展示 queue chips；或
  - 恢复第一条到 composer 时同时保存完整 hidden queued turn。
- queue merge：
  - 只有同 product_id、同 model/provider、无 internal_context 或 internal_context 兼容时才允许 merge。
  - 否则禁用 merge 或提示会丢上下文。
- 修 409 conflict path：
  - queue visible message。
  - structured internal context / product context 单独保存。

验收：

- busy queue、interrupt queue、steer fallback、goal continuation、409 conflict、refresh restore 都通过同一个 serializer。
- queued product turn 不因用户切换当前 AI 而发到错误 product。
- refresh 后重发 queued product turn 仍保留 product_id/scope/intent/internal_context。
- queue chip 编辑只改 `message`，不丢隐藏 request metadata。
- queue chip UI 能标出 product/model/files/internal context 是否存在，至少不会无提示丢失。
- merge 不会悄悄合并不同 product/internal context。

### 10.11 turn journal visible content contract

问题：

- `turn_journal.py` 本身设计清楚：append-only JSONL、fsync、malformed tolerant、stream_id 复用 turn_id。
- `/api/chat/start` submitted event 现在写的是 `content: msg`。
- `msg` 当前来自 `body.message`，也就是前端可能拼过 hidden instruction 的文本。
- `session_recovery.audit_session_recovery()` 使用 submitted `content` 判断是否存在未 materialize 的 user turn。
- 因此 submitted content 必须是 visible user message，不能含 internal context。

TODO：

- chat-start contract 落地后：
  - turn journal `submitted.content` 只写 visible message。
  - `submitted.product` 可以继续记录 product id/scope/title。
  - 如果需要 debug internal context，只记录 redacted metadata，例如 `internal_context_kinds`，不要记录全文。
- 增加测试：
  - submitted journal content 不包含 internal context。
  - recovery audit 对 visible message 做 materialization 判断。
  - internal context 不触发 `turn_journal_pending_turn`。
- `test_turn_journal_callsite.py` 从纯字符串顺序测试升级为至少一个行为测试，mock `append_turn_journal_event` 捕获 payload。

验收：

- journal 仍能用于 crash recovery / audit。
- internal context 不会进入 journal user content。
- turn lifecycle events 仍复用 submitted turn_id。

### 10.12 chat-start backend request model

问题：

- `/api/chat/start` 现在没有显式 request model。
- `_handle_chat_start()` 直接把 `body.message` 变成 `msg`。
- `msg` 接着流入：
  - `product_context_request_body(body, s, msg)`。
  - `_prepare_chat_start_session_for_stream(... msg=msg ...)`。
  - `_provisional_title_from_prompt(msg, ...)`。
  - eager save 的 `_checkpoint_user_message_for_eager_session_save(... msg ...)`。
  - turn journal submitted `content: msg`。
  - `_run_agent_streaming(session_id, msg, ...)`。
  - `persist_user_message=msg_text`。
- `product_context_request_body()` 在缺少 `product_intent` 时会用 `message` 作为 intent fallback。
- `_webui_ephemeral_system_prompt()` 已经是 runtime-only prompt 注入口，但目前只接 personality/product prompt，没有 internal context 参数。

TODO：

- 新增 chat-start normalization 层：
  - `normalize_chat_start_payload(body, session)`。
  - 输出 `visible_message`、`attachments`、`workspace_request`、`product_body`、`internal_context`。
  - 兼容旧 `hidden_instructions` / `internal_context` 两种输入。
- `_handle_chat_start()`：
  - 只用 `visible_message` 做非空校验。
  - 用 `visible_message` 调 `product_context_request_body()`。
  - 传 `internal_context` 给 `_start_chat_stream_for_session()`。
- `_start_chat_stream_for_session()`：
  - 新增 `internal_context=None` 参数。
  - pending/title/journal/thread visible args 继续用 `visible_message`。
  - journal 只记录 redacted internal metadata，例如 `internal_context_kinds`，不记录全文。
- `_run_agent_streaming()`：
  - 新增 `internal_context=None` 参数。
  - `persist_user_message` 和 `_context_messages_for_new_turn()` 只看 visible message。
  - 将 internal context 转成 runtime prompt，加入 `_webui_ephemeral_system_prompt()`。
- `_webui_ephemeral_system_prompt()`：
  - 短期可加 `internal_prompt` 参数。
  - 中期改成 `build_webui_runtime_prompt(parts)`，避免参数继续膨胀。
- runtime adapter 路径：
  - `StartRunRequest` 需要能携带 internal context metadata，或 adapter delegate 显式闭包传入。

测试：

- route 行为测试：
  - `message="hello"` + `internal_context` 后，session pending/eager user message/journal/persisted user message 都只含 `"hello"`。
  - agent `ephemeral_system_prompt` 包含 internal context prompt。
- product context 测试：
  - explicit `product_intent` 优先。
  - 缺 intent 时 fallback 只用 visible message。
- error/cancel/recovery 测试：
  - `_materialize_pending_user_turn_before_error()` 不会把 internal context 写成 user message。
  - cancel recovery 只恢复 visible user message。
- callsite 测试升级：
  - `test_turn_journal_callsite.py` 保留顺序断言，但新增 mock payload 行为断言。

验收：

- hidden instruction 不再进入 `pending_user_message`、`messages[].content`、session title、turn journal submitted content、recovery user bubble。
- product intent fallback 不会读到 hidden/internal instruction。
- agent 仍能收到 Creator / canvas bridge 所需内部上下文。

### 10.13 product preview asset serving contract

问题：

- `products.py` 的路径逃逸保护方向正确：`resolve()` 后要求 `target.relative_to(root)`。
- 但 product preview 响应层目前太薄，`_serve_file_response()` 只负责 MIME、no-store 和 bytes。
- iframe 里有 `sandbox="allow-scripts allow-forms"`，但直接打开 `/api/products/<id>/preview` 时没有 CSP sandbox。
- `/api/file/raw` 已经对 HTML inline、SVG、dangerous MIME 有更清楚的响应策略，product preview 没有对齐。
- `preview_product_file()` 直接 `_read_state()`，不走 builtin ensure；direct builtin preview 的初始化一致性不够强。
- bridge download allowlist 和后端 preview resolver 还不是同一个 contract。

TODO：

- 定义 product asset resolver：
  - product id/kind 解析。
  - builtin ensure。
  - workspace root。
  - normalized rel path。
  - target path。
  - MIME/disposition policy。
- 合并 route handler：
  - `/api/products/<id>/preview`
  - `/api/products/<id>/preview/<asset>`
  - `/api/products/<id>/<asset>` 兼容路径。
- route match 改为 segment-level，不要靠 `"/preview" in parsed.path`。
- HTML preview 默认带 CSP sandbox：
  - 初始可和 iframe sandbox 对齐：`sandbox allow-scripts allow-forms`。
  - 不给 `allow-same-origin`。
- SVG 和危险 MIME 默认 attachment，或进入明确 allowlist。
- bridge `nextai:product:download` 的 URL allowlist 使用同一套 product asset contract：
  - 只允许当前 product。
  - 允许 nested `assets/`、`outputs/`、相对 workspace 文件。
  - 拒绝跨 product、外部 URL、`javascript:`、`data:`。
- 测试覆盖：
  - clean state direct builtin preview。
  - default index。
  - nested asset。
  - path traversal。
  - strict preview segment matching。
  - HTML CSP sandbox。
  - SVG dangerous MIME。
  - bridge download allowed/denied cases。

验收：

- product preview 在 iframe 和 top-level 直接打开时都有一致的隔离边界。
- preview asset resolver 是单一事实源。
- bridge download 不再是 parent 任意 fetch/open。
- route tests 能保护未来拆 `routes_products.py` / `product_assets.py` 时不退化。

### 10.14 product registry / lifecycle service split

问题：

- `api/products.py` 目前 1400+ 行，但真正的问题不是行数本身，而是事实源太多：
  - `ai_products.json`
  - `products/<id>/product.json`
  - workspace registry
  - draft workspace
  - versions snapshots
  - product session binding
  - preview asset serving
  - ui_status lifecycle
- `_resolve_ui_status()` 这种局部设计是清楚的，但它和 registry I/O、manifest I/O、preview resolver、draft publish 混在同一个文件。
- `_write_state()` 直接写 `ai_products.json`，没有 atomic replace；如果进程中断，custom products 有被空 state 覆盖的恢复风险。
- `create_product()` 对 body 自带 `tools` 使用 `_unique_strings()`，不是 `normalize_product_toolsets()`；create response / state-on-disk / later read response 可能短暂不一致。
- `update_product()` 同时接受 public metadata 和 lifecycle 字段：
  - `versions`
  - `sessions`
  - `ui_status`
  - `last_session_id`
  - `ui_error_type/ui_error_message`
  这些字段应该由内部 lifecycle service 管。
- builtin product ensure 会用 definition 覆盖 existing 多数字段；如果 builtin 是否可被 agent 持久修改没有明确产品规则，后续会出现“明明改了又被还原”的疑惑。
- draft readiness 目前只认 `draft_status`，`original_title` 参数没有参与判断；这是安全的，但对 Creator 精准写状态依赖强。

TODO：

- 抽 `product_registry.py`：
  - `read_products_state()`
  - `write_products_state_atomic()`
  - product normalization / migrations。
  - state corrupt 时保留 bad file，并返回可诊断错误，不静默覆盖 custom products。
- 抽 `product_manifest.py`：
  - read/write manifest。
  - manifest schema allowlist。
  - agent-owned patch extraction。
  - snake/camel alias normalization。
- 抽 `product_lifecycle.py`：
  - create/update/delete。
  - record session。
  - finalize generation。
  - reconcile status。
  - 区分 public update 和 internal lifecycle patch。
- 抽 `product_drafts.py`：
  - create draft。
  - readiness check。
  - publish draft。
  - `.knead-published.json` idempotency。
- 抽 `product_versions.py`：
  - snapshot/list/rollback。
  - managed file set。
  - snapshot retention。
- 抽 `product_assets.py`：
  - product lookup + builtin ensure。
  - path normalization。
  - MIME/disposition/CSP policy。
  - bridge download allowlist 复用。
- 抽 `routes_products.py`：
  - GET/POST route table。
  - segment-level parser。
  - 不再让 `routes.py` 持有产品分支细节。

短期修复：

- `_write_state()` 改成 tmp 写入 + atomic replace。
- `create_product()` 对 body tools 使用 `normalize_product_toolsets()`，并保证返回值、磁盘、后续 list 一致。
- 为 builtin mutability 写明规则：
  - 内置定义强覆盖，agent 不应改 title/tools；或
  - builtin 允许 user override，ensure 只补缺省字段。
- `update_product()` 分出 internal-only fields，公开 endpoint 不应随便 patch `versions/sessions/ui_status`。
- `publish_product_draft()` readiness 增加可诊断返回：
  - 当前 draft status。
  - 缺哪些字段。
  - 是否缺 workspace entry。
- 为 `product.json` 建 schema 文档，至少包含：
  - identity fields。
  - runtime prompt fields。
  - UI/layout fields。
  - lifecycle fields。
  - agent 可写/不可写字段。

测试：

- registry：
  - atomic write 成功替换。
  - corrupt `ai_products.json` 不会静默丢 custom products。
  - create with alias tools 后 response/state/list 都一致。
- builtin：
  - clean state direct preview 前会 ensure builtin。
  - builtin field overwrite 规则明确并有测试。
- update：
  - public update 不能直接改 `versions/sessions/ui_status`。
  - internal lifecycle update 能改，并由专门 API/函数路径调用。
- draft：
  - not_ready 返回原因。
  - `.knead-published.json` repeated publish idempotent。
  - publish 后 draft-only fields 不进入 product manifest。
- versions：
  - snapshot skips seed。
  - snapshot copies nested assets。
  - snapshot skips hidden/large/excluded dirs。
  - rollback restores files and deletes generated managed files not in target snapshot。
  - retention cap 25。

验收：

- `products.py` 缩成薄 facade 或被拆空。
- registry/manifest/lifecycle/assets 的测试可以独立运行。
- 新增产品字段时，有明确落点，不需要同时改 routes、manifest、frontend store 和 product context 多处猜测。
- 产品状态损坏时，有诊断和恢复路径，而不是静默变成只剩 builtin products。

### 10.15 `ui.js` app shell split

问题：

- `apps/webui/static/ui.js` 目前 7961 行，顶层函数/导出/事件绑定约 400+ 个。
- 它不是单一 UI 文件，而是同时承担：
  - global app state。
  - offline/reconnect recovery。
  - model picker。
  - reasoning picker。
  - toolsets/access preset picker。
  - composer primary action。
  - busy state。
  - queued message controller。
  - message renderer。
  - markdown/media/katex/mermaid/pdf/html renderer。
  - compression/handoff cards。
  - tool cards。
  - system health/update banner。
  - workspace file tree。
  - attachment tray/upload。
- `S` 是所有模块共享的 mutable state；`S.session`、`S.messages`、`S.entries`、`S.busy`、`S.pendingFiles`、workspace tree cache、profile/model 状态混在一起。
- `setBusy(false)` 实际是 turn idle lifecycle：
  - 清 UI 状态。
  - drain queue。
  - 恢复 composer/files/model/product global pending fields。
  - 自动调用 `send()`。
  这个命名会误导未来维护者。
- `renderMessages()` 既做数据准备，又直接造 DOM，还执行 side effects：
  - windowing/cache。
  - compression/handoff。
  - thinking extraction。
  - product marker。
  - attachments。
  - tool card derivation。
  - usage/duration/gateway label。
  - post-process。
- HTML string 里仍有大量 inline `onclick`，不利于 CSP、模块拆分和测试。
- 当前测试对 `ui.js/messages.js` 有较多源码窗口断言；随着函数变长会继续变脆。

TODO：

- 先抽 state facade：
  - `app-state.js`
  - `getCurrentSessionId()`
  - `getVisibleMessages()`
  - `setBusyState(v)`
  - 明确哪些字段可以直接 mutate，哪些必须走 action。
- 拆 busy/turn idle：
  - `setBusyState(v)` 只更新 busy/composer UI。
  - `onTurnBecameIdle(sessionId)` 处理 activity clear、queue drain、status cleanup。
  - streaming done/error/restore path 显式调用 `onTurnBecameIdle(activeSid)`。
- 抽 queue controller：
  - `queue-storage.js`：memory + sessionStorage。
  - `queued-turn-request.js`：规范字段。
  - `queue-drain.js`：直接发 structured request，不写回 composer 再 `send()`。
  - `queue-view.js`：chip/flyout UI。
- 抽 composer controller：
  - primary action。
  - busy command。
  - pending files。
  - tray render。
  - upload flow。
- 抽 message model：
  - `buildRenderableMessages(messages, session, options)`。
  - hidden/internal context stripping。
  - thinking extraction。
  - product suggestion marker parsing。
  - compression/handoff placement model。
- 抽 message renderer：
  - 输入 render model，输出 DOM nodes。
  - 不读取全局 `S`。
  - event handler 通过 delegated listeners 注册。
- 抽 post-process renderers：
  - markdown sanitizer。
  - code highlight/copy。
  - mermaid/katex/csv/excalidraw/pdf/html inline preview。
- 抽 workspace tree：
  - `workspace-tree-controller.js`。
  - `workspace-tree-view.js`。
  - `workspace-context-menu.js`。
  - 保留临时 `window.renderFileTree/loadDir/openFile` facade。
- 抽 chrome controllers：
  - `model-picker.js`。
  - `reasoning-picker.js`。
  - `toolsets-picker.js`。
  - `health-panels.js`。
  - `update-banner.js`。

短期修复：

- `setBusy()` 改名或拆出 `onTurnBecameIdle()`，减少误用。
- Queue drain 不再通过 composer/global pending state 二次构造请求。
- 新增代码禁止 inline `onclick`，旧代码逐步迁移。
- 建一个轻量 JS behavior test harness：
  - Node/vm + fake DOM。
  - 测 `QueuedTurnRequest` merge/drain。
  - 测 `buildRenderableMessages()`。
  - 测 composer primary action。
- 对静态窗口测试做降级：
  - 从 `idx:idx+800` 改为 AST/function-body 或行为测试。

验收：

- `ui.js` 剩下 app bootstrap/glue，不再持有 workspace tree/message renderer/queue 实现细节。
- 改 queue 行为时不需要读 `renderMessages()`。
- 改 workspace tree 时不需要读 composer/model picker。
- 新增消息渲染规则时可以通过纯函数测试验证。
- TS 只进入 `QueuedTurnRequest`、message render model、app state action 这类边界，不包装旧全局脚本。

### 10.16 `routes.py` route table / service boundary split

目标：

- 让后端路由可枚举、可测试、可迁移。
- 新增 API 时不再往 10000 行 `routes.py` 继续追加 `if parsed.path`。
- 把 HTTP adapter 和领域服务拆开，避免 `/api/session`、`/api/session/new` 这种 route handler 继续承担完整业务服务。

当前观察：

- `apps/webui/api/routes.py` 约 10720 行。
- `parsed.path` 命中 189 处。
- `if parsed.path` 命中 178 处。
- `handle_get()` 横跨约 1050 行。
- `handle_post()` 横跨约 1620 行。
- `handle_patch()` / `handle_delete()` 只有 CSRF + `read_body()`，没有实际 route。
- `/api/session`、`/api/sessions`、`/api/session/new` 已经不是薄 handler，而是 service。
- 产品 preview route 仍使用 `"/preview" in parsed.path`，匹配偏宽。

第一步：建立 route manifest，而不是立刻大搬家。

- 新增 `api/route_table.py`：
  - route name。
  - method。
  - exact path 或 segment matcher。
  - handler callable。
  - csrf policy。
  - body policy：none/json/multipart/sse/file。
  - response kind：json/file/sse/html。
- `handle_get()` / `handle_post()` 先查 registry。
- 老 if 链保留为 fallback，降低一次性风险。
- 新增测试：
  - registry 里 path 不重复。
  - exact route 不被 catchall 遮挡。
  - `/api/products/<id>/preview` matcher 只匹配 segment，不匹配任意包含 preview 的路径。
  - POST route 默认必须 CSRF，豁免项显式列出。

第二步：迁移低耦合 HTTP helpers。

- `routes_static.py`：
  - `/static/*`
  - `/session/static/*`
  - manifest / sw / favicon。
- `routes_files.py`：
  - `/api/media`
  - `/api/file/raw`
  - `/api/file`
  - `/api/list`
  - file create/save/delete/rename/path/reveal。
- `http_responses.py`：
  - `json_response`。
  - `bad_request`。
  - `file_response`。
  - `sse_response_headers`。
  - `_security_headers()` 统一入口。

第三步：优先迁移 product routes。

- `routes_products.py` 只保留 HTTP adapter。
- `product_route_params.py` 统一解析：
  - body id。
  - URL id。
  - suffix path。
  - asset path。
- `preview_product_file()` 返回 target 后，统一用安全 file response。
- 产品 HTML preview：
  - CSP sandbox。
  - no same-origin。
  - no sniff。
- 产品 SVG：
  - 默认 download，除非有明确安全策略。
- 快速验收：
  - `list_products/get_status/list_versions/create/update/delete/finalize/snapshot/rollback/preview` route 行为不变。
  - security header 和 `/api/file/raw?inline=1` 对齐。

第四步：迁移 session read/list/mutation。

- `routes_sessions.py`：
  - 只解析 HTTP query/body 和异常映射。
- `session_read_service.py`：
  - `get_session_payload(sid, options)`。
  - message paging。
  - CLI/messaging merge。
  - model/provider/context length display fallback。
  - run journal payload。
  - redaction。
- `session_list_service.py`：
  - webui sessions。
  - CLI sessions。
  - profile scope。
  - messaging dedupe。
  - title redaction。
- `session_mutation_service.py`：
  - new/duplicate/update/delete/clear/truncate/branch/pin/archive/move。
- 快速验收：
  - route tests 不读 `routes.py` 源码窗口。
  - session read/list 的输入输出可以纯函数测试。
  - deleting/importing CLI/messaging sessions 的现有保护仍在。

第五步：迁移 SSE / long-lived routes。

- `routes_streams.py`：
  - chat stream。
  - gateway stream。
  - terminal output。
- `routes_approval.py`：
  - approval pending/respond/stream/inject。
- `routes_clarify.py`：
  - clarify pending/respond/stream/inject。
- 把重复 SSE headers、heartbeat、unsubscribe finally 模式抽 helper。
- 快速验收：
  - approval/clarify stream 初始 snapshot 不丢事件。
  - client disconnect 不泄露 subscriber。
  - queue full drop 行为保持。

第六步：迁移剩余业务域。

- `routes_crons.py`。
- `routes_skills.py`。
- `routes_memory.py`。
- `routes_mcp.py`。
- `routes_profile_settings.py`。
- `routes_updates.py`。
- `routes_rollback.py`。
- `routes_onboarding.py`。

短期修复：

- 产品 preview matcher 从 `"/preview" in path` 改为 segment matcher。
- `_serve_file_response()` 补统一 security headers。
- HTML/SVG 产品 asset 策略和 `/api/file/raw` 对齐。
- 给 `PATCH/DELETE` 明确：
  - 要么删除空壳。
  - 要么接入 route registry 并加 no-route test。
- 给 route 增加体量守门：
  - 禁止新 route 直接写进 `routes.py` 主 if 链。
  - 新 route 必须进入 registry 或对应 `routes_*.py`。

验收：

- `routes.py` 只剩：
  - legacy fallback。
  - common imports。
  - route registry dispatch。
- 新增一个 API 可以通过 route manifest 找到 owner。
- 安全 headers 由统一 response helper 控制。
- `routes.py` 行数不再增长。
- route tests 从源码字符串检查逐步转为行为测试。

### 10.17 `i18n.js` locale asset split / translation contract

目标：

- 把 11000 行的翻译资产从运行时代码里拆出来。
- 让缺 key、额外 key、函数型 key 类型不一致、占位符不一致可以被机器发现。
- 让英文 fallback 成为可靠基准，而不是混合中文/英文的兜底。

当前观察：

- `apps/webui/static/i18n.js` 约 11532 行。
- 真正运行时代码只有最后约 130 行：
  - `resolveLocale()`。
  - `resolvePreferredLocale()`。
  - `t()`。
  - `setLocale()`。
  - `loadLocale()`。
  - `applyLocaleToDOM()`。
- `LOCALES` 包含 11 个 locale：
  - `en`
  - `it`
  - `ja`
  - `ru`
  - `es`
  - `de`
  - `zh`
  - `zh-Hant`
  - `pt`
  - `ko`
  - `fr`
- `en` 有 1039 个非 metadata key。
- `en` 有 49 个 function-valued key。
- `en` 中有大量中文 fallback 文案，已经不是纯英文基准。

第一步：建立 i18n audit，不先改文案。

- 新增 `scripts/audit-i18n.mjs` 或 `apps/webui/scripts/audit-i18n.mjs`。
- audit 直接执行或解析 `LOCALES`。
- 输出：
  - locale 列表。
  - 每个 locale key 数。
  - missing key。
  - extra key。
  - duplicate key。
  - function/string type mismatch。
  - placeholder mismatch。
  - `en` 中的非英文字符。
- CI 或本地测试先允许 warning 模式，避免一次性修全部翻译。

第二步：定义 translation contract。

- 新增 `docs/I18N_CONTRACT.md`：
  - `en` 是唯一 fallback base。
  - 新 key 必须先进入 `en`。
  - 非英文 locale 可以临时缺 key，但必须由 audit 报告。
  - function-valued key 不再新增；新动态文案使用 `{0}` / `{name}` placeholder。
  - 每个 key 归属一个 domain：
    - `chat`
    - `session`
    - `workspace/files`
    - `product`
    - `settings`
    - `onboarding`
    - `mcp`
    - `cron`
    - `terminal`
- 建议追加机器可读 contract：
  - `static/i18n/schema.js`。
  - 标注 key type 和 required 级别。

第三步：拆文件，不改加载语义。

- 保留全局 API：
  - `LOCALES`
  - `t`
  - `setLocale`
  - `loadLocale`
  - `applyLocaleToDOM`
- 拆成：
  - `static/i18n/runtime.js`
  - `static/i18n/locales/en.js`
  - `static/i18n/locales/zh.js`
  - `static/i18n/locales/zh-Hant.js`
  - `static/i18n/locales/ko.js`
  - 其他 locale 同理。
- `index.html` script 顺序：
  - locale files 先加载。
  - runtime 后加载或 runtime 注册函数支持。
- 若不想增加 12 个 script，可先 build-time concat，源码拆分、产物仍是 `i18n.js`。

第四步：把 function-valued keys 收敛成模板。

- 现状 function key 示例：
  - `queued_count(n)`。
  - `provider_mismatch_warning(m, p)`。
  - `goal_status_active(goal)`。
  - `session_time_minutes_ago(n)`。
  - `workspace_switched_to(name)`。
- 新增 `formatI18n(key, params)`：
  - 支持 `{count}`。
  - 支持 `{model}`。
  - 支持 `{provider}`。
  - 支持简单 plural helper。
- 逐步把 function-valued translations 改成 template string。
- 验收前先保证 function key 的每个 locale 类型一致。

第五步：重写测试。

- `test_language_precedence.py` 保留，这是好测试。
- 新增或替换：
  - `test_i18n_audit.py` 调用 audit。
  - `test_i18n_locale_blocks.py` 动态读取 `LOCALES`，不使用手写 regex 截 block。
  - `test_i18n_placeholders.py` 检查 placeholder 集合一致。
- 删除或改造：
  - 基于 “字符串出现次数 >= 6” 的测试。
  - 假设 locale 顺序的测试。
  - 旧 DOM 类名如 `.rail-btn` / `<nav class="rail">` 的 tooltip 测试。

短期修复：

- 把 `product_ui_title`、`session_rename_failed_no_row` 补全到所有 shipped locale，或在 contract 里标 optional。
- 清理 `en` 中的中文 fallback，至少优先清理：
  - offline。
  - approval。
  - voice。
  - status。
  - session/workspace。
- 修 Spanish/Korean 测试的旧代表文案：
  - `tab_tasks/tab_skills/tab_memory/tab_profiles` 当前不在 shipped locale 中。
  - `settings_desc_sync_insights` 当前不在 shipped locale 中。
- 修 tooltip 测试的旧 rail DOM 断言，改为 `.nav-tab` / 当前 sidebar structure。
- 当前工作区已有 `Workspace -> Files`、`Toolsets -> Access` 文案改动；需要用一份术语表确认这是不是产品语言方向，而不是零散替换。

验收：

- `node --check static/i18n.js` 或拆分后的 runtime 通过。
- audit 输出可读报告。
- 每个新增 key 能看到归属 domain 和 fallback。
- 运行时 API 不变，旧页面不会闪英文或丢 `data-i18n-title` tooltip。
- 测试不再依赖 locale 顺序或字符串出现次数。
- `en` fallback 不再混入中文。

## 10.18. 拆 `streaming.py` Agent stream lifecycle

现状：

- `api/streaming.py` 5534 行。
- `_run_agent_streaming()` 约 2350 行，是后端会话执行主控制器。
- `cancel_stream()` 约 310 行，是取消流的另一套控制器。
- 当前行为不是完全错误，反而有很多经过线上问题修补出来的保护：
  - pending user message。
  - periodic checkpoint。
  - last-resort sync。
  - stale stream writeback guard。
  - cancel partial/reasoning/tool-call preservation。
  - context compression snapshot。
  - run journal / turn journal。
  - credential self-heal。
  - product generation finalize guard。
- 主要问题是责任边界过宽，修改任一局部都需要理解成功、失败、取消、压缩、重试、finally 多条远距离路径。

第一步：抽 stream turn context，不改行为。

- 新增 `api/stream_turn.py` 或 `api/stream_lifecycle.py`。
- 定义 `StreamTurnContext`：
  - `session_id`
  - `stream_id`
  - `original_session_id`
  - `workspace`
  - `model`
  - `provider`
  - `ephemeral`
  - `cancel_event`
  - `agent_lock`
  - `product_context`
- 封装：
  - `register_active_run`
  - phase update。
  - stream map cleanup。
  - thread env cleanup。
- 验收：
  - 不改 SSE event shape。
  - `test_issue765_streaming_persistence.py` 继续通过。
  - `test_cancel_interrupt.py` 继续通过。

第二步：抽产品 turn finalizer。

- 新增 `api/stream_product_turn.py`。
- 把 `_finalize_product_turn()` 从 `_run_agent_streaming()` nested closure 里拿出来。
- 提供幂等 API：
  - `success()`
  - `fail(error_type=None, error_message=None)`
  - `cancel()`
  - `fail_if_unfinished()`
- 保留现有语义：
  - 只处理 `product_init` / `product_builder`。
  - 无 `product_context` 时直接 no-op done。
  - `finalize_product_generation()` 成功后才标 finalized。
  - success 后 finally failure 不覆盖。
- 新增单测：
  - success + finally 不重复 failure。
  - failure + finally 不重复。
  - finalize 抛异常时允许后续重试。
  - 非 product scope no-op。

第三步：抽 callbacks / metering / live state。

- 新增 `api/stream_callbacks.py`。
- 移出：
  - `on_token`
  - `on_reasoning`
  - `on_interim_assistant`
  - `on_tool`
  - `on_tool_start`
  - `on_tool_complete`
  - live prompt estimate。
  - metering throttle。
  - partial/reasoning/tool-call mirror。
  - checkpoint activity bump。
- 验收：
  - cancel 后仍保留 partial text。
  - cancel 后仍保留 reasoning。
  - cancel 后仍保留 live tool calls。
  - cache usage / TPS 相关测试通过。

第四步：抽 agent runtime builder/cache。

- 新增 `api/stream_agent_runtime.py`。
- 移出：
  - model/provider/base_url/API key resolve。
  - custom provider resolve。
  - AIAgent kwargs build。
  - `SESSION_AGENT_CACHE` signature。
  - cached agent refresh。
  - primary runtime snapshot refresh。
  - profile env mutation 后 MCP discovery 的调用点。
- 验收：
  - `test_issue1897_profile_switch_agent_cache.py` 通过。
  - provider fallback/self-heal 相关测试通过。

第五步：抽 persistence / result merge。

- 新增 `api/stream_persistence.py`。
- 移出：
  - `_materialize_pending_user_turn_before_error`
  - `_last_resort_sync_from_core`
  - `_merge_display_messages_after_agent_result`
  - `_restore_reasoning_metadata`
  - `_context_messages_for_new_turn`
  - error assistant message append。
  - completed/cancelled turn journal append helper。
- 验收：
  - 错误消息仍 `_error=True`，不会进入下次 LLM API context。
  - pending user 在 error/cancel 后不丢。
  - turn journal event 顺序不变。

第六步：抽 provider errors / self-heal。

- 新增 `api/stream_errors.py`。
- 移出：
  - `_classify_provider_error`
  - `_provider_error_payload`
  - silent failure detection。
  - `_attempt_credential_self_heal`
  - retry run + merge result。
- 合并 silent failure 和 exception path 的重复 retry/persist 逻辑。
- 验收：
  - 401 self-heal 只重试一次。
  - retry 成功不发 apperror。
  - retry 失败发原错误。
  - product turn failure finalize 正确带 error type/message。

第七步：抽 compression / title / goal hooks。

- 新增：
  - `api/stream_compression.py`
  - `api/stream_titles.py`
  - `api/stream_goals.py`
- 移出：
  - pre-compression snapshot。
  - session id rotation。
  - lock/cache migration。
  - compressed SSE payload。
  - generated title sanitize / aux title / background refresh。
  - goal continuation event。
- 验收：
  - `test_auto_compression_card.py` 通过。
  - `test_title_sanitization.py` 通过。
  - context compression 后原 activeSid 的 `stream_end` 仍正确。

第八步：抽 cancel / steer。

- 新增：
  - `api/stream_cancel.py`
  - `api/stream_steer.py`
- `cancel_stream()` 保留现有 lock order：
  - `STREAMS_LOCK` 中只设置 cancel/interruption/pop stream maps。
  - session mutation 在 `STREAMS_LOCK` 外做。
  - session mutation 用 per-session agent lock。
- `_handle_chat_steer()` 明确 response contract：
  - `accepted`
  - `fallback`
  - `stream_id`
  - `product_scope`
- 修测试：
  - 后端响应测试不要严格等于整包，或更新 contract。
  - 前端 `_trySteer` 测试不要截固定 1500 字符；改成 AST/函数体完整提取或 vm 行为测试。

第九步：再引入 `internal_context`。

- 在 stream lifecycle 拆分后，再给 `_run_agent_streaming()` 或新入口增加 `internal_context`。
- `internal_context` 只进入 agent input/prompt，不进入 visible `msg_text`。
- queue、steer、product init 都使用同一 request contract。
- 这一步要和前端 hidden instruction 修复一起做。

验收：

- `py_compile api/streaming.py` 和拆出模块通过。
- streaming/cancel/steer/title/compression/provider fallback 测试通过。
- SSE `token/reasoning/tool/tool_complete/done/metering/stream_end/apperror/cancel` shape 不变。
- product generation success/failure/cancel 状态不再卡在 `generating`。
- 新增 stream 行为时不再直接扩大 `_run_agent_streaming()`。

## 10.19. 拆 session model / sidebar / command request contract

现状：

- `api/models.py` 2477 行，职责包括：
  - `Session` JSON sidecar model。
  - atomic save。
  - metadata-only load。
  - `_index.json` 写入。
  - stale pending repair。
  - run journal partial output recovery。
  - sidebar compact/list filtering。
  - compression lineage metadata。
  - projects。
  - cron project。
  - CLI session import/cache。
  - Claude Code JSONL import。
- `static/sessions.js` 3848 行，职责包括：
  - composer draft。
  - new/load session。
  - inflight restore。
  - message tail paging。
  - unread/observed streaming。
  - sidebar data store。
  - sidebar DOM render。
  - virtualization。
  - gateway SSE。
  - handoff hint。
  - project CRUD。
  - batch select。
- `static/commands.js` 1407 行，slash command 逻辑可读，但 request 组包分散。

总体判断：

- 这条线不是“坏代码”。相反，它有很多正确的可靠性保护：
  - metadata-only session 禁止 save。
  - session save shrink backup。
  - stale pending 30 秒 grace。
  - per-session agent lock。
  - run journal partial output recovery。
  - lazy message tail loading。
  - stale response guard。
  - inflight tail merge。
  - sidebar virtualization。
- 问题是职责边界太宽。重构时要保留这些保护，不要为了少行数破坏恢复语义。

后端第一步：定义 session wire contract。

- 新增 `docs/SESSION_CONTRACT.md`。
- 明确三类 payload：
  - persisted sidecar JSON。
  - compact sidebar row。
  - `/api/session` full/tail response。
- 字段分类：
  - identity/title/time。
  - workspace/model/profile。
  - product。
  - worktree。
  - runtime stream/pending。
  - compression。
  - usage。
  - CLI/messaging source。
  - draft。
- 明确哪些字段只后端持久化、哪些是前端可写。

后端第二步：拆 `api/session_model.py`。

- 移入：
  - `Session`。
  - `Session.save()`。
  - `Session.load()`。
  - `Session.load_metadata_only()`。
  - metadata field list。
  - sidecar path validation。
- 保留现有语义：
  - metadata-only save guard。
  - atomic write。
  - shrink backup。
- 验收：
  - `test_session_metadata_fast_path.py` 通过。
  - `test_metadata_save_wipe_1558.py` 通过。
  - `test_session_tail_payload.py` 通过。

后端第三步：拆 `api/session_index.py`。

- 移入：
  - `_cleanup_stale_tmp_files()`。
  - `_write_session_index()`。
  - `_index_entry_exists()`。
  - index full rebuild / fast update。
- `Session.save()` 通过 narrow API 调 index update。
- 验收：
  - `test_session_index.py` 通过。
  - empty session 不落盘测试通过。

后端第四步：拆 `api/session_repair.py`。

- 移入：
  - `_repair_stale_pending()`。
  - `_apply_core_sync_or_error_marker()`。
  - `_append_journaled_partial_output()`。
  - interrupted recovery marker。
  - run journal visible output helpers。
- 保留：
  - 30 秒 grace。
  - non-blocking per-session lock acquire。
  - core transcript / sidecar / journal 的修复顺序。
- 验收：
  - `test_session_sidecar_repair.py` 通过。
  - streaming persistence/cancel 相关测试通过。

后端第五步：拆 `api/session_sidebar.py`。

- 移入：
  - `all_sessions()` 的 sidebar aggregation。
  - empty Untitled filtering。
  - pre-compression snapshot filtering。
  - `_prefer_fuller_snapshots_for_sidebar()`。
  - lineage metadata enrichment。
  - active stream runtime marking。
- 验收：
  - `test_streaming_session_sidebar.py` 通过。
  - `test_session_lineage_collapse.py` 通过。
  - `test_sidebar_first_turn_visibility.py` 通过。
  - `test_issue2157_sessions_list_stale_stream_state.py` 通过。

后端第六步：拆 `api/session_read.py`。

- 移出 `/api/session` handler 的核心查询逻辑：
  - metadata-only。
  - full messages。
  - tail window。
  - `msg_before` paging。
  - CLI fallback。
  - messaging session merge。
  - effective model/provider display。
  - context length fallback。
  - runtime journal payload。
  - redaction 前的 raw session payload。
- route 只做 query parsing 和 response。
- 验收：
  - `test_session_tail_payload.py` 通过。
  - `test_session_cli_scan_fast_path.py` 通过。
  - `test_session_metadata_cli_lookup.py` 通过。
  - `test_issue1436_context_indicator_load_path.py` 通过。

后端第七步：拆 `api/session_mutations.py`。

- 移入：
  - draft save/get。
  - session update。
  - branch。
  - archive/delete/pin/rename 等 session mutation route 后续也迁入。
- `session_ops.py` 可保持 retry/undo/status/usage，或作为 mutation/read service 的子模块。
- 验收：
  - `test_stage326_composer_draft_validation.py` 通过。
  - `test_session_ops.py` 通过。
  - branch/duplicate/rename 相关测试通过。

前端第一步：拆 `session-drafts.js`。

- 移入：
  - `_saveComposerDraft`
  - `_saveComposerDraftNow`
  - `_restoreComposerDraft`
  - `_clearComposerDraft`
- 验收：
  - 快速切 session 不丢 draft。
  - 空 draft 能清掉上一个 session textarea。
  - draft files 语义先维持现状，不假装恢复未实现的 pendingFiles。

前端第二步：拆 `message-pager.js`。

- 移入：
  - `_ensureMessagesLoaded`
  - `_loadOlderMessages`
  - `_ensureAllMessagesLoaded`
  - `_mergeInflightTailMessages`
  - `_messagesTruncated`
  - `_oldestIdx`
  - `_messagesGeneration`
- 验收：
  - `test_session_endless_scroll.py` 通过。
  - `test_parallel_session_switch.py` 通过。
  - long transcript 切换不丢历史。

前端第三步：拆 `session-loader.js`。

- 保留 `loadSession()` public API，但内部拆阶段：
  - `saveCurrentDraftBeforeSwitch()`
  - `loadMetadata()`
  - `applySessionMetadata()`
  - `restoreStreamingSession()`
  - `restoreIdleSession()`
  - `finalizeSessionLoad()`
- 验收：
  - streaming session 重新 attach。
  - idle session 清 stale inflight。
  - approval/clarify/yolo polling 恢复不变。
  - URL/localStorage 同步不变。

前端第四步：拆 sidebar store/view。

- 新增 `session-sidebar-store.js`：
  - `_allSessions`
  - render fetch。
  - optimistic first-turn merge。
  - unread/observed streaming。
  - profile/project/archive/search state。
- 新增 `session-sidebar-view.js`：
  - `renderSessionListFromCache()` DOM render。
  - virtualization。
  - action menu。
  - project chips。
  - batch selection。
- 新增 `session-lineage-view.js`：
  - compression lineage collapse。
  - child session attach。
  - lineage report cache。
- 验收：
  - sidebar search/filter/virtualization 不回退。
  - context compression lineage collapse 不回退。
  - child sessions/forks 展示不回退。

前端第五步：拆 gateway sync。

- 新增 `session-gateway-sync.js`。
- 移入：
  - gateway SSE。
  - fallback poll。
  - active CLI session refresh。
- 验收：
  - gateway sync 测试通过。
  - SSE 失败后 fallback poll 生效。

前端第六步：建 `command-request-builder.js`。

- 统一给这些路径组包：
  - `send()`
  - `/queue`
  - `/interrupt`
  - `/steer`
  - retry 后 re-send。
- 输出 `TurnRequest`：
  - `text`
  - `files`
  - `model`
  - `model_provider`
  - `profile`
  - `product_id`
  - `product_scope`
  - `product_intent`
  - `internal_context`
- `withCurrentProductContext()` 变成 builder 的内部步骤，而不是散落调用。
- 验收：
  - queued turn 不丢 product context。
  - hidden instruction 不进入 visible text。
  - steer fallback 与 interrupt queue 走同一 contract。

本轮已验证基线：

- `node --check static/sessions.js` 通过。
- `node --check static/commands.js` 通过。
- `py_compile api/models.py api/session_ops.py` 通过。
- 137 个 session 相关测试通过：
  - `test_session_ops.py`
  - `test_session_tail_payload.py`
  - `test_session_metadata_fast_path.py`
  - `test_session_sidecar_repair.py`
  - `test_stage326_composer_draft_validation.py`
  - `test_empty_session_no_disk_write.py`
  - `test_issue2157_sessions_list_stale_stream_state.py`
  - `test_issue2066_stale_sidebar_spinner.py`
  - `test_issue500_session_list_virtualization.py`
  - `test_issue1144_session_time_sync.py`
  - `test_parallel_session_switch.py`

## 10.20. 拆 model / provider / settings 配置链路

目标：

- 让“模型选择器、provider key/OAuth、自定义 provider、默认模型设置”有明确契约。
- 把 `api/config.py` 从“全局内核”拆回可维护的配置/模型/provider/runtime state 模块。
- 把 `static/panels.js` 从杂糅设置面板拆成 settings/provider/system/checkpoint 子模块。
- 后续 TS 只迁纯逻辑和协议边界，而不是迁移巨型函数。

先建契约：

- 新增 `docs/MODEL_PROVIDER_CONTRACT.md`。
- 明确定义：
  - `ProviderId`
  - `CustomProviderId`
  - `ModelOption`
  - `ModelGroup`
  - `ResolvedRuntimeModel`
  - `SettingsPayload`
  - `ProviderStatus`
  - `ProviderCredentialMutation`
- 明确 UI model id grammar：
  - bare model。
  - `provider/model`。
  - `@provider:model`。
  - `@custom:<slug>:model`。
  - provider id 中含 `:` 时的 split 规则。
  - model id 后缀如 `:free`、`:beta` 不应被误拆。

后端第一步：拆路径和 config store。

- 新增 `api/config_paths.py`：
  - `HOME`
  - `STATE_DIR`
  - active profile config path。
  - auth store path。
- 新增 `api/config_store.py`：
  - YAML load/reload/save。
  - mtime guard。
  - in-memory override policy。
- 验收：
  - config mtime reload 测试通过。
  - profile switch 不读错 config。
  - provider key cleanup 不写错 config。

后端第二步：拆 provider identity。

- 新增 `api/provider_identity.py`：
  - provider alias/canonicalization。
  - display names。
  - env var mapping。
  - custom provider slug。
  - local server/base_url classification。
- 验收：
  - LM Studio/Ollama/local/custom provider tests 通过。
  - mixed case provider tests 通过。
  - same model across multiple custom providers tests 通过。

后端第三步：拆 model catalog。

- 新增 `api/model_catalog.py`：
  - static catalog。
  - live `hermes_cli.models.provider_model_ids()` adapter。
  - Codex local `models_cache.json` merge。
  - Nous/OpenCode/NVIDIA portal featured set。
  - label formatter。
- 验收：
  - picker 与 provider card 的 model count/model subset 由同一 catalog service 输出。
  - `get_available_models()` 和 `get_providers()` 不再复制 live/static merge 逻辑。

后端第四步：拆 model resolver。

- 新增 `api/model_resolver.py`。
- 把 `resolve_model_provider()` 改成规则链：
  - normalize input。
  - custom provider exact match。
  - explicit `@provider:model`。
  - slash model。
  - base_url/local server preservation。
  - OpenRouter fallback。
  - configured provider fallback。
- 每条规则都有 fixture 测试。
- 验收：
  - `test_model_resolver.py`
  - `test_resolve_model_provider_free_suffix.py`
  - `test_issue1855_resolve_model_provider_fast_path.py`
  - `test_issue1806_named_custom_provider_resolution.py`
  - `test_issue2177_nvidia_prefix_preservation.py`
  - `test_issue1625_local_server_model_id_preservation.py`
  - `test_provider_mismatch.py`。

后端第五步：拆 model cache。

- 新增 `api/model_cache.py`。
- 移入：
  - memory TTL。
  - disk cache。
  - schema version。
  - WebUI version stamp。
  - source fingerprint。
  - single-flight rebuild lock。
  - invalidate APIs。
- 验收：
  - `test_ttl_cache.py`
  - `test_model_cache_metadata.py`
  - `test_issue1633_models_cache_version_stamp.py`
  - `test_issue1699_model_cache_source_fingerprint.py`
  - `test_live_models_ttl_cache.py`。

后端第六步：拆 provider credentials。

- 新增 `api/provider_credentials.py`。
- 移入：
  - env file load/write。
  - env alias。
  - key format validation。
  - OAuth/non-OAuth guard。
  - JWT shadowed Codex OAuth guard。
  - config.yaml key cleanup。
- `_write_env_file()` 不应依赖 `api.streaming._ENV_LOCK`。
- 可新增独立 credential write lock。
- 验收：
  - `.env` comments/order 保持。
  - key save/remove 后 model cache invalidated。
  - OAuth provider 不走 API key save。

后端第七步：拆 provider usage / cost history。

- 新增 `api/provider_usage.py`。
- 新增 `api/provider_cost_history.py` 或并入 usage 子包。
- 移入：
  - account usage cache。
  - subprocess probe。
  - semaphore/timeout。
  - quota status response。
  - cost history。
- 验收：
  - `test_provider_quota_status.py`
  - `test_provider_cost_history.py`
  - `test_issue1765_codex_quota.py`。

后端第八步：拆 settings store。

- 新增 `api/settings_store.py`。
- 移入：
  - `_SETTINGS_DEFAULTS`
  - allowed keys。
  - `load_settings()`
  - `save_settings()`。
- 默认模型 mutation 与 `/api/settings` 分清：
  - ordinary settings save。
  - password mutation。
  - default model mutation。
- 验收：
  - settings save 不误清 auth。
  - default model 失败时有可测试 fallback。

前端第一步：拆 settings payload。

- 新增 `settings-payload.js`。
- 统一：
  - `_appearancePayloadFromUi()`
  - `_preferencesPayloadFromUi()`
  - `saveSettings()` 的手动 payload。
- 验收：
  - autosave 与手动 save 使用同一字段定义。
  - 新增 settings 字段时只改一处 schema/map。

前端第二步：拆 settings state/autosave/panel。

- 新增：
  - `settings-state.js`
  - `settings-autosave.js`
  - `settings-panel.js`
- 移出：
  - dirty state。
  - unsaved bar。
  - open baseline。
  - appearance/preference autosave。
  - `loadSettingsPanel()`。
- 验收：
  - dirty guard 不被 rail/sidebar navigation 绕过。
  - autosave 不误清 password/default model dirty state。

前端第三步：拆 provider panel。

- 新增：
  - `provider-panel.js`
  - `provider-card.js`
  - `provider-quota-view.js`
- 所有 provider card 文案走 i18n。
- 避免手写硬编码英文：
  - `Show`
  - `Hide`
  - `Models`
  - `+N more`
  - default model failure toast。
- 验收：
  - provider key save/remove 后刷新 model dropdown cache。
  - quota refresh 行为不变。
  - custom providers panel tests 通过。

前端第四步：拆 system/checkpoint panels。

- 新增：
  - `system-panel.js`
  - `checkpoint-panel.js`
- 移出：
  - MCP servers/tools。
  - gateway status。
  - checkpoint list/diff/restore。
- 验收：
  - `panels.js` 只剩 panel router 和 shared guard。

前端第五步：收口旧面板残留。

- 当前 `static/panels.js` 仍引用 `loadCrons()`，但 `static/` 下未找到定义。
- `test_settings_navigation_and_detail_refresh.py` 仍在寻找旧的 master-detail 清理逻辑。
- 先确认产品是否仍有 tasks/workspaces/profiles 面板：
  - 如果已迁移：删除残留调用，更新/删除静态测试。
  - 如果仍存在：恢复定义并补行为测试。
- 验收：
  - `test_settings_navigation_and_detail_refresh.py` 要么改成当前模块位置，要么删除陈旧断言。
  - 没有未定义全局函数引用。

本轮已验证基线：

- `node --check static/panels.js static/boot.js` 通过。
- `py_compile api/config.py api/providers.py api/profiles.py` 通过。
- model/provider/settings 相关 pytest：
  - 270 collected。
  - 265 passed。
  - 5 failed，集中在旧 settings master-detail 静态测试/残留面板逻辑。

## 10.21. 拆 boot / profile / workspace / update / onboarding 链路

目标：

- 把启动编排从 `boot.js` 的 UI controller 大杂烩里拆出来。
- 把 profile 的路径/env/cron/service 职责从 `profiles.py` 拆开。
- 把 workspace 的 store/security/files 职责拆开。
- 收口旧 profile dropdown / cron / tasks / profiles / workspaces 面板残留。
- 更新静态测试，让它保护当前产品形态，而不是保护已经不存在的旧函数名。

优先修复：缺失的 profile 前端入口。

- 当前 `static/index.html` 有：
  - `onclick="toggleProfileDropdown()"`
- 但当前 `apps/webui/static/*.js` 搜不到：
  - `toggleProfileDropdown`
  - `switchToProfile`
- 多个测试仍在 `static/panels.js` 中寻找 `switchToProfile()`。
- 处理路径：
  1. 如果 profile chip 仍是产品入口：恢复/重建 `profile-switcher.js`。
  2. 如果 profile chip 已废弃：删除 HTML 入口、删除相关死代码和陈旧测试。
- 验收：
  - 点击 profile chip 不会 `ReferenceError`。
  - profile switch 使用 `/api/profile/switch`，并应用 profile default model/workspace。
  - switch 时 chip 有 switching/disabled/optimistic/revert 行为或新的等价 UX。

前端第一步：拆启动编排。

- 新增 `boot-coordinator.js`。
- 只保留这些 boot 阶段：
  - settings preload。
  - profile preload。
  - model dropdown preload。
  - workspace list preload。
  - onboarding gate。
  - session restore。
  - inflight restore。
  - gateway SSE start。
- `boot.js` 不再承载 voice、appearance、workspace panel、profile dropdown。

前端第二步：拆 workspace panel。

- 新增：
  - `workspace-panel-controller.js`
  - `workspace-file-api.js`
  - `workspace-tree-view.js`
  - `workspace-preview.js`
- 移入：
  - `_workspacePanelMode`。
  - `syncWorkspacePanelState()`。
  - file tree expanded dirs。
  - preview/edit/save/download/open browser。
- 验收：
  - workspace 聚焦 66 个测试继续通过。
  - preview/edit/download 不回退。

前端第三步：拆 voice 和 appearance。

- 新增：
  - `voice-input.js`
  - `voice-mode.js`
  - `appearance-client.js`
- 移出：
  - mic dictation。
  - MediaRecorder fallback。
  - turn-based voice mode。
  - theme/skin/font/meta theme-color。
- 验收：
  - voice mode 不读错 session 的最后回复。
  - theme/skin/font 仍能 settings autosave。

前端第四步：收口旧 cron/tasks/profiles/workspaces 面板。

- 当前确认：
  - `panels.js` 调用 `loadCrons()`，但未找到定义。
  - HTML 中未找到 `cronRefreshBtn`。
  - 未找到 `loadProfilesPanel()` / `renderWorkspacesPanel()`。
- 决策：
  - 如果这些面板仍属于产品：恢复模块和当前 DOM。
  - 如果已被新产品形态替代：删除残留调用，更新测试。
- 验收：
  - `test_cron_refresh_button_835.py` 和 `test_settings_navigation_and_detail_refresh.py` 不再保护不存在的 DOM/函数。

后端第一步：拆 profile path/env/cron。

- 新增：
  - `profile_paths.py`
  - `profile_env.py`
  - `profile_cron_context.py`
  - `profile_service.py`
- 移入：
  - root/default/named profile path resolution。
  - root alias cache。
  - `.env` reload。
  - skill module patch。
  - background worker env。
  - cron env lock / scheduler patch。
  - list/create/delete/switch。
  - profile model validation。
- 验收：
  - `test_profile_path_security.py`
  - `test_profile_env_isolation.py`
  - `test_profile_terminal_env.py`
  - `test_issue1700_parallel_profile_switch.py` 后端项。

后端第二步：拆 workspace store/security/files。

- 新增：
  - `workspace_store.py`
  - `workspace_security.py`
  - `workspace_files.py`
- 移入：
  - per-profile workspace state。
  - migration/cleanup。
  - trusted roots。
  - blocked roots。
  - traversal/symlink guard。
  - list/read/git info。
- 验收：
  - workspace 聚焦 66 个测试继续通过。
  - symlink/system dir/path traversal 行为不回退。

后端第三步：拆 updates。

- 新增：
  - `update_check.py`
  - `update_summary.py`
  - `update_apply.py`
- 移入：
  - version detection。
  - git check/cache。
  - summary prompt/fallback。
  - active stream update guard。
  - apply/force update。
  - restart scheduling。
- 验收：
  - backend update conflict/success/force-update tests 通过。
  - update apply UI recovery 文案测试与当前产品文案对齐。

后端第四步：拆 onboarding provider setup。

- 新增：
  - `onboarding_status.py`
  - `onboarding_setup.py`
  - `provider_probe.py`
  - `onboarding_oauth.py`
- 移入：
  - status aggregation。
  - config/env write。
  - supported provider setup catalog。
  - endpoint probe。
  - OAuth flow。
- 验收：
  - existing config 不被默认覆盖。
  - skip env hard guard 不写 config。
  - probe tests 避免受本机 proxy/DNS hijack 影响，使用 mock server/socket fixture。

测试治理：

- 把 profile/cron/workspace panel 的源码字符串测试改成当前模块/DOM 的行为测试。
- 对缺失全局 inline handlers 建统一扫描测试：
  - 收集 `index.html` 的 `onclick="fn(...)"`。
  - 检查 `static/*.js` 是否定义或明确由 product iframe 提供。
- 对组合测试污染补 isolation fixture：
  - 清空 `api.config.STREAMS`。
  - 清空 profile TLS。
  - 清空 update cache。

本轮已验证基线：

- `node --check static/boot.js static/workspace.js static/ui.js static/panels.js` 通过。
- `py_compile api/profiles.py api/workspace.py api/updates.py api/onboarding.py api/routes.py` 通过。
- profile/workspace/update/onboarding 大聚焦测试：
  - 332 collected。
  - 289 passed。
  - 2 skipped。
  - 41 failed。
- 单独复跑：
  - profile path/env isolation：5 passed。
  - workspace 聚焦组：66 passed。
  - frontend profile switch 组：20 passed，13 failed，集中在缺失 `switchToProfile()` 和旧 placeholder 文案。
  - update apply backend tests 通过；`test_update_apply_ui.py` 仍 1 failed。

## 10.22. 拆 terminal / approval / MCP / skills / cron 权限链路

这一组优先级很高，因为它不是普通 UI，而是“会执行命令、接外部工具、切 profile 资源、读写本地文件”的权限面。

现状判断：

- 底层安全逻辑并不差：
  - `api/terminal.py` 有 env allowlist、PTY、close cleanup。
  - `tools/approval.py` 有 hardline block、contextvars、session YOLO、gateway queue。
  - approval SSE 避免 subscribe/snapshot 丢事件。
  - MCP 有 credential redaction、safe env、description injection scan。
  - skills API 有 profile-aware dir 和 path traversal guard。
- 主要问题是承载层不清晰：
  - `routes.py` 继续承接 terminal/approval/clarify/yolo/MCP/skills/cron。
  - `messages.js` 继续承接 approval/clarify/notification/btw/background。
  - `panels.js` 有 MCP panel、cron residue、旧 settings fragment。
  - HTML 仍指向缺失的 `toggleProfileDropdown()`。
  - 测试仍期待缺失的 `switchToProfile()`、`loadCrons()`、skill detail/collapse 旧函数。

建议 TODO：

1. 建 `RUNTIME_CAPABILITIES_CONTRACT.md`
   - 定义 terminal、file、code_execution、skills、MCP、approval、YOLO、cron 的能力边界。
   - 写清 session scoped / profile scoped / process scoped / server memory scoped。
   - 写清哪些状态 reload 保留、server restart 丢失、cross-tab 共享。

2. 建 `TERMINAL_CONTRACT.md`
   - 定义 `session_id` 是否是 terminal capability。
   - start/input/output/resize/close 的权限前置条件。
   - workspace mismatch 时的关闭语义。
   - terminal cleanup/reaper/TTL 规则。

3. 抽后端 terminal：
   - `api/terminal.py` 保留 PTY runtime。
   - `api/terminal_routes.py` 放 HTTP/SSE handler。
   - `api/terminal_service.py` 放 session/workspace ownership 校验。
   - `routes.py` 只注册 route，不写逻辑。

4. 补 terminal 测试：
   - input/output/resize/close 必须处理 missing session、stale session、closed terminal。
   - workspace 更新/delete session 时 terminal 一定关闭。
   - server memory 丢 terminal 后 UI 状态能恢复。
   - terminal env 不含 API key/secrets。

5. 抽前端 terminal：
   - `terminal-client.js`：API/SSE/input/resize/close。
   - `terminal-controller.js`：session/workspace lifecycle。
   - `terminal-view.js`：xterm/render/copy/theme/height。
   - `terminal.js` 留薄 facade 或删除。

6. 抽 approval/clarify/YOLO 前端：
   - `approval-client.js`：pending/stream/respond/yolo。
   - `approval-store.js`：per-session pending map、current id、visibility timer。
   - `approval-card.js`：DOM render。
   - `clarify-client/store/card.js` 同理。
   - `messages.js` 只消费事件，不维护 approval/clarify 大状态机。

7. 抽 approval/clarify 后端 routes：
   - `api/approval_routes.py`
   - `api/clarify_routes.py`
   - `api/runtime_control.py`
   - 保留现有 queue/SSE 竞态修复逻辑。

8. 明确 YOLO contract：
   - session scoped。
   - in-memory。
   - enabling 时 resolve all pending approval。
   - hardline block 不受 YOLO 影响。
   - 补一条 test：YOLO 开启不能绕过 hardline。

9. 收口 MCP WebUI panel：
   - 明确当前 UI 是 read-only inventory，还是要恢复 editable config。
   - 如果 read-only：删掉 `_handle_mcp_server_delete()` / `_handle_mcp_server_update()` 死代码，或移到未来分支。
   - 如果 editable：补真正路由、CSRF/secret masking/update tests。

10. 抽 MCP inventory 后端：
    - `api/mcp_inventory.py`
    - `api/mcp_config_service.py`
    - `api/mcp_routes.py`
    - `routes.py` 只保留 route registry。

11. 抽 MCP 前端 panel：
    - `mcp-server-list.js`
    - `mcp-tool-inventory.js`
    - `mcp-schema-summary-view.js`
    - `panels.js` 只触发 lazy load。

12. 收口 skills WebUI：
    - 抽 `api/skills_service.py`，把 `_skills_list_from_dir()` / `_skill_view_from_active_dir()` 从 `routes.py` 移走。
    - 保留 profile-aware dir 和 plugin-qualified fallback。
    - 为 linked file/path traversal/wildcard/error payload 建 contract tests。

13. 决定 skills UI 去留：
    - 如果 settings skills panel 仍是产品入口：恢复/重写 `renderSkills()`、skill detail error、collapse state。
    - 如果已被新产品壳替代：删旧测试和旧 CSS/HTML residue，保留 `/skills` slash command。

14. 收口 cron 前端：
    - `loadCrons()` 当前缺失，但 `panels.js` 仍调用。
    - 要么恢复 cron panel controller，要么删事件监听和旧 tests。
    - 不允许继续保留“看起来有入口但运行时缺函数”的状态。

15. 抽 cron 后端：
    - `api/cron_routes.py`
    - `api/cron_profile_service.py`
    - `api/cron_run_service.py`
    - `api/cron_output_service.py`
    - 保留 child process profile isolation。

16. 增加 inline global handler scan：
    - 扫 `static/index.html` 所有 `onclick="foo(...)"`。
    - 校验 `static/*.js` 存在 `function foo` 或 `window.foo =`。
    - 先覆盖 `toggleProfileDropdown()` / `loadCrons()` 这类缺失。

17. TS 化边界：
    - 不直接把 `messages.js` / `panels.js` 整体改 TS。
    - 先 TS 化 pure contract：
      - runtime capability schema。
      - terminal request/response types。
      - approval/clarify event types。
      - MCP inventory row/schema summary types。
      - skills list/view payload。
    - DOM controller 等边拆边迁。

本轮验证：

- `node --check static/terminal.js static/messages.js static/commands.js` 通过。
- `py_compile api/terminal.py api/routes.py api/streaming.py mcp_server.py` 和 runtime approval/MCP/skills tool 通过。
- terminal/approval/YOLO/MCP/skills 聚焦测试：
  - 204 collected。
  - 187 passed。
  - 1 skipped。
  - 17 failed。
- 失败集中在旧 skills panel：
  - `_renderSkillError()` 缺失。
  - skill API error guard 缺失。
  - linked file error detail 缺失。
  - `_collapsedCats` / `_toggleCatCollapse()` / `renderSkills()` collapse 行为缺失。

## 10.23. 拆 auth / file / upload / media / rollback / worktree 资源访问链路

这一组不是简单“文件浏览器代码”。它是本地资源访问权限面，必须先保住现有安全边界，再拆巨型 route。

现状判断：

- 代码局部质量比体量看起来更好：
  - auth session/cookie/PBKDF2/登录限流比较完整。
  - CSRF 做了 browser unsafe request 兼容。
  - upload 有 per-session attachment inbox、archive slip/bomb/cleanup guard。
  - workspace path resolver 对 macOS/system root/symlink cycle 有历史修复。
  - file/raw 和 media inline HTML 都有 CSP sandbox。
  - worktree remove 有 stream/terminal/dirty/untracked/ahead gate。
  - rollback checkpoint id 有 path traversal validation。
- 主要问题是边界没有文档化：
  - workspace 读取和 raw/edit 的 symlink 行为不同。
  - `/api/media` 是 absolute-path capability，不是 session file API。
  - rollback 是 workspace-list scoped，不是 session scoped。
  - routes dispatcher 太大，任何安全修复都要进 `routes.py`。

建议 TODO：

1. 建 `AUTH_CSRF_CONTRACT.md`
   - auth enabled/disabled 的行为。
   - public path 列表。
   - session cookie 签名和过期语义。
   - CSRF 对 browser unsafe request 的触发条件。
   - API client 兼容边界。

2. 抽 auth routes/middleware：
   - `api/auth.py` 保留 session/password store。
   - 新建 `api/auth_routes.py` 放 login/logout/status。
   - 新建 `api/csrf.py` 放 `_check_csrf()` / origin/referrer/token 校验。
   - `routes.py` 只注册 auth route 和调用 middleware。

3. 建 `FILE_ACCESS_CONTRACT.md`
   - 定义 workspace root、relative path、attachment fallback。
   - 写清 `safe_resolve_ws()` 和 `safe_resolve()` 的差异。
   - 决定 symlink-outside-workspace 是否允许 preview/edit/delete。
   - 写清 text read、raw read、save/create/delete/rename/path/reveal 的权限一致性。

4. 抽 file access 后端：
   - `api/file_routes.py`：HTTP parse/status/response。
   - `api/file_access_service.py`：workspace/session/path/mutation。
   - `api/file_response.py`：range、content-disposition、MIME、CSP sandbox。
   - `api/helpers.safe_resolve()` 只留通用 helper，workspace 行为统一走 service。

5. 补 file access 行为测试：
   - symlink inside workspace、symlink outside workspace、symlink to blocked system path。
   - list/read/raw/save/delete 对 symlink 的 contract 一致性。
   - HTML inline 只能 `inline=1` + CSP sandbox。
   - SVG 永远 attachment。
   - attachment fallback 只能同 session。

6. 建 `MEDIA_ACCESS_CONTRACT.md`
   - 明确 `MEDIA:` token 是 agent output local artifact。
   - 说明 allowed roots：Hermes home、`/tmp`、`~/.hermes`、last workspace、`MEDIA_ALLOWED_ROOTS`。
   - 写清它不是 workspace file browser。
   - 多用户化前必须改成 opaque media token 或 session-scoped artifact registry。

7. 抽 media 后端：
   - `api/media_routes.py`
   - `api/media_service.py`
   - `api/media_roots.py`
   - 复用 `api/file_response.py`。
   - route 层不再直接 resolve absolute path。

8. 修 workspace HTML open behavior：
   - `workspace.js openInBrowser()` 对 HTML 增加 `inline=1`。
   - 保持 `target` 新 tab + server CSP sandbox。
   - 增加行为测试，不只查字符串。

9. 抽 upload 后端：
   - `api/upload_routes.py`
   - `api/upload_service.py`
   - `api/archive_extract.py`
   - multipart parser 单独隔离，后续替换 streaming parser。

10. 补 upload/archive 测试：
    - oversize Content-Length。
    - multipart malformed boundary。
    - zip-slip/tar-slip。
    - extraction bomb。
    - partial extraction cleanup。
    - session attachment dir traversal。

11. 抽前端 workspace file client：
    - `workspace-file-client.js`：list/read/raw/save/create/delete/rename/path/reveal/upload。
    - `workspace-preview-controller.js`：image/audio/video/pdf/html/markdown/text preview。
    - `workspace-tree-view.js`：tree render/context menu。
    - `workspace.js` 降成 facade。

12. 建 `ROLLBACK_CONTRACT.md`
    - checkpoint id 格式。
    - workspace hash 规则。
    - profile active Hermes home。
    - workspace-list scoped 权限。
    - restore 不删除新增文件的语义。

13. 抽 rollback 后端：
    - `api/rollback_routes.py`
    - `api/rollback_service.py`
    - `api/checkpoint_store.py`
    - 保留 checkpoint repo trusted assumption，并在 contract 写清。

14. 补 rollback 测试：
    - checkpoint id traversal。
    - workspace 不在 allowlist。
    - checkpoint repo missing/corrupt。
    - restore only tracked files。
    - binary/text diff fallback。

15. 抽 worktree routes：
    - `api/worktree_routes.py`
    - `api/worktrees.py` 保留 service/runtime。
    - route 层只做 session id/body validation。

16. 补 worktree lifecycle 测试：
    - session id 格式和真实 session id 兼容。
    - active stream/terminal lock。
    - dirty/untracked/ahead gate。
    - force warnings。
    - worktree prune failure degrade。

17. 替换静态字符串测试：
    - 当前很多 tests 查源码 substring。
    - 拆模块前先改成 import/service 行为测试或轻量 DOM 测试。
    - 对必须保留的源码扫描，改扫 route manifest/exported API，而不是扫 `routes.py` 巨石。

18. TS 化边界：
    - 不把 `workspace.js` 整体改 TS。
    - 先 TS 化纯 payload/model：
      - file entry。
      - file preview kind。
      - upload result。
      - media artifact ref。
      - rollback checkpoint/diff。
      - worktree status/remove result。

本轮验证：

- JS 语法检查通过：
  - `static/workspace.js`
  - `static/ui.js`
  - `static/messages.js`
  - `static/boot.js`
  - `static/sessions.js`
- Python 编译检查通过：
  - `api/auth.py`
  - `api/upload.py`
  - `api/rollback.py`
  - `api/workspace.py`
  - `api/worktrees.py`
  - `api/routes.py`
- auth/file/upload/media/workspace/worktree/rollback 聚焦测试：
  - 303 collected。
  - 303 passed。

## 10.24. 补工程门禁 / 测试契约 / 前端全局入口治理

这一组应该排在大规模拆分前面。当前根 verify 能绿，但无法证明 WebUI 前端入口和旧面板契约健康。

现状判断：

- `pnpm-workspace.yaml` 只包含 `packages/*`。
- `pnpm -r check` 实际只检查：
  - `packages/hermes-client`
  - `packages/space-runtime`
- `scripts/verify.mjs` 只检查少数 WebUI 文件：
  - py_compile：`products.py`、`product_context.py`、`routes.py`、`updates.py`
  - node check：`product-runtime.js`、`product-store.js`、`product-shell-runtime.js`、`workspace.js`
- `apps/webui/tests` 有约 550 个 `test_*.py`，但根 CI 不跑。
- `index.html` 仍大量依赖 inline global handlers。
- 当前明确缺失的 inline handlers：
  - `toggleProfileDropdown()`
  - `toggleComposerWsDropdown()`
  - `clearConversation()`
- 当前旧测试与代码分叉：
  - `loadCrons()` 缺失。
  - `loadSkills()` 缺失。
  - `switchToProfile()` 缺失。
  - `renderWorkspaceDropdownInto()` 缺失。
  - profile/workspace help card 缺失。
  - `_positionComposerWsDropdown()` 缺失。

建议 TODO：

1. 建 `WEBUI_VERIFY_CONTRACT.md`
   - 定义 PR 必跑、local quick check、nightly/full check。
   - 区分 syntax、unit、static contract、browser smoke。
   - 写清哪些测试是旧契约待迁移，不让它们长期处在“知道会失败但无人处理”的状态。

2. 新增 `scripts/verify-webui.mjs`
   - `node --check apps/webui/static/*.js`。
   - `python -m py_compile apps/webui/api/*.py`。
   - 可配置 quick pytest list。
   - 输出清晰 PASS/FAIL，而不是需要人记命令。

3. 把 `scripts/verify.mjs` 接入 WebUI quick verify
   - 最少接入 syntax + inline handler scanner。
   - pytest 可以先接一组 smoke，避免 CI 时间突然膨胀。
   - full pytest 先放本地命令或 nightly。

4. 新增 inline handler scanner
   - 扫 `apps/webui/static/index.html`。
   - 提取 `onclick/oninput/onchange/onkeydown/...`。
   - 检查函数存在于当前 loaded scripts。
   - 对 `if(S.session)loadDir(...)` 这类表达式要跳过 keyword，提取真实调用。
   - 先让它捕获：
     - `toggleProfileDropdown`
     - `toggleComposerWsDropdown`
     - `clearConversation`

5. 建 `FRONTEND_GLOBALS_CONTRACT.md`
   - 当前阶段明确哪些函数允许被 HTML inline 调用。
   - 每个 global 标注 owner file。
   - 新增 global 必须加到 manifest，防止散落。

6. 建 script load manifest
   - 从 `index.html` 生成或维护 `static/script-manifest.json`。
   - 记录 script 顺序和每个脚本提供的 globals。
   - 后续拆模块时让测试看 manifest，而不是猜 `index.html` 字符串。

7. 决定 profile dropdown 去留
   - 如果保留：
     - 恢复 `toggleProfileDropdown()`。
     - 恢复/重写 `switchToProfile()`。
     - 保留 spinner、optimistic update、parallel fetch、active/pending session 语义。
   - 如果移除：
     - 删除 `profileChip` inline handler 和 dropdown DOM/CSS。
     - 删除或改写 profile switch 旧测试。

8. 决定 workspace dropdown 去留
   - 如果保留：
     - 恢复 `toggleComposerWsDropdown()`。
     - 恢复 `renderWorkspaceDropdownInto()`。
     - 恢复 `_positionComposerWsDropdown()`。
     - 覆盖 mobile action anchor。
   - 如果移除：
     - 删除 composer/mobile workspace action 的旧 handler。
     - 替换为 workspace panel 的明确入口。

9. 决定 settings conversation clear action 去留
   - 如果保留：
     - 恢复 `clearConversation()`。
     - 明确是否走 `/api/session/clear` 或现有 session mutation。
   - 如果移除：
     - 删除 `btnClearConvModal` 和旧测试。

10. 决定 cron/skills/memory legacy panel 去留
    - 当前测试还期待 `loadCrons()` / `loadSkills()` / `loadMemory()` 等旧函数。
    - 如果产品入口已经换到 plugins/settings/product shell，就删除旧测试和残留 DOM。
    - 如果还需要入口，恢复为新 controller，而不是把旧代码塞回 `panels.js`。

11. 加巨型文件体量守门
    - 建 `scripts/check-file-budgets.mjs`。
    - 先白名单当前大文件，但禁止继续增长：
      - `routes.py`
      - `ui.js`
      - `i18n.js`
      - `style.css`
      - `streaming.py`
      - `config.py`
      - `messages.js`
      - `sessions.js`
      - `panels.js`
    - 对新文件设合理上限，例如 800/1200/2000 行分级。

12. 将源码字符串测试迁移成契约测试
    - 旧 substring tests 先分三类：
      - still-valid behavior。
      - stale UI residue。
      - implementation-position assertion。
    - still-valid 改成 DOM/service 行为测试。
    - stale residue 删除或改写。
    - implementation-position assertion 改查 manifest/exported API。

本轮验证：

- `node scripts/verify.mjs` 通过。
- `pnpm -r check` 通过。
- `tests/test_sprint8.py`：
  - 13 passed。
  - 1 failed：`panels.js` 不包含 `clearConversation`。
- profile/workspace/dropdown/help 聚焦测试：
  - 29 collected。
  - 13 passed。
  - 16 failed。
- mobile workspace dropdown 单测：
  - failed：`_positionComposerWsDropdown()` 缺失。

## 10.25. 拆 session / state.db / run journal / recovery 数据层

这一组是核心 TODO。它解决的不是“文件太长难看”，而是 session 数据事实源、只读导入会话、恢复链路和前端 sidebar 行为没有清晰边界的问题。

现状判断：

- `api/models.py` 已经不是 model 文件：
  - session JSON store。
  - `_index.json` 读写。
  - metadata-only load。
  - LRU cache。
  - sidebar 列表投影。
  - CLI/Claude Code/messaging session import。
  - project persistence。
  - state.db/recovery glue。
- `api/session_recovery.py` 和 `api/run_journal.py` 质量较好：
  - 有 message count audit。
  - 有 `.json.bak` 恢复。
  - 有 state.db sidecar materialize。
  - 有 append-only run journal。
  - 不应该重写，应该保留行为后拆边界。
- `static/sessions.js` 已经不是单纯 sidebar：
  - list cache。
  - virtual rendering。
  - content/title search。
  - lineage collapse。
  - gateway SSE refresh。
  - CLI session import。
  - rename/delete/archive/project/read-only guard。
- 当前 read-only guard 行为基本存在，但测试还在找旧英文文案和旧源码字符串。

建议 TODO：

1. 建 `SESSION_STORAGE_CONTRACT.md`
   - session id 格式。
   - session JSON schema。
   - metadata-only session 的语义。
   - 什么情况下 session 必须落盘。
   - `Session.save()` 的禁止条件。
   - message count 变短时 `.json.bak` 的触发条件。
   - atomic write / fsync / replace 约定。

2. 建 `SESSION_INDEX_CONTRACT.md`
   - `_index.json` 是性能索引，不是唯一事实源。
   - O(1) update 和 full rebuild 的触发条件。
   - corrupt index 如何降级。
   - stale tmp 如何清理。
   - index 字段和 sidebar 字段的关系。

3. 建 `READ_ONLY_IMPORTED_SESSION_CONTRACT.md`
   - 哪些 source 是 read-only。
   - WebUI 允许查看哪些内容。
   - 禁止哪些 mutation：
     - rename。
     - archive。
     - delete。
     - clear/truncate。
     - send message。
     - duplicate 是否允许要明确。
   - 后端 API 和前端 UI 都必须有 guard。
   - 文案测试不要绑定具体语言字符串，改查行为。

4. 建 `AGENT_SESSION_PROJECTION_CONTRACT.md`
   - state.db row 如何变成 sidebar session。
   - raw_source / source_tag / session_source 归一化规则。
   - CLI、Claude Code、messaging 的可见性策略。
   - compressed chain / close continuation 规则。
   - lineage metadata 字段。

5. 建 `SESSION_RECOVERY_CONTRACT.md`
   - live JSON vs `.json.bak` 的优先级。
   - orphan backup 何时可恢复。
   - state.db row 缺 JSON sidecar 时怎么 materialize。
   - unsafe repair 条件。
   - repair_safe 能修什么、不能修什么。
   - workspace 为空时不能隐式解析到 cwd。

6. 建 `RUN_JOURNAL_CONTRACT.md`
   - journal 路径结构。
   - session/run id 正则。
   - event schema。
   - fsync 策略。
   - stale interrupted event 合成规则。
   - summary 读取规则。

7. 抽后端 `api/session_store.py`
   - 放 `Session` 的核心持久化。
   - 放 `get_session()` / `new_session()` 的 store 逻辑。
   - 不放 sidebar、CLI import、project、route response。
   - 保留 metadata-only save guard。

8. 抽后端 `api/session_index.py`
   - 放 `_write_session_index()`。
   - 放 full rebuild。
   - 放 index load/corrupt fallback。
   - 加单测覆盖 O(1) update、rebuild、tmp cleanup。

9. 抽后端 `api/session_sidebar.py`
   - 放 `all_sessions()` 里的 sidebar projection。
   - 只返回 UI list 需要的 metadata。
   - 不负责 session mutation。
   - 明确 profile scope、archived、cron hidden、snapshots。

10. 抽后端 `api/session_read.py`
    - 放 `/api/session` 的读逻辑。
    - 支持 metadata-only、paging、run journal status、CLI metadata merge。
    - route 层只解析 query/body。

11. 抽后端 `api/session_mutations.py`
    - 承接 rename、pin、archive、clear、truncate、duplicate、branch。
    - 统一调用 `_ensure_full_session_before_mutation()`。
    - 所有 mutation 先过 read-only guard。
    - 每个 mutation 单测覆盖 metadata-only stub 不可 save。

12. 扩充现有 `api/session_ops.py`
    - 保留 retry/undo。
    - 把可复用锁逻辑和 truncate/context reset 放进去。
    - 避免 mutation 逻辑继续散在 `routes.py`。

13. 抽后端 `api/agent_session_projection.py`
    - 从 `agent_sessions.py` 迁出纯投影逻辑。
    - 保留 current behavior。
    - 单测覆盖 CLI/messaging/read-only/source label/lineage。

14. 抽后端 `api/cli_session_bridge.py`
    - 放 CLI session import。
    - 放 Claude Code session import。
    - 放 state.db lookup/cache。
    - 明确什么时候创建 WebUI sidecar、什么时候只读展示。

15. 抽后端 `api/session_recovery_routes.py`
    - HTTP route 从 `routes.py` 移出。
    - `session_recovery.py` 保持 service。
    - route 只做 status/body/response。

16. 抽后端 `api/run_journal_routes.py`
    - journal service 不动。
    - route 从 `routes.py` 移出。
    - 加 API 行为测试，而不是查 `routes.py` 字符串。

17. 抽后端 `api/project_store.py` / `api/project_routes.py`
    - 当前 project persistence 混在 session 相关文件里。
    - 项目颜色、项目列表、session project_id 关联应独立。

18. 建 route manifest / route registry
    - 每个 route 文件声明 path/method/handler。
    - `routes.py` 降成 dispatcher。
    - 旧源码字符串测试改查 manifest。

19. 修 state.db recovery workspace 语义
    - 如果 state.db row workspace 为空，不要让 `Path('').resolve()` 变成 cwd。
    - 明确使用 trusted default workspace、unknown workspace，或拒绝 materialize。
    - 补回归测试。

20. 迁移 read-only UI 测试
    - 不再查 `Read-only imported sessions cannot be renamed` 这种固定英文字符串。
    - 改成：
      - read-only row 不渲染 action menu。
      - double click rename 不进入 input。
      - send message 被前端 guard。
      - rename/archive/delete API 返回 400。

21. 抽前端 `session-client.js`
    - 包 `/api/session`、`/api/sessions`、rename、pin、archive、delete、duplicate、branch、import_cli。
    - 不直接操作 DOM。

22. 抽前端 `session-store.js`
    - 放 `_allSessions`、active sid、selected sessions、render cache。
    - 提供纯状态更新函数。
    - 后续可 TS 化。

23. 抽前端 `session-title-model.js`
    - 统一 `_sessionDisplayTitle()`、assistant display title、product shell title fallback。
    - 明确 system prompt title 不可见。
    - 修旧测试对 `const rawTitle=...` 的源码绑定。

24. 抽前端 `session-sidebar-view.js`
    - 负责 row DOM、virtual spacer、timestamp、tags、badges。
    - 不做 API。
    - 不做 gateway。

25. 抽前端 `session-sidebar-actions.js`
    - rename/action menu/delete/archive/pin/duplicate。
    - read-only guard 在这里和 client 两侧都存在。

26. 抽前端 `session-lineage-view.js`
    - child sessions。
    - lineage segments。
    - lineage report cache/fetch。
    - collapse/expand state。

27. 抽前端 `session-gateway-sync.js`
    - gateway SSE。
    - active CLI session refresh。
    - stale active session import。
    - 不直接渲染 DOM，只通知 store/view。

28. 抽前端 `session-search.js`
    - title search。
    - content search。
    - search mode state。
    - search 结果和 virtual list 解耦。

29. 抽前端 `session-project-binding.js`
    - project dot。
    - project selection。
    - session project update。
    - 不留在 sidebar 主文件里。

30. 拆完后保留 `sessions.js` facade
    - 初期继续给 `index.html` 提供原有 global。
    - 内部转调新模块。
    - 等 inline handler 和 script manifest 治理完成后，再去掉 facade。

31. 给 session 数据层补一组 quick tests
    - metadata-only session 保存必须失败。
    - session index corrupt 能 rebuild。
    - `.json.bak` message count 大时能恢复。
    - state.db 缺 sidecar 能安全 materialize。
    - read-only imported session mutation 全拒绝。
    - run journal stale interrupted event 可读。
    - gateway watcher 只在 hash 变化时通知。

32. 给 frontend session 补轻量 DOM tests
    - read-only row。
    - rename lifecycle。
    - action menu first item。
    - lineage expand/collapse。
    - CLI import refresh 不覆盖当前 active WebUI turn。
    - title search 使用显示标题。

33. TS 化顺序
    - 不把 `sessions.js` 原地改 TS。
    - 只迁纯逻辑：
      - session payload type。
      - sidebar row type。
      - read-only/source enum。
      - lineage metadata type。
      - run journal event type。
      - session title model。
    - DOM controller 和 browser global 等拆稳定后再考虑 TS。

34. 完成标准
    - `routes.py` 不再直接写 session mutation 细节。
    - `models.py` 不再承担 sidebar/CLI/project/recovery route 职责。
    - `sessions.js` 不再同时包含 store、view、gateway、actions、lineage、project。
    - read-only、metadata-only、recovery、journal 都有独立 contract 和测试。
    - 新增 session 行为时能判断应该改哪个模块，而不是搜索 10000 行。

本轮验证：

- Python 编译检查通过：
  - `api/models.py`
  - `api/agent_sessions.py`
  - `api/session_recovery.py`
  - `api/run_journal.py`
  - `api/turn_journal.py`
  - `api/gateway_watcher.py`
  - `api/session_ops.py`
  - `api/routes.py`
- session / state.db / gateway / recovery / journal 聚焦测试：
  - 216 collected。
  - 214 passed。
  - 2 failed。
- 两个失败都偏“旧源码字符串/旧文案契约”：
  - `test_sidebar_search_and_rows_use_read_only_display_title`
  - `test_read_only_source_badge_ui_guards_are_present`

## 11. 建议执行顺序

1. 加 WebUI quick verify、inline handler scanner、体量守门和巨型文件维护说明。
2. 建 product DOM contract 和脚本顺序测试。
3. 建 product CSS duplicate audit 和 body dataset 状态表。
4. 明确前端 boot/product hydrate/session restore 阶段。
5. 拆 `ui.js` 的 busy/queue/composer 最小边界。
6. 做 product CSS 分区，不改视觉。
7. 修 access preset 的产品工具语义。
8. 修真实产品和 `knead-product` 契约不一致处。
9. 清理 PPT Designer demo 默认覆盖。
10. 定义 chat turn contract，把 hidden instruction 改成 `internal_context`。
11. 定义 queued turn request contract，修 queued product/internal context 恢复。
12. 定义 turn journal visible content contract。
13. 补 frontend JS 行为测试入口，先覆盖 queue/request、productize marker 和 bridge SDK。
14. 定义 product preview asset serving contract。
15. 修 bridge reply shape、download URL 校验。
16. 梳理 product draft 生命周期，并保存 productize marker metadata。
17. 补 `api/products.py` preview/snapshot/rollback/manifest 测试。
18. 修 product registry atomic write 和 create tools normalization。
19. 拆 `api/products.py` 产品服务模块。
20. 修 `product_context.py` status drift / reconcile 语义，并拆 prompt builder。
21. 建 `PRODUCT_SCHEMA.md`。
22. 抽 `product-model.js`。
23. 抽 `product-adapter.js`。
24. 抽 `product-context-client.js`。
25. 抽 `product-session-owner.js`。
26. 抽 `product-shell-state.js`。
27. 抽 `product-boot-coordinator.js`。
28. 抽 `product-bridge-host.js`。
29. 抽 `product-preview-controller.js`。
30. 合并或改名 `product-evolution.js`。
31. 抽 `productize-suggestion.js`。
32. 拆 product shell view。
33. 抽 `ui.js` message renderer / workspace tree。
34. 建 route registry / route manifest。
35. 抽低耦合 static/file/media routes 和统一 response helper。
36. 抽 `routes_products.py`，同步修 product preview matcher/security headers。
37. 定义 session storage/index/read-only/agent projection/recovery/run journal contracts。
38. 抽 `api/session_store.py`。
39. 抽 `api/session_index.py`。
40. 抽 `api/session_sidebar.py`。
41. 抽 `api/session_read.py`。
42. 抽 `api/session_mutations.py`，扩充 `api/session_ops.py`。
43. 抽 `api/agent_session_projection.py` 和 `api/cli_session_bridge.py`。
44. 抽 `api/session_recovery_routes.py` 和 `api/run_journal_routes.py`。
45. 抽 `api/project_store.py` / `api/project_routes.py`。
46. 修 state.db recovery 空 workspace 语义。
47. 迁移 read-only/imported session 旧源码字符串测试。
48. 抽前端 `session-client.js` / `session-store.js` / `session-title-model.js`。
49. 抽前端 sidebar view/actions/lineage/gateway/search/project 模块。
50. 抽前端 `session-drafts.js`。
51. 抽前端 `message-pager.js`。
52. 抽前端 `session-loader.js`。
53. 建 `command-request-builder.js`。
54. 建 `MODEL_PROVIDER_CONTRACT.md`。
55. 抽 `api/config_paths.py` / `api/config_store.py`。
56. 抽 `api/provider_identity.py`。
57. 抽 `api/model_catalog.py`，让 picker/provider card 共用 catalog。
58. 抽 `api/model_resolver.py`，把 resolver 改成规则链 + fixtures。
59. 抽 `api/model_cache.py`。
60. 抽 `api/provider_credentials.py`，移除对 streaming lock 的依赖。
61. 抽 `api/provider_usage.py` / provider cost history。
62. 抽 `api/settings_store.py`。
63. 抽前端 settings payload/state/autosave/panel。
64. 抽前端 provider panel/card/quota view。
65. 抽前端 system/checkpoint panels。
66. 修复或移除缺失的 profile chip handler：`toggleProfileDropdown()` / `switchToProfile()`。
67. 抽前端 `boot-coordinator.js`。
68. 建 `AUTH_CSRF_CONTRACT.md` / `FILE_ACCESS_CONTRACT.md` / `MEDIA_ACCESS_CONTRACT.md`。
69. 抽 auth routes 和 CSRF middleware。
70. 抽 file access routes/service/response helper。
71. 抽 media routes/service/allowed-roots。
72. 抽 upload routes/service/archive extract。
73. 修 workspace HTML `openInBrowser()` inline 行为，并补测试。
74. 抽前端 workspace file client / preview controller / tree view。
75. 建 `ROLLBACK_CONTRACT.md`，抽 rollback routes/service/checkpoint store。
76. 抽 worktree routes，并补 lifecycle tests。
77. 抽前端 voice input / voice mode / appearance client。
78. 收口 `loadCrons()` / profiles / workspaces 旧面板残留和陈旧静态测试。
79. 抽后端 profile paths/env/cron/service。
80. 抽后端 workspace store/security/files。
81. 抽后端 update check/summary/apply。
82. 抽 onboarding status/setup/probe/oauth。
83. 增加 inline global handler 扫描测试，防止 HTML 指向缺失函数。
84. 建 `RUNTIME_CAPABILITIES_CONTRACT.md` / `TERMINAL_CONTRACT.md`。
85. 抽后端 terminal routes/service，并补 terminal owner/reaper tests。
86. 抽前端 terminal client/controller/view。
87. 抽 approval/clarify/YOLO 前端 client/store/card。
88. 抽 approval/clarify 后端 routes/runtime control。
89. 明确 YOLO contract，补 hardline 不可绕过测试。
90. 收口 MCP panel：read-only 就删死代码，editable 就补真正路由和测试。
91. 抽 MCP inventory/config service 和 MCP panel。
92. 抽 profile-aware skills service。
93. 决定 skills UI 去留，修或删旧 skill detail/collapse 测试。
94. 收口 cron 前端 `loadCrons()` 残留。
95. 抽 cron routes/profile/run/output service。
96. 抽 SSE/approval/clarify/terminal stream routes。
97. 建 i18n audit / translation contract。
98. 拆 `i18n.js` locale assets，保留 runtime API。
99. 修 i18n 静态字符串测试漂移。
100. 抽 `streaming.py` 的 stream turn context / lifecycle cleanup。
101. 抽 streaming product turn finalizer / product prompt builder。
102. 抽 streaming callbacks / metering / live tool state。
103. 抽 streaming agent runtime builder / agent cache。
104. 抽 streaming persistence / result merge / pending user recovery。
105. 抽 streaming provider errors / credential self-heal。
106. 抽 streaming compression / title / goal hooks。
107. 抽 streaming cancel / steer，并修对应测试契约。
108. 引入 TS，只迁纯逻辑。
109. TS 化 bridge 协议。
110. TS 化 session/read-only/lineage/run-journal payload 类型。
111. TS 化 file/media/upload/rollback/worktree payload 类型。
112. TS 化 runtime capability / terminal / approval / MCP / skills payload 类型。
113. 分批命名统一。
114. 设定新代码不得进入巨型文件的工程规则。

## 12. 不建议做的事

- 不建议一次性 React/Vue 重写。
- 不建议一次性 TS 重写。
- 不建议先改所有命名。
- 不建议先动 `ui.js` 大主体。
- 不建议在没有浏览器冒烟前大规模移动 `messages.js` SSE 逻辑。
- 不建议在产品模型还继续变时重构所有文件。

## 13. 判断标准

完成这轮工程治理后，项目应该达到：

- 找一个产品行为时，不需要同时读 5 个巨型文件。
- 新增产品 layout 或 toolset 时，有明确 model/adapter/context/view 落点。
- 后端新增 API 时，不再改 10000 行 `routes.py`。
- 前端新增产品 UI 行为时，不再改 8000 行 `ui.js`。
- TS 类型保护的是产品模型和协议边界，而不是包装旧混乱结构。

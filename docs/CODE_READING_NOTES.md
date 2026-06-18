# Code Reading Notes

更新日期：2026-06-18

本文是逐行阅读笔记，不替代 `docs/PRODUCT_MODEL_CONTRACT.md` 和 `docs/ENGINEERING_HEALTH_TODO.md`。
目标是把真实代码链路读清楚，方便后续拆分和重构。

## 本轮已逐行读过的范围

- `apps/webui/static/index.html` 的脚本加载顺序。
- `apps/webui/static/product-store.js`
- `apps/webui/static/product-runtime.js`
- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/messages.js` 中产品相关、发送、完成、错误路径。
- `apps/webui/api/product_context.py`
- `apps/webui/api/products.py`
- `apps/webui/api/routes.py` 中 session/product/chat 关键分支。
- `apps/webui/static/ui.js` 中产品相关关键区段：access preset、suggest marker、status card、renderMessages、topbar。
- `apps/webui/static/sessions.js` 中产品会话创建、会话恢复、session list cache 关键区段。
- `apps/webui/api/streaming.py` 中 product prompt 注入、product turn finalize、done/error 路径关键区段。
- `apps/webui/api/models.py` 中 Session product 字段、save、compact 关键区段。
- `apps/webui/static/product-bridge-sdk.js`
- `apps/webui/static/workspace.js` 中文件树、文件预览、workspace API 关键区段。
- `products/ai-otome/*` 的产品 app 主链路。
- `products/ppt-designer/*` 的产品 app 主链路和 `ppt-skill/SKILL.md` 概览。
- `products/general/*` 的 chat_only 边界样例。
- `apps/webui/tests/test_product_scope_lines.py`
- `apps/webui/tests/test_product_ui_status.py`

暂未全量逐行读完：

- `apps/webui/static/ui.js` 全量 7961 行。产品链路关键区段已读，但非产品 UI、模型菜单、文件树、设置等仍未全量审完。
- `apps/webui/static/sessions.js` 全量 3848 行。产品会话链路已读，但批量操作、handoff、项目侧栏等仍未全量审完。
- `apps/webui/api/streaming.py` 全量 5534 行。产品注入/完成链路已读，但 provider self-heal、压缩、title、goal 等大块仍未全量审完。
- `apps/webui/api/models.py` 全量 2477 行。Session product 字段链路已读，但 run journal repair、index/search 等仍未全量审完。

## 1. 前端加载顺序

文件：`apps/webui/static/index.html`

关键行段：

- 1200-1214：所有静态脚本按 `defer` 顺序加载。
- 加载顺序是 `ui.js -> workspace.js -> terminal.js -> sessions.js -> commands.js -> messages.js -> product-store.js -> product-shell-runtime.js -> product-runtime.js -> product-evolution.js -> panels.js -> onboarding.js -> boot.js`。

判断：

- 这是旧式全局脚本依赖图，不是 ES module。
- 后面的文件依赖前面文件挂出的全局函数和全局状态。
- 重构时不能直接把单个文件改成独立 module，否则会破坏加载期依赖。
- 正确路线是先做兼容层：新模块导出到 `window.LegacyName`，旧调用方逐步迁移。

## 2. `product-store.js`

文件：`apps/webui/static/product-store.js`

责任概览：

- 产品 capability/toolset 配置。
- 后端 product 到前端 AI object 的 adapter。
- builtin/custom product 合并。
- 本地产品 UI status 同步。
- 产品能力设置弹窗。
- 给其他文件暴露少量 `window.*` API。

逐段笔记：

- 1-24：定义技能、工具和 alias。这里是前端一份 toolset 词表，后端 `api/products.py` 也有一份，存在双份事实。
- 26-51：能力数组去重和 alias 归一化。纯逻辑，适合最先抽到 `product-model.js` / TS。
- 57-82：`_assistantDefaultCapabilities` 仍保留，但新建产品现在默认 chat_only + 空能力，再由 init 决定形态。这个函数可能已经是旧策略残留。
- 84-149：layout / canvas 判断。这里是核心产品模型逻辑，但函数名仍是 `_assistant*`。
- 108-128：`_assistantHasGeneratedProductCanvas` 会读 `_activeProductPreview`。这让 model 判断依赖 UI runtime 全局状态，不够纯。
- 152-170：builtin product copy 覆盖。前端会覆盖后端 builtin 文案，属于展示层补丁。
- 177-218：`_productToCustomAssistant` 是核心 adapter。它同时做字段翻译、默认 starter kit、canvas availability 推导。
- 249-280：把后端 builtin product 合并进 `AI_OBJECTS`。这里直接 mutation 全局对象。
- 292-313：把后端 product 应用到本地。内部会 render list 和 sync meta，说明 adapter/store 和 view 混在一起。
- 315-370：本地/后端同步 product ui status。它同时改 target、`AI_OBJECTS`、`_backendProductAssistants`、`_activeProductPreview`、DOM copy。
- 372-400：hydrate 后端 products。这里是前端产品事实源同步入口。
- 402-409：解析当前产品对象，依赖 `_assistantKey`、`_activeProductPreview`。
- 411-457：能力选项渲染，已经进入 DOM view 责任。
- 458-539：产品能力弹窗 open/save。这里做 DOM、收集表单、调用 API、同步 store。
- 541-555：暴露 `openCurrentProductCapabilities`、`currentAssistantProductToolsets`、`currentAssistantProductSessionDefaults`。

结构判断：

- 文件名叫 store，但实际包含 model、adapter、store、view、API action 四层。
- 最适合第一批拆：纯函数和 adapter 很明确。
- 不建议先改 UI 弹窗，先抽 1-218 的纯逻辑。

## 3. `product-runtime.js`

文件：`apps/webui/static/product-runtime.js`

责任概览：

- 当前产品 workspace/preview URL。
- product scope 生成。
- iframe bridge host。
- 初始 product shape task。
- preview 状态和轮询。

逐段笔记：

- 1-44：preview URL、是否需要 initial generation。核心判断依赖 `_assistantCanShowProductCanvas` 和 `_activeProductPreview`。
- 46-58：生成 product init 的任务标题和可见用户消息。
- 60-68：判断当前 session 是否绑定同一个 product。
- 70-111：`currentAssistantProductContextForMessage` 是前端 scope 主入口。它读取 pending scope、adjust mode、UI generation 状态，产出后端结构化字段。
- 74-80：pending scope/intent 是 `window._nextAiPendingProductScope` 和 `window._nextAiPendingProductIntent`，属于隐式全局状态。
- 81-100：用/调开关明确决定 scope，这是产品模型里最重要的修复点。
- 113-227：canvas state bridge，负责 localStorage get/set/remove/clear。
- 127-147：state scope 支持 `product` 和 `session:<id>`，默认 session draft。
- 177-179：bridge state message 校验 event.source，安全边界比 origin 更适合 sandbox iframe。
- 229-247：canvas 请求 pending map。
- 249-273：从 canvas context 生成隐藏指令，注入角色/历史。
- 275-330：canvas 发消息到宿主 chat。它会设置 pending product scope/intent/hidden instruction，然后填入 composer 并调用 `send()`。
- 332-367：Agent reply/error 回传到 iframe。
- 369-403：监听 product iframe postMessage。这里还包含 download 代理。
- 405-411：把 runtime API 挂到 window。
- 413-471：初始化/塑形产品。它创建 product-bound session，设置 pending scope，然后调用 `send()`。
- 424：无条件把 status 设为 `generating`，但新 product_init 已经可能是 chat-only/config-only，这个状态语义需要拆。
- 476-531：preview timestamp、polling、hide active preview。
- 533-598：preview empty/generating/failed UI 文案。目前仍大量使用“产品界面”。
- 600-650：手动请求生成产品界面。
- 654-670：读取当前 preview runtime state，供 messages.js 完成后生成状态卡。
- 672-784：刷新 product preview，拉 `/api/products/<id>/status`，同步本地对象，设置 iframe src，启动/停止 polling。

结构判断：

- 这个文件不是单一 runtime，而是 scope client + bridge host + preview controller + init action。
- `send()` 被作为底层传输 API 使用，导致 canvas bridge 和 chat composer 强耦合。
- `_activeProductPreview` 是跨文件裸全局，需要封装。

## 4. `product-shell-runtime.js`

文件：`apps/webui/static/product-shell-runtime.js`

责任概览：

- 定义 builtin AI objects。
- 产品列表渲染。
- 创建/删除/重命名产品。
- session 和 product 的归属关系。
- product home、task header、preview chip、adjust/chat panel 状态。
- split pane resizer。

逐段笔记：

- 1-7：核心全局变量：`_activeProductPreview`、`_lastTaskAssistantKind`、`_backendProductAssistants`。
- 8-54：前端 builtin AI objects。后端 `BUILTIN_PRODUCTS` 也有一份，存在双份事实和启动期覆盖。
- 56-91：preview menu DOM 状态和全局点击/ESC 处理。
- 93-133：session-assistant assignment 和 backend product assistants 的本地读写。现在 `_customAssistantsRead` 实际只读内存数组，不再读 localStorage。
- 139-201：从 prompt 生成标题的规则。偏产品启发式，不应长期留在 shell view。
- 204-244：注册 custom assistant 到 `AI_OBJECTS`。
- 246-317：查找、去重、删除 custom assistant。
- 319-357：列表 meta 文案，比如“生成中/可重试/界面/待生成”。
- 359-407：渲染左侧 AI list，直接操作 DOM。
- 409-543：从 prompt 生成 draft。现在默认 `productType=custom`、`uiMode=chat_only`、`productLayout=chat_only`、空 tools/skills。
- 545-650：`confirmAssistantCreatePreview` 仍存在，但创建路径已经不再调用它，疑似旧 UI 残留。
- 652-684：draft -> product payload，调用 `/api/products/create`。
- 687-707：保存 product-backed assistant。
- 709-747：创建产品后异步启动 initial shape。
- 753-822：重命名和删除产品。
- 824-1001：当前 assistant key/object、session 到 product 的归属和过滤。这一段应该独立成 `product-session-assignment`。
- 1003-1043：avatar/icon 显示。
- 1045-1166：product home UI 渲染。
- 1168-1211：选择产品，更新当前全局状态、DOM、suggestions、preview。
- 1213-1267：打开产品主页，清空当前 session view。
- 1269-1481：任务标题规整、弱标题过滤、异步补 title。这是 session/title 责任。
- 1483-1558：任务是否活跃、任务进度条。
- 1560-1639：preview 顶栏 copy 和按钮。
- 1641-1668：header 打开/关闭 preview。
- 1670-1728：product layout、adjust mode、chat panel mode。
- 1735-1863：task header status/preview chip/action。
- 1865-1913：sidebar intro/directory。
- 1915-2010：`syncAssistantTaskUi` 是大状态机，统一刷新 body dataset、home、message shell、preview、sidebar、header。
- 2012-2037：关闭 preview / 外部打开 preview。
- 2039-2051：初始化入口：清 legacy localStorage、render list、hydrate products、sync UI。
- 2053-2086：chat/canvas splitter 交互。

结构判断：

- 这是前端产品 shell 的总聚合文件。内部确实有层次，但没有文件边界。
- 最危险的不是某段写错，而是 `syncAssistantTaskUi` 是全局状态协调中心，任何 layout 改动都会碰它。
- 应该先把 session assignment、title、view、preview chip 分出去。

## 5. `messages.js` 产品相关路径

文件：`apps/webui/static/messages.js`

已读行段：

- 55-205：product status card 和失败标记。
- 385-742：`send()` 主路径中 product context 注入。
- 1880-2010：stream done 后 product preview / bridge / status card。
- 2140-2177：stream app error 后 product failed 状态。

逐段笔记：

- 55-74：从 product context 提取 productId/title/scope，并写回当前 session。
- 76-118：product status card 文案已经从“产品界面”向“AI 准备/调整”迁移。
- 120-144：status card 是 transient assistant message。
- 146-168：把 provider/app error 映射成 product failure reason。
- 170-205：失败时调用 `_setProductUiStatus(..., failed, persist:true)` 并刷新 preview。
- 385-742：`send()` 是超大流程，负责并发队列、create product special case、busy mode、上传、session 创建、乐观渲染、`/api/chat/start`、SSE attach。
- 412-423：当当前 AI 是 `create` 时，普通发送变成 `createProductFromPrompt`。
- 592-657：取 `currentAssistantProductContextForMessage` 并把 product fields 展开进 `/api/chat/start` body。
- 650-657：`/api/chat/start` payload 中 product context 是直接 spread。
- 1931-1944：stream done 后把最后一条 assistant reply 回传给 canvas，同时 broadcast 到 active canvas。
- 1949-1950：如果 adjust mode 开着，直接 reload active preview。
- 1956-1977：done 后刷新 product preview，并根据 runtime state 追加 done/failed 状态卡。
- 2140-2177：stream error 后给 canvas error，同时把 product UI 标记 failed。

结构判断：

- `messages.js` 现在是 chat transport + stream renderer + product bridge completion + product status card 的混合体。
- product 相关代码应该先拆成 `messages/product-status-cards.js`，然后再拆 stream controller。
- `send()` 不适合一次性重构，必须先切旁路纯逻辑。

## 6. `product_context.py`

文件：`apps/webui/api/product_context.py`

责任概览：

- 后端 product scope/line 解析。
- build/use 工具集区分。
- workspace guard。
- 生成 product ephemeral prompt。

逐段笔记：

- 19：三个 scope：`product_usage`、`product_init`、`product_builder`。
- 21-26：builder 基础工具集固定为 skills/file/terminal/code_execution。
- 29-43：给 builder prompt 提供 product workspace 文件列表。
- 46-58：能力标签。
- 60-84：非显式 scope 的 fallback regex。
- 87-117：`infer_product_scope`。explicit 为真时完全信前端。
- 120-157：从已有 product session 恢复 product request body。build line 续聊保持 builder，use line 保持 usage。
- 160-230：核心 `product_context_from_request`。读取 product，推 scope，校验 build workspace，计算 effective tools。
- 178-187：非显式且 UI 空/失败时会升成 init。
- 188-195：line = build/use，只有 build line 强校验 workspace 等于 product workspace。
- 198-208：build line = builder tools ∪ product tools；use line = product tools。
- 233-432：`product_ephemeral_prompt`。
- 261-287：三种 scope guidance。
- 261-270：product_init 可选择 chat-only/config-only 或 workspace UI。
- 310-372：build line prompt，强调 builder 不是 persona，会编辑 product workspace。
- 373-432：usage line prompt，强调 product files read-only；chat-only usage 可能追加 productize marker。

结构判断：

- 这是目前最清晰的产品核心模块。
- 主要问题不是体量，而是 `product_init` guidance 和 build identity 有一定语义张力。
- 后续可以把 prompt 文案拆成模板函数，但现在可读性尚可。

## 7. `products.py`

文件：`apps/webui/api/products.py`

责任概览：

- AI product registry。
- builtin products。
- product workspace seed。
- product.json manifest。
- ui_status 推导。
- snapshot/rollback。
- preview file 安全解析。

逐段笔记：

- 21：状态文件 `ai_products.json`。
- 24-37：项目根和 products dir discovery。
- 38-42：snapshot 文件限制。
- 43-109：builtin products。包含 General、PPT Designer、AI Otome。
- 110-117：后端 toolset alias。前端也有一份。
- 121-161：时间/id/toolsets 基础工具。
- 164-182：按 title/source/type 推默认 skills/tools。新前端创建产品会传空数组，所以这里默认能力可能被绕开。
- 185-241：version id 和 seed html。
- 244-260：读写 product registry。
- 262-327：normalize product，处理 id/kind/layout/ui_mode/status/canvas_label/skills/tools。
- 334-400：确保 builtin products 存在并写 seed files。
- 414-440：写 README、seed index、manifest。
- 443-464：写 `product.json`。
- 466-487：注册/移除 workspace。
- 489-499：判断 entry 是否 real generated。
- 520-580：`_resolve_ui_status` 是产品 UI 状态唯一推导函数，注释和规则很清楚。
- 583-595：list products，纯派生 status，不持久化。
- 598-607：get product。
- 610-642：create product，写 seed、注册 workspace、写 state。
- 645-694：update product，白名单字段，normalize，写 manifest/state。
- 697-728：delete product，builtin 跳过删除。
- 745-795：snapshot 文件收集，排除 versions/node_modules 等。
- 812-861：从 workspace 的 `product.json` 读取 agent 写回的 manifest patch。
- 864-920：snapshot product。
- 930-980：rollback product。
- 983-999：record product session，可把 ui_status 设为 generating 并写 generation_started_at。
- 1002-1007：seed entry 判断。
- 1010-1025：layout promotion：chat_center + real entry -> chat_left_canvas_right。
- `finalize_product_generation`：读取 manifest patch，推最终 ui_status。
- `reconcile_product_status`：显式持久化修复漂移。
- `product_file_status`：纯读不持久化。
- `preview_product_file`：preview file path 安全解析。

结构判断：

- 这个文件虽然 1182 行，但分段清楚，注释比较好。
- 它可以拆，但优先级低于前端巨型文件和 `routes.py`。
- 最值得先抽的是 builtin definitions/toolset aliases，避免前后端双份。

## 8. `routes.py` 产品关键路径

文件：`apps/webui/api/routes.py`

已读行段：

- 4290-4396：`/api/session/new`
- 4598-4627：`/api/session/toolsets`
- 5111-5167：product management POST routes。
- 7980-8025：`/api/chat/start` 产品上下文。
- 8142-8160：sync chat 产品上下文。

逐段笔记：

- 4290-4340：new session 基础参数、worktree、model/provider。
- 4341-4367：处理 enabled toolsets 和 product context。
- 4368-4379：创建 product session 时，如果 init/builder 且不是 chat_only，记录 ui_status=generating。
- 4598-4627：session toolsets override。`toolsets: null` 语义是清空 override。
- 5111-5167：product create/update/delete/finalize/snapshot/rollback 全都还是扁平 if 分支。
- 7980-7999：chat start 前恢复/解析 product body，必要时设置 session title。
- 7999-8006：init/builder 前 snapshot product。
- 8007-8014：chat start 时任何 init/builder 都记录 ui_status=generating。
- 8142-8160：sync chat 路径有一份类似 product context + snapshot 逻辑。

结构判断：

- product 逻辑在 `routes.py` 中重复出现在 session/new、chat/start、sync chat 三处。
- 应该先抽一个 `bind_product_context_to_session(...)` 或 route helper，再迁移到 `routes_products.py` / `routes_chat.py`。
- `/api/session/toolsets` 和产品默认 tools 的语义目前需要前端配合修正。

## 9. 测试

文件：

- `apps/webui/tests/test_product_scope_lines.py`
- `apps/webui/tests/test_product_ui_status.py`

判断：

- `test_product_scope_lines.py` 覆盖了 explicit scope、regex fallback、build/use line、workspace guard、chat-only prompt、builder strong toolset。
- `test_product_ui_status.py` 覆盖了 status 推导矩阵、layout promotion、file_status 纯读、reconcile 持久化、chat_only finalize。
- 产品后端核心测试是有的，而且写得比较聚焦。
- 缺口在前端纯逻辑：layout/toolset/context/adapter/access preset/bridge host 没有对应模块级测试。

## 10. 当前最清楚的拆分边界

优先拆出的纯逻辑：

- product layout/toolsets/capability normalization。
- product adapter：后端 product -> frontend product object。
- product context client：scope/pending intent/with context。
- access preset classification。

优先封装的全局状态：

- `_activeProductPreview`
- `window._nextAiPendingProductScope`
- `window._nextAiPendingProductIntent`
- `window._nextAiPendingHiddenAgentInstruction`
- `window._currentAiAssistantKind`
- `window._currentAiAssistantTitle`

优先抽出的后端 helper：

- product routes。
- session product binding。
- chat start product context parsing/snapshot/status update。

## 11. 目前看到的结构性问题

1. 前端 product 模型和 UI runtime 互相依赖。

   例如 `product-store.js` 的 canvas 判断会读 `_activeProductPreview`，这让纯 model 逻辑依赖 preview UI 状态。

2. 后端/前端 toolset alias 双份维护。

   前端 `NEXT_AI_PRODUCT_TOOLSET_ALIASES` 和后端 `PRODUCT_TOOLSET_ALIASES` 需要合并到一个 API 或约定文件。

3. builtin product 双份维护。

   前端 `AI_OBJECTS` 和后端 `BUILTIN_PRODUCTS` 都写了 General/PPT 基础信息。hydrate 后虽然会覆盖，但启动期仍有双事实。

4. `product_init` 的状态语义仍偏 UI generation。

   后端 `products.py` 已支持 chat_only finalize ready，但前端 preview/status 仍有不少“产品界面”语义。

5. `routes.py` 中 product binding 逻辑重复。

   session new、chat start、sync chat 都自己解析 product context、snapshot、record session。

6. `send()` 是过载函数。

   它既是用户发送入口，也是 canvas bridge 复用的 agent dispatch。后续最好抽一个 `startAgentTurn(payload)`，composer 和 canvas 都调它。

7. 旧函数残留。

   `confirmAssistantCreatePreview` 看起来已不在新创建路径中使用，应后续确认并删除。

## 12. 第二轮：`ui.js` 产品相关胶水

文件：`apps/webui/static/ui.js`

已读关键区段：

- 246-257：`_statusCardHtml` 渲染 transient status card。它不只服务产品，也服务通用状态卡。
- 1520-1697：access preset / toolsets chip。
- 2337-2370：`[[NEXT_AI_SUGGEST_PRODUCT]]` marker 解析、隐藏和创建产品按钮。
- 4530-4570：`syncTopbar` 会间接触发 `syncAssistantTaskUi`、`syncModelChip`。
- 4659-4741：消息可见内容处理，包含隐藏 context 清理、assistant label、product view 的 thinking 文案。
- 5457-5737：`renderMessages` 里消费 status card、product suggest marker、assistant body。

结构判断：

- `ui.js` 是产品逻辑的消费者，不是产品事实源。
- access preset 这块是最适合从 `ui.js` 先拆出去的小模块，因为它的 DOM 面窄、状态输入少、问题明确。
- `renderMessages` 里产品相关代码不多，但这个函数承担太多消息渲染职责，先不要大拆；可以先把 status card renderer 和 marker parser 抽成纯函数。

具体问题：

- `_accessPresetForToolsets` 对未知非空 toolsets 默认归类为 `workspace`。
- `_accessLabelForToolsets` 对未知非空 toolsets 默认显示 Files。
- `_applyAccessPreset('default')` 发 `toolsets:null`，后端 `/api/session/toolsets` 语义是清除 session override，不等于恢复产品默认工具。
- 如果产品默认工具是 `['skills', 'image_gen']`，现在很容易被前端 access preset 标签误导或丢掉。

建议：

- 先抽 `session-access-model.js`，统一定义 access preset 与 toolset list 的关系。
- 后端 `/api/session/toolsets` 增加明确的 `mode: inherit_product_default | custom | full | workspace`，不要让 `null` 兼任多种含义。

## 13. 第二轮：`sessions.js` 会话恢复链路

文件：`apps/webui/static/sessions.js`

已读关键区段：

- 420-500：`newSession` 创建 session 时读取 `currentAssistantProductSessionDefaults()`，把 `product_id`、`product_scope`、`product_intent`、`enabled_toolsets` 带给后端。
- 515-796：`loadSession` 两阶段加载。metadata 先到后立刻调用 `syncAssistantForLoadedSession(S.session)`，之后 inflight/idle 分支在消息加载后再次同步。
- 1871-2005：session list cache 的并发 generation guard，避免旧响应覆盖新列表。
- 2687-2760：`renderSessionListFromCache` 过滤当前 product/assistant 下的 session。
- `product-shell-runtime.js` 900-939：`assistantKindForLoadedSession` 和 `syncAssistantForLoadedSession` 根据 `session.product_id` 恢复当前 AI object，必要时重新 hydrate 后端产品。

结构判断：

- `sessions.js` 本身不该懂产品 UI，它只应该保存和恢复 session metadata。
- 当前恢复链路实际是：session metadata -> `syncAssistantForLoadedSession` -> `selectAiObject`/`syncAssistantTaskUi` -> product preview refresh。
- 这个边界还算正确，但通过全局函数串起来，缺少显式依赖。

建议：

- 抽一个 `session-product-binding.js`，只处理：
  - 从 session 读取 product identity。
  - 新 session body 生成。
  - loaded session -> current product selection。
- `sessions.js` 只调用 `restoreProductBindingForSession(session)`，不直接知道 product shell 的内部函数名。

## 14. 第二轮：`streaming.py` 产品注入和完成链路

文件：`apps/webui/api/streaming.py`

已读关键区段：

- 149-157：`_webui_ephemeral_system_prompt` 把 personality、可见进度规则、product prompt 合并成非持久化 runtime prompt。
- 2765-2837：`_run_agent_streaming(..., product_context=None)` 和 `_finalize_product_turn`。只有 `product_init` / `product_builder` 会调用 `finalize_product_generation`。
- 3864-3894：运行前根据 `product_context` 生成 `product_ephemeral_prompt`，挂到 `agent.ephemeral_system_prompt`。
- 4240-4281：silent/no-response 错误路径会 `_finalize_product_turn(failed=True, ...)`，然后持久化 assistant error。
- 4728-4815：正常 done 前 `_finalize_product_turn(failed=False)`，然后发 `done`。
- 5188-5222：`/api/chat/steer` 会恢复 product context；builder/init scope 下把 product prompt 前置到 steer text。

结构判断：

- product prompt 不进入历史，这个方向是对的。
- product completion lifecycle 被塞在 streaming worker 内部，和 provider error、goal、title、compression 都混在一个长函数里。
- `_finalize_product_turn` 是小而清楚的内嵌函数，适合抽到后端产品生命周期 helper。

建议：

- 抽 `api/product_turns.py`：
  - `build_product_runtime_prompt(product_context)`
  - `finalize_product_turn(product_context, failed=False, error_type=None, error_message=None)`
  - `product_context_for_steer(body, session, text)`
- `streaming.py` 只保留调用点，减少对 product 模块细节的了解。

## 15. 第二轮：`models.py` Session 产品字段

文件：`apps/webui/api/models.py`

已读关键区段：

- 360-448：`Session.__init__` 接收 `enabled_toolsets`、`product_id`、`product_scope`、`product_intent`、`product_line`。
- 434-440：product 字段做了基础 string sanitize；`product_line` 只允许 `use` / `build`，否则置空。
- 455-502：`save` 的 metadata fields 明确包含产品字段和 `enabled_toolsets`。
- 630-688：`compact` 输出 product 字段；只在有 `product_id` 时输出，并给 `product_scope` 默认 `product_usage`、`product_line` 默认 `use`。
- 900-955：run journal 恢复逻辑与产品字段无直接耦合，说明产品身份主要走 session metadata，不依赖消息事件。

结构判断：

- 产品属于 session 是后端模型上的一等字段，不是前端临时状态。
- `product_scope` / `product_line` 的默认值散在不同层：model compact、product_context、routes、frontend context。未来应收口。
- `product_task_title` 没进 Session 模型，只作为创建时 title 生成输入，这符合现在语义。

建议：

- 增加 `Session.product_metadata()` 或 `session_product_compact(session)` helper，避免 `compact`、routes、product_context 各自拼字段。
- 把 `product_line` 和 `product_scope` 的默认规则写成后端单点函数。

## 16. 本轮更明确的可维护性结论

现在可以比较确定地说：

- 产品抽象足够清楚，代码实现不够清爽。
- 不是“逻辑错得无法维护”，而是“逻辑被挤在太大的文件里，跨文件靠全局函数和隐式状态传递”。
- 直接 TS 重写不合适；先抽模块，再 TS 化模块，风险更低。
- 第一刀应该切小块：access preset、product model、product adapter、product context client、product turn lifecycle。

最值得优先处理的真实风险：

1. Access preset 会误判/丢失 product-specific toolsets。
2. `product_init` 已经不等于 UI generation，但前端状态文案仍强绑定“生成界面”。
3. streaming 的 product finalize 在巨型 worker 里，后续排查生成状态卡住会困难。
4. `assistant` / `product` 命名混用让新代码很容易接错层。

## 17. 第三轮：product app 样例与 bridge SDK

### 17.1 `product-bridge-sdk.js`

文件：`apps/webui/static/product-bridge-sdk.js`

已读关键区段：

- 1-58：localStorage/sessionStorage fallback。sandbox 或隐私限制下会退到 memory storage。
- 60-95：`NextAI.chat.send` / `NextAI.product.send`。它发送 `nextai:product:send`，返回 `{ content, raw }`。
- 97-174：`NextAI.state.get/set/remove`。默认 scope 是 `session`，host 失败时回退到 localStorage。
- 176-214：host reply/error/agent message 处理。
- 216-237：暴露 `window.NextAI`。

结构判断：

- 这是最适合先 TypeScript 化的前端模块之一：协议面小，输入输出清楚，产品 app 都依赖它。
- SDK 已经做了 host 消息 `event.source === window.parent` 校验，安全边界比 origin 校验更适合 sandbox iframe。
- `chat.send` 现在只规范化 `content/raw`，但产品 app 已经在猜 `image_url`、`content_url` 等字段，说明返回类型需要扩展。

具体问题：

- 超时策略不统一。SDK state 默认 5 秒；PPT 自己 race 1.2 秒；AI Otome 直接等待 SDK 默认超时。
- `NextAI.chat.send` 的返回协议没有类型，导致不同产品各自猜结构。
- SDK 没有显式 `ready()` promise，产品 app 只能靠是否存在 `window.NextAI` 或监听事件。

建议：

- 抽 `product-bridge-sdk.ts`，定义：
  - `NextAIChatRequest`
  - `NextAIChatResponse`
  - `NextAIStateScope`
  - `NextAIStateRequest`
  - `NextAIAgentMessageEvent`
- 在 SDK 层统一 state get 的超时默认值，产品 app 不应各自写 race。
- 给产品 app 模板提供 `await NextAI.ready({timeoutMs})`。

### 17.2 `products/ai-otome`

已读关键区段：

- `app.js` 63-80：默认游戏状态。
- `app.js` 89-106：使用 `NextAI.state` 持久化，独立打开时 fallback 到 localStorage。
- `app.js` 174-332：render、choices、memory、scene 切换。
- `app.js` 368-440：用户发送 -> `NextAI.chat.send` -> product context。
- `app.js` 470-515：解析最后一行 JSON，更新 mood/bond/scene/memory/choices。
- `app.js` 555-579：生成立绘，期待 bridge response 里有 `image_url` 或 `content_url`。
- `product.json`：`canvas_full` + `tools: ['skills', 'image_gen']`。

结构判断：

- 这是 `canvas_full` 产品样例：产品 UI 拥有完整 use flow，host chat 更像 AI 后端。
- app 内部分区清楚，状态/渲染/AI 调用/解析大体可维护。
- 它正好暴露 access preset 风险：产品默认工具不是 Files/Full，而是 `skills + image_gen`。

具体问题：

- `loadState` 没有 PPT 那种短超时 race；host state 异常时可能让首屏等待 SDK 默认 5 秒。
- JSON 结构化回复靠最后一行 JSON/regex 解析，适合产品 demo，但长期最好由 bridge/agent 协议提供 structured payload。
- 生成图片返回字段未被 SDK 类型约束。

建议：

- 把 AI Otome 作为 `canvas_full` 产品模板参考。
- 把 `NextAI.chat.send` 的 structured response 和 image response 规范进 SDK。
- 给产品 app 加轻量 smoke test：离线 fallback、state fallback、chat send mock。

### 17.3 `products/ppt-designer`

已读关键区段：

- `app.js` 16-24：PPT 工作台状态。
- `app.js` 27-48：bridge state 持久化，自己加了 1.2 秒 timeout race。
- `app.js` 57-70：brief/outline/slides stage 切换。
- `app.js` 193-216：通过 `nextai:product:download` 让 host 触发 PPTX 下载。
- `app.js` 219-249：给 Agent 的 spec/generate prompt。
- `app.js` 252-261：canvas button -> `NextAI.chat.send`。
- `app.js` 292-329：Agent -> GUI 的两条路径：优先读 workspace `state.json`，失败再 parse chat reply。
- `app.js` 331-348：`window.PPT` callbacks。
- `app.js` 393-436：`HEYTEA_DECK` demo 数据在正常启动路径强制覆盖状态。
- `ppt-skill/SKILL.md`：PPT 生成产物落在 `outputs/<deck>/`，包含 `deck.pptx`、slide images、prompts、HTML viewer。

结构判断：

- 这是 `chat_left_canvas_right` 工作台样例：canvas 是 chat 的协作表面，不是完整独立应用。
- “Agent 写 workspace state.json，canvas 读取”是一个很实用的 AI->GUI 通道，比单纯解析聊天文本稳。
- PPT 产品 app 与 `ppt-skill` 强耦合，但这种耦合属于产品内部边界，可以接受。

具体问题：

- `HEYTEA_DECK` 在正常启动路径强制 `applyDeckState`，会覆盖 session state 和 workspace `state.json`，像 demo/调试残留。
- `parseOutlineReply` 和 `parseLoadImages` 用 regex 解析聊天文本，能跑但脆弱。
- prompt 里要求 Agent 输出 `window.PPT.loadImages(...)`，这是方便但不够安全/类型化的 callback 协议。

建议：

- 把 `HEYTEA_DECK` 移到 `?demo=heytea` 或 `demo/heytea.json`，默认启动不能覆盖用户状态。
- 把 `state.json` 约定写进 product app SDK/contract：文件名、字段、更新优先级、何时 fetch。
- 后续让 bridge 支持 `NextAI.canvas.update(payload)` 或标准 structured artifact，减少 regex 和 `window.PPT.*` 字符串协议。

### 17.4 `products/general`

已读关键区段：

- `product.json`：`chat_only`，但 tools 是 `skills/file/terminal/code_execution`。
- `index.html`：明确“通用 AI 使用默认 Chat 页面”。
- `about.html`：一个独立介绍页，目前不是默认 preview entry。

结构判断：

- General 是 `chat_only` 边界样例：有 product manifest 和 workspace，但正常不应该显示右侧 canvas。
- 它证明 product 不等于 canvas；后续命名和状态文案不能继续把 `product_init` 等同于“生成界面”。

## 18. 第三轮：workspace 与产品预览服务

文件：

- `apps/webui/static/workspace.js`
- `apps/webui/api/routes.py`
- `apps/webui/api/products.py`

已读关键区段：

- `workspace.js` 71-106：`loadDir` 只基于 `S.session.workspace` 拉普通 workspace 文件树。
- `workspace.js` 238-322：普通文件预览走 `/api/file` 和 `/api/file/raw`。
- `routes.py` 5912-5943：产品 preview/assets 走 `/api/products/<id>/preview/...` 或 `/api/products/<id>/...`。
- `products.py` 的 `product_file_status` 纯读取 entry/status/assets。
- `products.py` 的 `preview_product_file` 做 root resolve 和 `relative_to(root)` 防路径逃逸。

结构判断：

- 普通 workspace 文件树和 product preview 服务是两条路径，可以拆开。
- 产品 preview 文件服务安全边界比较清楚，适合迁到 `routes_products.py`。
- `product_file_status` 保持 pure read，这个设计合理；状态写入集中在 finalize/reconcile。

建议：

- 拆 product routes 时把 `_serve_product_preview`、`_serve_product_asset`、`_serve_file_response` 相关产品路径一起迁走。
- 给 product asset 路径加明确测试：默认 index、嵌套 asset、路径逃逸、缺文件。

## 19. 第三轮：toolsets / access preset 语义确认

已读关键区段：

- `routes.py` 4598-4627：`/api/session/toolsets` 的 `toolsets:null` 明确是 clear per-session override。
- `routes.py` 7638-7649：`_session_toolsets_from_request` 会 normalize 并过滤到 `_resolve_cli_toolsets()` 可用集合。
- `routes.py` 4328-4396：`/api/session/new` 若没有显式 enabled toolsets，会从 `product_ctx.tools` 写入 session。
- `routes.py` 4368-4374：new session 里 `chat_only` 产品不会把 ui_status 置为 generating。

结论：

- access preset 的风险被确认：前端把 Default 发送成 `toolsets:null`，后端语义是“清除 override”。对普通 session 尚可，但对 product default tools 容易和“继承产品默认工具”混淆。
- 后端新建 product session 已经会把 product tools 写入 `s.enabled_toolsets`，这和 “Default = null” 的 UI 表达更冲突。

建议：

- 前端显示上把 session 当前 `enabled_toolsets` 为产品默认工具时标成 “Product default” 或产品能力名，不要标 Files。
- API 层新增显式 mode，或者前端 Default 对 product session 发送产品默认 toolsets，而不是 null。

## 20. 第四轮：`boot.js` 启动链路

文件：`apps/webui/static/boot.js`

已读关键区段：

- 1395-1415：`applyBotName` 会同步 document title、sidebar title、placeholder，并调用 `syncAssistantTaskUi`。
- 1417-1515：boot IIFE 先加载 settings、主题、语言、bot name、默认 workspace。
- 1523-1550：加载 active profile 和 model dropdown。
- 1551-1570：确定 URL/sessionStorage saved session，先 `loadWorkspaceList`、onboarding，再 `renderSessionList`。
- 1581-1630：有 saved session 时走 `loadSession`；`loadSession` 内部会恢复 product binding 和 workspace file tree。
- 1633-1645：无 saved session 时显示 empty state，再 render session list。
- 1646-1653：boot 失败 fallback。
- 1663-1703：BFCache `pageshow` 恢复，会重新 `loadSession`、`checkInflightOnBoot`、`syncTopbar`、`syncWorkspacePanelState`、`renderSessionListFromCache`。

结构判断：

- `boot.js` 负责通用 app boot，不直接 hydrate products。
- 产品 hydrate 在 `product-shell-runtime.js` 的 `initNextAiAssistants` 里通过 DOMContentLoaded/readyState 自启动。
- 因为 `index.html` 使用 defer 脚本，`product-shell-runtime.js` 早于 `boot.js` 执行并注册 init；boot IIFE 同时在后面启动。现在靠全局函数和事件顺序自然协调。
- `loadSession` 恢复 product session 的逻辑比 boot 更关键：boot 只决定是否 load saved session。

风险/建议：

- 产品 hydrate 和 boot restore 是并行全局初始化，未来拆模块时需要显式 boot phases：settings/profile -> products hydrate -> session restore -> preview refresh。
- `applyBotName` 会调用 `syncAssistantTaskUi`，但此时产品 hydrate 可能尚未完成；目前靠后续 hydrate/sync 再覆盖。

## 21. 第四轮：`product-evolution.js`

文件：`apps/webui/static/product-evolution.js`

已读关键区段：

- 1-4：注释说明产品 UI 生成/编辑走正常 chat turn：`product_init` / `product_builder`。
- 5-32：`rollbackCurrentProductUiVersion`，检查 `_activeProductPreview`，调用 `/api/products/<id>/rollback`，应用后端 product，再刷新 preview。

结构判断：

- 文件名叫 `product-evolution`，但当前职责只有 recovery/rollback action。
- 真正的 version/snapshot/finalize 在后端 `api/products.py` 和 `routes.py`，前端只暴露一个 rollback 按钮动作。

建议：

- 如果后续没有更完整演化 UI，把它改名或并入 `product-preview-controller` / `product-recovery-actions`。
- rollback 文案仍强绑定“产品界面”，对 chat_only 产品不合适；不过当前 rollback 只有 active preview 时可用，影响面较小。

## 22. 第四轮：测试覆盖核对

已读测试：

- `apps/webui/tests/test_product_scope_lines.py`
- `apps/webui/tests/test_product_ui_status.py`
- `apps/webui/tests/test_knead_product_skill.py`
- `apps/webui/tests/test_issue1431_toolsets_chip_responsive.py`
- `apps/webui/tests/test_v050257_opus_followups.py`
- `apps/webui/tests/test_stage268_opus_followups.py`
- `apps/webui/tests/test_issue2232_legacy_toolsets.py`

已有强覆盖：

- `test_product_scope_lines.py` 覆盖 Session product_line、scope 推断、显式 scope 优先、build/use workspace guard、chat_only builder guard、productize marker、builder 强工具集、use 弱工具集、file manifest、builder/use prompt 分离。
- `test_product_ui_status.py` 覆盖 `_resolve_ui_status` 矩阵、layout promotion、`product_file_status` 纯读、`reconcile_product_status` 显式持久化、chat_only finalize ready。
- `test_knead_product_skill.py` 覆盖 knead-product skill 文档结构、bridge reference、模板里 SDK 在 app.js 前加载、builder prompt 会指向 skills。
- `test_v050257_opus_followups.py` 负向守住 streaming 读取 `Session.enabled_toolsets` 的 bug shape。
- `test_stage268_opus_followups.py` 守住 session duplicate 会复制 `enabled_toolsets`。
- `test_issue2232_legacy_toolsets.py` 覆盖 legacy CLI toolset alias normalization。

缺口：

- 没有测试 `_accessPresetForToolsets` / `_accessLabelForToolsets` 对 `['skills', 'image_gen']` 这类产品工具集的分类。
- 没有测试 “Default access” 在 product session 下应该继承产品默认工具，而不是误表达为普通 Files。
- 没有直接测试 product preview/asset serving：默认 index、嵌套 asset、路径逃逸、缺文件。
- 没有直接测试 `product-bridge-sdk.js`：send/state/download/host agent broadcast/timeout fallback。
- 没有测试 `ppt-designer` 默认启动不能覆盖用户 state；目前 `HEYTEA_DECK` 会强制覆盖。

测试建议：

- 新增 `test_product_access_presets.py` 或前端静态测试，钉住 custom/product toolsets 的 label 和 preset。
- 新增 `test_product_asset_serving.py`，直接测 `preview_product_file` 或路由 helper。
- 新增 JS/静态协议测试，至少检查 SDK 暴露 `NextAI.chat.send`、`state.get/set/remove`、message source guard。
- 新增 PPT product smoke/static test，禁止默认启动路径无条件 `applyDeckState(HEYTEA_DECK)`。

## 23. 更新后的下一轮阅读建议

还应继续读：

1. `apps/webui/static/index.html` 中产品 DOM 区域和 script 顺序细节
   - 之前只读了加载顺序，下一步可以把产品相关 DOM 节点和脚本依赖写清楚。

2. `.agents/skills/knead-product/references/*`
   - 测试已经覆盖它存在，但需要读真实指南和当前代码是否一致。

3. `apps/webui/api/products.py` 全量
   - 已读关键区段，但这个文件已经变动，建议再按当前状态全量过一遍 registry/version/snapshot。

4. 前端产品 CSS
   - `style.css` 的产品 layout、canvas_full、chat_left_canvas_right 响应式规则还没系统梳理。

## 24. 第五轮：`index.html` 产品 DOM 契约

文件：`apps/webui/static/index.html`

已读关键区段：

- 131-145：左侧产品品牌、折叠按钮、New task 入口。
- 153-182：`panelChat` 承载 AI shelf、产品列表、任务列表、session search。
- 220-237：产品聊天 header、面包屑、chat/product status chips、Shape it 入口。
- 238-257：`assistantHome` 是产品首页/创建入口/建议任务的统一首屏。
- 258-303：消息容器、adjust panel、任务上下文 strip、任务进度条、messages。
- 304-340：`paneResizer`、`activeProductSurface`、iframe preview、preview empty/generating/failed state。
- 580-586、650-664：composer access chip/dropdown。
- 1056-1065：右侧 workspace 的 product context strip/hint。
- 1129-1198：创建 AI 和 skills/tools 两个 product dialog。
- 1200-1214：前端 defer 脚本加载顺序：`ui.js -> workspace.js -> sessions.js -> messages.js -> product-store.js -> product-shell-runtime.js -> product-runtime.js -> product-evolution.js -> ... -> boot.js`。

结构判断：

- 产品壳的 DOM 契约集中在一个 1200 行 HTML 文件里，多个 JS 文件靠固定 id、class、inline onclick 读取和更新。
- 这个 DOM 本身并不难懂，但它是“隐式 API”：改一个 id 或移动一个 script，可能影响 `ui.js`、`sessions.js`、`messages.js`、`product-shell-runtime.js`、`product-runtime.js`、`product-evolution.js`。
- `activeProductFrame` 的 sandbox 是 `allow-scripts allow-forms`，产品 iframe 没有 same-origin，这和 bridge/state 设计一致。

风险/建议：

- 先写 `PRODUCT_DOM_CONTRACT` 或静态测试，钉住产品壳必需 id 和脚本顺序，再拆文件。
- `inline onclick` 是迁移阻力：抽模块时应优先把 product 相关 handler 统一挂到一个 host controller，再逐步删 inline handler。
- 产品 DOM 可以先从 HTML 中“逻辑标注/契约化”，不急着引入框架。

## 25. 第五轮：`style.css` 产品样式层

文件：`apps/webui/static/style.css`

已读关键区段：

- 628-683：product dialog / capabilities dialog 基础样式。
- 995-1186：active product surface、pane resizer、canvas_full、adjust panel 基础布局。
- 4102-4335：Next AI MVP shell 第一轮产品壳样式。
- 4534-5050：session product chip、product chat header、status chip、task context/progress、assistant home。
- 5297-5707：task 状态下 home 压缩、消息样式、composer/access dropdown。
- 5797-5889：workspace product context strip、移动端 header/home 调整。
- 5896-5988：`chat_left_canvas_right` 双栏布局和 splitter。
- 6041-6310：sidebar/product brand/AI object 第二轮覆盖。
- 6391-6645：Aura sidebar pass，再次覆盖 AI object/session list。
- 6646-6705、6978-6990：product chat header/task chip/assistant home 最终覆盖和移动端覆盖。

结构判断：

- 样式能跑，但组织方式是“多轮覆盖”而不是“按组件/布局边界组织”。
- 同一组件分散在多个位置：例如 `.product-chat-header` 在 4662、6646、6982 都有定义；`.ai-object-item` 在 4335、6191、6421、6536 多次覆盖。
- 产品 layout 由 body data 状态组合驱动：
  - `data-next-ai-view`
  - `data-next-ai-directory`
  - `data-next-ai-product-layout`
  - `data-next-ai-canvas`
  - `data-next-ai-chat-panel`
  - `data-next-ai-product-adjust`

风险/建议：

- 维护难点不是 CSS 技术复杂，而是“生效来源难找”。改一个产品按钮，需要跨多个区域确认覆盖顺序。
- 应先做无行为改动的 CSS 分区：dialog、sidebar、product shell、active preview、product layout、access dropdown。
- 双栏布局和 canvas_full 布局应有一个明确 layout state map，避免继续把状态组合散落在 CSS 和 JS 里。

## 26. 第五轮：`.agents/skills/knead-product` 产品契约

已读文件：

- `.agents/skills/knead-product/SKILL.md`
- `.agents/skills/knead-product/references/layouts.md`
- `.agents/skills/knead-product/references/bridge.md`
- `.agents/skills/knead-product/templates/minimal-canvas.html`

契约要点：

- 产品模型被约束成 4 个变量槽位：`product_layout`、`product_type`、`skills + tools`、`canvas_label`。
- 三种布局含义清楚：
  - `chat_only`：无 canvas 文件。
  - `chat_left_canvas_right`：聊天驱动右侧工作面。
  - `canvas_full`：产品界面拥有主输入，宿主 composer 只用于调整产品。
- canvas 不允许直接调模型或 `/api/chat`，必须经 `/static/product-bridge-sdk.js` 的 `window.NextAI.chat.send`。
- 持久 UI 状态建议走 `window.NextAI.state`，并强调不要阻塞 first paint。
- `minimal-canvas.html` 已保证 bridge SDK 在 `app.js` 前加载。

和真实产品对照：

- `products/ai-otome/index.html`、`products/ppt-designer/index.html` 都在 `app.js` 前加载 bridge SDK，符合契约。
- `products/ppt-designer/app.js` 的 `restore()` 会用 1200ms timeout race，不阻塞首屏，符合契约。
- `products/ai-otome/app.js` 的 `loadState()` 直接 await `NextAI.state.get`，如果启动路径在渲染前 await 它，会和“不阻塞 first paint”的契约冲突。
- `products/ppt-designer/app.js` 默认启动最后无条件 `applyDeckState(HEYTEA_DECK)`，会覆盖 saved/session/workspace state，不符合“产品默认可复用”的方向。

测试对照：

- `test_knead_product_skill.py` 覆盖 skill 文档结构、references、模板 bridge 顺序、builder prompt 会加载 `knead-product`/`impeccable`。
- 还没有测试真实 shipped products 的 bridge 顺序、无直接 `/api/chat`、`NextAI.state` 首屏 timeout、PPT 默认不覆盖 state。

## 27. 第五轮：product draft 生命周期

新增读到：

- `apps/webui/tests/test_product_drafts.py`

含义：

- `create_product_draft()` 现在有独立草稿目录，测试确认 draft 写入 `product.json`，但不会进入正式 `list_products()`。
- 这说明产品创建链路已经有 “draft product workspace -> registered product” 两层概念。

建议：

- 后续读 `api/products.py` 时要单独梳理 draft/create/promote/cancel/cleanup 生命周期。
- TODO 里要把 draft workspace 的路径隔离、正式注册、过期清理、失败恢复列出来。

## 28. 当前清晰度判断

已经足够清晰的部分：

- 产品意图：Knead 是 chat-first，多 AI object，每个产品可以是 chat-only、side canvas、full canvas。
- 后端产品上下文：product usage/builder 两条线分得比较清楚，builder 有文件权限，usage 更偏只读和弱工具集。
- UI 状态：`ui_status`、layout promotion、chat_only finalize 已经有较强测试。
- 产品 iframe 协议：bridge SDK 是正确方向。

还不够清晰、也是维护痛点的部分：

- 前端 DOM 契约没有显式文档/测试，id、inline handler、script order 是隐式依赖。
- CSS 是覆盖式堆叠，组件边界不清。
- access preset 的 “Default / 产品默认工具 / Files” 语义还容易混。
- product preview、bridge SDK、真实产品 app 没有足够冒烟测试。
- `products/ppt-designer` 还残留特定 demo 覆盖逻辑。

结论：

- 不建议直接 TS 重写整个项目。
- 建议先把隐式边界变成显式边界：DOM contract、CSS component split、product model/adapter、bridge typed protocol。
- 等这些边界稳定后，再局部 TS 化纯逻辑和协议层。

## 29. 第六轮：`api/products.py` 产品生命周期

文件：`apps/webui/api/products.py`

已读关键区段：

- 22-45：状态文件、draft 目录、products 目录、snapshot 文件规则。
- 45-111：三个内置产品 `general`、`ppt-designer`、`ai-otome`。
- 154-188：product tools alias 和默认 capabilities 推断。
- 250-333：state 读写和 `_normalize_product`。
- 340-406：`_ensure_builtin_products_locked`，确保内置产品存在、写 seed files、注册 workspace。
- 420-469：`_write_seed_files` 和 `product.json` manifest 写入。
- 526-586：`_resolve_ui_status`，纯函数状态推导。
- 589-648：`list_products` / `get_product` / `create_product`。
- 651-721：`create_product_draft`。
- 724-806：`update_product` / `delete_product`。
- 824-1059：snapshot / rollback。
- 1062-1192：session 记录、layout promotion、finalize、reconcile。
- 1195-1261：file status 和 preview asset 文件解析。

生命周期梳理：

1. 内置产品
   - `_ensure_builtin_products_locked()` 负责把 builtins 写进 state，且每次会 `_write_seed_files()` 和 `_register_workspace()`。
   - 它保留已有 `ui_status`、sessions、versions，但会用内置 definition 覆盖 identity/config。

2. 正式产品创建
   - `create_product()` 生成唯一 id，normalize，写 workspace seed files，注册 workspace，写入 `ai_products.json`。
   - fresh product 的 `ui_status` 走 `_resolve_ui_status(..., entry_generated=None)`，不是立刻检查磁盘。

3. 草稿创建
   - `create_product_draft()` 只创建 `STATE_DIR/product_drafts/<id>`，写 draft `product.json` 和 README。
   - draft 不写入 `ai_products.json`，不注册 workspace，不进入 shelf。
   - 当前没有 promote/register/cancel/cleanup API，草稿生命周期只实现了 create。

4. 产品更新
   - `update_product()` 只允许一组 scalar/list 字段，normalize 后调用 `_write_seed_files()` 和 `_write_state()`。
   - 这意味着更新产品配置时，如果 `index.html` 缺失，会重新写 seed placeholder；这是便利，但也让 update 同时承担“补文件”的副作用。

5. 状态推导
   - `_resolve_ui_status()` 是目前写得比较清楚的部分：读路径派生，不随便持久化。
   - `list_products()` 和 `product_file_status()` 都是纯读派生。
   - `finalize_product_generation()` 和 `reconcile_product_status()` 是明确的持久化写入口。

6. manifest 回写
   - `_product_manifest_patch_from_workspace()` 允许 agent 通过 workspace 里的 `product.json` 回写 title/avatar/skills/tools/layout 等窄字段。
   - 这是 product builder 的合理边界，值得保留并测试。

7. snapshot/rollback
   - `_product_ui_snapshot_files()` 会收集 workspace 下小文件，排除 `versions`、`.git`、`node_modules`、隐藏文件、大文件。
   - snapshot 最多保留 25 个 version。
   - rollback 会把当前 managed files 和 snapshot files 做集合，snapshot 里没有的当前文件会被删除，然后 `update_product(..., ui_status=ready)`。

8. preview
   - `product_file_status()` 走 `get_product()`，会触发内置产品 ensure。
   - `preview_product_file()` 直接 `_read_state()`，不触发 `_ensure_builtin_products_locked()`。
   - 因此直接访问内置产品 preview 可能隐含依赖前面已经访问过 `/api/products` 或其他 ensure 路径。

结构判断：

- 这个文件不是“写错了”，不少核心规则还有清晰注释和测试，尤其是 `ui_status`。
- 但职责明显过多：registry、builtins、workspace registration、draft、manifest、snapshot、status、preview 都在一个模块。
- 适合按职责拆成：
  - `product_registry.py`
  - `product_manifest.py`
  - `product_status.py`
  - `product_versions.py`
  - `product_drafts.py`
  - `product_assets.py`

测试缺口：

- snapshot/rollback 没有直接测试。
- preview asset/path traversal/no-store 没有直接测试。
- draft 只有 create 测试，没有 promote/cancel/cleanup。
- `preview_product_file()` 不 ensure builtins 的差异没有测试。

## 30. 第六轮：`routes.py` 产品 API 边界

文件：`apps/webui/api/routes.py`

已读关键区段：

- 3815-3841：GET 路由：product preview、list、versions、status、asset fallback。
- 5112-5171：POST 路由：draft create、create、update、delete、finalize、snapshot、rollback。
- 5916-5947：`_serve_product_preview` 和 `_serve_product_asset`。
- 5950-5960：`_serve_file_response`，设置 `Cache-Control: no-store`。

结构判断：

- 产品 API 的边界已经比较规整，抽 `routes_products.py` 不需要重新设计接口。
- GET 和 POST 的 product 路由散落在 `routes.py` 两个大区段里，helper 又在 5900 行以后，定位成本高。
- `_serve_product_preview` 和 `_serve_product_asset` 都做 path split/unquote，再调 `preview_product_file()`，可以合并成一个 product asset handler。

建议：

- 第一批后端拆分可以直接搬：
  - `handle_products_get(handler, parsed)`
  - `handle_products_post(handler, parsed, body)`
  - `serve_product_asset(handler, parsed)`
- routes 主文件只保留薄分发。
- 同时补 route-level 测试：preview 默认 index、嵌套 asset、路径逃逸、404、no-store header。

## 31. 第六轮中途阅读建议（已继续执行）

下一步继续读：

1. `apps/webui/api/product_context.py`
   - 重点核对 product usage/builder scope、tools、workspace guard、prompt 注入。

2. `apps/webui/api/streaming.py`
   - 重点看 product_init/product_builder/product_usage turn lifecycle，确认 finalize/snapshot/status 调用顺序。

3. `apps/webui/static/product-bridge-sdk.js` 和 host runtime 对照
   - 需要把 bridge protocol 的收发、state、download、agent broadcast 读成一张表。

## 32. 第六轮：`api/product_context.py` 产品 scope / line / tools

文件：`apps/webui/api/product_context.py`

已读关键区段：

- 19-26：`PRODUCT_SCOPES` 和 `BUILDER_BASE_TOOLSET`。
- 29-43：build 线文件 manifest，只列顶层、跳过 runtime/cache/version 目录。
- 60-84：builder intent regex 和 negation regex。
- 87-117：`infer_product_scope`，显式 scope 权威，regex 只作 fallback。
- 120-157：`product_context_request_body`，从 product-bound session 恢复 product fields。
- 160-230：`product_context_from_request`，生成 product context、line、tools、workspace guard。
- 233-432：`product_ephemeral_prompt`，生成 build/use 两套 ephemeral prompt。

结构判断：

- 这是当前产品逻辑里比较清楚的一层。
- 明确有两条会话线：
  - `build`：`product_init` / `product_builder`，用于造/改产品本身。
  - `use`：`product_usage`，用于使用产品完成任务。
- 显式 scope 优先，避免“用户在使用产品时说了改这一页”被 regex 错误切到 builder。
- session continuation 也按 `product_line` 恢复：build 会话继续 build，use 会话继续 use。
- build 线 workspace 必须等于产品 workspace；use 线允许跑在普通任务 workspace。
- build 线工具 = `skills,file,terminal,code_execution` ∪ 产品自有 tools。
- use 线工具 = 产品自有 tools，不自动给 file/terminal/code_execution。

prompt 设计：

- build prompt 明确说 “product engineer, NOT persona”，并要求先加载 `knead-product`，复杂 UI 再加载 `impeccable`。
- chat_only builder 有专门 guard：只改 `product.json` 身份/角色/技能/工具，不生成 `index.html/style.css/app.js`。
- use prompt 明确 product files READ-ONLY。
- PPT Designer use prompt 有专门 canvas contract：优先写 `state.json`，或追加结构化 outline block。
- chat_only usage 有 productize suggestion marker：`NEXT_AI_SUGGEST_PRODUCT`。

测试覆盖：

- `test_product_scope_lines.py` 覆盖：
  - `Session.product_line` compact。
  - 显式 scope 不被 regex 覆盖。
  - build/use line 推导。
  - build workspace guard。
  - session continuation scope 恢复。
  - chat_only builder guard。
  - productize marker。
  - build 强工具集 + use 弱工具集。
  - build file manifest + use 无 manifest。
  - build prompt 不是 persona，use prompt 是 runtime/read-only。

风险/建议：

- `product_context_from_request()` 使用 `get_product()` 的 stored `ui_status`，不是派生后的 file status；如果 registry 状态和磁盘不一致，scope 自动 init 可能判断不准。
- 当前调用点在新建 session/chat start/sync chat/steer 前，没有统一看到进入 product context 前 reconcile status。
- 建议在进入 product context 前调用 `reconcile_product_status()` 或让 `product_context_from_request()` 使用 derived status，避免 stale `ready/generating` 影响 init/build/use 分线。
- `CAPABILITY_LABELS`、前端 toolset label、`products.py` toolset aliases 仍是多份事实，后续应收敛成共享表。

## 33. 第六轮：`streaming.py` 产品 turn finalize 入口

文件：`apps/webui/api/streaming.py`

已读关键区段：

- 2765-2832：`_run_agent_streaming(..., product_context=None)` 内部定义 `_finalize_product_turn`。
- 2834-2836：cancel path 会 `_finalize_product_turn(failed=True)`。
- 3887-3894：agent ephemeral system prompt 注入 `product_ephemeral_prompt(product_context)`。
- 4245-4249：provider/app error path finalize failed，并带 error type/message。
- 4813-4815：正常 done path finalize success，再发 done。
- 5074-5078：异常 path finalize failed。
- 5093：finally 最后一层兜底 finalize failed；成功路径靠 `product_turn_finalized` 防重复。
- 5189-5210：steer path 会恢复 product context；builder/init steer 会把 product prompt prepend 到 steer text。

结构判断：

- 产品生成状态的关闭点在 streaming worker 里，不在前端。
- build/init turn 开始前 routes 会 snapshot，turn 结束时 streaming finalize。
- `_finalize_product_turn` 只处理 `product_init` / `product_builder`，usage 不会 finalize 产品 UI 状态。
- 方向正确，但这个逻辑埋在 5000+ 行 streaming 文件中，后续应抽成 product turn lifecycle helper。

测试缺口：

- 没有直接测试 done/error/cancel/finally 四条路径都会关闭 product generating。
- 没有测试 finalize 失败后 timeout/reconcile 能兜住。
- 没有测试 steer builder prompt 注入是否保持 build/use 线。

## 34. 第七轮：`product-bridge-sdk.js` iframe SDK 协议

文件：`apps/webui/static/product-bridge-sdk.js`

已读关键区段：

- 1-33：sandbox iframe 里 localStorage/sessionStorage 可能不可用，所以先做 memory storage fallback。
- 35-58：安装 storage fallback，尽量让产品 app 仍能使用 `localStorage` / `sessionStorage`。
- 64-84：`postToHost()` 和 `createPendingRequest()`，统一发 `{source:"nextai-product-canvas", ...payload}` 到 parent。
- 86-95：`send(payload)` 发 `nextai:product:send`，resolve 为 `{content, raw}`。
- 97-174：`NextAI.state.context/get/set/remove`，优先走 host state，失败后 fallback 到 iframe 本地 storage。
- 176-195：`settlePending()` 处理 ack/reply/state/error；ack 会派发 `nextai:ack`，但不会结束 pending request。
- 197-214：只接受 `source:"nextai-host"` 且 `event.source === window.parent` 的消息。
- 216-237：暴露 `window.NextAI.chat.send`、`window.NextAI.product.send`、`window.NextAI.state`、`window.NextAI.storage`。

协议表：

| 方向 | type | 用途 |
| --- | --- | --- |
| iframe -> host | `nextai:product:send` | 产品 iframe 请求宿主让 agent 处理一段产品内消息 |
| iframe -> host | `nextai:product:state` | get/set/remove/clear 产品状态 |
| iframe -> host | `nextai:product:download` | 请求宿主下载产品生成的文件 |
| host -> iframe | `nextai:host:ready` | 宿主 iframe ready，传 productId/sessionId/layout/canvasLabel |
| host -> iframe | `nextai:host:ack` | 宿主已接受 canvas send |
| host -> iframe | `nextai:host:reply` | agent 回答完成，返回 content |
| host -> iframe | `nextai:host:state` | state 请求返回 |
| host -> iframe | `nextai:host:error` | send/state 失败 |
| host -> iframe | `nextai:host:agent_message` | 广播最新 agent 消息给产品 app |

结构判断：

- SDK 方向是对的：产品 app 不直接知道宿主聊天实现，只依赖 `window.NextAI`。
- state 做了 host storage + iframe fallback，能覆盖 sandbox storage 失败的情况。
- SDK 现在很薄，适合作为第一批 TS 化对象。

风险：

- reply shape 有不一致风险。SDK 对外只返回 `{content, raw}`，但 `products/ai-otome/app.js` 的画像生成路径读 `res.image_url || res.content_url`，如果 host 只回 `{content}`，产品拿不到图片 URL。
- `nextai:host:reply` 当前只规范了 `content`，没有 typed `message/raw/assets` 字段。
- state fallback 会静默成功，可能掩盖 host state 失败；需要在测试里明确 fallback 语义。
- iframe origin 因 sandbox 可能是 opaque，不能简单依赖 origin 校验；当前主要靠 `event.source` 和 active frame 身份校验。

## 35. 第七轮：`product-runtime.js` host bridge / preview runtime

文件：`apps/webui/static/product-runtime.js`

已读关键区段：

- 1-102：根据当前产品 UI 状态和待处理 intent 生成 `currentAssistantProductContextForMessage()`。
- 115-156：active iframe window、host postMessage、state key 规则。
- 177-227：host 处理 `nextai:product:state` get/set/remove/clear。
- 249-273：`_productCanvasBridgeInstruction()` 生成隐藏上下文块。
- 275-330：`_sendProductCanvasAgentMessage()` 把 iframe 内消息转成宿主聊天发送。
- 332-367：`notifyProductCanvasAgentReply()` / `broadcastAgentMessageToCanvas()` / `notifyProductCanvasAgentError()`。
- 369-403：host message listener 处理 send/state/download。
- 413-468：`_startProductInitializationTask()` 产品初始化任务。
- 600-650：`requestCurrentProductUiGeneration()` 手动生成/重建产品 UI。
- 672-770：`refreshCurrentProductPreview()` 从 `/api/products/<id>/status` 拉状态，更新 iframe preview。

结构判断：

- preview 刷新走 status endpoint，会触发后端 reconcile；这比直接读 registry 安全。
- host 端对 message source 做了 active frame 校验，基本防住非当前 iframe 的消息串线。
- canvas 内发消息到 agent 的链路已经完整：iframe send -> host ack -> 宿主 `send()` -> SSE done/error -> host reply/error -> iframe promise settle。

风险：

- bridge host 强耦合全局 `S`、`send()`、`#msg`、`window._nextAiPendingProductScope`、`window._nextAiPendingHiddenAgentInstruction`，不像独立模块。
- 隐藏指令是字符串块追加到用户消息里，再由 UI 层 `stripProductHiddenContext()` 隐藏显示；后端仍收到混合后的 message。更清晰的做法是单独字段，比如 `hidden_product_instruction`。
- `nextai:product:download` 直接 fetch iframe 传来的 URL，缺少“只能下载当前产品 preview/assets 或允许列表 URL”的显式限制。
- host reply 只发 content，没有把 agent message id、assets、image_url 等结构化字段传回 iframe。
- pending bridge request fallback “如果只剩一个 pending 则用它” 有实用性，但需要测试防止并发 send 串 reply。

## 36. 第七轮：`product-store.js` / `product-shell-runtime.js` 产品壳

文件：

- `apps/webui/static/product-store.js`
- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/messages.js`

已读关键区段：

- `product-store.js` 1-100：前端 capability/tool aliases、默认能力、layout normalize。
- `product-store.js` 103-217：产品是否使用 canvas、backend product -> frontend AI object adapter。
- `product-store.js` 249-400：backend product hydrate、内置产品合并、自定义产品注册。
- `product-store.js` 431-555：产品能力弹窗和 toolsets 保存。
- `product-shell-runtime.js` 125-137：自定义产品只存在 `_backendProductAssistants` 内存集合，不再读 legacy localStorage。
- `product-shell-runtime.js` 724-808：创建产品先建 draft workspace，再开 Creator session，并注入内部 creator 指令。
- `messages.js` 417-439：Create AI 页面拦截第一条普通消息，转成 `createProductFromPrompt(..., deferInitialSend:true)`。
- `product-shell-runtime.js` 980-999：加载 product-bound session 时，如果本地还没有 product kind，会异步 hydrate 后再切换。
- `product-shell-runtime.js` 1229-1272：`selectAiObject()` 切换当前 AI/product，并同步标题、placeholder、layout。
- `product-shell-runtime.js` 1976-2070：`syncAssistantTaskUi()` 根据 product layout / active task / canvas 状态同步 body datasets 和主界面。
- `product-shell-runtime.js` 2100-2106：启动时 render shelf，然后异步 `hydrateProductsFromBackend()`，再同步 UI。

结构判断：

- “创建产品”已经从直接注册正式产品，变成先创建 draft workspace；这个产品逻辑更合理。
- `create_product_draft()` 后端明确不写入 `ai_products.json`，不出现在产品 shelf。
- 前端产品壳把 list/hydrate/select/task surface/access/capabilities 都串在一起，所以用户体验能跑通，但维护点密集。

风险：

- `product-store.js` 复制了后端的 tool aliases、capability defaults、layout normalize 规则；这是产品模型事实源分裂。
- `hydrateProductsFromBackend()` 在启动时没有 await，session restore / product-bound session 需要额外异步补救。
- body dataset 是事实上的 layout state machine：`nextAiView`、`nextAiProductLayout`、`nextAiCanvas`、`nextAiProductAdjust`、`nextAiChatPanel`。这些状态组合没有显式表和测试。
- Creator draft 生命周期现在只有 create。还缺 promote/publish、cancel、cleanup、draft preview 权限、manifest 校验这一整段正式生命周期。
- Creator 内部指令仍靠 `window._nextAiPendingHiddenAgentInstruction` 传给 `messages.js`，和 canvas bridge 的隐藏上下文机制重复。

## 37. 第八轮：`boot.js` 启动和 session restore 时序

文件：

- `apps/webui/static/index.html`
- `apps/webui/static/boot.js`
- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/sessions.js`

已读关键区段：

- `index.html` 1202-1214：脚本顺序是 `ui.js` -> `sessions.js` -> `messages.js` -> `product-store.js` -> `product-shell-runtime.js` -> `product-runtime.js` -> `boot.js`。
- `product-shell-runtime.js` 2100-2112：`initNextAiAssistants()` 在 `DOMContentLoaded` 自启动，先 render shelf，再异步 `hydrateProductsFromBackend()`，然后 sync UI。
- `boot.js` 1417-1645：主 boot IIFE 读取 settings/profile/model/workspace/onboarding，render session list，恢复 saved/url session，最后启动 gateway SSE。
- `boot.js` 1581-1630：有 saved session 时先 `loadSession(saved)`，然后根据空 session / in-flight 状态决定保留还是显示 empty state。
- `boot.js` 1663-1703：BFCache `pageshow` 会重新 `loadSession()`、`checkInflightOnBoot()`、sync topbar/workspace/session list/gateway SSE。
- `sessions.js` 420-513：`newSession()` 会从当前产品拿 workspace/product_id/product_scope/enabled_toolsets，再创建后端 session。
- `sessions.js` 515-796：`loadSession()` 两阶段加载，metadata 先到后立刻 `syncAssistantForLoadedSession()`，然后恢复 inflight 或完整 messages。

实际启动时序：

1. defer 脚本按 HTML 顺序执行。
2. `product-shell-runtime.js` 注册 DOMContentLoaded 自启动。
3. `boot.js` 执行 async IIFE，但它的 await 不会阻塞 DOMContentLoaded。
4. DOMContentLoaded 触发 `initNextAiAssistants()`，产品 shelf/hydrate 开始跑。
5. boot IIFE 继续 settings/profile/workspace/session restore。
6. 如果 restored session 是 product-bound，但产品 hydrate 还没完成，`syncAssistantForLoadedSession()` 先可能回到 general，随后 980-999 的异步 hydrate 补救再切回产品。

结构判断：

- 这条链路有大量容错，说明实际 bug 修过很多；但产品启动阶段不是一个明确 boot phase。
- session restore 和 product hydrate 是并行关系，不是线性关系。
- 当前靠 `syncAssistantForLoadedSession()` 里的二次 hydrate 补救 product-bound session，这个设计能兜住，但读起来要跨 4 个文件。

风险：

- product-bound session 首屏可能短暂显示 general / 错误 layout，再切回真实产品。
- BFCache restore 重新 `loadSession()`，但没有显式重新等待 products hydrated。
- `newSession()` 对当前产品上下文的读取依赖 `currentAssistantProductSessionDefaults()`；如果当前产品还没 hydrate，产品 session defaults 可能缺失。
- 启动时序没有测试能证明“产品 hydrate 完成前恢复 product session”这个场景不会闪错或丢 context。

## 38. 第八轮：`messages.js` send / SSE / product bridge 交汇点

文件：

- `apps/webui/static/messages.js`
- `apps/webui/static/ui.js`
- `apps/webui/static/product-runtime.js`

已读关键区段：

- `messages.js` 390-438：`send()` 防并发、读取 `window._nextAiPendingHiddenAgentInstruction`，Create AI 页面拦截第一条消息去创建 creator draft。
- `messages.js` 446-520：busy 时走 steer/interrupt/queue，入队 payload 会通过 `withCurrentProductContext()` 带上 product context。
- `messages.js` 582-673：普通发送时创建 session、上传文件、拼 hidden instruction、计算 `currentAssistantProductContextForMessage()`，再 POST `/api/chat/start`。
- `messages.js` 635-638：INFLIGHT 会保存 `productUiStatusContext`，用于跨刷新/重连恢复产品状态卡。
- `messages.js` 716-751：chat start 失败时通知 canvas bridge error。
- `messages.js` 780-1045：`attachLiveStream()` 建立每个 active session 的 EventSource，并管理 inflight snapshot。
- `messages.js` 1807-1998：SSE done 更新 session/messages/toolcalls，向 canvas reply/broadcast，refresh product preview，并追加产品状态 done/failed 卡。
- `messages.js` 2143-2203：SSE app error 标记产品 UI failed，并通知 canvas bridge error。
- `messages.js` 2217-2305：SSE transport error / cancel path，有 reconnect/restore/fallback，并把产品 UI 标记 failed。
- `messages.js` 2315-2399：`_restoreSettledSession()` 和 `_handleStreamError()` 是掉线后恢复/失败兜底。
- `ui.js` 4659-4669、5616-5622：显示消息时用 `stripProductHiddenContext()` 正则剥掉隐藏上下文。
- `ui.js` 3108-3143：setBusy(false) drain queue 时恢复 `product_scope/product_intent` 到全局 pending，然后调用 `send()`。
- `product-runtime.js` 104-110：`withCurrentProductContext()` 给队列 payload 补 product context。

结构判断：

- 主链路很完整：send -> start stream -> SSE events -> done/error/cancel -> product preview/bridge/status card。
- `messages.js` 做了大量现实问题修复：并发发送、队列、重连、journal replay、BFCache、inflight storage、产品 UI 状态恢复。
- 代码正确性方向不错，但文件职责过重，已经是 message controller、stream controller、product lifecycle UI、bridge responder、queue drain controller 的混合体。

风险：

- hidden instruction 通过字符串拼到 `message` 字段，再靠 UI 正则剥离；这不是可靠协议边界。
- canvas bridge reply 只从最后一条 assistant message 提取 `content/message`，无法保证 image/assets/raw 字段按 SDK 约定回传。
- queued product payload 保存了 `product_id/product_scope/product_intent`，但 drain 时只恢复 scope/intent；实际 product_id 依赖当前产品 selection 间接恢复。产品 hydrate 或 session selection 有竞态时，queued turn 可能走错产品上下文。
- `_restoreSettledSession()` 恢复已完成 session 时没有走 done path 的 product preview refresh / canvas reply 逻辑；如果 SSE done 丢了但 session 已完成，产品 preview 可能不会立刻刷新。
- 产品 UI 状态卡逻辑在 `messages.js` 顶部、send 中、SSE done/error/cancel 中多处参与，后续加状态会很难保证每条路径一致。

## 39. 第九轮：`api/products.py` 产品文件/版本/状态生命周期

文件：

- `apps/webui/api/products.py`
- `apps/webui/tests/test_product_ui_status.py`
- `apps/webui/tests/test_product_drafts.py`

已读关键区段：

- 1-45：产品 registry、draft 目录、snapshot 常量、built-in product 定义。
- 127-188：id 安全化、toolset alias、能力默认推导。
- 250-333：`_read_state()` / `_normalize_product()`，存储层保留 raw `ui_status`，不在 normalize 阶段派生。
- 340-407：`_ensure_builtin_products_locked()`，ensure builtins、写 seed files、注册 workspace。
- 420-469：`_write_seed_files()` / `_write_manifest()`，会补 README/index/product.json。
- 495-586：`_product_entry_generated()` / `_resolve_ui_status()`，产品 UI 状态的纯派生矩阵。
- 589-613：`list_products()` 派生 status 但不落盘；`get_product()` ensure builtins。
- 616-648：`create_product()` 直接注册正式产品，创建 workspace、seed files、registry entry。
- 651-721：`create_product_draft()` 只创建未注册 draft workspace 和 draft manifest。
- 724-773：`update_product()` 白名单更新 registry，再写 seed/manifest。
- 776-806：`delete_product()` 拦截 builtin 删除，custom 产品删除 registry/workspace。
- 824-873：`_product_ui_snapshot_files()` 管理 snapshot 文件，跳过 versions/node_modules/.git/隐藏目录/大文件。
- 891-940：`_product_manifest_patch_from_workspace()` 只允许 workspace `product.json` 回写窄字段。
- 943-998：`snapshot_product()` 跳过 seed-only UI，复制产品 UI/assets 到 `versions/<id>`。
- 1009-1059：`rollback_product()` 用 snapshot files 恢复/删除 managed files，并移除已使用版本。
- 1107-1151：`finalize_product_generation()` 读 manifest patch、派生最终 status、布局 promotion、记录错误。
- 1154-1192：`reconcile_product_status()` 是显式落盘修复点。
- 1195-1244：`product_file_status()` 纯读状态和 assets。
- 1247-1261：`preview_product_file()` 直接从 `_read_state()` 取 registry，做路径逃逸检查后返回文件。

结构判断：

- `ui_status` 设计是当前后端产品逻辑里最清楚的一块：纯函数派生、读不落盘、显式 reconcile/finalize 才写状态。
- snapshot/rollback 也有明显工程边界：跳过 seed，占用独立 `versions` 目录，排除 runtime/大文件/隐藏目录，rollback 会删掉 snapshot 不含的 managed file。
- workspace manifest patch 是窄白名单，这比让产品代码随意改 registry 安全很多。
- draft create 的语义也清楚：draft 不是正式产品，不进 shelf，不自动打开 canvas。

风险：

- `create_product_draft()` 只有 create，没有 promote/register/cancel/cleanup，也没有 draft preview/asset path。
- `preview_product_file()` 用 `_read_state()`，不像 `get_product()` / `product_file_status()` 会 ensure builtins；直接打开 builtin preview 可能依赖之前是否访问过 `/api/products`。
- preview/asset 服务不 reconcile status；`/status` 会 reconcile，但 `/preview` 不会。
- `update_product()` 总会 `_write_seed_files()`，这会写 manifest；如果后续拆模块，需要明确“更新 registry”和“补 seed/manifest”的副作用边界。
- `snapshot_product()` 在锁内调用 `get_product()` / `update_product()`，虽然是 RLock 不死锁，但阅读上会让状态流变绕。
- snapshot/rollback 的测试缺口明显：当前测试覆盖 status matrix 和 draft create，没有覆盖 preview path、snapshot file include/exclude、rollback 删除 managed file、manifest patch 白名单。

## 40. 第九轮：`routes.py` 产品 API 边界

文件：

- `apps/webui/api/routes.py`
- `apps/webui/api/streaming.py`

已读关键区段：

- `routes.py` 2215-2229：从 `api.products` import create/delete/finalize/status/preview/rollback/snapshot/update 等产品函数。
- `routes.py` 3815-3841：GET 产品 API：
  - `/api/products/<id>/preview...` -> `_serve_product_preview()`
  - `/api/products` -> `list_products()`
  - `/api/products/<id>/versions` -> `list_product_versions()`
  - `/api/products/<id>/status` -> `reconcile_product_status()` + `product_file_status()`
  - `/api/products/<id>/<asset>` -> `_serve_product_asset()`
- `routes.py` 5916-5960：preview/asset 统一走 `preview_product_file()`，响应 `Cache-Control: no-store`。
- `routes.py` 5112-5171：POST 产品 API：
  - `/api/product-drafts/create` / `/api/products/draft/create`
  - `/api/products/create`
  - `/api/products/update`
  - `/api/products/delete`
  - `/api/products/finalize`
  - `/api/products/<id>/snapshot`
  - `/api/products/<id>/rollback`
- `routes.py` 4320-4397：`/api/session/new` 创建 product-bound session，设置 product_id/scope/intent/line/toolsets，并记录 product session。
- `routes.py` 7939-8018：`/api/chat/start` 解析 product context；build/init turn 前 snapshot，随后 record product session 为 generating。
- `routes.py` 8136-8165：legacy `/api/chat` sync path 也会解析 product context 并在 builder 前 snapshot。
- `streaming.py` 2798-2829：build/init turn 结束时 `finalize_product_generation()`。
- `streaming.py` 5190-5211：steer 时恢复 product context，并把 product ephemeral prompt prepend 到 steer text。

结构判断：

- 产品生命周期跨越三层：routes 入口绑定/snapshot，streaming finalize，products 落盘/preview/rollback。
- `/status` 是目前最安全的产品 read 入口，因为它会 reconcile。
- build/init turn 的顺序是：chat start 前 snapshot -> record generating -> streaming run -> finalize success/error/cancel/finally。

风险：

- 产品 GET/POST routes 仍塞在 10000+ 行 `routes.py` 里，分布位置远；未来新增 draft promote/preview 很容易继续膨胀。
- `/api/session/new` 会 record product session，但不 snapshot；真正 snapshot 在 `/api/chat/start`，这符合“只有真实 build turn 才 snapshot”，但需要文档化。
- `/api/chat/start` 对 snapshot 失败只是 debug log，不阻断 builder turn；如果 snapshot 失败，用户可能以为 rollback 可用但其实没有版本。
- `preview_product_file()` 的 404 会被 `_serve_product_preview/_serve_product_asset` 吞成统一 not found，缺少状态细节；前端只能再查 `/status`。
- `routes.py` 直接 import 产品服务函数，后续应迁到 `routes_products.py` 或 route registry。

## 41. 第九轮：`product-evolution.js` 和 productize marker

文件：

- `apps/webui/static/product-evolution.js`
- `apps/webui/static/ui.js`
- `apps/webui/api/product_context.py`
- `apps/webui/tests/test_product_scope_lines.py`

已读关键区段：

- `product-evolution.js` 1-32：只有 `rollbackCurrentProductUiVersion()`，读取 `_activeProductPreview`，POST `/api/products/<id>/rollback`，再 refresh preview。
- `ui.js` 2337-2369：定义 `NEXT_AI_SUGGEST_PRODUCT` marker 的 strip/parse/click 逻辑。
- `ui.js` 5672-5677：render assistant 最后一条消息时，把 marker 渲染成“做成专属产品”按钮。
- `product_context.py` 417-430：chat_only usage prompt 允许模型在可复用场景下输出 productize marker。
- `test_product_scope_lines.py` 208-234：测试 chat_only usage 有 marker 协议，canvas usage / chat_only builder 不应该有。

结构判断：

- `product-evolution.js` 这个名字现在不准确；它实际是 product UI rollback action。
- productize suggestion 是一条独立业务线：prompt 约束 -> assistant marker -> UI strip/parse -> createProductFromPrompt。
- productize marker 有基础测试覆盖 prompt 注入，但 UI parse/render/click 行为没有独立测试。

风险：

- marker 仍然是文本协议，和 hidden context 一样依赖正则剥离；流式中未闭合 marker 的显示处理靠 `_stripProductSuggestMarker()`。
- `_onProductSuggestClick()` 只传 prompt，marker 中的 `title/type` 没有进入 create draft payload；模型建议的类型信息会丢。
- productize click 会直接 `createProductFromPrompt(prompt)`，没有让用户确认/编辑 title/type。
- rollback action 依赖 `_activeProductPreview.can_rollback/previous_version`，如果 snapshot 失败但 UI 状态误显示可 rollback，会在点击时才失败。

## 42. 第十轮：`knead-product` skill 与 shipped product 契约

文件：

- `.agents/skills/knead-product/SKILL.md`
- `.agents/skills/knead-product/references/bridge.md`
- `.agents/skills/knead-product/references/layouts.md`
- `.agents/skills/knead-product/references/doc-site-generators.md`
- `.agents/skills/knead-product/templates/minimal-canvas.html`
- `products/general/product.json`
- `products/general/index.html`
- `products/general/about.html`
- `products/ppt-designer/product.json`
- `products/ppt-designer/index.html`
- `products/ppt-designer/app.js`
- `products/ppt-designer/state.json`
- `products/ai-otome/product.json`
- `products/ai-otome/index.html`
- `products/ai-otome/app.js`

已读关键区段：

- `SKILL.md`：产品是小型自包含 web canvas + `product.json`；适用于 `product_init` / `product_builder`，不适用于普通 product usage。
- `SKILL.md`：非平凡 UI 还要加载 `impeccable`；所有编辑必须限制在当前产品 workspace 内。
- `SKILL.md`：必须读 `product.json`、`layouts.md`、`bridge.md`，优先用 minimal-canvas 模板。
- `SKILL.md`：产品模型核心变量是 `product_layout`、`product_type`、`skills+tools`、`canvas_label`。
- `SKILL.md`：内部词不能出现在用户可见 UI：产品、canvas、画布、演化、version、manifest、sandbox、persona、scope。
- `bridge.md`：产品 app 必须先加载 `product-bridge-sdk.js`，再加载自身 `app.js`。
- `bridge.md`：画布通过 `NextAI.chat.send({ text, action, context })` 和宿主通信，不能直接调 chat/model API。
- `bridge.md`：`NextAI.state` 是耐久状态通道；不应在首屏 paint 前无限等待 `state.get`，应短 timeout 或先渲染默认状态。
- `bridge.md`：推荐用 workspace `state.json` 做 AI -> GUI 的结构化通道，避免解析聊天文本。
- `layouts.md`：`chat_only` 不应该生成 canvas 文件；`chat_left_canvas_right` 是左聊右工作台；`canvas_full` 让产品 UI 拥有主输入。
- `minimal-canvas.html`：模板非常克制，SDK 在 app script 前，符合当前 shipped products 的基本加载方式。
- `doc-site-generators.md`：这是截至 2025 的本地研究 memo，含 Docusaurus/Nextra/Fumadocs/Mintlify 等版本信息；如果用于 2026 当前选型，需要联网刷新，不应当作稳定产品契约。

真实产品核对：

- `products/general/product.json` 是 `chat_only`，`ui_status` ready，工具集包含 skills/file/terminal/code_execution。
- `products/general/index.html` 是 chat_only 的默认 seed 页面，基本符合“无 canvas 产品”的定位。
- `products/general/about.html` 是未追踪、未被 `preview_entry` 引用的独立介绍页；如果它是临时产物还好，如果要变成产品表面，会和 chat_only 契约冲突。
- `products/ppt-designer/product.json` 是 `chat_left_canvas_right`，skill/tool 声明和 PPT 工作流相符。
- `products/ppt-designer/index.html` 正确在 app 前加载 bridge SDK。
- `products/ppt-designer/app.js` 有 `NextAI.state` + localStorage fallback，`restore()` 用 1200ms timeout，符合 bridge 文档的 state 恢复原则。
- `products/ppt-designer/app.js` 的 agent reply 处理优先 `fetchStateFile()`，再 fallback 解析 reply；这和 `state.json` 作为 AI -> GUI 通道的建议一致。
- `products/ppt-designer/app.js` 启动末尾无条件 `applyDeckState(HEYTEA_DECK)`，会覆盖 `restore()` 和 `state.json`，这是明显契约违背。
- `products/ppt-designer/state.json` 当前也提交了喜茶 demo deck；如果这是示例，应移到显式 demo/seed 路径。
- `products/ai-otome/product.json` 是 `canvas_full`，工具集含 skills/image_gen，定位和伴侣游戏一致。
- `products/ai-otome/index.html` 正确在 app 前加载 bridge SDK。
- `products/ai-otome/app.js` 启动时 `await loadState(); render();`，会在首屏 paint 前等待 bridge state，不符合 `bridge.md` 的 first paint 建议。
- `products/ai-otome/app.js` 的普通聊天 `NextAI.chat.send()` 使用 `res.content`，和 SDK 当前返回形态匹配。
- `products/ai-otome/app.js` 的生图逻辑读取 `res.image_url || res.content_url`，但 SDK 返回 `{ content, raw }`，宿主 reply 目前也只下发 content/message；这是产品 app 和 host bridge 的 response shape 不一致。

结构判断：

- skill 文档比现有代码更清楚，已经可以反过来作为 shipped products 的 contract source。
- 两个 shipped canvas 产品都遵守“SDK 在 app 前加载”和“不直接调模型 API”的大方向。
- 真正需要修的是细契约：first paint、state 优先级、typed response、demo 数据隔离。
- `ppt-designer` 和 `ai-otome` 现在是很好的回归测试样本，因为它们分别覆盖 `chat_left_canvas_right` 和 `canvas_full`。

风险：

- 如果 `ppt-designer` 继续默认写入 `HEYTEA_DECK`，任何用户保存状态或 AI 生成的 `state.json` 都可能被覆盖，产品会看起来“生成成功但刷新后回到 demo”。
- 如果 `ai-otome` 首屏依赖 bridge state resolve，bridge 慢或异常时 canvas_full 产品会出现白屏/晚 paint。
- 如果 image response shape 不统一，产品 app 会继续靠猜字段工作；以后每个产品都会各写一套不兼容解析。
- `doc-site-generators.md` 的版本信息有时间敏感性，不能和稳定 contract 文档混在同一可信层级。

## 43. 第十一轮：`style.css` 产品样式层和覆盖顺序

文件：

- `apps/webui/static/style.css`

已读关键区段：

- `style.css` 628-682：product create/capabilities dialog。
- `style.css` 979-1182：早期 active product preview / canvas_full / adjust mode / resizer 样式。
- `style.css` 1407-1430：access/toolsets dropdown 基础样式。
- `style.css` 4102-4435：`Next AI MVP shell` 主题变量、sidebar、AI object list 基础 pass。
- `style.css` 4662-5034：product chat header、task chips、task context/progress。
- `style.css` 5040-5334：assistant home / create screen / task mode compact home。
- `style.css` 5590-5990：composer/toolsets、product-context strip、`chat_left_canvas_right` 两栏和 resizer。
- `style.css` 6040-6325：第二轮 product sidebar / AI object list / icon colors 覆盖。
- `style.css` 6391-6814：`Aura sidebar pass`，再次覆盖 sidebar、AI object list、product chat header、task chips、assistant home。
- `style.css` 6970-6997：末尾 mobile override，再次覆盖 product chat header / assistant home。

重复/覆盖最明显的选择器：

- `.ai-object-item`：4335、6191、6536 附近多轮定义；avatar/icon 状态也多次覆盖。
- `.product-chat-header`：4662、6646、6982 附近多轮定义。
- `.product-task-chip`：4742、6663 附近多轮定义。
- `.assistant-home`：5040、6700、6985 附近多轮定义。
- `.active-product-surface`：995 附近基础定义，1055/1086/1180/5900/5928 再按 layout 和 media 改写。
- `body[data-next-ai-*]` 状态选择器：1006-1182、5280-5334、5594-5705、5896-5984 多段共同决定布局。

结构判断：

- CSS 的问题不是只有行数多，而是“主题 pass / 产品 pass / 响应式 pass”互相压在一个文件里。
- 当前视觉很大程度依赖后写规则覆盖前写规则；因此不能直接把某一段搬走，必须先列状态表和 selector ownership。
- `canvas_full` 和 `chat_left_canvas_right` 的布局逻辑都依赖 `body.dataset` 组合，不是一个单独组件样式能解释完。
- `active-product-surface` 比较像可拆出的稳定边界；`assistant-home` 和 `.ai-object-item` 更像全局 shell 与产品目录混在一起，拆分前需要命名和 ownership 先定。

风险：

- 改 `.product-chat-header` 可能被 6646/6982 后续规则覆盖，看代码时容易以为改生效但实际没有。
- 改 `.ai-object-item` 的 avatar/icon 可能被 Aura pass 强制变成状态点，和前面 product icon 色板冲突。
- `@media(max-width:1100px)` 同时包含 canvas_full 的列布局回退和 chat_left_canvas_right 的两栏规则，移动时很容易改变 mobile/tablet 行为。
- CSS 缺少“这些 data-state 组合应该怎样显示”的测试或表格；视觉回归只能靠人工看。

## 44. 第十一轮：现有 product 测试覆盖

文件：

- `apps/webui/tests/test_product_scope_lines.py`
- `apps/webui/tests/test_product_ui_status.py`
- `apps/webui/tests/test_product_drafts.py`
- `apps/webui/tests/test_knead_product_skill.py`
- `apps/webui/tests/test_sprint9.py`

已读关键区段：

- `test_product_scope_lines.py`：覆盖 product line/scope、workspace guard、chat_only builder guard、productize marker、builder/use toolset 差异、file manifest、builder/use prompt framing。
- `test_product_ui_status.py`：覆盖 `_resolve_ui_status()` matrix、layout promotion、`product_file_status()` 纯读、`reconcile_product_status()` 持久化、`finalize_product_generation()` chat_only 场景。
- `test_product_drafts.py`：只覆盖 draft create 不注册到产品列表。
- `test_knead_product_skill.py`：覆盖 skill 文档结构、references 存在、template 中 bridge SDK 在 app 前、builder prompt 指向 knead-product/impeccable。
- `test_sprint9.py`：覆盖旧 split modules 顺序，但只包含 `ui.js/workspace.js/sessions.js/messages.js/panels.js/boot.js`，没有覆盖 product scripts。

测试验证：

- 失败的尝试：
  - `python -m pytest ...`：当前 shell 没有 `python`。
  - `python3 -m pytest ...`：系统 Python 没有 pytest。
  - `.venv/bin/python -m pytest ...`：`.venv` 没有 pytest。
- 成功命令：
  - `.venv311/bin/python -m pytest tests/test_product_scope_lines.py tests/test_product_ui_status.py tests/test_product_drafts.py tests/test_knead_product_skill.py`
- 结果：
  - 63 passed in 2.04s。
- 后续基线已更新：产品专项现在是 65 collected / 65 passed，见后文第 58 节和 TODO 9.5。

结构判断：

- 后端 product scope / status 纯逻辑已经有不错的测试支点，可以作为后续拆分 `product_context.py` / `products.py` 的护栏。
- skill 文档本身也已经被测试约束，这点很少见，是好事。
- 前端产品壳缺少相同级别的契约测试：DOM id、product script order、`body.dataset` state matrix、bridge host message flow、CSS ownership 都没被锁住。
- shipped products 的契约也没有测试：`ppt-designer` demo 覆盖、`ai-otome` first paint、bridge response shape 都是人工阅读发现的。

风险：

- 如果直接拆 `style.css`，现有测试基本不会发现 product shell 布局坏了。
- 如果调整 `index.html` 脚本顺序，现有 `test_sprint9.py` 不会发现 product runtime 相关顺序错位。
- 如果修改 bridge response shape，现有测试不会保护 AI Otome 的生图按钮。
- 如果继续扩 `api/products.py`，后端 status 测试会保护一部分，但 preview/snapshot/rollback/draft lifecycle 仍缺。

## 45. 第十二轮：`product-shell-runtime.js` 产品壳状态机

文件：

- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/product-store.js`
- `apps/webui/static/product-runtime.js`

已读关键区段：

- `product-shell-runtime.js` 1-56：全局 `_activeProductPreview`、默认 current AI、内置 `AI_OBJECTS`。
- `product-shell-runtime.js` 894-903：`nextAiDirectory` 的来源和写入。
- `product-shell-runtime.js` 960-1003：`syncAssistantForLoadedSession()` 处理 product-bound session；如果 product 尚未 hydrate，先返回 general，再异步 hydrate 后切回真实 product。
- `product-shell-runtime.js` 1223-1264：`selectAiObject()` 切 AI 时重置 `nextAiProductAdjust`、`nextAiChatPanel`、`nextAiChatPanelManual`，并写 `nextAiProductLayout`。
- `product-shell-runtime.js` 1538-1620：`_assistantTaskHasActiveTask()`、task context/progress 的显示条件。
- `product-shell-runtime.js` 1622-1688：`_syncProductPreviewCopy()` 更新 active product toolbar 文案和 rollback/capabilities actions。
- `product-shell-runtime.js` 1741-1794：`setCurrentProductAdjustMode()` / `setCurrentProductChatPanelMode()` 互斥控制调态和聊天面板。
- `product-shell-runtime.js` 1836-1914：task header chips 根据 adjust/chat/canvas 状态变成按钮。
- `product-shell-runtime.js` 1976-2070：`syncAssistantTaskUi()` 是产品壳 layout state 的主写入函数。
- `product-shell-runtime.js` 2074-2094：`deactivateProductPreviewInChat()` 关闭 preview 时清 chat panel manual state。
- `product-shell-runtime.js` 2100-2111：DOMContentLoaded 自启动 `initNextAiAssistants()`。
- `product-runtime.js` 509-529：`_hideProductPreviewIfActive()` 清 `_activeProductPreview`，并关 `nextAiChatPanel`。
- `product-runtime.js` 655-767：`refreshCurrentProductPreview()` 查 `/api/products/<id>/status`、写 `_activeProductPreview`、显示 surface、调用 `syncAssistantTaskUi()`。
- `product-store.js` 94-145：layout/canvas 判断：`chat_left_canvas_right` / `canvas_full` 显示 canvas；`chat_only` 若已有 generated canvas 会提升成 `chat_left_canvas_right`；`general` 永不就地长 canvas。
- `product-store.js` 372-399：`hydrateProductsFromBackend()` 异步把后端 products merge 到 `AI_OBJECTS`，最后调用 `selectAiObject(current)`。

状态机输入：

- 当前 AI：`window._currentAiAssistantKind` / `AI_OBJECTS[kind]`。
- 当前 session/task：`S.session`、`S.messages`、`S.busy`、`S.activeStreamId`。
- 当前 preview：`_activeProductPreview`。
- 产品模型：`productLayout`、`uiMode`、`productId`、`entryGenerated`、`productCanvasAvailable`。
- 用户显式 UI state：`nextAiProductAdjust`、`nextAiChatPanelManual`。

`syncAssistantTaskUi()` 写出的 layout state：

- `document.body.dataset.nextAiView`：`task` 当存在 active task，否则 `assistant`。
- `document.body.dataset.nextAiProductLayout`：来自 `_currentProductLayoutForTaskHeader()`。
- `document.body.dataset.nextAiCanvas`：`usesProductCanvas && _activeProductPreview ? open : closed`。
- `document.body.dataset.nextAiProductAdjust`：
  - 非可调整产品强制 `closed`。
  - 可调整产品默认 `closed`，由 `setCurrentProductAdjustMode()` 打开。
- `document.body.dataset.nextAiChatPanel`：
  - 无 task、无 canvas、或 `canvas_full` use mode：强制 `closed` 并清 `nextAiChatPanelManual`。
  - adjust 打开：强制 `closed`。
  - `chat_left_canvas_right` 且 canvas open：默认 `open`，除非 manual 关过。
  - 其它情况默认 `closed`。
- `document.body.dataset.nextAiDirectory`：由 `_syncAssistantSidebarDirectory()` 写；有 task 时强制 `product`，无 task 时尊重 library/product。
- `productChatBody.dataset.nextAiView`：镜像 task/assistant，但 CSS 主要依赖 body dataset。

典型状态组合：

- AI shelf：`nextAiView=assistant`，无 task，home 显示，messages shell 隐藏，active product surface 隐藏。
- chat_only task：`nextAiView=task`，`nextAiProductLayout=chat_only`，`nextAiCanvas=closed`。
- chat_left_canvas_right task，无 preview：`nextAiView=task`，layout 为 `chat_left_canvas_right`，`nextAiCanvas=closed`。
- chat_left_canvas_right task，有 preview：`nextAiCanvas=open`，`nextAiChatPanel=open` 默认显示两栏；手动关闭后为 `closed`。
- canvas_full use mode：有 task + preview 时 `nextAiCanvas=open`，messages shell 和 composer 被 CSS 隐藏；adjust 打开后左侧聊天/输入重新出现。
- product adjust：`nextAiProductAdjust=open` 时 `nextAiChatPanel=closed`，placeholder 变成“调整产品”语义。

结构判断：

- `syncAssistantTaskUi()` 现在既是状态 reducer，又直接更新 DOM 文案、placeholder、sidebar、header、home、progress；职责太宽。
- `_activeProductPreview` 是跨 `product-shell-runtime.js` 和 `product-runtime.js` 的全局状态，没有单一 owner。
- `product-store.js` 的 layout 判断和 backend schema 没有共享事实源，特别是 `chat_only + generated canvas -> chat_left_canvas_right` 这个隐式提升。
- `hydrateProductsFromBackend()` 和 `boot.js` session restore 并行，已有补救逻辑，但不是可等待阶段。

风险：

- 新增 layout 时需要同时改 `product-store.js`、`syncAssistantTaskUi()`、CSS、后端 normalize 和 skill 文档。
- `nextAiChatPanelManual` 只在部分路径清理；如果后续加入更多 canvas mode，可能继承旧手动状态。
- product-bound session 在 hydrate 前可能短暂显示 General AI。
- 如果某个地方直接改 `_activeProductPreview` 而不调用 `syncAssistantTaskUi()`，body dataset 和 DOM 会失配。

## 46. 第十二轮：`index.html` 产品 DOM / script contract

文件：

- `apps/webui/static/index.html`

已读关键区段：

- `index.html` 131-180：产品品牌、primary nav、AI shelf 静态项。
- `index.html` 220-237：product chat header 和 task status chips。
- `index.html` 238-337：assistant home、messages shell、task context/progress、pane resizer、active product surface/iframe/preview state。
- `index.html` 1129-1161：assistant create dialog。
- `index.html` 1164-1195：product capabilities dialog。
- `index.html` 1204-1214：前端脚本加载顺序。

产品壳核心 DOM id：

- Shell/sidebar：`assistantPanelTitle`、`assistantPanelSub`、`assistantProductBackBtn`、`assistantTaskListTitle`、`newTaskPrimaryBtn`、`newTaskPrimaryIcon`。
- Header/status：`productModeTitle`、`productCrumbRoot`、`taskHeaderChatStatus`、`taskHeaderProductStatus`、`taskHeaderAdjustToggle`。
- Home：`assistantHome`、`assistantHomeAvatar`、`assistantHomeEyebrow`、`assistantHomeTitle`、`assistantHomeDesc`、`assistantHomeGuide`、`assistantHomeOrigin`、`assistantHomeNextStep`、`assistantHomeManage`。
- Task context/progress：`assistantTaskContextStrip`、`assistantTaskContextKicker`、`assistantTaskContextTitle`、`assistantTaskContextDesc`、`assistantTaskProgress`、`assistantTaskProgressDot`、`assistantTaskProgressTitle`、`assistantTaskProgressDesc`、`assistantTaskProgressProductKicker`、`assistantTaskProgressProduct`。
- Active preview：`productChatBody`、`paneResizer`、`activeProductSurface`、`activeProductKicker`、`activeProductPreviewName`、`activeProductVersion`、`activeProductNote`、`collapseActiveProductBtn`、`activeProductMoreBtn`、`activeProductMoreMenu`、`regenerateProductUiBtn`、`rollbackActiveProductBtn`、`productCapabilitiesBtn`、`activeProductFrame`、`productPreviewState`、`productPreviewStateKicker`、`productPreviewStateTitle`、`productPreviewStateDesc`、`productPreviewStateAction`。
- Dialogs：`assistantCreateOverlay`、`assistantCreateClose`、`assistantCreateTitle`、`assistantCreateDesc`、`assistantCreateSource`、`assistantCreatePreviewAvatar`、`assistantCreateName`、`assistantCreateDuty`、`assistantCreateTasks`、`assistantCreateCancel`、`assistantCreateApply`、`productCapabilitiesOverlay`、`productCapabilitiesClose`、`productCapabilitiesTitle`、`productCapabilitiesDesc`、`productCapabilitiesSkills`、`productCapabilitiesExtraSkills`、`productCapabilitiesTools`、`productCapabilitiesExtraTools`、`productCapabilitiesStatus`、`productCapabilitiesSave`。

产品相关 inline handlers：

- `openAssistantLanding()`、`startAssistantNewTask()`、`openAssistantHome()`。
- `toggleCurrentProductAdjustMode()`、`setCurrentProductAdjustMode(false)`。
- `deactivateProductPreviewInChat()`、`toggleActiveProductPreviewMenu(event)`、`requestCurrentProductUiGeneration()`、`rollbackCurrentProductUiVersion()`、`openCurrentProductCapabilities()`、`openActiveProductPreviewWindow()`。
- `closeCurrentProductCapabilities()`、`saveCurrentProductCapabilities()`。

脚本顺序：

- `i18n.js`
- `icons.js`
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

静态验证：

- 命令：
  - `.venv311/bin/python - <<'PY' ...`
- 检查内容：
  - 第一批产品壳关键 id 是否存在。
  - `messages.js -> product-store.js -> product-shell-runtime.js -> product-runtime.js -> product-evolution.js -> panels.js -> onboarding.js -> boot.js` 顺序。
- 结果：
  - `missing_ids=[]`
  - `script_order_ok=True`

结构判断：

- 产品壳 DOM contract 实际上已经很集中，适合写静态测试。
- `product-shell-runtime.js` 依赖 `product-store.js` 的 helper；`product-runtime.js` 又依赖 `_activeProductPreview` 和 DOM；所以三者顺序必须固定。
- `product-evolution.js` 只提供 rollback，但必须在 HTML 中晚于 product runtime、早于用户点击；名字仍然误导。
- 现有 `test_sprint9.py` 没有把 product scripts 纳入顺序测试。

风险：

- 删除/改名上述任一 id，运行时多半只会静默降级或报前端错误，后端测试不会发现。
- inline handler 让全局函数名成为 DOM API；抽模块前要先保留 `window.*` compatibility。
- `activeProductFrame` sandbox 只有 `allow-scripts allow-forms`，下载和状态都依赖 postMessage bridge；不能把 iframe 逻辑当普通 preview。

## 47. 第十三轮：`product-runtime.js` / `product-bridge-sdk.js` bridge 协议

文件：

- `apps/webui/static/product-runtime.js`
- `apps/webui/static/product-bridge-sdk.js`
- `apps/webui/static/messages.js`
- `apps/webui/static/ui.js`
- `products/ppt-designer/app.js`
- `products/ai-otome/app.js`

已读关键区段：

- `product-runtime.js` 74-111：`currentAssistantProductContextForMessage()` 和 `withCurrentProductContext()` 生成 product scope / intent。
- `product-runtime.js` 180-220：product canvas state 的 host 侧 get/set/remove/clear。
- `product-runtime.js` 222-330：canvas -> host chat send，pending map、hidden instruction、ack。
- `product-runtime.js` 332-377：host -> canvas reply / agent broadcast / error。
- `product-runtime.js` 379-407：iframe postMessage host 侧入口和 download 代理。
- `product-bridge-sdk.js` 1-237：iframe 内 `window.NextAI` SDK。
- `messages.js` 407-416：读取并清空 `_nextAiPendingHiddenAgentInstruction`。
- `messages.js` 598-613：hidden instruction 拼进真正发送给后端的 `msgText`，再生成 product context。
- `messages.js` 1948-1960：SSE done 后回传 bridge reply，并广播 agent message。
- `messages.js` 2177-2184：SSE app error 后回传 bridge error。
- `ui.js` 3124-3128：queue drain 只恢复 product scope / intent，不恢复 product id。

host bridge 当前行为：

- iframe 必须发送 `{source:'nextai-product-canvas'}`。
- host 只接受 `event.source === _activeProductFrameWindow()` 的消息。因为 iframe sandbox 没有 `allow-same-origin`，origin 会是 opaque / `null`，这里用 source window 校验是合理的。
- `nextai:product:state`：
  - host 用 `localStorage` 保存。
  - key 形如 `nextai:product-state:<productId>:<scope>:<key>`。
  - scope 默认为 `product`；传 `session` 时落到 `session:<sessionId||draft>`。
- `nextai:product:send`：
  - host 先确保有 session。
  - pending request 以 session id 作为 key。
  - 写 `window._nextAiPendingProductScope` / `_nextAiPendingProductIntent` / `_nextAiPendingHiddenAgentInstruction`。
  - 把 iframe 的文本塞进 `#msg`，再调用全局 `send()`。
  - 先发 `nextai:host:ack`，真正 reply 等 SSE done。
- `nextai:product:download`：
  - host 对 iframe 给出的 URL 直接 `fetch()`，失败则 `window.open()`。
  - 当前只有“来源必须是当前 iframe”防线，没有 URL allowlist。

SDK 当前行为：

- `NextAI.chat.send(payload)` 发送 `nextai:product:send`，resolve 为 `{content, raw}`。
- `NextAI.product.send` 是同一个函数的 alias。
- `NextAI.state.get/set/remove` 发送 `nextai:product:state`，默认 5s timeout，失败后 fallback 到 iframe 内 safe localStorage。
- `nextai:host:ack` 只派发 `nextai:ack` 事件，不 resolve pending，也不刷新 timeout。
- `nextai:host:reply` / `nextai:host:state` resolve pending。
- `nextai:host:error` reject pending。
- `nextai:host:agent_message` 派发 `nextai:agent` 事件，用于 canvas 监听普通 host chat 回复。

真实产品使用方式：

- `ppt-designer`：
  - `product-bridge-sdk.js` 在 `app.js` 前加载。
  - `persist()` 用 `NextAI.state.set('ppt', state, {scope:'session'})`。
  - `restore()` 自己 race 了 1200ms timeout。
  - `exportPptx()` 通过 `nextai:product:download` 请求 host 下载 `/api/products/ppt-designer/preview/outputs/.../deck.pptx`。
  - 启动末尾仍有 `applyDeckState(HEYTEA_DECK)`，会覆盖保存状态或 `state.json`。
- `ai-otome`：
  - `loadState()` 在首屏 render 前 await `NextAI.state.get()`，bridge 慢时会阻塞 first paint。
  - 普通聊天只读 `res.content`，和 SDK 当前 shape 匹配。
  - 画像生成读 `res.image_url || res.content_url`，但 SDK 返回 typed 字段在 `res.raw`，host 当前 reply 又只发 `content`，所以这条契约实际不成立。

结构判断：

- 安全边界意识是有的：host 和 SDK 都用 `event.source` 做来源校验。
- bridge 协议还没有被写成正式 contract，字段 shape 靠调用方猜。
- `product-runtime.js` 同时承担 preview polling、scope 生成、state bridge、chat bridge、download bridge，职责偏宽。
- canvas send 现在通过写 `#msg` + 调全局 `send()` 接入聊天，这保留了现有流水线，但把 product bridge 和 UI composer 强耦合。
- hidden instruction 现在被拼到实际 message 文本里，再一起发到后端；可用，但会污染消息语义，也需要靠 sentinel 避免外显。
- pending request 以 session id 为 key；同一 session 内如果允许多个 canvas request，就需要更明确的 requestId 匹配规则。
- host 125s timeout 只删除 pending，不主动发 `nextai:host:error`；SDK 自己也有 timeout，所以用户侧会失败，但 canvas 收不到 host 语义化错误。
- host reply 当前只回 `{content}`，`message` / `raw` / `assets` 都没有传给 SDK；这解释了 AI Otome 生图字段不可靠。
- state 当前主要是 host localStorage，不是后端持久产品状态；它适合短期会话状态，不适合被当作产品事实来源。
- download 需要 URL allowlist，至少限制在当前 product 的 preview/assets/output 路径内。

应补的 contract：

- `NextAI.chat.send` request：
  - `text` / `message`
  - `action`
  - `scope` / `productScope`
  - `context`
  - `timeoutMs`
- `NextAI.chat.send` response：
  - `content`
  - `message`
  - `raw`
  - `assets[]` / `files[]`
  - 兼容字段如 `image_url` 应有明确来源和废弃策略。
- `NextAI.state`：
  - `product` scope 和 `session` scope 的持久化边界。
  - timeout / fallback 是否由 SDK 统一，不让每个产品 app 自己 race。
- `nextai:product:download`：
  - 允许的 URL 前缀。
  - filename 规则。
  - 失败时 host error，而不是静默 open。
- hidden instruction：
  - 从 message 文本迁到结构化请求字段。
  - 可见 user message 和内部 product instruction 分离。

风险：

- 如果先拆文件但不定义 bridge contract，AI Otome / PPT Designer 这类产品仍然会各猜各的字段。
- 如果先 TS 化但保留隐式文本 sentinel 和裸全局 pending state，TS 只能约束表面字段，不能解决协议语义。
- 如果未来 iframe 获得更多 sandbox 权限，当前 download URL 代理必须重新审计。

## 48. 第十四轮：后端 product registry / context / streaming lifecycle

文件：

- `apps/webui/api/products.py`
- `apps/webui/api/product_context.py`
- `apps/webui/api/routes.py`
- `apps/webui/api/streaming.py`
- `apps/webui/tests/test_product_ui_status.py`
- `apps/webui/tests/test_product_scope_lines.py`
- `apps/webui/tests/test_product_drafts.py`

文件体量：

- `routes.py`：10711 行。
- `streaming.py`：5534 行。
- `products.py`：1261 行。
- `product_context.py`：432 行。

已读关键区段：

- `products.py` 1-180：built-in products、toolset alias、project/products root。
- `products.py` 180-430：seed HTML、state read/write、product normalize、builtins ensure。
- `products.py` 430-720：seed files、manifest write、workspace register、ui status derivation、list/get/create/draft。
- `products.py` 720-1045：update/delete、snapshot file selection、manifest patch、snapshot、rollback。
- `products.py` 1045-1261：record session、entry seed detection、layout promotion、finalize/reconcile/status/preview path。
- `product_context.py` 1-160：scope inference、session request body restore。
- `product_context.py` 160-238：product context construction、build/use line、workspace guard、toolset selection。
- `product_context.py` 238-432：ephemeral prompt builder，含 builder/use/ppt/productize 特例。
- `routes.py` 3816-3841：GET `/api/products`、versions、status、preview serving。
- `routes.py` 4347-4394：new session 时绑定 product context。
- `routes.py` 5114-5169：product draft/create/update/delete/finalize/snapshot/rollback POST。
- `routes.py` 5916-5956：product preview/asset serving。
- `routes.py` 7634-7653：product task title 和 toolsets normalize。
- `routes.py` 7709-7805：`_start_chat_stream_for_session()` 写 pending state、product metadata、turn journal。
- `routes.py` 7984-8077：`/api/chat/start` 恢复/解析 product context、snapshot、record session、启动 stream。
- `routes.py` 8146-8249：sync chat fallback 注入 product context。
- `streaming.py` 149-159：`_webui_ephemeral_system_prompt()` 组合 progress/personality/product prompt。
- `streaming.py` 2796-2835：product turn finalize guard。
- `streaming.py` 3887-3894：streaming agent 注入 product ephemeral prompt。
- `streaming.py` 4245、4813、5074、5093：error/done/except/finally 的 product finalize 调用点。
- `streaming.py` 5189-5222：steer 时恢复 product context。

后端 product registry 当前设计：

- `product.json` / registry 字段会被 `_normalize_product()` 归一化。
- built-in products 会被 `_ensure_builtin_products_locked()` 自动写入 registry、seed workspace、注册 workspace。
- `list_products()` 是展示入口，会派生 `entry_generated`、`product_canvas_available`，但不持久化状态。
- `get_product()` 返回 registry 中的 stored product，不派生文件状态。
- `product_file_status()` 是 pure read：看磁盘入口文件、seed 状态、assets，派生 ui_status，但不写回。
- `reconcile_product_status()` 是显式写入点：修 timed-out generating、missing entry、layout promotion。
- `finalize_product_generation()` 是生成结束写入点：读 workspace `product.json` 的窄字段 patch，派生 ready/failed，做 layout promotion，写 error 信息。
- `record_product_session()` 记录 last session；build/init 且非 chat_only 时会把产品标为 generating。
- `preview_product_file()` 直接 `_read_state()`，没有走 `get_product()` / builtins ensure，这和 status/list 路径不一致。

值得保留的设计：

- `_resolve_ui_status()` 是纯函数，并且有清晰规则表。
- `product_file_status()` pure read、`reconcile_product_status()` explicit write 的边界是对的。
- `finalize_product_generation()` 只允许从 workspace `product.json` 回写窄字段，避免产品代码任意改 shell registry。
- build/use line 的工具隔离清楚：build line 强制含 file/terminal/code_execution，use line 保持产品自己的轻工具。
- build line workspace guard 只允许写产品目录；use line 可以在普通任务 workspace 执行。

主要问题：

- `products.py` 同时负责 registry、workspace、manifest、draft、status、snapshot、rollback、preview path，职责太多。
- `update_product()` 的副作用很多：更新 registry、写 seed、写 manifest；后续拆模块前需要测试钉住。
- `create_product_draft()` 只有 create；没有 promote/register、cancel/delete、preview、cleanup。
- `snapshot_product()` / `rollback_product()` 有安全意识，但测试缺 include/exclude、删除 managed file、manifest patch 回写。
- `preview_product_file()` 路径安全有做 `relative_to(root)`，但不 ensure builtins；直接打开 built-in preview 可能依赖之前访问过 `/api/products`。
- `product_context_from_request()` 用 stored `ui_status` 决定是否自动切 `product_init`，如果状态 drift，scope 可能不准。

后端 product context 当前设计：

- explicit scope 优先；regex 只在没有 explicit scope 时兜底。
- `product_context_request_body()` 会从 product-bound session 恢复 product_id、scope、intent。
- build line：
  - scope 为 `product_init` / `product_builder`。
  - workspace 必须等于产品 workspace。
  - toolset = builder base toolset + 产品自身 tools。
  - 附带 product workspace 顶层 file manifest。
- use line：
  - scope 为 `product_usage`。
  - 不强制 workspace 是产品目录。
  - toolset 使用产品自身 tools，不加 file/terminal。
- `product_ephemeral_prompt()` 同时包含：
  - product identity。
  - init/build/use scope guidance。
  - builder prompt。
  - use prompt。
  - `ppt-designer` 特例。
  - chat_only productize marker 协议。

结构判断：

- `product_context.py` 的状态模型比前端清楚，但 `product_ephemeral_prompt()` 已经是 prompt monolith。
- PPT Designer 的 canvas contract 写死在后端 prompt 里，和 product app / skill contract 需要同步，否则容易漂移。
- productize marker 属于 chat_only use prompt，但渲染/点击逻辑在前端 `ui.js`；这需要明确为一个协议。

routes / streaming 当前链路：

- new session：
  - `product_context_from_request()` 解析 context。
  - 写 `s.product_id`、`s.product_scope`、`s.product_intent`、`s.product_line`。
  - 没有用户显式 toolsets 时，用 product context tools 填 session toolsets。
  - build/init 且非 chat_only 时 `record_product_session(..., ui_status="generating")`。
- chat start：
  - `product_context_request_body()` 先从 session 恢复 product fields。
  - `product_context_from_request()` 再做 scope/line/tool/workspace guard。
  - build/init 前 `snapshot_product()`。
  - `record_product_session()` 标 generating。
  - `_start_chat_stream_for_session()` 再写 session product metadata 和 turn journal product block。
- streaming：
  - agent 用 `_webui_ephemeral_system_prompt(personality, product_prompt)` 注入产品 prompt。
  - done path 调 `_finalize_product_turn(failed=False)`。
  - provider/app error path 调 `_finalize_product_turn(failed=True, error_type, error_message)`。
  - cancel path用 `_put_cancel()`，内部 failed finalize。
  - finally path会兜底 `_finalize_product_turn(failed=True)`，但 guard 避免覆盖已成功 finalize。
- steer：
  - 尝试恢复 product context。
  - build/init steer 会把 product prompt 直接拼到 steer text 前。

结构问题：

- product route 分散在主 `routes.py` 的 GET、POST、serve helper、chat start、sync chat、stream helper 多段里。
- chat start 和 new session 有一段相似的 product binding/toolsets/session metadata 逻辑。
- streaming product finalize 逻辑在巨型 `_run_agent_streaming()` 内部闭包里；正确但难测。
- `product_context_request_body()`、`product_context_from_request()`、snapshot、record session、start stream 组合很关键，但缺集成级测试。

测试现状：

- `test_product_ui_status.py` 覆盖：
  - `_resolve_ui_status()` 矩阵。
  - layout promotion。
  - `product_file_status()` pure read。
  - `reconcile_product_status()` 持久化。
  - chat_only manifest finalize。
- `test_product_scope_lines.py` 覆盖：
  - `Session.product_line`。
  - explicit scope 不被 regex 覆盖。
  - build/use line derivation。
  - build workspace guard。
  - session line 恢复 scope。
  - chat_only builder guard、productize marker、builder/use toolset。
- `test_product_drafts.py` 只覆盖：
  - create draft 不进入 list_products。

测试缺口：

- product preview/asset serving：默认 index、嵌套 asset、path traversal、built-in preview direct access。
- snapshot/rollback：seed skip、exclude dirs、hidden files、大文件、rollback 删除 managed file。
- manifest patch：只允许白名单字段。
- chat start product lifecycle：build/init 前 snapshot、record generating、session product fields、toolsets。
- streaming finalize：done/error/cancel/finally guard。
- product_context status drift：stored ready/missing entry、generating timeout。

## 49. 第十五轮：Session product metadata / frontend message turn lifecycle

文件：

- `apps/webui/api/models.py`
- `apps/webui/static/messages.js`
- `apps/webui/static/sessions.js`
- `apps/webui/static/ui.js`
- `apps/webui/static/product-runtime.js`
- `apps/webui/static/product-shell-runtime.js`

已读关键区段：

- `models.py` 350-455：`Session.__init__()` 接收 `product_id`、`product_scope`、`product_intent`、`product_line`。
- `models.py` 455-570：`Session.save()` 的 metadata fields 包含 product 四字段，写在 `messages` 之前。
- `models.py` 570-620：`load()` / `load_metadata_only()` 都会通过 `Session(**parsed)` 恢复 product fields。
- `models.py` 617-705：`compact()` 在有 `product_id` 时输出 `product_id/product_scope/product_intent/product_line`。
- `models.py` 94-180：`_write_session_index()` 用 `s.compact()` 写 sidebar index。
- `models.py` 1200-1590：`all_sessions()` index/full-scan 两条路径都基于 compact，product fields 会进入 session list。
- `messages.js` 55-203：product status card helper、product context 写入当前 session、失败持久化。
- `messages.js` 390-760：`send()` 主流程，含 busy queue、product context、running card、`/api/chat/start` payload。
- `messages.js` 760-930：`attachLiveStream()` 初始化 INFLIGHT 和 durable inflight state。
- `messages.js` 1800-2000：SSE `done`，bridge reply、preview refresh、product status card done/failed。
- `messages.js` 2140-2305：SSE `apperror` / network error / cancel 的 product status card failed。
- `messages.js` 2310-2415：`_restoreSettledSession()` 和 `_handleStreamError()`。
- `sessions.js` 440-490：`newSession()` 把 product fields 发给 `/api/session/new`，并写回 `S.session`。
- `sessions.js` 580-740：`loadSession()` 恢复 active stream、INFLIGHT、durable inflight state、reattach SSE。
- `product-runtime.js` 50-115：`currentAssistantProductContextForMessage()` / `withCurrentProductContext()`。
- `ui.js` 122-145：`queueSessionMessage()` / `shiftQueuedSessionMessage()`。
- `ui.js` 3100-3135：queue drain 恢复 product scope/intent。
- `ui.js` 3218-3235：queue merge 保留 product_id/scope/intent。

Session product metadata 结论：

- `Session` 的 product 四字段保存链路是完整的：
  - constructor 接收。
  - save 写入 metadata。
  - load 和 metadata-only load 读取。
  - compact 输出给前端。
  - session index 写 compact。
  - all_sessions index/full-scan 都保留。
- `product_line` 只接受 `use` / `build`；compact 默认 `use`，保证旧会话兼容。
- metadata-only load 能读 product fields，因为 save 把它们放在 `messages` 字段之前。

frontend product turn 生命周期：

1. 用户发送：
   - `send()` 从 `#msg` 拿 text。
   - 如果有 `_nextAiPendingHiddenAgentInstruction`，会拼到 `msgText` 后面。
   - `currentAssistantProductContextForMessage(text || msgText)` 生成 product context。
   - `_applyProductContextToCurrentSession()` 乐观写 `S.session.product_id/scope/intent`。
   - `product_init/product_builder` 会生成 `productUiStatusContext`。
   - `S.messages` 追加 user message；build/init 同时追加 running status card。
   - `INFLIGHT[activeSid]` 保存 messages、uploaded、toolCalls、`productUiStatusContext`。
   - `saveInflightState()` 持久化 inflight state 到 localStorage。
   - `/api/chat/start` payload 合并 product context。

2. SSE done：
   - 从 `INFLIGHT[activeSid].productUiStatusContext` 取状态卡上下文。
   - 清 INFLIGHT / durable inflight state。
   - 用 server done 的 `d.session` 覆盖 `S.session/S.messages`。
   - `notifyProductCanvasAgentReply()` 只把最后 assistant 文本回 bridge。
   - `broadcastAgentMessageToCanvas()` 广播普通 agent message。
   - adjust mode 下 `reloadActiveProductPreview()`。
   - `refreshCurrentProductPreview({reason:'stream-done'})`。
   - build/init 依据 runtime `uiStatus` 追加 done/failed status card，并可显示 rollback。
   - build/init 还会 900ms 后 late refresh。

3. SSE app error：
   - 从 inflight 取 product context。
   - 追加 assistant error。
   - 通知 bridge error。
   - 追加 failed status card。
   - `_markProductUiFailed()` 调 `_setProductUiStatus(..., 'failed', persist:true)` 或 `/api/products/update`。

4. SSE cancel：
   - 从 inflight 取 product context。
   - 拉最新 session，或本地追加 cancel error。
   - 追加 failed status card。
   - `_markProductUiFailed(..., 'product-ui-cancelled')`。

5. network error / settled restore：
   - network error 会尝试 reconnect。
   - 若 server stream 已结束，会调用 `_restoreSettledSession()` 拉 session。
   - `_restoreSettledSession()` 目前只恢复 transcript/tool calls/sidebar/idle state。
   - 它没有做 product preview refresh、bridge reply、product status card done/failed。
   - `_handleStreamError()` 会追加 connection lost，并把 product status 标 failed。

6. load session / reload：
   - `loadSession()` 如果 session 有 `active_stream_id`，会从 `loadInflightState()` 恢复 durable inflight，包括 `productUiStatusContext`。
   - INFLIGHT 分支会 merge live tail、恢复 tool cards、reattach SSE。
   - `syncAssistantForLoadedSession(session)` 用 `session.product_id` 切回产品 AI object。
   - 如果产品还没 hydrate，会 `hydrateProductsFromBackend()` 后再 select product 并 refresh preview。

queue 结论：

- queue item 可以保存完整 product context：
  - busy branch 通过 `withCurrentProductContext()` 保存。
  - chat/start conflict queue 直接 spread `productContext`。
  - queue merge 保留 `product_id/product_scope/product_intent`。
- 但 drain 时 `setBusy(false)` 只恢复：
  - `window._nextAiPendingProductScope`
  - `window._nextAiPendingProductIntent`
- drain 没有恢复 `product_id`。
- 下一次 `send()` 会重新调用 `currentAssistantProductContextForMessage()`，依赖当前选中的 product object 来补 `product_id`。
- 如果用户在排队期间切换产品，queued product turn 可能落到当前产品，而不是原始 queued product。

结构判断：

- Session product metadata 链路清晰，没发现明显漏项。
- `messages.js` 的 product turn 生命周期过宽：send、queue、status card、bridge、SSE done/error/cancel、connection restore 全在一个文件。
- `_restoreSettledSession()` 和 `done` path 不等价，这是产品 UI 状态的恢复缺口。
- queue product_id 只在存储层完整，消费层丢了关键字段。
- `productUiStatusContext` 的 durable inflight 持久化是好设计，但缺测试钉住。

测试现状：

- 现有测试覆盖许多 generic streaming/inflight：
  - `send()` active stream button。
  - queue functions 存在。
  - active_stream_id / pending_user_message。
  - INFLIGHT durable state。
  - restore settled session 的一些通用行为。
- 现有测试没有单独覆盖：
  - `productUiStatusContext` durable save/load。
  - `done` / `apperror` / `cancel` / `_restoreSettledSession()` 的 product UI 状态一致性。
  - queue drain 恢复 product_id。
  - bridge reply shape 对 product app typed response 的影响。

## 50. 第十六轮：`product-store.js` 前端产品模型 / hydrate / capabilities

文件：

- `apps/webui/static/product-store.js`
- `apps/webui/api/product_context.py`
- `apps/webui/api/products.py`

已读关键区段：

- `product-store.js` 1-140：前端 toolset alias、capability label、默认 capability、layout/canvas pure helpers。
- `product-store.js` 140-250：`_productToCustomAssistant()` 后端 product -> 前端 AI object adapter。
- `product-store.js` 250-370：`hydrateProductsFromBackend()`、本地 UI status patch、preview URL 解析。
- `product-store.js` 370-555：能力面板、tool/capability 读写、当前产品 session defaults。
- `product_context.py` 1-90：后端 `PRODUCT_TOOLSET_ALIASES`。
- `products.py` 95-135：后端 layout normalization / default layout。

结构结论：

- `product-store.js` 不是简单 store，它至少承担四类职责：
  - 前端 product model：layout、canvas availability、toolset normalize。
  - adapter：后端 `product` 转前端 `AI_OBJECTS`。
  - hydrate/cache：拉 `/api/products` 并把 custom product 写入全局对象。
  - settings UI：能力/工具面板的读写。
- 前端复制了不少后端事实：
  - `NEXT_AI_PRODUCT_TOOLSET_ALIASES` 复制 `PRODUCT_TOOLSET_ALIASES`。
  - `_assistantDefaultCapabilities()` 和后端 `suggest_product_capabilities()` 思路重复。
  - `_assistantNormalizeProductLayout()` 和后端 layout normalize 重复。
  - `_assistantHasGeneratedProductCanvas()` / `_assistantEffectiveProductLayout()` 体现了前端独有 canvas promotion 规则。
- 规则本身大体合理：
  - `chat_only` 默认不显示 canvas。
  - `ppt/research/data/image` 默认 `chat_left_canvas_right`。
  - generated canvas 可以把 `chat_only` 提升成 `chat_left_canvas_right`。
  - `general` 被特别保护，不会就地长出 canvas。
- 但这些规则散在 JS/Python/skill/manifest 之间，缺少单一 schema/fixture 对齐。

`_productToCustomAssistant()` 观察：

- 它是当前前端产品 adapter 的事实入口。
- 字段翻译覆盖较完整：
  - `product_id` -> `productId`
  - `workspace_path` -> `workspacePath`
  - `preview_url` -> `previewUrl`
  - `ui_status` -> `uiStatus`
  - `product_layout` / `layout` -> `productLayout`
  - `canvas_label` -> `canvasLabel`
- ready preview 判断是组合逻辑：
  - 有 `preview_url`
  - `ui_status === ready`
  - 非 `chat_only`
- canvas availability 判断还包含：
  - `entry_generated`
  - `product_canvas_available`
  - `uiStatus === generating`
  - `hasReadyPreview`
- 这说明“产品有没有画布”不是 manifest 单字段，而是 layout、status、生成产物共同决定。

hydrate 观察：

- `hydrateProductsFromBackend()` 拉 `/api/products` 后：
  - map 成 product-backed assistant。
  - 应用 built-in copy override。
  - 写入 `_backendProductAssistants`。
  - 删除已经不存在的后端 custom assistant。
  - 重新 render shelf。
  - 尝试保持 current selection，否则回到 general。
- 这个函数和 `product-shell-runtime.js` 的 `syncAssistantForLoadedSession()` 强耦合：
  - loaded session 如果有 `product_id` 但当前还找不到 kind，会等待 hydrate 后再切回 product。

能力面板观察：

- `openCurrentProductCapabilities()` / `saveCurrentProductCapabilities()` 直接读写 `/api/products/update`。
- 选项来源是前端常量，未知 capability/tool 会被保留成 extra item。
- 这对兼容旧数据有好处，但也说明 schema 没有统一事实源。

维护性判断：

- 这部分代码逻辑并不“错”，但文件名和职责不匹配。
- 最自然的拆分顺序：
  - `product-model.js`：layout/tool/status/canvas pure rules。
  - `product-adapter.js`：backend product -> frontend object。
  - `product-capabilities.js`：能力/工具选项、label、defaults。
  - `product-hydrate-store.js`：拉取、缓存、更新 UI status。
- TS 可以先从这些 pure/adaptor 模块开始，因为输入输出相对稳定。

测试缺口：

- 前后端 toolset alias fixture parity。
- default capability parity。
- layout normalize parity。
- `general` 永不就地生成 canvas。
- generated canvas promotion。
- `_productToCustomAssistant()` 对 ready/generating/empty/failed 的 canvas availability。
- hydrate 慢于 session restore 时，product-bound session 最终切回正确 product。

## 51. 第十七轮：`product-shell-runtime.js` session/product ownership

文件：

- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/product-store.js`
- `apps/webui/static/ui.js`
- `apps/webui/static/sessions.js`

已读关键区段：

- `product-shell-runtime.js` 1-180：`AI_OBJECTS` builtins、assignment localStorage、custom assistant helpers。
- `product-shell-runtime.js` 180-380：custom product registration、list meta、delete assignment cleanup。
- `product-shell-runtime.js` 760-880：draft product 创建、重命名、删除。
- `product-shell-runtime.js` 880-1075：session -> assistant kind 归属、loaded session 同步、task filtering。
- `product-shell-runtime.js` 1200-1325：`selectAiObject()`、`startAssistantNewTask()`、`openAssistantHome()`。
- `product-shell-runtime.js` 1450-1700：task title hydration、active task 判断、task context/progress、preview copy。
- `product-shell-runtime.js` 1700-1815：header 打开/关闭 workspace、adjust/chat panel state。
- `product-shell-runtime.js` 1940-2155：`syncAssistantTaskUi()`、body dataset、preview deactivate、init。

产品/会话归属链路：

1. 当前产品：
   - `_assistantKey()` 从 `window._currentAiAssistantKind` 取当前 AI/product kind。
   - `_assistantObject()` 从全局 `AI_OBJECTS` 取对象。

2. 老任务 assignment：
   - localStorage key：`next-ai-session-assistant-assignments`。
   - `markSessionForCurrentAssistant()` 把 session id -> 当前 kind 写进去。
   - 删除 custom product 时会清掉指向该 kind 的 assignment。

3. 新产品 session：
   - `assistantKindForLoadedSession(session)` 优先读 `session.product_id/productId`。
   - 找到 product kind 就返回对应 product。
   - 有 `product_id` 但本地找不到 product kind 时，先返回 general。
   - `syncAssistantForLoadedSession()` 会触发 `hydrateProductsFromBackend()`，hydrate 后如果当前 session 仍是该 product id，再 `selectAiObject(hydratedKind)` 并 refresh preview。

4. 旧 session fallback：
   - 没有 product id 时，读 `session.next_ai_assistant_kind` 或 localStorage assignment。
   - 还没有 assignment 时，用 `_assistantKindFromLegacySession()` 从标题/消息关键词猜 ppt/data/research。
   - 无法推断则归 general。

5. task list filtering：
   - `filterSessionsForCurrentAssistant()` 调 `assistantTaskBelongsToCurrentAssistant()`。
   - 该函数主要看 `next_ai_assistant_kind/localStorage assignment`。
   - 这里没有优先用 `session.product_id`。

重要不一致：

- loaded session 的产品选择优先 `product_id`。
- task list filtering 仍主要依赖 assignment / heuristic。
- 如果 session index 已经带 product_id，但没有 assignment，任务列表归属可能不如 loaded session 精准。
- 这不是立即错误，因为新任务通常会 `markSessionForCurrentAssistant()`；但它是隐式状态债。

`selectAiObject()` 观察：

- 它不只是“选择产品”：
  - 写 `window._currentAiAssistantKind/title`。
  - 写 `body.dataset.nextAiProductLayout`。
  - 清 adjust/chat panel manual state。
  - 更新 empty/home/title/input placeholder/suggestions。
  - `syncAssistantTaskUi()`。
  - `syncAssistantListMeta()`。
  - 如果有 active task 和 preview URL，refresh preview。
  - 否则 hide preview。
  - rerender session list cache。
- 这说明 selection、view sync、preview lifecycle、session list 都耦合在一个函数里。

`syncAssistantTaskUi()` 观察：

- 它是产品 shell 的 layout reducer，但当前直接操作 DOM。
- 输入事实包括：
  - 当前 assistant object。
  - 是否有 active task。
  - product layout。
  - 是否能显示 canvas。
  - `_activeProductPreview`。
  - adjust/chat panel manual state。
- 输出状态包括：
  - `body.dataset.nextAiView`
  - `body.dataset.nextAiProductLayout`
  - `body.dataset.nextAiCanvas`
  - `body.dataset.nextAiProductAdjust`
  - `body.dataset.nextAiChatPanel`
  - home/messages/surface/header/sidebar/progress 的显示。
- 这是非常适合抽成 pure reducer 的位置。

结构判断：

- `product-shell-runtime.js` 的问题不是某段写法明显错误，而是单文件职责过多：
  - built-in AI object registry。
  - custom product registration。
  - product draft creation。
  - product rename/delete。
  - session -> product ownership。
  - task title hydration。
  - task list filtering。
  - active preview copy。
  - layout dataset reducer。
  - adjust/chat panel controls。
  - splitter drag behavior。
- 文件名叫 runtime，但实际混合 model/store/view/controller。
- 这里不适合直接 TS 重写；应该先抽纯归属和 layout reducer。

优先拆分建议：

- `product-session-owner.js`
  - `assistantKindForLoadedSession`
  - `assistantTaskBelongsToCurrentAssistant`
  - assignment read/write
  - legacy inference
  - 统一优先 `product_id`
- `product-shell-state.js`
  - 从 object/hasTask/preview/manual state 得出 body dataset 和 UI visibility。
- `product-selection-controller.js`
  - `selectAiObject()` 的副作用分层：state update、DOM update、preview refresh、session list refresh。
- `product-draft-client.js`
  - draft create/rename/delete 与 shell view 分离。

测试缺口：

- `assistantKindForLoadedSession()` 对 product_id、missing hydrated product、legacy assignment、invalid assignment 的矩阵。
- `assistantTaskBelongsToCurrentAssistant()` 应优先识别 `session.product_id`。
- hydrate 慢于 session restore 时不闪到错误 product，或至少最终状态有测试。
- `selectAiObject()` 切换产品时清理 adjust/chat panel manual state。
- `syncAssistantTaskUi()` 的 body dataset 状态组合快照。

## 52. 第十八轮：product rollback / boot / panels 启动链路复核

文件：

- `apps/webui/static/product-evolution.js`
- `apps/webui/static/boot.js`
- `apps/webui/static/panels.js`
- `apps/webui/static/sessions.js`
- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/index.html`
- `apps/webui/tests/test_sprint9.py`

已读关键区段：

- `product-evolution.js` 1-32：`rollbackCurrentProductUiVersion()` 全文。
- `boot.js` 1360-1535：settings/profile/model/appearance boot。
- `boot.js` 1530-1705：workspace/session restore、saved/url session、BFCache `pageshow`。
- `sessions.js` 560-760：`loadSession()` metadata、inflight restore、`syncAssistantForLoadedSession()` 调用点。
- `sessions.js` 760-840：`loadSession()` 完成阶段。
- `sessions.js` 2687-2755：`renderSessionListFromCache()` task list filter。
- `sessions.js` 3090-3125：library mode 下 session product chip。
- `product-shell-runtime.js` 1425-1440：`assistantChromeTitleState()`。
- `product-shell-runtime.js` 2100-2112：`initNextAiAssistants()` 自启动。
- `panels.js` 1-240：app titlebar、settings guard、`switchPanel()`。
- `index.html` 1198-1214：defer script order。
- `test_sprint9.py` 60-85：旧 split module 顺序测试。

`product-evolution.js` 结论：

- 文件实际只有 rollback recovery action，不承担“产品演化”模型。
- rollback 直接读取裸全局 `_activeProductPreview`。
- rollback 直接调用：
  - `/api/products/<id>/rollback`
  - `_applyBackendProductToLocal(data.product)`
  - `refreshCurrentProductPreview({reason:'product-rollback'})`
- 文案仍然是“产品界面”，而其他地方已逐步改成 workspace。
- 结构判断：
  - 这段代码本身不复杂。
  - 文件名不准确，容易让人以为这里是 evolution/domain model。
  - 后续更适合并入 `product-preview-controller.js` 或改名 `product-recovery-actions.js`。
  - `_activeProductPreview` 应通过 preview controller API 读取。

boot 启动链路：

1. `index.html` defer script order：
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

2. product shell 自启动：
   - `product-shell-runtime.js` 定义 `AI_OBJECTS` 默认 general/ppt/create。
   - DOM ready 时 `initNextAiAssistants()`：
     - 清 legacy `next-ai-custom-assistants`。
     - `renderAssistantList()`。
     - 异步 `hydrateProductsFromBackend()`，没有 await。
     - `syncAssistantListMeta()`。
     - `syncAssistantTaskUi()`。

3. boot IIFE：
   - 拉 `/api/settings`。
   - 应用 theme/skin/font/i18n。
   - `applyBotName()`，内部会 `syncAssistantTaskUi()`。
   - 拉 active profile。
   - 非阻塞 model dropdown。
   - `loadWorkspaceList()`。
   - onboarding 可限时等待。
   - `renderSessionList()`。
   - 如果有 url/saved session，`loadSession(saved)`。
   - 根据 session/workspace/panel pref 恢复 workspace panel。
   - `checkInflightOnBoot(saved)`。
   - 启动 gateway SSE。

4. `loadSession()` 中的产品恢复：
   - metadata 进来后设置 `S.session=data.session`。
   - 立即调用 `syncAssistantForLoadedSession(S.session)`。
   - inflight restore 分支、idle 分支后还会再次调用 `syncAssistantForLoadedSession(S.session)`。
   - 这说明 product selection 恢复不在 boot phase，而分散在 session load 各阶段。

5. product-bound session hydrate fallback：
   - `assistantKindForLoadedSession()` 优先看 `session.product_id`。
   - 如果本地还没有 product kind，先返回 general。
   - `syncAssistantForLoadedSession()` 会异步 `hydrateProductsFromBackend()`，hydrate 后确认当前 session 还是同一个 product id，再 `selectAiObject(hydratedKind)` 并 refresh preview。

6. BFCache：
   - `pageshow(event.persisted)` 会重新 `loadSession(S.session.session_id)`。
   - 然后 `checkInflightOnBoot()`、`syncTopbar()`、`syncWorkspacePanelState()`、`renderSessionListFromCache()`、`startGatewaySSE()`。
   - 这里也没有显式等待产品 hydrate；依赖 `loadSession()` 里的补救。

结构判断：

- 当前启动链路能兜住不少真实问题，但可读性偏低：
  - product hydrate 是 product shell 自启动。
  - session restore 是 boot 自启动。
  - product-bound session 的最终正确性靠 `syncAssistantForLoadedSession()` 的补救。
  - BFCache 也是走 loadSession 补救。
- 这不一定导致功能错，但维护者要跨 `index.html`、`product-shell-runtime.js`、`boot.js`、`sessions.js`、`product-store.js` 才能证明顺序。
- 更好的结构是显式 boot controller：
  - settings/profile。
  - product defaults registered。
  - products hydrated 或 products hydration promise established。
  - saved/url session restored。
  - product selection reconciled。
  - preview refresh。
  - gateway/BFCache hooks。

task list 和 product ownership：

- `renderSessionListFromCache()` 在 product directory mode 下调用 `filterSessionsForCurrentAssistant(withMessages)`。
- library mode 下不过滤，并用 `assistantProductLabelForSession(s)` 显示 product chip。
- 这条路径进一步证明：
  - loaded session selection 和 task list filtering 必须共用同一个 product owner 判断。
  - 否则打开任务和左侧列表归属可能不一致。

`panels.js` 和产品 shell：

- `panels.js` 不是产品专属文件，但 app titlebar 会调用 `assistantChromeTitleState()`。
- `assistantChromeTitleState()` 返回：
  - `main`
  - `sub`
  - `documentTitle`
- 这是 product shell 暴露给 app shell 的隐式接口。
- 目前没有测试/文档锁住这个接口。
- `panels.js` 自身也很宽：
  - titlebar。
  - settings dirty guard。
  - panel switching。
  - drag/drop。
  - settings/providers/rollback checkpoints 等。
- 但产品相关的首要点不是拆整个 panels，而是把 app chrome title state contract 写清楚。

现有测试观察：

- `test_sprint9.py` 已覆盖旧模块存在和基础顺序：
  - `ui.js`
  - `workspace.js`
  - `sessions.js`
  - `messages.js`
  - `panels.js`
  - `boot.js`
- 它没有覆盖：
  - `product-store.js`
  - `product-shell-runtime.js`
  - `product-runtime.js`
  - `product-evolution.js`
  - `onboarding.js`
- 所以 product script order 仍是隐式约束。
- 当前额外跑 `test_sprint9.py` 有 2 个失败：
  - `test_panels_js_served` 仍期待 `panels.js` 里有 `async function loadCrons/loadSkills/loadMemory`。
  - `test_all_functions_present_across_modules` 仍期待这些函数在旧 split modules 中存在。
- 当前静态搜索结果：
  - `panels.js` 1679 仍调用 `loadCrons()`。
  - 没搜到 `loadCrons/loadSkills/loadMemory` 的函数定义。
- 这说明旧 split module 测试和当前 panel/modules 边界已经漂移；需要单独修测试或恢复/迁移这些全局函数。

新增测试缺口：

- product scripts 必须在 `messages.js` 后、`panels.js/onboarding/boot.js` 前。
- `product-shell-runtime.js` 必须早于 `product-runtime.js`，因为 runtime 读当前产品上下文和 shell 函数。
- `product-evolution.js` 必须在 HTML 里保留到 rollback inline onclick 被迁走。
- `panels.js` 可以读取 `assistantChromeTitleState()`，并应在缺失时 fallback。
- `boot.js` 应暴露或等待 product hydration promise，至少测试 hydrate slow / session restore fast。
- BFCache restore 应重新走 product session reconciliation。

## 53. 第十九轮：product bridge host / iframe SDK 协议复核

文件：

- `apps/webui/static/product-runtime.js`
- `apps/webui/static/product-bridge-sdk.js`
- `apps/webui/static/messages.js`
- `products/ai-otome/app.js`

已读关键区段：

- `product-bridge-sdk.js` 1-49：localStorage/sessionStorage fallback。
- `product-bridge-sdk.js` 51-96：pending request、`NextAI.chat.send()` / `NextAI.product.send()`。
- `product-bridge-sdk.js` 99-151：`NextAI.state` host request + fallback localStorage。
- `product-bridge-sdk.js` 175-212：host ack/reply/state/error/ready/agent message。
- `product-runtime.js` 1-115：当前产品 workspace/preview/context/scope。
- `product-runtime.js` 116-233：canvas state host storage。
- `product-runtime.js` 235-371：canvas -> host chat send、hidden instruction、pending reply。
- `product-runtime.js` 373-410：postMessage listener、download request。
- `product-runtime.js` 730-784：preview iframe ready message。

Bridge 当前协议：

iframe -> host：

- `nextai:product:send`
  - text/message。
  - optional requestId。
  - optional context/history/character/action。
  - optional productScope/scope。
- `nextai:product:state`
  - action: get/set/remove/clear。
  - key/value/fallback/scope。
- `nextai:product:download`
  - url。
  - filename。

host -> iframe：

- `nextai:host:ready`
  - productId。
  - sessionId。
  - layout。
  - canvasLabel。
- `nextai:host:ack`
  - requestId。
  - sessionId。
- `nextai:host:reply`
  - requestId。
  - sessionId。
  - content。
- `nextai:host:error`
  - requestId。
  - sessionId。
  - error。
- `nextai:host:state`
  - action/key/value/exists/productId/sessionId/scope。
- `nextai:host:agent_message`
  - content。

安全边界：

- SDK 只接受 `source === 'nextai-host'` 且 `event.source === window.parent`。
- host 只接受 `source === 'nextai-product-canvas'` 且 `event.source === activeProductFrame.contentWindow`。
- iframe sandbox 没有 `allow-same-origin`，所以 host 不能用 origin 字符串校验，改用 frame window 校验是合理的。

send 生命周期：

1. iframe `NextAI.chat.send(payload)`：
   - 生成 requestId。
   - pending map 等待 host reply/error。
   - 发 `nextai:product:send`。
   - promise 最终返回 `{content, raw}`。

2. host `_sendProductCanvasAgentMessage()`：
   - 校验 active frame。
   - 校验 text 非空。
   - busy/active stream 时返回 error。
   - 如无 session，先 `newSession()`。
   - 用 session id 作为 `PRODUCT_CANVAS_BRIDGE_PENDING` key。
   - 设置：
     - `_nextAiPendingProductScope`
     - `_nextAiPendingProductIntent`
     - `_nextAiPendingHiddenAgentInstruction`
   - 把 text 写进 composer。
   - 先发 `nextai:host:ack`。
   - 再调用全局 `send()`。

3. stream done 后：
   - `messages.js` 调 `notifyProductCanvasAgentReply()`。
   - host 找 pending。
   - 发 `nextai:host:reply`。

关键问题：

- SDK `send()` 返回 `{content, raw}`，但 host reply 只发送 `content`。
- 没有明确 `raw/assets/files/image_url/content_url` 的 contract。
- `products/ai-otome/app.js` 这类产品如果要拿图片 URL，只能猜 `res.image_url`、`res.content_url` 或从文本里解析。
- `nextai:host:ack` 不 resolve promise，这点是对的；但 ack 和 final reply/error 的 timeout 语义还没有文档。
- host pending timeout 现在只删除 `PRODUCT_CANVAS_BRIDGE_PENDING`，没有主动给 iframe 发 `nextai:host:error`。
- pending 以 session id 为主键，requestId 在 pending value 里；同一 session 多个 canvas request 理论上会覆盖/串线。
- hidden context 仍通过 `_nextAiPendingHiddenAgentInstruction` 拼进下一条 send 的消息路径，和普通 user message 字段没有完全分离。
- download request 直接 fetch/open `data.url`，没有限制必须属于当前 product preview/assets/output 路径。
- `NextAI.state` host 存储是宿主 localStorage，不是后端产品事实；SDK fallback 也是 iframe localStorage，两者语义不同但对 app 来说都叫 state。

结构判断：

- bridge 不是不能用，基础 source/window 校验是清楚的。
- 最大维护问题是“协议字段没有被类型/文档锁住”。
- Host、SDK、产品 app 三边都靠约定和猜测。
- 这块非常适合先写 `PRODUCT_APP_SDK_CONTRACT.md`，再做 TS 类型化。

优先测试：

- host reply 带 structured raw/assets 时，SDK 按 contract 暴露。
- ack 不 resolve promise。
- host timeout 主动 error。
- requestId 并发不串线。
- download URL allowlist。
- hidden instruction 不进入 visible user message。
- state host/local fallback 语义有文档和测试。

## 54. 第二十轮：productize marker / General chat -> Creator draft

文件：

- `apps/webui/static/ui.js`
- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/api/product_context.py`
- `apps/webui/api/products.py`
- `apps/webui/api/routes.py`
- `apps/webui/tests/test_product_scope_lines.py`
- `apps/webui/tests/test_product_drafts.py`

已读关键区段：

- `product_context.py` 400-430：chat_only usage 的 `NEXT_AI_SUGGEST_PRODUCT` prompt protocol。
- `ui.js` 2338-2368：marker strip/parse/click。
- `ui.js` 5650-5685：assistant render 时 strip marker、最后一条 assistant message 渲染 product suggestion button。
- `product-shell-runtime.js` 724-815：Creator draft instruction、`continueCreatorDraftTurn()`、`createProductFromPrompt()`。
- `products.py` 651-725：`create_product_draft()`。
- `routes.py` 5113：`/api/product-drafts/create` / `/api/products/draft/create`。
- `test_product_scope_lines.py` 215-234：chat_only usage 有 marker，canvas usage/builder 没有 marker。
- `test_product_drafts.py`：draft 不进入正式 products list。

产品孵化链路：

1. 后端 product prompt：
   - 仅在 `ui_mode=chat_only` 或 `product_layout=chat_only` 且 `scope=product_usage` 时提示可 append marker。
   - marker 格式：
     - `title`
     - `prompt`
     - `type`

2. 前端渲染：
   - `_stripProductSuggestMarker()` 从可见文本中移除完整 marker 和流式未闭合尾巴。
   - `_parseProductSuggestMarker()` JSON.parse marker，得到 `{title, prompt, type}`。
   - 只在该轮最后一条 assistant message、非 live 时渲染按钮。
   - 按钮文案用 `title`。
   - 按钮 data 只保存 `prompt`。

3. 点击按钮：
   - `_onProductSuggestClick()` 只取 `data-product-prompt`。
   - 调 `createProductFromPrompt(prompt)`。
   - `title/type` 丢失。

4. 创建草稿：
   - `createProductFromPrompt()` 用 `_assistantDraftFromPrompt(text)` 本地猜 title。
   - POST `/api/product-drafts/create`：
     - title。
     - avatar。
     - desc。
     - prompt/source_prompt。
   - 没传 marker 的 `type`。
   - 没传 marker 的 `title`，除非本地猜 title 恰好一致。

5. 后端 draft：
   - `create_product_draft()` 生成 `product.json`。
   - `product_type` 固定 `"custom"`。
   - `ui_mode` 固定 `chat_only`。
   - `product_layout` 固定 `chat_only`。
   - `skills/tools` 为空。
   - draft 不进入正式 product list。

6. Creator session：
   - `newSession(false, {workspace: draft.workspace_path, enabledToolsets:['skills','file','terminal','code_execution']})`。
   - `continueCreatorDraftTurn()` 写 composer。
   - 设置：
     - `_nextAiCreateBypassOnce`
     - `_nextAiActiveCreatorDraftId`
     - `_nextAiPendingHiddenAgentInstruction`
   - setTimeout 调 `send()`。

结构判断：

- productize marker 的后端协议是清楚的，且有后端 prompt 测试。
- 前端消费只完成了一半：
  - title 用于按钮展示。
  - prompt 用于创建。
  - type 完全丢失。
- 草稿创建默认 chat_only/custom，和 marker 里的 `interactive|ppt|image|research|data` 没有衔接。
- Creator instruction 会让 agent 再判断是否创建 index/style/app，但初始 manifest 已经偏向 chat_only。
- hidden creator instruction 和 product bridge hidden instruction 使用同一个 `_nextAiPendingHiddenAgentInstruction` 全局通道，说明“隐式 agent 指令”需要统一结构化。
- 这条链路和 `createProductFromPrompt()` 是同一条入口，不算重复；问题是 marker metadata 没完整传进去。

优先测试：

- `_parseProductSuggestMarker()` 能解析 title/type/prompt。
- `_onProductSuggestClick()` 不应丢 title/type。
- `createProductFromPrompt()` 支持 `{title, prompt, type}` object payload。
- `create_product_draft()` 能接受 product_type / suggested_type，并写进 manifest。
- interactive/image/ppt/research/data 的 draft 初始 defaults 不应全部固定 custom/chat_only。
- marker 未闭合时不会渲染给用户。
- live message 不显示 product suggest button。

## 55. 第二十一轮：真实产品 app 对 SDK 的依赖

文件：

- `products/ai-otome/index.html`
- `products/ai-otome/app.js`
- `products/ppt-designer/index.html`
- `products/ppt-designer/app.js`
- `apps/webui/static/product-runtime.js`
- `apps/webui/static/messages.js`

已读关键区段：

- `ai-otome/index.html` 112-123：bridge SDK 在 app.js 前加载。
- `ai-otome/app.js` 80-130：`NextAI.state` 保存/恢复。
- `ai-otome/app.js` 368-430：普通角色对话 `NextAI.chat.send()`。
- `ai-otome/app.js` 430-505：结构化文本 reply 解析。
- `ai-otome/app.js` 556-575：画像生成 `NextAI.chat.send()`。
- `ppt-designer/index.html` 116-124：bridge SDK 在 app.js 前加载。
- `ppt-designer/app.js` 27-45：bridge/state helper，state get race 1.2s。
- `ppt-designer/app.js` 195-214：通过 `nextai:product:download` 触发导出。
- `ppt-designer/app.js` 219-270：canvas 按钮发 agent prompt。
- `ppt-designer/app.js` 290-345：`state.json` + `nextai:agent` + `window.PPT` 回填。
- `ppt-designer/app.js` 394-436：`HEYTEA_DECK` 和启动顺序。
- `messages.js` 1944-1960：stream done 后只把 assistant content 回给 bridge。

AI Otome 结论：

- index 加载顺序正确：`product-bridge-sdk.js` 早于 `app.js`。
- 普通聊天路径：
  - `callMira()` 调 `NextAI.chat.send({action,text,context})`。
  - 只读取 `res.content`。
  - agent 被要求在最后一行输出 JSON。
  - `parseStructuredReply()` 从文本末尾解析 JSON。
  - 这条路径和当前 SDK/host reply 兼容。
- state 路径：
  - 在 iframe 内优先用 `NextAI.state.get/set`。
  - 不在 iframe 时用 localStorage。
  - 没有短 timeout race，host state 慢时可能等 SDK 默认 5 秒。
- 画像生成路径：
  - 调 `NextAI.chat.send({action:'generate_portrait', text, context:{product_action:'image_generate', save_as:'assets/mira-portrait.png'}})`。
  - 读取 `res?.image_url || res?.content_url`。
  - 当前 SDK 返回 `{content, raw}`，host `notifyProductCanvasAgentReply()` 只发 `content`。
  - 所以这条路径契约不成立：除非 agent 把 URL 写进 content 并产品自己解析，否则拿不到顶层 image_url。

PPT Designer 结论：

- index 加载顺序正确：bridge SDK 在 app.js 前。
- state 恢复比 AI Otome 更稳：
  - `NextAI.state.get('ppt')` race 1.2s。
  - 不让 host state 慢阻塞首屏。
- AI -> GUI 主通道比较清楚：
  - 首选 agent 写 `state.json`。
  - canvas 监听 `nextai:agent` 后 fetch `state.json`。
  - fallback 解析 chat reply 里的 outline / `window.PPT.loadImages(...)`。
- 下载路径：
  - product app 发 `nextai:product:download` 给宿主。
  - 宿主当前没有 URL allowlist，这是 host 侧问题。
- 启动硬伤：
  - `start()` 顺序是：
    - `setStage(default)` 先 paint。
    - `restore()` 读 session state。
    - `fetchStateFile()` 读 workspace `state.json`。
    - 最后无条件 `applyDeckState(HEYTEA_DECK)`。
  - 这会覆盖用户真实 state 和 agent 写出的 `state.json`。
  - demo 数据应该只在 `?demo=` 或 seed action 下生效。

真实产品对 SDK 的整体判断：

- 两个产品都遵守“SDK 在 app.js 前加载”和“不直接调模型 API”。
- PPT Designer 更接近推荐架构：workspace `state.json` 是 AI->GUI 事实通道。
- AI Otome 暴露了 typed reply 缺口：普通 text 可以，图片/file response 不行。
- 产品 app 已经开始各自补超时策略：PPT 自己 race，AI Otome 不 race。SDK 应统一 state timeout policy。

## 56. 第二十二轮：hidden instruction 通道 / messages send payload

文件：

- `apps/webui/static/messages.js`
- `apps/webui/static/product-runtime.js`
- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/api/routes.py`
- `apps/webui/api/products.py`

已读关键区段：

- `messages.js` 398-455：`send()` 开始，读取并清空 `_nextAiPendingHiddenAgentInstruction`。
- `messages.js` 455-605：busy/queue/command/session 创建。
- `messages.js` 606-690：hidden instruction 拼进 `msgText`，构造 product context，POST `/api/chat/start`。
- `product-runtime.js` 300-318：canvas bridge 设置 pending scope/intent/hidden instruction。
- `product-shell-runtime.js` 724-755：Creator draft instruction 设置 pending hidden instruction。
- `product-shell-runtime.js` 812-870：Creator draft publish helper。
- `products.py` 651-725：create draft。
- `products.py` 725-870：publish draft。
- `routes.py` 5113-5125：draft create/publish routes。

hidden instruction 当前来源：

1. product canvas bridge：
   - `_sendProductCanvasAgentMessage()` 设置：
     - `_nextAiPendingProductScope`
     - `_nextAiPendingProductIntent`
     - `_nextAiPendingHiddenAgentInstruction = _productCanvasBridgeInstruction(payload)`
   - 这个 hidden instruction 包含 canvas mode、character、history 等。

2. Creator draft：
   - `continueCreatorDraftTurn()` 设置：
     - `_nextAiCreateBypassOnce`
     - `_nextAiActiveCreatorDraftId`
     - `_nextAiActiveCreatorDraftTitle`
     - `_nextAiPendingHiddenAgentInstruction = _creatorDraftInstruction(...)`
   - instruction 包含 draft workspace、manifest path、原始请求、不要发布等。

3. send()：
   - 开始时读取 `_nextAiPendingHiddenAgentInstruction`。
   - 立刻清空全局。
   - 如果有 `msgText`，直接追加：
     - `msgText = user text + "\n\n" + hiddenAgentInstruction`
   - POST `/api/chat/start` 的 body 仍然只有 `message: msgText`。

结构判断：

- hidden instruction 的意图是合理的：给 agent 内部上下文，不展示给用户。
- 但实现路径是文本拼接，不是结构化 request 字段。
- 这会带来几个问题：
  - server 端无法区分用户原文和内部上下文。
  - session 的 pending/user message 可能包含 hidden block 的风险取决于后端如何保存 `message`。
  - bridge、creator、未来其他内部控制都抢同一个全局字符串。
  - queue/conflict 里传的是 `msgText`，可能把 hidden instruction 当普通 queued text 保存。
  - 产品 context 的 `product_intent` 用的是原始 `text || msgText`，多数时候能避开 hidden instruction，但这只是前端局部约定。
- 更好的结构：
  - request body 增加 `internal_context` 或 `hidden_instructions[]`。
  - user visible text 始终只放用户原文。
  - queue item 保存 visible text + structured internal context。
  - backend ephemeral prompt builder 负责把 internal context 放入 agent prompt，不进入 user message。

Creator draft 补充：

- 上轮以为只有 draft create；本轮确认已有 publish lifecycle：
  - `/api/product-drafts/publish`。
  - `publishCreatorDraftIfReady()`。
  - stream done 后 `messages.js` 会延迟触发 publish。
- draft publish 根据 manifest readiness 判断是否可发布，然后复制到正式 `products/<id>`，写 products state。
- 后续复核修正：当前 readiness 不是 title/mtime heuristic，而是 `draft_status` ready gate。
- 所以 productize 链路并不缺 publish，主要缺的是：
  - create draft 时 marker `title/type` 丢失。
  - hidden creator instruction 走文本拼接。
  - draft defaults 固定 custom/chat_only。

测试现状补充（后续复核已更新）：

- 当前 `apps/webui/tests/test_product_drafts.py` 是未追踪文件，且已包含 draft publish 测试。
- 最新运行产品专项测试时收集 65 项，结果 65 passed。
- `test_product_drafts.py` 已补：
  - draft create 默认 `draft_status: "clarifying"`。
  - `draft_status: "ready"` 时 publish/register。
  - `draft_status: "clarifying"` + `if_ready` 时不 publish。
- suggestion normalization 现在测试期望与实现一致：`prompt[:24]` -> `"Write about React Server"`。

优先测试：

- bridge hidden context 不进入 visible user message。
- creator hidden instruction 不进入 visible user message。
- queue/conflict 里的 hidden instruction 不被当普通 text 保存。
- `/api/chat/start` 支持 `internal_context` 后，后端 prompt 包含 internal context，但 session user message 只保存用户原文。
- Creator draft publish 触发条件：
  - manifest 未写 ready status 时不 publish。
  - manifest 写 `draft_status: "ready"` 后 publish。

## 57. 第二十三轮：`/api/chat/start` message persistence / internal context 插入点

本轮继续追 `/api/chat/start` 到 streaming 的后端路径，重点确认 hidden instruction 如果拼进 `message` 后，到底会不会成为持久用户消息。

读到的文件：

- `apps/webui/api/routes.py`
- `apps/webui/api/streaming.py`
- `apps/webui/api/models.py`
- `apps/webui/api/product_context.py`
- `apps/webui/static/messages.js`
- `apps/webui/static/product-runtime.js`
- `apps/webui/static/product-shell-runtime.js`

关键链路：

1. 前端 `send()`
   - `messages.js` 406-413：读取并清空 `window._nextAiPendingHiddenAgentInstruction`。
   - `messages.js` 585-590：先构造 `msgText`，再把 hidden instruction 直接追加到 `msgText`。
   - `messages.js` 594-612：用原始 `text || msgText` 计算 product context。
   - `messages.js` 666-674：POST `/api/chat/start`，body 里 `message: msgText`。
   - UI 本地 optimistic user message 使用的是 `displayText` / `text`，所以前端可见 transcript 和后端真实 message 可能不同。

2. `routes.py` chat start
   - `_handle_chat_start()` 7983：`msg = str(body.get("message", "")).strip()`。
   - `product_context_request_body(body, s, msg)` 会把 `msg` 作为默认 `message` / `product_intent` 候选。
   - `_start_chat_stream_for_session(..., msg=msg, product_context=product_context)`。
   - `_prepare_chat_start_session_for_stream()`：
     - `s.pending_user_message = msg`
     - eager 模式下 `_checkpoint_user_message_for_eager_session_save()` 会把 `msg` 直接写入 `s.messages`。
     - provisional title 也从 `msg` 推导。
   - turn journal `submitted` event 写入 `"content": msg`。

3. `streaming.py` agent run
   - `_webui_ephemeral_system_prompt(personality_prompt, product_prompt)` 是现有的非持久 prompt 注入口。
   - `_run_agent_streaming(..., msg_text, product_context=...)` 运行前把 `product_ephemeral_prompt(product_context)` 放进 `agent.ephemeral_system_prompt`。
   - `user_message = _build_native_multimodal_message(workspace_ctx, _agent_msg_text, ...)`。
   - `agent.run_conversation(..., persist_user_message=msg_text)`。
   - 成功写回时 `_merge_display_messages_after_agent_result(..., msg_text)` 用同一个 `msg_text` 找 current user turn 并合并 display transcript。
   - retry/self-heal 路径也继续用 `persist_user_message=msg_text` 和 merge `msg_text`。

4. cancel / crash recovery
   - `models.py` `_append_recovered_pending_turn()` 直接把 `session.pending_user_message` 作为 recovered user message。
   - `streaming.py` cancel path 也会把 pending user message synthesize 成 user turn。
   - 因此 hidden instruction 如果进了 pending，就可能出现在恢复后的用户消息、journal、title 或上下文匹配里。

结构判断：

- 后端已经有正确方向：`product_context.py` 文件头明确说前端不应该把产品指令藏进可见 message，而应该发送结构化字段。
- `product_context.py` 的 `product_context_from_request()` / `product_ephemeral_prompt()` 已经把产品上下文走到了 `ephemeral_system_prompt`，这条路比 hidden instruction 文本拼接更干净。
- 当前问题不是没有结构化通道，而是两套机制并存：
  - product_id/scope/intent 走 `product_context`。
  - Creator draft / canvas bridge 的内部指令走全局 hidden string，然后拼进 `message`。
- 这造成三份 transcript 语义不一致：
  - 前端 optimistic display：用户原文。
  - 后端 pending / journal / persist_user_message：用户原文 + hidden instruction。
  - agent ephemeral prompt：product context。

建议改造点：

- Request body 拆为：
  - `message`: 用户可见原文，只用于 UI transcript、pending、journal、title、recovery。
  - `internal_context` 或 `hidden_instructions[]`: Creator draft / canvas bridge / future internal controls。
  - `product_context`: product_id/scope/intent/tool hints。
- 后端新增一个小 helper：
  - `normalize_chat_start_payload(body, session)`：输出 visible message、attachments、product_context、internal_context。
  - `build_internal_context_prompt(internal_context)`：只进入 `_webui_ephemeral_system_prompt()`，不进入 user message。
- `_start_chat_stream_for_session()` 签名可先兼容增加 `internal_context=None`。
- `_run_agent_streaming()` 只把 internal context 拼入 ephemeral prompt，不传给 `persist_user_message`。
- queue/conflict/retry/drain 的 payload 必须保存 structured internal context，不能保存拼接后的 `msgText`。
- `product_context_request_body()` 的 `message` 参数应明确只接收 visible user text。

需要测试：

- `/api/chat/start` 收到 `message="hello"` + `internal_context` 时：
  - `pending_user_message == "hello"`。
  - turn journal submitted content 是 `"hello"`。
  - agent `ephemeral_system_prompt` 包含 internal context。
  - `persist_user_message == "hello"`。
- eager save / cancel / recovery 下 hidden instruction 不出现在 user message。
- canvas bridge 和 Creator draft 两个来源都走 structured internal context。
- queue conflict 把 internal context 连同 product context 一起排队和恢复。

结论：

- 产品逻辑已经足够清晰：产品上下文、builder/use 分线、workspace guard、ephemeral prompt 都能读通。
- 代码维护性不够清晰：同一个 `message` 字段承担用户文本、内部控制、恢复锚点、journal 内容、标题来源，职责过多。
- 这里不适合先 TS 重写；应该先修 request/turn contract，再给这个 contract 补类型。

## 58. 第二十四轮：draft publish / productize metadata 补读

补读 draft create/publish 之后，productize 链路更准确的结论是：生命周期已经存在，但 metadata 和 hidden instruction 边界不够完整。

关键文件：

- `apps/webui/api/products.py` 657-725：`create_product_draft()`。
- `apps/webui/api/products.py` 748-783：draft suggestions / manifest payload normalization。
- `apps/webui/api/products.py` 785-801：draft readiness。
- `apps/webui/api/products.py` 804-883：`publish_product_draft()`。
- `apps/webui/api/routes.py` 5114-5124：draft create/publish routes。
- `apps/webui/static/product-shell-runtime.js` 763-858：create draft / publish draft 前端 helper。
- `apps/webui/static/messages.js` 1972-1974：stream done 后自动 `publishCreatorDraftIfReady()`。

清楚的部分：

- `create_product_draft()` 只创建 `product_drafts/<id>` workspace，不进入正式 product registry。
- `publish_product_draft()` 会复制 draft workspace 到正式 `products/<id>`，然后写 registry。
- `.knead-published.json` 防止重复 publish。
- `if_ready` 现在只通过 manifest `draft_status` 判断是否可发布：
  - ready states：`ready` / `publish` / `published` / `final`。
  - not-ready states：`clarifying` / `draft` / `working` / `needs_input` / `not_ready`。
  - 没有 ready status 时，即使 title/desc/layout/index.html 已经变化，也会返回 `{published:false, not_ready:true}`。
- publish 后会走 `_normalize_product()` / `_write_manifest()`，并根据 `index.html` 是否存在设置 `ui_status`。

不清楚 / 不够可维护的部分：

- `createProductFromPrompt(prompt)` 只把 prompt 传给 draft create，productize marker 的 `title/type` 没有完整传递。
- `create_product_draft()` 默认：
  - `product_type = "custom"`
  - `ui_mode = "chat_only"`
  - `product_layout = "chat_only"`
  - `skills = []`
  - `tools = []`
- 这对“先让 Creator agent 决定产品形态”是合理默认，但没有把 marker type 作为 initial hint 保存到 manifest。
- Creator draft instruction 仍然通过 `_nextAiPendingHiddenAgentInstruction` 拼进 `message`，和上节问题相同。
- Creator agent / product.json schema 必须明确写入 `draft_status`，否则前端 stream done 后的 `publishCreatorDraftIfReady()` 不会发布。
- suggestion normalization 的 label 截断规则没有被 schema 明确：
  - 当前实现 `_normalize_draft_suggestions()` 使用 `prompt[:24]`。
  - 后续复核：当前未追踪测试已按 `prompt[:24]` 覆盖 ready publish 路径。

建议：

- draft create body 接收 `suggested_title` / `suggested_type` / `source` 或直接接收 parsed productize marker。
- draft manifest 保留 initial metadata：
  - `product_type` 可从 marker type 映射到 `interactive|ppt|image|research|data|custom`。
  - `source_prompt` 保持用户原始 creation prompt。
  - 可加 `creation_hint`，但不要让它成为最终产品必填字段。
- Creator internal instruction 改走 `internal_context`：
  - `kind: "creator_draft"`
  - `draft_id`
  - `workspace_path`
  - `manifest_path`
  - `original_user_request`
  - `initial_metadata`
- publish 测试需要先定 schema：
  - Creator 完成可发布版本时必须写 `draft_status: "ready"` 或同义 ready status。
  - suggestions label 最大长度到底是 24 chars、20 chars、还是不截断。
  - type/layout alias 是否在 publish 时继续兼容 `canvas -> workspace/canvas_full`。

测试现状修正（后续复核已更新）：

- 最新产品专项测试是 65 项，65 passed。
- 当前未追踪 `test_product_drafts.py` 已把 publish 测试 manifest 改为 `draft_status: "ready"`，并新增 not-ready 测试。
- readiness gate 和 suggestion label 截断规则目前已有测试覆盖。

## 59. 第二十五轮：queued message / drain / refresh restore

本轮读 queue 相关代码，确认 queued product turn 和未来 `internal_context` 会不会完整穿过排队、冲突、刷新恢复。

读到的文件：

- `apps/webui/static/ui.js`
- `apps/webui/static/messages.js`
- `apps/webui/static/commands.js`
- `apps/webui/static/sessions.js`
- `apps/webui/static/product-runtime.js`
- `apps/webui/tests/test_issue660.py`
- `apps/webui/tests/test_1062_busy_input_modes.py`
- `apps/webui/tests/test_regressions.py`

队列数据结构：

- `ui.js` 1-12：`SESSION_QUEUES` 是按 `session_id` 分组的内存队列，`_queueDrainSid` 指向刚结束的 session。
- `queueSessionMessage(sid, payload)`：
  - 浅拷贝 payload。
  - 增加 `_queued_at`。
  - 写入 `sessionStorage['hermes-queue-'+sid]`。
- 这个设计本身可以承载任意新字段，包括未来 `internal_context`，因为 payload 没有白名单过滤。

主要入队来源：

1. `send()` re-entrant guard：
   - `_sendInProgress` 时，把 composer 当前文本排队。
   - 通过 `withCurrentProductContext(_queuePayload, _text)` 补 product context。

2. busy queue / interrupt：
   - busy 分支构造 `queuePayloadBase`，包含：
     - `text`
     - `sendText`
     - `files`
     - `model`
     - `model_provider`
     - `profile`
     - product context（通过 `withCurrentProductContext`）
   - `interrupt` 分支先 queue，再 cancel，顺序有测试保护。

3. `/queue` / `/interrupt` / `/steer` fallback：
   - `commands.js` 856-1000。
   - 都会用 `withCurrentProductContext()` 补 product context。
   - `_trySteer()` 的 real steer 直接 POST `/api/chat/steer`，fallback 才 queue + cancel。

4. chat/start 409 conflict：
   - `messages.js` 720-727。
   - 如果 `/api/chat/start` 返回 active stream conflict，会 `queueSessionMessage(activeSid, {text: msgText, ...productContext})`。
   - 这里用了 `msgText`，而 `msgText` 可能已经拼了 hidden instruction。
   - 这是一个确定风险：正常 busy queue 用用户原文 `text`，409 conflict queue 用可能污染的 `msgText`。

5. goal continuation / steer leftover：
   - done handler 里 `_pendingGoalContinuation` 会入队。
   - `pending_steer_leftover` 会入队。
   - 两处都使用 `withCurrentProductContext(..., {consumePending:false})`，避免 pending product scope/intent 被提前消费。

drain 路径：

- `setBusy(false)`：
  - 用 `_queueDrainSid || S.session.session_id` 找要 drain 的 sid。
  - 只有当前正在查看这个 sid 时才 `shiftQueuedSessionMessage(sid)`。
  - drain 时把：
    - `next.sendText || next.text` 写回 composer。
    - `next.product_scope` 写到 `window._nextAiPendingProductScope`。
    - `next.product_intent` 写到 `window._nextAiPendingProductIntent`。
    - `next.files` 写回 `S.pendingFiles`。
    - `next.model/model_provider` 写回 session/dropdown。
  - 然后调用 `send()`。

结构判断：

- queue item 目前不是“完整 chat request”，而是“恢复 composer + 几个全局 pending 字段”。
- product scope/intent 能恢复，但 `product_id` 没有在 drain 中显式恢复；下一次 `send()` 仍依赖当前 selected assistant / loaded session 推导 product context。
- 如果用户在排队后切换 AI 或 hydrate 顺序变化，queued turn 可能被当前产品选择影响。
- 未来 `internal_context` 即使保存在 queue entry，drain 也不会自动带入 `/api/chat/start`，除非新增统一 request serializer。
- Queue merge 会把多条 text 合并，并只保留第一条 product_id/scope/intent；如果多条来自不同 product 或含不同 internal context，合并会语义丢失。

刷新恢复路径：

- `sessions.js` 695-721：
  - 读取 `sessionStorage['hermes-queue-'+sid]`。
  - 用 `_queued_at > last assistant ts` 过滤 stale entries。
  - 只把第一条 `_first.text` 放回 composer。
  - 然后删除 storage。
- 这意味着刷新后：
  - queue 不会重新进入 `SESSION_QUEUES`。
  - files/model/product_context/profile 会丢。
  - future `internal_context` 也会丢。
  - 用户点击发送时，会变成当前界面上下文下的一条普通消息。

测试现状：

- `test_issue660.py` 覆盖了 sessionStorage 写入、shift 删除、restore first text、stale timestamp guard。
- `test_1062_busy_input_modes.py` 覆盖 queue-before-cancel、busy slash command intercept。
- `test_regressions.py` 覆盖 session-scoped queue wiring。
- 这些测试保护的是“能排队、能恢复第一条文本、不串 session”，还没有保护：
  - product_id 必须在 drain 中保持。
  - hidden/internal context 不能污染 queued text。
  - refresh restore 不能丢 product/internal context。

建议：

- 抽一个 `queued-turn.js` 或 `chat-turn-request.js`：
  - `serializeQueuedTurn({message, attachments, model, provider, product_context, internal_context})`
  - `restoreQueuedTurnToComposerOrSend(entry)`
  - `startChatFromTurnRequest(entry)`
- drain 不应该靠全局 `_nextAiPendingProductScope/_Intent` 传递产品上下文；应该把 queued entry 作为 start request 的来源。
- queue entry 必须显式保存 `product_id/product_scope/product_intent/product_task_title/internal_context`。
- 409 conflict path 必须 queue visible `text`，不能 queue `msgText`。
- refresh restore 应该恢复完整 queue entry：
  - 要么放回 `SESSION_QUEUES` 并展示 chips。
  - 要么保留一个 hidden `pendingQueuedTurn` 对象，而不是只放 text。
- Queue merge 遇到不同 product_id 或含 internal_context 时应禁用，或要求明确丢弃上下文。

## 60. 第二十六轮：turn journal / recovery audit

本轮读 turn journal，确认它如何记录 submitted turn，以及它和 hidden instruction 的关系。

读到的文件：

- `apps/webui/api/turn_journal.py`
- `apps/webui/api/routes.py`
- `apps/webui/api/streaming.py`
- `apps/webui/api/session_recovery.py`
- `apps/webui/tests/test_turn_journal.py`
- `apps/webui/tests/test_turn_journal_lifecycle.py`
- `apps/webui/tests/test_turn_journal_callsite.py`

turn journal 模块本身：

- `turn_journal.py` 很小，职责清晰：
  - `_journal_path()` 校验 session_id。
  - `append_turn_journal_event()` 追加 JSONL，填默认 version/session_id/turn_id/created_at。
  - 使用 `O_APPEND` + fcntl lock + fsync。
  - `read_turn_journal()` 容忍 malformed lines。
  - `derive_turn_journal_states()` 取每个 turn_id 最新事件，同时报告 terminal collision。
  - `append_turn_journal_event_for_stream()` 根据 stream_id 复用 submitted turn_id。
- 它不理解业务字段，payload 原样保存。这是合理的低层设计。

callsite：

- `routes.py` `_start_chat_stream_for_session()`：
  - pending state 保存之后、worker thread 启动之前，写 `submitted` journal event。
  - event 内容包括：
    - `role: "user"`
    - `content: msg`
    - `attachments`
    - workspace/model/provider
    - `product: {id, scope, title}`（如果有 product_context）
  - 这里的 `content` 是同一个 `msg`，也就是 body.message。
- `streaming.py`：
  - worker 启动后写 `worker_started`。
  - 成功过程中可能写 `assistant_started`。
  - 成功完成写 `completed`。
  - cancel/error 写 `interrupted`。
  - 这些 lifecycle events 通过 `append_turn_journal_event_for_stream()` 找回 submitted turn_id。

recovery audit：

- `session_recovery.py` 502-529：
  - 读取 journal states。
  - 如果 latest state 不是 terminal event，取 `event.content`。
  - 如果 content 不为空且不在现有 user messages 里，就报告 `turn_journal_pending_turn`。
- 所以 `submitted.content` 是 recovery/audit 的用户消息事实来源。
- 如果 hidden instruction 被拼到 `msg`：
  - journal 会保存用户原文 + hidden instruction。
  - recovery audit 会用污染后的 content 判断是否 materialized。
  - 未来如果基于 journal 自动修复用户 turn，就会把 hidden instruction 一起恢复成用户消息。

测试现状：

- `test_turn_journal.py` 覆盖 fsync、锁、malformed line、latest event、terminal collision。
- `test_turn_journal_lifecycle.py` 覆盖 stream_id 复用 turn_id。
- `test_turn_journal_callsite.py` 只做静态检查：
  - submitted journal 写在 worker thread start 之前。
  - 写在 session lock 之后。
  - failure 被捕获。
- 还缺：
  - `/api/chat/start` visible message + internal context 时，journal submitted content 只含 visible message。
  - product metadata 可以进 journal 的 metadata/product 字段，但 internal context 不应该进 `content`。
  - recovery audit 不把 internal context 当 user content。

结论：

- turn journal 模块本身算优雅、合理、可维护。
- 需要修的是 chat-start contract：submitted `content` 必须绑定 visible user message，而不是拼接后的 agent instruction。
- 如果要记录 internal context 便于 debug，也应放在受控 metadata 字段，且默认 redacted/summary，不参与 recovery content 匹配。

## 61. 第二十七轮：product bridge host / SDK current-state 复核

本轮复核 product bridge host 与 iframe SDK，确认前面判断在当前 worktree 中是否仍然成立。

读到的文件：

- `apps/webui/static/product-runtime.js`
- `apps/webui/static/product-bridge-sdk.js`
- `apps/webui/static/messages.js`
- `apps/webui/static/index.html`
- `products/ai-otome/app.js`
- `products/ppt-designer/app.js`
- `apps/webui/tests/test_knead_product_skill.py`

host bridge 当前行为：

- iframe sandbox：
  - `index.html` 的 `#activeProductFrame` 使用 `sandbox="allow-scripts allow-forms"`。
  - 没有 `allow-same-origin`，所以 iframe origin 是 opaque/null。
  - host 不能可靠用 origin 字符串校验，当前用 `event.source === activeProductFrame.contentWindow` 是合理边界。
- host -> iframe：
  - `_postProductCanvasBridgeMessage()` 向 active frame `postMessage({source:'nextai-host', ...payload}, '*')`。
  - `frame.onload` 发送 `nextai:host:ready`，包含 `productId/sessionId/layout/canvasLabel`。
- iframe -> host：
  - listener 只接收 `source === 'nextai-product-canvas'` 且来自 active frame window。
  - `nextai:product:state` 走 localStorage host state。
  - `nextai:product:send` 走 `_sendProductCanvasAgentMessage()`。
  - `nextai:product:download` 直接 `fetch(data.url)` 下载，失败则 `window.open(data.url)`。

send pending 当前行为：

- host 的 `PRODUCT_CANVAS_BRIDGE_PENDING` 是 `Map<sessionId, pending>`。
- `_sendProductCanvasAgentMessage()`：
  - busy/active stream 时直接给 iframe `nextai:host:error`。
  - 没有 session 时先 `newSession()`。
  - pending value 包含 `requestId/sentAt/timeoutId/productId`。
  - timeout 125s 只 `delete(sid)`，不会主动给 iframe `nextai:host:error`。
  - 设置 `_nextAiPendingProductScope/_Intent/_nextAiPendingHiddenAgentInstruction`。
  - 把 text 写入 composer，发 ack，然后调用全局 `send()`。
- `notifyProductCanvasAgentReply()`：
  - 用 sessionId 找 pending；找不到时如果 pending map 只有一条，会 fallback 到那条。
  - reply 只发 `{type:'nextai:host:reply', requestId, sessionId, content}`。
  - 虽然 caller 传了 `message: bridgeAsst`，host reply 没有转发 message/raw/assets。
- `notifyProductCanvasAgentError()`：
  - 同样按 sessionId/fallback 找 pending，然后发 error。
- `messages.js` done path：
  - 找最新 assistant message。
  - 调 `notifyProductCanvasAgentReply({sessionId, content, message})`。
  - 同时 broadcast `nextai:host:agent_message`，所以 canvas request reply 和全量 agent broadcast 都可能被 canvas 收到。

SDK 当前行为：

- `createPendingRequest()`：
  - pending 以 `requestId` 为 key。
  - 默认 chat timeout 120s，state timeout 5s。
  - timeout 时 reject `Next AI bridge timed out`。
  - 发送 `source:'nextai-product-canvas'`。
- `NextAI.chat.send()` / `NextAI.product.send()`：
  - 发 `nextai:product:send`。
  - resolve 后返回 `{content: String(response.content || ''), raw: response}`。
- `NextAI.state.get/set/remove()`：
  - 先发 host state request。
  - 失败或超时时 fallback 到 iframe localStorage。
  - host state 是宿主 localStorage，fallback state 是 iframe localStorage；两者同名但持久化边界不同。
- SDK message listener：
  - 只接受 `source:'nextai-host'` 且 `event.source === window.parent`。
  - `nextai:host:ack` 不 resolve promise，只 dispatch `nextai:ack`。
  - `nextai:host:reply` / `nextai:host:state` resolve。
  - `nextai:host:error` reject。
  - `nextai:host:ready` 更新 `hostContext`，dispatch `nextai:ready`。
  - `nextai:host:agent_message` dispatch `nextai:agent`。

当前确认的优点：

- 两端 source/window 校验都比较清楚，和 sandbox 选择匹配。
- SDK 以 requestId 管理 pending，比 host 用 sessionId 更稳。
- ack 不 resolve promise，这个语义是正确的。
- state get 有 fallback，不会永久挂死产品 app。

当前确认的问题：

- host pending 以 sessionId 为 key，不以 requestId 为 key；同 session 内并发两个 canvas send 会覆盖。
- host timeout 静默删除 pending，iframe 只能等 SDK 自己 timeout，用户不会收到 host-side 具体错误。
- host reply 只回 content，SDK 虽然保留 raw，但 raw 里也没有 assets/files/data/message。
- `ai-otome` 画像生成读取 `res.image_url || res.content_url`，但 SDK 返回顶层只有 `content/raw`；这条路径仍不成立。
- `nextai:product:download` 没有 URL allowlist，当前 iframe 可要求 parent fetch/open 任意 URL。
- `NextAI.state` 的 host/fallback state 边界没有 contract，产品 app 看到的 API 一样，但真实存储位置不同。
- `_sendProductCanvasAgentMessage()` 仍然通过 `_nextAiPendingHiddenAgentInstruction` 把 canvas context 拼入下一次 chat message 路径。
- `ai-otome` boot 仍是 `await loadState(); render();`，host state 慢时会阻塞 first paint。
- `ppt-designer` 正常启动最后仍无条件 `applyDeckState(HEYTEA_DECK)`，会覆盖 defaults -> session state -> workspace `state.json`。

测试现状：

- 现有 `test_knead_product_skill.py` 只检查 skill 文档和模板里 bridge SDK 在 app.js 前加载。
- 没有直接测试：
  - `product-bridge-sdk.js` ack/reply/error/ready/agent message。
  - host pending 以 requestId 不串线。
  - host timeout 主动 error。
  - download URL allowlist。
  - SDK typed response assets/files/data。
  - iframe source guard。
  - shipped products 不读未记录字段。

建议：

- 先写 `PRODUCT_APP_SDK_CONTRACT.md`，再改实现。
- host pending map 改成 requestId primary：
  - `Map<requestId, {sessionId, productId, timeoutId, ...}>`。
  - sessionId 只用于把 stream done/error 路由回 request。
- host timeout 应主动给 iframe 发 `nextai:host:error`。
- host reply 应按 typed contract 透传：
  - `content`
  - `message` summary（如需要）
  - `data`
  - `assets[]`
  - `files[]`
  - 兼容 `raw`。
- download proxy 必须限制：
  - 当前 product preview path。
  - 当前 product outputs/assets。
  - 拒绝跨 product、外部 URL、javascript/data URL。
- SDK 提供 helper：
  - `NextAI.ready({timeoutMs})`。
  - `NextAI.chat.send()` 返回 documented typed response。
  - `NextAI.download(url, filename)`，不要让产品 app 手写 postMessage。

## 62. 更新后的下一轮阅读建议

下一步继续读：

1. `apps/webui/api/products.py` preview/download asset serving
   - 对照 bridge download allowlist，确认后端 preview 路径、outputs/assets 路径和路径逃逸保护。

2. `apps/webui/static/product-shell-runtime.js` Creator draft instruction / draft_status contract
   - 看 Creator 是否明确要求写 `draft_status: "ready"`，以及是否仍提示“不要发布”。

3. `apps/webui/tests`
   - 设计 bridge SDK/host 的静态或 jsdom 测试切入点。

## 63. 第二十八轮：`api/products.py` preview / asset serving 复核

本轮沿着上一轮 bridge download allowlist 往后端读，重点看产品 preview 路径、asset resolver、route 层响应头和测试覆盖。

读到的文件：

- `apps/webui/api/products.py`
- `apps/webui/api/routes.py`
- `apps/webui/static/product-runtime.js`
- `apps/webui/static/product-bridge-sdk.js`
- `apps/webui/tests/test_product_ui_status.py`

代码体量：

- `products.py` 约 1421 行。
- `product-runtime.js` 约 784 行。
- `product-bridge-sdk.js` 约 237 行。
- `product-shell-runtime.js` 约 2195 行。

后端 preview 当前路径：

- `product_file_status(product_id_or_kind)`：
  - 通过 `get_product()` 找产品。
  - `root = Path(product["workspace_path"]).resolve()`。
  - `preview_entry` 默认 `index.html`。
  - `entry = (root / entry_rel).resolve()` 后要求 `entry.relative_to(root)`。
  - 只列 root 顶层最多 80 个 assets，不递归列 nested outputs。
  - status 是 pure read，不持久化。
- `preview_product_file(product_id, asset)`：
  - `product_id = _safe_id(product_id)`。
  - 直接读 `_read_state()["products"]` 建 id map。
  - `target = (root / rel).resolve()` 后要求 `target.relative_to(root)`。
  - 目标不存在或不是 file 时 404。

route 层当前行为：

- GET `/api/products/<id>/preview...`：
  - `routes.py` 用 `parsed.path.startswith("/api/products/") and "/preview" in parsed.path` 匹配。
  - `_serve_product_preview()` 把 rest 按 `"/preview"` split。
  - asset 默认 `index.html`，`unquote()` 后交给 `preview_product_file()`。
  - 成功后走 `_serve_file_response()`。
- GET `/api/products/<id>/<asset>`：
  - `_serve_product_asset()` 也走 `preview_product_file()` 和 `_serve_file_response()`。
- `_serve_file_response()`：
  - 根据 `_STATIC_MIME` 设置 Content-Type。
  - 对 text/css、application/javascript、text/html、image/svg+xml、text/plain 加 charset。
  - 设置 `Cache-Control: no-store`。
  - 直接读 bytes 写回。
  - 没有 Content-Disposition。
  - 没有 CSP sandbox。
  - 没有 X-Content-Type-Options / Referrer-Policy / Permissions-Policy。

当前确认的优点：

- 关键路径逃逸保护是对的：`resolve()` 后 `relative_to(root)`，`../` 不能逃出产品 workspace。
- preview route 和 asset route 最终使用同一个 resolver，方向对。
- 产品文件 no-store，符合热刷新和产品迭代需要。
- `product_file_status()` 保持 pure read，这个边界值得保留。

当前确认的问题：

- `preview_product_file()` 直接 `_read_state()`，不走 `get_product()` / `_ensure_builtin_products_locked()`；干净状态下直接打开 builtin preview 可能依赖之前是否访问过 `/api/products`。
- route 匹配条件是 “path contains `/preview`”，不是严格的 segment match；维护上比较脆。
- product preview HTML 直接 top-level 打开时没有 CSP sandbox。iframe 里有 `sandbox="allow-scripts allow-forms"`，但用户或 app 直接打开 `/api/products/<id>/preview` 时会在 WebUI 同源下执行产品 HTML/JS。
- product SVG 走 `_serve_file_response()` 时会 inline `image/svg+xml`，没有强制 attachment，也没有 CSP。对比 `/api/file/raw`，那里明确把 SVG 当危险 MIME 强制 download。
- product preview 响应层没有复用 `_serve_file_bytes()` 那套 security headers / Content-Disposition helper / range handling。
- bridge `nextai:product:download` 当前在前端 parent 里直接 `fetch(data.url)`，没有调用后端 product asset resolver；因此 allowlist 需要前后端一起定义，否则会出现 host JS 一套、backend preview 一套。
- `product_file_status()` assets 只列顶层，这适合 UI 摘要，但不能作为 download/preview allowlist 的完整依据；nested `outputs/<deck>/slide-01.png` 仍可被 preview resolver 服务。

和 `/api/file/raw` 的对比：

- `/api/file/raw?inline=1` 对 HTML inline 会设置 CSP `sandbox allow-scripts`。
- SVG 会强制 download。
- dangerous MIME 有明确 disposition 规则。
- product preview 目前没有同等级响应策略，主要靠 iframe sandbox，但 direct preview URL 没有这个保护。

建议：

- 抽出 `product_assets.py` 或至少抽出单一 resolver：
  - `resolve_product_asset(product_id, asset, *, ensure_builtin=True)`。
  - 返回 `product/root/target/rel/mime/disposition_policy`。
- preview route 严格匹配：
  - `/api/products/<id>/preview`
  - `/api/products/<id>/preview/<asset>`
  - 避免任意包含 `/preview` 的 path 被误判。
- product HTML 响应默认加 CSP sandbox：
  - 可先用 `sandbox allow-scripts allow-forms`，和 iframe sandbox 对齐。
  - 不加 `allow-same-origin`，保持产品代码无法读 WebUI localStorage/cookies。
- SVG 默认 attachment，或者至少不允许 inline 执行。
- `nextai:product:download` 不应 parent 直接 fetch 任意 URL：
  - 只允许当前 product 的 `/api/products/<id>/preview/...`。
  - 允许 nested `assets/`、`outputs/`、workspace 相对文件。
  - 拒绝跨 product、绝对外部 URL、`javascript:`、`data:`。
  - 最好走同一个 `resolve_product_asset()` contract。
- 增加 route tests：
  - 默认 index。
  - nested output asset。
  - `../` 路径逃逸。
  - direct builtin preview 不依赖先访问 `/api/products`。
  - HTML response 有 CSP sandbox。
  - SVG 不 inline。
  - no-store 保持。

更新后的下一轮建议：

1. 继续读 `product-shell-runtime.js` 的 Creator draft instruction / `draft_status` contract。
2. 再读 `apps/webui/tests`，设计 product bridge host/SDK 的测试入口。
3. 之后再开始实现第一批小修：preview response contract 和 bridge download allowlist 可以组成一组。

## 64. 第二十九轮：Creator draft instruction / `draft_status` contract 复核

本轮复核 “一句话创建 AI 产品” 的 draft 生命周期，确认前端 Creator instruction、后端 publish gate、productize marker 是否一致。

读到的文件：

- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/messages.js`
- `apps/webui/static/ui.js`
- `apps/webui/api/products.py`
- `apps/webui/api/routes.py`
- `apps/webui/api/product_context.py`
- `.agents/skills/knead-product/SKILL.md`
- `apps/webui/tests/test_product_drafts.py`

当前链路：

- 普通 Create AI 入口：
  - `messages.js send()` 发现当前 AI 是 `create`，且不是 Creator draft session。
  - 调 `createProductFromPrompt(text, {deferInitialSend:true})`。
  - 创建 draft session 后再 `continueCreatorDraftTurn(created)`。
- productize marker 入口：
  - `ui.js` 解析 `[[NEXT_AI_SUGGEST_PRODUCT]]{"title":"...","prompt":"...","type":"..."}`。
  - 最后一条 settled assistant message 渲染按钮。
  - `_onProductSuggestClick(btn)` 目前只读取 `data-product-prompt`，调用 `createProductFromPrompt(prompt)`。
- draft create：
  - `/api/product-drafts/create` -> `create_product_draft()`。
  - 创建 `STATE_DIR/product_drafts/<draft_id>/product.json`。
  - 默认 `draft: true`、`draft_status: "clarifying"`、`product_type: "custom"`、`ui_mode: "chat_only"`、`product_layout: "chat_only"`。
  - draft 不进入正式 `ai_products.json`。
- Creator turn：
  - `createProductFromPrompt()` 新建 session，workspace 指向 draft workspace。
  - `continueCreatorDraftTurn()` 把 initial text 放入 composer。
  - 设置 `window._nextAiPendingHiddenAgentInstruction = _creatorDraftInstruction(...)`。
  - 调全局 `send()`。
- publish：
  - `messages.js` 每次 stream done 后都会调用 `publishCreatorDraftIfReady({silent:false})`。
  - `_currentCreatorDraftPayload()` 只有当前 workspace 命中 `product_drafts` 时才返回 payload。
  - `/api/product-drafts/publish` -> `publish_product_draft()`。
  - `if_ready` 默认 true；只有 `draft_status` 是 ready/publish/published/final 才发布。
  - clarifying/draft/working/needs_input/not_ready 不发布。

当前确认的优点：

- Creator instruction 已经明确写了：
  - `draft_status="clarifying"` 用于讨论/塑形阶段。
  - 只有用户明确确认，或请求已经足够具体时，才设置 `draft_status="ready"`。
  - host 只在 ready 时发布。
- 后端 publish gate 和测试已经对齐：
  - 创建 draft 不注册产品。
  - ready 后 publish 注册正式产品。
  - clarifying + if_ready 不发布。
- draft workspace 有路径隔离：`_product_draft_workspace_from_body()` 要求 workspace 在 `PRODUCT_DRAFTS_DIR` 下。
- promote 会把 `ui_mode:"canvas"` / `product_layout:"canvas"` 兼容转换成正式值。
- publish 后写 `.knead-published.json`，重复 publish 能打开已有 product。

当前确认的问题：

- Creator instruction 同时说 “The host publishes the AI only when draft_status is ready” 和 “This is still a draft until the user chooses to publish it”。但实际 host 会在 done 后自动尝试 publish ready draft；“用户选择发布”这句话容易让 agent 不敢把 ready 写上。
- productize marker 的 `title/type` 解析了，但 click handler 没传：
  - `_parseProductSuggestMarker()` 返回 `{title,prompt,type}`。
  - button 只写 `data-product-prompt`。
  - `_onProductSuggestClick()` 只调用 `createProductFromPrompt(prompt)`。
  - `createProductFromPrompt()` 也只接受 string prompt，不接受 object payload。
- draft create 默认 `product_type/custom`、`chat_only`，没有承接 marker type 或 creation hint。
- Creator hidden instruction 仍通过 `_nextAiPendingHiddenAgentInstruction` 拼入下一次 `send()` 路径；这和前面 chat turn contract 的 internal_context TODO 是同一个根问题。
- 前端 done 后自动 publish 没有测试：
  - ready draft 是否会 publish。
  - clarifying draft 是否只返回 not_ready。
  - done 后非 draft workspace 不会误 publish。
  - 已 published draft 是否打开 existing product。
- 没有测试 productize marker 的 title/type 下传。
- `.agents/skills/knead-product/SKILL.md` 讲的是产品 workspace 编辑和 bridge contract，但没有写 draft 生命周期/`draft_status`；Creator internal instruction 和 skill 文档不是同一个事实源。

需要澄清的产品语义：

- 如果 Creator 可以在“请求已经足够具体”时自动 ready 并让 host 发布，那文案应避免暗示必须再次用户点击发布。
- 如果产品想要“用户显式确认后才发布”，那 host done 后自动 publish 逻辑应改成只展示确认 UI，而不是自动 publish ready draft。
- 当前代码更接近第一种：足够具体即可自动 ready，host 自动 publish。

建议：

- 把 Creator draft lifecycle 写成 contract：
  - `clarifying`：继续问/继续塑形，不发布。
  - `ready`：host 可自动 publish。
  - `published`：幂等打开已有 product。
  - `not_ready/needs_input`：显式等待用户。
- 修改 Creator instruction 文案，去掉“until the user chooses to publish it”的歧义，改成“until the host publishes a ready draft”之类。
- `createProductFromPrompt()` 支持 object payload：
  - `{title, prompt, type}`。
  - string 继续兼容。
- productize button 写入 `data-product-title` / `data-product-type`，click 时完整传入。
- draft manifest 增加受控 initial metadata：
  - `creation_hint` / `initial_metadata`。
  - `suggested_type` 走白名单映射，不让任意字符串直接进入 product schema。
- Creator internal instruction 改到 structured `internal_context`，不要拼进 visible message。
- 测试：
  - productize marker parse/render/click 保留 title/type。
  - `createProductFromPrompt({title,prompt,type})` body 传到 draft create。
  - Creator instruction 包含 ready gate 且不含互相矛盾的 publish 文案。
  - stream done 只在 draft workspace 调 publish。
  - ready/clarifying/already_published 三种 publish 前端行为。

更新后的下一轮建议：

1. 读 `apps/webui/tests`，设计 bridge SDK/host 和 productize marker 的测试入口。
2. 如果开始动实现，第一批可选小修：
   - productize marker title/type 下传。
   - Creator instruction 去歧义。
   - product preview HTML/SVG response contract。

## 65. 第三十轮：frontend product/bridge 测试入口复核

本轮重点看测试体系本身，确认 bridge SDK / host / productize marker 应该怎样落测试，避免继续堆脆弱静态字符串测试。

读到的文件：

- `apps/webui/tests/conftest.py`
- `apps/webui/tests/test_product_scope_lines.py`
- `apps/webui/tests/test_product_ui_status.py`
- `apps/webui/tests/test_product_drafts.py`
- `apps/webui/tests/test_knead_product_skill.py`
- `apps/webui/tests/test_1062_busy_input_modes.py`
- `apps/webui/tests/test_renderer_js_behaviour.py`
- `apps/webui/tests/test_reasoning_chip_js_behaviour.py`
- `apps/webui/tests/test_kanban_ui_static.py`
- `apps/webui/tests/test_cli_only_slash_commands.py`
- `apps/webui/static/product-bridge-sdk.js`
- `apps/webui/static/product-runtime.js`

测试体系现状：

- `apps/webui/tests` 约 553 个测试文件，主入口是 pytest。
- `apps/webui` 没有自己的 Vitest/Jest/jsdom 配置。
- `conftest.py` 做了比较强的隔离：
  - 独立 test state dir。
  - 自动派生 test port。
  - 默认禁止公网网络。
  - 生产状态路径被环境变量切到测试目录。
- 前端 JS 测试现在主要有三类：
  - 纯静态 source grep。
  - Python 调 Node，extract 真实 JS function 后行为测试。
  - Node `vm.runInContext()` 执行整个 JS 文件或大块脚本，mock browser globals。

可借鉴的好测试模式：

- `test_renderer_js_behaviour.py`：
  - 用 Node 运行真实 `static/ui.js` 中的 `renderMd()`。
  - 比 Python mirror 更能防 drift。
- `test_reasoning_chip_js_behaviour.py`：
  - mock DOM element。
  - extract 真实函数，断言行为输出。
- `test_kanban_ui_static.py` / `test_cli_only_slash_commands.py`：
  - 用 `vm.runInContext()` 执行实际 JS。
  - 适合 IIFE 或依赖全局变量的文件。

不稳定的测试模式：

- `test_1062_busy_input_modes.py` 有多个固定窗口截取：
  - `idx:idx+800`
  - `send_idx:send_idx+3000`
  - `send_idx:send_idx+5000`
- 当前这类测试已经失败过：源码里逻辑存在，但函数体增长后超出窗口。
- 更稳的方式：
  - 用 brace matching 提取完整函数体。
  - 或用 Node/vm 跑真实行为。
- Node 行为测试也要固定测试前提：
  - `test_reasoning_chip_js_behaviour.py` 当前期待英文 label/title。
  - 实际 `ui.js` 已返回中文 label/title（例如 `默认`、`关闭`、`思考强度：默认`），导致该测试 9 个失败。
  - 这不是 Node/vm 模式的问题，而是测试没有 mock/固定 locale，或断言过度绑定展示文案。

本轮临时 Node 验证：

1. `product-bridge-sdk.js` SDK 行为可测：
   - mock `window.parent.postMessage`、`window.addEventListener`、`localStorage`。
   - `NextAI.chat.send()` 会 post `nextai:product:send`。
   - `nextai:host:ack` 只 dispatch `nextai:ack`，不会 settle promise。
   - `nextai:host:reply` 后 promise resolve。
   - SDK 返回 `{content, raw}`，`raw` 保留原始 reply payload。
2. `NextAI.state` fallback 可测：
   - host state 请求超时时，`state.set/get` fallback 到 iframe localStorage。
   - fallback key 形如 `nextai:state:session:<key>`。
3. `product-runtime.js` host download 问题可测：
   - mock active iframe window 和 `fetch()`。
   - 发送 `{type:'nextai:product:download', url:'https://evil.example/file.txt'}`。
   - host 直接 fetch 该外部 URL 并触发下载。
   - 说明没有 allowlist，这不是只靠代码阅读的推断。
4. `product-runtime.js` host pending 覆盖问题可测：
   - 同一个 session 连发 `r1`、`r2` 两个 canvas request。
   - 两个都收到 ack。
   - `notifyProductCanvasAgentReply({sessionId:'sid-1'})` 只回 `requestId:'r2'`。
   - `r1` 被 `Map<sessionId,pending>` 覆盖。

本轮测试结果：

- 通过：
  - `.venv311/bin/python -m pytest tests/test_product_scope_lines.py tests/test_product_drafts.py tests/test_knead_product_skill.py tests/test_renderer_js_behaviour.py`
  - 87 passed。
- 失败但已归因：
  - 加上 `tests/test_reasoning_chip_js_behaviour.py` 后：98 collected，89 passed，9 failed。
  - 失败原因是测试期望英文文案，但当前实际 UI 文案是中文。
  - 这个结果被记录为 JS 行为测试 hygiene 问题，不属于本轮 product/bridge 逻辑变更。

建议的测试落点：

- 新建 `tests/test_product_bridge_sdk_js_behaviour.py`：
  - 用 Node/vm 加载 `static/product-bridge-sdk.js`。
  - 覆盖 ack 不 resolve、reply resolve、error reject、ready/agent event、source guard、state fallback。
- 新建 `tests/test_product_bridge_host_js_behaviour.py`：
  - 用 Node/vm 加载 `static/product-runtime.js`。
  - mock `$('activeProductFrame')`、`S`、`send()`、`fetch()`、`document`。
  - 覆盖 download allowlist（当前应先写成待修 TODO，或实现后再上断言）。
  - 覆盖 pending requestId 不串线。
  - 覆盖 host timeout 主动 error。
- 新建 `tests/test_productize_marker_js_behaviour.py`：
  - 用 Node extract `_stripProductSuggestMarker()`、`_parseProductSuggestMarker()`、`_onProductSuggestClick()`。
  - mock `createProductFromPrompt()`。
  - 覆盖 marker title/type/prompt 不丢。
  - 覆盖未闭合 marker 不渲染。
- 修 `test_1062_busy_input_modes.py`：
  - 先抽一个 Python helper：按函数名 brace-match 完整函数体。
  - 替换固定字符窗口。

下一步建议：

1. 如果继续纯梳理：读 `messages.js send()` 的完整函数体，用 function-body extraction 方式重新标注 busy / product / journal / creator publish 的分支。
2. 如果开始小修：优先修 `productize marker title/type 下传`，因为范围小、测试入口清楚、不会碰 bridge 大状态。
3. bridge 相关修复要先上行为测试，再改 host pending/download。

## 66. 第三十一轮：`messages.js send()` / SSE done / queue drain 全流程复核

本轮按真实行号补读 `messages.js send()`、`attachLiveStream()` 的 done 收尾，以及 `ui.js` queue drain。目标是确认“发送一轮消息”到底承担了多少职责，以及 hidden instruction / product context / queued turn 在哪里相互污染。

读到的文件：

- `apps/webui/static/messages.js`
- `apps/webui/static/ui.js`
- `apps/webui/static/sessions.js`
- `docs/ENGINEERING_HEALTH_TODO.md`

当前代码体量：

- `messages.js` 约 3296 行。
- `ui.js` 约 7961 行。
- `commands.js` 约 1407 行。

`send()` 主流程当前分段：

- `messages.js` 390-407：`_sendInProgress` re-entrant guard。
  - 如果发送已经进行中，会把当前 composer 文本 + pending files + model/profile 入队。
  - 这里用 `withCurrentProductContext()` 尝试补 product context。
- 410-413：读取并清空 `window._nextAiPendingHiddenAgentInstruction`。
- 416-441：Create AI 特殊入口。
  - 当前 AI 是 `create`、非 draft session 时，第一条消息转成 `createProductFromPrompt()`。
  - Creator draft 再通过 `continueCreatorDraftTurn()` 回到 `send()`。
- 448-521：busy/compression 分支。
  - 先拦截 `/steer`、`/interrupt`、`/queue`、`/terminal`、`/goal`。
  - 再按 `window._busyInputMode` 做 queue / interrupt / steer。
  - queue payload 仍通过 `withCurrentProductContext()` 现算。
- 526-583：slash command 正常分支。
  - echo/noEcho、CLI-only、Plugin command 都在 `send()` 里处理。
- 586-604：确保 session、上传文件、构造 `msgText`。
- 606：`hiddenAgentInstruction` 直接拼进 `msgText`。
- 608-616：调用 `currentAssistantProductContextForMessage(text || msgText)`，并把 product context 写回当前 `S.session`。
- 619-646：清 composer、构造 visible user bubble、running product status card、INFLIGHT、approval/clarify polling。
- 666-715：POST `/api/chat/start`。
  - request body 的 `message` 是 `msgText`，也就是可能已经带 hidden instruction 的文本。
  - product context 作为顶层字段展开。
- 718-737：`/api/chat/start` active-stream conflict。
  - 删除 inflight。
  - `queueSessionMessage(activeSid, {text: msgText, ...productContext})`。
  - 这里明确会把拼接后的 `msgText` 入队。
- 760：`attachLiveStream(activeSid, streamId, uploadedNames)`。

`attachLiveStream()` / SSE done 当前收尾：

- 760-910：live stream 管理、INFLIGHT persistence、owner helpers、run journal replay cursor。
- 1530-1810：共享 SSE handler。
  - token/reasoning/tool/tool_complete/approval/clarify/title/goal 等事件都在一个大闭包里。
- 1810-2025：`done` handler。
  - finalizes stream DOM / smd parser / thinking card。
  - 用 `d.session` 覆盖 `S.session` / `S.messages`。
  - 计算 usage delta、tool calls、uploaded attachments、goal status。
  - 调 `notifyProductCanvasAgentReply()` 和 `broadcastAgentMessageToCanvas()`。
  - 如果 `nextAiProductAdjust=open`，调用 `reloadActiveProductPreview()`。
  - 调 `publishCreatorDraftIfReady({silent:false})`。
  - 调 `refreshCurrentProductPreview()`，再补 done/failed product status card。
  - 处理 goal continuation queue。
  - 设置 `_queueDrainSid=activeSid`，最后 `_setActivePaneIdleIfOwner()` -> `setBusy(false)`。
- 2330-2435：settled restore path。
  - 也会设置 `_queueDrainSid=activeSid` 再 `_setActivePaneIdleIfOwner()`。
  - 但它不做 bridge reply / Creator publish / preview refresh 这套 done path 逻辑。

Queue 当前实现：

- `ui.js` 119-140：
  - `queueSessionMessage(sid, payload)` 直接 shallow copy payload，加 `_queued_at` 后保存到 `SESSION_QUEUES` 和 `sessionStorage`。
  - 这个容器本身可以承载未来 `internal_context`。
- `ui.js` 3105-3146：
  - `setBusy(false)` drain 一条 queue。
  - 只在完成的 sid 仍是当前 viewed session 时 drain。
  - 把 queued item 拆回：
    - composer `#msg` = `sendText || text`
    - `window._nextAiPendingProductScope`
    - `window._nextAiPendingProductIntent`
    - `S.pendingFiles`
    - `S.session.model/model_provider`
  - 然后调用全局 `send()`。
  - 没有显式恢复 `product_id`。
  - 没有恢复 `internal_context`。
- `ui.js` 3196-3235：
  - queue merge 会合并 text。
  - 合并后的 item 只保留 first product metadata，且没有 internal context 规则。
- `ui.js` 3260-3355：
  - queue chip inline edit 只改 `text`，其它 hidden metadata 保留但不可见。
- `sessions.js` 698-722：
  - refresh restore 只把第一条 `_fresh[0].text` 放回 composer。
  - 然后删除 `sessionStorage` 中整个 queue。
  - files/model/product context/internal context 都不会完整恢复。

当前确认的优点：

- `_sendInProgress` early guard 是必要的，避免 queue drain + 用户点击同时通过 `S.busy`。
- queue payload 是开放对象，这为后续 structured request 迁移留了空间。
- `_queueDrainSid` 解决了一部分“完成的 session 和当前查看 session 不一致”问题。
- `productUiStatusContext` 已经在 INFLIGHT 中持久化，说明 product turn status 可以抽成独立 controller。
- done path 里 bridge reply 和 broadcast 分开，语义上可拆。

当前确认的问题：

- `send()` 不只是发送：
  - create product intercept。
  - busy mode routing。
  - slash command runtime。
  - upload。
  - optimistic session list。
  - product status card。
  - `/api/chat/start`。
  - SSE attach。
  - error/conflict queue。
  - 这些全在一个函数内，维护者必须一次理解完整 WebUI。
- hidden instruction 的污染点很明确：
  - 先读全局 `_nextAiPendingHiddenAgentInstruction`。
  - 再拼到 `msgText`。
  - 再作为 `/api/chat/start.message` 发后端。
  - conflict 时还会以 `text: msgText` 入队。
- product context 生成依赖当前 assistant selection：
  - queue entry 即使保存了 `product_id`，drain 时也只恢复 scope/intent。
  - 下一次 `send()` 仍会重新从当前 assistant 推导 product_id。
- `setBusy(false)` 是业务 drain 入口：
  - 这个名字看起来只是 UI busy state，但实际还会自动发下一条 queued turn。
  - 这让 queue drain 和 UI state 过度耦合。
- SSE done handler 是第二个巨型收口点：
  - bridge reply、Creator publish、preview refresh、product status card、goal continuation、notification 都放在同一处。
  - settled restore path 没有同等 product/bridge/Creator 收尾，语义不完全一致。
- refresh restore queue 会丢完整 queued request：
  - 只恢复 text 到 composer。
  - 删除 queue storage。
  - 后续用户手动发送时上下文已降级成普通 composer text。

建议的拆分方向：

- 抽 `buildChatTurnRequest()`：
  - 输入：composer text、pending files、selected model/session、product context、internal context。
  - 输出：`visibleMessage`、`attachments`、`productContext`、`internalContext`、`transportPayload`、`displayUserMessage`。
- 抽 `sendChatTurnRequest(request)`：
  - 不读 DOM。
  - 不读 `_nextAiPending*` 全局。
  - 只负责 `/api/chat/start` + inflight setup。
- 抽 `queuedTurnRequest` serializer：
  - `queueSessionMessage()` 保存规范化 request。
  - drain 直接发送 request，composer 只是展示层。
- 抽 `productTurnCompletionController`：
  - 处理 product status card、preview refresh、Creator publish。
  - done / restore / error / cancel 走同一组接口。
- 抽 `bridgeReplyController`：
  - 从 assistant message 生成 bridge reply typed payload。
  - 和 `broadcastAgentMessageToCanvas()` 分开测试。
- `setBusy(false)` 不再直接 drain：
  - 改成 emit/调用 `onTurnBecameIdle(sessionId)`。
  - queue controller 决定是否 drain。

下一步建议：

1. 若继续阅读：补读 `/api/chat/start` route handler 的完整 request path，对照 `send()` payload。
2. 若开始小修：先做 productize marker metadata 下传，避开 `send()` 巨型改动。
3. 若开始拆 `send()`：第一步不要改行为，只加测试和 extract helper，替换固定窗口静态测试。

本轮核对：

- `node --check apps/webui/static/messages.js && node --check apps/webui/static/ui.js` 通过。
- `.venv311/bin/python -m pytest tests/test_1062_busy_input_modes.py`：
  - 27 collected，24 passed，3 failed。
  - 失败仍是固定字符窗口截断：
    - `cmdQueue` 的 `renderTray()` 在源码存在，但超出 `idx:idx+800`。
    - `_busyInputMode`、`cancelStream` 在 `send()` 中存在，但超出 `send_idx:+3000/+5000`。

## 67. 第三十三轮：`/api/chat/start` 后端请求链路精读

本轮继续沿着前端 `send()` 的 payload 往后端追，目标是把“用户可见 message”和“内部上下文 internal context”应该在哪些点分离说清楚。

后端主链路：

- `routes.py` 7948-8090：`_handle_chat_start()`。
  - 7951-7959：要求 `session_id`，读取 session。
  - 7982-7985：`msg = str(body.get("message", "")).strip()`，空字符串直接 400。
  - 7986-7987：normalize attachments。
  - 7989-7992：解析 workspace。
  - 7994-8001：`product_context_request_body(body, s, msg)` 后再 `product_context_from_request(...)`。
  - 8012-8019：build/init scope 时尝试 snapshot product。
  - 8020-8027：`record_product_session(... ui_status="generating")`。
  - 8045-8071：runtime adapter 开启时把 `msg` 放进 `StartRunRequest.message`。
  - 8077-8087：普通路径把 `msg` 传给 `_start_chat_stream_for_session()`。
- `product_context.py` 120-157：`product_context_request_body()`。
  - 如果请求没带 product id，会从 session 恢复。
  - 如果 body 没有 `message/text`，会把 `message` 补成传入的 `message` 参数。
  - 如果缺 `product_intent`，有旧 session intent 且无历史时用 session intent，否则用 `message`。
  - 这意味着 `message` 如果被 hidden instruction 污染，product intent fallback 也会被污染。
- `product_context.py` 160-230：`product_context_from_request()`。
  - `intent = product_intent/productIntent/message`。
  - `infer_product_scope()` 基于 intent 和 explicit scope 推导 build/use 线。
  - build 线会校验 workspace 必须等于 product workspace；use 线保留当前会话 workspace。
  - product prompt 已经走结构化 context，再由 `product_ephemeral_prompt()` 注入 agent，这条路是正确方向。
- `routes.py` 7665-7704：`_prepare_chat_start_session_for_stream()`。
  - `s.pending_user_message = msg`。
  - 默认标题从 `msg` 生成。
  - eager save 时 `_checkpoint_user_message_for_eager_session_save(... msg ...)` 会把 `msg` 写入 `messages`。
- `routes.py` 7707-7825：`_start_chat_stream_for_session()`。
  - active stream guard 返回 409。
  - session lock 内写 pending state，再写 product session binding。
  - 7775-7794：append submitted turn journal，`content: msg`。
  - 7807-7810：启动 `_run_agent_streaming(..., msg, ..., product_context=product_context)`。
- `streaming.py` 149-157：`_webui_ephemeral_system_prompt(personality_prompt, product_prompt)`。
  - 已经是“非持久化 runtime instruction”的入口。
  - 当前只支持 personality + visible progress + product prompt。
- `streaming.py` 2765-2777：`_run_agent_streaming()` 签名仍只有 `msg_text`，没有 `internal_context`。
- `streaming.py` 3888-3894：product context 生成 `_product_prompt`，并放进 `_webui_ephemeral_system_prompt()`。
- `streaming.py` 3901-3902：历史上下文用 `_context_messages_for_new_turn(s, msg_text)`。
- `streaming.py` 3947-3958：真正调用 agent：
  - `_agent_msg_text = msg_text`。
  - process notifications 会拼到 agent input 前面。
  - `persist_user_message=msg_text`。

结论：

- 当前后端没有“chat turn request”这个独立模型。
- `msg/message/msg_text` 同时承担：
  - 用户可见消息。
  - session pending user message。
  - eager save 的 user message。
  - provisional title seed。
  - product intent fallback。
  - turn journal submitted content。
  - agent user_message。
  - `persist_user_message`。
  - crash/error/cancel recovery 的恢复来源。
- 因此前端把 hidden instruction 拼进 `message` 后，不只是 UI 显示问题，而是后端 contract 被污染。
- 产品上下文本身已经有比较正确的结构化方向：`product_context` -> `product_ephemeral_prompt()` -> `_webui_ephemeral_system_prompt()`。
- Creator draft / canvas bridge 这类内部指令应该复用同一类注入口，而不是继续拼进 `message`。

更准确的重构落点：

1. 新增 `normalize_chat_start_payload(body, session)`：
   - 输出 `visible_message`。
   - 输出 `attachments`。
   - 输出 `product_context_body` / `product_context`。
   - 输出 `internal_context`。
   - 兼容旧字段 `hidden_instructions`。
2. `_handle_chat_start()` 只把 `visible_message` 传入 `_start_chat_stream_for_session()`。
3. `_start_chat_stream_for_session()` 增加 `internal_context=None`：
   - pending、title、journal、thread args 继续使用 visible message。
   - response 可选返回 redacted `internal_context_kinds` 方便 debug。
4. `_run_agent_streaming()` 增加 `internal_context=None`：
   - `persist_user_message` 仍是 visible message。
   - `_context_messages_for_new_turn()` 仍看 visible message。
   - `agent user_message` 可保持 visible message。
   - internal context 转成 runtime prompt 后进入 `_webui_ephemeral_system_prompt()`。
5. `_webui_ephemeral_system_prompt()` 改为接收更多 instruction parts：
   - personality。
   - WebUI progress contract。
   - product prompt。
   - internal context prompt。
   - 后续可以变成 `build_webui_runtime_prompt(parts)`，避免签名一直增长。

建议测试：

- `/api/chat/start` 收到 `message="hello"` + `internal_context`：
  - `pending_user_message == "hello"`。
  - eager save 的 user message content 是 `"hello"`。
  - submitted journal `content == "hello"`。
  - `persist_user_message == "hello"`。
  - agent `ephemeral_system_prompt` 含 internal context prompt。
- `product_context_request_body()`：
  - explicit `product_intent` 优先，不被 message 影响。
  - 缺 intent 时只使用 visible message。
- 409 conflict queue：
  - queued `text` 是 visible message。
  - `internal_context` 存在独立字段。
- cancel/error recovery：
  - `_materialize_pending_user_turn_before_error()` 恢复 visible message。
  - cancel recovery 不恢复 hidden/internal context 到 user bubble。

当前测试债：

- `test_turn_journal_callsite.py` 仍是源码字符串顺序测试，只保护“append 在 thread 前”。
- 它不能证明 submitted content 的语义，也不能覆盖 internal context。
- 后续应增加行为测试，mock session + `_run_agent_streaming` + `append_turn_journal_event`，捕获 payload。

## 68. 第三十四轮：`api/products.py` 产品注册 / draft / snapshot / preview 服务层

本轮逐段读 `apps/webui/api/products.py` 1-1421、`routes.py` 产品 GET/POST/preview 路由，以及当前产品相关测试。

当前职责图：

- `products.py` 1-120：产品根目录、内置产品、工具 alias、锁。
- 127-188：id/string/toolset/capability normalization。
- 196-247：seed HTML。
- 250-335：`ai_products.json` 读写和 `_normalize_product()`。
- 342-408：内置产品 ensure。
- 422-475：seed files + `product.json` manifest 写入。
- 478-499：workspace 注册/注销。
- 501-592：entry 是否生成、`ui_status` 派生矩阵。
- 595-654：list/get/create product。
- 657-876：draft create/publish。
- 879-963：update/delete product。
- 966-1219：snapshot / rollback。
- 1222-1352：record session / finalize generation / reconcile status。
- 1355-1421：file status / preview asset resolver。

读完后的整体判断：

- 局部设计并不差，尤其是 `_resolve_ui_status()`：
  - 注释有规则表。
  - 纯函数，不做 I/O。
  - list/status/finalize/reconcile 都复用它。
  - 这是这个文件里比较优雅的部分。
- draft 和 product 的边界也有意识：
  - draft 不进入 `ai_products.json`。
  - publish 时才 copy 到 `products/<id>`。
  - `if_ready` 防止还在 clarifying 的 draft 自动上架。
- snapshot/rollback 的路径安全方向也正确：
  - snapshot 枚举 root 下文件。
  - 跳过 hidden file、versions、node_modules、大文件。
  - rollback 时 source/destination 都做 `relative_to()`。
- 主要问题不是单个函数“看不懂”，而是一个模块同时管理太多事实源：
  - `ai_products.json`
  - `products/<id>/product.json`
  - product workspace files
  - `workspaces.json`
  - versions snapshots
  - session/product binding
  - preview asset serving
  - draft workspace

具体优点：

- `_normalize_product()` 是事实归一化入口，支持 snake/camel alias。
- `_resolve_ui_status()` 明确区分 stored status 和 derived status，避免 list/read 悄悄写状态。
- `reconcile_product_status()` 把“读时派生”和“显式修复写入”分开，语义比很多隐式 self-heal 清楚。
- `record_product_session()` 在进入 build/init turn 时写 `generation_started_at`，配合 timeout 避免 generating 永久卡住。
- `finalize_product_generation()` 会读取 agent 写入的 `product.json` manifest patch，把产品身份/布局变更同步回 registry。
- `publish_product_draft()` 用 `.knead-published.json` 避免重复发布同一个 draft。

具体风险：

1. Registry 写入不是 atomic。
   - `_write_state()` 直接 `PRODUCTS_FILE.write_text(...)`。
   - 如果写到一半崩溃，`_read_state()` catch 后会返回空 products。
   - 下一次 `_ensure_builtin_products_locked()` 可能重建内置产品，但 custom products 需要人工恢复。
   - session 侧已经很重视 WAL/sidecar/recovery；product registry 这里还没有同等级保护。

2. `create_product()` 返回/持久化的 tools 可能和后续读出的 tools 不一致。
   - 630：先 `_normalize_product()`。
   - 645-646：如果 body 自带 `tools`，又把 `product["tools"]` 改成 `_unique_strings(body.get("tools"))`。
   - 之后直接 `_write_state()`。
   - 后续 `_read_state()` 会再 `_normalize_product()`，才会走 `normalize_product_toolsets()`。
   - 因此 create response / state-on-disk / later list response 可能短暂不一致。
   - 这里应该用 `normalize_product_toolsets()`，或者二次 `_normalize_product()` 后再写。

3. Builtin product 是“定义强覆盖”，不是完全自演化产品。
   - `_ensure_builtin_products_locked()` 对已有 builtin 做 `{**existing, **definition}`。
   - definition 会覆盖 title/desc/suggestions/source_prompt/tools 等字段。
   - 如果 agent 改了 builtin product 的 manifest，并通过 finalize sync 到 state，下一次 ensure 仍可能被 builtin definition 覆盖。
   - 这可能是有意的“内置模板稳定”，但应该文档化：builtin 是否允许被产品自己修改？

4. Draft publish readiness 规则过窄。
   - `_draft_changed_enough_for_publish()` 现在只认 `draft_status in {"ready","publish","published","final"}`。
   - `original_title` 参数传入但实际没有参与判断。
   - 这使得 Creator 必须非常准确写状态；否则即使 manifest 内容已足够，也不会上架。
   - 短期安全，但对 Creator 指令依赖强。

5. Preview resolver 没走 builtin ensure。
   - `preview_product_file()` 使用 `_read_state()`。
   - clean state 下，如果用户直接打开 `/api/products/general/preview`，它不一定先 ensure builtin。
   - `list_products()` / `get_product()` 会 ensure，但 direct preview route 排在 `/api/products` list 前。
   - 这就是 preview resolver 应该成为单一 product asset service 的原因。

6. Preview route matching 太宽。
   - GET route：`parsed.path.startswith("/api/products/") and "/preview" in parsed.path`。
   - `_serve_product_preview()` 再用 `rest.split("/preview", 1)`。
   - 这不是 segment-level match，`previewevil`、包含 preview 字符串的路径都会进 preview 分支。
   - 应该按 path segments 解析：`/api/products/{id}/preview` 或 `/api/products/{id}/preview/{asset...}`。

7. Product preview response 安全策略不足。
   - `_serve_file_response()` 只设置 Content-Type、no-store、length。
   - 没有 CSP sandbox。
   - 没有 HTML/SVG dangerous MIME 策略。
   - iframe sandbox 只能保护 iframe 场景，用户直接打开 preview URL 时仍是同源页面。

8. `update_product()` patch 面较宽。
   - 允许外部 patch `versions`、`sessions`、`ui_status`。
   - 这些字段有生命周期含义，但目前和普通 UI metadata 走同一个 update endpoint。
   - 后续拆模块时应把 public update 和 internal lifecycle update 分开。

9. Snapshot/rollback 目前测试缺口明显。
   - 代码已经有不少路径保护。
   - 但当前 product tests 里没有直接覆盖 `snapshot_product()` / `rollback_product()`。
   - 没有覆盖 managed file 删除、nested asset、hidden file skip、大文件 skip、version cap。

当前测试覆盖：

- `test_product_drafts.py`：
  - draft 不进入 shelf。
  - ready draft 发布为真实 product。
  - clarifying + `if_ready` 不发布。
- `test_product_ui_status.py`：
  - `_resolve_ui_status()` 矩阵。
  - file status pure read。
  - reconcile 持久化。
  - finalize chat_only manifest。
- `test_product_scope_lines.py`：
  - use/build line。
  - workspace guard。
  - builder/use toolset。
  - product prompt guard。

缺口：

- `preview_product_file()` 没有行为测试。
- `_serve_product_preview()` / `_serve_product_asset()` 没有 route-level 测试。
- `create_product()` 自带 tools alias 的响应/持久化一致性没有测试。
- `_write_state()` atomic/recovery 没有测试。
- builtin direct preview clean state 没有测试。
- builtin self-modification 是否保留没有测试/文档。
- snapshot/rollback 没有专门测试。

建议拆分：

- `product_registry.py`
  - `_read_state` / `_write_state` / atomic replace / migration / normalize。
- `product_manifest.py`
  - manifest read/write、schema normalization、agent-owned patch allowlist。
- `product_lifecycle.py`
  - create/update/delete、record session、finalize/reconcile。
- `product_drafts.py`
  - draft create/publish/readiness。
- `product_versions.py`
  - snapshot/list/rollback。
- `product_assets.py`
  - preview resolver、MIME/disposition/CSP policy。
- `routes_products.py`
  - all `/api/products*` routing，segment parser。

短期可先做的最小安全改动：

1. 给 `_write_state()` 做 tmp + atomic replace。
2. `create_product()` body tools 改成 `normalize_product_toolsets()`，并加测试。
3. `preview_product_file()` 改为通过 ensure 后的 product lookup。
4. preview route 改成 segment-level match。
5. `_serve_file_response()` 对 product HTML/SVG 加 CSP/disposition policy。
6. 补 `snapshot_product()` / `rollback_product()` 单测。

## 69. 第三十五轮：`ui.js` 巨型前端壳体结构

本轮读 `apps/webui/static/ui.js` 的顶层结构、全局状态、queue/busy、topbar、message render、workspace file tree、attachments/upload 等关键区段。

当前文件体量：

- `apps/webui/static/i18n.js`：11532 行。
- `apps/webui/api/routes.py`：10720 行。
- `apps/webui/static/ui.js`：7961 行。
- `apps/webui/static/style.css`：6997 行。
- `apps/webui/api/streaming.py`：5534 行。
- `apps/webui/static/messages.js`：3296 行。
- `apps/webui/static/sessions.js`：3848 行。
- `apps/webui/static/product-shell-runtime.js`：2195 行。

`ui.js` 顶层大致职责：

- 1-13：全局 app state：
  - `S`
  - `INFLIGHT`
  - `SESSION_QUEUES`
  - `_queueDrainSid`
  - `$` DOM helper
- 14-116：offline monitor / fetch patch。
- 117-146：session queue primitive。
- 153-279：escaping、user fenced block、status card。
- 280-409：message render window / jump buttons。
- 410-557：image lightbox、attachment/media renderer。
- 558-642：provider quota indicator。
- 644-1399：model dropdown / smart model resolver / live model fetch。
- 1401-1519：reasoning effort chip。
- 1520-1688：toolsets/access preset chip。
- 1696-1759：mobile composer config。
- 1761-2204：scroll pinning / context indicator / composer context display。
- 2218-2382：model labels、product suggest marker、markdown helper entry。
- 2382-2933：`renderMd()` 及 markdown/html sanitization pipeline。
- 2934-3146：status/composer lock/primary action/`setBusy()`。
- 3148-3422：queue chip UI。
- 3423-3615：toast + shared dialogs。
- 3616-3780：copy + TTS。
- 3781-3899：inflight/reconnect recovery。
- 3901-4066：system health + agent heartbeat。
- 4068-4479：session refresh / update banner。
- 4482-4657：pending session message + `syncTopbar()`。
- 4659-5310：message content helpers、thinking/compression/handoff cards。
- 5312-6102：`renderMessages()`。
- 6104-6369：tool cards + live tool card helpers。
- 6373-6481：edit/regenerate/post-process。
- 6482-7209：syntax highlight、tree view、copy buttons、mermaid/csv/excalidraw/pdf/html/katex inline render。
- 7210-7877：workspace breadcrumb/file tree/context menu/new file/folder/delete/rename。
- 7878-7961：attachment tray + upload.

这说明 `ui.js` 不是单纯 UI 文件，而是：

- app shell state store。
- composer controller。
- model/profile/toolset selector controller。
- queue controller。
- message renderer。
- markdown/media renderer。
- reconnect/session recovery UI。
- system health/update UI。
- workspace file explorer。
- attachment upload controller。

具体优点：

- 这个文件不是“随便堆代码”：
  - 很多区段有 issue 注释和回归背景。
  - message render 有窗口化和 HTML cache，说明性能问题被处理过。
  - markdown 渲染有 sanitizer 注释，安全意识存在。
  - workspace file tree 有隐藏文件过滤、rename debounce、expanded dirs cache。
  - queue UI 支持拖拽、编辑、合并、collapse。
- 作为“旧式全局脚本”还能运行，是因为约定很稳定：
  - `S` 作为单一 mutable state。
  - DOM id 作为组件边界。
  - `window.*` 作为模块间 API。
  - script order 决定函数可见性。

具体风险：

1. `S` 过于宽泛。
   - `S.session`、`S.messages`、`S.entries`、`S.busy`、`S.pendingFiles`、`S.currentDir`、`S.activeProfile`、hidden-file pref、workspace expanded dirs/cache 都放在一起。
   - 消息渲染、workspace 文件树、composer、model dropdown、queue 都直接读写它。
   - 这会让“改一个局部 UI 状态”很难证明不会影响别处。

2. `setBusy(v)` 命名和实际职责不匹配。
   - 3105-3146：它不仅设置 `S.busy`。
   - 还会：
     - update send button。
     - sync assistant task UI。
     - 清 activity elapsed/status/composer status。
     - 用 `_queueDrainSid` 找刚完成的 session。
     - update queue badge。
     - shift queued message。
     - 把 queued fields 写回 composer、`window._nextAiPendingProductScope`、`window._nextAiPendingProductIntent`、`S.pendingFiles`、session model。
     - 调 `send()` 自动发送下一条。
   - 所以它本质是 `onTurnBecameIdle()` + `queue drain` + UI busy state 的混合。

3. Queue model 已经超过 string queue，但 drain 仍回退到 DOM/global state。
   - `queueSessionMessage()` 可以保存任意 payload。
   - `_renderQueueChips()` 显示 text/files/model。
   - merge 会保留 first product metadata。
   - drain 时没有直接构造 structured chat request，而是恢复 composer 后 `send()`。
   - 这和前面 chat turn/internal context 问题是同一个结构根源。

4. `renderMessages()` 是巨型 renderer。
   - 5457-6102 一次性处理：
     - sync task UI。
     - scroll snapshot。
     - session HTML cache。
     - compression/handoff state。
     - visible message filtering。
     - render window。
     - date separators。
     - reasoning/thinking extraction。
     - hidden product context stripping。
     - attachments。
     - product suggestion marker。
     - status cards。
     - assistant turn grouping。
     - compression/handoff card insertion。
     - historical tool card derivation。
     - usage/duration/gateway labels。
     - postProcess / media playback / cache write。
   - 这个函数是维护风险最大点之一，因为它既做 data preparation，又直接造 DOM，又处理 side effects。

5. Message renderer 仍依赖 inline `onclick` 字符串。
   - `product_suggest`、copy/edit/undo/regenerate/fork/TTS、tool card toggle、thinking toggle 等都在 HTML string 里写 `onclick=...`。
   - 这让模块拆分、CSP 收紧、测试 mock 都更困难。

6. Workspace file explorer 放在 `ui.js` 末尾。
   - 它有独立模型：
     - current dir。
     - entries。
     - expanded dirs。
     - dir cache。
     - hidden files pref。
     - context menu。
     - create/delete/rename。
   - 这块应该是 `workspace-tree.js` 或 `file-tree-controller.js`，和 message renderer 没必要在同一文件。

7. 测试多为静态源码窗口。
   - 当前测试里大量 `src.index(...)` / `block = body[start:end]`。
   - `test_1062_busy_input_modes.py` 已经因为 `send()` 变长而出现固定窗口失败。
   - `ui.js` 若继续靠静态窗口保护，会越来越脆。

建议拆分顺序：

1. 不先重写框架。
2. 先抽纯 helper：
   - `ui-state.js`：`S` facade、busy state setter、session id helpers。
   - `queue-controller.js`：queue storage/merge/drain request，不读 DOM。
   - `composer-controller.js`：primary action、pending files、upload tray。
3. 再抽 renderer：
   - `message-model.js`：normalize/visible messages/thinking extraction/product marker parse。
   - `message-renderer.js`：render turn DOM，输入 normalized model。
   - `message-postprocess.js`：highlight/copy/mermaid/katex/media。
4. 再抽 workspace：
   - `workspace-tree-controller.js`：entries/current dir/expanded/cache。
   - `workspace-context-menu.js`。
5. 再抽 chrome/controllers：
   - `model-picker.js`。
   - `reasoning-picker.js`。
   - `toolsets-picker.js`。
   - `health-panels.js`。
   - `update-banner.js`。

短期最值得做的改动：

- 把 `setBusy(false)` queue drain 改名/拆出：
  - `setBusyState(v)` 只更新 busy UI。
  - `onTurnBecameIdle(sessionId)` 负责 queue drain。
- 给 queue 定义 `QueuedTurnRequest`：
  - `visibleText`
  - `files`
  - `model/model_provider`
  - `product_context`
  - `internal_context`
  - `created_at`
- `renderMessages()` 先拆成纯 preparation：
  - `buildRenderableMessages(S.messages, options)`。
  - `buildMessageTurnNodes(renderModel)`。
- 禁止新增 inline `onclick`，新增事件走 delegated listener。
- 将 workspace file tree 整段迁到独立文件，先保留 `window.renderFileTree/loadDir/openFile` API 兼容旧调用。

判断：

- 可以用 TS，但不应该直接“把 8000 行 ui.js 改成 TS”。
- 更合理路线是先把 `queue-controller`、`message-model`、`product-model` 这些纯数据边界抽出来，再给这些边界加类型。
- `ui.js` 剩下的 DOM glue 最后再慢慢迁。

本轮验证：

- `node --check apps/webui/static/ui.js && node --check apps/webui/static/messages.js && node --check apps/webui/static/sessions.js` 通过。
- `.venv311/bin/python -m pytest tests/test_sprint9.py tests/test_status_command_card.py tests/test_workspace_display_prefix.py tests/test_tars_scroll_reset_regressions.py tests/test_workspace_panel_persists_on_empty_boot.py tests/test_1707_workspace_filename_click.py`：
  - 40 collected，36 passed，4 failed。
  - `test_sprint9.py` 仍期待旧函数名 `loadCrons/loadSkills` 存在。
  - `test_status_command_card.py` 期待旧 i18n 字符串形态 `cmd_status:'Show session info'`。
  - `test_workspace_display_prefix.py` 找到 legacy render loop 注释 `for(let vi=0;vi<visWithIdx.length;vi++)`，再在错误窗口里找 displayContent；这是静态字符串测试和真实 windowed render loop 脱节。
  - `test_tars_scroll_reset_regressions.py`、`test_workspace_panel_persists_on_empty_boot.py`、`test_1707_workspace_filename_click.py` 通过。

## 70. 第三十六轮：`routes.py` 路由巨石结构

这轮目标是回答：`routes.py` 是不是只是“长一点的路由文件”，还是已经把多个后端子系统写成了一个顺序敏感的巨型分发器。

实际看到：

- `apps/webui/api/routes.py` 约 10720 行。
- `rg "parsed\\.path"` 命中 189 处。
- `rg "if parsed\\.path"` 命中 178 处。
- `rg "^def _handle_|^def handle_|^def _serve_"` 命中 124 个 handler/helper 级函数。
- `handle_get()` 从 3180 行开始，直到 4232 行附近结束。
- `handle_post()` 从 4235 行开始，直到 5854 行附近结束。
- `handle_patch()` / `handle_delete()` 只做 CSRF 和 `read_body()`，然后直接 `False`，目前没有实际路由。

`handle_get()` 的主干不是 route table，而是一条长 `if` 链：

- `/session/static/` 和 `/session/` 在最前面处理前端 fallback。
- `/api/session` 是一个大型读取服务：
  - 解析 `messages`、`resolve_model`、`msg_limit`、`msg_before`。
  - 读取 WebUI session 或 CLI/messaging session。
  - 合并 messaging sidecar / CLI transcript。
  - 做消息分页。
  - 回填 effective model/provider/context length。
  - 附带 active stream / pending user message / run journal。
  - redaction 后响应。
- `/api/sessions` 是另一个大型列表服务：
  - 合并 WebUI sessions 和 CLI sessions。
  - 根据 settings 决定是否展示 CLI sessions。
  - profile scoping。
  - messaging session 去重。
  - CLI cap。
  - title redaction。
- 产品 GET route 分散在主链里：
  - `/api/products/<id>/preview...`
  - `/api/products`
  - `/api/products/<id>/versions`
  - `/api/products/<id>/status`
  - `/api/products/<id>/<asset>` catchall。
- 文件、媒体、approval SSE、clarify SSE、cron、skills、memory、MCP、rollback 都在同一条链上。

`handle_post()` 同样不是薄路由层：

- 先处理 `/api/csp-report`，然后 CSRF，再按需读 body。
- `/api/session/new` 内联做了：
  - trusted workspace resolution。
  - worktree session 创建。
  - model/provider 解析。
  - previous session memory commit。
  - session 创建。
  - toolsets 绑定。
  - product context 绑定。
  - product session record。
  - session save。
- session duplicate / rename / update / delete / clear / truncate / branch / pin / archive / move 都在同一个函数里。
- chat start/sync、terminal、crons、file ops、workspace management、product draft/create/update/delete/finalize/snapshot/rollback、approval/clarify、commands、skills、memory、profile/settings/onboarding/projects/import/update/auth/rollback 也都继续写在同一条 `if` 链里。
- 产品 POST 路由重复解析 product id：
  - create/update/delete/finalize 用 body 字段。
  - snapshot/rollback 从 URL slice 解析，缺失时再 fallback body。

安全相关好点：

- POST 有统一 CSRF 检查，`/api/csp-report` 明确豁免。
- `/api/file/raw` 用 `safe_resolve()` 限定 workspace / session attachment。
- `/api/media` 用 allowed roots，并且 SVG 强制 download。
- workspace HTML inline preview 已经通过 `Content-Security-Policy: sandbox allow-scripts` 做服务端隔离。
- `/static/` 有 `relative_to(static_root)` 防 traversal。

但产品 preview 仍是单独风险：

- GET route 使用 `parsed.path.startswith("/api/products/") and "/preview" in parsed.path`，匹配条件偏宽。
- `_serve_product_preview()` 又用 `rest.split("/preview", 1)` 解析。
- `_serve_file_response()` 只写 `Content-Type` / `Cache-Control` / `Content-Length`，没有 `_security_headers()`，也没有 CSP sandbox。
- 因此产品 HTML/SVG preview 和 `/api/file/raw?inline=1` 的安全语义不一致。

结构上的核心问题：

1. 路由顺序决定语义。
   - `/session/`、`/api/products/`、`/static/`、asset catchall 都是前后顺序敏感。
   - 新增 route 时需要读上下几百行确认不会被提前截获。

2. handler 层承担了领域服务。
   - `/api/session/new` 已经是 session creation service。
   - `/api/session` 已经是 session read/query service。
   - `/api/sessions` 已经是 sidebar aggregation service。
   - 产品管理只是调用了 `api.products`，但 route 层仍负责 URL/body id 解析、状态响应和异常映射。

3. 响应写法混杂。
   - 大多数 API 用 `j()` / `bad()`。
   - 文件、auth、SSE、static、export 手写 `send_response/send_header/wfile.write`。
   - 这让安全 header、cache header、CSP 行为难统一。

4. 测试保护偏字符串化。
   - 已有不少 tests 直接读 `routes.py` 源码查字符串或窗口。
   - 这会让拆路由时测试先碎掉，而不是行为回归先暴露。

5. `PATCH/DELETE` 壳子存在但没有 route。
   - 这说明 HTTP method 分发没有形成统一 route registry。
   - 未来如果继续添加 REST 风格接口，很容易继续把逻辑塞进 POST。

建议拆分边界：

1. 先建 route registry，不大改业务：
   - `api/http_routes.py` 或 `api/route_table.py`。
   - 每条 route 显式声明 method、path matcher、handler、csrf policy、body policy。
   - 先让现有 `handle_get/handle_post` 调 registry，旧链路作为 fallback。

2. 先迁移低耦合 GET helpers：
   - static / media / file raw / file read。
   - health / auth status / settings read。
   - product preview/status/list/version。

3. 再迁移 product routes：
   - `routes_products.py` 只做 HTTP adapter。
   - id parsing 统一为 `parse_product_route_id(path, suffix)`。
   - preview 统一通过安全 file response。

4. 再迁移 session routes：
   - `routes_sessions.py`。
   - `session_read_service.py`：`get_session_payload(query)`。
   - `session_list_service.py`：`list_sidebar_sessions(query, settings)`。
   - `session_mutation_service.py`：new/duplicate/update/delete/branch/archive/pin/move。

5. 再迁移 event routes：
   - `routes_streams.py`：chat stream / gateway stream / terminal output。
   - `routes_approval.py`：approval pending/respond/stream/inject。
   - `routes_clarify.py`：clarify pending/respond/stream/inject。

6. 最后迁移杂项后台能力：
   - cron。
   - skills。
   - memory。
   - MCP。
   - rollback/update/auth/onboarding。

短期最值得做的改动：

- 建一个 route manifest 测试，至少列出 method + path + handler 名。
- 给 `handle_get/handle_post` 加“新增 route 必须进入 registry”的注释和体量 guard。
- 修产品 preview response：对 HTML 加 CSP sandbox，对 SVG download 或 no-sniff，补 `_security_headers()`。
- 将 `/api/products/<id>/preview...` matcher 改成明确 segment matcher，避免 `"/preview" in path`。
- 把 `/api/session` 的 payload 组装抽成纯函数，先不拆文件也能让测试从源码字符串转成行为测试。

判断：

- `routes.py` 不是代码写法错误，而是典型的“长期追加导致边界消失”。
- 直接 TS 重写对这里没有意义，因为主要问题是 Python 后端路由层没有 registry 和 service boundary。
- 更合理的是先让 route table 可枚举、可测试，再按领域迁移 handler。

本轮验证：

- `.venv311/bin/python -m py_compile api/routes.py` 通过。
- `.venv311/bin/python -m pytest tests/test_issue1909_csp_report_only.py tests/test_subpath_frontend_routes.py tests/test_779_html_preview.py tests/test_approval_sse.py tests/test_sprint8.py tests/test_sprint28.py`：
  - 85 collected，84 passed，1 failed。
  - 通过项覆盖 CSP report、subpath frontend route、HTML preview、approval SSE、session sprint28 基础路由。
  - 失败项：`tests/test_sprint8.py::test_app_js_contains_clear_conversation` 仍期待 `/static/panels.js` 包含 `clearConversation` 字符串；这是静态源码断言漂移，不是本轮文档整理引入的语法或路由行为失败。

## 71. 第三十七轮：`i18n.js` locale bundle / 翻译资产治理

这轮目标是回答：最大的前端文件 `i18n.js` 是业务逻辑复杂，还是数据资产过大。

实际看到：

- `apps/webui/static/i18n.js`：11532 行，是当前最大的 JS 文件。
- 文件结构非常集中：
  - 1-11402：`LOCALES` 大对象。
  - 11403-11532：运行时 helper。
- 当前 locale：
  - `en`：7-1102，约 1096 行。
  - `it`：1103-2185，约 1083 行。
  - `ja`：2186-3273，约 1088 行。
  - `ru`：3274-4299，约 1026 行。
  - `es`：4300-5319，约 1020 行。
  - `de`：5320-6343，约 1024 行。
  - `zh`：6344-7362，约 1019 行。
  - `zh-Hant`：7363-8467，约 1105 行。
  - `pt`：8468-9383，约 916 行。
  - `ko`：9384-10456，约 1073 行。
  - `fr`：10457-11533，约 1077 行。

真正运行时代码：

- `_locale = LOCALES.en`。
- `resolveLocale(lang)`：
  - 支持 exact match。
  - 支持大小写无关。
  - 支持 `zh-CN/zh-SG/zh-Hans -> zh`。
  - 支持 `zh-TW/zh-HK/zh-MO/zh-Hant -> zh-Hant`。
  - 支持 base language fallback。
- `resolvePreferredLocale(primary, fallback)`：
  - server setting 优先。
  - localStorage fallback。
  - 默认 `en`。
- `t(key, ...args)`：
  - 当前 locale 缺 key 时 fallback 到 `LOCALES.en`。
  - 支持 function-valued translations。
  - 支持 `{0}`、`{1}` 这种编号占位符。
  - 最后 fallback 返回 key 本身。
- `setLocale(lang)`：
  - normalize。
  - 写 `localStorage.hermes-lang`。
  - 写 `document.documentElement.lang`。
- `applyLocaleToDOM()`：
  - 支持 `data-i18n`。
  - 支持 `data-i18n-title`。
  - 支持 `data-i18n-placeholder`。
  - 支持 `data-i18n-aria-label`。
  - 特别处理 `data-tooltip`，避免 native title 和 custom tooltip 同时出现。

判断：

- `i18n.js` 的代码逻辑本身不复杂。
- 一万多行主要来自翻译字典。
- 这个文件“长”不等于业务逻辑不可读，但它不适合继续作为单个手写 JS 文件维护。

字典完整性现状：

- `en` 有 1039 个非 metadata key。
- `en` 有 49 个 function-valued key。
- 各 locale 与 `en` 的 key 差异：
  - `it`：1032 keys，缺 7。
  - `ja`：1037 keys，缺 2。
  - `ru`：983 keys，缺 58，额外 2。
  - `es`：984 keys，缺 57，额外 2。
  - `de`：982 keys，缺 58，额外 1。
  - `zh`：983 keys，缺 57，额外 1。
  - `zh-Hant`：1011 keys，缺 30，额外 2。
  - `pt`：880 keys，缺 174，额外 15。
  - `ko`：1037 keys，缺 2。
  - `fr`：931 keys，缺 108。
- 函数型 key 类型不一致：
  - `de` 有 11 个英文为 function 但德语为 string 的 key。
  - `pt` 缺 14 个 function key，另有 1 个类型不一致。
  - `fr` 缺 39 个 function key。

最明显的问题：

1. `en` 不是纯英文基准。
   - `en` 中有 378 个 string value 含中日韩字符。
   - 示例：
     - `offline_title: '连接已断开'`
     - `voice_dictate: '语音输入'`
     - `approval_heading: '需要确认'`
     - `cmd_status: '查看任务信息'`
     - `session_rename_failed_no_row: '无法开始重命名，任务行不存在。'`
   - 这会让英文 fallback 失去“基准语言”的意义。

2. 缺 key 依赖 runtime fallback，而不是显式治理。
   - 当前 fallback 让 UI 不容易崩。
   - 但缺 key 长期存在会被掩盖。
   - 对非英文用户来说，缺 key 最终会回落到混有中文的 `en`。

3. function-valued translation 没有 schema。
   - 如果英文是 `(n) => ...`，其他语言写成 string，`t(key, arg)` 会直接返回 string，不做 function 调用。
   - 有时这只是少了动态数据，有时会导致文案不完整。

4. 测试方式不统一。
   - `test_language_precedence.py` 用 Node/vm 执行真实 i18n runtime，这个方向是好的。
   - `test_spanish_locale.py` 用 regex 截 `en` 到 `es`，但当前 locale 顺序是 `en/it/ja/ru/es`，所以它实际把意大利语、日语、俄语也算进英文 block。
   - 很多测试只查字符串出现次数，比如 “至少 6 个 locale 有 key”，不能证明每个 shipped locale 都有。
   - tooltip 测试还在找旧 `rail-btn` / `<nav class="rail">`，当前 DOM 已经是 `.nav-tab` / sidebar nav。

5. 翻译和产品术语改名交织在一起。
   - 当前工作区已有将 workspace 文案改成 `Files`、toolsets 改成 `Access` 的修改。
   - 这类产品语言变化若直接散落在 `index.html`、`i18n.js`、`ui.js`、测试里，会造成大量静态断言漂移。

建议拆分：

1. 不先重写 i18n runtime。
   - `resolveLocale`、`resolvePreferredLocale`、`t`、`applyLocaleToDOM` 可以先保留。
   - 这部分代码不大，行为也有测试。

2. 先把翻译资产拆出去。
   - `static/i18n/runtime.js`
   - `static/i18n/locales/en.js`
   - `static/i18n/locales/zh.js`
   - `static/i18n/locales/ko.js`
   - 其他 locale 同理。
   - 或者改为 JSON + runtime formatter，但 function-valued key 要先迁到 template 占位符。

3. 建 `i18n.schema.json` 或 `i18n-contract.js`。
   - key 名。
   - value kind：string/template/function。
   - required / optional。
   - default locale。
   - allowed placeholders。

4. 建 `scripts/audit-i18n.mjs`。
   - 读取所有 locale。
   - 输出 missing / extra / type mismatch / duplicate key。
   - 检查 `en` 中非英文字符。
   - 检查 placeholder 是否一致。
   - 检查 shipped locale 数和 metadata。

5. 把测试从源码字符串改成 audit。
   - Spanish/Korean 不再手写 regex。
   - 所有 locale coverage 统一从 `LOCALES` 动态读取。
   - 旧 DOM 类名测试改成实际导航结构测试。

短期最值得做：

- 修 `en` 基准语言，至少不要让 fallback 出中文。
- 给 `product_ui_title`、`session_rename_failed_no_row` 这类新增 key 补全所有 shipped locale，或明确 optional。
- 修 `test_spanish_locale.py` 的 locale block 提取逻辑。
- 修 `test_css_tooltips.py` 里旧 `.rail-btn` / `<nav class="rail">` 断言。
- 将产品术语改名整理成一份 `COPY_TERMS.md` 或 `PRODUCT_LANGUAGE.md`，统一 `Task / Session / Workspace / Files / Access` 的边界。

本轮验证：

- `node --check apps/webui/static/i18n.js` 通过。
- `.venv311/bin/python -m pytest tests/test_language_precedence.py tests/test_spanish_locale.py tests/test_korean_locale.py tests/test_pr1721_rtl_salvage.py tests/test_css_tooltips.py`：
  - 46 collected，39 passed，7 failed。
  - `test_language_precedence.py` 4 个全部通过。
  - `test_pr1721_rtl_salvage.py` 9 个全部通过。
  - 失败项集中在：
    - Spanish 旧代表翻译和 coverage。
    - Korean 旧代表翻译和 coverage。
    - Tooltip 测试仍查旧 rail DOM。
  - 这些失败说明当前 i18n 资产和测试预期已漂移，不是 runtime 语法错误。

## 72. 第三十八轮：`streaming.py` Agent stream lifecycle / 产品 turn 终态

文件概况：

- `apps/webui/api/streaming.py`：5534 行。
- 顶层函数约 80 个。
- 最大主函数是 `_run_agent_streaming()`，从 2765 行到 5122 行，约 2350 行。
- 第二个大函数是 `cancel_stream()`，从 5225 行到 5534 行，约 310 行。

这个文件是后端真正的“会话执行核心”：

- 创建并管理 SSE stream。
- 创建/复用 AIAgent。
- 注入 profile/workspace/session 环境变量。
- 注册 token/reasoning/tool/approval/clarify callbacks。
- 拼 workspace context、product ephemeral prompt、personality prompt。
- 调用 `agent.run_conversation()`。
- 合并 agent result 到 `session.messages` 和 `session.context_messages`。
- 写 run journal / turn journal。
- 更新 usage、metering、gateway routing、context length。
- 处理 context compression 后的 session id 迁移。
- 处理 pending user message、checkpoint、last-resort sync。
- 处理 provider error、silent failure、credential self-heal。
- 处理产品生成成功/失败 finalize。
- 处理 `/steer` 和 cancel。

产品相关链路：

- `_run_agent_streaming(..., product_context=None)` 接收 `routes.py` 传来的产品上下文。
- `_webui_ephemeral_system_prompt(personality_prompt, product_prompt)` 把 personality prompt 和 product prompt 拼进 agent ephemeral system prompt。
- 成功路径：
  - `agent.ephemeral_system_prompt = _webui_ephemeral_system_prompt(...)`。
  - 运行 agent。
  - 合并 session。
  - 写 usage / journal。
  - 调 `_finalize_product_turn(failed=False)`。
  - 发 `done`。
- 失败路径：
  - silent failure 路径会 `_finalize_product_turn(failed=True, error_type=..., error_message=...)`。
  - exception 路径会 `_finalize_product_turn(failed=True, ...)`。
  - cancel 路径会 `_put_cancel()`，里面调用 `_finalize_product_turn(failed=True)`。
  - 外层 `finally` 还有 `_finalize_product_turn(failed=True)` 兜底。
- `_finalize_product_turn()` 用 `product_turn_finalized` guard 防重复。
- 只有 `product_context.scope in {"product_init", "product_builder"}` 才会调用 `api.products.finalize_product_generation()`。

这块逻辑本身是合理的：

- 成功路径确实在 `done` 前 finalize success。
- 兜底 failure 不会覆盖成功，因为 guard 已设置。
- finalize 失败不会立刻吞掉状态，而是 warning；并且产品 resolver 侧还有 timeout healing。

但维护风险很高：

1. 产品 turn 终态是一个 nested closure。
   - 它依赖 `_run_agent_streaming()` 的多处分支都记得调用。
   - 现在靠 guard 和 finally 兜住。
   - 逻辑对，但很难一眼证明。
   - 未来若新增 `internal_context`、产品子任务、后台产品生成，就会继续把状态塞进主函数。

2. `_run_agent_streaming()` 同时负责太多层。
   - request/session 状态。
   - agent runtime build/cache。
   - callbacks。
   - prompt/context。
   - persistence。
   - SSE protocol。
   - errors/self-heal。
   - product lifecycle。
   - title/background title。
   - goal continuation。
   - compression migration。
   - cleanup。
   - 这些都在一个函数里，局部修改非常容易影响远处 finally/error path。

3. error/self-heal 有重复结构。
   - silent failure 路径和 exception 路径都有 credential self-heal。
   - retry 成功后的 session merge/save 逻辑也有重复。
   - error persistence、journal interrupted、product finalize、apperror event 分散。

4. cancel 与 worker 共享很多隐式全局状态。
   - `STREAMS`
   - `CANCEL_FLAGS`
   - `AGENT_INSTANCES`
   - `STREAM_PARTIAL_TEXT`
   - `STREAM_REASONING_TEXT`
   - `STREAM_LIVE_TOOL_CALLS`
   - `STREAM_LAST_EVENT_ID`
   - `SESSION_AGENT_LOCKS`
   - `SESSION_AGENT_CACHE`
   - `session.active_stream_id`
   - `session.pending_user_message`
   - `session.pending_attachments`
   - `session.pending_started_at`
   - 现在有很多注释说明 lock 顺序，说明之前确实踩过 race。
   - 注释很有价值，但状态边界没有被类型或对象封装。

5. `put(event, data)` 同时做两件事。
   - 写 run journal。
   - 写 SSE queue。
   - 还通过 `STREAM_LAST_EVENT_ID` side-channel 传 event id。
   - 这个设计兼容了旧 queue tuple shape，但也让 SSE 事件、journal、replay 游标耦合。

6. prompt/context 拼装位置偏晚且耦合。
   - product prompt、personality prompt、workspace context 都在主函数里处理。
   - 当前没有 `internal_context` 参数。
   - 前面已经发现前端 hidden instruction 会污染 visible `msgText`，如果直接在这里加更多参数，会继续加剧主函数复杂度。

7. `cancel_stream()` 是另一个小型控制器。
   - 它先在 `STREAMS_LOCK` 中设 cancel flag / interrupt agent / pop stream state。
   - 再在 session lock 中恢复 pending user、保存 partial assistant、reasoning、tool calls、cancel marker。
   - 这个顺序合理，注释也清楚。
   - 但函数需要知道太多 session/message 内部结构。

好的地方：

- `pending_user_message` 机制很重要，能避免断流/错误/取消丢用户输入。
- periodic checkpoint 和 `_last_resort_sync_from_core()` 是很强的数据保护。
- `_stream_writeback_is_current()` 能避免旧 stream 覆盖新 stream。
- cancel 保存 partial text、reasoning 和 live tool calls，数据保真度不错。
- context compression 会保留 pre-compression snapshot，并迁移 session lock/cache。
- title sanitization 比较稳，有 aux/agent fallback。
- run journal 和 turn journal 有助于断线重连和事件审计。
- `MCP discovery` 放在 profile env mutation 后，这个修复方向是正确的。
- 测试覆盖了不少历史 race：cancel interrupt、stream persistence、profile cache、compression card、context length fallback、cache usage、title sanitization。

最应该拆的边界：

1. `stream_turn.py`
   - 定义 `StreamTurnContext`。
   - 包含 `session_id`、`stream_id`、`original_session_id`、`ephemeral`、`workspace`、`model`、`provider`、`cancel_event`、`agent_lock`、`product_context`。
   - 集中管理 active run phase 和 cleanup。

2. `stream_product_turn.py`
   - 抽出产品 turn finalizer。
   - API 类似：
     - `finalizer = ProductTurnFinalizer(product_context)`
     - `finalizer.success()`
     - `finalizer.fail(error_type, error_message)`
     - `finalizer.cancel()`
     - `finalizer.finally_fail_if_unfinished()`
   - 目标是让成功/失败/取消/finally 的幂等性可以单测。

3. `stream_callbacks.py`
   - token/reasoning/interim/tool callbacks。
   - live metering。
   - partial/reasoning/tool-call shared state mirror。
   - checkpoint activity bump。

4. `stream_agent_runtime.py`
   - model/provider/base_url/api key resolve。
   - AIAgent kwargs build。
   - SESSION_AGENT_CACHE signature。
   - cached agent refresh。
   - MCP discovery env timing。

5. `stream_persistence.py`
   - pending user materialize。
   - result merge。
   - reasoning metadata restore。
   - error message persistence。
   - cancelled turn persistence。
   - last-resort sync。

6. `stream_errors.py`
   - provider error classify/payload。
   - silent failure detection。
   - credential self-heal。
   - retry run result merge。
   - `apperror` event emission。

7. `stream_compression.py`
   - pre-compression snapshot。
   - session id rotation。
   - session lock/cache migration。
   - compressed SSE payload。

8. `stream_titles.py`
   - generated title sanitization。
   - aux title generation。
   - background title update/refresh。

9. `stream_cancel.py`
   - `cancel_stream()` 的 session cleanup 和 partial preservation。
   - 保留现有 lock order，但把 message recovery 单测化。

10. `stream_steer.py`
   - `_handle_chat_steer()`。
   - 产品 prompt 前缀逻辑。
   - 与前端 `_trySteer()` 的 response contract。

短期不建议：

- 不建议把 `streaming.py` 直接 TS 重写。
- 这是 Python 后端 Agent 执行层，问题不是语言，而是 lifecycle 边界。
- TS 更适合先保护前端产品模型、bridge SDK、queue/request contract。

本轮验证：

- `.venv311/bin/python -m py_compile api/streaming.py` 通过。
- `.venv311/bin/python -m pytest tests/test_cancel_interrupt.py tests/test_issue765_streaming_persistence.py tests/test_issue1897_profile_switch_agent_cache.py tests/test_auto_compression_card.py tests/test_issue1896_context_length_fallback_args.py tests/test_issue2419_cache_usage_display.py tests/test_real_steer.py tests/test_title_sanitization.py`：
  - 102 collected，100 passed，2 failed。
  - 失败集中在 `tests/test_real_steer.py`：
    - `test_accepts_when_agent_cached_and_running` 严格比较整包响应，但后端现在额外返回 `product_scope: None`。
    - `test_try_steer_handles_fallback` 只截 `_trySteer()` 开头 1500 字符，`cancelStream` 实际在函数后半段存在。
  - 这两个失败更像测试契约/静态窗口没有跟上现代码，不是 `streaming.py` 当前语法或核心 lifecycle 失败。

## 73. 第三十九轮：Session model / sidebar / command contract

本轮看的文件：

- `apps/webui/api/models.py`
- `apps/webui/api/session_ops.py`
- `apps/webui/api/routes.py` 中 `/api/session`、`/api/session/draft`、`/api/session/retry`、`/api/session/undo`
- `apps/webui/static/sessions.js`
- `apps/webui/static/commands.js`

体量：

- `models.py`：2477 行。
- `sessions.js`：3848 行。
- `commands.js`：1407 行。
- `session_ops.py`：195 行。

后端 session 存储逻辑：

- `Session` 是 WebUI 自己的 sidecar JSON 模型。
- `Session.save()`：
  - metadata 字段排在 JSON 前面，方便 metadata-only 读取。
  - atomic tmp + `os.replace()` 写主文件。
  - 若 incoming message count 比已有文件少，会先写 `.json.bak`。
  - metadata-only session 被强制禁止保存，避免 `messages=[]` 覆盖完整历史。
  - 保存后更新 `_index.json`。
- `Session.load_metadata_only()`：
  - 只读到顶层 `messages` 字段前。
  - 设置 `_loaded_metadata_only=True`。
  - `_metadata_message_count` 从 index 回填。
- `_write_session_index()`：
  - 支持 full rebuild。
  - 支持单 session fast update。
  - 用 `_INDEX_WRITE_LOCK` 序列化 index 写。
  - disk I/O 不持全局 `LOCK`。
- `get_session(sid, metadata_only=False)`：
  - metadata-only 不进 full-session LRU cache。
  - full load 进 `SESSIONS` LRU。
  - full load 后尝试 `_repair_stale_pending()`。
- `new_session()`：
  - 默认只进内存，不立刻落盘。
  - 避免空 Untitled session 污染 sidebar。
  - worktree session 例外，会立即保存。

stale pending / crash recovery：

- `_repair_stale_pending()` 只在这些条件下触发：
  - `pending_user_message` 存在。
  - `active_stream_id` 存在。
  - stream 已不在 `STREAMS`。
  - pending age 超过 30 秒 grace。
- 修复时使用 per-session agent lock，且 non-blocking acquire，避免 retry/undo/cancel 已持锁时死锁。
- `_apply_core_sync_or_error_marker()` 会根据状态选择：
  - 已有 messages：追加 recovered pending user，恢复 run journal 可见输出，再加 interrupted marker。
  - messages 为空且 core transcript 存在：同步 core transcript，必要时恢复 run journal 可见输出。
  - core 缺失：恢复 pending user + interrupted marker。
- `_append_journaled_partial_output()` 会从 run journal 恢复：
  - token。
  - interim assistant。
  - tool。
  - tool_complete。
- 它不会恢复 hidden reasoning，这个选择是保守的。

这块后端设计总体较好：

- 数据保护意识强。
- 关键写入路径有 atomic write。
- shrink backup 是非常实用的防灾设计。
- metadata-only save guard 是 P0 级别正确保护。
- stale pending 修复考虑了 race、lock order、grace window。
- session index 避免每次 sidebar 都扫全量文件。
- `session_ops.py` 把 retry/undo/status/usage 从 routes 拿出来了，是后续拆分的好样板。

主要维护问题：

1. `models.py` 职责过宽。
   - Session JSON model。
   - index 写入。
   - stale pending repair。
   - run journal partial recovery。
   - sidebar row filtering。
   - compression lineage sidebar metadata。
   - projects load/save。
   - cron project。
   - CLI session import/cache。
   - Claude Code JSONL import。
   - 这些混在一个文件，导致“session model”概念变得过大。

2. session 字段没有显式 schema。
   - product 字段、worktree 字段、CLI/messaging source 字段、compression 字段、runtime pending 字段都在 `Session.__init__` 参数里。
   - `compact()` 是事实上的 wire schema。
   - 前端直接依赖 `compact()` 的许多字段。
   - 新字段容易只加后端或只加前端，缺少 contract 检查。

3. `/api/session` handler 仍在 `routes.py` 里承担过多职责。
   - metadata/full/tail message loading。
   - CLI fallback。
   - messaging session merge。
   - effective model/provider display resolve。
   - context length fallback。
   - runtime journal payload。
   - redaction。
   - slow diagnostics。
   - 这应该拆成 `session_read_service.py` + route wrapper。

4. draft 保存路径局部合理但仍在 route monolith。
   - 有 50KB text cap 和 50 files cap。
   - 持 per-session agent lock。
   - 但 draft 是 session mutation，应进入 session mutation service。

前端 session 逻辑：

- `sessions.js` 顶部有 composer draft 保存/恢复。
- `newSession()`：
  - 组 new session request。
  - 合并产品默认 workspace/toolsets。
  - 写 URL/localStorage。
  - 重置 busy/active stream。
  - 同步 topbar/messages/workspace。
- `loadSession()` 是核心状态机：
  1. 保存当前 composer draft。
  2. 写 `_loadingSessionId` 防 stale response。
  3. 先 `messages=0` 拉 metadata。
  4. 同步 active session / URL / topbar。
  5. 若 server 已 idle，清本地 `INFLIGHT`。
  6. streaming session：先恢复 persisted transcript，再 merge local inflight tail。
  7. idle session：lazy load tail messages。
  8. 恢复 sessionStorage queue。
  9. merge pending user message。
  10. 恢复 approval/clarify/yolo polling。
  11. 恢复 composer draft。
  12. handoff hint。
- `_ensureMessagesLoaded()`：
  - 默认只取最后 30 条。
  - 设置 `_messagesTruncated` 和 `_oldestIdx`。
  - 若 message 内已有 tool metadata，就不发送 session-level `tool_calls`。
- `_loadOlderMessages()`：
  - 用 `_messagesGeneration` 防 stale prepend。
  - 保留 scroll position。
- `renderSessionList()` / `renderSessionListFromCache()`：
  - server fetch。
  - optimistic first-turn merge。
  - profile/project/archive/search/filter。
  - compression lineage collapse。
  - child session attach。
  - virtualization。
  - DOM render。
  - gateway SSE / fallback polling。

前端好的地方：

- `_loadingSessionId` 防快速切 session 的 stale response，方向正确。
- `INFLIGHT` 作为 live tail，而不是完整 transcript，避免切回长会话丢历史。
- `_mergeInflightTailMessages()` 只合并 live tail 附近，避免重复整段。
- lazy tail loading + older paging 对长会话性能有帮助。
- `_messagesGeneration` 解决了 older prefetch 和 full load 的竞态。
- sidebar 有 pointer/scroll interaction defer，避免刷新打断用户操作。
- session list virtualization 有独立窗口计算，测试也覆盖。

前端主要问题：

1. `loadSession()` 太大，且是多职责状态机。
   - 会话切换。
   - draft。
   - inflight restore。
   - message paging。
   - product assistant sync。
   - prompt polling。
   - workspace dir load。
   - UI empty/loading 文案。
   - 这些应该拆成阶段函数。

2. `sessions.js` 文件名已经不准确。
   - 它包含 sidebar store/view、message pager、handoff、gateway sync、project CRUD、batch selection、virtual list。
   - 这不是一个“session module”，而是半个 app shell。

3. queue restore 与 queue send contract 仍然不稳。
   - `loadSession()` 会从 `sessionStorage['hermes-queue-'+sid]` 恢复 queued message 到 composer。
   - 只展示 first message。
   - 前面已经发现 queue path 会把 payload 再灌回 composer/global state 再调用 `send()`。
   - 对 product context、internal context、attachments 的语义仍需统一。

4. `commands.js` 里 request 组包分散。
   - `/queue`
   - `/interrupt`
   - `/steer`
   - `/retry`
   - `/undo`
   - `/btw`
   - `/background`
   - 普通 `send()`
   - 多条路径各自拼 payload。
   - `withCurrentProductContext()` 是补丁式桥接，不是统一 request builder。

5. 静态测试仍有固定窗口问题。
   - 前面 `test_real_steer.py` 的 `_trySteer` 只截 1500 字符就是例子。
   - session 这组测试整体更好，137 个全过，但后续重构还是应优先行为测试/vm 测试。

建议拆分：

后端：

1. `api/session_model.py`
   - `Session`。
   - load/save/metadata-only。
   - JSON schema defaults。

2. `api/session_index.py`
   - `_write_session_index()`。
   - `_cleanup_stale_tmp_files()`。
   - `all_sessions()` 的 index read 部分。

3. `api/session_repair.py`
   - stale pending repair。
   - run journal partial output recovery。
   - interrupted marker。

4. `api/session_sidebar.py`
   - compact/list row filtering。
   - compression snapshot preference。
   - lineage metadata enrichment。

5. `api/session_read.py`
   - `/api/session` handler 的核心 query service。
   - metadata/full/tail paging。
   - CLI fallback。
   - context length fallback。
   - runtime journal payload。

6. `api/session_mutations.py`
   - draft。
   - update。
   - branch。
   - retry/undo 可保留在 `session_ops.py` 或并入 mutation service。

前端：

1. `session-drafts.js`
   - `_saveComposerDraft`
   - `_saveComposerDraftNow`
   - `_restoreComposerDraft`
   - `_clearComposerDraft`

2. `session-loader.js`
   - `newSession`
   - `loadSession`
   - 拆成：
     - `loadSessionMetadata`
     - `loadSessionMessages`
     - `restoreStreamingSession`
     - `restoreIdleSession`
     - `finalizeSessionLoad`

3. `message-pager.js`
   - `_ensureMessagesLoaded`
   - `_loadOlderMessages`
   - `_ensureAllMessagesLoaded`
   - `_mergeInflightTailMessages`

4. `session-sidebar-store.js`
   - `_allSessions`
   - render fetch。
   - optimistic first-turn merge。
   - unread/observed streaming。
   - profile/project/archive/search filter state。

5. `session-sidebar-view.js`
   - DOM render。
   - virtualization。
   - action menus。
   - project chips。
   - batch selection。

6. `session-lineage-view.js`
   - compression lineage collapse。
   - child session attach。
   - lineage report cache。

7. `session-gateway-sync.js`
   - gateway SSE。
   - fallback polling。
   - CLI import refresh。

8. `command-request-builder.js`
   - 给 `send()`、`/queue`、`/interrupt`、`/steer`、`/retry` 后续发送统一 payload builder。
   - 输出统一 `TurnRequest`：
     - `text`
     - `files`
     - `model`
     - `model_provider`
     - `profile`
     - `product_id`
     - `product_scope`
     - `product_intent`
     - `internal_context`
   - 这是后续 TS 化最适合的入口之一。

本轮验证：

- `node --check static/sessions.js` 通过。
- `node --check static/commands.js` 通过。
- `.venv311/bin/python -m py_compile api/models.py api/session_ops.py` 通过。
- `.venv311/bin/python -m pytest tests/test_session_ops.py tests/test_session_tail_payload.py tests/test_session_metadata_fast_path.py tests/test_session_sidecar_repair.py tests/test_stage326_composer_draft_validation.py tests/test_empty_session_no_disk_write.py tests/test_issue2157_sessions_list_stale_stream_state.py tests/test_issue2066_stale_sidebar_spinner.py tests/test_issue500_session_list_virtualization.py tests/test_issue1144_session_time_sync.py tests/test_parallel_session_switch.py`：
  - 137 collected，137 passed。
  - 说明 session 这条线当前行为护栏较稳，重构策略应是保留语义逐步拆模块，而不是重写。

## 74. 第四十轮：Model / provider / settings 配置链路

本轮看的主链路：

- `apps/webui/api/config.py`
- `apps/webui/api/providers.py`
- `apps/webui/static/panels.js`
- 辅助对照：
  - `apps/webui/static/boot.js`
  - `apps/webui/api/profiles.py`
  - model/provider/settings 相关测试。

文件体量：

- `config.py`：4402 行。
- `providers.py`：2146 行。
- `panels.js`：2093 行。
- `boot.js`：1703 行。
- `profiles.py`：1364 行。

结论先说：

1. 这条链路的业务语义是清楚的。
   - 用户配置默认 provider/default model。
   - Provider key/OAuth/custom provider 决定哪些 provider 可用。
   - `/api/models` 构建 picker groups。
   - 前端 settings panel 选择 default model、保存 settings、管理 provider key、刷新 model cache。
   - streaming/chat start 再通过 `resolve_model_provider()` 把 UI model id 解析成 runtime model/provider/base_url。

2. 代码的主要问题不是“写错”，而是中心函数过载。
   - `config.py` 名义上是 config，实际包含 path discovery、YAML cache、model catalog、provider resolver、models cache、settings store、stream runtime globals。
   - `get_available_models()` 是模型选择器的核心，但一口气处理 config/auth/custom endpoint/live catalog/fallback/static catalog/cache/credential pool/provider group。
   - `resolve_model_provider()` 规则很强，但已像一个手写 parser，所有 provider 特例都堆在一个函数里。
   - `panels.js` 名义上是 panel 管理，实际包含 settings dirty state、appearance autosave、preferences autosave、providers UI、quota card、plugins、MCP、gateway、checkpoints。

3. 不建议直接 TS 重写。
   - TS 适合先落在 contract 和纯逻辑：
     - `ModelProviderContract`
     - `TurnRequest`
     - product bridge protocol
     - settings payload schema
   - 如果直接把这些巨型函数翻译成 TS，只会得到“带类型的巨石”。

`config.py` 读到的职责：

1. 路径与运行目录。
   - `HOME`
   - `STATE_DIR`
   - profile-aware config path。

2. YAML config cache/reload。
   - `get_config()`
   - `reload_config()`
   - `_cfg_has_in_memory_overrides()`。
   - 当前代码会尊重测试/运行时 monkeypatch，不会轻易用磁盘覆盖内存。

3. Provider identity 和静态 catalog。
   - `_PROVIDER_DISPLAY`
   - `_PROVIDER_MODELS`
   - alias/canonical provider helper。
   - custom provider slug helper。

4. Runtime model resolver。
   - `resolve_model_provider()`。
   - `resolve_custom_provider_connection()`。
   - `model_with_provider_context()`。

5. `/api/models` cache 和 response builder。
   - `_MODELS_CACHE_SCHEMA_VERSION`
   - `_models_cache_source_fingerprint()`
   - `_load_models_cache_from_disk()`
   - `_save_models_cache_to_disk()`
   - `invalidate_models_cache()`
   - `get_available_models()`。

6. Stream/global runtime state。
   - `StreamChannel`
   - stream maps。
   - active run registry。
   - agent cache/session locks/thread env。

7. Settings store。
   - `_SETTINGS_DEFAULTS`
   - `load_settings()`
   - `save_settings()`。

`resolve_model_provider()` 的正面价值：

- 支持裸 model、`provider/model`、`@provider:model`。
- 支持 `custom:<name>` 这种 provider hint。
- 处理 OpenRouter `:free` 等 suffix。
- 处理 custom provider name/base_url。
- 处理 local server provider：
  - LM Studio
  - Ollama
  - llama.cpp
  - vLLM
  - TabbyAPI
- 处理 portal providers：
  - Nous
  - OpenCode
  - NVIDIA NIM。
- 处理 OpenAI Codex endpoint 的窄例外。
- 处理 provider prefix stripping 与 full model id preservation。

`resolve_model_provider()` 的结构风险：

- provider id parser、custom provider lookup、base_url policy、OpenRouter routing、local-server policy 都在同一个函数。
- 新 provider 加一条规则时，很难一眼判断会不会改变已有 provider 的 precedence。
- 这个函数已经需要大量 issue 注释才能解释行为，说明它应该变成“规则表 + fixture 测试”，而不是继续扩 if/elif。

`get_available_models()` 的正面价值：

- 有 memory TTL cache。
- 有 disk cache schema version。
- 有 WebUI version stamp。
- 有 config/auth/catalog source fingerprint。
- 有 single-flight lock，避免多个请求同时 rebuild。
- 会在 provider key 变动后 invalidation。
- 会优先读 live provider catalog，再 fallback 到静态 catalog。
- 对 custom endpoint 有 SSRF guard 相关测试。
- Provider group 会带 `provider_id`，支持同名 model 出现在多个 provider。

`get_available_models()` 的结构风险：

- 函数本体仍太大，且内部 helper 闭包依赖外层 `active_provider/groups`。
- 它同时负责：
  - active provider 解析。
  - default model 解析。
  - auth store 读取。
  - credential pool 检查。
  - live catalog 读取。
  - custom endpoint 拉取。
  - group 去重。
  - configured model badge。
  - cache load/save。
- 这些职责互相耦合后，任何小修都会带来大范围回归测试压力。

`providers.py` 读到的职责：

1. Provider 列表和状态。
   - `get_providers()`。
   - `has_key`
   - `key_source`
   - `is_oauth`
   - models/models_total。

2. Provider key 管理。
   - `_load_env_file()`
   - `_write_env_file()`
   - `set_provider_key()`
   - `remove_provider_key()`
   - `_clean_provider_key_from_config()`。

3. OAuth/provider key 判断。
   - 避免把 Codex OAuth JWT 当 OpenAI API key。
   - 支持 env aliases。
   - 支持 config.yaml provider key。

4. Provider quota/account usage。
   - quota 状态缓存。
   - subprocess probe。
   - cost history。

`providers.py` 的正面价值：

- `.env` 写入会尽量保留 comments/order。
- key 写入后会 `invalidate_models_cache()`。
- remove key 也会清理 config.yaml 中可能残留的 key。
- account usage probe 有并发限制和 timeout。
- OAuth provider 不会走普通 key 保存路径。

`providers.py` 的结构风险：

- 它从 `api.config` 导入很多私有/半私有符号，owner 边界不清。
- `get_providers()` 与 `get_available_models()` 都在做 live/static model catalog merge，picker 与 provider card 需要一致，但一致性靠复制逻辑维持。
- `_write_env_file()` 依赖 `api.streaming._ENV_LOCK`，provider credential 写入和 streaming 实现产生反向耦合。
- quota/account usage/cost history 不应该放在 provider credential module 里。

`panels.js` 读到的职责：

- settings section switch。
- settings dirty/unsaved bar。
- appearance autosave。
- preferences autosave。
- `loadSettingsPanel()`。
- providers panel：
  - provider quota card。
  - provider card。
  - key save/remove。
  - model refresh。
- plugins/system/MCP/gateway/checkpoint。
- auth sign out/disable。

`panels.js` 的正面价值：

- Appearance/preference 已经支持 autosave。
- password/default model 这种显式保存字段不会被 autosave 误清 dirty state。
- provider key 保存/删除后会刷新 JS 侧 model dropdown cache。
- provider quota card 对大 catalog 做了 featured/total count 区分。

`panels.js` 的结构风险：

- settings payload 在 `_preferencesPayloadFromUi()`、`_appearancePayloadFromUi()`、`saveSettings()` 里重复组装。
- provider card UI 里仍有硬编码英文：
  - `Show`
  - `Hide`
  - `Models`
  - `+N more`
  - `Failed to update default model — settings saved`
- 多处 `innerHTML` 与 DOM builder 混用，虽然多数使用 `esc()`，但长期维护风险仍比组件化 builder 高。
- `panels.js` 末尾仍引用 `loadCrons()`，但当前 `static/` 下没有搜到 `loadCrons()` 定义；相关测试也仍在寻找旧的 master-detail 清理逻辑。这说明旧面板迁移/删除没有完全收口。

建议拆分：

后端：

1. `api/config_paths.py`
   - HOME/state/config/auth path discovery。

2. `api/config_store.py`
   - YAML load/reload/save。
   - mtime/in-memory override policy。

3. `api/provider_identity.py`
   - provider aliases。
   - display names。
   - custom provider slug。
   - base_url -> provider classification。

4. `api/model_catalog.py`
   - static `_PROVIDER_MODELS`。
   - live catalog adapter。
   - Codex local cache merge。
   - featured set。

5. `api/model_resolver.py`
   - `resolve_model_provider()`。
   - `model_with_provider_context()`。
   - table-driven rule chain。

6. `api/model_cache.py`
   - `/api/models` memory/disk cache。
   - schema/version/source fingerprint。
   - invalidation。

7. `api/provider_credentials.py`
   - env/config/OAuth key detection。
   - key save/remove。
   - `.env` writer。

8. `api/provider_usage.py`
   - quota/account usage probe。
   - subprocess isolation。
   - account status cache。

9. `api/settings_store.py`
   - `_SETTINGS_DEFAULTS`
   - `load_settings()`
   - `save_settings()`
   - default model mutation contract。

10. `api/runtime_state.py`
   - stream maps。
   - active run registry。
   - agent cache/session locks。
   - 后续也可以并入 streaming lifecycle 拆分。

前端：

1. `settings-state.js`
   - dirty state。
   - pending target。
   - settings open baseline。

2. `settings-payload.js`
   - appearance payload。
   - preferences payload。
   - manual save payload。
   - password/default model explicit mutation。

3. `settings-autosave.js`
   - appearance autosave。
   - preferences autosave。
   - retry/status UI。

4. `settings-panel.js`
   - `loadSettingsPanel()`。
   - section hydration。
   - save/discard close flow。

5. `provider-panel.js`
   - `loadProvidersPanel()`。
   - key save/remove。
   - model refresh。

6. `provider-card.js`
   - provider card DOM builder。
   - no hardcoded English。

7. `provider-quota-view.js`
   - quota status card。
   - quota formatting。
   - refresh action。

8. `system-panel.js`
   - MCP servers/tools。
   - gateway status。

9. `checkpoint-panel.js`
   - checkpoint list/diff/restore。

本轮验证：

- `node --check static/panels.js static/boot.js` 通过。
- `.venv311/bin/python -m py_compile api/config.py api/providers.py api/profiles.py` 通过。
- `.venv311/bin/python -m pytest tests/test_model_resolver.py tests/test_resolve_model_provider_free_suffix.py tests/test_issue1855_resolve_model_provider_fast_path.py tests/test_issue1806_named_custom_provider_resolution.py tests/test_pr1947_same_model_multiple_custom_providers.py tests/test_issue1106_custom_providers_models.py tests/test_issue1105_ssrf_custom_providers.py tests/test_issue1699_model_cache_source_fingerprint.py tests/test_model_cache_metadata.py tests/test_issue1633_models_cache_version_stamp.py tests/test_live_models_ttl_cache.py tests/test_provider_management.py tests/test_provider_quota_status.py tests/test_provider_cost_history.py tests/test_custom_providers_in_panel.py tests/test_quota_chip_settings_toggle.py tests/test_1059_settings_picker_active_state.py tests/test_settings_navigation_and_detail_refresh.py tests/test_issue2399_provider_config_flags.py tests/test_issue1568_duplicate_provider_groups.py tests/test_issue2245_mixed_case_provider_models.py tests/test_issue1765_codex_quota.py tests/test_credential_pool_providers.py`：
  - 270 collected。
  - 265 passed。
  - 5 failed，全部集中在 `test_settings_navigation_and_detail_refresh.py`：
    - `loadCrons()` empty-state detail clear。
    - `loadCrons()` selected job disappear clear。
    - `renderWorkspacesPanel()` selected workspace disappear clear。
    - `loadProfilesPanel()` empty-state detail clear。
    - `loadProfilesPanel()` selected profile disappear clear。
  - 当前 `static/` 下没有这些函数定义，`panels.js` 仍有 `loadCrons()` 调用；这更像旧面板代码迁移未收口/静态测试未更新，而不是 model/provider 主链路失败。

## 75. 第四十一轮：boot / profile / workspace / update / onboarding 链路

本轮看的主链路：

- `apps/webui/static/boot.js`
- `apps/webui/static/workspace.js`
- `apps/webui/static/ui.js` profile/update/topbar 相关区段
- `apps/webui/api/profiles.py`
- `apps/webui/api/workspace.py`
- `apps/webui/api/updates.py`
- `apps/webui/api/onboarding.py`
- `apps/webui/api/routes.py` 中 profile/workspace/update/onboarding endpoint glue。

文件体量：

- `boot.js`：1703 行。
- `workspace.js`：约 375 行。
- `profiles.py`：1364 行。
- `workspace.py`：810 行。
- `updates.py`：961 行。
- `onboarding.py`：1046 行。

产品逻辑概览：

1. 启动：
   - `boot.js` 先取 `/api/settings`。
   - 应用语言、主题、皮肤、字体、模型默认值、quota/update/voice 等偏好。
   - 再取 `/api/profile/active`。
   - 并行/异步取 model dropdown。
   - 加载 workspace list。
   - 跑 onboarding wizard。
   - render session list。
   - 恢复 URL/localStorage session。
   - 检查 inflight stream。
   - 启动 gateway SSE。

2. Profile：
   - WebUI profile 不只是 UI 概念，它影响 `HERMES_HOME`、config、skills、memory、cron、API key、terminal env。
   - 后端同时支持：
     - process-wide active profile。
     - cookie/thread-local per-request profile。
     - background worker 临时 profile env。
     - cron profile context。

3. Workspace：
   - workspace list/last workspace 是 per-profile 的。
   - 后端读写文件前用 trusted workspace root + traversal/symlink/system-path guard。
   - 前端 workspace panel 负责 tree、preview、edit、download、media/pdf/html iframe。

4. Updates：
   - 后端检测 webui/agent git repo。
   - 更新前拒绝 active streams。
   - `_apply_lock` 防并发更新。
   - update 后 schedule restart / re-exec。
   - summary 支持 fallback 和 LLM callback。

5. Onboarding：
   - 状态接口把 settings/config/imports/provider readiness/workspace/models 打包给前端。
   - setup 会写 config.yaml 和 `.env`。
   - 已有 config.yaml 时默认拒绝覆盖，必须 confirm。
   - `HERMES_WEBUI_SKIP_ONBOARDING` 是 operator hard override。

正面评价：

1. `profiles.py` 对 profile 的复杂性认识很清楚。
   - 注释解释了为什么需要 patch imported skill/cron modules。
   - 有 per-request TLS，避免不同浏览器 tab/profile 完全依赖 process global。
   - `process_wide=False` 允许用户在一个 profile 有 stream 时切到另一个 profile。
   - `profile_env_for_background_worker()` 说明后台线程也考虑了 profile env 泄漏。

2. `workspace.py` 安全边界比一般文件浏览器更认真。
   - per-profile workspace state。
   - workspace list 清理跨 profile 泄漏。
   - 系统目录阻止。
   - macOS `/private/var` / `/var/folders` carve-out。
   - 读写时防 traversal。
   - symlink 指向系统目录会被挡住。

3. `updates.py` 不是裸 `git pull`。
   - active stream 时拒绝 update。
   - 并发 update 被 lock。
   - dirty/conflict/diverged 有专门响应。
   - restart 等待 apply lock，避免第二个 repo 更新中被重启打断。

4. `onboarding.py` 对既有用户比较谨慎。
   - 非 wizard provider + 已配置时自动 complete。
   - existing config 默认不覆盖。
   - provider endpoint probe 有 redirect 禁止、timeout、body size 上限。

结构风险：

1. `boot.js` 文件名不再准确。
   - 它包含：
     - cancel stream。
     - workspace panel。
     - mobile/sidebar。
     - mic dictation。
     - turn-based voice mode。
     - new chat/import/export。
     - model select mutation。
     - composer keydown。
     - theme/skin/font。
     - boot IIFE。
   - 这些应该拆成 `boot-coordinator.js` + 若干 controller。

2. Profile 前端链路有明显残留。
   - `index.html` 中：
     - `onclick="toggleProfileDropdown()"`
   - 当前 `apps/webui/static/*.js` 搜不到 `toggleProfileDropdown()`。
   - 当前也搜不到 `switchToProfile()`。
   - 多个测试仍在 `static/panels.js` 里找 `switchToProfile()`。
   - 这不是纯重构问题：profile chip 点击可能直接报 `ReferenceError`。

3. 旧 panel/test 残留扩大了。
   - 除了上一轮发现的 `loadCrons()`，这轮还确认：
     - `cronRefreshBtn` 在 HTML 中不存在。
     - `loadCrons()` 在 `panels.js` 中不存在。
     - `loadProfilesPanel()` / `renderWorkspacesPanel()` 当前也搜不到。
   - 这些测试可能是旧 UI 的陈旧断言，也可能说明功能被删但入口没有清干净。
   - 必须先确认产品是否还需要 Tasks/Profile/Workspace 管理面板，再决定恢复还是删除。

4. `profiles.py` 仍然太像“全局状态修补器”。
   - process env。
   - TLS profile。
   - cron env lock。
   - skill module patch。
   - profile CRUD。
   - profile model validation。
   - profile terminal env。
   - 这些混在一个文件里，正确性靠大量注释和测试维持。

5. `workspace.js` 是 file panel 全家桶。
   - API client。
   - expanded dir persistence。
   - git badge。
   - preview route。
   - edit/save/cancel。
   - breadcrumb。
   - download/open browser。
   - 它虽不大，但职责很集中，后续如果加 file CRUD、search、diff，很快会膨胀。

6. `updates.py` 应拆 check/apply/summary。
   - 现在版本检测、git check、summary prompt、apply update、force reset、restart 都在一个模块。
   - 目前还可维护，但和 `config.py/providers.py` 一样有继续膨胀趋势。

建议拆分：

前端：

1. `boot-coordinator.js`
   - 只保留启动阶段：
     - settings preload。
     - profile preload。
     - models preload。
     - workspace preload。
     - onboarding gate。
     - session restore。
     - inflight restore。
     - gateway start。

2. `workspace-panel-controller.js`
   - `_workspacePanelMode`
   - open/close/sync panel state。
   - mobile/desktop panel behavior。

3. `voice-input.js`
   - mic dictation。
   - MediaRecorder fallback。
   - transcription request。

4. `voice-mode.js`
   - turn-based voice mode。
   - STT -> send -> TTS -> resume。
   - session pin guard。

5. `appearance-client.js`
   - theme/skin/font apply。
   - theme-color meta sync。
   - picker sync。

6. `profile-switcher.js`
   - `toggleProfileDropdown()`。
   - `switchToProfile()`。
   - profile chip spinner/disabled/optimistic state。
   - profile default workspace/model application。
   - dropdown close handler。
   - 与 `/api/profile/switch` 的 cookie/TLS contract。

7. `workspace-file-api.js`
   - `loadWorkspaceList()`。
   - `loadDir()`。
   - `read/save/raw/download` request helpers。

8. `workspace-preview.js`
   - preview mode routing。
   - code/md/image/html/pdf/audio/video。
   - edit/cancel/save。

9. `workspace-tree-view.js`
   - expanded dirs。
   - breadcrumb。
   - tree render。
   - git badge。

后端：

1. `profile_paths.py`
   - root/default/named profile path resolution。
   - root profile alias cache。

2. `profile_env.py`
   - runtime env。
   - `.env` reload。
   - skill module patch。
   - background worker profile env。

3. `profile_cron_context.py`
   - cron env lock。
   - cron.jobs / cron.scheduler patching。
   - scheduled job profile home resolution。

4. `profile_service.py`
   - list/create/delete/switch。
   - model validation。
   - workspace default extraction。

5. `workspace_store.py`
   - per-profile workspace list/last workspace。
   - migration/cleanup。

6. `workspace_security.py`
   - trusted roots。
   - blocked roots。
   - symlink/traversal logic。
   - add-path validation。

7. `workspace_files.py`
   - list/read/git info。
   - file save/raw/download 相关 helper。

8. `update_check.py`
   - version detection。
   - git release/branch check。
   - cache。

9. `update_summary.py`
   - summary cache。
   - prompt/fallback formatting。

10. `update_apply.py`
   - apply/force update。
   - active stream guard。
   - restart scheduling。

本轮验证：

- `node --check static/boot.js static/workspace.js static/ui.js static/panels.js` 通过。
- `.venv311/bin/python -m py_compile api/profiles.py api/workspace.py api/updates.py api/onboarding.py api/routes.py` 通过。
- 大聚焦 pytest：
  - 332 collected。
  - 289 passed。
  - 2 skipped。
  - 41 failed。
- 失败分类：
  1. `switchToProfile()` / profile dropdown 前端函数缺失：
     - `test_issue1700_parallel_profile_switch.py`
     - `test_profile_switch_ux.py`
     - `test_issue1116_composer_placeholder.py`
  2. 旧 cron/tasks/profile/workspace panel 静态断言：
     - `test_cron_refresh_button_835.py`
     - `test_settings_navigation_and_detail_refresh.py`
     - `test_issue2147_profile_workspace_copy.py`
  3. update/onboarding/i18n 文案静态断言漂移：
     - `test_update_apply_ui.py`
     - `test_update_banner_fixes.py` 的部分 UI 文案断言。
     - `test_onboarding_static.py`。
  4. onboarding probe 在本机网络环境中把 bad host / refused port 变成 HTTP 503：
     - `test_issue1499_onboarding_probe.py` 2 项。
     - 这更像本机网络/proxy 截获导致的测试不稳定，不能直接推断产品 probe 逻辑错。
  5. profile path/env isolation 在大组合里曾因 active `STREAMS` 污染失败；单独复跑通过。
- 单独复跑：
  - `test_profile_path_security.py` + `test_profile_env_isolation.py`：5 passed。
  - update apply backend conflict/success/force update tests：5 passed。
  - `test_update_apply_ui.py` 仍 1 failed，缺少 expected recovery 文案。
  - frontend profile switch 组：20 passed，13 failed，失败都围绕缺失 `switchToProfile()` 或 placeholder 旧文案。
- workspace 聚焦组：66 passed。

## 76. 第四十二轮：terminal / approval / MCP / skills / cron 权限链路

本轮读的重点不是普通 UI，而是“会执行命令、会接外部工具、会改 profile 资源”的权限面：

- `apps/webui/static/terminal.js`
- `apps/webui/api/terminal.py`
- `apps/webui/api/routes.py` 的 terminal / approval / yolo / skills / MCP / cron 路由段。
- `apps/webui/static/messages.js` 的 approval / clarify / YOLO 状态机。
- `apps/webui/static/commands.js` 的 `/terminal`、`/skills`、`/yolo`。
- `apps/webui/static/panels.js` 的 cron residue 和 MCP inventory panel。
- `apps/webui/mcp_server.py`
- `runtimes/hermes-agent/tools/approval.py`
- `runtimes/hermes-agent/tools/mcp_tool.py`
- `runtimes/hermes-agent/tools/skills_tool.py`

### 76.1 产品逻辑

这条链路的产品逻辑可以分成五层：

1. 嵌入式 workspace terminal：
   - 前端 `/terminal` 命令或按钮创建/打开 composer terminal。
   - `terminal.js` 绑定当前 `S.session.session_id` 和 `S.session.workspace`。
   - 后端 `/api/terminal/start` 从 session 取 workspace，并用 `resolve_trusted_workspace()` 校验。
   - `api/terminal.py` 用 PTY 启动交互 shell。
   - 输出走 `/api/terminal/output` SSE，输入走 `/api/terminal/input`。
   - session/workspace 切换时前端关闭不匹配的 terminal。

2. 危险命令 approval：
   - agent runtime 的 `tools.approval` 负责 pattern detection、hardline block、session approval、permanent allowlist、gateway blocking queue。
   - `streaming.py` 在切到 session profile 的 `HERMES_HOME` 后注册 approval notify callback。
   - callback 把 `approval` event 推给 WebUI stream。
   - `routes.py` 也提供 `/api/approval/pending`、`/api/approval/stream`、`/api/approval/respond`。
   - `messages.js` 维护当前 session 的 approval card，支持 SSE 优先、poll fallback、多 approval queue counter、最小可见时间。

3. YOLO：
   - `/yolo` 或 approval card 内按钮 POST `/api/session/yolo`。
   - 后端状态在 `tools.approval._session_yolo`，session scoped、server memory scoped。
   - 开启时会清 pending approval，并 `resolve_gateway_approval(..., resolve_all=True)` 释放等待中的 agent thread。
   - 生命周期注释写得很明确：reload/cross-tab 共享，server restart 丢失，cross-session 隔离。

4. MCP：
   - `streaming.py` 必须在 profile env/HERMES_HOME mutation 之后调用 `discover_mcp_tools()`。
   - `tools/mcp_tool.py` 连接外部 MCP server，注册工具到 registry，支持 stdio/http/sse、sampling、parallel opt-in、stderr 重定向、credential redaction、tool description injection scan。
   - `routes.py` 的 `/api/mcp/servers` 和 `/api/mcp/tools` 只读展示已知 runtime/registry inventory，不主动 probe/spawn。
   - `panels.js` 的 MCP panel 是 read-only visibility panel。
   - `apps/webui/mcp_server.py` 是另一个方向：把 WebUI 的 project/session 管理暴露成 MCP server，mutation 走 WebUI HTTP API，避免直接写 session 文件导致运行中缓存漂移。

5. Skills / cron：
   - WebUI skills GET API 每次按 active profile 计算 skills dir，避免 `tools.skills_tool.SKILLS_DIR` 这个 module global 串 profile。
   - skill content 支持 linked file，并做 path traversal/wildcard guard。
   - cron 后端大量依赖 `cron_profile_context()`，手动 run 还用 child process 隔离 cron.scheduler / cron.jobs 的 process-global `HERMES_HOME`。
   - 但前端 cron/skills 旧面板已经残缺：`panels.js` 仍调用 `loadCrons()`，当前静态文件里没有定义；skills detail/collapse 的旧函数也不在 `panels.js`。

### 76.2 代码写得好的地方

这一轮最重要的结论：不是所有大文件都“烂”。很多局部代码有很成熟的工程判断：

- `api/terminal.py`
  - 和 agent execution path 明确分离。
  - 不修改 global env。
  - terminal 子进程只拿 allowlist env，避免 API key/secrets 泄漏。
  - PTY output queue 有最大长度，满了丢旧 chunk，避免无限涨内存。
  - close 时先 SIGHUP，再必要时 SIGKILL。

- `tools/approval.py`
  - YOLO env 在 import 时冻结，避免 skill 动态改 `os.environ` 绕过审批。
  - session identity 用 contextvars，避免并发 gateway/agent thread 串 session。
  - hardline block 在 YOLO / approvals.mode=off 之前执行。
  - sudo stdin guard、敏感路径、Hermes config/env path 的说明很清楚。
  - gateway queue 是 per-session FIFO，支持多个并发 approval。

- approval SSE in `routes.py`
  - subscribe 和 initial snapshot 在同一个 lock 下完成，避免“刚 snapshot 完、还没订阅时来了 approval”的丢事件竞态。
  - respond 后会通知新的 queue head，避免第二个 approval 卡在后面不可见。

- MCP runtime：
  - stdio MCP subprocess stderr 重定向到 per-profile log，避免污染 TUI。
  - stdio env 做 safe env filter。
  - error text 做 credential redaction。
  - tool description 做 prompt injection pattern scan。
  - `/api/mcp/tools` 只读 already-known runtime，不为了展示 UI 主动启动 server。

- `mcp_server.py`
  - mutation 不直接改 session 文件，而是走 HTTP API，明确知道运行中 WebUI cache 可能覆盖 direct filesystem write。
  - project/session visibility 使用 profile match helper，不自己复制一套规则。

### 76.3 主要维护性问题

问题主要不是语法，而是边界：

1. `routes.py` 仍是权限面的总入口。
   - terminal、approval、clarify、cron、skills、MCP 都在一个 10000+ 行文件里分发。
   - handler 本身有不少好逻辑，但 API ownership 不清晰。

2. terminal session ownership 需要更明确的 contract。
   - start 会读取 session 并校验 workspace。
   - input/resize/close/output 只拿 `session_id` 找 in-memory terminal。
   - 在单用户本地 WebUI里通常够用，但作为权限面最好显式定义“session_id 是否就是 terminal capability”。
   - 建议增加 terminal owner/active-session contract，避免之后多用户/auth 改造时踩坑。

3. terminal 生命周期靠前端关闭和 session delete cleanup。
   - 没看到独立 TTL/reaper。
   - browser reload、网络断开、server 长时间运行时，泄漏 terminal 的风险主要靠 beforeunload/sendBeacon 和显式 close 管。

4. `messages.js` 承担太多全局状态机。
   - chat streaming、approval、clarify、notification、btw/background 都在同一个文件里。
   - approval/clarify 状态本身设计细，但和主消息流耦合太紧。

5. MCP routes 有未接线 handler。
   - `routes.py` 定义了 `_handle_mcp_server_delete()` / `_handle_mcp_server_update()`。
   - 当前只看到 `/api/mcp/servers` 和 `/api/mcp/tools` GET 路由，未看到 update/delete 路由调用。
   - 如果未来要恢复编辑能力，要先决定 MCP panel 是 read-only 还是 editable，避免死代码继续漂。

6. skills API duplicated agent skill logic。
   - WebUI 为 profile scoping 复制/镜像了 `tools.skills_tool` 的 list/view 逻辑。
   - 这是合理的战术修复，但长期应该抽一个 profile-aware skill service，而不是 routes 顶部继续膨胀。

7. 旧面板残留是实际债务。
   - `static/index.html` 仍有 `onclick="toggleProfileDropdown()"`。
   - `static/*.js` 没找到 `toggleProfileDropdown()` / `switchToProfile()`。
   - `panels.js` 仍调用 `loadCrons()`，但当前静态文件里没找到定义。
   - skill detail/collapse 相关旧函数也缺失，测试仍在期待。
   - 这属于“迁移一半”的风险：不是简单删测试，也不能简单补函数，必须先明确这些 UI 入口是否仍是产品入口。

### 76.4 本轮验证

- `node --check static/terminal.js` 通过。
- `node --check static/messages.js` 通过。
- `node --check static/commands.js` 通过。
- `py_compile` 通过：
  - `api/terminal.py`
  - `api/routes.py`
  - `api/streaming.py`
  - `mcp_server.py`
  - `runtimes/hermes-agent/tools/approval.py`
  - `runtimes/hermes-agent/tools/mcp_tool.py`
  - `runtimes/hermes-agent/tools/skills_tool.py`
- 聚焦 pytest：
  - 204 collected。
  - 187 passed。
  - 1 skipped。
  - 17 failed。
- 通过的重点：
  - terminal cleanup/ownership/workspace/env。
  - approval queue/SSE/unblock/card layering。
  - YOLO toggle。
  - MCP management/visibility/tool inventory/tool list overflow。
  - profile-scoped skills。
  - profile MCP discovery timing。
  - skill module HERMES_HOME patching / env lock import guard。
- 失败集中在旧 skills panel：
  - `_renderSkillError()` 缺失。
  - `data.success === false || data.error` guard 缺失。
  - linked file error detail pane 缺失。
  - `_collapsedCats` / `_toggleCatCollapse()` / `renderSkills()` collapse 行为缺失。

### 76.5 判断

这条权限链路的底层安全逻辑比前端壳清晰。真正不优雅的地方是：

- 安全/运行时能力分散在 `routes.py`、`messages.js`、`panels.js` 这些巨型文件。
- 旧 UI 函数和测试没有和新产品壳同步。
- 对 session/profile/MCP/terminal 这些“会执行东西”的能力，缺少一份统一 contract。
- TS 重写不能直接解决这些问题；更好的顺序是先抽 contract 和模块，再把协议/pure model 层 TS 化。

## 77. 第四十三轮：auth / file / upload / media / rollback / worktree 资源访问链路

这一轮继续看本地资源访问能力。这个区域很重要，因为它直接决定：

- 浏览器是否能读写 workspace 文件。
- 上传文件是否会落到安全位置。
- HTML/PDF/media 预览是否会造成同源 XSS。
- rollback/worktree 是否可能误删或跨 workspace 操作。

### 77.1 产品逻辑

产品上可以分成六层：

1. auth/session：
   - 默认可以不开密码。
   - 开启 auth 时用 cookie session。
   - 浏览器 unsafe request 走 CSRF。

2. workspace file browser：
   - `/api/list`、`/api/file`、`/api/file/raw`、`/api/file/save/create/delete/rename/path/reveal`。
   - UI 里是 workspace panel 的 tree、preview、edit、download、open。

3. uploads：
   - 普通 upload 进 session-scoped attachment inbox。
   - archive upload 会 extract 到 workspace。
   - transcribe 用临时文件。

4. media：
   - `MEDIA:` token 用 `/api/media?path=<absolute path>`。
   - 主要给 agent 生成的本地图片/PDF/HTML/audio/video 预览。

5. rollback checkpoints：
   - checkpoint 按 workspace hash 存在 active Hermes home 下。
   - UI 用 rollback panel list/diff/restore。

6. worktree lifecycle：
   - session 可以绑定 worktree。
   - 删除 worktree 前检查 stream、terminal、dirty、untracked、ahead。

### 77.2 代码逻辑和优点

这条链路不是“随便写的”。读下来有不少成熟补丁：

- `api/auth.py` 结构相对清晰：
  - PBKDF2-SHA256 600k iteration。
  - session cookie HMAC 签名。
  - session/login attempt 都原子写入，权限 0600。
  - 登录限流按 IP 记。
  - cookie 有 HttpOnly / SameSite=Lax / Max-Age，能按配置加 Secure。

- `routes.py` 的 CSRF 逻辑考虑了兼容性：
  - `/api/auth/login` 和 `/api/csp-report` exempt。
  - unsafe method 且像 browser request 时校验 Origin/Referer + session-bound token。
  - 非浏览器 API client 保留兼容。

- `api/upload.py` 的边界比较全：
  - Content-Length 受 `MAX_UPLOAD_BYTES` 限制。
  - 普通附件写到 `STATE_DIR/attachments/<session_id>/`。
  - archive extract 用 `safe_resolve_ws()`，有 zip-slip/tar-slip 检查。
  - extract byte guard 是 `10 * MAX_UPLOAD_BYTES`。
  - 出错会清理 partial extraction dir。

- `api/workspace.py` 是本轮最认真写的安全模块之一：
  - `resolve_trusted_workspace()` 阻止系统根目录。
  - 对 macOS `/private/var`、`/var/folders`、home symlink 有专门处理。
  - `safe_resolve_ws()` 允许 workspace 内用户自己放的 symlink，但挡系统路径。
  - `list_dir()` 避免 symlink cycle。

- `/api/file/raw` 和 `/api/media` 都有 HTML 防护：
  - SVG 强制 download。
  - HTML 只有 `inline=1` 才能 inline。
  - inline HTML 会加 `Content-Security-Policy: sandbox allow-scripts`。
  - sandbox 分支不发 `X-Frame-Options: DENY`，避免 iframe 被挡。

- `api/worktrees.py` 删除 worktree 前有明确 safety gate：
  - active stream 拦截。
  - active terminal 拦截。
  - dirty/untracked/ahead 默认拦截。
  - force 时仍返回 warnings。

- `api/rollback.py` 有 checkpoint id regex：
  - 拒绝 `/`、`.`、`..`。
  - checkpoint diff/restore 都先 validate。
  - restore 只复制 checkpoint tracked files，不删除 workspace 新增文件。

### 77.3 主要维护性问题

这条链路的风险主要不是“写法错”，而是契约分散：

1. `routes.py` 仍然在承载资源权限面。
   - media/file/raw/rollback/worktree/remove/upload 都在同一个巨型 dispatcher 里。
   - 每段局部代码不少是对的，但 ownership 不清晰。

2. workspace file 的 path contract 不统一。
   - `list_dir()` / `read_file_content()` 用 `safe_resolve_ws()`。
   - `/api/file/raw`、save/create/delete/rename/path/reveal 用 `api.helpers.safe_resolve()`。
   - 结果是：目录浏览/文本读取允许 workspace 内 symlink 指向非系统路径，但 raw preview/edit/delete 会更严格地挡掉 resolved-outside-root。
   - 安全上偏保守，但产品行为需要写进 contract，否则用户会遇到“能看列表但不能预览/编辑”的不一致。

3. `/api/media` 是 absolute-path capability。
   - allowed roots 包括 Hermes home、`/tmp`、`~/.hermes`、last workspace、`MEDIA_ALLOWED_ROOTS`。
   - 这是为了 agent 产物预览而设计的，不是 session workspace 文件 API。
   - 如果未来多用户化，需要把它改成 session-scoped media token，而不是继续传绝对路径。

4. rollback 是 workspace-list scoped，不是 session scoped。
   - `_resolve_workspace()` 校验目标在 profile workspace list 里。
   - 单用户本地 WebUI 合理。
   - 如果有多用户/auth 强化，需要明确“有 workspace list 权限就能 diff/restore”是否成立。

5. workspace preview 的 Open in browser 有一个前端契约小问题。
   - preview iframe 对 HTML 用 `&inline=1`。
   - `openInBrowser()` 生成的 `/api/file/raw?...` 没有 `inline=1`。
   - 对 HTML 来说，这可能会变成 download，而不是打开 sandboxed browser view。

6. upload multipart parser 是 homemade，并且 full body in memory。
   - 目前有 body size limit，风险可控。
   - 长期应该换成 streaming parser 或至少把 parser/service 独立测试。

7. 前端 API wrapper 重复。
   - `workspace.js` 有自己的 `api()`。
   - `ui.js`、`messages.js` 也在各自管理 request/状态。
   - 拆分时应先抽 file/workspace client，而不是继续复制 fetch + auth redirect。

### 77.4 本轮验证

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

通过的重点包括：

- auth session persistence / login attempt / password hash cache。
- CSRF token / CSP report / PWA manifest CSP。
- `/api/media` inline、range、auth gate、HTML CSP sandbox。
- native image attachments 和 `/api/file/raw` session fallback。
- PDF/HTML preview。
- upload size preflight。
- macOS blocked roots / inaccessible workspace / session import workspace validation。
- workspace rename/context menu/stale recovery/add quote strip。
- worktree remove/status/lifecycle/UI static。
- rollback checkpoint id validation。

### 77.5 判断

这条资源访问链路整体质量比“上万行”这个现象看起来要好。它的局部安全补丁很多，测试也不少，所以不能粗暴改。

但它仍然需要拆：

- HTTP route、权限校验、路径解析、文件服务、UI 预览行为混在一起。
- `routes.py` 让新增 API 的认知成本过高。
- `safe_resolve` / `safe_resolve_ws` 的差异没有被产品契约解释。
- `/api/media` absolute path 模式需要明确边界。

推荐拆法是：

1. 先写 `FILE_ACCESS_CONTRACT.md` / `MEDIA_ACCESS_CONTRACT.md` / `AUTH_CSRF_CONTRACT.md`。
2. 抽 `api/file_routes.py`、`api/file_access_service.py`。
3. 抽 `api/media_routes.py`、`api/media_service.py`。
4. 抽 `api/upload_routes.py`、`api/upload_service.py`。
5. 抽 `api/rollback_routes.py`、`api/rollback_service.py`。
6. 抽 `api/worktree_routes.py`，保留 `api/worktrees.py` 作为 runtime/service。
7. 前端抽 `workspace-file-client.js`、`workspace-preview-controller.js`。
8. 最后再考虑把 file/media payload 和 preview model TS 化。

## 78. 第四十四轮：工程门禁 / 测试契约 / 前端全局入口

这一轮看的是：如果要拆上万行文件，当前工程有没有足够的门禁告诉我们“拆对了还是拆坏了”。

结论比较明确：目前门禁覆盖不足，且有一批旧前端契约已经和当前代码分叉。

### 78.1 CI / package check 现状

根目录：

- `package.json`：
  - `check = pnpm -r check && pnpm verify`
  - `verify = node scripts/verify.mjs`
- `.github/workflows/verify.yml`：
  - install pnpm。
  - setup Node 22。
  - setup Python 3.12。
  - run `pnpm check`。
- `pnpm-workspace.yaml`：
  - 只有 `packages/*`。

实际含义：

- `pnpm -r check` 只跑：
  - `packages/hermes-client`
  - `packages/space-runtime`
- 不跑：
  - `apps/webui`
  - `experiments/*`
  - `runtimes/hermes-agent/*`
  - `products/*`

`scripts/verify.mjs` 目前只做：

- repo audit。
- `py_compile` 少数 Python 文件：
  - `apps/webui/api/products.py`
  - `apps/webui/api/product_context.py`
  - `apps/webui/api/routes.py`
  - `apps/webui/api/updates.py`
- `node --check` 少数 JS 文件：
  - `product-runtime.js`
  - `product-store.js`
  - `product-shell-runtime.js`
  - `workspace.js`
  - `products/ppt-designer/app.js`

它没有跑：

- `apps/webui/tests` pytest。
- `node --check static/ui.js`。
- `node --check static/messages.js`。
- `node --check static/panels.js`。
- `node --check static/boot.js`。
- `node --check static/sessions.js`。
- `py_compile apps/webui/api/*.py` 全量。

本轮验证：

- `node scripts/verify.mjs` 通过。
- `pnpm -r check` 通过。
- 但这两个绿灯并不代表 WebUI 前端入口和 pytest 契约健康。

### 78.2 体量和测试库存

当前 WebUI 仍有明显巨型文件：

- `apps/webui/static/i18n.js`：11533 行。
- `apps/webui/api/routes.py`：10721 行。
- `apps/webui/static/ui.js`：7962 行。
- `apps/webui/static/style.css`：6998 行。
- `apps/webui/api/streaming.py`：5535 行。
- `apps/webui/api/config.py`：4403 行。
- `apps/webui/static/sessions.js`：3849 行。
- `apps/webui/static/messages.js`：3297 行。
- `apps/webui/static/panels.js`：2094 行。
- `apps/webui/static/boot.js`：1704 行。

测试库存：

- `apps/webui/tests` 约 23M。
- `test_*.py` 文件约 550 个。

问题不是“没有测试”，而是：

- CI 默认不跑这些 pytest。
- 很多 pytest 是源码字符串测试，绑定旧函数名/旧模块位置。
- 这些测试对防回归有用，但拆模块前必须升级成行为测试或 route manifest/exported API 测试。

### 78.3 前端 script 和全局入口

`index.html` 当前加载顺序：

1. `i18n.js`
2. `icons.js`
3. `ui.js`
4. `workspace.js`
5. `terminal.js`
6. `sessions.js`
7. `commands.js`
8. `messages.js`
9. `product-store.js`
10. `product-shell-runtime.js`
11. `product-runtime.js`
12. `product-evolution.js`
13. `panels.js`
14. `onboarding.js`
15. `boot.js`

这是典型 browser-global architecture：

- 大量函数靠全局名字被 HTML inline handler 调用。
- 脚本顺序就是 dependency graph。
- 没有 module import/export 约束。

本轮写了一个临时扫描器检查 `index.html` 的 inline handlers，当前明确缺失：

- `toggleProfileDropdown()`
- `toggleComposerWsDropdown()`
- `clearConversation()`

其中：

- `profileChip` 仍有 `onclick="toggleProfileDropdown()"`。
- `composerWorkspaceChip` 和 mobile workspace action 仍有 `onclick="toggleComposerWsDropdown()"`。
- settings conversation 里 `btnClearConvModal` 仍有 `onclick="clearConversation()"`。

### 78.4 旧 UI 契约和当前代码分叉

聚焦测试结果：

- `tests/test_sprint8.py`：
  - 14 collected。
  - 13 passed。
  - 1 failed。
  - 失败：`panels.js` 不包含 `clearConversation`。

- `tests/test_sprint9.py`
- `tests/test_issue1700_parallel_profile_switch.py`
- `tests/test_profile_switch_ux.py`
- `tests/test_issue1464_workspace_dropdown_filter.py`
- `tests/test_issue2147_profile_workspace_copy.py`

合并跑：

- 29 collected。
- 13 passed。
- 16 failed。

失败集中在：

- `loadCrons()` 缺失。
- `loadSkills()` 缺失。
- `switchToProfile()` 缺失。
- `renderWorkspaceDropdownInto()` 缺失。
- profile/workspace mental-model help card 缺失。
- 旧 profile switch spinner/parallel fetch 契约缺失。

移动端 workspace 测试单独跑：

- `test_workspace_control_lives_in_mobile_overflow_panel` failed。
- 原因：`panels.js` 不存在 `_positionComposerWsDropdown()`。

这说明当前前端不是简单“拆得不够好”，而是：

- HTML/CSS 还保留一部分旧 dropdown 壳。
- 测试还保留旧面板行为预期。
- JS 里相关实现已经缺失或迁移走。
- 当前 CI 不会拦住这些断口。

### 78.5 判断

拆分顺序要调整：在大规模移动代码前，先做工程门禁。

建议：

1. 先加 WebUI verify profile。
   - `node --check apps/webui/static/*.js`。
   - `python -m py_compile apps/webui/api/*.py`。
   - 跑一组快速 pytest smoke。

2. 加 inline handler scanner。
   - 扫 `index.html` 的 `onclick/oninput/...`。
   - 检查被调用函数存在于当前 loaded scripts。
   - 对复杂 expression 只抽第一个真实 function call。

3. 收口旧面板契约。
   - profile dropdown/workspace dropdown/clear conversation/load crons/load skills，要么恢复，要么从 HTML/CSS/tests 删除。
   - 不要让“半迁移壳”继续留在产品里。

4. 给巨型文件加体量守门。
   - 新代码不得继续进 `routes.py` / `ui.js` / `i18n.js` / `style.css` / `streaming.py`。
   - 可允许临时白名单，但新增行要解释。

5. 再开始拆 route/service/client。

这个顺序比直接 TS 重写更稳。TS 只能约束迁出的模块；对于现在这种 browser global + inline handler + stale pytest 的状态，先上 TS 也只是把混乱搬进 `.ts` 文件。

## 79. 第四十五轮：session / state.db / run journal / recovery 数据层

这一轮收束到“会话数据到底怎么存、怎么恢复、怎么和 CLI/Claude Code 导入会话合并”。这是拆 `routes.py`、`sessions.js` 之前最关键的一层，因为它决定：

- 侧边栏看到什么 session。
- 当前聊天如何分页/恢复/继续。
- 只读导入会话能不能修改。
- stream 中断后 pending turn 怎么补救。
- `.json`、`.json.bak`、`_index.json`、`state.db`、run journal 之间谁是事实来源。

结论：这层代码不算乱写，反而有很多防数据丢失的修补。但它现在集中在 `models.py`、`routes.py`、`sessions.js` 里，职责过宽，必须按数据契约拆，不适合直接 TS 重写。

### 79.1 产品逻辑

会话数据层可以理解成六条产品链路：

1. WebUI 原生 session：
   - 新建 session 后不一定马上落盘。
   - 有消息或绑定 worktree 时才持久化。
   - sidebar 用 metadata/index 快速展示。

2. session 读写：
   - `/api/session` 支持 metadata-only、分页、run journal 状态、CLI metadata 合并。
   - mutation 前必须把 metadata-only session 升级为完整 session，避免半截数据覆盖完整文件。

3. sidebar 列表：
   - `/api/sessions` 以 `_index.json` 为快路径。
   - 叠加内存 session、profile scope、CLI/messaging session、lineage metadata。

4. 外部/导入 session：
   - `state.db` 里的 CLI、Claude Code、messaging session 可以进入 WebUI 列表。
   - 有些 session 是 read-only，只能查看，不能改名、归档、删除、发送消息。

5. recovery：
   - `.json.bak` 用来防止 message count 回退。
   - state.db 里存在但 JSON sidecar 缺失时，可以 materialize sidecar。
   - run/turn journal 用来判断中断和恢复状态。

6. frontend session UX：
   - `sessions.js` 同时负责列表、搜索、virtualization、lineage 展开、CLI 导入、read-only guard、rename、delete、project、gateway SSE。
   - 它已经不是单纯的“侧边栏 JS”。

### 79.2 代码逻辑和优点

`apps/webui/api/models.py` 虽然 2000 多行，但不是无脑堆代码。里面有几组比较成熟的保护：

- `_write_session_index()`：
  - 有 `_INDEX_WRITE_LOCK`。
  - 支持 O(1) update。
  - 失败时可以 full rebuild。
  - 写入走 tmp + fsync + replace。
  - 会清理 stale tmp。

- `Session.save()`：
  - 拒绝保存 `_loaded_metadata_only` 的 stub，避免 metadata-only 覆盖完整 messages。
  - incoming message count 变少时先写 `.json.bak`。
  - 保存 session JSON 和更新 index 是原子化思路。

- `load_metadata_only()`：
  - 只读到 messages 前的 prefix。
  - 从 index 填 `_metadata_message_count`。
  - 明确标记成不能直接 save 的 stub。

- `all_sessions()`：
  - 优先读 `_index.json`。
  - overlay 内存 session。
  - 过滤空 Untitled。
  - 兼容 snapshots、cron hidden、profile default backfill。
  - 能补 lineage metadata。

- `agent_sessions.py`：
  - 把 raw source、CLI visibility、compressed chain、close continuation、lineage report 统一投影出来。
  - 这块已经像一个独立 service，应单独成模块。

- `gateway_watcher.py`：
  - 轮询 active profile 的 `state.db`。
  - 用 session id / updated / message_count 做 hash。
  - 广播给 subscriber queue，并清理慢 subscriber。

- `session_recovery.py`：
  - 会比较 live JSON 和 `.bak` message count。
  - orphan backup restore 前会确认 state.db 仍有 row。
  - state.db 缺 sidecar 时用 atomic create-or-fail。
  - audit 能区分 repairable 和 unsafe。

- `run_journal.py`：
  - append-only JSONL。
  - session/run id 有正则限制，拒绝 slash/backslash。
  - per-path writer lock。
  - `O_APPEND` + 0600 + fsync 策略。
  - 能读 summary，也能合成 stale interrupted event。

### 79.3 主要维护性问题

1. `models.py` 名字不准确。
   - 它现在同时是 session model、session store、index writer、sidebar projection、CLI bridge、project persistence、recovery glue。
   - 这不是“模型文件”，而是多个数据服务混在一起。

2. `routes.py` 承载太多 session HTTP 行为。
   - `/api/session`
   - `/api/sessions`
   - `/api/session/new`
   - duplicate / rename / pin / archive / delete / clear / truncate / branch / import / import_cli
   - run journal / recovery / lineage 相关入口
   - 这些应该拆成 session read routes、mutation routes、CLI import routes、recovery routes、journal routes。

3. session contract 隐含在代码里。
   - metadata-only session 不能 save。
   - read-only imported session 不能 mutation。
   - `_index.json` 是性能索引，不应该是唯一事实源。
   - `.json.bak` 只在 message count 缩短时写。
   - 这些都需要文档化，否则拆模块时很容易破坏。

4. state.db 恢复 sidecar 的 workspace 语义需要再钉牢。
   - recovery payload 里 workspace 可能为空。
   - `Session.__init__` 对空字符串路径可能解析到当前 cwd。
   - 这应该明确成 contract：state.db recovery 不允许把空 workspace 隐式变成 cwd，必须用 trusted/default workspace 或保持 unknown。

5. frontend read-only 契约和测试分叉。
   - 当前 `sessions.js` 已经有 `_isReadOnlySession()`。
   - read-only session 不显示 action menu。
   - double click rename 会 toast 并 return。
   - `messages.js` 也阻止 read-only session 发送。
   - 但测试还在找旧英文字符串和旧源码形态，说明测试需要升级成行为测试。

6. `sessions.js` 过重。
   - sidebar store、virtual list、search、lineage、gateway SSE、CLI import、rename/delete/project、read-only guard 全在一个文件。
   - 继续往里加功能会越来越难验证。

7. frontend/backend session title 逻辑有多套。
   - `_sessionDisplayTitle()`
   - `assistantDisplayTitleForSession()`
   - product shell title normalization
   - tests 还假设某个固定源码字符串。
   - 应该抽成 title/display contract。

8. route dispatcher 容易出现死代码和错位。
   - 本轮确认 `/api/session/conversation-rounds` 后没有直接混入 provider probe 死代码。
   - 但 provider probe、session mutation、onboarding probe 都仍塞在同一个 `routes.py` dispatcher 里，认知成本很高。

### 79.4 本轮验证

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

失败项：

1. `test_sidebar_search_and_rows_use_read_only_display_title`
   - 测试期待 `const rawTitle=_sessionDisplayTitle(s);`
   - 当前实现改成优先 `assistantDisplayTitleForSession(s)`，再 fallback `_sessionDisplayTitle(s)`。
   - 这更像旧源码字符串测试过严，不一定是产品 bug。

2. `test_read_only_source_badge_ui_guards_are_present`
   - 测试期待英文字符串 `Read-only imported sessions cannot be renamed`。
   - 当前实现中文 toast：`只读导入任务不能重命名。`
   - read-only guard 行为存在，但测试仍绑旧文案。

### 79.5 判断

session 数据层不是“写错了”，而是“职责太集中”。正确拆法是：

1. 先写 session storage/index/recovery/read-only/agent projection contract。
2. 把 `models.py` 拆成 store/index/sidebar/projection/bridge/project 几个后端模块。
3. 把 `routes.py` 的 session API 拆成 route 文件。
4. 把 `sessions.js` 拆成 store/client/view/lineage/gateway/action modules。
5. 最后只把纯 payload/model/client 类型 TS 化。

不建议直接用 TS 重写这一层。TS 可以帮 payload 和前端纯逻辑，但不能替你定义 `.json`、`.bak`、`state.db`、read-only、metadata-only 这些数据契约。

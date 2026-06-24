# AI Computer / Product OS Research Blueprint

更新日期：2026-06-20

本文是调研与执行蓝图，不替代 `docs/PRODUCT_MODEL_CONTRACT.md`。如果两者冲突，以产品模型契约为准。本文回答一个问题：Knead 为什么应该长成一台 AI Computer，以及怎样从当前代码稳妥地走过去。

## 1. 需求判断

用户想要的不是“桌面皮肤”，而是一个能承接“持续造很多 AI 产品”的空间模型。

这个隐喻成立的原因：

- Knead 的核心动作是造产品，不是只聊天。
- 用户会不断创建不同用途的 AI 产品：PPT、写作、游戏、研究、数据、图片、角色、工具。
- 每个 AI 产品都有名字、图标、能力、记忆、工作区、预览、版本和任务历史。
- 大量产品如果还放在聊天列表里，会被理解成“几个助手”；放在桌面/电脑里，会被理解成“我拥有一套会生长的软件系统”。
- 创建一个产品像桌面上多一个 App；调整一个产品像进入 App 的设置/升级；产品产物像文件或项目留在电脑里。

一句话：

> Knead 是一台用来创造、使用、管理和进化 AI 产品的电脑。

这不是装饰性类比，而是产品模型和 UI 容器天然对齐。

## 2. 外部调研

### 2.1 PostHog Product OS

来源：

- <https://posthog.com/blog/why-os>
- <https://posthog.com/handbook/engineering/posthog-com/how-posthog-website-works>
- <https://posthog.com/handbook/engineering/posthog-com/technical-architecture>
- <https://github.com/PostHog/posthog.com>

关键实现：

- Gatsby 页面通过 `wrapPageElement` 进入全局 App Provider。
- `Wrapper` 渲染系统外壳：TaskBarMenu、Desktop、AppWindow。
- 普通页面不再直接占满浏览器，而是被转换成窗口。
- App Provider 管理窗口数组：element、position、size、zIndex、minimized、path、appSettings。
- 路由行为和窗口行为绑定：打开新窗口、聚焦已有窗口、替换当前窗口。
- Desktop 提供图标和背景，AppWindow 提供可拖拽、缩放、最小化、聚焦、关闭的窗口。
- 支持两种体验模式：OS mode 和普通网站模式。移动端或用户切换时可回退。

适合我们学习的点：

- “OS 感”来自架构，而不是背景图。页面对象进入窗口系统，用户才会相信这是一个电脑。
- 每个入口都是 app-like object，不只是导航链接。
- 桌面图标是内容对象的空间化表达。
- 需要普通模式 fallback，避免 OS 壳影响移动端、可访问性和调试。
- Window state 是一等状态，不应该散落在 DOM class 里。

不适合照搬的点：

- PostHog 是内容网站 + 产品导航，Knead 是用户生成产品系统。
- PostHog 的核心对象是页面，Knead 的核心对象是 AI 产品。
- PostHog 的视觉世界观可以参考气质，但不能复制画风。

### 2.2 daedalOS

来源：

- <https://github.com/DustinBrett/daedalOS>

关键实现：

- 浏览器里的完整桌面环境。
- 有文件系统、窗口、任务栏、开始菜单、拖拽、右键菜单、持久化位置、IndexedDB、应用别名、文件打开方式。
- 窗口使用可拖拽/可缩放组件，打开关闭带动效。

适合我们学习的点：

- 文件/作品抽象可以成为第二阶段能力：AI 产品产出的 deck、文档、图片、数据表，不应该只藏在 session 里。
- 窗口位置、图标布局、最近打开状态需要持久化。
- 桌面交互需要一套小内核：focus、z-index、open、close、minimize、restore。

不适合照搬的点：

- 它是完整 OS 模拟器，范围太大。
- 文件系统、右键菜单、开始菜单、模拟器生态会把 Knead 带偏。
- 我们第一阶段只需要 Product OS，不需要 general-purpose OS。

### 2.3 Puter

来源：

- <https://github.com/HeyPuter/puter>
- <https://puter.com>

关键实现：

- 定位为 open-source internet computer。
- 同时服务用户和开发者：文件、应用、游戏、App Store、开发者能力、云存储、数据库、serverless。
- 应用可以被构建、发布、分发。

适合我们学习的点：

- “电脑”可以同时承载用户视角和开发/发布视角，但需要分层。
- App Store / publish / developer platform 的心智可以帮助我们理解“创建产品 -> 发布产品 -> 使用产品”。
- 用户拥有一个可从任何地方打开的个人工作空间，这和 Knead 的长期产品库类似。

不适合照搬的点：

- Puter 是云操作系统和开发平台，Knead 不是要先做通用应用市场。
- 我们的创建动作是 AI 造产品，不是开发者上传 Web App。

### 2.4 OS.js

来源：

- <https://www.os-js.org/>
- <https://github.com/os-js/OS.js>

关键实现：

- 浏览器桌面平台，包含 window manager、application APIs、GUI toolkit、filesystem abstraction。

适合我们学习的点：

- Desktop Shell 应该分成稳定内核和应用 API。
- 应用不是随便 iframe，应该有一组 host capability：打开窗口、存状态、发消息、读写产品状态、请求 AI。

不适合照搬的点：

- OS.js 是平台框架，抽象很重。
- Knead 的 app API 应该围绕 AI 产品生命周期，不是通用 GUI toolkit。

### 2.5 常见 macOS / Windows 网页仿站

结论：

- 可以参考第一眼的桌面识别，比如顶部栏、图标、窗口、dock。
- 不适合作为主要范式，因为多数作品集 clone 只有视觉，没有产品生命周期。
- Knead 的价值在“造出来的产品真的住在这里”，不是“网页看起来像 macOS”。

### 2.6 实现级模式抽取

#### PostHog：窗口是一等数据结构

PostHog 的 `src/context/Window.tsx` 给窗口定义了完整对象：

- `key`
- `path`
- `element`
- `zIndex`
- `minimized`
- `position`
- `size`
- `previousPosition`
- `previousSize`
- `sizeConstraints`
- `appSettings`
- `location`

这说明“电脑感”的关键不是 CSS，而是把窗口当作可管理的数据对象。Knead 第一版不需要完全复制，但必须至少有：

- `id`
- `type`
- `productId`
- `title`
- `zIndex`
- `state`
- `position`
- `size`

否则多窗口、恢复、聚焦、用/调并行都会变成 DOM class 拼凑。

#### PostHog：路由和窗口生命周期绑定

PostHog 的 App Provider 在 `addWindow` / `updatePages` 中决定：

- 路径已有窗口时聚焦。
- `newWindow` 时新增。
- 普通导航时替换当前窗口。
- 关闭窗口后导航到下一聚焦窗口或根页。

Knead 的等价规则应该是：

- 同一个 product 默认只打开一个 Use window。
- Adjust 可以是同 product 的独立窗口，或同窗口 mode，必须显式。
- Draft Creator 是独立窗口，不和正式 App 混。
- Preview 可以嵌在 Product window，非必要不单独开。

#### PostHog：OS mode 和 boring mode 并存

PostHog 有 `siteSettings.experience = posthog | boring`，并在 mobile/website mode 下改变窗口渲染方式。

Knead 也需要：

- Desktop mode：桌面、图标、窗口。
- Simple mode：移动端或低性能环境下，用普通列表/单窗口。

这不是退路，而是可访问性、移动端和调试必需品。

#### PostHog：桌面图标位置持久化并校验

PostHog `Desktop` 使用 `desktop-icon-positions` 存 icon 坐标，并在加载时验证是否越界；无效则重排。

Knead 可以采用同样策略：

- Phase 1 先自动布局。
- Phase 2 持久化图标位置。
- 每次 viewport 变化校验越界，避免图标跑出屏幕。

#### daedalOS：完整 OS 的能力边界

daedalOS 依赖和能力显示它是完整 OS：`react-rnd`、`browserfs`、`idb`、`monaco-editor`、`xterm`、`fflate`。这说明完整桌面平台会迅速扩张到文件系统、终端、编辑器、压缩、上传、模拟器等。

Knead 第一阶段必须拒绝：

- 通用文件系统。
- 通用文件打开方式。
- 右键菜单生态。
- 终端 App。
- 通用编辑器 App。

这些不是不好，而是会把“造 AI 产品”主线打散。

#### Puter：平台化需要强分层

Puter 后端文档强调 Controller -> Driver -> Service -> Store -> Client 分层。它的源码目录也分为 `backend`、`gui`、`puter-js`、`dev-center`、`worker` 等。

对 Knead 的启发：

- AI Computer 一旦进入创建/发布/运行时，就不能靠一个前端文件承载全部。
- Product registry、draft、runtime、window、desktop state 必须有边界。
- 如果以后做 App Store 或多人同步，才考虑更重的平台分层。

#### OS.js：应用 API 比视觉更重要

OS.js 定位是 web desktop platform with window manager, application APIs, GUI toolkit, filesystem abstractions。

Knead 不需要通用 GUI toolkit，但需要一组窄的 Product App API：

- 打开当前 App。
- 打开调整模式。
- 读/写产品状态。
- 请求 AI。
- 刷新预览。
- 发布草稿。
- 回退版本。

这组 API 应围绕 AI 产品生命周期设计，不围绕传统 OS 设计。

### 2.7 AI 造应用 / Artifacts 类产品

这一类产品回答“怎么造”，Web Desktop / Product OS 类产品回答“造出来的东西住在哪里”。Knead 的机会在交叉处：用户用 AI 造产品，产品又长期住在一个 AI Computer 里。

#### Lovable

来源：

- <https://docs.lovable.dev/introduction/welcome>
- <https://lovable.dev/blog>
- <https://lovable.dev/guides/best-ai-app-builders>

公开定位：

- 全栈 AI development platform。
- 用户用自然语言构建、迭代、部署 Web 应用。
- 强调 real code、security、governance、deployment。
- 近期方向不只造 App，也扩展到分析数据、创建/编辑文件、生成 business docs，把表格等材料转成可工作的应用。

适合我们学习的点：

- “一句话 -> 可用应用”必须有可见的生成过程和可继续迭代的上下文。
- 安全、真实代码、发布治理是产品化路径的一部分。
- 用户需要看到项目不是临时回答，而是一个可继续维护的对象。

不适合照搬的点：

- Lovable 更像 app builder / software engineer。Knead 对用户不应该暴露开发者 builder 心智。
- Knead 的产品可以是 chat-only、workspace、full canvas，不应该默认都变成外部 Web App。

#### Bolt / StackBlitz

来源：

- <https://bolt.new>
- <https://github.com/stackblitz/bolt.new>
- <https://support.bolt.new/building/intro-bolt>

公开定位：

- AI-powered builder for websites, web apps, mobile apps。
- Prompt、run、edit、deploy full-stack apps directly from browser。
- 开源代码库强调 WebContainers：在浏览器里运行项目。

适合我们学习的点：

- 浏览器内完整生成/运行/预览的即时反馈很重要。
- 文件树、preview、terminal、package install 这些是开发者路径的强能力。
- Prompt 到可运行产物的状态应该清楚：building、running、error、deployed。

不适合照搬的点：

- Bolt 的主场是代码项目；Knead 的主场是 AI 产品。
- Knead 第一版不应该给普通用户终端、package、通用文件树，这会把“造 AI 产品”变成“写软件项目”。

#### Replit Agent

来源：

- <https://docs.replit.com/references/agent/overview>
- <https://replit.com/agent4>
- <https://docs.replit.com/learn/effective-prompting>

公开定位：

- Agent 可以构建 web apps、mobile apps、dashboards、AI tools、visual prototypes、files/documents。
- Agent 4 强调 Design Canvas、并行任务、task-based workflows、协作。
- 官方 prompting 文档强调先 plan，再分阶段 build。

适合我们学习的点：

- “Agent 正在做什么”要可见，尤其是多步骤任务。
- Design Canvas / preview 先探索再应用，是调整产品 UI 的好模式。
- 大任务拆成 task，让用户看到进度和中间状态。

不适合照搬的点：

- Replit 是开发环境，用户默认接受项目、代码、部署、任务队列。
- Knead 要隐藏内部开发细节，只暴露“App 正在准备 / 可以打开 / 可以调整”。

#### v0 / Vercel

来源：

- <https://v0.app>
- <https://vercel.com/blog/announcing-v0-generative-ui>
- <https://vercel.com/blog/build-your-own-ai-app-builder-with-the-v0-platform-api>
- <https://ai-sdk.dev/docs/introduction>

公开定位：

- v0 从 Generative UI 发展到生成 working applications。
- 支持发布 live websites、同步 repo、GitHub push。
- v0 Platform API 允许开发者把 text-to-app 能力接入自己的产品。

适合我们学习的点：

- 生成 UI 不等于最终产品，用户需要 publish / sync / handoff。
- 组件/应用生成适合被封装成平台能力，而不是散在前端临时代码里。
- 对 Knead 来说，“产品生成管线”未来应该有 API 化边界。

不适合照搬的点：

- v0 强项是前端/React/UI 生成和发布；Knead 更宽，包含 chat-only、PPT、互动游戏、研究、数据、角色。
- Knead 不应把所有产品都压成 React app 生成问题。

#### Claude Artifacts

来源：

- <https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them>

公开定位：

- Artifacts 让 Claude 在对话外的独立窗口中呈现 substantial standalone content。
- 可以把想法变成 shareable apps、tools、content、visualizations、experiences。
- 适合用户修改、继续构建、引用。

适合我们学习的点：

- 聊天旁边长出可操作对象，比把所有内容塞进聊天更自然。
- “独立窗口”是用户理解工作对象的关键。
- artifact 的可分享、可修改、可引用，是 AI 产品长期化的重要方向。

不适合照搬的点：

- Artifact 通常还是某次对话中的产物。Knead 的对象应该更长期，拥有产品身份、记忆、版本、任务历史。
- Knead 不是一个 artifact gallery，而是用户自己的 AI 产品电脑。

#### ChatGPT Canvas / blocks

来源：

- <https://help.openai.com/en/articles/9930697-what-is-the-canvas-feature-in-chatgpt-and-how-do-i-use-it>
- <https://openai.com/index/introducing-canvas/>
- <https://help.openai.com/en/articles/20001246-working-with-writing-blocks-and-code-blocks-in-chatgpt>

公开定位：

- Canvas 是与 ChatGPT 协作写作和编码的独立工作界面。
- 重点是编辑、修订、协作，而不只是聊天回答。
- OpenAI 近期也把写作块和代码块能力推进到 chat responses 内。

适合我们学习的点：

- 当任务需要修订，独立工作区比聊天更清楚。
- 用户需要直接编辑对象，并让 AI 基于对象继续协作。
- 版本恢复是工作区能力的一部分。

不适合照搬的点：

- Canvas 主要是一个当前任务对象。Knead 的主对象不是文档/代码块，而是 AI 产品。
- Knead 的桌面应该管理多个产品，而不是只管理单个工作区。

### 2.8 产品类别对比结论

| 类别 | 代表 | 主对象 | 我们学什么 | 我们避开什么 |
|---|---|---|---|---|
| Product OS / 网站桌面 | PostHog | 页面/内容入口 | 路由进窗口、桌面图标、OS/simple 双模式 | 复制画风、把产品做成官网导航 |
| 完整 Web Desktop | daedalOS、OS.js | 文件/应用/窗口 | window manager、持久化、app API | 通用文件系统、右键生态、终端/编辑器泛化 |
| Internet Computer | Puter | 云文件、应用、开发平台 | 分层、发布、应用平台心智 | 过早做 App Store/开发者平台 |
| AI App Builder | Lovable、Bolt、Replit、v0 | 代码项目/应用 | 生成过程、preview、publish、task progress | 暴露 builder/code/project 心智 |
| AI Workspace / Artifact | Claude Artifacts、ChatGPT Canvas | 当前任务产物 | 聊天外工作面、可编辑/可恢复对象 | 只做一次性 artifact，不做长期产品 |

Knead 的独特位置：

> 不是通用电脑，不是开发者 app builder，不是一次性 artifact，而是一台承载长期 AI 产品生命周期的 AI Computer。

## 3. 当前代码意图

### 3.1 后端已经具备 Product OS 内核雏形

`apps/webui/api/products.py` 是产品注册表和生命周期核心。

已具备：

- Built-in products：General AI、PPT Designer、AI Otome。
- `list_products()`：返回产品列表，并派生 `entry_generated`、`product_canvas_available`、`ui_status`。
- `create_product()`：创建正式产品，写入产品目录和 registry。
- `create_product_draft()`：创建未发布草稿 workspace。这个非常像“桌面中新建一个临时 App”。
- `publish_product_draft()`：把草稿发布成正式产品。
- `update_product()` / `delete_product()`：产品维护。
- `snapshot_product()` / `rollback_product()`：产品 UI 文件快照和回退。
- `product_file_status()` / `preview_product_file()`：预览和状态。

判断：

- 后端不是问题的起点。它已经承认 AI 产品是长期对象，不是单轮聊天。
- Desktop Shell 应该复用这些 API，而不是另建一套“desktop app”事实源。
- 缺口是草稿在前端还没有被空间化：用户创建时没看到“桌面上正在长出一个 App”。

### 3.2 `product_context.py` 已经把用/调边界建起来

`apps/webui/api/product_context.py` 通过 `product_scope` 区分：

- `product_init`：初始化产品。
- `product_builder`：调整产品本身。
- `product_usage`：正常使用产品。

并且推导两条线：

- build line：能编辑产品 workspace 和 product.json。
- use line：只使用产品能力，不能修改产品自身。

判断：

- 这正是 AI Computer 里“打开 App 使用”和“进入 App 设置/更新”的底层语义。
- UI 必须把这条边界变成明确状态，而不是继续让用户在聊天框里猜。

### 3.3 前端产品逻辑已经存在，但容器不对

关键文件：

- `apps/webui/static/product-store.js`
- `apps/webui/static/product-shell-runtime.js`
- `apps/webui/static/product-runtime.js`
- `apps/webui/static/messages.js`
- `apps/webui/static/ui.js`

已具备：

- 后端 product -> 前端 AI object adapter。
- built-in/custom product hydrate。
- `createProductFromPrompt()`：一句话创建草稿并启动 Creator 会话。
- `publishCreatorDraft()`：用户点击 Add to shelf 后发布草稿产品。
- `openAssistantHome()`：打开某个产品主页。
- `withCurrentProductContext()`：发消息时注入产品上下文。
- product iframe bridge：canvas 与宿主互发消息、存状态、请求 AI。
- product preview polling：生成/失败/ready 状态更新。

问题：

- `product-shell-runtime.js` 同时负责产品列表、创建、删除、会话归属、产品主页、task header、preview chip、布局状态、splitter。
- `product-runtime.js` 同时负责 scope、bridge、preview、初始化任务。
- `product-store.js` 同时包含 model、adapter、store、view、API action。
- 大量状态通过 `window.*`、裸全局变量和 DOM dataset 传播。
- 当前 UI 容器仍然是 chat shell，产品像“助手列表”，不是“桌面上的 App”。

判断：

- 代码意图是正确的：它一直在把 assistant 推向 product。
- 代码形态拖后腿：巨型全局脚本让新 shell 很难优雅接入。
- 正确策略不是全量重写，而是新增 Desktop 模块，让旧代码逐步退成兼容层。

### 3.4 当前 `desktop.html` 是方向验证，不是最终架构

当前新增的：

- `apps/webui/static/desktop.html`
- `apps/webui/static/desktop.css`
- `apps/webui/static/desktop-shell.js`

它已经从后台式布局改成：

- 顶部 system bar。
- 桌面图标。
- window layer。
- AI Computer 窗口。
- Dock。

但仍然只是第一阶段雏形：

- 只有一个 library window。
- 窗口不可拖拽/缩放/最小化。
- App 打开还是跳回旧 `/?assistant=...`。
- 创建和调整入口禁用。
- 没有草稿 App 空间化。
- 没有最近作品/文件/任务。

判断：

- 这个文件可以保留为实验入口。
- 但正式蓝图必须拆成 `desktop-apps.js`、`desktop-windows.js`、`desktop-creator.js`、`desktop-store.js`，不能让 `desktop-shell.js` 重演 `ui.js`。

### 3.5 当前代码证据表

| 能力 | 当前证据 | 判断 |
|---|---|---|
| 产品注册表 | `apps/webui/api/products.py:list_products/create_product/update_product/delete_product` | 已有后端事实源，Desktop 不应另建 registry |
| 草稿产品 | `create_product_draft()` 创建 `product_drafts/<id>`，`publish_product_draft()` 发布 | 天然对应 Draft App，前端需要空间化 |
| 产品预览 | `preview_product_file()` + `/api/products/<id>/preview` | 可嵌入 Product/Preview window |
| 版本回退 | `snapshot_product()` / `rollback_product()` | 对应 Adjust window 的恢复能力 |
| 用/调边界 | `product_context_from_request()` 推导 `product_usage/product_builder/product_init` | AI Computer 必须把这个边界做成可见状态 |
| 产品 App adapter | `product-store.js:_productToCustomAssistant` | 现在混在 store/view 中，应抽为 `product-adapter.js` |
| 创建入口 | `product-shell-runtime.js:createProductFromPrompt` | 复用，但 UI 表现要从“开 Creator 会话”变成“桌面出现草稿 App” |
| 发布入口 | `publishCreatorDraft` / Add to shelf | 复用，但要更新 desktop app registry |
| 产品打开 | `openAssistantHome(kind)` | 短期兼容，长期应由 Product window 接管 |
| 产品 bridge | `product-runtime.js` 的 iframe message/state/agent bridge | 可复用，但要从聊天页 runtime 中抽控制器 |
| 巨型文件风险 | `ui.js` 7961 行、`product-shell-runtime.js` 2263 行、`routes.py` 5656 行 | 新 Desktop 代码必须模块化，避免新巨型文件 |

### 3.6 当前代码的真实意图

从代码看，这个项目已经不是“给助手列表加产品名”。真实意图已经很明显：

- `products/<id>/product.json` 是长期产品定义。
- 产品有 workspace，不只是 prompt。
- 产品可以生成 UI，不只是回答。
- 产品有 versions，可以回退。
- 产品会绑定 session，有历史。
- 产品能区分 usage 和 builder。
- Chat-only 产品可以在合适时建议“升格”为独立产品。

所以 AI Computer 不是额外概念，而是把现有代码已经长出来的产品模型显性化。

### 3.7 迁移落点表

| 目标模块 | 现有代码锚点 | 迁移方式 |
|---|---|---|
| `desktop-apps.js` | `product-store.js:177 _productToCustomAssistant`、`product-store.js:372 hydrateProductsFromBackend`、`products.py:595 list_products` | 先新增独立标准化函数，把 product -> desktop app；旧 hydrate 继续保留 |
| `desktop-store.js` | 当前 `desktop-shell.js` 内 `state`；PostHog App Provider 的 windows 状态模式 | 管理 selected app、windows、zIndex、recent apps，禁止 DOM 逻辑 |
| `desktop-windows.js` | PostHog `Window.tsx` / `App.tsx`；当前 `desktop-shell.js` 的 library window class | 实现 open/focus/close/minimize/restore，窗口对象数据化 |
| `desktop-creator.js` | `product-shell-runtime.js:createProductFromPrompt`、`product-shell-runtime.js:publishCreatorDraft`、`products.py:create_product_draft`、`products.py:publish_product_draft` | 第一版通过兼容函数调用，第二版直接接 draft API 并渲染 Draft App |
| `desktop-runtime.js` | `product-shell-runtime.js:1374 openAssistantHome`、`product-runtime.js:70 currentAssistantProductContextForMessage`、`product-runtime.js:107 withCurrentProductContext` | 短期打开旧首页，长期在 Product window 中直接控制 use/adjust |
| `product-preview-controller.js` | `product-runtime.js:657 currentProductPreviewRuntimeState`、`product-runtime.js:675 refreshCurrentProductPreview`、`products.py:1369 product_file_status` | 抽 iframe 状态、polling、ready/failed/generating 文案 |
| `product-bridge-controller.js` | `product-runtime.js:180 _handleProductCanvasStateMessage`、`product-runtime.js:278 _sendProductCanvasAgentMessage` | 把 canvas bridge 从 chat shell DOM 中解耦 |
| `product-context-client.js` | `product_context.py:160 product_context_from_request`、`product_context.py:233 product_ephemeral_prompt` | 前端只负责明确传 scope/intention，后端继续做安全推导 |
| `desktop-routes` | `routes.py:2417 /api/products`、`routes.py:3035 /api/product-drafts/create`、`routes.py:3038 /api/product-drafts/publish`、`routes.py:3081 snapshot`、`routes.py:3092 rollback` | 短期不改后端；中期增加 `/computer` 正式入口并注入 CSRF |

迁移顺序原则：

1. 先新增 Desktop 专用模块，不移动旧函数。
2. 让新模块调用旧兼容函数，保证行为不坏。
3. 等新路径稳定，再把旧函数内部改为调用新模块。
4. 最后删除旧 DOM 逻辑和重复 adapter。

这能避免“一口气 TS 重写”带来的功能断裂。

## 4. Knead 应该怎么定义这个体验

### 4.1 命名

候选：

- Knead Computer
- AI Computer
- Product OS
- AI Product OS

建议产品内部称为 `AI Computer`，文档/架构层称为 `Product OS`。

原因：

- 用户语言里“电脑”更直觉。
- 工程语言里“OS”更适合表达 shell、window、app registry、runtime。
- 不要在 UI 上大面积说 Product OS，这会像概念包装。

### 4.2 核心对象

桌面上不应该只有 AI 产品，还应该逐步有四类对象：

| 对象 | 用户语言 | 数据来源 |
|---|---|---|
| AI App | 用户造出来或内置的 AI 产品 | `/api/products` |
| Draft App | 正在创建但未发布的产品 | `/api/product-drafts/*` |
| Work Item | 某个 App 的一次任务或最近工作 | product sessions |
| Output File | App 产出的 deck、文档、图片、数据 | workspace files / product preview |

第一阶段先只做 AI App；第二阶段接 Draft App；第三阶段再接 Work Item 和 Output File。

### 4.3 第一屏意图

第一屏不是解释产品，而是让用户感到：

- 我进入了一台 AI 电脑。
- 这里已经有一些 App。
- 我能打开 App 工作。
- 我能创建新的 App。
- App 会留在这里。

因此第一屏结构应是：

- 顶部 system bar：AI Computer、Apps、Create、Search、当前选中、时间。
- 桌面空间：主要 App 图标、最近工作、创建入口。
- 品牌世界区域：一个安静但有记忆点的中心视觉，不必是 PostHog 插画。
- Window layer：点击图标出现窗口。
- Dock：常用 App 和 AI Computer。

### 4.4 视觉方向

不要抄 PostHog 农场，也不要抄 macOS。

Knead 更合适的气质：

- 像一台安静、聪明、有生命的 AI 工作电脑。
- 不是游戏化乐园，也不是冷冰冰控制台。
- 背景可以有“桌面空间”感，但不要占据任务。
- 图标应该像产品实体，不像普通导航链接。
- 窗口要熟悉可信，打开后是工作工具，不是展示卡片。

设计约束：

- 桌面有个性，窗口里克制。
- 第一屏可以有世界观，工作窗口必须高密度、稳定、可扫读。
- 不使用内部词：manifest、sandbox、canvas、scope、version directory。
- 不做花哨 OS 功能：右键菜单、开始菜单、文件系统、窗口动画特技，都放后面。

## 5. 架构蓝图

### 5.1 分层

```
AI Computer Shell
  ├─ Desktop World
  │   ├─ wallpaper / spatial layout / desktop icons / dock
  │   └─ first-run / empty / loading / offline states
  ├─ Window Manager
  │   ├─ open / close / focus / minimize / restore
  │   ├─ position / size / z-index
  │   └─ route <-> window binding
  ├─ Product App Registry
  │   ├─ product -> app icon
  │   ├─ product -> launch config
  │   ├─ draft -> temporary app
  │   └─ session/output -> secondary desktop object
  ├─ Product Runtime Adapter
  │   ├─ open usage window
  │   ├─ open adjust window
  │   ├─ open preview window
  │   └─ bind product_scope/product_layout
  └─ Legacy Bridge
      ├─ openAssistantHome compatibility
      ├─ createProductFromPrompt compatibility
      └─ product preview bridge reuse
```

### 5.2 新模块

第一批模块：

- `desktop-shell.js`：只负责启动和组装。
- `desktop-store.js`：desktop state，选中对象、窗口数组、z-index、最近打开。
- `desktop-apps.js`：拉取 `/api/products`，标准化为 App 对象。
- `desktop-windows.js`：窗口打开、关闭、聚焦、持久化。
- `desktop-creator.js`：新建 App 草稿、显示临时图标、发布。
- `desktop-runtime.js`：把 App launch 映射到现有 product runtime。
- `desktop.css`：桌面和窗口样式。

第二批模块：

- `product-model.js`：从 `product-store.js` 抽纯逻辑。
- `product-adapter.js`：后端 product -> 前端 app/product view model。
- `product-session-assignment.js`：product 和 session 的绑定。
- `product-preview-controller.js`：从 `product-runtime.js` 抽 preview polling/iframe 状态。

### 5.3 窗口类型

| 窗口类型 | 用户看到 | 底层 |
|---|---|---|
| Library window | Applications / 全部 App | `/api/products` |
| Product window | 正常使用某个 App | `product_usage` |
| Adjust window | 调整当前 App | `product_builder` |
| Creator window | 新建 App | draft workspace + Creator session |
| Preview window | App 的工作界面 | `/api/products/<id>/preview` iframe |
| Work window | 最近一次任务 | product-bound session |

第一阶段只做 Library window 和 Product launch；第二阶段做 Creator window；第三阶段做 Adjust/Preview 统一窗口。

### 5.4 路由策略

短期：

- 保留 `/static/desktop.html` 作为实验入口。
- App 打开可以先跳到旧 `/?assistant=<kind>`，确保功能不丢。

中期：

- 增加正式 `/computer` 或 `/desktop` 服务端入口。
- 服务端注入 CSRF 和必要 boot config。
- 支持 URL 恢复桌面状态，比如 `/computer?app=ppt-designer`。

长期：

- 旧首页成为 AI Computer 的一个窗口或 fallback mode。
- 移动端默认进入 simplified mode，不强行模拟桌面。

### 5.5 状态持久化

需要持久化：

- 桌面图标位置。
- Dock pinned apps。
- 最近打开 App。
- Window position/size/minimized。
- 最近工作对象。

不要第一阶段就做同步后端。先用 localStorage，等模型稳定后再考虑 profile-level state。

### 5.6 产品生命周期映射

| 用户动作 | Desktop 表现 | 当前代码 |
|---|---|---|
| 打开 App | 桌面图标打开窗口 | `openAssistantHome(kind)`，后续替换为 product window |
| 创建 App | 出现临时图标，Creator 窗口打开 | `createProductFromPrompt()` + `/api/product-drafts/create` |
| 发布 App | 临时图标变正式 App | Add to shelf -> `publishCreatorDraft()` + hydrate |
| 使用 App | Product window 内对话或预览 | `product_usage` |
| 调整 App | Adjust window，明确切换状态 | `product_builder` |
| 预览 UI | 窗口中嵌 iframe | `/api/products/<id>/preview` |
| 回退版本 | Window toolbar 中的恢复动作 | `rollback_product()` |

### 5.7 最小窗口内核规格

第一版 `desktop-windows.js` 应该只实现这些，先不做完整 OS：

```js
{
  id: "window:ppt-designer:use",
  type: "product-use",
  productId: "ppt-designer",
  title: "PPT Designer",
  state: "open",
  zIndex: 12,
  position: { x: 120, y: 72 },
  size: { width: 920, height: 640 },
  previousPosition: null,
  previousSize: null
}
```

必需操作：

- `openWindow(config)`
- `focusWindow(id)`
- `closeWindow(id)`
- `minimizeWindow(id)`
- `restoreWindow(id)`
- `moveWindow(id, position)`
- `resizeWindow(id, size)`，可延后到 Phase 2 后半。

去重规则：

- `product-use:<productId>` 默认唯一。
- `product-adjust:<productId>` 默认唯一。
- `creator:<draftId>` 默认唯一。
- `preview:<productId>` 默认嵌入，不默认单独开。

持久化规则：

- Phase 1：不持久化窗口，只持久化最近选中 App。
- Phase 2：localStorage 持久化窗口位置/大小/最小化状态。
- Phase 3：草稿 App 需要从后端或 draft 目录恢复，不能只靠 localStorage。

### 5.8 Product App 对象规格

`desktop-apps.js` 不直接把后端 product 塞给 UI，应先标准化成 Desktop App：

```js
{
  id: "app:ppt-designer",
  productId: "ppt-designer",
  kind: "ppt",
  title: "PPT Designer",
  iconText: "P",
  description: "...",
  layout: "chat_left_canvas_right",
  status: "ready",
  source: "product",
  launch: {
    use: true,
    adjust: true,
    preview: true
  }
}
```

Draft App：

```js
{
  id: "draft:<draftId>",
  draftId: "<draftId>",
  title: "New App",
  status: "clarifying|working|ready",
  source: "draft",
  launch: {
    creator: true,
    publish: false
  }
}
```

这个规格能避免 UI 到处判断 snake_case/camelCase，也避免 `assistant/product/kind/id` 继续混杂。

### 5.9 和旧 runtime 的兼容策略

短期桥接：

- Desktop 读 `/api/products` 自己渲染 App。
- 打开 App 先调用旧 URL `/?assistant=<kind>`，保证真实功能可用。
- 创建 App 先复用 `createProductFromPrompt()`，但前端表现改为 Draft App。

中期桥接：

- 抽 `product-adapter.js` 后，旧 `product-store.js` 和新 `desktop-apps.js` 都调用同一 adapter。
- 抽 `product-preview-controller.js` 后，旧 chat shell 和新 Product window 共用 preview 状态。
- 抽 `product-session-assignment.js` 后，Desktop 可以打开最近工作，不需要读旧全局状态。

长期桥接：

- `openAssistantHome()` 退化为打开 AI Computer 中的 product-use window。
- 旧 chat shell 变成 fallback/simple mode。

## 6. 分阶段实施计划

### Phase 0：确认方向与研究沉淀

当前交付：

- 外部调研完成。
- 当前代码链路复查完成。
- 本蓝图写入 `docs/research/AI_COMPUTER_PRODUCT_OS_BLUEPRINT.md`。
- `PRODUCT_MODEL_CONTRACT.md` 的 Desktop 章节需要同步为 AI Computer 方向。

验收：

- 团队能看懂为什么是电脑，不是 dashboard。
- 团队能看懂哪些外部实现可学，哪些不能照搬。
- 下一步代码不再继续往 `ui.js` / `product-shell-runtime.js` 里堆。

### Phase 1：AI Computer 第一屏

目标：

- 第一眼像进入一台 AI 电脑。
- 不是管理后台，不是聊天列表。

TODO：

- 完善 `desktop.html/css/js`：
  - 桌面图标布局。
  - 顶部 system bar。
  - Dock。
  - Library window。
  - 选中 App 预览信息。
  - 双击 App 打开。
- 从 `desktop-shell.js` 拆出：
  - `desktop-apps.js`
  - `desktop-store.js`
  - `desktop-windows.js`
- 禁止继续扩大 `desktop-shell.js` 到 500 行以上。

验收：

- 打开 `/static/desktop.html`，用户第一眼理解这是 AI Computer。
- `/api/products` 的所有产品都有图标。
- 点击/双击/ Dock 打开动作可用。
- `node --check` 通过。
- 移动端有 simplified fallback。

### Phase 2：正式 Window Manager

目标：

- 从静态窗口变成真正窗口系统。

TODO：

- 实现窗口数组状态：
  - id、type、productId、title、position、size、zIndex、minimized。
- 实现 open/focus/close/minimize/restore。
- 用 pointer events 实现拖拽标题栏。
- 先不做复杂 resize，至少支持最大化和还原。
- localStorage 持久化窗口布局。
- Product launch 不再直接跳旧首页，而是在 Product window 中打开。

验收：

- 多个 App 可同时打开。
- 点击窗口会置顶。
- 刷新后能恢复最近窗口。
- 不出现重复打开同一产品造成状态混乱。

### Phase 3：Creator as New App

目标：

- 新建 App 像桌面长出一个临时 App。

TODO：

- `desktop-creator.js` 接 `/api/product-drafts/create`。
- 新建后桌面出现 Draft App 图标。
- Creator window 绑定 draft workspace。
- 草稿状态显示为“Draft / Preparing / Ready to add”。
- 发布后临时图标变正式 App。
- 发布失败或 not_ready 时保留草稿。

验收：

- 用户能从 AI Computer 完成一句话创建。
- 草稿不会伪装成正式 App。
- 刷新后能找回未发布草稿。
- UI 不出现 manifest、sandbox、builder 等词。

### Phase 4：Use / Adjust 双模式窗口

目标：

- 用户能清楚区分使用 App 和调整 App。

TODO：

- Product window 默认是 Use。
- Window toolbar 提供 Adjust。
- Adjust 打开独立窗口或同窗口 mode switch。
- Use 发送 `product_usage`。
- Adjust 发送 `product_builder`。
- 对 `canvas_full` 产品，使用时隐藏宿主输入，调整时显示调整输入。
- 调整产生预览、应用、回退入口。

验收：

- 用户知道自己是在用 App 还是调 App。
- product_usage 不会改 product.json 或产品 UI 文件。
- product_builder 能改产品定义和界面。
- 回退路径清晰可见。

### Phase 5：Product outputs as files

目标：

- 产品产物成为 AI Computer 里的“文件/作品”，而不是只在聊天历史里。

TODO：

- 从 product sessions/workspace files 抽最近作品。
- 桌面增加 Recent Work 或 Documents 窗口。
- PPT 输出、图片、文档、数据表有文件化入口。
- 文件打开仍然回到对应 App。

验收：

- 用户能从电脑里找回某个 App 产出的东西。
- App、任务、产物的层级清楚。

### Phase 6：旧 UI 收敛

目标：

- AI Computer 成为主入口，旧 chat shell 退为兼容窗口或 fallback。

TODO：

- 增加正式 `/computer`。
- 旧首页提供切换入口。
- 抽 `product-model.js` 和 `product-adapter.js`。
- 拆 `product-shell-runtime.js` 里的产品列表/创建/会话归属/preview 状态。
- 拆 `product-runtime.js` 里的 bridge 和 preview controller。
- 给 desktop modules 加基础测试。

验收：

- 新产品功能优先进入 Desktop 模块。
- 旧巨型文件行数开始下降。
- AI Computer 不依赖隐式全局顺序才能启动。

## 7. 风险和取舍

### 7.1 最大风险

做成假电脑。

规避：

- 每个图标必须对应真实产品、草稿、任务或产物。
- 每个窗口必须承载真实工作流。
- 装饰性 OS 功能全部延后。

### 7.2 第二风险

做成通用 OS，范围失控。

规避：

- 不做通用文件管理器。
- 不做 App Store 市场。
- 不做右键菜单生态。
- 不做开发者 SDK。
- 第一版只服务 AI 产品生命周期。

### 7.3 第三风险

继续堆前端巨型文件。

规避：

- `desktop-shell.js` 只负责启动和组装。
- 产品标准化放 `desktop-apps.js`。
- 窗口状态放 `desktop-windows.js`。
- 创建流程放 `desktop-creator.js`。
- 旧 runtime 只通过 adapter 调用。

### 7.4 第四风险

视觉过于 PostHog 或 macOS。

规避：

- 学 PostHog 的结构，不学它的农场画风。
- 学 macOS 的可识别 affordance，不抄窗口皮肤。
- Knead 的视觉要服务“安静、聪明、有生命的 AI 工作电脑”。

## 8. 下一步建议

立即做：

1. 把当前 `desktop-shell.js` 拆成 `desktop-apps.js`、`desktop-store.js`、`desktop-windows.js`。
2. 完善第一屏：桌面图标、窗口、dock、system bar、创建入口的视觉存在。
3. 先让 App window 在桌面内打开预览/使用入口，减少跳回旧首页。
4. 给 AI Computer 增加最小冒烟验证：产品 API 可读、图标渲染、窗口打开、移动端 fallback。

不要立刻做：

- 不要全量 TypeScript 重写。
- 不要接复杂文件系统。
- 不要做通用应用市场。
- 不要先做高级窗口 resize。
- 不要把旧首页全部迁移。

成功标准：

- 用户第一眼说“这是我的 AI 电脑”，不是“这是一个产品列表”。
- 用户能自然理解“我创建的 AI 产品会住在这里”。
- 工程上新能力有明确模块落点，不再扩大巨型文件。

## 9. 决策矩阵

| 决策 | 选择 | 不选什么 | 原因 | 验收证据 |
|---|---|---|---|---|
| 主隐喻 | AI Computer | 普通 dashboard、助手列表、纯聊天页 | 用户持续造很多 AI 产品，电脑能自然承载 App、文件、窗口、最近工作 | 第一屏不用解释也能看出有 App、窗口、创建入口 |
| 核心对象 | AI App = Product | Page、Artifact、Code Project | 当前代码事实源是 `products.py` 和 `product.json`，不是页面或代码项目 | `/api/products` 能直接驱动桌面图标 |
| 创建体验 | Draft App | 直接发布、纯聊天草稿、开发者项目 | 草稿已经有 workspace 和 publish API，应表现成“正在长出来的 App” | 创建后出现临时 App，发布后变正式 App |
| 使用/调整 | 两种可见模式 | 后端正则猜 scope、一个万能聊天框 | `product_usage` 和 `product_builder` 已是关键安全边界 | UI 明确显示 Use / Adjust，payload 带显式 scope |
| 技术路线 | 并行新 shell + 兼容旧 runtime | 一次性重写、继续塞旧 `ui.js` | 旧功能复杂且可用，重写风险高；但巨型文件不能继续扩张 | 新 Desktop 模块增长，旧巨型文件不再新增桌面逻辑 |
| 窗口系统 | 最小 window manager | 完整 OS.js / daedalOS 级平台 | 当前只需要 AI 产品生命周期，不需要通用 OS | 支持 open/focus/close/minimize，暂不做右键/文件系统 |
| 路由 | 短期 `/static/desktop.html`，中期 `/computer` | 立刻替换首页 | 需要先验证方向，再接 CSRF、boot config、mobile fallback | 实验入口可用，正式入口有服务端注入计划 |
| 视觉 | 自有 AI 工作电脑气质 | 复制 PostHog 农场、macOS clone | 学结构，不抄画风；Knead 需要安静、聪明、有生命感 | 截图不像 PostHog/macOS，也不像 SaaS 管理台 |
| TypeScript | 新模块可逐步 TS 化 | 全量 TS 重写 | 当前依赖全局 defer 脚本，直接 TS 重写会打断加载顺序 | 新模块有清晰接口后再转换 |
| 输出对象 | 后续文件/作品化 | 第一版通用文件管理器 | 产品产物应可找回，但文件系统会扩大范围 | Phase 5 才接 Recent Work / Files |

## 10. 实施验收清单

### 10.1 Phase 1 验收

- `/static/desktop.html` 能加载。
- `/api/products` 返回的每个产品都能显示为 App 图标。
- App 图标至少支持 click 选中、double click 打开。
- Library window 可打开/关闭，窗口状态不靠散落 DOM class 维护。
- Dock 可显示常用 App 和 AI Computer。
- `desktop-shell.js` 拆到小于 200 行，只负责 boot/assembly。
- 新增 `desktop-apps.js`、`desktop-store.js`、`desktop-windows.js`。
- `node --check` 覆盖所有新增 desktop JS。
- 窄屏不强行模拟桌面，进入 single-column/simple layout。

### 10.2 Phase 2 验收

- 支持多个窗口同时存在。
- 点击窗口会置顶。
- 窗口可关闭、最小化、恢复。
- 同一个 product-use 窗口默认不重复打开。
- Window state 至少包含 id/type/productId/title/state/zIndex/position/size。
- localStorage 持久化最近窗口和位置，越界时自动重排。
- Product window 能在桌面内部打开，而不是只能跳旧首页。

### 10.3 Phase 3 验收

- New App 入口可创建 draft workspace。
- 草稿以 Draft App 图标出现。
- Creator window 绑定 draft workspace。
- publish 后草稿图标替换为正式 App。
- publish not_ready 时草稿保留，不伪装成正式 App。
- 刷新后能恢复未发布 draft。
- UI 不出现 manifest、sandbox、builder、scope。

### 10.4 Phase 4 验收

- Product window 默认 Use。
- Adjust 入口明显，且是产品级调整，不是普通聊天。
- Use 请求显式传 `product_scope=product_usage`。
- Adjust 请求显式传 `product_scope=product_builder`。
- `canvas_full` 产品使用时不出现竞争性宿主输入。
- 调整后有 preview/apply/restore 路径。
- product_usage 路径不能改 product.json 或产品 UI 文件。

### 10.5 Phase 5 验收

- 每个 App 能显示最近工作。
- 至少一种产物类型可作为文件/作品打开，比如 PPT 输出或图片。
- 文件/作品打开能回到所属 App。
- Work Item / Output File 不混成新的 Product。

### 10.6 Phase 6 验收

- 正式 `/computer` 或 `/desktop` 路由存在。
- 服务端入口注入 CSRF/boot config。
- 旧首页可以作为 fallback/simple mode。
- `product-store.js`、`product-runtime.js`、`product-shell-runtime.js` 至少各有一个责任块被抽出。
- 新增 desktop/product 模块有基础测试或静态验证。
- `ui.js`、`product-shell-runtime.js` 不再因为 AI Computer 继续增长。

## 11. 完成定义

这个方向“第一版成了”的定义：

- 用户进入后先看到 AI Computer，而不是聊天页或 dashboard。
- 已有 AI 产品都像 App 一样住在桌面里。
- 用户能打开 App、创建 App、看到草稿变正式 App 的过程。
- 用户能明确区分使用 App 和调整 App。
- 工程上 Desktop 有自己的小内核，不依赖继续堆旧全局脚本。

这个方向“不能算成了”的情况：

- 只是换背景或加 Dock，但 App 打开仍然只是普通跳转。
- 继续把所有逻辑塞进 `desktop-shell.js`。
- 创建产品没有 Draft App 心智。
- 调整产品仍然靠聊天内容猜。
- UI 看起来像 PostHog 或 macOS，但没有 Knead 自己的产品逻辑。

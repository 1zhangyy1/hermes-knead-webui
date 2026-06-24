# Hermes WebUI 复用评估

日期：2026-05-18

> 2026-05-23 更新：本文对 Hermes WebUI 的技术复用判断仍有参考价值，但其中“左侧导航增加一级工作台 / Workbench 作为显性 feature”的产品结论需要按当前准则收敛。当前产品定义以 [PRODUCT.md](../../PRODUCT.md) 和 [PRODUCT_UIUX.md](../../PRODUCT_UIUX.md) 为准：Knead 是 AI product shelf，用户先选择或创建 AI product，再从 Chat 开始，让产品在需要结构时长出自己的 product canvas。

## 1. 本次验证对象

### 官方 Hermes Dashboard

路径：

```text
vendor/hermes-agent/web
```

本地地址：

```text
http://127.0.0.1:9119/
```

截图：

```text
prototypes/official-hermes-dashboard.png
```

### nesquena/hermes-webui

路径：

```text
vendor/hermes-webui
```

来源：

```text
https://github.com/nesquena/hermes-webui.git
```

当前 commit：

```text
e6be01c
```

本地地址：

```text
http://127.0.0.1:8788/
```

截图：

```text
prototypes/nesquena-hermes-webui-home.png
prototypes/nesquena-hermes-webui-after-api-chat.png
```

## 2. 启动方式

标准 git clone 使用代理完成：

```sh
export https_proxy=http://127.0.0.1:6152
export http_proxy=http://127.0.0.1:6152
export all_proxy=socks5://127.0.0.1:6153
git clone --depth 1 https://github.com/nesquena/hermes-webui.git vendor/hermes-webui
```

本地隔离启动命令：

```sh
cd $REPO_ROOT

HERMES_HOME=$PWD/.hermes-home \
HERMES_WEBUI_AGENT_DIR=$PWD/vendor/hermes-agent \
HERMES_WEBUI_PYTHON=$PWD/vendor/hermes-agent/.venv/bin/python \
HERMES_WEBUI_STATE_DIR=$PWD/.hermes-home/webui-reference \
HERMES_WEBUI_DEFAULT_WORKSPACE=$PWD \
HERMES_WEBUI_SKIP_ONBOARDING=1 \
HERMES_WEBUI_PORT=8788 \
HERMES_WEBUI_HOST=127.0.0.1 \
HERMES_WEBUI_FOREGROUND=1 \
vendor/hermes-agent/.venv/bin/python vendor/hermes-webui/bootstrap.py \
  --host 127.0.0.1 \
  --foreground \
  --no-browser \
  8788
```

Health check:

```text
GET http://127.0.0.1:8788/health
```

结果：

```json
{
  "status": "ok",
  "sessions": 0,
  "active_streams": 0
}
```

## 3. 真实对话验证

通过 WebUI API 创建 session：

```text
POST /api/session/new
```

然后启动 chat：

```text
POST /api/chat/start
GET  /api/chat/stream?stream_id=...
```

验证结果：

```text
User: 用中文回复一句：Hermes WebUI 已连接。
Assistant: Hermes WebUI 已连接。
```

模型：

```text
provider: openrouter
model: anthropic/claude-sonnet-4-6
```

说明：

> nesquena/hermes-webui 已成功使用项目隔离 `.hermes-home` 和 `vendor/hermes-agent`，不是静态 UI。

## 4. 产品判断

### 官方 Dashboard

优点：

- 官方随 Hermes Agent 分发。
- MIT。
- 和 runtime、config、sessions、skills、cron、plugins、profiles、keys 集成最可靠。
- 适合做管理后台和系统能力页。

问题：

- 视觉和交互更像管理后台。
- Chat 是 Dashboard/TUI 取向，不像用户每天打开的轻量 Agent 产品。
- 不适合作为我们的主用户界面。

结论：

> 官方 Dashboard 作为 Hermes 系统管理层复用，不作为主 Agent Shell。

### nesquena/hermes-webui

优点：

- MIT。
- 三栏 Agent UI：左会话/导航，中间 chat，右 workspace/files。
- 无构建步骤，Python + vanilla JS，适合 Agent 直接修改。
- 已有 sessions、workspace file browser、tasks/cron、skills、logs、models、profiles、control center。
- 真实连接 Hermes Agent，SSE streaming 可用。
- 比当前自建 React 壳更接近可日用 Agent。

问题：

- 非官方 Nous 项目。
- 前端是 vanilla JS，不是我们当前 React/Vite 栈。
- 源码体量不小：`static/*.js` 约 4.5 万行。
- 直接 fork 会继承它自己的产品心智，工作台 feature 需要嵌进去，而不是另起炉灶。

结论：

> 最适合作为主用户侧 Agent Shell 的候选底座。建议进入 fork/patch 实验。

## 5. 对我们产品的启发

我们的产品不应该重写 Hermes 的基础 UI 能力，而应该在成熟 Agent UI 中增加差异化：

```text
Agent Chat
  + sessions
  + workspace files
  + skills
  + automation
  + model/profile controls
  + our Workbench feature
```

工作台 feature 应插入两个位置：

1. 左侧导航增加一级 `工作台` 区块。
2. 中间 chat 流中增加 `建议改造当前任务` 卡片。

第一版不要再维护复杂的 `AI Space Platform` 独立壳。

更合理路线：

```text
fork nesquena/hermes-webui
  -> 换品牌与浅色/简洁主题
  -> 加左侧 Workbench 区块
  -> 加 WorkbenchProposalCard
  -> 加 PPT Workbench 预览页
  -> 接 Apply / Rollback
```

官方 Dashboard 继续作为系统管理入口：

```text
System / Runtime / Admin
  -> official hermes-agent/web
```

用户日常入口：

```text
Task / Chat / Workbench
  -> nesquena/hermes-webui fork
```

## 6. 下一步

建议下一步不是继续当前 React 壳，而是在 `vendor/hermes-webui` 基础上做一个实验 patch：

1. 新建 `apps/agent-shell` 或直接复制 `vendor/hermes-webui` 为 `apps/agent-shell`.
2. 保留 Python server + vanilla JS 结构。
3. 修改 `static/index.html`：
   - 左侧加入 `工作台` 面板。
   - 将 `Spaces` 文案替换为 `Workbenches` / `工作台`。
4. 修改 `static/messages.js`：
   - 在用户输入 PPT 相关任务后插入 WorkbenchProposalCard。
5. 新增 API：
   - `GET /api/workbenches`
   - `POST /api/workbenches/propose`
   - `POST /api/workbenches/apply`
   - `POST /api/workbenches/rollback`
6. 第一版 workbench 状态存在：
   - `.hermes-home/webui-reference/workbenches.json`
7. PPT Workbench 可以先是静态预览页，不急着真的生成代码。

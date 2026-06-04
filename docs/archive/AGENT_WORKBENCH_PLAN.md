# Next AI: Agent + Workbench 产品与实施计划

日期：2026-05-18

> 2026-05-23 更新：本文早期把 `Agent` 作为产品主语，把 `工作台` 作为一级 feature。当前认知已调整，执行以 [当前产品认知：自进化工作台](docs/PRODUCT_DIRECTION_CURRENT.md) 为准：**默认入口是新对话，普通对话就是空工作台；专属工作台从对话任务中沉淀出来。**

## 1. 当前定稿心智

不要从 `Space` 开始讲，也不要从“新建工作台”开始讲。外部产品语言改成：

> 一个极简的 AI Chat 工作台。用户从新对话开始做事；任务变复杂时，工作台内部长出适合当前任务的界面；常用做法可以保存成专属工作台，并继续自我改造。

核心顺序：

```text
新对话
  -> 普通对话工作台
  -> 用户让 AI 做一件事
  -> 工作台内部出现材料、结果和临时任务界面
  -> 用户在 Chat 里继续指挥 AI
  -> 任务流程值得复用时，保存为专属工作台
  -> 专属工作台后续提出改造建议
```

外部叫法：

- `新对话`
- `普通对话工作台`
- `工作台`
- `任务`
- `改造当前任务`
- `保存为工作台`
- `预览 / 应用 / 回滚`

内部仍然可以叫：

- `space`
- `manifest`
- `generated app`
- `patch`
- `version`
- `sandbox`

但这些不要先暴露给用户。

## 2. 产品结构

推荐第一版主界面：

```text
Next AI
├─ 新对话
├─ 搜索
├─ 工作台
│  ├─ PPT 工作台
│  └─ 研究工作台
├─ 历史
└─ 设置
```

原则：

1. 第一眼必须是极简新对话，而不是工作台平台。
2. `新对话` 是第一入口，不能改成 `新建工作台`。
3. 普通对话就是默认空工作台。
4. 中间默认是 Chat 和输入框；右侧可以有材料和结果。
5. 工作台建议以对话卡片出现，且只能在用户已经开始做事之后出现。
6. 专属工作台不能替代 Chat。Chat 是工作台里的控制台，必须始终在场。

## 3. 原型图

当前原型文件：

```text
prototypes/agent-workbench-prototype-board.svg
prototypes/sidebar-structure-options.svg
prototypes/recommended-agent-workbench-screen.svg
```

当前推荐方向是：

```text
新对话 / 普通对话工作台 + 任务中长出界面 + 保存为专属工作台
```

早期 `sidebar-structure-options.svg` 的“一级工作台”方案不再作为第一版依据。

自我批评：

- 如果把工作台放太靠前，产品会变成“工作台市场”，用户无法理解第一步要做什么。
- 如果 Chat 消失，专属界面会退化成传统 SaaS 工具。
- 第一版最重要的是让用户感到：打开后就能开始对话做事，材料和结果自然出现。

## 4. 可复用项目结论

### 4.1 Hermes Agent 官方 Web Dashboard

来源：[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)

当前可靠性最高。仓库自带 `web/` 和 `ui-tui/`：

```text
vendor/hermes-agent/web
vendor/hermes-agent/ui-tui
```

适合复用：

- Hermes runtime 管理
- sessions
- logs
- analytics
- cron
- skills
- plugins
- profiles
- config
- keys
- dashboard API
- embedded TUI chat

不适合作为唯一用户主界面：

- 更像管理后台 + TUI 容器。
- Chat 通过 xterm 嵌 TUI，产品感不如现代聊天界面。
- 我们的工作台生成/预览/应用体验需要自己做。

结论：

> 作为 runtime/admin/settings 底座复用，不直接作为最终主界面。

### 4.2 nesquena/hermes-webui

来源：[nesquena/hermes-webui](https://github.com/nesquena/hermes-webui)

当前最适合研究或 fork 成用户侧 Agent UI：

- MIT
- stars 高
- 更新活跃
- Python + vanilla JS
- 无构建步骤
- 三栏布局：左 sessions/nav，中 chat，右 workspace file browser
- 强调接近 Hermes CLI parity

适合复用：

- 现代 Hermes WebUI 的主交互骨架
- sessions / task list
- chat stream
- workspace file browser
- profile/model/workspace controls
- control center 思路

风险：

- 非官方 Nous 项目。
- vanilla JS 不是我们当前 React/Vite 栈。
- 直接 fork 后要评估与官方 Hermes 版本的兼容成本。

结论：

> 最值得认真研究。可以作为第一版 UI 的主要参考，甚至可以先 fork 做实验分支。

### 4.3 EKKOLearnAI/hermes-web-ui

来源：[EKKOLearnAI/hermes-web-ui](https://github.com/EKKOLearnAI/hermes-web-ui)

功能很多，但许可证是 BSL-1.1。

优点：

- Vue / TypeScript / Koa / Socket.IO
- chat sessions
- platform channels
- analytics
- scheduled jobs
- model management
- profiles
- file browser
- group chat
- logs
- web terminal

风险：

- BSL-1.1，商业或嵌入产品使用需要特别谨慎。
- 不能作为我们开源产品的直接代码底座。

结论：

> 只研究产品能力，不直接复用代码。

### 4.4 lotsoftick/hermes_client

来源：[lotsoftick/hermes_client](https://github.com/lotsoftick/hermes_client)

优点：

- MIT
- profile = agent 的抽象不错
- CLI-driven streaming chat，不依赖 gateway
- 支持 cron / skills / plugins
- PWA

风险：

- 项目规模小，生态和维护确定性不足。

结论：

> 参考 profile/agent 抽象，不作为主底座。

## 5. MVP 范围

第一版只做一个闭环：

```text
普通 Agent 聊天
  -> 用户要求做 PPT
  -> Agent 产出大纲/初稿
  -> 对话中出现“建议改造当前任务”
  -> 用户点击“预览 PPT 工作台”
  -> 打开临时工作台预览
  -> 用户点击“应用”
  -> 左侧工作台里出现 PPT 工作台
  -> 用户可回滚
```

明确不做：

- 工作台市场
- 多用户协作
- 商业化
- 大量预置场景
- 真正无限制自我修改
- 复杂权限系统

## 6. 技术路径

### Phase 0: 复用路线验证

目标：决定“fork nesquena”还是“继续自建 React 壳”。

状态：已完成初步验证。结论是：

> 用户侧主壳优先基于 `nesquena/hermes-webui` 做实验 fork；官方 `vendor/hermes-agent/web` 作为 runtime/admin/settings 管理层保留；当前 React host-shell 暂时不作为第一版主路线。

验证记录见：

```text
docs/HERMES_WEBUI_EVAL.md
docs/WORKBENCH_MVP_EXECUTION_PLAN.md
prototypes/nesquena-hermes-webui-home.png
prototypes/nesquena-hermes-webui-after-api-chat.png
prototypes/official-hermes-dashboard.png
```

任务：

1. 已下载 `nesquena/hermes-webui` 到 `vendor/`，使用 git clone，当前 commit `e6be01c`。
2. 已本地跑起来，地址 `http://127.0.0.1:8788/`，连接当前项目隔离 `.hermes-home`。
3. 已对比官方 `vendor/hermes-agent/web` 与 `nesquena/hermes-webui`：
   - 聊天体验
   - sessions
   - workspace 文件
   - skills/cron
   - model/profile controls
   - 和我们的工作台 feature 的插入成本
4. 已形成复用决策：
   - `fork nesquena`：作为用户日常 Agent Shell。
   - `基于官方 dashboard 改`：只作为系统管理层，不做主入口。
   - `当前 React 壳吸收两者设计`：降级为原型参考，不继续堆复杂度。

### Phase 1: Agent Shell

目标：先让产品像一个好用 Agent。

执行文档：

```text
docs/WORKBENCH_MVP_EXECUTION_PLAN.md
```

页面：

- 新任务
- 任务历史
- 工作台
- Skills
- Automation
- 设置

能力：

- Hermes 聊天可用
- 文件上传/引用
- 工具执行状态可见
- 模型/权限状态可见
- sessions 可恢复

### Phase 2: Workbench Proposal

目标：把我们的核心 feature 嵌入 Agent 流。

组件：

- `WorkbenchProposalCard`
- `WorkbenchPreview`
- `ApplyWorkbench`
- `RollbackWorkbench`

第一版规则可以先硬编码：

```text
如果当前任务包含 PPT / slide / deck / 融资 / 路演
  -> 展示 PPT 工作台建议卡
```

之后再接入真实 pattern detector。

### Phase 3: 代码级生成与预览

目标：让 AI 真的改应用，但先关在笼子里。

流程：

```text
Generate patch
  -> write to generated workbench dir
  -> pnpm check/build
  -> preview iframe
  -> user approve
  -> save snapshot
  -> apply
  -> rollback available
```

边界：

- AI 只能改 `workbenches/generated/*` 或 `spaces/generated/*`。
- Host shell 核心不允许自动修改。
- 每次应用前保存快照。
- build 不过不能应用。
- 用户数据与生成代码分离。

## 7. 第一周任务建议

### Day 1: 复用调研落地

- 下载并运行 `nesquena/hermes-webui`。
- 跑官方 Hermes Dashboard。
- 截图对比两者。
- 写复用决策。

### Day 2: 定主壳

- 如果选 nesquena：fork/拷贝为实验壳。
- 如果选自建：把当前 host-shell 重构成推荐原型。
- 保留 Hermes runtime 接入。

### Day 3: 工作台一级入口

- 左侧加入工作台区块。
- 工作台有状态：模板 / 建议中 / 已启用。
- 默认首页仍然是 Agent composer。

### Day 4: PPT 建议卡

- 在任务流中加入 `建议改造当前任务` 卡片。
- 支持预览/应用/忽略。
- 暂时用规则触发。

### Day 5: PPT 工作台预览

- 做一个可用的 PPT 工作台：
  - 大纲
  - slide canvas
  - speaker notes
  - Agent side panel
  - 回滚提示

### Day 6-7: 预览/应用/回滚闭环

- 应用后进入左侧工作台。
- local snapshot。
- rollback。
- 写 README 和演示脚本。

## 8. 关键判断

现在最重要的不是“AI Space 平台”，而是：

> 先做一个用户愿意每天打开的 Agent。

差异化也不是“它有很多工作台”，而是：

> 它会为了更好的结果，把高频任务沉淀成专属工作台。

第一版必须证明：

1. 普通 Agent 体验不差。
2. 工作台入口足够显眼。
3. 建议生成工作台的时机自然。
4. 应用工作台后，完成 PPT 这种任务真的更好。
5. 改坏了能回滚。

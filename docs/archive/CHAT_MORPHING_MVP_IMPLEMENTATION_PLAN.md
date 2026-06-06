# Chat 变形工作台 MVP 实施计划

日期：2026-05-31

本文是基于 `CHAT_MORPHING_WORKBENCH_MODEL.md` 的完整落地计划。目标不是先做一个庞大的工作台平台，而是先跑通一条最能说明产品心智的 demo：

```text
普通 Chat
  -> 用户发起 PPT 任务
  -> Chat 长出关键信息卡
  -> 页面进入 PPT 生成模式
  -> 生成后进入 PPT 编辑器形态
  -> 用户让系统记住工作方式 / 调整页面形态
  -> 下次 PPT 任务自动更好用
```

## 1. 总目标

第一版要证明：

> Next AI 是一个会变形的 Chat。用户从聊天开始做事，Chat 会随着任务阶段长出更合适的界面；当用户表达“以后都这样”时，系统能记住工作方式，并在下次自动进入更适合的形态。

不要证明：

- AI 能任意生成应用。
- AI 能直接改 Host Core。
- 工作台市场有多丰富。
- 所有任务类型都支持。

## 2. MVP 范围

只做 AI PPT 一条线。

### 必须支持

- 普通 Chat。
- PPT 任务识别。
- PPT 关键信息卡。
- PPT 生成模式。
- PPT 编辑器形态。
- 通过 Chat 修改当前 PPT。
- 通过 Chat 记住默认工作方式。
- 下次 PPT 任务自动应用默认工作方式。
- 撤销最近一次默认设置。

### 暂不支持

- 真正完整 PPTX 导出。
- 任意 UI 代码生成。
- 多工作台复杂版本 diff。
- 多用户协作。
- 复杂权限系统。
- 工作台市场。
- 自动安装依赖。

## 3. 产品主链路

### 3.1 第一次使用

```text
1. 用户打开 Next AI。
2. 默认看到普通 Chat。
3. 用户输入：做一个介绍 Codex 的 PPT。
4. 系统识别为 PPT 任务。
5. Chat 中出现“关键信息卡”。
6. 用户确认或补充信息。
7. 页面变成 PPT 生成模式。
8. AI 生成大纲和页面结构。
9. 页面变成 PPT 编辑器形态。
10. 用户继续用 Chat 控制 PPT。
```

### 3.2 记住工作方式

```text
1. 用户说：以后每页都带讲稿，文案短一点。
2. AI 先执行当前任务修改。
3. AI 询问：要不要把这变成 PPT 默认方式？
4. 用户点击“以后默认这样”。
5. 系统保存默认设置。
6. Chat 显示：已记住，可撤销。
```

### 3.3 下次使用

```text
1. 用户进入 PPT 工作台，或再次发起 PPT 任务。
2. 系统读取默认工作方式。
3. Chat 不再从空白开始，而是问：按你的默认方式来，我们先确认主题、受众和页数。
4. PPT 形态自动包含：短文案、讲稿、默认信息收集流程。
```

## 4. 信息架构

### 4.1 母体应用

母体应用保持稳定，负责：

- 新对话。
- 会话列表。
- 工作台列表。
- 文件和产物。
- 设置。
- 撤销 / 恢复。

第一版不要让 AI 改母体。

### 4.2 Chat

Chat 是入口，也是控制台。

不同阶段的 Chat：

```text
普通 Chat
PPT 信息收集 Chat
PPT 生成 Chat
PPT 编辑器里的 AI 控制台
```

### 4.3 工作台

工作台是保存下来的 Chat 任务形态。

PPT 工作台保存：

- 默认任务类型：ppt。
- 默认提问字段。
- 默认输出结构。
- 用户偏好。
- 页面形态。
- 最近产物。

## 5. 状态模型

### 5.1 Session State

每个会话需要绑定一个任务状态：

```json
{
  "sessionId": "session-xxx",
  "task": {
    "type": "ppt",
    "phase": "collecting_info",
    "surface": "ppt_info_card",
    "subject": "Codex 介绍",
    "scenario": "技术产品介绍",
    "pageCount": "auto",
    "ratio": "16:9",
    "language": "简体中文",
    "style": null,
    "slides": [],
    "selectedSlide": null
  }
}
```

### 5.2 Task Phase

第一版 PPT 状态机：

```text
idle
  -> collecting_info
  -> choosing_style
  -> outlining
  -> generating_slides
  -> editing
```

含义：

- `idle`：普通 Chat。
- `collecting_info`：收集主题、受众、页数等。
- `choosing_style`：选择风格模板。
- `outlining`：生成和确认大纲。
- `generating_slides`：生成页面。
- `editing`：进入 PPT 编辑器形态。

### 5.3 Surface

页面形态由 `surface` 控制：

```text
chat_default
ppt_info_card
ppt_style_picker
ppt_outline_review
ppt_generating
ppt_editor
```

UI 根据 `surface` 渲染，而不是散落在聊天文本里。

### 5.4 Workbench Defaults

PPT 工作台默认值：

```json
{
  "id": "ppt-workbench",
  "name": "PPT 工作台",
  "taskType": "ppt",
  "defaults": {
    "askFirst": ["主题", "受众", "页数"],
    "ratio": "16:9",
    "language": "简体中文",
    "includeSpeakerNotes": true,
    "copyStyle": "短文案",
    "layout": "canvas_thumbnails_notes"
  },
  "updatedAt": "2026-05-31T00:00:00+08:00"
}
```

### 5.5 Preference Change

每次“以后默认这样”都记录为一个 change：

```json
{
  "id": "change-xxx",
  "workbenchId": "ppt-workbench",
  "summary": "PPT 默认短文案并包含讲稿",
  "patch": {
    "includeSpeakerNotes": true,
    "copyStyle": "短文案"
  },
  "createdFromSessionId": "session-xxx",
  "createdAt": "2026-05-31T00:00:00+08:00",
  "reverted": false
}
```

撤销就是把最近一个 change 标记为 reverted，并重新计算 defaults。

## 6. 前端计划

第一版可以继续基于当前 Hermes WebUI 外壳实现，不重写整套前端。

### 6.1 新增模块

建议新增：

```text
vendor/hermes-webui/static/task-state.js
vendor/hermes-webui/static/task-detector.js
vendor/hermes-webui/static/surfaces.js
vendor/hermes-webui/static/ppt-surface.js
vendor/hermes-webui/static/workbench-defaults.js
```

职责：

- `task-state.js`：管理当前 session 的 task state。
- `task-detector.js`：根据用户输入识别 PPT 任务和“以后默认”意图。
- `surfaces.js`：根据 task state 切换页面形态。
- `ppt-surface.js`：渲染 PPT 信息卡、风格选择、编辑器形态。
- `workbench-defaults.js`：读取和应用工作台默认设置。

### 6.2 UI 组件

需要实现：

- `PPTInfoCard`
- `PPTStylePicker`
- `PPTOutlineReview`
- `PPTGeneratingView`
- `PPTEditorSurface`
- `RememberPreferenceCard`
- `CurrentWorkModePanel`

### 6.3 页面布局

#### 默认 Chat

```text
左侧：会话 / 工作台
中间：Chat
右侧：无或收起
```

#### 信息收集

```text
左侧：会话 / 工作台
中间：Chat + 关键信息卡
右侧：当前 PPT 工作方式
```

#### PPT 生成模式

```text
左侧：Chat / 任务步骤
右侧：关键信息 / 风格选择 / 大纲确认
```

#### PPT 编辑器形态

```text
左侧：AI Chat / 操作历史
中间：PPT 画布
底部：Slide 缩略图
右侧：大纲 / 讲稿 / 页面属性
```

## 7. 后端计划

### 7.1 本地状态文件

先落本地 JSON：

```text
.hermes-home/webui-nesquena/task_states.json
.hermes-home/webui-nesquena/workbench_defaults.json
.hermes-home/webui-nesquena/preference_changes.json
```

### 7.2 API

新增或补齐：

```text
GET  /api/task-state?session_id=
POST /api/task-state
PATCH /api/task-state/:session_id

GET  /api/workbench-defaults
PATCH /api/workbench-defaults/:workbench_id

POST /api/preferences/remember
POST /api/preferences/undo
```

### 7.3 API 设计原则

- API 只处理结构化状态，不参与 UI 细节。
- 后端不需要知道如何渲染 PPT 编辑器。
- 默认值和变更记录必须可恢复。

## 8. Agent 计划

第一版可以先用规则触发 + UI 状态模拟，随后再接 Agent tool。

### 8.1 第一阶段：规则触发

前端/后端规则：

```text
包含 PPT / slide / deck / 演示文稿 / 路演
  -> create_task(type=ppt)

包含 以后 / 每次 / 默认 / 下次
  -> suggest_remember_preference

包含 讲稿 / 短文案 / 页数 / 受众
  -> 生成可保存偏好
```

### 8.2 第二阶段：Agent Tool

给 Agent 暴露工具：

```text
create_task(type, initial_state)
update_task_state(patch)
set_surface(surface_id)
remember_preference(workbench_id, patch, summary)
suggest_surface_change(summary, patch)
undo_last_preference(workbench_id)
```

Agent 不直接改 DOM，不直接写 Host Core。

### 8.3 Agent 回复风格

需要明确区分三类意图：

```text
改当前内容：
  好，我来改第 3 页。

改以后默认：
  我可以把这个变成 PPT 默认习惯，要以后都这样吗？

改页面形态：
  我可以调整 PPT 工作台页面，先给你看效果。
```

## 9. 交互文案

### 9.1 识别 PPT 任务

```text
我先帮你整理做 PPT 需要的关键信息。
确认后我会生成大纲和页面。
```

按钮：

```text
确认
继续补充
```

### 9.2 记住工作方式

```text
我会先按你的要求改当前这份 PPT。
另外，你说了“以后”，要不要把它设为 PPT 默认方式？
```

按钮：

```text
以后默认这样
只这次
```

确认后：

```text
已记住：PPT 默认短文案 + 每页讲稿。
下次自动使用。
[撤销]
```

### 9.3 页面形态改造

```text
我理解这是在调整 PPT 工作台页面。
可以把讲稿区固定到右侧，方便你边看页面边改讲稿。
```

按钮：

```text
预览布局
以后默认
只这次
```

## 10. 实施步骤

### Step 0：冻结产品定义

产物：

- `CHAT_MORPHING_WORKBENCH_MODEL.md`
- 本计划文档

验收：

- 团队统一使用“会变形的 Chat”这个心智。

### Step 1：实现 task_state 基础层

任务：

- 新增 task state 本地存储。
- 给当前 session 绑定 task state。
- 实现读取 / 写入 / patch。

验收：

- 用户输入 PPT 关键词后，当前 session 出现 `type=ppt`。
- 刷新后 task state 仍存在。

### Step 2：实现 PPT 信息卡

任务：

- 检测 PPT 任务。
- 从用户输入提取 subject。
- 渲染 `PPTInfoCard`。
- 支持确认 / 补充。

验收：

- 输入“做一个介绍 Codex 的 PPT”后，Chat 里出现关键信息卡。
- 点确认后 phase 进入 `choosing_style` 或 `outlining`。

### Step 3：实现 PPT 生成模式

任务：

- 页面从纯 Chat 扩展为 Chat + PPT 任务区。
- 展示关键信息和风格选择。
- 生成一个模拟大纲。
- 支持确认大纲。

验收：

- 用户能看到页面从 Chat 变成 PPT 工作流。
- Chat 仍然可输入。

### Step 4：实现 PPT 编辑器形态

任务：

- 渲染模拟 PPT 画布。
- 渲染 slide 缩略图。
- 渲染讲稿 / 页面属性区。
- 支持选择当前页。
- 支持通过 Chat 改当前页的模拟内容。

验收：

- 用户看到“AI PPT 产品”的形态。
- 用户说“第 3 页重做”，当前页状态能变化。

### Step 5：实现工作方式记忆

任务：

- 检测“以后 / 默认 / 每次”。
- 生成 RememberPreferenceCard。
- 用户确认后写入 workbench defaults。
- 支持撤销。

验收：

- 用户说“以后每页都带讲稿，文案短一点”。
- UI 提示是否以后默认。
- 点确认后右侧显示当前 PPT 工作方式已更新。
- 点撤销后恢复。

### Step 6：下次自动应用默认形态

任务：

- 新建 PPT 任务时读取 defaults。
- 自动填入 includeSpeakerNotes / copyStyle 等偏好。
- 开场文案体现“按你的默认方式来”。

验收：

- 用户第二次发起 PPT 任务，不再从完全空白开始。
- 默认短文案和讲稿偏好自动出现。

### Step 7：页面形态改造 MVP

任务：

- 支持用户说“把讲稿区放右边 / 默认显示讲稿”。
- 展示轻量布局建议。
- 用户确认后写入 layout default。

验收：

- 下次进入 PPT 编辑器时，讲稿区默认显示在约定位置。

## 11. 验收 Demo

完整 demo 脚本：

```text
1. 打开 Next AI。
2. 点击新对话。
3. 输入：做一个介绍 Codex 的 PPT。
4. Chat 出现关键信息卡。
5. 确认主题、场景、比例、语言。
6. 页面变成 PPT 生成模式。
7. 选择一个风格。
8. 生成大纲。
9. 确认大纲。
10. 页面变成 PPT 编辑器形态。
11. 用户说：第 3 页重做，更像发布会。
12. 第 3 页更新。
13. 用户说：以后每页都带讲稿，文案短一点。
14. AI 提示是否设为默认。
15. 用户点“以后默认这样”。
16. 系统显示已记住，可撤销。
17. 新建另一个 PPT 任务。
18. Chat 开场：按你的默认方式来，我们先确认主题、受众和页数。
```

这条链路跑通，MVP 成立。

## 12. 风险和边界

### 风险 1：页面乱变，用户失控

控制方式：

- 页面变化必须由 task phase 驱动。
- 主动建议必须少。
- 改默认必须确认。
- 撤销始终可见。

### 风险 2：像 Lovable

控制方式：

- 不说“生成应用”。
- 不展示代码 diff。
- 不展示发布流程。
- 只围绕当前任务和下次更顺手。

### 风险 3：Agent 能力不稳定

控制方式：

- 第一版用规则 + 模拟状态跑通体验。
- Agent 只负责文本和有限工具调用。
- UI 状态不依赖模型自由发挥。

### 风险 4：工程复杂度爆炸

控制方式：

- 只做 PPT。
- 只做本地 JSON。
- 只做配置化 surface。
- 暂不做任意生成代码。

## 13. 开工优先级

P0：

- task state。
- PPT 任务识别。
- PPT 信息卡。
- PPT 生成模式。
- PPT 编辑器形态。

P1：

- 工作方式记忆。
- 默认值保存。
- 撤销。
- 下次自动应用。

P2：

- 页面形态改造。
- 主动建议。
- 真实 PPTX 导出。
- 更多工作台类型。

## 14. 最终判断

当前最重要的不是“让 AI 改代码”，而是先把这件事做得可感知：

> 用户从 Chat 开始做 PPT，页面一步步变成 AI PPT 产品；用户说以后都这样，系统记住；下次打开真的更顺手。

如果这条体验成立，再往后扩展研究、数据、文档、代码工作台，才有基础。

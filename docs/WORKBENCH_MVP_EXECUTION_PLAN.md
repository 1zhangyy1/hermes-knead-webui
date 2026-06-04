# Workbench MVP 执行计划

日期：2026-05-18

> 2026-05-23 更新：本文是旧的“一级工作台入口 / 静态 PPT 工作台”执行计划。当前第一版已调整为：**先做极简空工作台 Chat；新对话是入口；普通对话是默认工作台；工作台从任务中保存出来。** 当前以 [当前产品认知：自进化工作台](PRODUCT_DIRECTION_CURRENT.md) 为准。

## 1. 当前决策

第一版不要继续扩展当前 React host-shell。

主路线：

```text
用户侧 Agent Shell: vendor/hermes-webui
系统管理层: vendor/hermes-agent/web
旧 host-shell: 原型参考，暂不继续堆功能
```

原因：

- `vendor/hermes-webui` 已经有可用聊天、session、文件浏览、模型选择、skills、automation、profiles。
- 它是 Python + vanilla JS，没有构建步骤，Agent 自己修改成本低。
- 我们的差异化可以作为一层“工作台能力”嵌进去，不需要重写 Agent 基础体验。

## 2. 第一阶段目标

旧闭环如下，已不作为第一版目标：

```text
打开 Agent
  -> 左侧看到一级“工作台”
  -> 聊天里输入 PPT/路演/slide 相关任务
  -> 对话流出现“建议生成 PPT 工作台”卡片
  -> 点击预览
  -> 打开 PPT 工作台预览页
  -> 点击应用
  -> 左侧工作台出现“PPT 工作台 已启用”
  -> 可以回滚
```

当前第一阶段目标改为：

```text
打开产品
  -> 点击“新对话”
  -> 进入普通对话工作台
  -> Chat 可用
  -> 右侧有材料和结果
  -> 用户输入 PPT/路演/slide 相关任务
  -> 对话过程中出现 PPT 大纲/页面/讲稿等临时任务界面
  -> 完成一次任务后，提示“保存为 PPT 工作台”
  -> 用户确认后，左侧工作台出现“PPT 工作台”
```

这一阶段不要求 AI 真的生成任意 UI 代码。

先证明三件事：

1. 新对话 / Chat 主体验清晰。
2. 普通对话就是默认空工作台。
3. Chat 始终在场，任务界面不能替代 Chat。
4. “从对话任务中沉淀出专属工作台”的感觉能跑通。

## 3. 文件级落点

### 前端入口

```text
vendor/hermes-webui/static/index.html
```

要做：

- 在 rail 和移动 sidebar 中增加 `workbenches` tab。
- 增加 `panelWorkbenches` 左侧面板。
- 增加主内容区的 `workbenches` view。

现有参考：

```text
panelWorkspaces
panelSkills
panelTasks
```

### 前端面板逻辑

```text
vendor/hermes-webui/static/panels.js
```

要做：

- 在 `switchPanel()` 中加入 `workbenches`。
- 新增：
  - `loadWorkbenchesPanel()`
  - `renderWorkbenchesPanel()`
  - `openWorkbenchDetail()`
  - `previewWorkbench()`
  - `applyWorkbench()`
  - `rollbackWorkbench()`

现有参考：

```text
loadWorkspacesPanel()
renderWorkspacesPanel()
openWorkspaceDetail()
```

### 聊天流建议卡

```text
vendor/hermes-webui/static/messages.js
```

要做：

- 在 `send()` 里记录用户发送文本后，判断是否命中 PPT 触发词。
- 在 assistant 响应完成后，插入一个非模型消息的 UI 卡片。
- 第一版可以只做前端规则，不进入模型上下文。

触发规则先硬编码：

```text
PPT / powerpoint / slide / slides / deck / 路演 / 融资 / 演示文稿
```

### 样式

```text
vendor/hermes-webui/static/style.css
```

要做：

- 工作台列表 row。
- 工作台状态 badge：模板 / 建议中 / 已启用。
- `WorkbenchProposalCard`。
- PPT 工作台预览布局。

设计原则：

- 不要做成营销页。
- 不要太花。
- 更接近 Codex：左侧清晰、主区干净、卡片克制。

### 后端状态与 API

新增：

```text
vendor/hermes-webui/api/workbenches.py
```

状态文件：

```text
$HERMES_WEBUI_STATE_DIR/workbenches.json
```

当前本地对应：

```text
.hermes-home/webui-nesquena/workbenches.json
```

API：

```text
GET  /api/workbenches
POST /api/workbenches/propose
POST /api/workbenches/apply
POST /api/workbenches/rollback
```

在这里挂路由：

```text
vendor/hermes-webui/api/routes.py
```

参考现有：

```text
GET  /api/workspaces
POST /api/workspaces/add
POST /api/workspaces/remove
POST /api/workspaces/rename
```

## 4. 数据结构

第一版 `workbenches.json`：

```json
{
  "items": [
    {
      "id": "ppt-studio",
      "name": "PPT 工作台",
      "type": "ppt",
      "status": "enabled",
      "source": "suggested",
      "created_at": "2026-05-18T00:00:00Z",
      "updated_at": "2026-05-18T00:00:00Z",
      "version": 1,
      "description": "把 PPT 任务拆成大纲、页面、讲稿和导出。",
      "entry": "builtin:ppt-studio"
    }
  ]
}
```

状态：

```text
template   模板
suggested  建议中
enabled    已启用
archived   已回滚/归档
```

## 5. 第一版 PPT 工作台

先做内置静态工作台，不生成代码。

页面包含：

- 大纲栏
- Slide 列表
- 当前 slide 画布
- 右侧 Agent 指令栏
- 操作：生成大纲、优化文案、生成讲稿、导出占位

这不是最终能力，只是证明“应用工作台后，任务界面变得更适合 PPT”。

## 6. 验收标准

必须能在 `http://127.0.0.1:8788/` 看到：

1. 左侧有一级 `工作台`。
2. 工作台面板能列出 PPT 工作台。
3. 聊天输入 PPT 相关内容后，出现建议卡。
4. 点击预览能看到 PPT 工作台界面。
5. 点击应用后状态变成已启用。
6. 刷新页面后状态仍存在。
7. 点击回滚后状态变成 archived 或回到 suggested。
8. 原本 Hermes 聊天仍能用。

## 7. 开工顺序

### Step 1: 最小 UI 插入

只改前端：

- 增加 `工作台` tab。
- 增加空面板。
- 加静态 PPT 工作台 row。

验收：

```text
左侧层级正确，视觉不乱。
```

### Step 2: 本地状态 API

新增 `api/workbenches.py`，挂到 `routes.py`。

验收：

```text
curl /api/workbenches 返回 JSON。
apply / rollback 后刷新仍保存。
```

### Step 3: 接入真实面板

前端调用 `/api/workbenches` 渲染列表。

验收：

```text
工作台状态来自后端，不是写死。
```

### Step 4: 聊天建议卡

在聊天完成后根据用户任务插入建议卡。

验收：

```text
用户聊 PPT，卡片自然出现；用户聊普通问题，不出现。
```

### Step 5: PPT 工作台预览

做静态但可操作的 PPT 工作台界面。

验收：

```text
点击预览能进入一个明显更适合 PPT 任务的工作界面。
```

## 8. 暂不做

- 不做 marketplace。
- 不做多用户协作。
- 不做复杂权限。
- 不做任意代码生成。
- 不让 Agent 直接改 host shell。
- 不让生成代码进入 Hermes WebUI 核心目录。

真正 AI 改代码放到下一阶段：

```text
workbenches/generated/*
  -> build/check
  -> preview
  -> approve
  -> apply
  -> rollback
```

# Chat Kernel + AI Generated Workbench 产品计划

日期：2026-05-31

本文是当前最新方向的收敛版。它覆盖此前“Chat 变形工作台”的理解，但进一步明确：第一性原理不是 Block 渲染器，而是稳定 Chat 内核 + AI 生成的任务界面。

## 1. 当前判断

我们不应该把 Next AI 做成：

```text
工作台管理器
Block 搭建器
Lovable 式应用生成器
传统 AI PPT 工具
```

更准确的产品定义是：

> Next AI 是一个稳定 Chat 内核。用户从 Chat 开始做事；当某类任务需要更合适的界面时，AI 可以为当前任务生成一个专属工作台界面。这个界面仍然由 Chat 驱动，但可以长得越来越像真正的 AI PPT、AI 研究、AI 数据产品。

## 2. 核心关系

```text
Next AI 母体
├─ Chat Kernel              稳定，不随便改
├─ Workbench Runtime        加载、预览、应用、回滚生成界面
└─ Generated Workbenches    AI 生成的任务产品界面
```

### 2.1 Chat Kernel

Chat Kernel 是固定核心，负责：

- 消息流。
- 输入框。
- Agent 调用。
- 工具调用过程。
- 文件和产物引用。
- 权限提示。
- 会话状态。
- 工作台和 Agent 的通信协议。

它是产品的“脊柱”，不应该被 AI 随意改。

### 2.2 Workbench Runtime

Workbench Runtime 是生成界面的运行层，负责：

- 加载 AI 生成的 UI。
- 沙盒隔离。
- 预览。
- 应用。
- 回滚。
- 版本管理。
- 向生成界面暴露安全 SDK。

### 2.3 Generated Workbench

Generated Workbench 是 AI 写出来的具体任务界面，例如：

- AI PPT 工作台。
- AI 研究工作台。
- AI 表格分析工作台。
- AI 情感陪伴空间。
- AI 课程设计工作台。

这些界面可以是 React / HTML / CSS / JS。它们不是母体的一部分，而是运行在 Runtime 里的可替换子界面。

## 3. 为什么不以 Block 为主

Block 的优点：

- 稳定。
- 快。
- 容易撤销。
- 适合 Chat 消息、工具卡、文件卡等核心能力。

但 Block 的问题是：

- 容易把产品变成配置器。
- 限制 AI 的创造力。
- 很难长出真正新颖的任务产品形态。

所以当前决策：

> Block 只用于 Chat 核心和安全基础组件；具体任务工作台尽量让 AI 自己写。

## 4. 用户体验心智

用户不需要理解“生成应用”。

用户感知应该是：

```text
我在 Chat 里做事。
AI 发现这个任务需要更合适的界面。
AI 生成一个工作台预览。
我确认后，当前 Chat 页面变成更适合这件事的产品。
以后同类任务可以默认用这个形态。
不满意可以回滚。
```

## 5. AI PPT 的理想演进

### 阶段 1：普通 Chat

```text
用户：做一个介绍 Codex 的 PPT
```

页面还是普通 Chat。

### 阶段 2：Chat 识别任务，需要 PPT 界面

AI 回复：

```text
这是一个 PPT 制作任务。我可以先用 PPT 工作台来组织信息、风格和页面。

[使用 PPT 工作台] [继续纯聊天]
```

### 阶段 3：生成 PPT 工作台预览

AI 生成一个工作台 UI：

```text
左侧：AI Chat / 任务步骤
中间：PPT 画布
底部：页面缩略图
右侧：关键信息 / 风格 / 讲稿 / 页面属性
```

用户看到预览：

```text
[应用到当前任务] [继续修改预览] [不用]
```

### 阶段 4：应用后

当前会话进入 AI PPT 产品形态：

```text
Chat 还在
PPT 画布出现
缩略图出现
讲稿区出现
用户继续用自然语言控制页面
```

### 阶段 5：自进化

用户说：

```text
以后讲稿区一直放右边。
```

AI 回复：

```text
我可以修改 PPT 工作台界面，让讲稿区默认固定在右侧。

[预览新版] [应用为默认] [只这次]
```

AI 生成 v2，用户确认后应用，可回滚。

## 6. 关键机制

### 6.1 三类变化

```text
改当前内容
  直接改任务产物，例如第 3 页文案。

改工作方式
  保存偏好，例如以后默认短文案。

改工作台界面
  生成新版 UI，例如讲稿区固定右侧。
```

### 6.2 两种进化速度

小进化：

```text
偏好、默认值、流程顺序
立即保存，可撤销
```

大进化：

```text
新界面、新交互、新工作台形态
生成代码，预览，应用，回滚
```

### 6.3 AI 生成界面的安全边界

AI 可以改：

- 当前工作台 UI。
- 当前工作台样式。
- 当前工作台交互流程。
- 当前工作台默认行为。

AI 不可以直接改：

- 母体导航。
- 登录和权限。
- Chat Kernel。
- 文件系统权限。
- 回滚机制。
- Agent 核心调用链。

## 7. Workbench SDK

AI 生成的 UI 不能随便访问系统，只能通过 SDK 和母体通信。

第一版 SDK：

```ts
type WorkbenchSDK = {
  getMessages(): Message[]
  sendMessage(text: string): Promise<void>

  getTaskState(): TaskState
  updateTaskState(patch: Partial<TaskState>): Promise<void>

  getArtifacts(): Artifact[]
  saveArtifact(artifact: Artifact): Promise<void>

  getPreferences(): Record<string, unknown>
  rememberPreference(patch: Record<string, unknown>): Promise<void>
  undoLastPreference(): Promise<void>

  requestAgentAction(action: string, payload: unknown): Promise<unknown>
}
```

生成界面只能调用 SDK，不直接碰 Host。

## 8. 文件结构建议

```text
apps/
  shell/                         # 母体应用

workbenches/
  generated/
    ppt-workbench/
      manifest.json
      versions/
        v1/
          index.html
          app.js
          style.css
        v2/
          index.html
          app.js
          style.css
      current

.hermes-home/
  webui-nesquena/
    workbench_registry.json
    workbench_versions.json
    workbench_preferences.json
```

## 9. Manifest

每个生成工作台必须有 manifest：

```json
{
  "id": "ppt-workbench",
  "name": "PPT 工作台",
  "description": "用于制作、编辑和讲稿生成的 AI PPT 工作台。",
  "type": "ppt",
  "currentVersion": "v1",
  "entry": "versions/v1/index.html",
  "createdFromSessionId": "session-xxx",
  "permissions": ["messages", "taskState", "artifacts", "preferences"],
  "createdAt": "2026-05-31T00:00:00+08:00",
  "updatedAt": "2026-05-31T00:00:00+08:00"
}
```

## 10. MVP 路线

### MVP 0：稳定 Chat Kernel

目标：

- 现在的 Hermes Chat 能稳定对话。
- 工具调用卡片可见。
- 会话可恢复。
- 输入框简洁。

验收：

- 用户能把它当普通 Agent 用。

### MVP 1：Workbench Runtime 壳

目标：

- 能加载一个本地生成工作台。
- 能在 Chat 旁边或当前页面中切换到工作台形态。
- 能从 manifest 读取入口。

验收：

- 手写一个 `ppt-workbench/v1` 能在产品中打开。
- Chat Kernel 仍然可用。

### MVP 2：AI PPT 静态生成版

目标：

- 先不用 AI 动态写代码，手写一个 v1 作为目标形态。
- 证明体验：Chat + PPT 画布 + 缩略图 + 讲稿。

验收：

- 用户输入 PPT 任务后，可以进入 PPT 工作台。
- 能用 Chat 修改当前页的模拟内容。

### MVP 3：AI 生成 / 修改工作台 UI

目标：

- 让 AI 根据用户要求生成 v2。
- v1/v2 可以并存。
- 预览 v2。
- 应用 v2。
- 回滚 v1。

验收：

- 用户说“把讲稿区固定右侧”。
- 系统生成 v2 预览。
- 应用后布局变化。
- 回滚后恢复 v1。

### MVP 4：保存工作方式

目标：

- 用户说“以后都这样”，保存到当前工作台偏好。
- 生成界面能读取偏好。

验收：

- 第二次进入 PPT 工作台，默认使用已保存偏好。

## 11. 第一版不要做

- 不做工作台市场。
- 不做所有任务类型。
- 不做复杂多用户。
- 不做任意 npm install。
- 不做母体代码自修改。
- 不把所有 UI 都抽象成 Block。
- 不让用户看 manifest、代码 diff、构建日志，除非进入开发模式。

## 12. 我们现在的开工建议

最稳妥的顺序：

```text
1. 先把当前 Chat Shell 稳定成可用 Agent。
2. 做 Workbench Runtime：能加载一个 generated workbench。
3. 手写 PPT Workbench v1，作为目标体验。
4. 接入 Chat 和 PPT Workbench 的 SDK 通信。
5. 做 preview/apply/rollback 版本机制。
6. 再让 AI 真的生成 v2。
```

这比一上来让 AI 任意改页面更稳，也比 Block 系统更接近最终产品。

## 13. 当前一句话

> Next AI 的核心不是 Block，也不是 app builder，而是稳定 Chat 内核 + AI 生成的任务工作台。Chat 负责持续对话和 Agent 能力；工作台负责长出最适合当前任务的产品形态；AI 可以改工作台，但必须通过预览、应用和回滚。

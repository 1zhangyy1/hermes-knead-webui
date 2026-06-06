# 自进化工作台核心实现计划

日期：2026-05-18

> 2026-05-23 更新：本文偏向“从一句话生成专属工作台”的核心闭环，仍可作为后续实现参考。但第一版产品入口已调整为：**新对话 -> 普通对话工作台 -> 任务中长出界面 -> 保存为专属工作台**。当前以 [当前产品认知：自进化工作台](PRODUCT_DIRECTION_CURRENT.md) 为准。

## 1. 当前判断

现在不要继续把界面做复杂，也不要一开始追求“AI 修改整个母体应用”。

第一阶段的核心目标不是先生成一个完整专属工作台，而是先把空工作台 Chat 做清楚。随后再跑通一个最小但真实的沉淀闭环：

> 用户从新对话开始做事；任务中出现材料、结果和临时任务界面；完成后可以保存为一个可预览、可继续修改的专属工作台。

这才是产品从“普通 Agent”进入“会长出子应用的母体”的关键一步。

## 2. 第一版闭环

核心路径改为：

```text
用户点击新对话
  -> 进入普通对话工作台
  -> 用户说“帮我做一个融资 PPT”
  -> AI 追问受众、目标和材料
  -> 任务中出现 PPT 大纲、页面、讲稿等临时界面
  -> 用户在 Chat 里继续指挥 AI 修改
  -> AI 提示“这类任务以后可以保存为 PPT 工作台”
  -> 用户确认保存
  -> PPT 工作台出现在左侧工作台列表
  -> 后续 PPT 工作台可以继续提出改造建议
```

第一版可以先用 PPT 工作台，因为它最容易体现“不同界面召唤不同需求”。

## 3. 产品原则

1. `新对话` 是第一入口。
2. 普通对话就是默认空工作台。
3. 工作台不是模板市场，而是从任务中沉淀出来的工作环境。
4. AI Chat 是工作台里的控制台，不能被专属界面替代。
5. AI 可以改代码，但第一阶段只允许改 generated spaces，不允许直接改 Host Core。
6. 所有工作台改造都必须有预览、应用、回滚。
7. 用户不需要理解代码，只需要理解“保存 / 预览变化 / 应用到工作台 / 回滚”。

## 4. 技术边界

第一阶段把代码分成三层：

```text
Host Core
  当前 Hermes WebUI / Next AI 母体。
  负责新对话、Chat、导航、设置、工作台注册、权限、预览入口。
  第一阶段不让 Agent 直接改这一层。

Generated Spaces
  AI 可以生成和修改的专属工作台实现目录。
  例如 spaces/generated/ppt-studio/v1。

Runtime Bridge
  Host 和 Generated Space 之间的桥。
  负责读取 manifest、启动预览、注册入口、应用版本、回滚版本。
```

## 5. 目录设计

建议新增：

```text
spaces/generated/
  ppt-studio/
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
    current -> versions/v1

.hermes-home/webui-nesquena/
  workbenches.json
  workbench_versions.json
```

第一版为了降低复杂度，可以先生成纯 HTML/CSS/JS 子应用，不立刻引入 React/Vite。等闭环跑通后再升级到 React/Vite。

## 6. Manifest 设计

每个工作台必须有一个 manifest：

```json
{
  "id": "ppt-studio",
  "name": "PPT 工作台",
  "description": "把 PPT 任务拆成主题、受众、大纲、页面和讲稿。",
  "version": "v1",
  "status": "preview",
  "entry": "/api/workbenches/ppt-studio/preview",
  "createdFromSession": "session-id",
  "createdAt": "2026-05-18T00:00:00Z"
}
```

Host 只通过 manifest 认识工作台，不直接假设子应用内部结构。

## 7. 后端接口

第一版新增或补齐这些接口：

```text
POST /api/workbenches/propose
  从已发生的任务上下文生成“保存为工作台”提案。

POST /api/workbenches/create
  根据提案创建 generated space 初始版本。

GET /api/workbenches
  列出工作台。

GET /api/workbenches/:id/preview
  返回当前预览版本入口。

POST /api/workbenches/:id/apply
  把 preview 版本设为 current。

POST /api/workbenches/:id/rollback
  回滚到上一个版本。

POST /api/workbenches/:id/evolve
  根据用户的新要求生成下一个版本。
```

## 8. Agent 侧工具

要让聊天 Agent 能进入核心，需要给它暴露最小工具：

```text
propose_workbench(requirement)
create_workbench(proposal)
evolve_workbench(workbench_id, instruction)
list_workbenches()
```

第一阶段可以先不接完整 tool calling，而是在 `messages.js` 里做轻量触发：

```text
如果用户消息包含 “工作台 / 专属界面 / 经常做 / PPT / 生成一个”
  -> 显示工作台提案卡片
  -> 用户点确认
  -> 调用 create_workbench
```

这不是最终形态，但足够让产品闭环先活起来。

## 9. 第一版生成策略

为了快速进入核心，不要一开始依赖大模型稳定生成完整前端工程。

第一版采用混合策略：

```text
模板骨架 + AI 填充配置/文案/模块
```

PPT 工作台 v1 至少包含：

```text
主题输入
受众选择
PPT 类型选择
大纲区域
页面列表
讲稿区域
一键让 Agent 优化
继续改造这个工作台
```

这样它已经不是静态展示，而是一个可以由用户继续演化的独立子应用。

## 10. UI 改动

Host UI 保持简单：

```text
左侧：
  Agent
  自动化
  工作台
  技能
  设置

中间：
  通用 Agent 对话
  工作台提案卡片

工作台页：
  已启用工作台
  预览中的工作台
  版本 / 应用 / 回滚
```

第一版不要做复杂 Marketplace，不要做很多 Space 分类。

## 11. 实施步骤

### Step 1：定义 generated space 目录和 manifest

产物：

- `spaces/generated/ppt-studio/manifest.json`
- `spaces/generated/ppt-studio/versions/v1/`
- 后端能读取 manifest 并返回工作台列表。

完成标准：

- `GET /api/workbenches` 能返回 generated 工作台。

### Step 2：生成第一个真实 PPT 工作台页面

产物：

- 一个可打开的 HTML/CSS/JS PPT 工作台。
- 页面不是展示图，而是真有输入区、模块区、操作区。

完成标准：

- 用户能在 Host 的工作台入口打开它。

### Step 3：把聊天里的提案卡片接到创建流程

产物：

- 用户在 Agent 输入“帮我创建一个 PPT 工作台”。
- 页面出现“是否创建 PPT 工作台”的提案卡。
- 点确认后创建 generated space。

完成标准：

- 从聊天到工作台注册不需要手动改文件。

### Step 4：实现 evolve 生成新版本

产物：

- 用户说“把这个 PPT 工作台改成更适合融资路演”。
- 系统生成 `v2`。
- 用户可以预览 v2。

完成标准：

- v1 和 v2 可以并存。
- current 指向可以切换。

### Step 5：实现 apply / rollback

产物：

- 应用 v2。
- 回滚到 v1。

完成标准：

- 版本切换不会丢失工作台入口。

## 12. 第一版不做什么

暂时不做：

- Marketplace
- 多用户权限
- 完整代码审查系统
- 自动测试沙盒
- 任意 npm install
- 让 AI 改 Host Core
- 复杂 React/Vite 工程生成
- 多种工作台同时生成

这些都等第一条闭环跑通后再加。

## 13. MVP 成功标准

如果用户可以完成下面这条路径，就算进入核心 MVP：

```text
打开 Next AI
  -> 和 Agent 说：我想要一个 PPT 工作台
  -> 看到创建提案
  -> 点击创建
  -> 打开生成出来的 PPT 工作台
  -> 再说：把它改成融资路演风格
  -> 看到新版本预览
  -> 应用新版本
  -> 可以回滚
```

这条链路一旦成立，产品就不再只是聊天壳，而是开始拥有“自进化工作台”的真实骨架。

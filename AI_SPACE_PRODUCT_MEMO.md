# AI Space 产品概念备忘录

日期：2026-05-17

> 2026-05-23 更新：本文保留早期战略思考，但其中 “Space 首页 / AI Space 平台 / 先进入专属 Space” 的表达已经不是当前第一版产品准则。当前以 [当前产品认知：自进化工作台](docs/PRODUCT_DIRECTION_CURRENT.md) 为准：**新对话是入口，普通对话是默认工作台；专属工作台从对话中长出来，并在后续使用中自我改造。**

## 1. 核心判断

我们要做的不是一个固定形态的 AI 应用，而是一个能够长出很多专属 AI 子应用的母体。

它的核心能力是：让 Agent 的工作范围足够大，大到可以改造它自己的工作环境，甚至改造它所在应用的一部分。

换句话说，Agent 不只是回答问题、调用工具、生成内容，而是可以根据用户真实使用场景，持续生成、修改、维护属于用户的 AI 空间。

一句话定义：

> 一个会把自己改造成你需要的软件的 AI 产品。

平台化定义（内部语言）：

> 一个由 AI Chat 驱动、可持续改造自己的工作台系统。

更面向用户的表达：

> 你每做一次工作，它都会把下一次变简单。

## 2. 为什么不是只做万能聊天框

现在大部分 AI 产品都从聊天框开始。Chat 仍然是最低门槛入口，第一版也必须从新对话开始；但只停留在聊天框会有问题：任务变复杂后，用户缺少可指代、可操作、可复用的工作环境。

例如，一个做 PPT 的用户面对聊天框，可能只会说：

> 帮我做个 PPT。

更自然的路径不是让用户先选择 PPT Studio，而是用户从普通对话开始做 PPT；做着做着，界面里出现：

- Slides
- Outline
- Brand Kit
- Assets
- Speaker Notes
- Export
- Critique
- Version History

他会自然产生更具体、更高价值的需求：

- 帮我重排第 3 页。
- 把这页改成投资人风格。
- 统一品牌色。
- 生成讲稿。
- 检查逻辑漏洞。
- 做一个竞品页。

关键判断：

> 新对话是入口；当任务变复杂时，工作台内部会长出更适合这个任务的界面。界面本身会帮助用户提出更具体的需求。

这也是我们和普通 AI Chatbot 最大的区别。AI 不应该只有一种界面。

## 3. 产品形态

产品可以分成四层，但用户第一眼不应该先看到这四层：

```text
1. Host Shell
   稳定母体，负责账号、权限、数据、模型、文件、支付、安全、版本、回滚。

2. Workbenches
   工作台是容器。普通对话工作台是默认入口；PPT、研究、数据等专属工作台从任务中沉淀出来。

3. Evolution Engine
   Agent 可以根据用户使用，修改空间的代码、界面、prompt、skill、workflow。

4. Sharing / Marketplace
   远期能力。第一版不做市场，不让用户先理解平台。
```

更直白地说：

> 我们不是做一个固定 Chat，也不是做一个工作台市场，而是做一个从新对话开始、能把任务界面沉淀成专属工作台的产品。

当前技术路线决策：

> Hermes Agent 完全复用为底层 Agent Runtime / Agent OS。我们不重写 agent loop、memory、skills、tools、gateway、approval、cron、MCP，而是在 Hermes 外面做 AI Space Host Shell、Space Runtime、Evolution UX。

也就是说：

```text
AI Space Host Shell
  - Space 首页
  - PPT Studio / Research Lab / Companion World
  - Agent side panel
  - evolution proposal
  - preview / apply / rollback
  - Space marketplace

        ↓ API / SSE / approval

Hermes Agent
  - AIAgent
  - memory
  - skills
  - tools
  - gateway
  - cron
  - MCP
  - terminal backends
  - OpenAI-compatible API
  - /v1/runs event stream
```

## 4. AI Space 是什么

AI Space 是一个面向具体需求的 AI 子应用。

每个 Space 都可以拥有：

- 自己的页面和交互方式
- 自己的 Agent 角色
- 自己的 prompt 和 memory
- 自己的工具和权限
- 自己的 workflow
- 自己的数据视图
- 自己的版本历史
- 自己的进化路径

例如：

```text
PPT Studio
  - Slides
  - Outline
  - Brand Kit
  - Speaker Notes
  - Export
  - Slide Critique

Research Lab
  - Sources
  - Notes
  - Cards
  - Citations
  - Drafts
  - Research Map

Companion World
  - Room
  - Character
  - Memory
  - Events
  - Relationship Progress
  - Mini Games

Creator Studio
  - Script
  - Assets
  - Timeline
  - Publishing
  - Feedback
  - Analytics
```

这些空间不是普通模板。它们是可以继续被 Agent 和用户共同改造的活空间。

## 5. 自进化机制

自进化不是后台偷偷乱改，而是一个可见、可控、可回滚的过程。

基本流程：

```text
用户使用某个空间
  ↓
Agent 发现重复需求，或用户明确提出改造
  ↓
Agent 生成/修改代码、workflow、skill、UI
  ↓
启动预览环境
  ↓
跑测试和安全检查
  ↓
展示改动说明和效果预览
  ↓
用户批准
  ↓
应用到这个用户的空间
  ↓
保留版本，可回滚
```

核心体验不是“AI 神秘地进化”，而是：

> 它会把这次协作沉淀成下次可直接使用的软件能力。

普通 AI：这次帮你做一份 PPT。

我们的产品：这次帮你做 PPT，并把自己进化成更适合你下次做 PPT 的软件。

## 6. 代码层面的判断

我们更倾向于让 AI 真的改代码，而不是只改配置。

原因是：如果这个 AI 本来就能帮用户写页面、写组件、写 workflow，那么它也应该可以写自己的页面和工作环境。这个产品叙事更自然，也更有冲击力。

但工程上不能让它无限制裸改核心系统。应该分成：

```text
Host Core
  稳定，不轻易被改。

Agent-owned Surface
  大面积允许 Agent 修改，是 Agent 能够拥有和改造的区域。

Generated Spaces
  AI 生成和维护的子应用。

Sandbox Runtime
  隔离运行 AI 生成代码。

Review System
  测试、预览、审批、回滚。
```

Agent 可以改：

```text
spaces/*
workflows/*
skills/*
ui/*
memory/*
agents/*
```

高风险区域要保护：

```text
auth
billing
security
permission system
sandbox
update mechanism
audit log
```

准确说法：

> AI 可以改自己所在的应用，但必须在隔离、验证、审批、回滚的机制里改。

## 7. 平台机会

这个产品里，普通用户不只是消费者。

用户通过使用、反馈、选择、确认进化方向，会逐渐变成 Space Creator。他们不一定写代码，但他们会和 Agent 一起创造新的产品形态。

未来可能出现：

- VC Fundraising Deck OS
- Student Research Lab
- Therapy-like Companion Space
- Indie Hacker Launch Room
- Sales Proposal Studio
- Courseware Builder

这些空间可以从真实使用中长出来，再被分享给其他人。

这意味着：好的 AI 空间不是由产品团队全部设计出来，而是在用户真实工作中长出来的。

## 8. 早期 MVP 建议

不要一开始做通用平台。先选一个最容易体现价值的场景，比如 PPT。

PPT 适合作为第一个场景，因为它天然需要：

- UI
- 文件
- 模板
- 素材
- 大纲
- 反复编辑
- 审美判断
- 版本管理
- 最终交付

MVP 流程：

```text
1. 用户进入 PPT Studio
2. 用聊天或结构化输入生成一份 PPT
3. Agent 完成任务后总结用户流程
4. Agent 提议生成专属工作台，比如 Pitch Deck Studio
5. 用户确认
6. AI 生成新的页面、流程、组件、技能
7. 下次用户进入时，不再从空白聊天开始，而是进入进化后的工作环境
```

这个 MVP 要证明一件事：

> 用户不是每次都从聊天框重新开始，而是能看到自己的工作方式被产品沉淀下来了。

## 9. 需要避免的坑

1. 不要把第一卖点说成“AI 会改自己”。

   这句话技术圈会兴奋，但普通用户可能会害怕。更好的表达是：“你每做一次工作，它都会把下一次变简单。”

2. 不要一上来做太多预制空间。

   早期空间太多会造成选择疲劳。建议先做 3 到 5 个高质量空间。

3. 不要让用户感受到自己在管理 AI 代码。

   用户应该看到的是新工作台、新按钮、新流程、新能力，而不是一堆文件 diff。

4. 不要让 UI 频繁无提示变化。

   变化应该发生在任务完成后，由 Agent 提出建议，用户预览并确认。

5. 不要只做界面变化。

   真正有价值的是 UI、workflow、memory、tool 能力一起进化。

6. 不要没有回滚。

   没有回滚，用户不会信任一个会自我改造的软件。

## 10. 当前最重要的产品命题

未来的 AI 产品不是一个万能聊天框，而是一组会自我进化的场景空间。

用户不是在使用一个固定软件，而是在和 AI 一起长出自己的软件。

最终我们要做的是：

> 一个稳定母体，让 Agent 可以不断长出、修改、维护各种 AI Spaces。每个 Space 都是一个面向具体需求的 AI 子应用，它有自己的界面、能力、记忆、流程，并且会随着用户使用继续进化。

核心不是“AI 会改 prompt”。

核心是：

> AI 会改造它自己的工作环境，直到这个环境越来越像用户真正需要的软件。

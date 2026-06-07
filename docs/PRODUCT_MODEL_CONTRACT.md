# Next AI 产品模型契约（唯一事实来源）

更新日期：2026-06-05

> 本文是 Next AI 产品与架构的**唯一准则**。`docs/archive/` 下的所有旧计划（AI Space、Agent+Workbench、Chat Morphing、Self-Evolving Workbench、PRODUCT_DIRECTION_CURRENT、NEXT_AI_PRODUCT_MOTHER 等）与本文冲突时，一律以本文为准。
>
> 规则：任何新功能，先问「它是改骨架，还是填某个槽？」。填不进下面的模型 → 要么不做，要么先慎重扩槽。**不再新增互相打架的计划文档。**

---

## 1. 一句话定义 + 「成了」的判据

> Next AI 是一个 AI 产品母体：用户**选择、使用、进化**很多能自己长出任务界面的 AI 产品。

**「成了」的判据：**

> 通用聊天 / 工具型（如 AI PPT）/ 游戏型（如二次元角色）三类完全不同的产品，走的是**同一套创建-迭代-管理生命周期**；它们的差异，收敛到少数几个**明确命名的变量槽**里，而不是三套各自为政的逻辑。

核心赌注（一切配套都服务于它）：

> **「一句话 → 生成一个我真的会用、还能调教的 AI 产品」能不能稳定做到。**

反定位：不是普通 AI 助手列表，不是插件市场，不是开发者 App builder。（注意：机制上我们确实在生成可演化的 HTML 产品——承认这一点，但对用户隐藏。）

---

## 2. 统一模型（三个视角，同一个东西）

### 2.1 数据视角：骨架 + 4 个变量槽

**共有骨架**（三类产品完全一样，**绝不为类型分叉**）：
`id / title / avatar / desc / source_prompt / workspace / sessions（历史）/ versions（迭代回滚）/ preview / created_at`

**变量槽**（类型的全部差异，**只活在这 4 个里**）：

| 槽 | 含义 | 通用聊天 | AI PPT | 二次元游戏 |
|---|---|---|---|---|
| `product_layout` | UI 长在哪（唯一真正重要的槽） | `chat_only` | `chat_left_canvas_right` | `canvas_full` |
| `product_type` | 语义标签（只用来推默认值） | `general` | `ppt` | `interactive`/`image` |
| `skills` + `tools` | 能力（由 type 推导） | 无 | presentations/office | imagegen/image_gen |
| `canvas_label` | 画布标题（纯展示） | 空 | "PPT 工作区" | "角色聊天" |

### 2.2 架构视角：一个模型，两顶帽子

底层永远是**同一个模型、同一个 agent runtime**。换帽子 ≠ 换 agent，而是换三样东西：

```
帽子 = ① system prompt（人设/指令） + ② 工具集（tools） + ③ 上下文线（读哪段记忆）
```

| 帽子 | scope | ① 人设 | ② 工具 | ③ 上下文线 |
|---|---|---|---|---|
| **造物帽** | `product_builder` / `product_init` | 「你在改造这个产品」 | 文件读写 / code_execution | 造物对话线 |
| **产品帽** | `product_usage` | 产品自己的 role | 任务工具，**禁止改自身 product.json** | 用/玩对话线 |

**角色不是第三顶帽子**：它是「产品帽」里换一个 `context.character` 变量，由产品帽扮演。

落地约束：
- ③ 造 / 用 是**两条上下文线**（同模型）：调产品的对话不与用/玩的记忆混在一起。
- ② 工具按 scope 切：产品帽与角色**绝不能拿到改自身产品的工具**（安全边界）。
- `product_ephemeral_prompt` 已在按 scope 注入 ①——这部分已做一半。

### 2.3 用户视角：一排 App，三个动词

用户**永不感知**造物/产品/角色三层。用户只感知「一排能说话、偶尔能调教的 AI」。

| 动词 | 含义 |
|---|---|
| **选** | 从一排 AI 里挑一个，或新建一个 |
| **用** | 跟它说话、做事 |
| **调** | 偶尔说「以后这样」，让它变顺手 |

用户已有的常识就是映射：**手机 → App → App 里的角色**。没人会把游戏 NPC 当成另一个 App，所以「角色不是独立产品」**不用向用户解释**。

唯一必须让用户**看得见**的边界：**「我在用它 / 我在调它」**——做成屏幕上一个明确状态，不靠系统猜。

屏幕上禁止出现的内部词：`产品/canvas/画布/演化/version/manifest/sandbox/persona/scope`。用用户语言代替（产品名、"调整"、"换回上一版"）。

---

## 3. 层级与升格规则

```
宿主 Shell（运行时）
 └─ 造物帽         —— 创建/演化「产品」
     └─ 产品（4 槽对象）  ← 产品库里的一行
         ├─ 产品帽（每产品 1 个身份/记忆/版本线）
         └─ 画布（生成的 UI）
             └─ 角色/人格（N 个，运行时内容，走 context，不是子产品）
```

铁律：
1. **造物帽操作产品，产品帽操作内容，永不混用。** 产品帽永不改自己的 product.json（要改 = 演化，交回造物帽）。
2. **产品不嵌套产品。** 产品里装「内容/人格（数据）」，不是子产品。永不做无限层级。
3. **一个产品 = 一个产品帽 = 一条记忆/版本线。**

升格规则：只有当用户想**单独创建-迭代-管理-复用**某个角色时，它才升格成独立产品（拿一行 product.json）；只在使用中被切换的，永远是内容。

---

## 4. 现状：两个总根源 + 已澄清事实

- **根源 B（产品，未解决）**：「用/调」边界在 UI 上不存在 → 后端只能用正则 `infer_product_scope` 猜 scope。**最高优先修复对象。**
- **根源 A（工程，已大半修好）**：前端 `assistant` / 后端 `product` 双词汇。**注意：双事实来源已修**——后端 `products.json` 是唯一来源，`hydrateProductsFromBackend` 负责拉取，localStorage `next-ai-custom-assistants` 仅剩遗留清理。剩下的只是**命名/字段翻译层**（assistant↔product、kind↔id、camel↔snake），是认知税不是 bug，**留到模型证稳后机械清扫**。

其余问题（内部词漏屏、ui_mode 冗余、bridge 不校验 origin、巨型文件、并发竞态、i18n 半成品、产品层缺测试）见执行顺序第 5–6 阶段。

---

## 5. 执行顺序（先证模型，再清内债）

三条铁律贯穿全程：**① WIP=1。② 不再写新概念文档。③ 模型没证稳前不碰纯内部重构（命名、拆文件）。**

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 锁基线：冻结 Hermes 底座、归档旧计划、写本契约 | ✅ 完成 |
| 1 | **用/调开关** → `product_scope`，正则降级兜底（治根源 B） | ✅ 完成 |
| 2.1 | 按 scope 收紧用态指令（产品文件只读，改产品引导去「调整」） | ✅ 完成（prompt 级） |
| 2.2 | 造/用拆上下文线（用户目标:可见的用/调边界 + 用态不乱改产品） | ✅ **实际交付=单会话**：前端 `canAdjustProduct` 开关翻 scope(任何产品可调),达成用户目标。后端双会话机制(2.2a/b/c:product_line + 按线工作区守卫)**已写好、单测通过、单会话下休眠无害**,留作"记忆串味/误改文件成为实际问题时"再激活的备用项。**2.2d 双会话切换 superseded**(降级为可选未来项,非遗漏);其结构性硬隔离的临时替代是 2.1 的 prompt 软指令 |
| 3 | 二次元游戏产品进左侧栏 + 角色走 bridge context（验证第三层） | ✅ 代码完成:3.1 产品入栏(API真验)；3.2 canvas 发 context.character → 宿主 _productCanvasBridgeInstruction 注入"扮演该角色" → messages 送达 agent,契约一致；运行观察需浏览器+LLM |
| 4 | 黄金路径真人验证：5 句话造产品，≥3 个当场能用 | 🟡 机械链路已端到端验通(2026-06-06,本地 3.11 venv + 真实 gpt-5.5):一句话→创建→init会话→生成→真 index.html→清理。"一句话→可用画布"成立。剩真人验收(多句话、≥3"愿再用")需你浏览器走查。**跑法:`HERMES_WEBUI_PORT=8799 apps/webui/.venv311/bin/python apps/webui/server.py`**(勿用 3.14 的 `.venv`) |
| 5 | 内债清理（模型证稳后机械 sweep）：删内部词副标题、砍 ui_mode、新建拆出列表、E1 命名统一、bridge origin 校验 | 缓做 |
| 6 | 工程健康（按需）：产品层补测试、并发竞态、巨型文件、i18n | 6.1 产品 scope/line 单测 ✅(24/24,tests/test_product_scope_lines.py);其余背景 |
| 7 | **通用 AI 主动提议升格**：chat_only 用态聊到可复用工具时,回答末尾发 `[[NEXT_AI_SUGGEST_PRODUCT]]{title,prompt,type}[[/...]]` marker | ✅ 后端(product_ephemeral_prompt 注入协议 + 3 单测)+ 前端(ui.js 解析/抹除 marker、渲染「做成专属产品」按钮 → createProductFromPrompt;messages.js 流式不闪现;style.css 按钮样式)均完成。marker 只在该轮最终助手消息落定后变按钮 |

详细分解见任务列表（TaskList）。

---

## 6. 被本文取代 / 归档的文档

以下文档已移入 `docs/archive/`，仅作历史参考，与本文冲突以本文为准：

ASSISTANT_PRODUCT_UI_REDESIGN_PLAN · ASSISTANT_WORK_INTERFACE_UX_SPEC · CHAT_KERNEL_GENERATED_WORKBENCH_PLAN · CHAT_MORPHING_MVP_IMPLEMENTATION_PLAN · CHAT_MORPHING_WORKBENCH_MODEL · CURRENT_WALKTHROUGH_ISSUES · GENERATED_WORKBENCH_LANDING_PLAN · NEXT_AI_DETAILED_TODO · NEXT_AI_PRODUCT_MOTHER_CURRENT · NEXT_AI_PRODUCT_RUNTIME_PLAN · PRODUCT_DIRECTION_CURRENT · SELF_EVOLVING_WORKBENCH_CORE_PLAN · WORKBENCH_MVP_EXECUTION_PLAN

参考/分析类文档移入 `docs/references/`：HERMES_RUNTIME_NOTES · HERMES_WEBUI_EVAL · LOBEHUB_ASSISTANT_REFERENCE_ANALYSIS

产品愿景与 UIUX 细则仍以仓库根的 `PRODUCT.md` / `PRODUCT_UIUX.md` 为权威；本文是它们之上的**模型与执行**契约。

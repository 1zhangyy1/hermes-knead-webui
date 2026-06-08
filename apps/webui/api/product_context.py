"""Runtime product context passed to Hermes Agent turns.

The frontend should not hide product instructions inside the user's visible
message. It sends structured fields, and this module turns them into a WebUI-only
ephemeral prompt.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from api.products import get_product

logger = logging.getLogger(__name__)

PRODUCT_SCOPES = {"product_usage", "product_init", "product_builder"}
CAPABILITY_LABELS = {
    "presentations": "presentation/deck creation",
    "office": "Office document workflows",
    "imagegen": "image generation/editing",
    "browser": "browser and web research",
    "spreadsheets": "spreadsheet/data analysis",
    "skills": "runtime skills",
    "file": "file editing",
    "terminal": "terminal commands",
    "code_execution": "code execution",
    "image_gen": "image generation toolset",
    "web": "web search",
}

_PRODUCT_BUILDER_RE = re.compile(
    r"("
    r"界面|页面|UI|布局|工作流|流程|表单|字段|按钮|面板|模块|导航|入口|样式|"
    r"右侧|左侧|上方|下方|顶部|底部|侧栏|顶栏|预览区|工作台|参数区|历史|"
    r"区域|卡片|工具栏|输入框|下拉|筛选器|上传区|导出|下载|"
    r"资料栏|参考资料栏|讲稿区|大纲区|缩略图|模板选择|风格选择|页数选择|"
    r"头像|名称|名字|简介|职责|人设|身份|提示词|prompt|技能|工具|能力|"
    r"放上面|放下面|放到|放在|移到|挪到|"
    r"改自己|产品自己|长出来|长出|"
    r"以后|每次|下次|默认|固定|常驻|"
    r"workflow|layout|interface|form|panel|sidebar|toolbar|card|default|always|next\s*time"
    r")",
    re.IGNORECASE,
)
_PRODUCT_BUILDER_NEGATION_RE = re.compile(
    r"("
    r"(?:不要|不用|不必|不需要|无需|别|先别|不要再|不用再).{0,16}"
    r"(?:改|修改|调整|重写|更新|生成|设计|动|写|编辑).{0,16}"
    r"(?:界面|页面|UI|布局|工作流|流程|表单|面板|模块|产品画布|产品界面|产品UI)"
    r"|"
    r"(?:不改|不动|不调整|不修改|不更新).{0,16}"
    r"(?:界面|页面|UI|布局|工作流|流程|表单|面板|模块|产品画布|产品界面|产品UI)"
    r")",
    re.IGNORECASE,
)


def infer_product_scope(
    intent: str,
    requested_scope: str = "product_usage",
    *,
    explicit: bool = False,
) -> str:
    """Resolve the product runtime scope.

    When ``explicit`` is True the frontend has decided the scope from the visible
    用/调 toggle (or first-generation / bridge), so that scope is authoritative and
    the keyword regex is skipped entirely. The regex only runs as a last-resort
    fallback for callers that omit an explicit scope.
    """

    scope = requested_scope if requested_scope in PRODUCT_SCOPES else "product_usage"
    if explicit:
        return scope
    if scope in {"product_init", "product_builder"}:
        return scope
    seed = str(intent or "").strip()
    if not seed:
        return scope
    if _PRODUCT_BUILDER_NEGATION_RE.search(seed):
        return scope
    if _PRODUCT_BUILDER_RE.search(seed):
        logger.info(
            "product_scope regex fallback fired (no explicit scope): usage -> builder; intent=%r",
            seed[:80],
        )
        return "product_builder"
    return scope


def product_context_request_body(body: dict[str, Any] | None, session: Any, message: str) -> dict[str, Any]:
    """Restore product request fields from a product-bound session when needed."""

    source = body if isinstance(body, dict) else {}
    next_body = dict(source)
    product_id = str(next_body.get("product_id") or next_body.get("productId") or "").strip()
    if not product_id:
        product_id = str(getattr(session, "product_id", None) or "").strip()
        if not product_id:
            return next_body
        next_body["product_id"] = product_id

    if not (next_body.get("message") or next_body.get("text")):
        next_body["message"] = message

    has_existing_turns = bool(
        getattr(session, "messages", None)
        or getattr(session, "context_messages", None)
        or getattr(session, "pending_user_message", None)
    )
    if not (next_body.get("product_scope") or next_body.get("productScope")):
        session_line = str(getattr(session, "product_line", None) or "").strip()
        session_scope = str(getattr(session, "product_scope", None) or "").strip()
        if session_line == "build":
            # 造物会话续聊:保持 build 线 scope,绝不退回 usage(双会话分离的关键)。
            next_body["product_scope"] = session_scope if session_scope in {"product_init", "product_builder"} else "product_builder"
            next_body["product_scope_explicit"] = True
        elif session_line == "use":
            next_body["product_scope"] = "product_usage"
            next_body["product_scope_explicit"] = True
        elif not has_existing_turns and session_scope in {"product_init", "product_builder"}:
            next_body["product_scope"] = session_scope
        else:
            next_body["product_scope"] = "product_usage"
    if not (next_body.get("product_intent") or next_body.get("productIntent")):
        session_intent = str(getattr(session, "product_intent", None) or "").strip()
        next_body["product_intent"] = session_intent if session_intent and not has_existing_turns else message
    return next_body


def product_context_from_request(body: dict[str, Any], *, workspace: str | None = None) -> dict[str, Any] | None:
    product_id = str(body.get("product_id") or body.get("productId") or "").strip()
    if not product_id:
        return None
    product = get_product(product_id)
    if not product:
        raise ValueError("AI product not found")

    product_workspace = Path(product["workspace_path"]).expanduser().resolve()

    intent = str(body.get("product_intent") or body.get("productIntent") or body.get("message") or "").strip()
    requested_scope = str(body.get("product_scope") or body.get("productScope") or "product_usage").strip()
    scope_explicit = bool(body.get("product_scope_explicit") or body.get("productScopeExplicit"))
    scope = infer_product_scope(intent, requested_scope, explicit=scope_explicit)
    ui_status = str(product.get("ui_status") or "").strip().lower()
    ui_mode = str(product.get("ui_mode") or "workspace").strip() or "workspace"
    product_layout = str(product.get("product_layout") or "chat_center").strip() or "chat_center"
    uses_product_canvas = product_layout in {"chat_left_canvas_right", "canvas_full"}
    if (
        not scope_explicit
        and ui_mode != "chat_only"
        and uses_product_canvas
        and scope == "product_usage"
        and ui_status in {"", "empty", "failed"}
    ):
        scope = "product_init"
    elif ui_mode != "chat_only" and scope == "product_builder" and ui_status in {"", "empty", "failed"}:
        scope = "product_init"
    # 会话线由最终 scope 推导:build 线承载 init/builder,use 线承载 usage。
    line = "build" if scope in {"product_init", "product_builder"} else "use"
    # 工作区校验只对造物线生效:造物线要写产品画布,必须落在产品目录;
    # 使用线在自己的会话工作区运行,结构上无法触碰 product.json / 画布文件。
    if workspace and line == "build":
        requested_workspace = Path(workspace).expanduser().resolve()
        if requested_workspace != product_workspace:
            raise ValueError("AI product workspace does not match this session")
    return {
        "id": product["id"],
        "kind": product.get("kind"),
        "title": product.get("title") or "AI 产品",
        "avatar": product.get("avatar") or "",
        "desc": product.get("desc") or "",
        "source_prompt": product.get("source_prompt") or "",
        "product_type": product.get("product_type") or "custom",
        "ui_mode": ui_mode,
        "product_layout": product_layout,
        "canvas_label": product.get("canvas_label") or "",
        "workspace_path": str(product_workspace),
        "preview_entry": product.get("preview_entry") or "index.html",
        "preview_url": product.get("preview_url") or "",
        "ui_status": product.get("ui_status") or "empty",
        "skills": product.get("skills") if isinstance(product.get("skills"), list) else [],
        "tools": product.get("tools") if isinstance(product.get("tools"), list) else [],
        "scope": scope,
        "line": line,
        "intent": intent,
    }


def product_ephemeral_prompt(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    title = context.get("title") or "AI 产品"
    avatar = context.get("avatar") or ""
    desc = context.get("desc") or ""
    source_prompt = context.get("source_prompt") or ""
    workspace_path = context.get("workspace_path") or ""
    preview_entry = context.get("preview_entry") or "index.html"
    preview_url = context.get("preview_url") or ""
    product_type = context.get("product_type") or "custom"
    ui_mode = context.get("ui_mode") or "workspace"
    product_layout = context.get("product_layout") or "chat_center"
    canvas_label = context.get("canvas_label") or ""
    scope = context.get("scope") or "product_usage"
    intent = context.get("intent") or ""
    skills = [str(item) for item in context.get("skills") or [] if item]
    tools = [str(item) for item in context.get("tools") or [] if item]
    capability_items = []
    for item in [*skills, *tools]:
        label = CAPABILITY_LABELS.get(item, "")
        capability_items.append(f"{item} ({label})" if label else item)
    ppt_like = product_type == "ppt" or "ppt" in f"{title} {desc} {source_prompt}".lower() or any(
        token in f"{title} {desc} {source_prompt}" for token in ("幻灯", "演示", "路演", "汇报")
    )

    scope_guidance = {
        "product_init": (
            "This turn initializes the selected AI product. Do not stop at naming or planning. "
            "Create or replace a first usable product interface in the product workspace. "
            "Prioritize speed: after any truly required skill loading, immediately write index.html, style.css, and app.js. "
            "Do not wait to ask clarifying questions when the creation request already gives a product direction; choose reasonable defaults and make them editable in the UI. "
            "Do not broadly inspect the repository, search unrelated files, generate images, run build tools, or polish visual details before the first UI files exist unless the user explicitly asked for those outputs. "
            "The UI should match the user's product idea, stay simple, and make the first task easy to start."
        ),
        "product_builder": (
            "This turn is about changing the selected AI product itself. If the user asks for UI, "
            "flow, layout, default fields, identity, avatar, skills/tools, or product behavior changes, "
            "edit the product workspace files directly and then summarize the change. For product identity "
            "or configuration changes, update product.json in the product workspace."
        ),
        "product_usage": (
            "This turn is normal use of the selected AI product. Complete the user's task naturally. "
            "Do NOT modify the product's own definition or interface in this scope: never edit product.json, "
            "and never rewrite the product canvas files (index.html, style.css, app.js) in the product workspace. "
            "Producing task outputs (decks, documents, data, images) in the workspace is fine; changing the product "
            "ITSELF is not. If the user wants to change the product's UI, workflow, identity, or defaults, do not do it "
            "here — tell them this belongs to the product's 调整 (adjust) entry, which switches to the builder scope where "
            "such changes are made."
        ),
    }.get(scope, "")

    lines = [
        "Next AI product runtime:",
        "- The user has selected one AI product. This is not an external app-builder task and not a generic assistant chat.",
        f"- Product title: {title}",
        avatar and f"- Product avatar: {avatar}",
        f"- Product type: {product_type}",
        f"- Product UI mode: {ui_mode}",
        f"- Product page layout: {product_layout}",
        canvas_label and f"- Product canvas label: {canvas_label}",
        f"- Product workspace: {workspace_path}",
        f"- Product preview entry: {preview_entry}",
        preview_url and f"- Product preview URL: {preview_url}",
        desc and f"- Product responsibility: {desc}",
        source_prompt and f"- Original creation request: {source_prompt}",
        intent and f"- Current user intent: {intent}",
        capability_items and f"- Enabled product capabilities: {', '.join(capability_items)}",
        skills and f"- Product skills: {', '.join(skills)}",
        tools and f"- Preferred product tools: {', '.join(tools)}",
        f"- Runtime scope: {scope}",
        f"- Scope guidance: {scope_guidance}",
        "",
        "Direct product UI contract:",
        "- When this turn is product_init or product_builder, you should edit files in the product workspace instead of only describing a design.",
        "- Product identity/config lives in product.json. For avatar/name/description/placeholder/skills/tools/ui_mode/product_layout/canvas_label changes, update product.json rather than shell code.",
        "- If ui_mode is chat_only, keep the product as a pure chat product unless the user explicitly asks for a visible product canvas.",
        "- If you create a visible product UI, set product_layout in product.json: use chat_left_canvas_right for side-by-side work surfaces, or canvas_full when the product UI should be the main page, such as character chat, games, image editors, or other immersive products.",
        "- For canvas_full, the product UI owns the primary user input. Build the product's own input/output flow and do not rely on the host composer for normal product use; the host composer is reserved for adjusting the product.",
        "- If the product UI needs AI inside its own controls, include /static/product-bridge-sdk.js before the product's app script and call window.NextAI.chat.send({text, action, context}). Do not fetch /api/chat or call model APIs directly from product code.",
        "- If the product UI needs durable task state, use window.NextAI.state.get/set/remove. State is scoped to the current product plus current session by default; use {scope:'product'} only for product-wide preferences.",
        "- window.NextAI.storage is only a sandbox-safe fallback for temporary client storage. Do not rely on raw localStorage for product chat history, task data, or generated UI state.",
        "- Prefer a small browser-native static interface first: index.html, style.css, app.js. Avoid build steps unless the user asked for them.",
        "- For product_init, first write the minimal useful UI files, then optionally inspect, refine, or explain. The first UI can be simple; it must be real and usable.",
        "- For product_init, use editable defaults rather than asking the user to clarify every field. The user can continue chatting to change the product later.",
        "- In product_usage scope, treat product.json and the canvas files (index.html/style.css/app.js) as read-only. Editing the product itself belongs to the builder scope reached via the 调整 (adjust) entry, not to ordinary use turns. When a use-scope turn seems to want a product change, say so and point the user to 调整 instead of editing files.",
        "- Chat remains the control surface. The product UI is the evolving working surface; it can sit beside chat or become the main page when product_layout is canvas_full.",
        "- Product skills/tools are the product's configured capability hints. Prefer matching runtime skills or tools when they are available, and say clearly when a configured capability is unavailable.",
        "- Keep the first product UI clean, legible, and task-focused; no marketing landing page unless the requested product is a landing page.",
        "- After file changes, briefly tell the user what changed and what they can do next.",
        "- Do not emit hidden UI state blocks. If the UI should change, edit the product workspace files directly.",
    ]
    if str(context.get("id") or "") == "ppt-designer":
        # Built-in PPT Designer has a fixed stage-driven canvas on the right. The canvas
        # is a surface FOR this conversation: it auto-expands to the right stage when your
        # reply carries the agreed structured blocks. Drive it through normal chat.
        lines.extend(
            [
                "",
                "PPT Designer canvas contract (drive the right canvas through conversation):",
                "- EASIEST & most reliable: write the deck state to a file `state.json` in the product workspace; "
                "the canvas reads it after every turn. Schema (write only the parts you have): "
                '{"title": "...", "style": "minimal|dark-tech|corporate|chinese|editorial|warm", '
                '"stage": "brief|outline|slides", "outline": [{"title": "...", "points": ["..."], "notes": "..."}], '
                '"slides": [{"title": "...", "imgUrl": "/api/products/ppt-designer/preview/outputs/<deck>/slide-01.png", "notes": "..."}]}. '
                "Writing this file is the smoothest way to put your content into the GUI — prefer it.",
                "- Alternative (if you'd rather not write a file): append the fenced block below. When you propose or refine the deck plan, END your reply with this — the canvas auto-expands to an editable outline:",
                '  ```outline.json',
                '  {"title":"Deck title","slides":[{"title":"Slide title","points":["point 1","point 2"],"notes":"speaker notes"}]}',
                '  ```',
                "- To generate the actual slides (this product's signature is GPT Image 2 decks), run from the product root: "
                "`python ppt-skill/ppt.py gen <deck> \"<per-slide prompt>\" --quality high` (needs ppt-skill/.env fal key + ppt-skill/requirements.txt; output lands in outputs/<deck>/). "
                "Then END your reply with this block so the canvas shows the slides:",
                '  ```js',
                '  window.PPT.loadImages("<title>", "<deck>", [{slot:1, imgUrl:"/api/products/ppt-designer/preview/outputs/<deck>/slide-01.png", title:"Slide 1"}]);',
                '  ```',
                "- If the fal key or deps are missing, say exactly what to set up; do not pretend slides were generated.",
                "- When you want the user to choose a visual style, include the token `style.pick` in your reply — the canvas expands a clickable style picker; their pick comes back to you as a message.",
                "- Chat is the control channel; the canvas reflects the conversation. Keep prose natural; just append the block at the end.",
            ]
        )
    elif ppt_like:
        lines.extend(
            [
                "",
                "PPT product UI guidance:",
                "- If you create or update this product UI, make it feel like a working PPT product, not a landing page.",
                "- Useful first UI regions: topic/subject, audience, page count, style, outline, slide/page thumbnails, speaker notes, assets/references, and next-step controls.",
                "- Keep the chat as the decision/control channel; use the UI for task state, editable inputs, and previewable PPT structure.",
            ]
        )
    if scope == "product_builder" and (ui_mode == "chat_only" or product_layout == "chat_only"):
        lines.extend(
            [
                "",
                "Chat-only product adjustment:",
                "- This is a chat-only product (no product canvas). 'Adjusting' it means changing its identity, role, "
                "description, avatar, skills, or tools via product.json — NOT generating index.html/style.css/app.js.",
                "- Do not create a visible product canvas unless the user explicitly asks this chat-only product to become a UI product.",
            ]
        )
    if scope == "product_usage" and (ui_mode == "chat_only" or product_layout == "chat_only"):
        lines.extend(
            [
                "",
                "Suggest making it a product (chat-only usage):",
                "- Help with the user's request normally in chat. Do NOT grow your own canvas — you are a chat-only product.",
                "- If the request is a REUSABLE tool, app, generator, tracker, or repeatable workflow (e.g. a timer, "
                "calculator, habit tracker, flashcards, an image/PPT generator, a role-play chat) that the user would "
                "likely come back to, then AFTER your normal answer, append exactly ONE suggestion marker on its own line:",
                '  [[NEXT_AI_SUGGEST_PRODUCT]]{"title":"<short product name>","prompt":"<one-sentence creation request>","type":"interactive|ppt|image|research|data"}[[/NEXT_AI_SUGGEST_PRODUCT]]',
                "- The marker is machine-read by the host to offer a one-click 'make it a dedicated product' button; do not describe the marker in prose.",
                "- Only emit it when the thing is genuinely reusable. For one-off questions, writing, analysis, or chitchat, do NOT emit it.",
                "- Emit at most one marker per reply.",
            ]
        )
    return "\n".join(str(line) for line in lines if line)

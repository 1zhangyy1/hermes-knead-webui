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

# The Builder Agent (调整/Shape line) is Knead's product engineer, not the product's
# in-character runtime. It always gets the strong product-engineering toolset regardless
# of how light the product's own use-tools are; the product's own tools (e.g. image_gen)
# are unioned on top so it can still exercise the product's own capabilities.
BUILDER_BASE_TOOLSET = ("skills", "file", "terminal", "code_execution")
_MANIFEST_SKIP = {"versions", "outputs", ".venv", "__pycache__", "node_modules", ".git"}


def _product_file_manifest(workspace: Path, limit: int = 40) -> list[str]:
    """Top-level source files/dirs in the product workspace, for the Builder Agent's
    context — so the engineer sees the real structure instead of blind-exploring.
    Skips runtime junk (generated output, venvs, caches, version history)."""
    try:
        names: list[str] = []
        for p in sorted(workspace.iterdir()):
            if p.name in _MANIFEST_SKIP or p.name.startswith("."):
                continue
            names.append(p.name + "/" if p.is_dir() else p.name)
            if len(names) >= limit:
                break
        return names
    except Exception:
        return []


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
    product_skills = product.get("skills") if isinstance(product.get("skills"), list) else []
    product_tools = product.get("tools") if isinstance(product.get("tools"), list) else []
    if line == "build":
        # Builder line: the strong product-engineering toolset ∪ the product's own tools
        # (so e.g. AI Otome's image_gen still works while building). Plus a file manifest
        # so the engineer sees the product structure up front.
        effective_tools = list(dict.fromkeys([*BUILDER_BASE_TOOLSET, *product_tools]))
        files = _product_file_manifest(product_workspace)
    else:
        # Use line: keep the product's own (intentionally light) toolset untouched, so a
        # use turn cannot edit the product's own files.
        effective_tools = product_tools
        files = []
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
        "skills": product_skills,
        "tools": effective_tools,
        "files": files,
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
    system_prompt = context.get("system_prompt") or ""
    instructions = context.get("instructions") or ""
    workspace_path = context.get("workspace_path") or ""
    preview_entry = context.get("preview_entry") or "index.html"
    preview_url = context.get("preview_url") or ""
    product_type = context.get("product_type") or "custom"
    ui_mode = context.get("ui_mode") or "workspace"
    product_layout = context.get("product_layout") or "chat_center"
    canvas_label = context.get("canvas_label") or ""
    scope = context.get("scope") or "product_usage"
    # Build line carries product_init + product_builder; use line carries product_usage.
    line = context.get("line") or ("build" if scope in {"product_init", "product_builder"} else "use")
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
            "Shape the first usable version of this AI product, not necessarily a UI. "
            "Choose the smallest useful form from the user's request: (1) chat-only/config-only, by updating product.json identity, intended behavior, placeholder, suggestions, skills/tools, ui_mode=chat_only, and product_layout=chat_only; "
            "or (2) workspace UI, by writing minimal working index.html/style.css/app.js and updating product.json to the right workspace layout. "
            "If the request is mainly about persona, default behavior, prompts, skills, tools, or a normal chat assistant, prefer chat-only/config-only. "
            "If repeated work would be easier with visible controls, state, files, previews, or interactive affordances, create the smallest useful workspace UI. "
            "Do not wait to ask clarifying questions when the creation request gives a direction; choose reasonable defaults and make them easy to revise later. "
            "The visible user message is the user's original request, not an internal build command. After shaping the product, reply naturally as this AI would; do not quote or explain internal product.json/workspace instructions unless the user asks."
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

    files = [str(f) for f in (context.get("files") or [])]

    # ── Shared identity header: both agents need to know which product this is. ──
    lines = [
        "Knead product runtime:",
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
        system_prompt and f"- Product behavior prompt: {system_prompt}",
        instructions and f"- Product instructions: {instructions}",
        intent and f"- Current user intent: {intent}",
        f"- Runtime scope: {scope}",
        f"- Scope guidance: {scope_guidance}",
    ]

    if line == "build":
        # ── Builder Agent: Knead's product engineer for THIS product. ──
        # Distinct identity, tools, files and skills from the Use Agent. It changes the
        # product by editing workspace files; it never plays the product's runtime persona.
        lines.append("")
        lines.append(
            f'You are Knead\'s product builder for "{title}". You are a product engineer — NOT the product\'s '
            "in-character persona and not its end-user assistant. Your job is to change this product itself by "
            "editing its workspace files, then explain what changed."
        )
        if source_prompt:
            lines.append(f"- What this product is (original creation request): {source_prompt}")
        lines.append(f"- Your working directory is locked to the product workspace: {workspace_path}")
        lines.append(
            "- Files you own and may read/write: product.json (identity/config), index.html, style.css, app.js "
            "(the product UI/canvas), and assets/*. Do not touch the host shell or unrelated repo files unless the "
            "user explicitly asks to change the Knead platform itself."
        )
        if files:
            lines.append(f"- Current product files: {', '.join(files)}")
        if capability_items:
            lines.append(f"- Your builder toolset: {', '.join(capability_items)}")
        lines.extend(
            [
                "",
                "Skills (load FIRST, before building):",
                "- Load the 'knead-product' skill via the skills tool — it is the authoritative contract for "
                "building/adjusting Knead products (the 4-slot model, product.json schema, the three layouts, "
                "the NextAI bridge, worked examples to read, and a minimal canvas template).",
                "- For non-trivial UI or visual work, also load the 'impeccable' frontend-design skill and follow "
                "its setup and restraint rules.",
                "",
                "Core build contract (details live in the knead-product skill):",
                "- Edit files in the product workspace directly instead of only describing a design.",
                "- Product identity/config lives in product.json: title, avatar, desc, source_prompt/intended behavior, "
                "placeholder, suggestions, skills, tools, ui_mode, product_layout, and canvas_label.",
                "- For product_init, decide whether the first useful product is chat-only/config-only or needs a workspace UI. "
                "Chat-only means update product.json and do NOT generate index.html/style.css/app.js. Workspace UI means write "
                "browser-native static files (index.html/style.css/app.js), no build steps. No marketing landing pages.",
                "- AI inside the canvas goes through /static/product-bridge-sdk.js (window.NextAI), never direct "
                "model/API calls from canvas code.",
                "- After file changes, briefly tell the user what changed and what they can do next, in user "
                "language (never internal words like canvas/version/scope on screen).",
            ]
        )
        if ppt_like:
            lines.extend(
                [
                    "",
                    "When building a PPT product UI: make it feel like a working PPT product, not a landing page. "
                    "Useful regions: topic, audience, page count, style, outline, slide thumbnails, speaker notes, next-step controls.",
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
    else:
        # ── Use Agent: the product itself, run for the user. ──
        lines.append("")
        lines.append(f'You are running "{title}" for the user. Complete the user\'s task naturally with this product\'s own capabilities.')
        if source_prompt:
            lines.append(f"- Product identity / intended behavior: {source_prompt}")
        if capability_items:
            lines.append(f"- Product capabilities: {', '.join(capability_items)}")
        lines.extend(
            [
                "- Treat product.json and the canvas files (index.html/style.css/app.js) as READ-ONLY. Producing task outputs (decks, documents, data, images) in the workspace is fine; changing the product ITSELF is not.",
                "- If the user wants to change the product's UI, workflow, identity, or defaults, do not do it here — tell them it belongs to the product's 调整 (adjust) entry, which switches to the builder.",
                "- Chat remains the control surface; the product UI is the working surface beside it, or the main page when product_layout is canvas_full.",
                "- Say clearly when a configured capability is unavailable instead of pretending.",
            ]
        )
        if str(context.get("id") or "") == "ppt-designer":
            # Built-in PPT Designer has a fixed stage-driven canvas. During USE the agent
            # drives that canvas by writing state (file) or appending structured blocks.
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
        if ui_mode == "chat_only" or product_layout == "chat_only":
            lines.extend(
                [
                    "",
                    "Suggest making it a product (chat-only usage):",
                    "- Help with the user's request normally in chat. Do NOT grow your own canvas — you are a chat-only product.",
                    "- If the request is a REUSABLE tool, app, generator, tracker, or repeatable workflow (e.g. a timer, "
                    "calculator, habit tracker, flashcards, an image/PPT generator, a role-play chat) that the user would "
                    "likely come back to, then AFTER your normal answer, append exactly ONE suggestion marker on its own line:",
                    '  [[KNEAD_SUGGEST_PRODUCT]]{"title":"<short product name>","prompt":"<one-sentence creation request>","type":"interactive|ppt|image|research|data"}[[/KNEAD_SUGGEST_PRODUCT]]',
                    "- The marker is machine-read by the host to offer a one-click 'make it a dedicated product' button; do not describe the marker in prose.",
                    "- Only emit it when the thing is genuinely reusable. For one-off questions, writing, analysis, or chitchat, do NOT emit it.",
                    "- Emit at most one marker per reply.",
                ]
            )
    return "\n".join(str(line) for line in lines if line)

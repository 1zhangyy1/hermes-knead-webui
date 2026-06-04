"""Runtime product context passed to Hermes Agent turns.

The frontend should not hide product instructions inside the user's visible
message. It sends structured fields, and this module turns them into a WebUI-only
ephemeral prompt.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from api.products import get_product

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
    r"(?:界面|页面|UI|布局|工作流|流程|表单|面板|模块|产品界面|产品UI)"
    r"|"
    r"(?:不改|不动|不调整|不修改|不更新).{0,16}"
    r"(?:界面|页面|UI|布局|工作流|流程|表单|面板|模块|产品界面|产品UI)"
    r")",
    re.IGNORECASE,
)


def infer_product_scope(intent: str, requested_scope: str = "product_usage") -> str:
    """Infer product runtime scope when the frontend misses a builder intent."""

    scope = requested_scope if requested_scope in PRODUCT_SCOPES else "product_usage"
    if scope in {"product_init", "product_builder"}:
        return scope
    seed = str(intent or "").strip()
    if not seed:
        return scope
    if _PRODUCT_BUILDER_NEGATION_RE.search(seed):
        return scope
    if _PRODUCT_BUILDER_RE.search(seed):
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
        session_scope = str(getattr(session, "product_scope", None) or "").strip()
        if not has_existing_turns and session_scope in {"product_init", "product_builder"}:
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
    if workspace:
        requested_workspace = Path(workspace).expanduser().resolve()
        if requested_workspace != product_workspace:
            raise ValueError("AI product workspace does not match this session")

    intent = str(body.get("product_intent") or body.get("productIntent") or body.get("message") or "").strip()
    requested_scope = str(body.get("product_scope") or body.get("productScope") or "product_usage").strip()
    scope = infer_product_scope(intent, requested_scope)
    ui_status = str(product.get("ui_status") or "").strip().lower()
    ui_mode = str(product.get("ui_mode") or "workspace").strip() or "workspace"
    if ui_mode != "chat_only" and scope in {"product_usage", "product_builder"} and ui_status in {"", "empty", "failed"}:
        scope = "product_init"
    return {
        "id": product["id"],
        "kind": product.get("kind"),
        "title": product.get("title") or "AI 产品",
        "avatar": product.get("avatar") or "",
        "desc": product.get("desc") or "",
        "source_prompt": product.get("source_prompt") or "",
        "product_type": product.get("product_type") or "custom",
        "ui_mode": ui_mode,
        "workspace_path": str(product_workspace),
        "preview_entry": product.get("preview_entry") or "index.html",
        "preview_url": product.get("preview_url") or "",
        "ui_status": product.get("ui_status") or "empty",
        "skills": product.get("skills") if isinstance(product.get("skills"), list) else [],
        "tools": product.get("tools") if isinstance(product.get("tools"), list) else [],
        "scope": scope,
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
            "Do not edit the product preview UI files for ordinary task answers. If the user explicitly asks to change the product interface or workflow, update the product workspace files directly."
        ),
    }.get(scope, "")

    lines = [
        "Next AI product runtime:",
        "- The user has selected one AI product. This is not an external app-builder task and not a generic assistant chat.",
        f"- Product title: {title}",
        avatar and f"- Product avatar: {avatar}",
        f"- Product type: {product_type}",
        f"- Product UI mode: {ui_mode}",
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
        "- Product identity/config lives in product.json. For avatar/name/description/placeholder/skills/tools/ui_mode changes, update product.json rather than shell code.",
        "- If ui_mode is chat_only, keep the product as a pure chat product unless the user explicitly asks for a visible workspace UI.",
        "- Prefer a small browser-native static interface first: index.html, style.css, app.js. Avoid build steps unless the user asked for them.",
        "- For product_init, first write the minimal useful UI files, then optionally inspect, refine, or explain. The first UI can be simple; it must be real and usable.",
        "- For product_init, use editable defaults rather than asking the user to clarify every field. The user can continue chatting to change the product later.",
        "- For product_usage, answer in chat and do not rewrite index.html/style.css/app.js unless the user clearly asks to change the product UI or workflow.",
        "- Chat remains the control surface. The product UI is the evolving working surface beside chat.",
        "- Product skills/tools are the product's configured capability hints. Prefer matching runtime skills or tools when they are available, and say clearly when a configured capability is unavailable.",
        "- Keep the first product UI clean, legible, and task-focused; no marketing landing page unless the requested product is a landing page.",
        "- After file changes, briefly tell the user what changed and what they can do next.",
        "- Do not emit hidden UI state blocks. If the UI should change, edit the product workspace files directly.",
    ]
    if ppt_like:
        lines.extend(
            [
                "",
                "PPT product UI guidance:",
                "- If you create or update this product UI, make it feel like a working PPT product, not a landing page.",
                "- Useful first UI regions: topic/subject, audience, page count, style, outline, slide/page thumbnails, speaker notes, assets/references, and next-step controls.",
                "- Keep the chat as the decision/control channel; use the UI for task state, editable inputs, and previewable PPT structure.",
                "- For a normal PPT request while the UI is empty, both help with the requested PPT and create the first reusable PPT product interface.",
            ]
        )
    return "\n".join(str(line) for line in lines if line)

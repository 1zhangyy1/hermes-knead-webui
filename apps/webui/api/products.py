"""Persistent AI product registry for the Next AI layer.

An AI product owns a product page. Chat is the stable core block in that page;
some products also open a product canvas from files in their directory.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.config import REPO_ROOT, STATE_DIR
from api.workspace import load_workspaces, save_workspaces

PRODUCTS_FILE = STATE_DIR / "ai_products.json"


def _discover_project_root() -> Path:
    raw = os.getenv("NEXT_AI_PROJECT_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    for candidate in (REPO_ROOT, *REPO_ROOT.parents):
        if (candidate / "PRODUCT.md").exists() and (candidate / "package.json").exists():
            return candidate.resolve()
    return REPO_ROOT.resolve()


PROJECT_ROOT = _discover_project_root()
PRODUCTS_DIR = Path(
    os.getenv("NEXT_AI_PRODUCTS_DIR", str(PROJECT_ROOT / "products"))
).expanduser().resolve()
PRODUCT_UI_SNAPSHOT_FILES = ("index.html", "style.css", "app.js", "product.json")
PRODUCT_UI_SNAPSHOT_EXCLUDED_DIRS = {"versions", "__pycache__", "node_modules", ".git"}
PRODUCT_UI_SNAPSHOT_EXCLUDED_FILES = {"README.md", ".DS_Store"}
PRODUCT_UI_SNAPSHOT_MAX_FILES = 200
PRODUCT_UI_SNAPSHOT_MAX_FILE_BYTES = 10 * 1024 * 1024
BUILTIN_PRODUCTS: tuple[dict[str, Any], ...] = (
    {
        "id": "general",
        "kind": "general",
        "title": "General AI",
        "avatar": "G",
        "desc": "Open-ended chat for quick questions, writing, analysis, and files.",
        "placeholder": "Say what you want to do...",
        "suggestions": [
            ["Help me organize today’s work into clear next steps.", "Plan my day"],
            ["Rewrite this copy so it is clearer and more professional.", "Polish copy"],
            ["Analyze this problem and give me a few possible paths.", "Analyze a problem"],
        ],
        "source_prompt": "Built-in AI product: General AI. It stays as normal chat by default. Its identity, flow, skills, and tools belong to itself.",
        "product_type": "general",
        "ui_mode": "chat_only",
        "product_layout": "chat_only",
        "canvas_label": "",
        "ui_status": "ready",
        "tools": ["skills", "file", "terminal", "code_execution"],
        "builtin": True,
    },
    {
        "id": "ppt-designer",
        "kind": "ppt",
        "title": "PPT Designer",
        "avatar": "P",
        "desc": "Tell me the topic, audience, and goal. I will shape the outline, slides, and speaker notes.",
        "placeholder": "Describe this deck, or upload material...",
        "suggestions": [
            ["Help me create a product intro deck. First confirm the topic, audience, and outline.", "Start from topic"],
            ["I have source material. Turn it into a presentation structure.", "Use source material"],
            ["Help me improve an existing deck structure. First tell me what should change.", "Improve structure"],
        ],
        "source_prompt": "Built-in AI product: PPT Designer. It helps users create and refine presentations through chat, then opens a PPT workspace when structure is useful.",
        "product_type": "ppt",
        "ui_mode": "workspace",
        "product_layout": "chat_left_canvas_right",
        "canvas_label": "PPT workspace",
        "ui_status": "empty",
        "skills": ["presentations", "office"],
        "tools": ["skills", "file", "terminal", "code_execution"],
        "builtin": True,
    },
    {
        "id": "ai-otome",
        "kind": "ai-otome",
        "title": "AI Otome",
        "avatar": "♡",
        "desc": "A single-character AI otome companion with memory, mood, affection, and choice-driven scenes.",
        "placeholder": "Say something to Mira...",
        "suggestions": [
            ["Tell Mira you came to see her and let her choose the next scene.", "Start with Mira"],
            ["Ask Mira what she remembers about you.", "Check memory"],
            ["Make the mood warmer and more romantic.", "Shape the mood"],
        ],
        "source_prompt": "Built-in AI product: AI Otome. It is a single-character companion experience. The product UI owns the use flow. AI drives dialogue, mood, affection, memories, choices, and scene changes.",
        "product_type": "interactive",
        "ui_mode": "workspace",
        "product_layout": "canvas_full",
        "canvas_label": "Otome companion",
        "ui_status": "ready",
        "skills": ["imagegen"],
        "tools": ["skills", "image_gen"],
        "builtin": True,
    },
)
PRODUCT_TOOLSET_ALIASES = {
    "officecli": ("skills", "file", "terminal", "code_execution"),
    "office-cli": ("skills", "file", "terminal", "code_execution"),
    "image-generation": ("image_gen",),
    "imagegen": ("image_gen",),
    "web-research": ("browser", "web"),
    "spreadsheet-analysis": ("skills", "file", "terminal", "code_execution"),
}
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(raw: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(raw).lower()).strip("-")
    return cleaned[:64] or "product"


def _product_dir(product_id: str) -> Path:
    return PRODUCTS_DIR / _safe_id(product_id)


def _unique_strings(items: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    if not isinstance(items, list):
        return result
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def normalize_product_toolsets(items: Any) -> list[str]:
    """Return real Hermes CLI toolset names for product-level tool choices."""

    result: list[str] = []
    seen: set[str] = set()
    for item in _unique_strings(items):
        replacements = PRODUCT_TOOLSET_ALIASES.get(item, (item,))
        for replacement in replacements:
            value = str(replacement or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
    return result


def suggest_product_capabilities(*, title: str = "", source_prompt: str = "", product_type: str = "") -> dict[str, list[str]]:
    """Suggest small default skills/tools from the product's responsibility."""

    seed = f"{title} {source_prompt} {product_type}".lower()
    skills: list[str] = []
    tools: list[str] = []
    if product_type == "ppt" or any(token in seed for token in ("ppt", "powerpoint", "slide", "slides", "deck", "演示", "幻灯", "路演", "汇报")):
        skills.extend(["presentations", "office"])
        tools.extend(["skills", "file", "terminal", "code_execution"])
    if product_type == "image" or any(token in seed for token in ("image", "photo", "poster", "visual", "图片", "图像", "生图", "绘图", "海报", "封面", "插画", "头像", "视觉")):
        skills.append("imagegen")
        tools.extend(["skills", "file", "image_gen"])
    if product_type == "research" or any(token in seed for token in ("research", "web", "browser", "调研", "研究", "资料", "报告", "竞品", "行业")):
        skills.append("browser")
        tools.extend(["skills", "browser", "web", "file"])
    if product_type == "data" or any(token in seed for token in ("data", "sheet", "spreadsheet", "table", "数据", "表格", "指标", "看板", "报表")):
        skills.append("spreadsheets")
        tools.extend(["skills", "file", "terminal", "code_execution"])
    return {"skills": _unique_strings(skills), "tools": normalize_product_toolsets(tools)}


def _safe_version_id(raw: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(raw)).strip("-")
    return cleaned[:80] or f"v-{int(datetime.now(timezone.utc).timestamp())}"


def _seed_index_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI workspace</title>
  <style>
    body{margin:0;font:14px/1.6 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#171717;background:#fff}
    main{min-height:100vh;display:grid;place-items:center;padding:32px}
    section{max-width:520px;text-align:center}
    h1{margin:0 0 8px;font-size:22px;letter-spacing:0}
    p{margin:0;color:#737373}
  </style>
</head>
<body>
  <main>
    <section>
      <h1>This AI does not have a workspace yet</h1>
      <p>Keep chatting with it. The agent can create index.html, style.css, or app.js in this workspace.</p>
    </section>
  </main>
</body>
</html>
"""


def _chat_only_seed_index_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>General AI</title>
  <style>
    body{margin:0;font:14px/1.6 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#171717;background:#fff}
    main{min-height:100vh;display:grid;place-items:center;padding:32px}
    section{max-width:520px;text-align:center}
    h1{margin:0 0 8px;font-size:22px;letter-spacing:0}
    p{margin:0;color:#737373}
  </style>
</head>
<body>
  <main>
    <section>
      <h1>This AI uses the default chat page</h1>
      <p>It does not need a side workspace. Return to the main page and keep chatting.</p>
    </section>
  </main>
</body>
</html>
"""


def _read_state() -> dict[str, Any]:
    if not PRODUCTS_FILE.exists():
        return {"products": []}
    try:
        data = json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    items = data.get("products") if isinstance(data, dict) else None
    if not isinstance(items, list):
        items = []
    return {"products": [_normalize_product(item) for item in items if isinstance(item, dict)]}


def _write_state(state: dict[str, Any]) -> None:
    PRODUCTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PRODUCTS_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_product(item: dict[str, Any]) -> dict[str, Any]:
    title = str(item.get("title") or item.get("name") or "AI product").strip() or "AI product"
    product_id = _safe_id(str(item.get("id") or item.get("kind") or title))
    workspace_path = str(item.get("workspace_path") or _product_dir(product_id))
    created_at = str(item.get("created_at") or _now())
    updated_at = str(item.get("updated_at") or created_at)
    preview_url = f"/api/products/{product_id}/preview"
    sessions = item.get("sessions") if isinstance(item.get("sessions"), list) else []
    skills = item.get("skills") if isinstance(item.get("skills"), list) else []
    tools = item.get("tools") if isinstance(item.get("tools"), list) else []
    versions = item.get("versions") if isinstance(item.get("versions"), list) else []
    product_type = str(item.get("product_type") or item.get("productType") or "custom").strip() or "custom"
    ui_mode = str(item.get("ui_mode") or item.get("uiMode") or "workspace").strip() or "workspace"
    raw_layout = str(item.get("product_layout") or item.get("productLayout") or item.get("layout") or "").strip()
    if not raw_layout:
        raw_layout = (
            "chat_only"
            if ui_mode == "chat_only"
            else "chat_left_canvas_right"
            if product_type in {"ppt", "research", "data", "image"}
            else "chat_center"
        )
    allowed_layouts = {"chat_only", "chat_center", "chat_left_canvas_right", "canvas_full"}
    product_layout = raw_layout if raw_layout in allowed_layouts else "chat_center"
    if ui_mode == "chat_only":
        product_layout = "chat_only"
    elif product_layout == "chat_only":
        ui_mode = "chat_only"
    ui_status = str(item.get("ui_status") or item.get("status") or "empty").strip() or "empty"
    if ui_mode == "chat_only" and ui_status in {"empty", "failed"}:
        ui_status = "ready"
    canvas_label = str(item.get("canvas_label") or item.get("canvasLabel") or "").strip()
    if not canvas_label and product_layout != "chat_only":
        canvas_label = "Workspace"
    return {
        "id": product_id,
        "kind": str(item.get("kind") or f"custom-{product_id}"),
        "title": title,
        "avatar": str(item.get("avatar") or "").strip(),
        "desc": str(item.get("desc") or item.get("description") or "").strip(),
        "placeholder": str(item.get("placeholder") or f'Tell "{title}" what you want to finish...').strip(),
        "suggestions": item.get("suggestions") if isinstance(item.get("suggestions"), list) else [],
        "source_prompt": str(item.get("source_prompt") or item.get("sourcePrompt") or "").strip(),
        "product_type": product_type,
        "ui_mode": ui_mode,
        "product_layout": product_layout,
        "canvas_label": canvas_label,
        "workspace_path": workspace_path,
        "preview_entry": str(item.get("preview_entry") or "index.html"),
        "preview_url": preview_url,
        "ui_status": ui_status,
        "ui_error_type": str(item.get("ui_error_type") or "").strip(),
        "ui_error_message": str(item.get("ui_error_message") or "").strip(),
        "last_session_id": str(item.get("last_session_id") or "").strip(),
        "sessions": [str(session_id) for session_id in sessions if session_id],
        "skills": [str(skill) for skill in skills if skill],
        "tools": normalize_product_toolsets(tools),
        "versions": versions,
        "builtin": bool(item.get("builtin")),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _builtin_product_ids() -> set[str]:
    return {_safe_id(str(item.get("id") or "")) for item in BUILTIN_PRODUCTS if item.get("id")}


def _ensure_builtin_products_locked() -> dict[str, Any]:
    state = _read_state()
    products = state["products"]
    changed = False
    now = _now()

    for definition in BUILTIN_PRODUCTS:
        product_id = _safe_id(str(definition.get("id") or definition.get("kind") or definition.get("title") or ""))
        if not product_id:
            continue
        definition = {**definition, "id": product_id}
        existing_index = next(
            (
                idx
                for idx, item in enumerate(products)
                if item.get("id") == product_id or item.get("kind") == definition.get("kind")
            ),
            -1,
        )
        if existing_index >= 0:
            existing = products[existing_index]
            merged = {
                **existing,
                **definition,
                "id": product_id,
                "kind": definition.get("kind") or product_id,
                "avatar": definition.get("avatar") or existing.get("avatar") or "",
                "ui_mode": definition.get("ui_mode") or existing.get("ui_mode") or "workspace",
                "product_layout": definition.get("product_layout") or existing.get("product_layout") or "",
                "canvas_label": definition.get("canvas_label") or existing.get("canvas_label") or "",
                "workspace_path": str(_product_dir(product_id).resolve()),
                "preview_url": f"/api/products/{product_id}/preview",
                "ui_status": existing.get("ui_status") or definition.get("ui_status") or "empty",
                "sessions": existing.get("sessions") if isinstance(existing.get("sessions"), list) else [],
                "versions": existing.get("versions") if isinstance(existing.get("versions"), list) else [],
                "created_at": existing.get("created_at") or now,
                "updated_at": existing.get("updated_at") or now,
                "builtin": True,
            }
            normalized = _normalize_product(merged)
            if normalized != existing:
                products[existing_index] = normalized
                changed = True
            _write_seed_files(normalized)
            _register_workspace(normalized)
            continue

        product = _normalize_product(
            {
                **definition,
                "id": product_id,
                "kind": definition.get("kind") or product_id,
                "workspace_path": str(_product_dir(product_id).resolve()),
                "preview_url": f"/api/products/{product_id}/preview",
                "created_at": now,
                "updated_at": now,
                "builtin": True,
            }
        )
        _write_seed_files(product)
        _register_workspace(product)
        products.append(product)
        changed = True

    if changed:
        _write_state({"products": products})
    return {"products": products}


def _ensure_unique_product_id(base: str, existing_ids: set[str]) -> str:
    product_id = _safe_id(base)
    if product_id not in existing_ids:
        return product_id
    for index in range(2, 1000):
        candidate = _safe_id(f"{product_id}-{index}")
        if candidate not in existing_ids:
            return candidate
    return _safe_id(f"{product_id}-{int(datetime.now().timestamp())}")


def _write_seed_files(product: dict[str, Any]) -> None:
    workspace = Path(product["workspace_path"])
    workspace.mkdir(parents=True, exist_ok=True)
    readme = workspace / "README.md"
    if not readme.exists():
        if str(product.get("ui_mode") or "") == "chat_only":
            workspace_note = "When you chat with this AI, the agent maintains its identity, prompt, skills, and tools here. It does not need a side workspace."
        else:
            workspace_note = "When you chat with this AI, the agent creates and updates its workspace files here."
        readme.write_text(
            "\n".join(
                [
                    f"# {product['title']}",
                    "",
                    product.get("desc") or "This directory is this AI's own code workspace.",
                    "",
                    workspace_note,
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    index = workspace / "index.html"
    if not index.exists():
        seed_html = _chat_only_seed_index_html() if str(product.get("ui_mode") or "") == "chat_only" else _seed_index_html()
        index.write_text(seed_html, encoding="utf-8")
    _write_manifest(product)


def _write_manifest(product: dict[str, Any]) -> None:
    workspace = Path(product["workspace_path"])
    workspace.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": product["id"],
        "kind": product.get("kind"),
        "title": product.get("title"),
        "avatar": product.get("avatar") or "",
        "desc": product.get("desc"),
        "source_prompt": product.get("source_prompt"),
        "product_type": product.get("product_type"),
        "ui_mode": product.get("ui_mode") or "workspace",
        "product_layout": product.get("product_layout") or "chat_center",
        "canvas_label": product.get("canvas_label") or "",
        "preview_entry": product.get("preview_entry") or "index.html",
        "ui_status": product.get("ui_status") or "empty",
        "skills": _unique_strings(product.get("skills") if isinstance(product.get("skills"), list) else []),
        "tools": normalize_product_toolsets(product.get("tools") if isinstance(product.get("tools"), list) else []),
        "updated_at": product.get("updated_at") or _now(),
    }
    (workspace / "product.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _register_workspace(product: dict[str, Any]) -> None:
    workspace_path = str(Path(product["workspace_path"]).expanduser().resolve())
    workspaces = load_workspaces()
    if any(item.get("path") == workspace_path for item in workspaces if isinstance(item, dict)):
        return
    workspaces.append({"path": workspace_path, "name": product["title"]})
    save_workspaces(workspaces)


def _unregister_workspace(product: dict[str, Any]) -> None:
    workspace_path = str(Path(product.get("workspace_path") or "").expanduser().resolve())
    if not workspace_path:
        return
    workspaces = load_workspaces()
    next_workspaces = [
        item
        for item in workspaces
        if not isinstance(item, dict) or item.get("path") != workspace_path
    ]
    if len(next_workspaces) != len(workspaces):
        save_workspaces(next_workspaces)


def _product_entry_generated(product: dict[str, Any]) -> bool:
    try:
        root = Path(product["workspace_path"]).resolve()
        entry_rel = str(product.get("preview_entry") or "index.html").strip("/") or "index.html"
        entry = (root / entry_rel).resolve()
        entry.relative_to(root)
    except Exception:
        return False
    if not entry.exists() or not entry.is_file():
        return False
    return not _entry_is_seed(entry)


def list_products() -> dict[str, Any]:
    with _LOCK:
        state = _ensure_builtin_products_locked()
        products = []
        for product in state["products"]:
            item = dict(product)
            entry_generated = _product_entry_generated(item)
            item["entry_generated"] = entry_generated
            item["product_canvas_available"] = entry_generated or str(item.get("ui_status") or "") == "generating"
            if entry_generated and str(item.get("ui_status") or "") in {"empty", "generating"}:
                item["ui_status"] = "ready"
            products.append(item)
        return {"products": products}


def get_product(product_id_or_kind: str) -> dict[str, Any] | None:
    key = str(product_id_or_kind or "").strip()
    if not key:
        return None
    safe_key = _safe_id(key)
    with _LOCK:
        for product in _ensure_builtin_products_locked()["products"]:
            if product["id"] == safe_key or product.get("kind") == key:
                return dict(product)
    return None


def create_product(body: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        state = _ensure_builtin_products_locked()
        products = state["products"]
        existing_ids = {item["id"] for item in products}
        title = str(body.get("title") or body.get("name") or "AI product").strip() or "AI product"
        raw_kind = str(body.get("kind") or body.get("id") or title)
        product_id = _ensure_unique_product_id(raw_kind, existing_ids)
        product = _normalize_product({**body, "id": product_id, "kind": body.get("kind") or f"custom-{product_id}"})
        product["workspace_path"] = str(_product_dir(product_id).resolve())
        product["preview_url"] = f"/api/products/{product_id}/preview"
        requested_status = str(body.get("ui_status") or product.get("ui_status") or "empty").strip() or "empty"
        product["ui_status"] = "ready" if product.get("ui_mode") == "chat_only" else requested_status
        product["sessions"] = []
        capability_defaults = suggest_product_capabilities(
            title=product.get("title") or title,
            source_prompt=product.get("source_prompt") or "",
            product_type=product.get("product_type") or "",
        )
        product["skills"] = _unique_strings(body.get("skills")) if isinstance(body.get("skills"), list) else capability_defaults["skills"]
        product["tools"] = _unique_strings(body.get("tools")) if isinstance(body.get("tools"), list) else capability_defaults["tools"]
        product["versions"] = []
        product["created_at"] = _now()
        product["updated_at"] = product["created_at"]
        _write_seed_files(product)
        _register_workspace(product)
        products.append(product)
        _write_state({"products": products})
        return {"ok": True, "product": product}


def update_product(product_id_or_kind: str, patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(patch, dict):
        patch = {}
    with _LOCK:
        state = _read_state()
        products = state["products"]
        safe_key = _safe_id(product_id_or_kind)
        index = next(
            (
                idx
                for idx, item in enumerate(products)
                if item["id"] == safe_key or item.get("kind") == str(product_id_or_kind)
            ),
            -1,
        )
        if index < 0:
            raise FileNotFoundError(product_id_or_kind)
        current = products[index]
        allowed_scalar = {
            "title",
            "avatar",
            "desc",
            "placeholder",
            "source_prompt",
            "product_type",
            "ui_mode",
            "product_layout",
            "canvas_label",
            "preview_entry",
            "ui_status",
            "ui_error_type",
            "ui_error_message",
            "last_session_id",
        }
        next_item = dict(current)
        for key in allowed_scalar:
            if key in patch:
                next_item[key] = str(patch.get(key) or "").strip()
        if "ui_status" in patch and str(patch.get("ui_status") or "").strip() != "failed":
            next_item["ui_error_type"] = ""
            next_item["ui_error_message"] = ""
        for key in ("suggestions", "skills", "tools", "versions", "sessions"):
            if key in patch and isinstance(patch.get(key), list):
                next_item[key] = patch[key]
        next_item["updated_at"] = _now()
        normalized = _normalize_product(next_item)
        products[index] = normalized
        _write_seed_files(normalized)
        _write_state({"products": products})
        return {"ok": True, "product": normalized}


def delete_product(product_id_or_kind: str, *, remove_files: bool = True) -> dict[str, Any]:
    with _LOCK:
        state = _read_state()
        products = state["products"]
        safe_key = _safe_id(product_id_or_kind)
        removed: dict[str, Any] | None = None
        kept: list[dict[str, Any]] = []
        for item in products:
            if item["id"] == safe_key or item.get("kind") == str(product_id_or_kind):
                removed = item
            else:
                kept.append(item)
        if not removed:
            raise FileNotFoundError(product_id_or_kind)
        if removed.get("builtin") or removed.get("id") in _builtin_product_ids():
            return {"ok": True, "product": removed, "removed_files": False, "skipped": "builtin"}
        _write_state({"products": kept})
        _unregister_workspace(removed)

        removed_files = False
        if remove_files:
            workspace = Path(removed.get("workspace_path") or "").expanduser().resolve()
            products_root = PRODUCTS_DIR.resolve()
            try:
                workspace.relative_to(products_root)
            except ValueError:
                workspace = Path()
            if workspace and workspace.name == removed["id"] and workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)
                removed_files = not workspace.exists()
        return {"ok": True, "product": removed, "removed_files": removed_files}


def _product_index_generated(product: dict[str, Any]) -> bool:
    try:
        return bool(product_file_status(product["id"]).get("entry_generated"))
    except Exception:
        return False


def _version_dir(product: dict[str, Any], version_id: str) -> Path:
    return Path(product["workspace_path"]).resolve() / "versions" / _safe_version_id(version_id)


def _has_excluded_snapshot_dir(parts: tuple[str, ...]) -> bool:
    return any(part in PRODUCT_UI_SNAPSHOT_EXCLUDED_DIRS for part in parts)


def _product_ui_snapshot_files(workspace: Path) -> list[str]:
    """Return product UI files that rollback should manage.

    The agent can add images, JSON, fonts, or other small assets beside the
    static UI files. Snapshot those too, while keeping runtime/version folders
    and large generated blobs out of the rollback surface.
    """

    root = workspace.resolve()
    if not root.exists():
        return []
    files: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item.relative_to(root)).lower()):
        try:
            rel_path = path.relative_to(root)
        except ValueError:
            continue
        rel_parts = rel_path.parts
        if not rel_parts:
            continue
        if _has_excluded_snapshot_dir(rel_parts[:-1]):
            continue
        if any(part.startswith(".") for part in rel_parts):
            continue
        rel = rel_path.as_posix()
        if rel in PRODUCT_UI_SNAPSHOT_EXCLUDED_FILES:
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            continue
        try:
            if path.stat().st_size > PRODUCT_UI_SNAPSHOT_MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        files.append(rel)
        if len(files) >= PRODUCT_UI_SNAPSHOT_MAX_FILES:
            break
    for rel in PRODUCT_UI_SNAPSHOT_FILES:
        if rel not in files and (root / rel).is_file():
            files.insert(0, rel)
    seen: set[str] = set()
    result: list[str] = []
    for rel in files:
        if rel in seen:
            continue
        seen.add(rel)
        result.append(rel)
    return result


def _remove_empty_dirs(root: Path) -> None:
    for child in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        try:
            rel_path = child.relative_to(root)
        except ValueError:
            continue
        if _has_excluded_snapshot_dir(rel_path.parts):
            continue
        if child.is_dir():
            try:
                child.rmdir()
            except OSError:
                pass


def _product_manifest_patch_from_workspace(product: dict[str, Any]) -> dict[str, Any]:
    """Read product-owned metadata changes written by the agent.

    Product turns may update product.json for identity/config changes such as
    avatar, placeholder, skills, tools, ui_mode, or product_layout. Keep this intentionally
    narrow so product code can evolve itself without mutating shell state.
    """

    workspace = Path(product["workspace_path"]).resolve()
    manifest_path = workspace / "product.json"
    if not manifest_path.exists() or not manifest_path.is_file():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}

    patch: dict[str, Any] = {}
    scalar_keys = {
        "title",
        "avatar",
        "desc",
        "placeholder",
        "source_prompt",
        "product_type",
        "ui_mode",
        "product_layout",
        "canvas_label",
        "preview_entry",
    }
    aliases = {
        "sourcePrompt": "source_prompt",
        "productType": "product_type",
        "uiMode": "ui_mode",
        "productLayout": "product_layout",
        "canvasLabel": "canvas_label",
        "layout": "product_layout",
        "previewEntry": "preview_entry",
    }
    for key, value in data.items():
        target_key = aliases.get(key, key)
        if target_key in scalar_keys:
            patch[target_key] = str(value or "").strip()
    for key in ("suggestions", "skills", "tools"):
        value = data.get(key)
        if isinstance(value, list):
            patch[key] = value
    return patch


def snapshot_product(product_id_or_kind: str, reason: str = "") -> dict[str, Any]:
    """Copy the current product UI files into versions/<timestamp>.

    The first seed-only product UI is skipped. That keeps rollback focused on
    meaningful product interfaces instead of restoring the empty placeholder.
    """

    with _LOCK:
        product = get_product(product_id_or_kind)
        if not product:
            raise FileNotFoundError(product_id_or_kind)
        if not _product_index_generated(product):
            return {"ok": True, "product": product, "snapshot": None, "skipped": "seed"}

        workspace = Path(product["workspace_path"]).resolve()
        if not workspace.exists():
            raise FileNotFoundError(str(workspace))

        created_at = _now()
        version_id = _safe_version_id(f"v-{created_at.replace(':', '').replace('-', '')}")
        target_dir = _version_dir(product, version_id)
        counter = 2
        while target_dir.exists():
            version_id = _safe_version_id(f"{version_id}-{counter}")
            target_dir = _version_dir(product, version_id)
            counter += 1
        target_dir.mkdir(parents=True, exist_ok=False)

        copied: list[str] = []
        for rel in _product_ui_snapshot_files(workspace):
            source = (workspace / rel).resolve()
            try:
                source.relative_to(workspace)
            except ValueError:
                continue
            if source.exists() and source.is_file():
                destination = target_dir / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                copied.append(rel)

        if not copied:
            shutil.rmtree(target_dir, ignore_errors=True)
            return {"ok": True, "product": product, "snapshot": None, "skipped": "empty"}

        snapshot = {
            "id": version_id,
            "created_at": created_at,
            "reason": str(reason or "product-ui-snapshot")[:240],
            "files": copied,
        }
        versions = [item for item in product.get("versions", []) if isinstance(item, dict)]
        versions.insert(0, snapshot)
        versions = versions[:25]
        updated = update_product(product["id"], {"versions": versions})
        return {"ok": True, "product": updated["product"], "snapshot": snapshot}


def list_product_versions(product_id_or_kind: str) -> dict[str, Any]:
    product = get_product(product_id_or_kind)
    if not product:
        raise FileNotFoundError(product_id_or_kind)
    versions = [item for item in product.get("versions", []) if isinstance(item, dict)]
    return {"ok": True, "product": product, "versions": versions}


def rollback_product(product_id_or_kind: str, version_id: str | None = None) -> dict[str, Any]:
    with _LOCK:
        product = get_product(product_id_or_kind)
        if not product:
            raise FileNotFoundError(product_id_or_kind)
        versions = [item for item in product.get("versions", []) if isinstance(item, dict)]
        if not versions:
            raise FileNotFoundError("product version")
        requested = str(version_id or "").strip()
        snapshot = None
        if requested:
            safe_requested = _safe_version_id(requested)
            snapshot = next((item for item in versions if _safe_version_id(item.get("id") or "") == safe_requested), None)
        else:
            snapshot = versions[0]
        if not snapshot:
            raise FileNotFoundError("product version")

        workspace = Path(product["workspace_path"]).resolve()
        source_dir = _version_dir(product, str(snapshot.get("id") or ""))
        if not source_dir.exists():
            raise FileNotFoundError(str(source_dir))

        snapshot_files = {str(item) for item in snapshot.get("files", []) if item}
        managed_files = set(_product_ui_snapshot_files(workspace)) | snapshot_files
        for rel in sorted(managed_files):
            destination = (workspace / rel).resolve()
            try:
                destination.relative_to(workspace)
            except ValueError:
                continue
            source = (source_dir / rel).resolve()
            try:
                source.relative_to(source_dir)
            except ValueError:
                continue
            if rel in snapshot_files and source.exists() and source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            elif destination.exists() and destination.is_file():
                destination.unlink()
        _remove_empty_dirs(workspace)

        remaining_versions = [item for item in versions if item is not snapshot]
        updated = update_product(product["id"], {"versions": remaining_versions, "ui_status": "ready"})
        return {
            "ok": True,
            "product": updated["product"],
            "restored_version": snapshot,
            "versions": remaining_versions,
        }


def record_product_session(product_id_or_kind: str, session_id: str, *, ui_status: str | None = None) -> None:
    product = get_product(product_id_or_kind)
    if not product or not session_id:
        return
    sessions = [sid for sid in product.get("sessions", []) if sid != session_id]
    sessions.insert(0, session_id)
    patch: dict[str, Any] = {
        "sessions": sessions[:50],
        "last_session_id": session_id,
    }
    if ui_status:
        patch["ui_status"] = ui_status
    update_product(product["id"], patch)


def _entry_is_seed(entry: Path) -> bool:
    try:
        content = entry.read_text(encoding="utf-8").strip()
        return content == _seed_index_html().strip() or content == _chat_only_seed_index_html().strip()
    except Exception:
        return False


def finalize_product_generation(
    product_id_or_kind: str,
    *,
    failed: bool = False,
    error_type: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any] | None:
    product = get_product(product_id_or_kind)
    if not product:
        return None
    try:
        status = product_file_status(product["id"])
    except Exception:
        status = {"entry_generated": False}
    manifest_patch = _product_manifest_patch_from_workspace(product)
    next_ui_mode = str(manifest_patch.get("ui_mode") or product.get("ui_mode") or "workspace").strip() or "workspace"
    next_product_layout = str(manifest_patch.get("product_layout") or product.get("product_layout") or "chat_center").strip() or "chat_center"
    if failed:
        next_status = "failed"
    elif next_ui_mode == "chat_only":
        next_status = "ready"
    else:
        next_status = "ready" if status.get("entry_generated") else "failed"
    patch: dict[str, Any] = {**manifest_patch, "ui_status": next_status}
    if next_status == "ready" and next_ui_mode != "chat_only" and status.get("entry_generated") and next_product_layout == "chat_center":
        patch["product_layout"] = "chat_left_canvas_right"
        if not patch.get("canvas_label") and not product.get("canvas_label"):
            patch["canvas_label"] = "Workspace"
    if next_status == "failed":
        patch["ui_error_type"] = str(error_type or "generation_failed").strip()
        patch["ui_error_message"] = str(error_message or "Workspace generation did not finish. Try again.").strip()
    else:
        patch["ui_error_type"] = ""
        patch["ui_error_message"] = ""
    try:
        updated = update_product(product["id"], patch)
        return updated.get("product")
    except Exception:
        return None


def product_file_status(product_id_or_kind: str) -> dict[str, Any]:
    product = get_product(product_id_or_kind)
    if not product:
        raise FileNotFoundError(product_id_or_kind)
    root = Path(product["workspace_path"]).resolve()
    entry_rel = str(product.get("preview_entry") or "index.html").strip("/") or "index.html"
    entry = (root / entry_rel).resolve()
    try:
        entry.relative_to(root)
    except ValueError:
        raise FileNotFoundError(entry_rel)
    assets = []
    if root.exists():
        for child in sorted(root.iterdir(), key=lambda path: path.name.lower())[:80]:
            try:
                stat = child.stat()
            except OSError:
                continue
            assets.append(
                {
                    "name": child.name,
                    "path": str(child.relative_to(root)),
                    "is_dir": child.is_dir(),
                    "size": stat.st_size if child.is_file() else None,
                    "mtime": stat.st_mtime,
                }
            )
    entry_stat = entry.stat() if entry.exists() and entry.is_file() else None
    entry_is_seed = bool(entry_stat) and _entry_is_seed(entry)
    entry_generated = bool(entry_stat) and not entry_is_seed
    ui_mode = str(product.get("ui_mode") or "workspace").strip() or "workspace"
    ui_status = str(product.get("ui_status") or "empty").strip() or "empty"
    next_ui_status = ui_status
    if ui_mode == "chat_only" and ui_status in {"empty", "failed"}:
        next_ui_status = "ready"
    elif entry_generated and ui_status in {"empty", "generating"}:
        next_ui_status = "ready"
    elif ui_mode != "chat_only" and not entry_generated and ui_status == "ready":
        next_ui_status = "failed"
    product_layout = str(product.get("product_layout") or "chat_center").strip() or "chat_center"
    should_promote_layout = entry_generated and ui_mode != "chat_only" and product_layout == "chat_center"
    if next_ui_status != ui_status:
        try:
            patch: dict[str, Any] = {"ui_status": next_ui_status}
            if should_promote_layout:
                patch["product_layout"] = "chat_left_canvas_right"
                if not product.get("canvas_label"):
                    patch["canvas_label"] = "Workspace"
            if next_ui_status == "failed":
                patch["ui_error_type"] = product.get("ui_error_type") or "entry_missing"
                patch["ui_error_message"] = product.get("ui_error_message") or "Workspace files are missing or still placeholders. You can rebuild it."
            updated = update_product(product["id"], patch)
            product = updated.get("product") or {**product, "ui_status": next_ui_status}
            ui_status = next_ui_status
        except Exception:
            ui_status = next_ui_status
    elif should_promote_layout:
        try:
            patch = {"product_layout": "chat_left_canvas_right"}
            if not product.get("canvas_label"):
                patch["canvas_label"] = "Workspace"
            updated = update_product(product["id"], patch)
            product = updated.get("product") or {**product, **patch}
        except Exception:
            pass
    return {
        "ok": True,
        "product": product,
        "root": str(root),
        "entry": entry_rel,
        "entry_exists": bool(entry_stat),
        "entry_is_seed": entry_is_seed,
        "entry_generated": entry_generated,
        "entry_size": entry_stat.st_size if entry_stat else 0,
        "entry_mtime": entry_stat.st_mtime if entry_stat else None,
        "assets": assets,
        "preview_url": product.get("preview_url"),
        "ui_status": ui_status,
    }


def preview_product_file(product_id: str, asset: str = "index.html") -> Path:
    product_id = _safe_id(product_id)
    products = {item["id"]: item for item in _read_state()["products"]}
    if product_id not in products:
        raise FileNotFoundError(product_id)
    root = Path(products[product_id]["workspace_path"]).resolve()
    rel = asset.strip("/") or "index.html"
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise FileNotFoundError(asset)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(asset)
    return target

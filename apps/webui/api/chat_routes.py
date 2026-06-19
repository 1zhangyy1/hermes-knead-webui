"""Chat route helper functions."""

from __future__ import annotations

from typing import Callable


def is_default_or_empty_session_title(title) -> bool:
    return str(title or "").strip() in ("", "Untitled", "New Chat")


def provisional_title_from_prompt(prompt: str, fallback: str = "Untitled", *, title_from_fn: Callable) -> str:
    text = str(prompt or "").strip()
    if not text:
        return fallback
    return title_from_fn([{"role": "user", "content": text}], fallback) or fallback


def product_task_title_from_request(body: dict) -> str:
    raw = body.get("product_task_title") or body.get("productTaskTitle") or ""
    title = " ".join(str(raw or "").split()).strip()
    if not title:
        return ""
    return title[:80]


def session_toolsets_from_request(
    body: dict,
    *,
    resolve_cli_toolsets_fn: Callable[[], list[str]],
    normalize_product_toolsets_fn: Callable,
) -> list[str] | None:
    raw = body.get("enabled_toolsets")
    if raw is None:
        raw = body.get("enabledToolsets")
    if raw is None:
        raw = body.get("toolsets")
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        return None
    available = set(resolve_cli_toolsets_fn())
    return [name for name in normalize_product_toolsets_fn(raw) if name in available]


def normalize_chat_attachments(raw_attachments):
    """Normalize attachment payloads from the browser."""
    normalized = []
    if not isinstance(raw_attachments, list):
        return normalized
    for item in raw_attachments:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("filename") or "").strip()
            path = str(item.get("path") or "").strip()
            mime = str(item.get("mime") or "").strip()
            att = {"name": name or path, "path": path, "mime": mime}
            size = item.get("size")
            if isinstance(size, int):
                att["size"] = size
            is_image = item.get("is_image")
            if isinstance(is_image, bool):
                att["is_image"] = is_image
            normalized.append(att)
        else:
            value = str(item).strip()
            if value:
                normalized.append({"name": value, "path": "", "mime": ""})
    return normalized

"""Plugin visibility helpers for the WebUI route layer."""

from __future__ import annotations

import logging
from typing import Callable

from api.helpers import j

logger = logging.getLogger(__name__)

PLUGIN_VISIBILITY_HOOKS = (
    "pre_tool_call",
    "post_tool_call",
    "pre_llm_call",
    "post_llm_call",
)
PLUGIN_VISIBILITY_HOOK_SET = set(PLUGIN_VISIBILITY_HOOKS)


def get_plugin_manager_for_visibility():
    """Return Hermes Agent's plugin manager for read-only WebUI visibility."""
    from hermes_cli.plugins import get_plugin_manager

    return get_plugin_manager()


def clean_plugin_visibility_text(value, *, limit=240) -> str:
    """Return bounded display text without path/callback-like internals."""
    if value is None:
        return ""
    text = str(value).replace("\x00", "").strip()
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "..."
    return text


def plugin_visibility_payload(manager=None, *, manager_factory: Callable[[], object] = get_plugin_manager_for_visibility) -> dict:
    """Build a sanitized plugin/hook visibility payload for Settings."""
    manager = manager or manager_factory()
    manager.discover_and_load(force=False)

    plugins = []
    raw_plugins = getattr(manager, "_plugins", {}) or {}
    for key, loaded in sorted(raw_plugins.items(), key=lambda item: str(item[0])):
        manifest = getattr(loaded, "manifest", None)
        if manifest is None:
            continue
        plugin_key = clean_plugin_visibility_text(
            getattr(manifest, "key", None) or key or getattr(manifest, "name", ""),
            limit=120,
        )
        name = clean_plugin_visibility_text(getattr(manifest, "name", "") or plugin_key, limit=120)
        version = clean_plugin_visibility_text(getattr(manifest, "version", ""), limit=80)
        description = clean_plugin_visibility_text(getattr(manifest, "description", ""), limit=280)
        registered = []
        for hook in list(getattr(manifest, "provides_hooks", []) or []) + list(getattr(loaded, "hooks_registered", []) or []):
            hook_name = str(hook or "").strip()
            if hook_name in PLUGIN_VISIBILITY_HOOK_SET and hook_name not in registered:
                registered.append(hook_name)
        registered.sort(key=PLUGIN_VISIBILITY_HOOKS.index)
        plugins.append({
            "name": name,
            "key": plugin_key or name,
            "version": version,
            "description": description,
            "enabled": bool(getattr(loaded, "enabled", False)),
            "hooks": registered,
        })

    return {
        "plugins": plugins,
        "empty": not bool(plugins),
        "supported_hooks": list(PLUGIN_VISIBILITY_HOOKS),
        "read_only": True,
    }


def handle_plugins(handler, parsed, *, payload_factory=plugin_visibility_payload, responder=j) -> bool:
    try:
        return responder(handler, payload_factory())
    except Exception as exc:
        logger.warning("Failed to build plugin visibility payload: %s", exc)
        return responder(
            handler,
            {
                "plugins": [],
                "empty": True,
                "supported_hooks": list(PLUGIN_VISIBILITY_HOOKS),
                "read_only": True,
                "unavailable": True,
            },
        )

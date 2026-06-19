"""Messaging/gateway session metadata helpers for WebUI routes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any, Callable


def normalize_messaging_source(raw_source) -> str:
    return str(raw_source or "").strip().lower()


def is_known_messaging_source(raw_source, known_sources: set[str]) -> bool:
    return normalize_messaging_source(raw_source) in known_sources


def safe_first(*values) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def gateway_session_metadata_path() -> Path:
    try:
        from api.profiles import get_active_hermes_home

        hermes_home = Path(get_active_hermes_home()).expanduser().resolve()
    except Exception:
        hermes_home = Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser().resolve()
    return hermes_home / "sessions" / "sessions.json"


def load_gateway_session_identity_map(
    *,
    path_fn: Callable[[], Path] = gateway_session_metadata_path,
    cache: dict[str, Any],
    cache_lock: Lock,
    safe_first_fn: Callable[..., str] = safe_first,
    logger,
) -> dict[str, dict]:
    path = path_fn()
    if not path.exists():
        return {}

    try:
        st = path.stat()
        with cache_lock:
            if cache["path"] == str(path) and cache["mtime"] == st.st_mtime:
                return cache["identity"].copy()
    except Exception:
        return {}

    try:
        raw_sessions = json.loads(path.read_text(encoding="utf-8"))
    except Exception as json_err:
        logger.debug("Failed to parse gateway sessions metadata from %s: %s", path, json_err)
        return {}

    mapping: dict[str, dict] = {}
    if isinstance(raw_sessions, dict):
        for entry in raw_sessions.values():
            if not isinstance(entry, dict):
                continue
            session_id = safe_first_fn(entry.get("session_id"))
            if not session_id:
                continue
            origin = entry.get("origin") if isinstance(entry.get("origin"), dict) else {}
            platform = safe_first_fn(origin.get("platform"), entry.get("platform"))
            mapping[session_id] = {
                "session_key": safe_first_fn(entry.get("session_key"), entry.get("key")),
                "chat_id": safe_first_fn(origin.get("chat_id"), entry.get("chat_id")),
                "thread_id": safe_first_fn(origin.get("thread_id"), entry.get("thread_id")),
                "chat_type": safe_first_fn(origin.get("chat_type"), entry.get("chat_type")),
                "user_id": safe_first_fn(origin.get("user_id"), entry.get("user_id")),
                "platform": platform,
                "raw_source": platform,
            }

    with cache_lock:
        cache["path"] = str(path)
        cache["mtime"] = st.st_mtime
        cache["identity"] = mapping
    return mapping.copy()

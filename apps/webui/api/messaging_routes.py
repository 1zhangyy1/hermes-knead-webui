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


def lookup_gateway_session_identity(session_id: str, *, load_identity_map: Callable[[], dict[str, dict]]) -> dict:
    if not session_id:
        return {}
    metadata = load_identity_map().get(str(session_id))
    return metadata if isinstance(metadata, dict) else {}


def messaging_session_identity(
    session: dict,
    raw_source: str,
    *,
    lookup_gateway_identity_fn: Callable[[str], dict],
    safe_first_fn: Callable[..., str] = safe_first,
) -> str:
    metadata = lookup_gateway_identity_fn(session.get("session_id"))
    session_key = safe_first_fn(
        metadata.get("session_key"),
        session.get("session_key"),
        session.get("gateway_session_key"),
    )
    if session_key:
        return f"{raw_source}|session_key:{session_key}"

    chat_id = safe_first_fn(
        metadata.get("chat_id"),
        session.get("chat_id"),
        session.get("origin_chat_id"),
    )
    thread_id = safe_first_fn(metadata.get("thread_id"), session.get("thread_id"))
    chat_type = safe_first_fn(metadata.get("chat_type"), session.get("chat_type"))
    user_id = safe_first_fn(
        metadata.get("user_id"),
        session.get("user_id"),
        session.get("origin_user_id"),
    )

    identity_parts = []
    if chat_type:
        identity_parts.append(f"chat_type:{chat_type}")
    if chat_id:
        identity_parts.append(f"chat_id:{chat_id}")
    if thread_id:
        identity_parts.append(f"thread_id:{thread_id}")
    if user_id:
        identity_parts.append(f"user_id:{user_id}")

    if identity_parts:
        return f"{raw_source}|" + "|".join(identity_parts)
    return raw_source


def session_messaging_raw_source(
    session: dict,
    *,
    safe_first_fn: Callable[..., str] = safe_first,
    normalize_source_fn: Callable[[Any], str] = normalize_messaging_source,
) -> str:
    raw = safe_first_fn(
        session.get("raw_source"),
        session.get("source_tag"),
        session.get("source"),
        session.get("platform"),
    )
    if not raw:
        raw = session.get("source_label") or "messaging"
    return normalize_source_fn(raw)


def has_durable_messaging_identity(
    session: dict,
    *,
    lookup_gateway_identity_fn: Callable[[str], dict],
    safe_first_fn: Callable[..., str] = safe_first,
) -> bool:
    metadata = lookup_gateway_identity_fn(session.get("session_id"))
    return bool(safe_first_fn(
        metadata.get("session_key"),
        session.get("session_key"),
        session.get("gateway_session_key"),
        metadata.get("chat_id"),
        session.get("chat_id"),
        session.get("origin_chat_id"),
        metadata.get("thread_id"),
        session.get("thread_id"),
    ))


def numeric_count(value, *, safe_first_fn: Callable[..., str] = safe_first) -> int:
    try:
        return int(float(safe_first_fn(value, 0) or 0))
    except (TypeError, ValueError):
        return 0


def should_hide_stale_messaging_session(
    session: dict,
    active_gateway_session_ids: set[str],
    active_gateway_sources: set[str],
    *,
    stale_end_reasons: set[str],
    session_raw_source_fn: Callable[[dict], str],
    is_known_messaging_source_fn: Callable[[Any], bool],
    safe_first_fn: Callable[..., str] = safe_first,
    has_durable_identity_fn: Callable[[dict], bool],
    numeric_count_fn: Callable[[Any], int] = numeric_count,
) -> bool:
    """Hide stale Gateway-owned internal rows after an external chat moved on."""
    raw_source = session_raw_source_fn(session)
    if not is_known_messaging_source_fn(raw_source):
        return False
    if not active_gateway_session_ids or raw_source not in active_gateway_sources:
        return False

    sid = safe_first_fn(session.get("session_id"))
    if sid and sid in active_gateway_session_ids:
        return False

    if safe_first_fn(session.get("end_reason")) in stale_end_reasons:
        return True

    if not has_durable_identity_fn(session):
        return True

    if session.get("parent_session_id"):
        return True

    message_count = numeric_count_fn(session.get("message_count"))
    actual_count = numeric_count_fn(session.get("actual_message_count"))
    if message_count <= 0 and actual_count <= 0:
        return True

    return False


def is_messaging_session_record(
    session,
    *,
    safe_first_fn: Callable[..., str] = safe_first,
    is_known_messaging_source_fn: Callable[[Any], bool],
) -> bool:
    """Return true for sessions backed by external messaging channels."""
    if not session:
        return False
    if (
        (getattr(session, "session_source", None) if not isinstance(session, dict) else session.get("session_source")) == "messaging"
    ):
        return True
    raw = safe_first_fn(
        getattr(session, "raw_source", None) if not isinstance(session, dict) else session.get("raw_source"),
        getattr(session, "source_tag", None) if not isinstance(session, dict) else session.get("source_tag"),
        getattr(session, "source", None) if not isinstance(session, dict) else session.get("source"),
        session.get("source_label") if isinstance(session, dict) else None,
    )
    return is_known_messaging_source_fn(raw)


def messages_include_tool_metadata(messages) -> bool:
    """Return true when returned messages can reconstruct their own tool cards."""
    if not isinstance(messages, list):
        return False
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        if isinstance(msg.get("tool_calls"), list) and msg.get("tool_calls"):
            return True
        content = msg.get("content")
        if isinstance(content, list) and any(
            isinstance(part, dict) and part.get("type") == "tool_use"
            for part in content
        ):
            return True
    return False


def session_requires_cli_metadata_lookup(
    session,
    *,
    is_messaging_session_record_fn: Callable[[Any], bool],
    safe_first_fn: Callable[..., str] = safe_first,
    normalize_source_fn: Callable[[Any], str] = normalize_messaging_source,
) -> bool:
    """Return True when a sidecar/session row still needs CLI metadata."""
    if not session:
        return False

    def _field(name):
        return session.get(name) if isinstance(session, dict) else getattr(session, name, None)

    if is_messaging_session_record_fn(session):
        return True
    if bool(_field("is_cli_session")) or bool(_field("read_only")):
        return True
    session_source = normalize_source_fn(safe_first_fn(_field("session_source")))
    if session_source in {"messaging", "external_agent", "external-agent"}:
        return True
    return bool(safe_first_fn(
        _field("source_tag"),
        _field("raw_source"),
        _field("source"),
        _field("source_label"),
        _field("platform"),
    ))


def session_sort_timestamp(session: dict, *, safe_first_fn: Callable[..., str] = safe_first) -> float:
    return float(
        safe_first_fn(
            session.get("last_message_at"),
            session.get("updated_at"),
            session.get("created_at"),
            session.get("started_at"),
            0,
        ) or 0
    ) or 0.0


def is_cli_session_for_settings(
    session: dict,
    *,
    is_cli_session_row_fn: Callable[[dict], bool],
    messaging_sources: set[str],
) -> bool:
    """Return True for importable CLI sessions that are safe to classify for settings."""
    if not isinstance(session, dict):
        return False
    if is_cli_session_row_fn(session):
        return True

    if not session.get("is_cli_session"):
        return False
    source = str(session.get("source") or "").strip().lower()
    if source in messaging_sources:
        return False
    title = str(session.get("title") or "").strip().lower()
    return title in ("", "untitled", "cli", "cli session") or title.endswith(" session") and (
        not source or source == "cli"
    )


def cap_recent_cli_sessions(
    sessions: list[dict],
    cli_cap: int,
    *,
    is_cli_session_for_settings_fn: Callable[[dict], bool],
) -> list[dict]:
    """Keep only the most recent CLI-visible sessions after filtering."""
    if cli_cap <= 0:
        return sessions
    kept = []
    cli_seen = 0
    for session in sessions:
        if is_cli_session_for_settings_fn(session):
            cli_seen += 1
            if cli_seen > cli_cap:
                continue
        kept.append(session)
    return kept


def merge_cli_sidebar_metadata(
    ui_session: dict,
    cli_meta: dict,
    *,
    safe_first_fn: Callable[..., str] = safe_first,
    numeric_count_fn: Callable[[Any], int] = numeric_count,
) -> dict:
    """Merge source-of-truth CLI metadata into a sidebar session row."""
    if not ui_session:
        return ui_session
    if not cli_meta:
        return dict(ui_session)
    merged = dict(ui_session)
    merged["is_cli_session"] = True
    for key in (
        "source_tag",
        "raw_source",
        "session_source",
        "source_label",
        "user_id",
        "chat_id",
        "chat_type",
        "thread_id",
        "session_key",
        "platform",
        "parent_session_id",
        "end_reason",
        "actual_message_count",
        "_lineage_root_id",
        "_lineage_tip_id",
        "_compression_segment_count",
    ):
        value = safe_first_fn(cli_meta.get(key))
        if value:
            merged[key] = value

    if cli_meta.get("created_at") is not None:
        merged["created_at"] = cli_meta["created_at"]
    if cli_meta.get("updated_at") is not None:
        merged["updated_at"] = cli_meta["updated_at"]
    if cli_meta.get("last_message_at") is not None:
        merged["last_message_at"] = cli_meta["last_message_at"]
    if cli_meta.get("message_count") is not None:
        merged["message_count"] = max(
            numeric_count_fn(merged.get("message_count")),
            numeric_count_fn(cli_meta.get("message_count")),
        )
    elif cli_meta.get("actual_message_count") is not None:
        merged["message_count"] = max(
            numeric_count_fn(merged.get("message_count")),
            numeric_count_fn(cli_meta.get("actual_message_count")),
        )

    if cli_meta.get("title"):
        current_title = merged.get("title")
        if not current_title or current_title == "Untitled":
            merged["title"] = cli_meta["title"]

    if cli_meta.get("model"):
        if not merged.get("model") or merged.get("model") == "unknown":
            merged["model"] = cli_meta["model"]
    return merged


def messaging_source_key(
    session: dict,
    *,
    session_raw_source_fn: Callable[[dict], str],
    is_known_messaging_source_fn: Callable[[Any], bool],
    messaging_session_identity_fn: Callable[[dict, str], str],
) -> str | None:
    raw = session_raw_source_fn(session)
    if not is_known_messaging_source_fn(raw):
        return None
    return messaging_session_identity_fn(session, raw)


def keep_latest_messaging_session_per_source(
    sessions: list[dict],
    *,
    load_identity_map: Callable[[], dict[str, dict]],
    normalize_source_fn: Callable[[Any], str] = normalize_messaging_source,
    safe_first_fn: Callable[..., str] = safe_first,
    is_known_messaging_source_fn: Callable[[Any], bool],
    messaging_source_key_fn: Callable[[dict], str | None],
    should_hide_stale_fn: Callable[[dict, set[str], set[str]], bool],
    session_sort_timestamp_fn: Callable[[dict], float],
) -> list[dict]:
    """Keep only the newest sidebar row per messaging session identity."""
    gateway_metadata = load_identity_map()
    active_gateway_session_ids = {str(sid) for sid in gateway_metadata.keys() if sid}
    active_gateway_sources = {
        normalize_source_fn(safe_first_fn(meta.get("raw_source"), meta.get("platform")))
        for meta in gateway_metadata.values()
        if isinstance(meta, dict)
    }
    active_gateway_sources = {source for source in active_gateway_sources if is_known_messaging_source_fn(source)}

    kept_sources: set[str] = set()
    best_by_source: dict[str, dict] = {}
    kept: list[dict] = []
    for session in sessions:
        key = messaging_source_key_fn(session)
        if not key:
            kept.append(session)
            continue
        if should_hide_stale_fn(session, active_gateway_session_ids, active_gateway_sources):
            continue
        if key in kept_sources:
            kept_sources.add(key)
            current = best_by_source.get(key)
            if current is None or session_sort_timestamp_fn(session) > session_sort_timestamp_fn(current):
                best_by_source[key] = session
            continue
        kept_sources.add(key)
        best_by_source[key] = session

    kept.extend(best_by_source.values())
    kept.sort(key=session_sort_timestamp_fn, reverse=True)
    return kept

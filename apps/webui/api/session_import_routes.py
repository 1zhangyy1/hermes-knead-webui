"""Session import helpers for WebUI routes."""

from __future__ import annotations

from typing import Callable


def normalize_message_for_import_refresh(message: object) -> object:
    if not isinstance(message, dict):
        return message
    normalized = dict(message)
    normalized.pop("timestamp", None)
    normalized.pop("_ts", None)
    return normalized


def message_has_cli_tool_metadata(message: object) -> bool:
    if not isinstance(message, dict):
        return False
    if message.get("role") == "assistant" and message.get("tool_calls"):
        return True
    if message.get("role") == "tool" and (message.get("tool_call_id") or message.get("tool_name") or message.get("name")):
        return True
    return False


def strip_cli_tool_metadata_for_refresh(message: object) -> object:
    if not isinstance(message, dict):
        return normalize_message_for_import_refresh(message)
    normalized = normalize_message_for_import_refresh(message)
    if not isinstance(normalized, dict):
        return normalized
    for key in ("tool_calls", "tool_call_id", "tool_name", "name"):
        normalized.pop(key, None)
    return normalized


def is_cli_tool_metadata_enrichment(existing_messages: list, fresh_messages: list) -> bool:
    """Return True when fresh messages only add CLI tool metadata."""
    if not isinstance(existing_messages, list) or not isinstance(fresh_messages, list):
        return False
    if len(existing_messages) != len(fresh_messages):
        return False
    if any(message_has_cli_tool_metadata(message) for message in existing_messages):
        return False
    if not any(message_has_cli_tool_metadata(message) for message in fresh_messages):
        return False
    for idx, existing_message in enumerate(existing_messages):
        if strip_cli_tool_metadata_for_refresh(existing_message) != strip_cli_tool_metadata_for_refresh(fresh_messages[idx]):
            return False
    return True


def is_messages_refresh_prefix_match(existing_messages: list, fresh_messages: list) -> bool:
    """Return True when existing_messages is a prefix of fresh_messages by value."""
    if not isinstance(existing_messages, list) or not isinstance(fresh_messages, list):
        return False
    if len(existing_messages) > len(fresh_messages):
        return False
    for idx, existing_message in enumerate(existing_messages):
        fresh_message = fresh_messages[idx]
        if normalize_message_for_import_refresh(existing_message) != normalize_message_for_import_refresh(fresh_message):
            return False
    return True


def handle_session_import(
    handler,
    body,
    *,
    bad_fn: Callable,
    json_response_fn: Callable,
    resolve_trusted_workspace_fn: Callable,
    session_cls,
    sessions: dict,
    sessions_lock,
    sessions_max: int,
    default_workspace,
    default_model,
):
    """Import a session from a JSON export. Creates a new session with a new ID."""
    if not body or not isinstance(body, dict):
        return bad_fn(handler, "Request body must be a JSON object")
    messages = body.get("messages")
    if not isinstance(messages, list):
        return bad_fn(handler, 'JSON must contain a "messages" array')
    title = body.get("title", "Imported session")
    try:
        workspace = str(resolve_trusted_workspace_fn(body.get("workspace", str(default_workspace))))
    except (TypeError, ValueError) as e:
        return bad_fn(handler, str(e))
    model = body.get("model", default_model)
    session = session_cls(
        title=title,
        workspace=workspace,
        model=model,
        messages=messages,
        tool_calls=body.get("tool_calls", []),
    )
    session.pinned = body.get("pinned", False)
    with sessions_lock:
        sessions[session.session_id] = session
        sessions.move_to_end(session.session_id)
        while len(sessions) > sessions_max:
            sessions.popitem(last=False)
    session.save()
    return json_response_fn(handler, {"ok": True, "session": session.compact() | {"messages": session.messages}})

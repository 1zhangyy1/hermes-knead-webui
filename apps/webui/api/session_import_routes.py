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


def handle_session_import_cli(
    handler,
    body,
    *,
    require_fn: Callable,
    bad_fn: Callable,
    json_response_fn: Callable,
    session_cls,
    get_cli_session_messages_fn: Callable,
    get_cli_sessions_fn: Callable,
    is_messages_refresh_prefix_match_fn: Callable,
    is_cli_tool_metadata_enrichment_fn: Callable,
    title_from_fn: Callable,
    is_cron_session_fn: Callable,
    ensure_cron_project_fn: Callable,
    get_last_workspace_fn: Callable,
    import_cli_session_fn: Callable,
):
    """Import a single CLI session into the WebUI store."""
    try:
        require_fn(body, "session_id")
    except ValueError as e:
        return bad_fn(handler, str(e))

    sid = str(body["session_id"])

    # Check if already imported — refresh messages from CLI store if new ones arrived
    existing = session_cls.load(sid)
    if existing:
        fresh_msgs = get_cli_session_messages_fn(sid)
        changed = False
        cli_meta = None
        for cs in list(get_cli_sessions_fn()):
            if cs["session_id"] == sid:
                cli_meta = cs
                break
        if fresh_msgs and len(fresh_msgs) > len(existing.messages):
            # Prefix-equality guard: only extend if existing messages are a prefix of
            # the fresh CLI messages. Prevents silently dropping WebUI-added messages
            # on hybrid sessions (user sent messages via WebUI while CLI continued).
            if is_messages_refresh_prefix_match_fn(existing.messages, fresh_msgs):
                existing.messages = fresh_msgs
                changed = True
        elif fresh_msgs and is_cli_tool_metadata_enrichment_fn(existing.messages, fresh_msgs):
            # Same row count, richer payload: rebuild sidecars imported before
            # CLI tool metadata was preserved (#1772).
            existing.messages = fresh_msgs
            changed = True
        if cli_meta:
            updates = {
                "is_cli_session": True,
                "source_tag": existing.source_tag or cli_meta.get("source_tag"),
                "raw_source": existing.raw_source or cli_meta.get("raw_source") or cli_meta.get("source_tag"),
                "session_source": existing.session_source or cli_meta.get("session_source"),
                "source_label": existing.source_label or cli_meta.get("source_label"),
                "parent_session_id": existing.parent_session_id or cli_meta.get("parent_session_id"),
            }
            for attr, value in updates.items():
                if getattr(existing, attr, None) != value:
                    setattr(existing, attr, value)
                    changed = True
        if changed:
            existing.save(touch_updated_at=False)
        return json_response_fn(
            handler,
            {
                "session": existing.compact()
                | {
                    "messages": existing.messages,
                    "is_cli_session": True,
                    "read_only": bool((cli_meta or {}).get("read_only")),
                },
                "imported": False,
            },
        )

    # Fetch messages from CLI store
    msgs = get_cli_session_messages_fn(sid)
    if not msgs:
        return bad_fn(handler, "Session not found in CLI store", 404)

    # Get profile, model, timestamps, and title from CLI session metadata
    profile = None
    created_at = None
    updated_at = None
    cli_title = None
    cli_source_tag = None
    model = "unknown"
    cli_raw_source = None
    cli_session_source = None
    cli_source_label = None
    cli_user_id = None
    cli_chat_id = None
    cli_chat_type = None
    cli_thread_id = None
    cli_session_key = None
    cli_platform = None
    cli_parent_session_id = None
    cli_read_only = False
    for cs in get_cli_sessions_fn():
        if cs["session_id"] == sid:
            profile = cs.get("profile")
            model = cs.get("model", "unknown")
            created_at = cs.get("created_at")
            updated_at = cs.get("updated_at")
            cli_title = cs.get("title")
            cli_source_tag = cs.get("source_tag")
            cli_raw_source = cs.get("raw_source")
            cli_session_source = cs.get("session_source")
            cli_source_label = cs.get("source_label")
            cli_user_id = cs.get("user_id")
            cli_chat_id = cs.get("chat_id")
            cli_chat_type = cs.get("chat_type")
            cli_thread_id = cs.get("thread_id")
            cli_session_key = cs.get("session_key")
            cli_platform = cs.get("platform")
            cli_parent_session_id = cs.get("parent_session_id")
            cli_read_only = bool(cs.get("read_only"))
            break

    # Use the CLI session title if available (e.g., cron job name), otherwise derive from messages
    title = cli_title or title_from_fn(msgs, "CLI Session")

    # Auto-assign cron sessions to the dedicated "Cron Jobs" project (#1079)
    cron_project_id = None
    if is_cron_session_fn(sid, cli_source_tag):
        cron_project_id = ensure_cron_project_fn()

    if cli_read_only:
        session_payload = {
            "session_id": sid,
            "title": title,
            "workspace": str(get_last_workspace_fn()),
            "model": model,
            "message_count": len(msgs),
            "created_at": created_at,
            "updated_at": updated_at,
            "last_message_at": updated_at or created_at,
            "pinned": False,
            "archived": False,
            "project_id": None,
            "profile": profile,
            "is_cli_session": True,
            "source_tag": cli_source_tag,
            "raw_source": cli_raw_source or cli_source_tag,
            "session_source": cli_session_source,
            "source_label": cli_source_label,
            "parent_session_id": cli_parent_session_id,
            "read_only": True,
            "messages": msgs,
            "tool_calls": [],
        }
        return json_response_fn(handler, {"session": session_payload, "imported": False})

    s = import_cli_session_fn(
        sid,
        title,
        msgs,
        model,
        profile=profile,
        created_at=created_at,
        updated_at=updated_at,
        parent_session_id=cli_parent_session_id,
    )
    if cron_project_id:
        s.project_id = cron_project_id
    s.is_cli_session = True
    s.source_tag = cli_source_tag
    s.raw_source = cli_raw_source or cli_source_tag
    s.session_source = cli_session_source
    s.source_label = cli_source_label
    s.user_id = cli_user_id
    s.chat_id = cli_chat_id
    s.chat_type = cli_chat_type
    s.thread_id = cli_thread_id
    s.session_key = cli_session_key
    s.platform = cli_platform
    s._cli_origin = sid
    s.save(touch_updated_at=False)
    return json_response_fn(
        handler,
        {
            "session": s.compact()
            | {
                "messages": msgs,
                "is_cli_session": True,
            },
            "imported": True,
        },
    )

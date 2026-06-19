"""Handoff summary marker helpers."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Callable


def build_handoff_summary_tool_message(
    sid: str,
    summary: str,
    channel: str | None,
    rounds: int | None = None,
    fallback: bool = False,
) -> dict:
    """Build a compact tool-role transcript marker for persistence."""
    now = time.time()
    return {
        "role": "tool",
        "tool_call_id": "",
        "name": "handoff_summary",
        "timestamp": now,
        "_ts": now,
        "content": json.dumps(
            {
                "_handoff_summary_card": True,
                "session_id": sid,
                "summary": str(summary or "").strip(),
                "channel": (str(channel or "").strip() or None),
                "rounds": rounds,
                "fallback": bool(fallback),
                "generated_at": now,
            },
            ensure_ascii=False,
        ),
    }


def extract_handoff_summary_payload(message: dict) -> dict | None:
    """Return a normalized handoff-summary payload if *message* is a tool marker."""
    if not isinstance(message, dict):
        return None
    if message.get("role") != "tool" or message.get("name") != "handoff_summary":
        return None

    content = message.get("content")
    if isinstance(content, dict):
        payload = content
    else:
        try:
            payload = json.loads(content or "")
        except Exception:
            return None

    if not isinstance(payload, dict) or not payload.get("_handoff_summary_card"):
        return None
    if payload.get("session_id") is None:
        return None
    return {
        "session_id": str(payload.get("session_id")),
        "summary": str(payload.get("summary", "")),
        "channel": payload.get("channel"),
        "rounds": payload.get("rounds"),
        "fallback": bool(payload.get("fallback")),
        "_handoff_summary_card": True,
    }


def is_matching_handoff_summary_message(
    existing: dict,
    target: dict,
    *,
    extract_payload_fn: Callable[[dict], dict | None] = extract_handoff_summary_payload,
) -> bool:
    """Return True when two message payloads represent the same handoff summary."""
    existing_payload = extract_payload_fn(existing)
    target_payload = extract_payload_fn(target)
    if not existing_payload or not target_payload:
        return False
    return (
        existing_payload.get("session_id") == target_payload.get("session_id")
        and existing_payload.get("summary") == target_payload.get("summary")
        and existing_payload.get("channel") == target_payload.get("channel")
        and existing_payload.get("rounds") == target_payload.get("rounds")
        and existing_payload.get("fallback") == target_payload.get("fallback")
        and existing_payload.get("_handoff_summary_card") == target_payload.get("_handoff_summary_card")
    )


def is_matching_handoff_summary_content(content: object, target_payload: dict | None) -> bool:
    """Return True if DB content JSON matches an expected handoff summary payload."""
    if target_payload is None:
        return False
    try:
        payload = json.loads(content or "")
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("session_id") is None:
        return False
    return (
        payload.get("_handoff_summary_card") is True
        and str(payload.get("session_id")) == str(target_payload.get("session_id"))
        and str(payload.get("summary", "")) == str(target_payload.get("summary", ""))
        and payload.get("channel") == target_payload.get("channel")
        and payload.get("rounds") == target_payload.get("rounds")
        and bool(payload.get("fallback")) == bool(target_payload.get("fallback"))
    )


def persist_handoff_summary_locally(
    sid: str,
    message: dict,
    *,
    get_session_fn,
    is_matching_message_fn: Callable[[dict, dict], bool] = is_matching_handoff_summary_message,
    logger,
) -> bool:
    """Persist a handoff summary marker into a local WebUI session file."""
    try:
        session = get_session_fn(sid)
    except KeyError:
        return False

    try:
        if session.messages and is_matching_message_fn(session.messages[-1], message):
            return True
        session.messages.append(message)
        session.save()
        return True
    except Exception as exc:
        logger.warning("Failed to persist handoff summary marker in local session %s: %s", sid, exc)
        return False


def persist_handoff_summary_to_state_db(
    sid: str,
    message: dict,
    *,
    active_home_fn,
    extract_payload_fn: Callable[[dict], dict | None] = extract_handoff_summary_payload,
    is_matching_content_fn: Callable[[object, dict | None], bool] = is_matching_handoff_summary_content,
    logger,
) -> bool:
    """Persist a handoff summary marker into CLI sessions state.db."""
    try:
        hermes_home = Path(active_home_fn()).expanduser().resolve()
    except Exception:
        hermes_home = Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser().resolve()

    db_path = hermes_home / "state.db"
    if not db_path.exists():
        return False

    ts = message.get("timestamp", time.time())
    content = message.get("content", "")
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)

    marker_payload = extract_payload_fn(message)
    try:
        with sqlite3.connect(str(db_path)) as conn:
            try:
                if marker_payload is not None:
                    cur = conn.execute(
                        "SELECT content FROM messages WHERE session_id = ? AND role = 'tool' "
                        "ORDER BY rowid DESC LIMIT 1",
                        (sid,),
                    )
                    row = cur.fetchone()
                    if row is not None and is_matching_content_fn(row[0], marker_payload):
                        return True
            except Exception:
                logger.debug("Unable to read tail handoff marker from state.db for %s", sid)

            conn.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) "
                "VALUES (?, 'tool', ?, ?)",
                (sid, content, ts),
            )
            conn.execute(
                "UPDATE sessions SET message_count = COALESCE(message_count, 0) + 1 "
                "WHERE id = ?",
                (sid,),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("Failed to persist handoff summary marker in state.db for %s: %s", sid, exc)
        return False


def persist_handoff_summary(
    sid: str,
    summary: str,
    channel: str | None,
    rounds: int | None,
    fallback: bool = False,
    *,
    is_messaging_session_fn: Callable[[str], bool],
    build_marker_fn: Callable[..., dict] = build_handoff_summary_tool_message,
    persist_local_fn: Callable[[str, dict], bool],
    persist_state_db_fn: Callable[[str, dict], bool],
) -> dict:
    """Persist a handoff summary marker across local/session backends."""
    marker = build_marker_fn(sid, summary, channel, rounds, fallback)
    if is_messaging_session_fn(sid):
        persist_state_db_fn(sid, marker)
        persist_local_fn(sid, marker)
        return marker
    if persist_local_fn(sid, marker):
        return marker
    return marker if persist_state_db_fn(sid, marker) else marker

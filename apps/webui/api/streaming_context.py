"""Message context and transcript merge helpers for streaming."""

import copy
import json
import re

from api.streaming_attachments import resolve_image_input_mode as _resolve_image_input_mode
from api.streaming_titles import (
    looks_like_current_user_turn as _looks_like_current_user_turn,
    message_text as _message_text,
    strip_workspace_prefix as _strip_workspace_prefix,
)


API_SAFE_MSG_KEYS = {
    'role',
    'content',
    'tool_calls',
    'tool_call_id',
    'name',
    'refusal',
    'reasoning_content',
}


def strip_native_image_parts_from_content(content):
    """Return provider-safe content with native image parts removed."""
    if not isinstance(content, list):
        return content
    clean_parts = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get('type') == 'image_url' or 'image_url' in part:
            continue
        clean_parts.append(copy.deepcopy(part))
    if not clean_parts:
        return ''
    if len(clean_parts) == 1 and clean_parts[0].get('type') == 'text':
        return str(clean_parts[0].get('text') or '')
    return clean_parts


def sanitize_messages_for_api(messages, *, cfg: dict = None):
    """Return a deep copy of messages with only API-safe fields."""
    strip_native_images = cfg is not None and _resolve_image_input_mode(cfg) == "text"
    valid_tool_call_ids: set = set()
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get('role') == 'assistant':
            for tc in msg.get('tool_calls') or []:
                if isinstance(tc, dict):
                    tid = tc.get('id') or tc.get('call_id') or ''
                    if tid:
                        valid_tool_call_ids.add(tid)

    clean = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get('_error'):
            continue
        role = msg.get('role')
        if role == 'tool':
            tid = msg.get('tool_call_id') or ''
            if not tid or tid not in valid_tool_call_ids:
                continue
        sanitized = {k: v for k, v in msg.items() if k in API_SAFE_MSG_KEYS}
        if strip_native_images and 'content' in sanitized:
            sanitized['content'] = strip_native_image_parts_from_content(sanitized.get('content'))
        if sanitized.get('role'):
            clean.append(sanitized)
    return clean


def api_safe_message_positions(messages):
    """Return [(original_index, sanitized_message)] for API-safe messages."""
    valid_tool_call_ids: set = set()
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get('role') == 'assistant':
            for tc in msg.get('tool_calls') or []:
                if isinstance(tc, dict):
                    tid = tc.get('id') or tc.get('call_id') or ''
                    if tid:
                        valid_tool_call_ids.add(tid)

    out = []
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        role = msg.get('role')
        if role == 'tool':
            tid = msg.get('tool_call_id') or ''
            if not tid or tid not in valid_tool_call_ids:
                continue
        sanitized = {k: v for k, v in msg.items() if k in API_SAFE_MSG_KEYS}
        if sanitized.get('role'):
            out.append((idx, sanitized))
    return out


def restore_reasoning_metadata(previous_messages, updated_messages):
    """Carry forward display-only metadata lost during API-safe history sanitization."""
    if not previous_messages or not updated_messages:
        return updated_messages
    updated_messages = list(updated_messages)
    prev_safe = api_safe_message_positions(previous_messages)

    def _safe_projection(msg):
        if not isinstance(msg, dict):
            return None
        return {k: v for k, v in msg.items() if k in API_SAFE_MSG_KEYS and msg.get('role')}

    def _reasoning_only_assistant(msg):
        if not isinstance(msg, dict) or msg.get('role') != 'assistant' or not msg.get('reasoning'):
            return False
        if msg.get('tool_calls'):
            return False
        return not _message_text(msg.get('content'))

    safe_pos = 0
    while safe_pos < len(prev_safe):
        prev_idx, _ = prev_safe[safe_pos]
        prev_msg = previous_messages[prev_idx]
        cur_msg = updated_messages[safe_pos] if safe_pos < len(updated_messages) else None

        if isinstance(prev_msg, dict) and isinstance(cur_msg, dict) and _safe_projection(prev_msg) == _safe_projection(cur_msg):
            if prev_msg.get('role') == 'assistant' and prev_msg.get('reasoning') and not cur_msg.get('reasoning'):
                cur_msg['reasoning'] = prev_msg['reasoning']
            if prev_msg.get('timestamp') and not cur_msg.get('timestamp'):
                cur_msg['timestamp'] = prev_msg['timestamp']
            elif prev_msg.get('_ts') and not cur_msg.get('_ts') and not cur_msg.get('timestamp'):
                cur_msg['_ts'] = prev_msg['_ts']
            safe_pos += 1
            continue

        if _reasoning_only_assistant(prev_msg):
            updated_messages.insert(safe_pos, copy.deepcopy(prev_msg))
            safe_pos += 1
            continue

        safe_pos += 1
    return updated_messages


def session_context_messages(session):
    """Return model-facing history without assuming it matches the UI transcript."""
    context_messages = getattr(session, 'context_messages', None)
    if isinstance(context_messages, list) and context_messages:
        return context_messages
    return session.messages or []


def message_identity(msg):
    if not isinstance(msg, dict):
        return None
    role = str(msg.get('role') or '')
    content = msg.get('content', '')
    text = _message_text(content)
    if role == 'user':
        text = _strip_workspace_prefix(text, include_legacy=True)
    if not text and not msg.get('tool_call_id') and not msg.get('tool_calls'):
        return None
    return (
        role,
        " ".join(str(text or '').split())[:500],
        str(msg.get('tool_call_id') or ''),
        json.dumps(msg.get('tool_calls') or [], sort_keys=True, ensure_ascii=False),
    )


def messages_have_prefix(messages, prefix):
    if len(messages or []) < len(prefix or []):
        return False
    for idx, expected in enumerate(prefix or []):
        if message_identity((messages or [])[idx]) != message_identity(expected):
            return False
    return True


def is_context_compression_marker(msg):
    if not isinstance(msg, dict):
        return False
    text = _message_text(msg.get('content', '')).lower()
    return (
        'context compaction' in text
        or 'context compression' in text
        or 'context was auto-compressed' in text
        or 'active task list was preserved across context compression' in text
    )


def compact_summary_text(raw_text: str | None, limit: int = 320) -> str | None:
    """Normalize a text blob used in compression summary cards."""
    if not isinstance(raw_text, str):
        return None
    txt = raw_text.strip()
    if not txt:
        return None
    txt = re.sub(r"\s+", " ", txt).strip()
    if len(txt) > limit:
        txt = f"{txt[: limit - 6]}\u2026"
    return txt


def compression_anchor_message_key(message):
    if not isinstance(message, dict):
        return None
    role = str(message.get('role') or '')
    if not role or role == 'tool':
        return None
    content = message.get('content', '')
    text = _message_text(content)
    if len(text) > 160:
        text = text[:160]
    ts = message.get('_ts') or message.get('timestamp')
    attachments = message.get('attachments')
    attach_count = len(attachments) if isinstance(attachments, list) else 0
    if not text and not attach_count and not ts:
        return None
    return {'role': role, 'ts': ts, 'text': text, 'attachments': attach_count}


def compression_summary_from_messages(messages):
    for m in reversed(messages or []):
        if not isinstance(m, dict):
            continue
        if not is_context_compression_marker(m):
            continue
        text = _message_text(m.get('content'))
        if text:
            return text
    return None


def preserve_pre_compression_snapshot(session, old_sid: str, *, session_dir, logger=None, session_loader=None) -> None:
    """Persist old_sid as a read-only pre-compression snapshot."""
    old_path = session_dir / f'{old_sid}.json'
    if not old_path.exists():
        return
    try:
        existing_text = old_path.read_text(encoding='utf-8')
        try:
            existing = json.loads(existing_text)
            existing_msgs = len(existing.get('messages') or [])
        except (json.JSONDecodeError, ValueError):
            existing_msgs = -1
        if len(session.messages) > existing_msgs:
            saved_sid = session.session_id
            saved_snapshot = bool(getattr(session, 'pre_compression_snapshot', False))
            saved_active_stream_id = getattr(session, 'active_stream_id', None)
            saved_pending_user_message = getattr(session, 'pending_user_message', None)
            saved_pending_attachments = list(getattr(session, 'pending_attachments', []) or [])
            saved_pending_started_at = getattr(session, 'pending_started_at', None)

            session.session_id = old_sid
            session.pre_compression_snapshot = True
            session.active_stream_id = None
            session.pending_user_message = None
            session.pending_attachments = []
            session.pending_started_at = None
            try:
                session.save(touch_updated_at=False, skip_index=False)
                if logger is not None:
                    logger.info(
                        "Preserved pre-compression session %s (%d messages) to disk",
                        old_sid, len(session.messages),
                    )
            finally:
                session.session_id = saved_sid
                session.pre_compression_snapshot = saved_snapshot
                session.active_stream_id = saved_active_stream_id
                session.pending_user_message = saved_pending_user_message
                session.pending_attachments = saved_pending_attachments
                session.pending_started_at = saved_pending_started_at
            return

        if session_loader is None:
            from api.models import Session
            session_loader = Session.load
        snapshot = session_loader(old_sid)
        if snapshot:
            snapshot.pre_compression_snapshot = True
            snapshot.active_stream_id = None
            snapshot.pending_user_message = None
            snapshot.pending_attachments = []
            snapshot.pending_started_at = None
            snapshot.save(touch_updated_at=False, skip_index=False)
            if logger is not None:
                logger.info(
                    "Marked pre-compression session %s as sidebar-hidden snapshot",
                    old_sid,
                )
    except OSError:
        if logger is not None:
            logger.debug("Could not read old session file before preservation")
    except Exception:
        if logger is not None:
            logger.debug("Failed to preserve pre-compression session file", exc_info=True)


def find_current_user_turn(messages, msg_text):
    needle = " ".join(str(msg_text or '').split())
    fallback = None
    for idx, msg in enumerate(messages or []):
        if not isinstance(msg, dict) or msg.get('role') != 'user':
            continue
        fallback = idx
        if _looks_like_current_user_turn(msg, msg_text):
            return idx
        text = " ".join(
            _strip_workspace_prefix(
                _message_text(msg.get('content', '')),
                include_legacy=True,
            ).split()
        )
        if needle and (needle in text or text in needle):
            return idx
    return fallback


def drop_checkpointed_current_user_from_context(messages, msg_text):
    """Return model history without an eager-checkpointed current user turn."""
    history = list(messages or [])
    if not history:
        return history
    current_user_key = message_identity({'role': 'user', 'content': msg_text})
    if current_user_key and message_identity(history[-1]) == current_user_key:
        return history[:-1]
    return history


def normalize_fresh_chat_text(text):
    text = _strip_workspace_prefix(str(text or ''), include_legacy=True)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text.strip(" \t\r\n.!?\u3002\uff01\uff1f,\uff0c~\uff5e")


def is_casual_fresh_chat_message(msg_text):
    """Return True for short opener messages that should not resume old tasks."""
    text = normalize_fresh_chat_text(msg_text)
    if not text or len(text) > 24:
        return False
    continuation_terms = (
        "continue",
        "resume",
        "carry on",
        "go on",
        "\u7ee7\u7eed",
        "\u63a5\u7740",
        "\u5f80\u4e0b",
        "\u4e0b\u4e00\u6b65",
    )
    if any(term in text for term in continuation_terms):
        return False
    return text in {
        "hi",
        "hello",
        "hey",
        "hello there",
        "hi there",
        "\u4f60\u597d",
        "\u60a8\u597d",
        "\u55e8",
        "\u54c8\u55bd",
        "\u5728\u5417",
        "\u5728\u4e48",
    }


def has_task_resume_compaction_marker(messages):
    """Detect compacted model context that tells the agent to resume an old task."""
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        text = _message_text(msg.get('content', '')).lower()
        if not text:
            continue
        if "context compaction" not in text and "context compression" not in text:
            continue
        if (
            "active task" in text
            or "resume exactly" in text
            or "current task" in text
            or "task list was preserved" in text
            or "in_progress" in text
        ):
            return True
    return False


def context_messages_for_new_turn(session, msg_text):
    """Return provider-facing history for a new user turn."""
    history = drop_checkpointed_current_user_from_context(
        session_context_messages(session),
        msg_text,
    )
    if is_casual_fresh_chat_message(msg_text) and has_task_resume_compaction_marker(history):
        return []
    return history


def merge_display_messages_after_agent_result(previous_display, previous_context, result_messages, msg_text):
    """Keep UI transcript durable while allowing model context to compact."""
    previous_display = list(previous_display or [])
    previous_context = list(previous_context or [])
    result_messages = list(result_messages or [])
    if not result_messages:
        return previous_display

    if messages_have_prefix(result_messages, previous_context):
        candidates = result_messages[len(previous_context):]
    else:
        current_user_idx = find_current_user_turn(result_messages, msg_text)
        marker_candidates = [
            m for m in result_messages[:current_user_idx if current_user_idx is not None else len(result_messages)]
            if is_context_compression_marker(m)
        ]
        turn_candidates = result_messages[current_user_idx:] if current_user_idx is not None else []
        candidates = marker_candidates + turn_candidates

    merged = previous_display[:]
    seen = {message_identity(m) for m in merged}
    current_user_key = message_identity({'role': 'user', 'content': msg_text})
    current_user_in_candidates = any(
        message_identity(m) == current_user_key or _looks_like_current_user_turn(m, msg_text)
        for m in candidates
    )
    current_user_already_checkpointed = bool(
        merged
        and (
            message_identity(merged[-1]) == current_user_key
            or _looks_like_current_user_turn(merged[-1], msg_text)
        )
    )
    if (
        current_user_key is not None
        and not current_user_in_candidates
        and not current_user_already_checkpointed
        and any(
            isinstance(m, dict) and m.get('role') in ('assistant', 'tool')
            for m in candidates
        )
    ):
        current_user_msg = {'role': 'user', 'content': msg_text}
        insert_at = 0
        while insert_at < len(candidates) and is_context_compression_marker(candidates[insert_at]):
            insert_at += 1
        candidates = candidates[:insert_at] + [current_user_msg] + candidates[insert_at:]

    for msg in candidates:
        key = message_identity(msg)
        is_current_user_turn = _looks_like_current_user_turn(msg, msg_text)
        if (
            ((key is not None and key == current_user_key) or is_current_user_turn)
            and merged
            and (
                message_identity(merged[-1]) == current_user_key
                or _looks_like_current_user_turn(merged[-1], msg_text)
            )
        ):
            continue
        if (
            key is not None
            and isinstance(msg, dict)
            and msg.get('role') == 'assistant'
            and merged
            and message_identity(merged[-1]) == key
        ):
            continue
        if is_context_compression_marker(msg) and key is not None and key in seen:
            continue
        display_msg = msg
        if (
            ((key is not None and key == current_user_key) or is_current_user_turn)
            and isinstance(msg, dict)
            and msg.get('role') == 'user'
        ):
            display_msg = copy.deepcopy(msg)
            display_msg['content'] = msg_text
        merged.append(copy.deepcopy(display_msg))
        if key is not None:
            seen.add(key)
    return merged


def assistant_reply_added_after_current_turn(result_messages, previous_context, msg_text) -> bool:
    """Return True only when the just-finished turn produced assistant text."""
    result_messages = list(result_messages or [])
    previous_context = list(previous_context or [])
    if messages_have_prefix(result_messages, previous_context):
        candidates = result_messages[len(previous_context):]
    else:
        current_user_idx = find_current_user_turn(result_messages, msg_text)
        candidates = result_messages[current_user_idx + 1:] if current_user_idx is not None else result_messages
    return any(
        isinstance(m, dict)
        and m.get('role') == 'assistant'
        and not m.get('_error')
        and str(m.get('content') or '').strip()
        for m in candidates
    )

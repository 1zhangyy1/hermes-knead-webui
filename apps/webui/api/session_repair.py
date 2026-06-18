"""Helpers for repairing interrupted in-flight session turns."""


def append_recovered_turn_to_context(session, recovered: dict) -> None:
    context_messages = getattr(session, 'context_messages', None)
    if not isinstance(context_messages, list) or not context_messages:
        return
    recovered_text = " ".join(str(recovered.get('content') or '').split())
    if recovered_text:
        for existing in reversed(context_messages[-8:]):
            if not isinstance(existing, dict) or existing.get('role') != 'user':
                continue
            existing_text = " ".join(str(existing.get('content') or '').split())
            if existing_text == recovered_text:
                return
    context_entry = {k: v for k, v in recovered.items() if k != 'timestamp'}
    context_messages.append(context_entry)


def append_recovered_pending_turn(
    session,
    *,
    timestamp: int | None = None,
    now,
    append_recovered_turn_to_context,
) -> dict | None:
    pending_text = str(session.pending_user_message or '')
    if not pending_text:
        return None
    recovered_ts = int(now())
    if isinstance(timestamp, (int, float)) and timestamp > 0:
        recovered_ts = int(timestamp)
    recovered: dict = {
        'role': 'user',
        'content': session.pending_user_message,
        'timestamp': recovered_ts,
        '_recovered': True,
    }
    if session.pending_attachments:
        recovered['attachments'] = list(session.pending_attachments)
    session.messages.append(recovered)
    append_recovered_turn_to_context(session, recovered)
    return recovered


def interrupted_recovery_marker(*, recovered_output: bool = False, now) -> dict:
    if recovered_output:
        content = (
            '**Response interrupted.**\n\n'
            'The WebUI process restarted before this turn finished. '
            'The partial output above was recovered from the run journal, '
            'but the interrupted agent process could not continue.'
        )
    else:
        content = (
            '**Response interrupted.**\n\n'
            'The WebUI process restarted before this turn finished. '
            'The user message above was preserved, but no agent output was recovered.'
        )
    return {
        'role': 'assistant',
        'content': content,
        'timestamp': int(now()),
        '_error': True,
        'type': 'interrupted',
    }


def truncate_journal_tool_args(args, limit: int = 4) -> dict:
    if not isinstance(args, dict):
        return {}
    out = {}
    for key, value in list(args.items())[:limit]:
        text = str(value)
        out[str(key)] = text[:120] + ('...' if len(text) > 120 else '')
    return out


def normalize_journal_recovery_text(value) -> str:
    return " ".join(str(value or "").split())


def find_existing_assistant_for_journal_content(session, content: str) -> int | None:
    candidate = normalize_journal_recovery_text(content)
    if not candidate:
        return None
    for idx, message in enumerate(session.messages or []):
        if not isinstance(message, dict) or message.get('role') != 'assistant':
            continue
        if message.get('_error'):
            continue
        existing = normalize_journal_recovery_text(message.get('content'))
        if not existing:
            continue
        if existing == candidate:
            return idx
        if len(candidate) >= 24 and candidate in existing:
            return idx
    return None


def journal_tool_already_present(session, name: str, preview: str) -> bool:
    candidate_name = str(name or '')
    candidate_preview = normalize_journal_recovery_text(preview)
    for tool_call in session.tool_calls or []:
        if not isinstance(tool_call, dict):
            continue
        if str(tool_call.get('name') or '') != candidate_name:
            continue
        existing_preview = normalize_journal_recovery_text(
            tool_call.get('preview') or tool_call.get('snippet') or ''
        )
        if existing_preview == candidate_preview:
            return True
    return False


def run_journal_has_visible_output(session, stream_id: str | None, *, read_run_events) -> bool:
    if not stream_id:
        return False
    try:
        journal = read_run_events(session.session_id, stream_id)
    except Exception:
        return False
    for event in journal.get('events') or []:
        if not isinstance(event, dict):
            continue
        event_name = str(event.get('event') or event.get('type') or '')
        payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
        if event_name == 'token' and str(payload.get('text') or ''):
            return True
        if event_name == 'interim_assistant':
            if payload.get('already_streamed'):
                continue
            if str(payload.get('text') or '').strip():
                return True
        if event_name == 'tool':
            return True
    return False


def append_journaled_partial_output(
    session,
    stream_id: str | None,
    *,
    read_run_events,
    logger,
    now,
    find_existing_assistant_for_journal_content,
    journal_tool_already_present,
    truncate_journal_tool_args,
    dedupe_existing: bool = False,
) -> bool:
    """Recover already-emitted visible output from a dead stream journal."""
    if not stream_id:
        return False

    try:
        journal = read_run_events(session.session_id, stream_id)
    except Exception:
        logger.debug(
            "Session %s: failed to read run journal for stream %s",
            getattr(session, 'session_id', '?'),
            stream_id,
            exc_info=True,
        )
        return False

    events = [event for event in journal.get('events') or [] if isinstance(event, dict)]
    if not events:
        return False

    appended_any = False
    assistant_parts: list[str] = []
    assistant_started_at: float | None = None
    current_assistant_idx: int | None = None
    recovered_tool_calls: list[dict] = []

    def flush_assistant() -> int | None:
        nonlocal appended_any, assistant_parts, assistant_started_at, current_assistant_idx
        content = ''.join(assistant_parts).strip()
        assistant_parts = []
        if not content:
            return current_assistant_idx
        if dedupe_existing:
            existing_idx = find_existing_assistant_for_journal_content(session, content)
            if existing_idx is not None:
                current_assistant_idx = existing_idx
                assistant_started_at = None
                return existing_idx
        timestamp = int(assistant_started_at or now())
        session.messages.append({
            'role': 'assistant',
            'content': content,
            'timestamp': timestamp,
            '_recovered_from_run_journal': True,
            '_recovered_stream_id': stream_id,
        })
        current_assistant_idx = len(session.messages) - 1
        assistant_started_at = None
        appended_any = True
        return current_assistant_idx

    def ensure_assistant_anchor(created_at: float | None = None) -> int:
        nonlocal appended_any, current_assistant_idx
        idx = flush_assistant()
        if idx is not None:
            return idx
        session.messages.append({
            'role': 'assistant',
            'content': '',
            'timestamp': int(created_at or now()),
            '_recovered_from_run_journal': True,
            '_recovered_stream_id': stream_id,
        })
        current_assistant_idx = len(session.messages) - 1
        appended_any = True
        return current_assistant_idx

    for event in events:
        event_name = str(event.get('event') or event.get('type') or '')
        payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
        created_at = event.get('created_at') if isinstance(event.get('created_at'), (int, float)) else None
        if event_name == 'token':
            text = str(payload.get('text') or '')
            if not text:
                continue
            if not assistant_parts and assistant_started_at is None:
                assistant_started_at = created_at or now()
            assistant_parts.append(text)
            continue
        if event_name == 'interim_assistant':
            if payload.get('already_streamed'):
                flush_assistant()
                continue
            text = str(payload.get('text') or '').strip()
            if not text:
                continue
            if not assistant_parts and assistant_started_at is None:
                assistant_started_at = created_at or now()
            if assistant_parts and not ''.join(assistant_parts).endswith(('\n', ' ')):
                assistant_parts.append('\n\n')
            assistant_parts.append(text)
            flush_assistant()
            continue
        if event_name == 'tool':
            anchor_idx = flush_assistant()
            if anchor_idx is None:
                anchor_idx = ensure_assistant_anchor(created_at)
            name = str(payload.get('name') or 'tool')
            preview = str(payload.get('preview') or '')
            if dedupe_existing and journal_tool_already_present(session, name, preview):
                current_assistant_idx = anchor_idx
                continue
            recovered_tool_calls.append({
                'name': name,
                'preview': preview,
                'snippet': preview,
                'tid': f"journal-{event.get('seq') or len(recovered_tool_calls) + 1}",
                'assistant_msg_idx': anchor_idx,
                'args': truncate_journal_tool_args(payload.get('args') or {}),
                'done': False,
                '_recovered_from_run_journal': True,
                '_recovered_stream_id': stream_id,
            })
            appended_any = True
            current_assistant_idx = anchor_idx
            continue
        if event_name == 'tool_complete':
            name = str(payload.get('name') or '')
            for tool_call in reversed(recovered_tool_calls):
                if tool_call.get('done'):
                    continue
                if not name or tool_call.get('name') == name:
                    tool_call['done'] = True
                    if payload.get('preview'):
                        tool_call['preview'] = str(payload.get('preview') or '')
                        tool_call['snippet'] = str(payload.get('preview') or '')
                    if payload.get('duration') is not None:
                        tool_call['duration'] = payload.get('duration')
                    tool_call['is_error'] = bool(payload.get('is_error', False))
                    break
            continue
        if event_name in {'done', 'stream_end', 'cancel', 'apperror', 'error'}:
            flush_assistant()

    flush_assistant()
    if recovered_tool_calls:
        session.tool_calls = list(session.tool_calls or []) + recovered_tool_calls
        appended_any = True
    return appended_any

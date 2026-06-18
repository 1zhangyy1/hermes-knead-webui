"""Helpers for repairing interrupted in-flight session turns."""

import json


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


def apply_core_sync_or_error_marker(
    session,
    core_path,
    stream_id_for_recheck=None,
    *,
    require_stream_dead=True,
    touch_updated_at=True,
    active_stream_ids,
    append_recovered_pending_turn,
    append_recovered_turn_to_context,
    append_journaled_partial_output,
    interrupted_recovery_marker,
    normalize_journal_recovery_text,
    run_journal_has_visible_output,
    logger,
    now,
) -> bool:
    """Sync a crashed turn from core transcript or materialize a recovery marker."""
    sid = session.session_id
    if not session.pending_user_message:
        return False
    if stream_id_for_recheck is not None:
        if session.active_stream_id != stream_id_for_recheck:
            return False
        if require_stream_dead and session.active_stream_id in active_stream_ids():
            return False

    if len(session.messages) != 0:
        pending_text = " ".join(str(session.pending_user_message or "").split())
        already_checkpointed = False
        if pending_text and session.messages:
            last_msg = session.messages[-1]
            if isinstance(last_msg, dict) and last_msg.get('role') == 'user':
                last_text = " ".join(str(last_msg.get('content') or "").split())
                already_checkpointed = last_text == pending_text
        recovered_ts = int(now())
        if isinstance(session.pending_started_at, (int, float)) and session.pending_started_at > 0:
            recovered_ts = int(session.pending_started_at)
        if not already_checkpointed:
            append_recovered_pending_turn(session, timestamp=recovered_ts)
        else:
            recovered = {
                'role': 'user',
                'content': session.pending_user_message,
                '_recovered': True,
            }
            if session.pending_attachments:
                recovered['attachments'] = list(session.pending_attachments)
            append_recovered_turn_to_context(session, recovered)
        recovered_output = append_journaled_partial_output(
            session,
            stream_id_for_recheck or session.active_stream_id,
        )
        session.active_stream_id = None
        session.pending_user_message = None
        session.pending_attachments = []
        session.pending_started_at = None
        session.messages.append(interrupted_recovery_marker(recovered_output=recovered_output))
        session.save(touch_updated_at=touch_updated_at)
        logger.info(
            "Session %s: recovered pending user turn (messages non-empty), added error marker",
            sid,
        )
        return True

    if core_path.exists():
        with open(core_path, encoding='utf-8') as f:
            core = json.load(f)
        core_messages = core.get('messages', [])
        if core_messages:
            stream_id = stream_id_for_recheck or session.active_stream_id
            session.messages = core_messages
            session.tool_calls = core.get('tool_calls', [])
            for field in ('input_tokens', 'output_tokens', 'estimated_cost'):
                if core.get(field) is not None:
                    setattr(session, field, core[field])
            pending_text = normalize_journal_recovery_text(session.pending_user_message)
            already_checkpointed = False
            if pending_text and session.messages:
                for last_msg in reversed(session.messages):
                    if isinstance(last_msg, dict) and last_msg.get('role') == 'user':
                        last_text = normalize_journal_recovery_text(last_msg.get('content'))
                        already_checkpointed = last_text == pending_text
                        break
            if (
                pending_text
                and not already_checkpointed
                and run_journal_has_visible_output(session, stream_id)
            ):
                recovered_ts = int(now())
                if isinstance(session.pending_started_at, (int, float)) and session.pending_started_at > 0:
                    recovered_ts = int(session.pending_started_at)
                append_recovered_pending_turn(session, timestamp=recovered_ts)
            recovered_output = append_journaled_partial_output(
                session,
                stream_id,
                dedupe_existing=True,
            )
            session.active_stream_id = None
            session.pending_user_message = None
            session.pending_attachments = []
            session.pending_started_at = None
            if recovered_output:
                session.messages.append(
                    interrupted_recovery_marker(recovered_output=True)
                )
            session.save(touch_updated_at=touch_updated_at)
            logger.info(
                "Session %s: synced %d messages from core transcript%s",
                sid,
                len(core_messages),
                " and recovered journaled output" if recovered_output else "",
            )
            return True

    if session.pending_user_message:
        recovered_ts = int(now())
        if isinstance(session.pending_started_at, (int, float)) and session.pending_started_at > 0:
            recovered_ts = int(session.pending_started_at)
        append_recovered_pending_turn(session, timestamp=recovered_ts)
    recovered_output = append_journaled_partial_output(
        session,
        stream_id_for_recheck or session.active_stream_id,
    )
    session.active_stream_id = None
    session.pending_user_message = None
    session.pending_attachments = []
    session.pending_started_at = None
    session.messages.append(interrupted_recovery_marker(recovered_output=recovered_output))
    session.save(touch_updated_at=touch_updated_at)
    logger.info("Session %s: no core transcript found, added error marker", sid)
    return True


def repair_stale_pending(
    session,
    *,
    active_stream_ids,
    get_profile_home,
    get_session_agent_lock,
    apply_core_sync_or_error_marker,
    logger,
    now,
    grace_seconds: float,
) -> bool:
    """Recover a sidecar stuck with empty messages and stale pending state."""
    seen_stream_id = session.active_stream_id
    if (not session.pending_user_message
            or not seen_stream_id
            or seen_stream_id in active_stream_ids()):
        return False

    started = getattr(session, 'pending_started_at', None)
    if started:
        try:
            age = now() - float(started)
        except (TypeError, ValueError):
            age = float('inf')
        if age < grace_seconds:
            logger.debug(
                "_repair_stale_pending: skipping repair for session %s — "
                "pending_started_at age=%.1fs < %ds grace window",
                session.session_id, age, grace_seconds,
            )
            return False
    else:
        age = float('inf')

    sid = session.session_id
    if not sid or not all(c in '0123456789abcdefghijklmnopqrstuvwxyz_' for c in sid):
        return False

    try:
        profile_home = get_profile_home(session.profile)
        core_path = profile_home / 'sessions' / f'session_{sid}.json'

        lock = get_session_agent_lock(sid)
        if not lock.acquire(blocking=False):
            logger.debug(
                "_repair_stale_pending: lock contended, skipping repair for session %s", sid,
            )
            return False
        try:
            diag_warn_window_seconds = 300
            age_str = ('inf' if age == float('inf') else f'{age:.1f}s')
            log = logger.warning if age < diag_warn_window_seconds else logger.debug
            log(
                "_repair_stale_pending firing: session=%s stream_id=%s pending_age=%s",
                sid, seen_stream_id, age_str,
            )
            return apply_core_sync_or_error_marker(
                session, core_path, stream_id_for_recheck=seen_stream_id,
            )
        finally:
            lock.release()
    except Exception:
        logger.exception("_repair_stale_pending failed for session %s", sid)
        return False

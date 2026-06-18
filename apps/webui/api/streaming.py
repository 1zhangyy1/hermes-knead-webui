"""
Hermes Web UI -- SSE streaming engine and agent thread runner.
Includes Sprint 10 cancel support via CANCEL_FLAGS.
"""
import contextlib
import json
import logging
import os
import re
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from api.config import (
    get_config,
    STREAMS, STREAMS_LOCK, CANCEL_FLAGS, AGENT_INSTANCES, STREAM_PARTIAL_TEXT,
    STREAM_REASONING_TEXT, STREAM_LIVE_TOOL_CALLS,
    STREAM_GOAL_RELATED, PENDING_GOAL_CONTINUATION,
    STREAM_LAST_EVENT_ID,
    LOCK, SESSIONS, SESSION_DIR,
    _get_session_agent_lock, _set_thread_env, _clear_thread_env,
    register_active_run, update_active_run, unregister_active_run,
    SESSION_AGENT_LOCKS, SESSION_AGENT_LOCKS_LOCK,
    resolve_model_provider,
    resolve_custom_provider_connection,
    model_with_provider_context,
    load_settings,
)
from api.helpers import redact_session_data, _redact_text
from api.compression_anchor import visible_messages_for_anchor
from api.metering import meter
from api.run_journal import RunJournalWriter
from api.turn_journal import append_turn_journal_event_for_stream
from api.streaming_errors import (
    CANCEL_MARKER_PATTERNS as _CANCEL_MARKER_PATTERNS,
    cancelled_turn_content as _cancelled_turn_content_impl,
    cancelled_turn_hint as _cancelled_turn_hint_impl,
    classify_provider_error as _classify_provider_error_impl,
    is_quota_error_text as _is_quota_error_text_impl,
    preferred_agent_display_name as _preferred_agent_display_name_impl,
    provider_error_payload as _provider_error_payload_impl,
)
from api.streaming_gateway import (
    GATEWAY_ROUTING_ATTEMPT_KEYS as _GATEWAY_ROUTING_ATTEMPT_KEYS,
    GATEWAY_ROUTING_CONTAINER_KEYS as _GATEWAY_ROUTING_CONTAINER_KEYS,
    GATEWAY_ROUTING_TOP_LEVEL_KEYS as _GATEWAY_ROUTING_TOP_LEVEL_KEYS,
    clean_gateway_routing_scalar as _clean_gateway_routing_scalar,
    extract_gateway_routing_metadata as _extract_gateway_routing_metadata,
    find_gateway_metadata_payload as _find_gateway_metadata_payload,
    normalize_gateway_routing_metadata as _normalize_gateway_routing_metadata,
)
from api.streaming_attachments import (
    IMAGE_MAGIC as _IMAGE_MAGIC,
    NATIVE_IMAGE_MAX_BYTES as _NATIVE_IMAGE_MAX_BYTES,
    attachment_name as _attachment_name,
    build_native_multimodal_message as _build_native_multimodal_message,
    is_valid_image as _is_valid_image,
)
from api.streaming_context import (
    API_SAFE_MSG_KEYS as _API_SAFE_MSG_KEYS_IMPL,
    api_safe_message_positions as _api_safe_message_positions_impl,
    assistant_reply_added_after_current_turn as _assistant_reply_added_after_current_turn_impl,
    compact_summary_text as _compact_summary_text_impl,
    compression_anchor_message_key as _compression_anchor_message_key_impl,
    compression_summary_from_messages as _compression_summary_from_messages_impl,
    context_messages_for_new_turn as _context_messages_for_new_turn_impl,
    drop_checkpointed_current_user_from_context as _drop_checkpointed_current_user_from_context_impl,
    find_current_user_turn as _find_current_user_turn_impl,
    has_task_resume_compaction_marker as _has_task_resume_compaction_marker_impl,
    is_casual_fresh_chat_message as _is_casual_fresh_chat_message_impl,
    is_context_compression_marker as _is_context_compression_marker_impl,
    merge_display_messages_after_agent_result as _merge_display_messages_after_agent_result_impl,
    message_identity as _message_identity_impl,
    messages_have_prefix as _messages_have_prefix_impl,
    normalize_fresh_chat_text as _normalize_fresh_chat_text_impl,
    restore_reasoning_metadata as _restore_reasoning_metadata_impl,
    sanitize_messages_for_api as _sanitize_messages_for_api_impl,
    session_context_messages as _session_context_messages_impl,
    strip_native_image_parts_from_content as _strip_native_image_parts_from_content_impl,
)
from api.streaming_tool_calls import (
    TOOL_RESULT_SNIPPET_MAX as _TOOL_RESULT_SNIPPET_MAX,
    extract_tool_calls_from_messages as _extract_tool_calls_from_messages,
    nearest_assistant_msg_idx as _nearest_assistant_msg_idx,
    tool_result_snippet as _tool_result_snippet,
    truncate_tool_args as _truncate_tool_args,
)
from api.streaming_tool_bridge import StreamingToolEventBridge as _StreamingToolEventBridge
from api.streaming_agent_runtime import (
    agent_cache_api_key_sig as _agent_cache_api_key_sig,
    refresh_cached_agent_primary_runtime_snapshot as _refresh_cached_agent_primary_runtime_snapshot,
    refresh_cached_agent_runtime as _refresh_cached_agent_runtime,
)
from api.streaming_agent_config import (
    resolve_fallback_config as _resolve_fallback_config_impl,
    resolve_max_iterations_config as _resolve_max_iterations_config_impl,
    resolve_max_tokens_config as _resolve_max_tokens_config_impl,
    resolve_reasoning_config as _resolve_reasoning_config_impl,
)
from api.streaming_agent_status import make_agent_status_callback as _make_agent_status_callback
from api.streaming_event_sink import StreamingEventSink as _StreamingEventSink
from api.streaming_live_usage import LiveUsageTracker as _LiveUsageTracker
from api.streaming_metering import StreamingMeteringTicker as _StreamingMeteringTicker
from api.streaming_output_bridge import StreamingOutputBridge as _StreamingOutputBridge
from api.streaming_process_notifications import (
    drain_webui_process_notifications as _drain_webui_process_notifications_impl,
    format_process_notification as _format_process_notification_impl,
    mark_process_completion_consumed as _mark_process_completion_consumed_impl,
)
from api.streaming_product_turn import ProductTurnFinalizer as _ProductTurnFinalizer
from api.streaming_titles import (
    LEGACY_WORKSPACE_PREFIX_ANY_RE as _LEGACY_WORKSPACE_PREFIX_ANY_RE,
    LEGACY_WORKSPACE_PREFIX_RE as _LEGACY_WORKSPACE_PREFIX_RE,
    WORKSPACE_PREFIX_ANY_RE as _WORKSPACE_PREFIX_ANY_RE,
    WORKSPACE_PREFIX_RE as _WORKSPACE_PREFIX_RE,
    count_exchanges as _count_exchanges,
    escape_workspace_prefix_path as _escape_workspace_prefix_path,
    fallback_title_from_exchange as _fallback_title_from_exchange,
    first_exchange_snippets as _first_exchange_snippets,
    is_generic_fallback_title as _is_generic_fallback_title,
    is_provisional_title as _is_provisional_title_impl,
    latest_exchange_snippets as _latest_exchange_snippets,
    looks_invalid_generated_title as _looks_invalid_generated_title,
    sanitize_generated_title as _sanitize_generated_title,
    strip_thinking_markup as _strip_thinking_markup,
    strip_workspace_prefix as _strip_workspace_prefix,
    workspace_context_prefix as _workspace_context_prefix,
)
# Source-guard anchor: streaming title helpers still reject generic completion
# phrases such as "all set" before persisting generated session titles.
from api.streaming_title_generation import (
    _aux_title_configured as _aux_title_configured_impl,
    _aux_title_timeout as _aux_title_timeout_impl,
    _extract_title_response as _extract_title_response_impl,
    _generate_llm_session_title_for_agent as _generate_llm_session_title_for_agent_impl,
    _generate_llm_session_title_via_aux as _generate_llm_session_title_via_aux_impl,
    _is_minimax_route as _is_minimax_route_impl,
    _safe_obj_value as _safe_obj_value_impl,
    _safe_text_value as _safe_text_value_impl,
    _title_completion_budget as _title_completion_budget_impl,
    _title_retry_completion_budget as _title_retry_completion_budget_impl,
    _title_retry_status as _title_retry_status_impl,
    _title_should_skip_remaining_attempts as _title_should_skip_remaining_attempts_impl,
    generate_title_raw_via_agent as _generate_title_raw_via_agent_impl,
    generate_title_raw_via_aux as _generate_title_raw_via_aux_impl,
)
# Source-guard anchor: MiniMax title calls set reasoning_split in
# streaming_title_generation while streaming.py keeps the public wrappers.
from api.streaming_recovery import (
    attempt_credential_self_heal as _attempt_credential_self_heal_impl,
    last_resort_sync_from_core as _last_resort_sync_from_core_impl,
    materialize_pending_user_turn_before_error as _materialize_pending_user_turn_before_error_impl,
)
from api.streaming_runtime_helpers import (
    WEBUI_VISIBLE_PROGRESS_PROMPT as _WEBUI_VISIBLE_PROGRESS_PROMPT_IMPL,
    aiagent_import_error_detail as _aiagent_import_error_detail_impl,
    build_agent_thread_env as _build_agent_thread_env,
    clarify_timeout_seconds as _clarify_timeout_seconds_impl,
    has_new_assistant_reply as _has_new_assistant_reply_impl,
    webui_clarify_callback as _webui_clarify_callback_impl,
    webui_ephemeral_system_prompt as _webui_ephemeral_system_prompt_impl,
)

# Global lock for os.environ writes. Per-session locks (_agent_lock) prevent
# concurrent runs of the SAME session, but two DIFFERENT sessions can still
# interleave their os.environ writes. This global lock serializes the env
# save/restore — held only briefly across the env-mutation critical section,
# NOT for the entire agent run. The agent runs outside the lock; the finally
# block re-acquires to atomically restore env vars. See narrow-lock pattern
# in _run_agent_streaming (line ~2719) and profile_env_for_background_worker
# (api/profiles.py:715).
_ENV_LOCK = threading.Lock()


def _prewarm_skill_tool_modules():
    """Import tools.skills_tool and tools.skill_manager_tool outside any lock.

    First-time module imports can trigger heavy initialisation (disk I/O,
    transitive imports, plugin discovery).  Performing those imports while
    holding ``_ENV_LOCK`` serialises every concurrent session behind the
    slowest import.  Prewarming ensures the modules are already in
    ``sys.modules`` before the lock is acquired, so the lock body only
    does lightweight attribute patching.

    We cannot place these at module top-level because ``tools.*`` lives
    in the hermes-agent package which may not be on ``sys.path`` at
    import time (Docker volume-mount ordering).  A dedicated helper
    keeps the lazy-import try/except in one place and makes the intent
    explicit.
    """
    for _mod_name in ('tools.skills_tool', 'tools.skill_manager_tool'):
        try:
            __import__(_mod_name)
        except ImportError:
            pass


# Lazy import to avoid circular deps -- hermes-agent is on sys.path via api/config.py
try:
    from run_agent import AIAgent
except ImportError:
    AIAgent = None

def _get_ai_agent():
    """Return AIAgent class, retrying the import if the initial attempt failed.

    auto_install_agent_deps() in server.py may install missing packages after
    this module is first imported (common in Docker with a volume-mounted agent).
    Re-attempting the import here picks up the newly installed packages without
    requiring a server restart.
    """
    global AIAgent
    if AIAgent is None:
        try:
            from run_agent import AIAgent as _cls  # noqa: PLC0415
            AIAgent = _cls
        except ImportError:
            pass
    return AIAgent


def _is_quota_error_text(err_text: str) -> bool:
    return _is_quota_error_text_impl(err_text)


def _clarify_timeout_seconds(default: int = 120) -> int:
    return _clarify_timeout_seconds_impl(get_config, default)


_WEBUI_VISIBLE_PROGRESS_PROMPT = _WEBUI_VISIBLE_PROGRESS_PROMPT_IMPL

def _webui_ephemeral_system_prompt(personality_prompt: Optional[str], product_prompt: Optional[str] = None) -> str:
    return _webui_ephemeral_system_prompt_impl(personality_prompt, product_prompt)


def _has_new_assistant_reply(all_messages: list, prev_count: int) -> bool:
    return _has_new_assistant_reply_impl(all_messages, prev_count)


def _preferred_agent_display_name() -> str:
    return _preferred_agent_display_name_impl(
        load_settings_fn=load_settings,
        logger=logger,
    )


def _cancelled_turn_hint(agent_name: str | None = None) -> str:
    return _cancelled_turn_hint_impl(
        agent_name,
        load_settings_fn=load_settings,
        logger=logger,
    )


def _classify_provider_error(err_str: str, exc=None, *, silent_failure: bool = False) -> dict:
    return _classify_provider_error_impl(
        err_str,
        exc,
        silent_failure=silent_failure,
        cancelled_turn_hint_fn=_cancelled_turn_hint,
        is_quota_error_text_fn=_is_quota_error_text,
    )


def _provider_error_payload(message: str, err_type: str, hint: str = '') -> dict:
    return _provider_error_payload_impl(
        message,
        err_type,
        hint,
        redact_text_fn=_redact_text,
    )


def _session_has_cancel_marker(session) -> bool:
    """Return True if a visible cancel/interrupted marker is already persisted."""
    for msg in reversed(getattr(session, 'messages', None) or []):
        if not isinstance(msg, dict):
            continue
        if msg.get('role') == 'user':
            return False
        if msg.get('role') != 'assistant':
            continue
        content = msg.get('content')
        text = ''
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    parts.append(str(part.get('text') or part.get('content') or ''))
            text = '\n'.join(parts)
        normalized = text.strip().lower()
        if any(pattern in normalized for pattern in _CANCEL_MARKER_PATTERNS):
            return True
    return False


def _cancelled_turn_content(message: str = 'Task cancelled.') -> str:
    return _cancelled_turn_content_impl(
        message,
        cancelled_turn_hint_fn=_cancelled_turn_hint,
    )


def _persist_cancelled_turn(session, *, message: str = 'Task cancelled.') -> None:
    """Persist a user-cancelled terminal state without provider-error wording.

    cancel_stream() usually writes this marker first, but the streaming thread can
    later unwind through the silent-failure or exception path. Those paths must
    not append a misleading provider no-response error after an explicit cancel.
    """
    _materialize_pending_user_turn_before_error(session)
    session.active_stream_id = None
    session.pending_user_message = None
    session.pending_attachments = []
    session.pending_started_at = None
    if not _session_has_cancel_marker(session):
        session.messages.append({
            'role': 'assistant',
            'content': _cancelled_turn_content(message),
            '_error': True,
            'provider_details': str(message or 'Task cancelled.').strip(),
            'provider_details_label': 'Cancellation details',
            'timestamp': int(time.time()),
        })


def _cleanup_ephemeral_cancelled_turn(session) -> None:
    """Remove transient /btw session state after a cancel without saving it."""
    session.active_stream_id = None
    session.pending_user_message = None
    session.pending_attachments = []
    session.pending_started_at = None
    try:
        import pathlib
        pathlib.Path(session.path).unlink(missing_ok=True)
    except Exception:
        logger.debug("Failed to clean up ephemeral cancelled session", exc_info=True)


def _finalize_cancelled_turn(session, *, ephemeral: bool = False, message: str = 'Task cancelled.') -> None:
    """Finalize a cancelled turn for persistent or ephemeral sessions."""
    if ephemeral:
        _cleanup_ephemeral_cancelled_turn(session)
        return
    _persist_cancelled_turn(session, message=message)
    try:
        session.save()
    except Exception:
        logger.debug("Failed to persist cancelled turn", exc_info=True)


def _aiagent_import_error_detail() -> str:
    return _aiagent_import_error_detail_impl()
from api.models import get_session, title_from
from api.workspace import set_last_workspace

# Fields that are safe to send to LLM provider APIs.
# Everything else (attachments, timestamp, _ts, etc.) is display-only
# metadata added by the webui and must be stripped before the API call.
_API_SAFE_MSG_KEYS = _API_SAFE_MSG_KEYS_IMPL


def _format_process_notification(evt: dict) -> str:
    return _format_process_notification_impl(evt)


def _mark_process_completion_consumed(process_registry, process_id: str) -> None:
    _mark_process_completion_consumed_impl(process_registry, process_id, logger=logger)


def _drain_webui_process_notifications(session_id: str) -> list[str]:
    return _drain_webui_process_notifications_impl(session_id, logger=logger)


def _strip_xml_tool_calls(text: str) -> str:
    """Strip XML-style function_calls blocks that DeepSeek and similar models
    emit in their raw response text.  These blocks are processed separately as
    tool calls; leaving them in the assistant content causes them to render
    visibly in the chat bubble.

    Handles both complete blocks (<function_calls>…</function_calls>) and
    partial/orphaned opening tags that may appear at the tail of a stream.
    Also handles variants like <｜DSML｜function_calls> from DeepSeek on Bedrock.
    """
    if not text:
        return text
    s = str(text)
    # Check if contains any function_calls/DSML marker (case-insensitive)
    _lo = s.lower()
    if 'function_calls' not in _lo and 'dsml' not in _lo:
        return text
    
    _dsml_prefix = r'(?:\s*｜\s*DSML\s*[｜|]\s*)?'
    open_tag = rf'<{_dsml_prefix}function_calls'
    close_tag = rf'</{_dsml_prefix}function_calls>'
    # Strip complete blocks for both <function_calls> and <｜DSML｜function_calls>.
    s = re.sub(
        rf'{open_tag}>.*?{close_tag}',
        '',
        s,
        flags=re.IGNORECASE | re.DOTALL
    )
    # Strip orphaned/truncated opening tags, including missing ">" at stream tail.
    s = re.sub(
        rf'{open_tag}(?:>|$).*$',
        '',
        s,
        flags=re.IGNORECASE | re.DOTALL
    )
    # Remove malformed DSML fragments like "<｜DSML |" that can leak in tokens.
    s = re.sub(r'<\s*｜\s*DSML\s*[｜|]\s*', '', s, flags=re.IGNORECASE)
    return s.strip()


def _get_title_refresh_interval() -> int:
    """Read the auto_title_refresh_every setting (0 = disabled)."""
    try:
        from api.config import load_settings
        settings = load_settings()
        val = settings.get('auto_title_refresh_every', '0')
        return int(val) if str(val).strip().isdigit() and int(val) > 0 else 0
    except Exception:
        return 0


def _is_provisional_title(current_title: str, messages) -> bool:
    return _is_provisional_title_impl(current_title, messages, title_from_fn=title_from)


def _is_minimax_route(provider: str = '', model: str = '', base_url: str = '') -> bool:
    return _is_minimax_route_impl(provider, model, base_url)


def _aux_title_configured() -> bool:
    return _aux_title_configured_impl()


def _aux_title_timeout(default: float = 15.0) -> float:
    return _aux_title_timeout_impl(default)


def _title_completion_budget(provider: str = '', model: str = '', base_url: str = '') -> int:
    return _title_completion_budget_impl(provider, model, base_url)


def _title_retry_completion_budget(provider: str = '', model: str = '', base_url: str = '') -> int:
    return _title_retry_completion_budget_impl(provider, model, base_url)


def _title_retry_status(status: str) -> bool:
    return _title_retry_status_impl(status)


def _title_should_skip_remaining_attempts(status: str) -> bool:
    return _title_should_skip_remaining_attempts_impl(status)


def _safe_obj_value(obj, key: str):
    return _safe_obj_value_impl(obj, key)


def _safe_text_value(value) -> str:
    return _safe_text_value_impl(value)


def _extract_title_response(resp, *, aux: bool = False) -> tuple[str, str]:
    return _extract_title_response_impl(resp, aux=aux)


def generate_title_raw_via_aux(
    user_text: str,
    assistant_text: str,
    provider: str = '',
    model: str = '',
    base_url: str = '',
) -> tuple[Optional[str], str]:
    return _generate_title_raw_via_aux_impl(
        user_text,
        assistant_text,
        provider=provider,
        model=model,
        base_url=base_url,
    )


def generate_title_raw_via_agent(agent, user_text: str, assistant_text: str) -> tuple[Optional[str], str]:
    return _generate_title_raw_via_agent_impl(agent, user_text, assistant_text)


def _generate_llm_session_title_for_agent(agent, user_text: str, assistant_text: str) -> tuple[Optional[str], str, str]:
    return _generate_llm_session_title_for_agent_impl(agent, user_text, assistant_text)


def _generate_llm_session_title_via_aux(user_text: str, assistant_text: str, agent=None, *, use_agent_model: bool = False) -> tuple[Optional[str], str, str]:
    return _generate_llm_session_title_via_aux_impl(
        user_text,
        assistant_text,
        agent=agent,
        use_agent_model=use_agent_model,
    )


def _put_title_status(put_event, session_id: str, status: str, reason: str = '', title: str = '', raw_preview: str = '') -> None:
    payload = {'session_id': session_id, 'status': status}
    if reason:
        payload['reason'] = reason
    if title:
        payload['title'] = title
    if raw_preview:
        payload['raw_preview'] = raw_preview
    put_event('title_status', payload)
    logger.info(
        "title_status session=%s status=%s reason=%s title=%r raw_preview=%r",
        session_id,
        status,
        reason or '-',
        title or '',
        (raw_preview or '')[:120],
    )


def _run_background_title_update(session_id: str, user_text: str, assistant_text: str, placeholder_title: str, put_event, agent=None):
    """Generate and publish a better title after `done`, then end the stream."""
    try:
        try:
            s = get_session(session_id)
        except KeyError:
            _put_title_status(put_event, session_id, 'skipped', 'missing_session')
            return
        # Allow self-heal when a previously generated title leaked thinking text.
        _invalid_existing = _looks_invalid_generated_title(s.title)
        if getattr(s, 'llm_title_generated', False) and not _invalid_existing:
            _put_title_status(put_event, session_id, 'skipped', 'already_generated', str(s.title or ''))
            return
        current = str(s.title or '').strip()
        still_auto = (
            current == placeholder_title
            or current in ('Untitled', 'New Chat', '')
            or _is_provisional_title(current, s.messages)
            or _invalid_existing
        )
        if not still_auto:
            _put_title_status(put_event, session_id, 'skipped', 'manual_title', current)
            return
        from api import profiles as profiles_api

        with profiles_api.profile_env_for_background_worker(s, "background title", logger_override=logger):
            aux_title_configured = _aux_title_configured()
            if agent and not aux_title_configured:
                next_title, llm_status, raw_preview = _generate_llm_session_title_for_agent(agent, user_text, assistant_text)
                if not next_title and llm_status in ('llm_error', 'llm_invalid'):
                    next_title, llm_status, raw_preview = _generate_llm_session_title_via_aux(user_text, assistant_text, agent=agent, use_agent_model=True)
            else:
                next_title, llm_status, raw_preview = _generate_llm_session_title_via_aux(user_text, assistant_text)
                if not next_title and agent and llm_status in ('llm_error_aux', 'llm_invalid_aux'):
                    next_title, llm_status, raw_preview = _generate_llm_session_title_for_agent(agent, user_text, assistant_text)
            source = llm_status
            if not next_title:
                fallback_title = _fallback_title_from_exchange(user_text, assistant_text)
                if fallback_title and not _is_generic_fallback_title(fallback_title):
                    logger.debug("Using local fallback for session title generation")
                    next_title = fallback_title
                    source = 'fallback'
                elif fallback_title:
                    logger.debug("Skipping generic local fallback for session title generation: %r", fallback_title)
        fallback_reason = (
            f'local_summary:{llm_status}'
            if source == 'fallback' and llm_status
            else 'local_summary'
        )
        wrote_title = False
        effective_title = current
        if next_title:
            with _get_session_agent_lock(session_id):
                with LOCK:
                    s = SESSIONS.get(session_id, s)
                    effective_title = str(s.title or '').strip()
                    invalid_existing_now = _looks_invalid_generated_title(s.title)
                    still_auto = (
                        effective_title == placeholder_title
                        or effective_title in ('Untitled', 'New Chat', '')
                        or _is_provisional_title(effective_title, s.messages)
                        or invalid_existing_now
                    )
                if not still_auto:
                    _put_title_status(put_event, session_id, 'skipped', 'manual_title', effective_title)
                    return
                if next_title != effective_title:
                    s.title = next_title
                    s.llm_title_generated = True
                    # Keep chronological ordering stable in the sidebar.
                    s.save(touch_updated_at=False)
                    effective_title = s.title
                    wrote_title = True

        if wrote_title:
            if source == 'fallback':
                _put_title_status(put_event, session_id, source, fallback_reason, effective_title, raw_preview)
            else:
                _put_title_status(put_event, session_id, source, llm_status, effective_title, raw_preview)
            put_event('title', {'session_id': session_id, 'title': effective_title})
        else:
            _put_title_status(put_event, session_id, 'skipped', source or 'unchanged', effective_title, raw_preview)
    finally:
        put_event('stream_end', {'session_id': session_id})


def _run_background_title_refresh(session_id: str, user_text: str, assistant_text: str, current_title: str, put_event, agent=None):
    """Refresh an existing LLM-generated title using the latest exchange text.

    Unlike _run_background_title_update, this does NOT guard on
    llm_title_generated — it assumes the title was already LLM-generated
    and the session has progressed enough to warrant a refresh.
    It does NOT emit stream_end (the caller already did).
    """
    try:
        try:
            s = get_session(session_id)
        except KeyError:
            return
        # Safety: skip if user manually renamed since the check
        effective = str(s.title or '').strip()
        if effective != current_title:
            _put_title_status(put_event, session_id, 'skipped', 'manual_title', effective)
            return
        if not effective or effective in ('Untitled', 'New Chat'):
            return
        from api import profiles as profiles_api

        with profiles_api.profile_env_for_background_worker(s, "background title", logger_override=logger):
            aux_title_configured = _aux_title_configured()
            if agent and not aux_title_configured:
                next_title, llm_status, raw_preview = _generate_llm_session_title_for_agent(agent, user_text, assistant_text)
                if not next_title and llm_status in ('llm_error', 'llm_invalid'):
                    next_title, llm_status, raw_preview = _generate_llm_session_title_via_aux(user_text, assistant_text, agent=agent, use_agent_model=True)
            else:
                next_title, llm_status, raw_preview = _generate_llm_session_title_via_aux(user_text, assistant_text)
                if not next_title and agent and llm_status in ('llm_error_aux', 'llm_invalid_aux'):
                    next_title, llm_status, raw_preview = _generate_llm_session_title_for_agent(agent, user_text, assistant_text)
        if not next_title:
            _put_title_status(put_event, session_id, 'refresh_skipped', llm_status or 'empty', effective, raw_preview)
            return
        # Skip if the new title is essentially the same (after normalization)
        normalized_current = re.sub(r'\s+', ' ', effective).strip().lower()
        normalized_new = re.sub(r'\s+', ' ', next_title).strip().lower()
        if normalized_current == normalized_new:
            _put_title_status(put_event, session_id, 'refresh_skipped', 'same_title', effective, raw_preview)
            return
        with _get_session_agent_lock(session_id):
            with LOCK:
                s = SESSIONS.get(session_id, s)
                # Re-check: user may have renamed while we were generating
                if str(s.title or '').strip() != current_title:
                    _put_title_status(put_event, session_id, 'skipped', 'manual_title', str(s.title or '').strip())
                    return
                s.title = next_title
                s.llm_title_generated = True
                effective_title = s.title
            # Session.save() calls _write_session_index(), which acquires LOCK.
            # Keep the per-session agent lock for mutation serialization, but
            # release the global session LOCK before persisting to avoid a
            # self-deadlock in the background title-refresh thread.
            s.save(touch_updated_at=False)
        _put_title_status(put_event, session_id, 'refreshed', llm_status, effective_title, raw_preview)
        put_event('title', {'session_id': session_id, 'title': effective_title})
        logger.info("Adaptive title refresh: session=%s new_title=%r", session_id, effective_title)
    except Exception:
        logger.debug("Background title refresh failed for session %s", session_id, exc_info=True)


def _preserve_pre_compression_snapshot(s, old_sid: str) -> None:
    """Persist old_sid as a read-only pre-compression snapshot.

    Context compression rotates the active WebUI session id from old_sid to the
    agent's new continuation id. The old JSON must remain on disk for lineage
    traversal, but it should not continue to appear as an active sidebar row.
    """
    old_path = SESSION_DIR / f'{old_sid}.json'
    if not old_path.exists():
        return
    try:
        existing_text = old_path.read_text(encoding='utf-8')
        try:
            existing = json.loads(existing_text)
            existing_msgs = len(existing.get('messages') or [])
            existing_snapshot = bool(existing.get('pre_compression_snapshot'))
        except (json.JSONDecodeError, ValueError):
            # Treat corrupt/malformed old JSON as missing history and rewrite it
            # from the in-memory pre-compression messages below. That is safer
            # than leaving an unreadable recovery snapshot behind.
            existing_msgs = -1
            existing_snapshot = False
        if len(s.messages) > existing_msgs:
            # In-memory messages are newer than the file; save the full old
            # snapshot from the current session object while preserving its
            # pre-existing parent_session_id lineage.
            saved_sid = s.session_id
            saved_snapshot = bool(getattr(s, 'pre_compression_snapshot', False))
            s.session_id = old_sid
            s.pre_compression_snapshot = True
            # Stage-359 / PR #2295: clear runtime stream-state fields on the
            # archived snapshot so the sidebar does not reopen the parent as
            # a permanently-running session while the child already holds the
            # completed answer. The continuation session's live state is
            # restored from saved_* locals in the finally block.
            saved_active_stream_id = getattr(s, 'active_stream_id', None)
            saved_pending_user_message = getattr(s, 'pending_user_message', None)
            saved_pending_attachments = list(getattr(s, 'pending_attachments', []) or [])
            saved_pending_started_at = getattr(s, 'pending_started_at', None)
            s.active_stream_id = None
            s.pending_user_message = None
            s.pending_attachments = []
            s.pending_started_at = None
            try:
                # skip_index=False so the snapshot appears in _index.json with
                # the pre_compression_snapshot marker. The sidebar projection
                # (#2285) reads that marker to hide the snapshot from active
                # rows while keeping the JSON discoverable for lineage traversal.
                s.save(touch_updated_at=False, skip_index=False)
                logger.info(
                    "Preserved pre-compression session %s (%d messages) to disk",
                    old_sid, len(s.messages),
                )
            finally:
                s.session_id = saved_sid
                s.pre_compression_snapshot = saved_snapshot
                s.active_stream_id = saved_active_stream_id
                s.pending_user_message = saved_pending_user_message
                s.pending_attachments = saved_pending_attachments
                s.pending_started_at = saved_pending_started_at
            return
        # Existing file is already at least as complete as memory; stamp only
        # the snapshot marker so index/sidebar projection can hide it without
        # rewriting a shorter messages array over a fuller transcript.
        from api.models import Session
        snapshot = Session.load(old_sid)
        if snapshot:
            snapshot.pre_compression_snapshot = True
            # Stage-359 Opus SHOULD-FIX: clear runtime fields on the loaded
            # snapshot too. If the disk snapshot was last persisted while the
            # parent was live, it could carry a stale active_stream_id /
            # pending_* over to disk. The sidebar projection filters snapshot
            # rows so this is latent today, but the contract should match the
            # primary branch above so future readers can trust snapshot files
            # to never contain live runtime state.
            snapshot.active_stream_id = None
            snapshot.pending_user_message = None
            snapshot.pending_attachments = []
            snapshot.pending_started_at = None
            snapshot.save(touch_updated_at=False, skip_index=False)
            logger.info(
                "Marked pre-compression session %s as sidebar-hidden snapshot",
                old_sid,
            )
    except OSError:
        logger.debug("Could not read old session file before preservation")
    except Exception:
        logger.debug("Failed to preserve pre-compression session file", exc_info=True)


def _maybe_schedule_title_refresh(session, put_event, agent):
    """Check if the session is due for an adaptive title refresh and schedule it."""
    refresh_interval = _get_title_refresh_interval()
    if refresh_interval <= 0:
        return
    current_title = str(session.title or '').strip()
    if not current_title or current_title in ('Untitled', 'New Chat'):
        return
    if not getattr(session, 'llm_title_generated', False):
        return
    exchange_count = _count_exchanges(session.messages)
    if exchange_count <= 0 or exchange_count % refresh_interval != 0:
        return
    last_u, last_a = _latest_exchange_snippets(session.messages)
    if not last_u and not last_a:
        return
    threading.Thread(
        target=_run_background_title_refresh,
        args=(session.session_id, last_u, last_a, current_title, put_event, agent),
        daemon=True,
    ).start()


def _strip_native_image_parts_from_content(content):
    return _strip_native_image_parts_from_content_impl(content)


def _sanitize_messages_for_api(messages, *, cfg: dict = None):
    return _sanitize_messages_for_api_impl(messages, cfg=cfg)


def _api_safe_message_positions(messages):
    return _api_safe_message_positions_impl(messages)


def _restore_reasoning_metadata(previous_messages, updated_messages):
    return _restore_reasoning_metadata_impl(previous_messages, updated_messages)


def _session_context_messages(session):
    return _session_context_messages_impl(session)


def _message_identity(msg):
    return _message_identity_impl(msg)


def _messages_have_prefix(messages, prefix):
    return _messages_have_prefix_impl(messages, prefix)


def _is_context_compression_marker(msg):
    return _is_context_compression_marker_impl(msg)


def _compact_summary_text(raw_text: str | None, limit: int = 320) -> str | None:
    return _compact_summary_text_impl(raw_text, limit)


def _compression_anchor_message_key(message):
    return _compression_anchor_message_key_impl(message)


def _compression_summary_from_messages(messages):
    return _compression_summary_from_messages_impl(messages)


def _find_current_user_turn(messages, msg_text):
    return _find_current_user_turn_impl(messages, msg_text)


def _drop_checkpointed_current_user_from_context(messages, msg_text):
    return _drop_checkpointed_current_user_from_context_impl(messages, msg_text)


def _normalize_fresh_chat_text(text):
    return _normalize_fresh_chat_text_impl(text)


def _is_casual_fresh_chat_message(msg_text):
    return _is_casual_fresh_chat_message_impl(msg_text)


def _has_task_resume_compaction_marker(messages):
    return _has_task_resume_compaction_marker_impl(messages)


def _context_messages_for_new_turn(session, msg_text):
    return _context_messages_for_new_turn_impl(session, msg_text)


def _stream_writeback_is_current(session, stream_id):
    """Return True only while a worker still owns the session writeback.

    cancel_stream() intentionally clears ``active_stream_id`` early so the UI can
    accept a follow-up turn while the old worker is unwinding. That old worker
    must not later persist its stale result over the newer transcript.
    """
    return bool(stream_id) and getattr(session, 'active_stream_id', None) == stream_id


def _merge_display_messages_after_agent_result(previous_display, previous_context, result_messages, msg_text):
    return _merge_display_messages_after_agent_result_impl(
        previous_display,
        previous_context,
        result_messages,
        msg_text,
    )


def _assistant_reply_added_after_current_turn(result_messages, previous_context, msg_text) -> bool:
    return _assistant_reply_added_after_current_turn_impl(
        result_messages,
        previous_context,
        msg_text,
    )


def _sse(handler, event, data):
    """Write one SSE event to the response stream."""
    payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    handler.wfile.write(payload.encode('utf-8'))
    handler.wfile.flush()


def _materialize_pending_user_turn_before_error(session) -> bool:
    return _materialize_pending_user_turn_before_error_impl(session)


def _last_resort_sync_from_core(session, stream_id, agent_lock):
    from api.models import _get_profile_home, _apply_core_sync_or_error_marker
    return _last_resort_sync_from_core_impl(
        session,
        stream_id,
        agent_lock,
        cancel_flags=CANCEL_FLAGS,
        get_profile_home=_get_profile_home,
        apply_core_sync_or_error_marker=_apply_core_sync_or_error_marker,
        logger=logger,
    )


def _attempt_credential_self_heal(
    provider_id, session_id, _agent_lock_ref,
):
    return _attempt_credential_self_heal_impl(
        provider_id,
        session_id,
        _agent_lock_ref,
        logger=logger,
    )


def _run_agent_streaming(
    session_id,
    msg_text,
    model,
    workspace,
    stream_id,
    attachments=None,
    *,
    ephemeral=False,
    model_provider=None,
    goal_related=False,
    product_context=None,
):
    """Run agent in background thread, writing SSE events to STREAMS[stream_id].

    When ephemeral=True, session mutations are skipped — used by /btw to get
    a streaming answer without persisting to the parent session.
    """
    q = STREAMS.get(stream_id)
    if q is None:
        return
    register_active_run(
        stream_id,
        session_id=session_id,
        started_at=time.time(),
        phase="starting",
        workspace=str(workspace),
        model=model,
        provider=model_provider,
        ephemeral=bool(ephemeral),
    )
    _product_turn_finalizer = _ProductTurnFinalizer(product_context, logger=logger)

    def _finalize_product_turn(
        *,
        failed: bool = False,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        _product_turn_finalizer.finalize(
            failed=failed,
            error_type=error_type,
            error_message=error_message,
        )

    def _put_cancel(message: str = "Cancelled by user") -> None:
        _finalize_product_turn(failed=True)
        put('cancel', {'message': message})

    try:
        run_journal = RunJournalWriter(session_id, stream_id)
    except Exception:
        run_journal = None
        logger.debug("Failed to initialize run journal for stream %s", stream_id, exc_info=True)
    if not ephemeral:
        try:
            append_turn_journal_event_for_stream(
                session_id,
                stream_id,
                {"event": "worker_started", "created_at": time.time()},
            )
        except Exception:
            logger.debug("Failed to append worker_started turn journal event", exc_info=True)
    s = None
    _rt = {}
    old_cwd = None
    old_exec_ask = None
    old_session_key = None
    old_session_id = None
    old_session_platform = None
    old_hermes_home = None
    old_profile_env = {}

    # MCP discovery moved to AFTER the per-profile HERMES_HOME mutation below
    # (was here at v0.51.30) — the previous placement always read the default
    # profile's mcp_servers because os.environ['HERMES_HOME'] hadn't been
    # rewritten yet.  See https://github.com/nesquena/hermes-webui/issues/1968.

    # Sprint 10: create a cancel event for this stream
    cancel_event = threading.Event()
    with STREAMS_LOCK:
        CANCEL_FLAGS[stream_id] = cancel_event
        STREAM_PARTIAL_TEXT[stream_id] = ''  # start accumulating partial text (#893)
        STREAM_REASONING_TEXT[stream_id] = ''  # start accumulating reasoning trace (#1361 §A)
        STREAM_LIVE_TOOL_CALLS[stream_id] = []  # start accumulating tool calls (#1361 §B)

    agent = None
    _live_usage_tracker = _LiveUsageTracker(
        get_session=lambda: get_session(session_id),
        get_agent=lambda: agent,
    )
    _live_prompt_estimate_seen_ids = _live_usage_tracker.seen_tool_call_ids

    def _bump_live_prompt_estimate(messages) -> int:
        return _live_usage_tracker.bump_prompt_estimate(messages)

    def _live_usage_snapshot():
        return _live_usage_tracker.snapshot()

    _event_sink = _StreamingEventSink(
        stream_id=stream_id,
        queue=q,
        cancel_event=cancel_event,
        run_journal=run_journal,
        last_event_ids=STREAM_LAST_EVENT_ID,
        logger=logger,
    )

    def put(event, data):
        _event_sink.put(event, data)

    _metering_ticker = _StreamingMeteringTicker(
        stream_id=stream_id,
        session_id=session_id,
        usage_snapshot=_live_usage_snapshot,
        put=put,
    ).start()

    _agent_status_callback = _make_agent_status_callback(session_id=session_id, put=put)

    # Initialised here (before any code that may raise) so the outer `finally`
    # block can safely check `if _checkpoint_stop is not None` even when an
    # exception fires before the checkpoint thread is created (Issue #765).
    _checkpoint_stop = None
    _ckpt_thread = None
    _agent_lock = None
    try:
        s = get_session(session_id)
        update_active_run(stream_id, phase="running", session_id=session_id)
        s.workspace = str(Path(workspace).expanduser().resolve())
        s.model = model
        provider_context = (
            str(model_provider).strip().lower()
            if model_provider is not None
            else getattr(s, "model_provider", None)
        )
        s.model_provider = provider_context or None

        _agent_lock = _get_session_agent_lock(session_id)
        # TD1: set thread-local env context so concurrent sessions don't clobber globals
        # Check for pre-flight cancel (user cancelled before agent even started)
        if cancel_event.is_set():
            with _agent_lock:
                _finalize_cancelled_turn(s, ephemeral=ephemeral, message='Task cancelled before start.')
            _put_cancel('Cancelled before start')
            return

        # Resolve profile home for this agent run — use the session's own profile
        # (stamped at new_session() time from the client's S.activeProfile) so that
        # two concurrent tabs on different profiles don't clobber each other via the
        # process-level active-profile global.  Falls back gracefully.
        try:
            from api.profiles import (
                patch_skill_home_modules,
                get_hermes_home_for_profile,
                get_profile_runtime_env,
            )
            _profile_home_path = get_hermes_home_for_profile(getattr(s, 'profile', None))
            _profile_home = str(_profile_home_path)
            _profile_runtime_env = get_profile_runtime_env(_profile_home_path)
        except ImportError:
            _profile_home = os.environ.get('HERMES_HOME', '')
            _profile_runtime_env = {}
            patch_skill_home_modules = None
        
        # Capture the resolved profile name now, while profile context is
        # reliable. Used in the compression migration block to stamp s.profile
        # on the continuation session. We resolve it here rather than calling
        # get_active_profile_name() at compression time because that function
        # reads thread-local storage (_tls.profile) set by set_request_profile()
        # on the HTTP handler thread. The streaming thread is a separate
        # threading.Thread and does not inherit TLS. At compression time,
        # get_active_profile_name() would fall back to the process-global
        # _active_profile, which may belong to a different concurrent tab.
        _resolved_profile_name = getattr(s, 'profile', None)
        if not _resolved_profile_name:
            try:
                from api.profiles import get_active_profile_name
                _resolved_profile_name = get_active_profile_name()
            except Exception:
                _resolved_profile_name = None
        
        _thread_env = _build_agent_thread_env(
            _profile_runtime_env,
            str(s.workspace),
            session_id,
            _profile_home,
        )
        _set_thread_env(**_thread_env)
        # Prewarm skill-tool imports *before* acquiring the lock so that
        # first-time module initialisation (which can be slow) does not
        # block other concurrent sessions waiting on _ENV_LOCK (#2024).
        _prewarm_skill_tool_modules()
        # Still set process-level env as fallback for tools that bypass thread-local
        # Acquire lock only for the env mutation, then release before the agent runs.
        # The finally block re-acquires to restore — keeping critical sections short
        # and preventing a deadlock where the restore would re-enter the same lock.
        with _ENV_LOCK:
            old_profile_env = {key: os.environ.get(key) for key in _profile_runtime_env}
            old_cwd = os.environ.get('TERMINAL_CWD')
            old_exec_ask = os.environ.get('HERMES_EXEC_ASK')
            old_session_key = os.environ.get('HERMES_SESSION_KEY')
            old_session_id = os.environ.get('HERMES_SESSION_ID')
            old_session_platform = os.environ.get('HERMES_SESSION_PLATFORM')
            old_hermes_home = os.environ.get('HERMES_HOME')
            os.environ.update(_profile_runtime_env)
            os.environ['TERMINAL_CWD'] = str(s.workspace)
            os.environ['HERMES_EXEC_ASK'] = '1'
            os.environ['HERMES_SESSION_KEY'] = session_id
            os.environ['HERMES_SESSION_ID'] = session_id
            os.environ['HERMES_SESSION_PLATFORM'] = 'webui'
            if _profile_home:
                os.environ['HERMES_HOME'] = _profile_home
                # Patch module-level caches to match the active profile.
                # _set_hermes_home() does this for process-wide switches
                # but per-request switches skip it (#1700).
                # Modules were prewarmed by _prewarm_skill_tool_modules()
                # above, so we only do lightweight sys.modules lookups and
                # attribute assignments here — no first-time import under
                # the lock (#2024).
                if patch_skill_home_modules is not None:
                    patch_skill_home_modules(Path(_profile_home))
        # Lock released — agent runs without holding it
        # ── MCP Server Discovery (lazy import, idempotent) ──
        # MUST run AFTER the HERMES_HOME mutation above — `discover_mcp_tools()`
        # reads `~/.hermes/config.yaml` via `get_hermes_home()`, which uses
        # `os.environ['HERMES_HOME']`.  Calling it before the mutation always
        # loaded the default profile's `mcp_servers`, even when the session
        # was stamped with a non-default profile.  See issue #1968.
        #
        # NOTE: `_servers` in `tools/mcp_tool.py` is a process-global registry
        # keyed by server name.  This means once profile A registers a server
        # named e.g. `postgres`, profile B's discovery sees it as already
        # connected and skips it — even if B's config points at a different
        # binary.  Fully fixing multi-profile concurrent use requires keying
        # `_servers` by `(profile_home, name)` upstream in hermes-agent; that
        # lives outside this WebUI repo.  This change fixes the headline bug
        # for users who run a single non-default profile per WebUI process.
        try:
            from tools.mcp_tool import discover_mcp_tools
            discover_mcp_tools()
        except Exception:
            pass  # MCP not available or not configured — non-fatal

        # Register a gateway-style notify callback so the approval system can
        # push the `approval` SSE event the moment a dangerous command is
        # detected, without waiting for the next on_tool() poll cycle.
        # Without this, the agent thread blocks inside the terminal tool
        # waiting for approval that the UI never knew to ask for, leaving
        # the chat stuck in "Thinking…" forever.
        _approval_registered = False
        _unreg_notify = None
        try:
            from tools.approval import (
                register_gateway_notify as _reg_notify,
                unregister_gateway_notify as _unreg_notify,
            )
            def _approval_notify_cb(approval_data):
                put('approval', approval_data)
            _reg_notify(session_id, _approval_notify_cb)
            _approval_registered = True
        except ImportError:
            logger.debug("Approval module not available, falling back to polling")

        _clarify_registered = False
        _unreg_clarify_notify = None
        try:
            from api.clarify import (
                register_gateway_notify as _reg_clarify_notify,
                unregister_gateway_notify as _unreg_clarify_notify,
            )

            def _clarify_notify_cb(clarify_data):
                put('clarify', clarify_data)

            _reg_clarify_notify(session_id, _clarify_notify_cb)
            _clarify_registered = True
        except ImportError:
            logger.debug("Clarify module not available, falling back to polling")

        try:
            _token_sent = False  # tracks whether any streamed tokens were sent
            _self_healed = False  # (#1401) prevents infinite self-heal retries
            _reasoning_text = ''  # accumulates reasoning/thinking trace for persistence
            _live_tool_calls = []  # tool progress fallback when final messages omit tool IDs

            _output_bridge = _StreamingOutputBridge(
                stream_id=stream_id,
                session_id=session_id,
                partial_texts=STREAM_PARTIAL_TEXT,
                reasoning_texts=STREAM_REASONING_TEXT,
                usage_snapshot=_live_usage_snapshot,
                put=put,
            )

            def _emit_metering():
                _output_bridge.emit_metering()

            def on_token(text):
                nonlocal _token_sent
                if _output_bridge.on_token(text):
                    _token_sent = True

            def on_reasoning(text):
                nonlocal _reasoning_text
                emitted = _output_bridge.on_reasoning(text)
                if emitted:
                    _reasoning_text += emitted

            def on_interim_assistant(text, **cb_kwargs):
                _output_bridge.on_interim_assistant(text, **cb_kwargs)

            # Pre-initialise the activity counter here so on_tool (which
            # closes over it) never captures an unbound name even if this
            # block is reordered later (Issue #765).
            _checkpoint_activity = [0]

            def _emit_tool_reasoning(reason_text):
                nonlocal _reasoning_text
                emitted = _output_bridge.on_reasoning(reason_text)
                if emitted:
                    _reasoning_text += emitted

            def _emit_tool_metering_snapshot():
                _tool_stats = meter().get_stats()
                _tool_stats['session_id'] = session_id
                _tool_stats['usage'] = _live_usage_snapshot()
                put('metering', _tool_stats)

            _tool_bridge = _StreamingToolEventBridge(
                stream_id=stream_id,
                session_id=session_id,
                live_tool_calls=_live_tool_calls,
                shared_live_tool_calls=STREAM_LIVE_TOOL_CALLS,
                checkpoint_activity=_checkpoint_activity,
                seen_tool_call_ids=_live_prompt_estimate_seen_ids,
                put=put,
                emit_reasoning=_emit_tool_reasoning,
                emit_metering_snapshot=_emit_tool_metering_snapshot,
                bump_live_prompt_estimate=_bump_live_prompt_estimate,
                tool_result_snippet=_tool_result_snippet,
            )

            def on_tool(*cb_args, **cb_kwargs):
                _tool_bridge.on_tool(*cb_args, **cb_kwargs)

            def on_tool_start(tool_call_id, name, args):
                try:
                    _tool_bridge.on_tool_start(tool_call_id, name, args)
                except Exception:
                    logger.debug('Failed to update live prompt estimate on tool start', exc_info=True)

            def on_tool_complete(tool_call_id, name, args, function_result):
                try:
                    _tool_bridge.on_tool_complete(tool_call_id, name, args, function_result)
                except Exception:
                    logger.debug('Failed to update live prompt estimate on tool completion', exc_info=True)

            _AIAgent = _get_ai_agent()
            if _AIAgent is None:
                raise ImportError(_aiagent_import_error_detail())

            # Initialize SessionDB so session_search works in WebUI sessions
            _session_db = None
            try:
                from hermes_state import SessionDB
                _session_db = SessionDB()
            except Exception as _db_err:
                print(f"[webui] WARNING: SessionDB init failed — session_search will be unavailable: {_db_err}", flush=True)
            resolved_model, resolved_provider, resolved_base_url = resolve_model_provider(
                model_with_provider_context(model, provider_context)
            )

            # Resolve API key via Hermes runtime provider (matches gateway behaviour).
            # Pass the resolved provider so non-default providers get their own credentials.
            resolved_api_key = None
            try:
                from api.oauth import resolve_runtime_provider_with_anthropic_env_lock
                from hermes_cli.runtime_provider import resolve_runtime_provider
                _rt = resolve_runtime_provider_with_anthropic_env_lock(
                    resolve_runtime_provider,
                    requested=resolved_provider,
                )
                resolved_api_key = _rt.get("api_key")
                if not resolved_provider:
                    resolved_provider = _rt.get("provider")
                if not resolved_base_url:
                    resolved_base_url = _rt.get("base_url")
            except Exception as _e:
                print(f"[webui] WARNING: resolve_runtime_provider failed: {_e}", flush=True)

            # Named custom providers (custom:slug) may not be resolvable by
            # hermes_cli.runtime_provider directly. Fall back to config.yaml
            # custom_providers[] so WebUI can pass explicit creds/base_url.
            if isinstance(resolved_provider, str) and resolved_provider.startswith("custom:"):
                _cp_key, _cp_base = resolve_custom_provider_connection(resolved_provider)
                if not resolved_api_key and _cp_key:
                    resolved_api_key = _cp_key
                if not resolved_base_url and _cp_base:
                    resolved_base_url = _cp_base

            # Read per-profile config at call time (not module-level snapshot)
            from api.config import get_config as _get_config
            _cfg = _get_config()

            # Per-profile toolsets — use _resolve_cli_toolsets() so MCP
            # server toolsets are included, matching native CLI behaviour.
            from api.config import _resolve_cli_toolsets
            _toolsets = _resolve_cli_toolsets(_cfg)

            # Per-session toolset override (#493): if the session has
            # enabled_toolsets set, use that instead of the global config.
            try:
                from api.models import Session, SESSION_DIR
                _session_path = SESSION_DIR / f"{session_id}.json"
                if _session_path.exists():
                    _session_meta = Session.load_metadata_only(session_id)
                    # load_metadata_only returns a Session INSTANCE, not a dict.
                    # The previous .get('enabled_toolsets') raised AttributeError
                    # which was swallowed by the bare except below — the entire
                    # per-session toolset override silently no-op'd. Use
                    # getattr() to read the attribute correctly.
                    # (Opus pre-release advisor finding for v0.50.257.)
                    _override = getattr(_session_meta, 'enabled_toolsets', None) if _session_meta else None
                    if _override:
                        _toolsets = _override
            except Exception as _ts_err:
                print(f"[webui] WARNING: failed to read per-session toolsets for {session_id}: {_ts_err}", flush=True)

            _fallback_resolved = _resolve_fallback_config_impl(_cfg)

            # Build kwargs defensively — guard newer params so the WebUI
            # degrades gracefully when run against an older hermes-agent build.
            # (fixes: TypeError: AIAgent.__init__() got an unexpected keyword
            # argument 'credential_pool' — issue #772)
            import inspect as _inspect
            _agent_params = set(_inspect.signature(_AIAgent.__init__).parameters)

            _max_iterations_cfg = _resolve_max_iterations_config_impl(_cfg)
            _max_tokens_cfg = _resolve_max_tokens_config_impl(_cfg)
            try:
                from api.config import parse_reasoning_effort as _parse_reff
                _reasoning_config = _resolve_reasoning_config_impl(_cfg, _parse_reff)
            except Exception:
                _reasoning_config = None

            _agent_kwargs = dict(
                model=resolved_model,
                provider=resolved_provider,
                base_url=resolved_base_url,
                api_key=resolved_api_key,
                # Identify browser-originated sessions as WebUI so Hermes Agent
                # does not inject CLI-specific terminal/output guidance.
                platform='webui',
                quiet_mode=True,
                enabled_toolsets=_toolsets,
                fallback_model=_fallback_resolved,
                session_id=session_id,
                session_db=_session_db,
                stream_delta_callback=on_token,
                reasoning_callback=on_reasoning,
                tool_progress_callback=on_tool,
                clarify_callback=(
                    lambda question, choices: _webui_clarify_callback_impl(
                        question,
                        choices,
                        session_id,
                        cancel_event,
                        _clarify_timeout_seconds,
                    )
                ),
            )
            # reasoning_config has been an AIAgent param for several releases,
            # but guard defensively to avoid TypeError on an older agent build.
            if 'reasoning_config' in _agent_params and _reasoning_config is not None:
                _agent_kwargs['reasoning_config'] = _reasoning_config
            if 'interim_assistant_callback' in _agent_params:
                _agent_kwargs['interim_assistant_callback'] = on_interim_assistant
            if 'tool_start_callback' in _agent_params:
                _agent_kwargs['tool_start_callback'] = on_tool_start
            if 'tool_complete_callback' in _agent_params:
                _agent_kwargs['tool_complete_callback'] = on_tool_complete
            if 'status_callback' in _agent_params:
                _agent_kwargs['status_callback'] = _agent_status_callback
            if 'max_iterations' in _agent_params and _max_iterations_cfg is not None:
                _agent_kwargs['max_iterations'] = _max_iterations_cfg
            if 'max_tokens' in _agent_params and _max_tokens_cfg is not None:
                _agent_kwargs['max_tokens'] = _max_tokens_cfg
            # Params added in newer hermes-agent — skip if not supported
            if 'api_mode' in _agent_params:
                _agent_kwargs['api_mode'] = _rt.get('api_mode')
            if 'acp_command' in _agent_params:
                _agent_kwargs['acp_command'] = _rt.get('command')
            if 'acp_args' in _agent_params:
                _agent_kwargs['acp_args'] = _rt.get('args')
            if 'credential_pool' in _agent_params:
                _agent_kwargs['credential_pool'] = _rt.get('credential_pool')
            # Pin Honcho memory sessions to the stable WebUI session ID.
            # Without this, 'per-session' Honcho strategy creates a new Honcho
            # session on every streaming request because HonchoSessionManager is
            # re-instantiated fresh each turn (#855).
            if 'gateway_session_key' in _agent_params:
                _agent_kwargs['gateway_session_key'] = session_id

            # ── Agent cache: reuse across messages in the same session ──
            # Mirrors gateway _agent_cache.  Keeps _user_turn_count alive so
            # injectionFrequency: "first-turn" actually suppresses after turn 1.
            if ephemeral:
                agent = _AIAgent(**_agent_kwargs)
                logger.debug('[webui] Created ephemeral agent for session %s', session_id)
            else:
                import hashlib as _hashlib
                import json as _json
                from api.config import SESSION_AGENT_CACHE, SESSION_AGENT_CACHE_LOCK
                _credential_pool = _rt.get('credential_pool')
                _sig_blob = _json.dumps([
                    resolved_model or '',
                    _agent_cache_api_key_sig(resolved_api_key, _credential_pool),
                    resolved_base_url or '',
                    resolved_provider or '',
                    _rt.get('api_mode') or '',
                    _rt.get('command') or '',
                    _rt.get('args') or [],
                    bool(_credential_pool),
                    _max_iterations_cfg or '',
                    _max_tokens_cfg or '',
                    _fallback_resolved or {},
                    sorted(_toolsets) if _toolsets else [],
                    _reasoning_config or {},
                    # #1897: profile_home is part of the agent's identity because
                    # AIAgent caches `_cached_system_prompt` from `load_soul_md()`
                    # at construction time, sourced from HERMES_HOME. Same-session
                    # profile switches keep `session_id` stable, so without this
                    # field the cached agent silently retains the previous
                    # profile's SOUL.md (and any other profile-scoped context).
                    _profile_home or '',
                ], sort_keys=True)
                _agent_sig = _hashlib.sha256(_sig_blob.encode()).hexdigest()[:16]

                agent = None
                with SESSION_AGENT_CACHE_LOCK:
                    _cached = SESSION_AGENT_CACHE.get(session_id)
                    if _cached and _cached[1] == _agent_sig:
                        agent = _cached[0]
                        SESSION_AGENT_CACHE.move_to_end(session_id)  # LRU: mark as recently used
                        logger.debug('[webui] Reusing cached agent for session %s', session_id)
                        # Reopened/cache-hit sessions must register the agent
                        # so later lifecycle commits can find it.
                        try:
                            from api.session_lifecycle import register_agent
                            register_agent(session_id, agent)
                        except Exception:
                            logger.debug("Lifecycle register_agent failed for cached session %s", session_id, exc_info=True)

                if agent is not None:
                    # Refresh volatile runtime credentials selected from provider
                    # pools without discarding cross-turn agent/provider state.
                    if not _refresh_cached_agent_runtime(agent, _agent_kwargs):
                        logger.warning(
                            '[webui] Cached agent runtime could not be safely refreshed; rebuilding agent for session %s',
                            session_id,
                        )
                        try:
                            if getattr(agent, '_session_db', None) is not None:
                                agent._session_db.close()
                        except Exception:
                            pass
                        with SESSION_AGENT_CACHE_LOCK:
                            SESSION_AGENT_CACHE.pop(session_id, None)
                        agent = None

                if agent is not None:
                    # Refresh per-turn callbacks — these close over request-scoped
                    # objects (put queue, cancel_event) that are new each request.
                    agent.stream_delta_callback = _agent_kwargs.get('stream_delta_callback')
                    agent.tool_progress_callback = _agent_kwargs.get('tool_progress_callback')
                    if hasattr(agent, 'tool_start_callback'):
                        agent.tool_start_callback = _agent_kwargs.get('tool_start_callback')
                    if hasattr(agent, 'tool_complete_callback'):
                        agent.tool_complete_callback = _agent_kwargs.get('tool_complete_callback')
                    if hasattr(agent, 'status_callback'):
                        agent.status_callback = _agent_kwargs.get('status_callback')
                    if hasattr(agent, 'interim_assistant_callback'):
                        agent.interim_assistant_callback = _agent_kwargs.get('interim_assistant_callback')
                    if hasattr(agent, 'reasoning_callback'):
                        agent.reasoning_callback = _agent_kwargs.get('reasoning_callback')
                    if hasattr(agent, 'clarify_callback'):
                        agent.clarify_callback = _agent_kwargs.get('clarify_callback')
                    if _session_db is not None:
                        # Close any previously held SessionDB connection before
                        # replacing it. Without this, each streaming request creates
                        # a new SessionDB whose WAL handles leak indefinitely,
                        # eventually causing EMFILE crashes (#streaming FD leak).
                        if hasattr(agent, '_session_db') and agent._session_db is not None:
                            try:
                                agent._session_db.close()
                            except Exception:
                                pass
                        agent._session_db = _session_db
                    if hasattr(agent, '_api_call_count'):
                        agent._api_call_count = 0
                    # Reset interrupt state from a prior cancel so the reused
                    # agent does not think it is still interrupted.
                    if hasattr(agent, '_interrupted'):
                        agent._interrupted = False
                    if hasattr(agent, '_interrupt_message'):
                        agent._interrupt_message = None
                else:
                    agent = _AIAgent(**_agent_kwargs)
                    # Register the new agent with the memory lifecycle so
                    # its commit_memory_session() can be found later.
                    try:
                        from api.session_lifecycle import register_agent
                        register_agent(session_id, agent)
                    except Exception:
                        logger.debug("Lifecycle register_agent failed for new session %s", session_id, exc_info=True)
                    _evicted_items = []
                    with SESSION_AGENT_CACHE_LOCK:
                        SESSION_AGENT_CACHE[session_id] = (agent, _agent_sig)
                        SESSION_AGENT_CACHE.move_to_end(session_id)  # LRU: mark as recently used
                        from api.config import SESSION_AGENT_CACHE_MAX
                        while len(SESSION_AGENT_CACHE) > SESSION_AGENT_CACHE_MAX:
                            evicted_sid, evicted_entry = SESSION_AGENT_CACHE.popitem(last=False)
                            _evicted_items.append((evicted_sid, evicted_entry))
                    # Commit and close evicted agents outside the cache lock so
                    # concurrent cache users are not blocked by provider I/O.
                    for _evicted_sid, _evicted_entry in _evicted_items:
                        try:
                            _evicted_agent = _evicted_entry[0] if isinstance(_evicted_entry, tuple) else None
                            _should_close_evicted_agent = True
                            if _evicted_agent is not None:
                                try:
                                    from api.session_lifecycle import (
                                        commit_session_memory as _lifecycle_commit,
                                        has_uncommitted_work as _lifecycle_has_uncommitted_work,
                                        unregister_agent as _lifecycle_unregister_agent,
                                    )
                                    _lifecycle_commit(_evicted_sid, agent=_evicted_agent, wait=True)
                                    if not _lifecycle_has_uncommitted_work(_evicted_sid):
                                        _lifecycle_unregister_agent(_evicted_sid)
                                    else:
                                        _should_close_evicted_agent = False
                                except Exception:
                                    _should_close_evicted_agent = False
                                    logger.debug("Lifecycle commit on eviction failed for %s", _evicted_sid, exc_info=True)
                            if _should_close_evicted_agent and _evicted_agent is not None and getattr(_evicted_agent, '_session_db', None) is not None:
                                _evicted_agent._session_db.close()
                        except Exception:
                            logger.debug("Failed to close evicted agent for session %s", _evicted_sid, exc_info=True)
                        logger.debug('[webui] Evicted LRU agent from cache: %s', _evicted_sid)
                    logger.debug('[webui] Created new agent for session %s', session_id)

            # Store agent instance for cancel/interrupt propagation
            with STREAMS_LOCK:
                AGENT_INSTANCES[stream_id] = agent
                # Check if cancel was requested during agent initialization
                if stream_id in CANCEL_FLAGS and CANCEL_FLAGS[stream_id].is_set():
                    # Cancel arrived during agent creation - interrupt immediately
                    try:
                        agent.interrupt("Cancelled before start")
                    except Exception:
                        logger.debug("Failed to interrupt agent before start")
                    with _agent_lock:
                        _finalize_cancelled_turn(s, ephemeral=ephemeral, message='Task cancelled before start.')
                    _put_cancel()
                    return

            # Prepend workspace context so the agent always knows which directory
            # to use for file operations, regardless of session age or AGENTS.md defaults.
            workspace_ctx = _workspace_context_prefix(str(s.workspace))
            workspace_system_msg = (
                f"Active workspace at session start: {s.workspace}\n"
                "Every user message is prefixed with [Workspace::v1: /absolute/path] indicating the "
                "workspace the user has selected in the web UI at the time they sent that message. "
                "This tag is the single authoritative source of the active workspace and updates "
                "with every message. It overrides any prior workspace mentioned in this system "
                "prompt, memory, or conversation history. Always use the value from the most recent "
                "[Workspace::v1: ...] tag as your default working directory for ALL file operations: "
                "write_file, read_file, search_files, terminal workdir, and patch. "
                "Never fall back to a hardcoded path when this tag is present."
            )
            # Resolve personality prompt from config.yaml agent.personalities
            # (matches hermes-agent CLI behavior — passes via ephemeral_system_prompt)
            _personality_prompt = None
            _pname = getattr(s, 'personality', None)
            if _pname:
                _agent_cfg = _cfg.get('agent', {})
                _personalities = _agent_cfg.get('personalities', {})
                if isinstance(_personalities, dict) and _pname in _personalities:
                    _pval = _personalities[_pname]
                    if isinstance(_pval, dict):
                        _parts = [_pval.get('system_prompt', '') or _pval.get('prompt', '')]
                        if _pval.get('tone'):
                            _parts.append(f'Tone: {_pval["tone"]}')
                        if _pval.get('style'):
                            _parts.append(f'Style: {_pval["style"]}')
                        _personality_prompt = '\n'.join(p for p in _parts if p)
                    else:
                        _personality_prompt = str(_pval)
            # Pass WebUI-only runtime guidance via ephemeral_system_prompt
            # (agent's own mechanism). This preserves any selected personality
            # while making long tool runs emit real user-visible interim text
            # through interim_assistant_callback instead of frontend guesses.
            _product_prompt = ""
            if product_context:
                try:
                    from api.product_context import product_ephemeral_prompt

                    _product_prompt = product_ephemeral_prompt(product_context)
                except Exception:
                    logger.debug("Failed to build product runtime prompt", exc_info=True)
            agent.ephemeral_system_prompt = _webui_ephemeral_system_prompt(_personality_prompt, _product_prompt)
            _pending_started_at = getattr(s, 'pending_started_at', None)
            # Normal chat-start sets pending_started_at before spawning this thread;
            # fallback to now only for recovered/legacy flows where that marker is absent
            # or has been zeroed out (e.g. via a buggy migration / manual file edit).
            # Truthy-check covers None, missing-attr, and 0 uniformly.
            _turn_started_at = _pending_started_at if _pending_started_at else time.time()
            _previous_messages = list(s.messages or [])
            _previous_context_messages = _context_messages_for_new_turn(s, msg_text)
            _pre_compression_count = getattr(
                getattr(agent, 'context_compressor', None),
                'compression_count', 0,
            )

            # ── Periodic checkpoint during streaming (Issue #765) ──
            # The agent works on an internal copy of s.messages during run_conversation()
            # so we cannot watch s.messages for growth. Instead, on_tool() increments
            # _checkpoint_activity[0] each time a tool call completes — that is the real
            # signal that progress has been made worth persisting.
            #
            # What gets saved on each checkpoint:
            #   - s.pending_user_message (already written before run starts)
            #   - s.pending_started_at / s.active_stream_id (turn bookkeeping)
            # On a server restart the UI will see a session with a pending message and no
            # response — better than a silent loss of the entire conversation turn.
            # The final s.save() at task completion handles the full session update + index.
            # (_checkpoint_stop is pre-initialised at the top of the outer try.)
            # (_checkpoint_activity is already initialised before on_tool().)

            def _periodic_checkpoint():
                last_saved_activity = 0
                while not _checkpoint_stop.wait(15):
                    try:
                        cur = _checkpoint_activity[0]
                        if cur > last_saved_activity:
                            with _agent_lock:
                                s.save(skip_index=True)
                            last_saved_activity = cur
                    except Exception as e:
                        logger.debug("Periodic checkpoint save failed: %s", e)

            _checkpoint_stop = threading.Event()
            # Persist the user message BEFORE streaming starts so it's durable even if
            # the server crashes before the first checkpoint fires (every 15s).
            with _agent_lock:
                s.save(touch_updated_at=True, skip_index=False)

            _ckpt_thread = threading.Thread(
                target=_periodic_checkpoint, daemon=True,
                name=f"ckpt-{session_id[:8]}",
            )
            _ckpt_thread.start()

            _process_notifications = _drain_webui_process_notifications(session_id)
            _agent_msg_text = msg_text
            if _process_notifications:
                _agent_msg_text = "\n\n".join([*_process_notifications, msg_text]).strip()
            user_message = _build_native_multimodal_message(workspace_ctx, _agent_msg_text, attachments, workspace, cfg=_cfg)
            result = agent.run_conversation(
                user_message=user_message,
                system_message=workspace_system_msg,
                conversation_history=_sanitize_messages_for_api(_previous_context_messages, cfg=_cfg),
                task_id=session_id,
                persist_user_message=msg_text,
            )
            if cancel_event.is_set():
                if _checkpoint_stop is not None:
                    _checkpoint_stop.set()
                if _ckpt_thread is not None:
                    _ckpt_thread.join(timeout=15)
                if ephemeral:
                    _cleanup_ephemeral_cancelled_turn(s)
                else:
                    with _agent_lock:
                        _finalize_cancelled_turn(s, ephemeral=False)
                        try:
                            append_turn_journal_event_for_stream(
                                s.session_id,
                                stream_id,
                                {
                                    "event": "interrupted",
                                    "created_at": time.time(),
                                    "reason": "cancelled",
                                },
                            )
                        except Exception:
                            logger.debug("Failed to append cancelled turn journal event", exc_info=True)
                # Emits put('cancel', ...) through _put_cancel() for the
                # source-guarded post-run cancel path.
                _put_cancel()
                return
            # ── Ephemeral mode (/btw): deliver answer, skip persistence, cleanup ──
            if ephemeral:
                _answer = ''
                for _m in reversed(result.get('messages') or []):
                    if isinstance(_m, dict) and _m.get('role') == 'assistant':
                        _answer = str(_m.get('content', ''))
                        break
                put('done', {
                    'session': {'session_id': session_id, 'messages': result.get('messages', [])},
                    'usage': {'input_tokens': 0, 'output_tokens': 0},
                    'ephemeral': True,
                    'answer': _answer,
                })
                if _checkpoint_stop is not None:
                    _checkpoint_stop.set()
                try:
                    import pathlib
                    pathlib.Path(s.path).unlink(missing_ok=True)
                except Exception:
                    pass
                return  # skip all normal persistence for ephemeral sessions
            if _checkpoint_stop is not None:
                _checkpoint_stop.set()
            if _ckpt_thread is not None:
                _ckpt_thread.join(timeout=15)
            if cancel_event.is_set():
                with _agent_lock:
                    _finalize_cancelled_turn(s, ephemeral=False)
                    try:
                        append_turn_journal_event_for_stream(
                            s.session_id,
                            stream_id,
                            {
                                "event": "interrupted",
                                "created_at": time.time(),
                                "reason": "cancelled",
                            },
                        )
                    except Exception:
                        logger.debug("Failed to append cancelled turn journal event", exc_info=True)
                _put_cancel()
                return
            with _agent_lock:
                if not ephemeral and not _stream_writeback_is_current(s, stream_id):
                    logger.info(
                        "Skipping stale stream writeback for session %s stream %s; active_stream_id=%s",
                        getattr(s, 'session_id', session_id),
                        stream_id,
                        getattr(s, 'active_stream_id', None),
                    )
                    return
                _result_messages = result.get('messages') or _previous_context_messages
                if cancel_event.is_set():
                    _finalize_cancelled_turn(s, ephemeral=False)
                    try:
                        append_turn_journal_event_for_stream(
                            s.session_id,
                            stream_id,
                            {
                                "event": "interrupted",
                                "created_at": time.time(),
                                "reason": "cancelled",
                            },
                        )
                    except Exception:
                        logger.debug("Failed to append cancelled turn journal event", exc_info=True)
                    _put_cancel()
                    return
                _next_context_messages = _restore_reasoning_metadata(
                    _previous_context_messages,
                    _result_messages,
                )
                s.context_messages = _next_context_messages
                s.messages = _merge_display_messages_after_agent_result(
                    _previous_messages,
                    _previous_context_messages,
                    _restore_reasoning_metadata(_previous_messages, _result_messages),
                    msg_text,
                )
                # Strip XML tool-call blocks from assistant message content.
                # DeepSeek and some other providers emit <function_calls>...</function_calls>
                # in the raw response text; this must be removed before the content is
                # saved to the session and displayed in the chat bubble. (#702)
                for _m in s.messages:
                    if isinstance(_m, dict) and _m.get('role') == 'assistant':
                        _raw_content = _m.get('content')
                        if isinstance(_raw_content, str):
                            _cleaned = _strip_xml_tool_calls(_raw_content)
                            if _cleaned != _raw_content:
                                _m['content'] = _cleaned
                        elif isinstance(_raw_content, list):
                            for _part in _raw_content:
                                if isinstance(_part, dict) and isinstance(_part.get('text'), str):
                                    _part['text'] = _strip_xml_tool_calls(_part['text'])

                # ── Detect silent agent failure (no assistant reply produced) ──
                # When the agent catches an auth/network error internally it may return
                # an empty final_response without raising — the stream would end with
                # a done event containing zero assistant messages, leaving the user with
                # no feedback. Emit an apperror so the client shows an inline error.
                # Keep the current-turn assistant detection aligned with the
                # display-merge logic. A compacted or replayed result payload
                # is not always a simple append-only suffix, so use the
                # workspace-aware helper from this branch while still
                # preserving the pre-turn length for downstream self-heal
                # checks introduced on master.
                _all_result_messages = result.get('messages') or []
                _prev_len = len(_previous_context_messages)
                _assistant_added = _assistant_reply_added_after_current_turn(
                    _all_result_messages,
                    _previous_context_messages,
                    msg_text,
                )
                # _token_sent tracks whether on_token() was called (any streamed text)
                if not _assistant_added and not _token_sent:
                    if cancel_event.is_set():
                        _finalize_cancelled_turn(s, ephemeral=ephemeral)
                        if not ephemeral:
                            try:
                                append_turn_journal_event_for_stream(
                                    s.session_id,
                                    stream_id,
                                    {
                                        "event": "interrupted",
                                        "created_at": time.time(),
                                        "reason": "cancelled",
                                    },
                                )
                            except Exception:
                                logger.debug("Failed to append cancelled turn journal event", exc_info=True)
                        _put_cancel()
                        return
                    _last_err = getattr(agent, '_last_error', None) or result.get('error') or ''
                    _err_str = str(_last_err) if _last_err else ''
                    _classification = _classify_provider_error(
                        _err_str,
                        _last_err,
                        silent_failure=not bool(_err_str),
                    )
                    _is_quota = _classification['type'] == 'quota_exhausted'
                    _is_auth = _classification['type'] == 'auth_mismatch'
                    if _is_quota:
                        _err_label = _classification['label']
                        _err_type = _classification['type']
                        _err_hint = _classification['hint']
                    elif _is_auth and not _self_healed:
                        # ── Credential self-heal on 401 (#1401) ──
                        # Before emitting the error, try re-reading credentials
                        # and retrying once with a fresh agent.
                        _heal_result = None
                        _heal_rt = _attempt_credential_self_heal(
                            resolved_provider or '', session_id, _agent_lock,
                        )
                        if _heal_rt is not None:
                            logger.info('[webui] self-heal: retrying stream after credential refresh')
                            # Rebuild runtime variables from the refreshed resolve
                            _rt = _heal_rt
                            resolved_api_key = _heal_rt.get('api_key')
                            if not resolved_provider:
                                resolved_provider = _heal_rt.get('provider')
                            if not resolved_base_url:
                                resolved_base_url = _heal_rt.get('base_url')
                            if isinstance(resolved_provider, str) and resolved_provider.startswith('custom:'):
                                _cp_key, _cp_base = resolve_custom_provider_connection(resolved_provider)
                                if not resolved_api_key and _cp_key:
                                    resolved_api_key = _cp_key
                                if not resolved_base_url and _cp_base:
                                    resolved_base_url = _cp_base
                            # Rebuild agent kwargs and create a fresh agent
                            _agent_kwargs['api_key'] = resolved_api_key
                            _agent_kwargs['base_url'] = resolved_base_url
                            _agent_kwargs['model'] = resolved_model
                            _agent_kwargs['provider'] = resolved_provider
                            if 'credential_pool' in _agent_params:
                                _agent_kwargs['credential_pool'] = _heal_rt.get('credential_pool')
                            agent = _AIAgent(**_agent_kwargs)
                            with STREAMS_LOCK:
                                AGENT_INSTANCES[stream_id] = agent
                            from api.config import SESSION_AGENT_CACHE as _SAC, SESSION_AGENT_CACHE_LOCK as _SAC_L
                            with _SAC_L:
                                _SAC[session_id] = (agent, _agent_sig)
                                _SAC.move_to_end(session_id)
                            # Retry the conversation once with fresh credentials
                            _self_healed = True
                            _token_sent = False
                            try:
                                _heal_result = agent.run_conversation(
                                    user_message=user_message,
                                    system_message=workspace_system_msg,
                                    conversation_history=_sanitize_messages_for_api(_previous_context_messages, cfg=_cfg),
                                    task_id=session_id,
                                    persist_user_message=msg_text,
                                )
                                _heal_all_msgs = _heal_result.get('messages') or []
                                _heal_ok = _has_new_assistant_reply(_heal_all_msgs, _prev_len) or _token_sent
                            except Exception as _retry_exc:
                                logger.warning(
                                    '[webui] self-heal: retry also failed: %s', _retry_exc,
                                )
                                _heal_ok = False
                            if _heal_ok and _heal_result is not None:
                                # Retry succeeded — replace result and skip error
                                result = _heal_result
                                # Fall through past the error-emission block;
                                # the post-result persistence code below will
                                # process ``result`` normally.  We jump past
                                # the ``put('apperror', ...)`` + ``return`` by
                                # NOT entering the ``if not _assistant_added``
                                # guard again — but we are already inside it.
                                # Solution: set _assistant_added so the guard
                                # evaluates False on next conceptual pass.
                                # Since we're in a flat block, directly run the
                                # post-result merge logic here.
                                _result_messages = result.get('messages') or _previous_context_messages
                                _next_context_messages = _restore_reasoning_metadata(
                                    _previous_context_messages,
                                    _result_messages,
                                )
                                s.context_messages = _next_context_messages
                                s.messages = _merge_display_messages_after_agent_result(
                                    _previous_messages,
                                    _previous_context_messages,
                                    _restore_reasoning_metadata(_previous_messages, _result_messages),
                                    msg_text,
                                )
                                # Skip the error block — jump directly to the
                                # normal post-result persistence path by
                                # leaving _assistant_added truthy (set below).
                                _assistant_added = True  # prevent re-entering guard
                        if not _assistant_added:
                            # Self-heal didn't apply or retry failed — emit error
                            _err_label = 'Authentication failed'
                            _err_type = 'auth_mismatch'
                            _err_hint = (
                                'The selected model may not be supported by your configured provider or '
                                'your API key is invalid. Run `hermes model` in your terminal to '
                                'update credentials, then restart the WebUI.'
                            )
                    elif _is_auth:
                        _err_label = 'Authentication failed'
                        _err_type = 'auth_mismatch'
                        _err_hint = (
                            'The selected model may not be supported by your configured provider or '
                            'your API key is invalid. Run `hermes model` in your terminal to '
                            'update credentials, then restart the WebUI.'
                        )
                    else:
                        _err_label = _classification['label']
                        _err_type = _classification['type']
                        _err_hint = _classification['hint']
                    # Skip error emission if credential self-heal succeeded
                    # (#1401) — _assistant_added is set True on successful retry.
                    if _assistant_added:
                        # Self-heal succeeded: messages are already merged into s,
                        # fall through to normal post-result persistence below.
                        pass
                    else:
                        _error_payload = _provider_error_payload(
                            _err_str or f'{_err_label}.',
                            _err_type,
                            _err_hint,
                        )
                        _finalize_product_turn(
                            failed=True,
                            error_type=_err_type,
                            error_message=_error_payload.get('message') or _err_label,
                        )
                        put('apperror', _error_payload)
                        # Clear stream/pending state so the session does not appear
                        # "agent_running" on reload after a silent failure.
                        # Persist the error so it survives page reload.
                        # _error=True ensures _sanitize_messages_for_api excludes it from
                        # subsequent API calls so the LLM never sees its own error as prior context.
                        _materialize_pending_user_turn_before_error(s)
                        s.active_stream_id = None
                        s.pending_user_message = None
                        s.pending_attachments = []
                        s.pending_started_at = None
                        _error_message = {
                            'role': 'assistant',
                            'content': f'**{_err_label}:** {_error_payload.get("message") or _err_label}\n\n*{_err_hint}*',
                            'timestamp': int(time.time()),
                            '_error': True,
                        }
                        if _error_payload.get('details'):
                            _error_message['provider_details'] = _error_payload['details']
                        if _err_type == 'cancelled':
                            _error_message['provider_details_label'] = 'Cancellation details'
                        elif _err_type == 'interrupted':
                            _error_message['provider_details_label'] = 'Interruption details'
                        s.messages.append(_error_message)
                        try:
                            s.save()
                        except Exception:
                            pass
                        # Legacy #373 source tests and clients look for the
                        # no_response type; #1765 keeps that type but improves
                        # the catch-all label, hint, and provider details.
                        return  # apperror already closes the stream on the client side

                # ── Handle context compression side effects ──
                # If compression fired inside run_conversation, the agent may have
                # rotated its session_id. Detect and fix the mismatch so the WebUI
                # continues writing to the correct session file.
                #
                # Lock migration: when session_id rotates, we alias the new ID to
                # the *same* Lock object under SESSION_AGENT_LOCKS so that
                # subsequent callers using _get_session_agent_lock(new_sid) get the
                # same Lock the streaming thread is already holding.  We then pop
                # the old-id entry to prevent a leak.  This is safe because we
                # already hold _agent_lock (the Lock object itself), so the
                # reference stays alive even after the dict entry is removed.
                # Concurrent readers that already looked up the old ID will still
                # see the same Lock object until they release it.
                _agent_sid = getattr(agent, 'session_id', None)
                _compressed = False
                if _agent_sid and _agent_sid != session_id:
                    old_sid = session_id
                    new_sid = _agent_sid
                    s.session_id = new_sid
                    # Carry profile identity across the compression boundary.
                    # Without this, s.profile stays None on the continuation
                    # session. On the next request, _run_agent_streaming calls
                    # get_hermes_home_for_profile(getattr(s, 'profile', None))
                    # which falls back to the default profile's HERMES_HOME.
                    # Memory writes then land in the wrong profile's MEMORY.md.
                    # Stamping here also ensures s.save() persists a non-null
                    # profile field to the continuation session's JSON file,
                    # covering the case where the session is later evicted from
                    # SESSIONS and reconstructed from disk via Session.load().
                    if not s.profile and _resolved_profile_name:
                        s.profile = _resolved_profile_name
                        logger.info(
                            "Stamped profile=%r on continuation session %s after compression",
                            _resolved_profile_name, new_sid,
                        )
                    # Preserve the original session file so the full pre-compression
                    # history survives even when summarisation fails.  The previous
                    # implementation renamed old_sid.json → new_sid.json, which
                    # destroyed the only persistent copy of the uncompressed history
                    # before the new (possibly summary-only) session had been saved.
                    # If the LLM summariser also failed, the user was left with zero
                    # recoverable messages.  (#2223)
                    # ---
                    # Archive the old session: write its current state to disk so
                    # the full conversation history survives even when context
                    # compression removes messages from the model's context.  Skip
                    # the write when the file already contains up-to-date data
                    # (i.e. it was just saved by a checkpoint).
                    _preserve_pre_compression_snapshot(s, old_sid)
                    # Always link the continuation session to its immediate predecessor
                    # (the preserved snapshot).  This OVERRIDES any prior
                    # parent_session_id because the new continuation IS the next link
                    # in the chain: traversal walks new → old → old.parent → ... root.
                    # Stage-353 Opus SHOULD-FIX: previous `if not s.parent_session_id`
                    # guard skipped this stamp on fork-of-fork compressions, so a
                    # subsequent traversal from the new continuation would jump
                    # over the just-preserved snapshot back to the original fork
                    # parent, losing access to the recoverable history in old_sid.json.
                    s.parent_session_id = old_sid
                    with LOCK:
                        if old_sid in SESSIONS:
                            SESSIONS[new_sid] = SESSIONS.pop(old_sid)
                    # Migrate the per-session lock: alias new_sid to the held
                    # _agent_lock reference directly (not via old_sid lookup),
                    # then remove the old_sid entry to prevent a leak.
                    with SESSION_AGENT_LOCKS_LOCK:
                        SESSION_AGENT_LOCKS[new_sid] = _agent_lock
                        SESSION_AGENT_LOCKS.pop(old_sid, None)
                    # Migrate cached agent to the new session ID so the turn
                    # count survives context compression.
                    from api.config import SESSION_AGENT_CACHE, SESSION_AGENT_CACHE_LOCK
                    with SESSION_AGENT_CACHE_LOCK:
                        _cached_entry = SESSION_AGENT_CACHE.pop(old_sid, None)
                        if _cached_entry:
                            SESSION_AGENT_CACHE[new_sid] = _cached_entry
                    _compressed = True
                # Also detect compression via the result dict or compressor state
                if not _compressed:
                    _compressor = getattr(agent, 'context_compressor', None)
                    if _compressor and getattr(_compressor, 'compression_count', 0) > _pre_compression_count:
                        _compressed = True
                # Notify the frontend that compression happened
                if _compressed:
                    visible_after = visible_messages_for_anchor(s.messages, auto_compression=True)
                    s.compression_anchor_visible_idx = (
                        max(0, len(visible_after) - 1) if visible_after else None
                    )
                    s.compression_anchor_message_key = (
                        _compression_anchor_message_key(visible_after[-1]) if visible_after else None
                    )
                    s.compression_anchor_summary = _compact_summary_text(
                        _compression_summary_from_messages(s.messages)
                        or _compression_summary_from_messages(s.context_messages)
                    )
                    put('compressed', {
                        'session_id': s.session_id,
                        'message': 'Context auto-compressed to continue the conversation',
                        'usage': _live_usage_snapshot(),
                    })

                # Stamp 'timestamp' on any messages that don't have one yet
                _now = time.time()
                for _m in s.messages:
                    if isinstance(_m, dict) and not _m.get('timestamp') and not _m.get('_ts'):
                        _m['timestamp'] = int(_now)
                # Only auto-generate title when still default; preserves user renames
                if s.title == 'Untitled' or s.title == 'New Chat' or not s.title:
                    s.title = title_from(s.messages, s.title)
                _looks_default = (s.title == 'Untitled' or s.title == 'New Chat' or not s.title)
                _looks_provisional = _is_provisional_title(s.title, s.messages)
                _invalid_existing_title = _looks_invalid_generated_title(s.title)
                _should_bg_title = (
                    (_looks_default or _looks_provisional or _invalid_existing_title)
                    and (not getattr(s, 'llm_title_generated', False) or _invalid_existing_title)
                )
                _u0 = ''
                _a0 = ''
                if _should_bg_title:
                    _u0, _a0 = _first_exchange_snippets(s.messages)
                # Read token/cost usage from the agent object (if available).
                # Per-turn overwrite (#1857): replace cumulative session totals with the
                # agent's most recent values, which already represent the current turn's
                # full prompt+completion (input_tokens are the entire context, not delta).
                # Defensive: only overwrite when the agent reports non-zero / non-None
                # values. A rebuilt-from-cache-miss agent (post-restart, post-LRU-eviction)
                # starts at zero; without this guard, the next turn would zero out the
                # persisted disk total before any new tokens were spent. Per Opus advisor
                # on stage-320: prevents restart-induced regression of session usage data.
                input_tokens = getattr(agent, 'session_prompt_tokens', 0) or 0
                output_tokens = getattr(agent, 'session_completion_tokens', 0) or 0
                estimated_cost = getattr(agent, 'session_estimated_cost_usd', None)
                cache_read_tokens = getattr(agent, 'session_cache_read_tokens', 0) or 0
                cache_write_tokens = getattr(agent, 'session_cache_write_tokens', 0) or 0
                if input_tokens > 0:
                    s.input_tokens = input_tokens
                if output_tokens > 0:
                    s.output_tokens = output_tokens
                if estimated_cost is not None:
                    s.estimated_cost = estimated_cost
                if cache_read_tokens > 0:
                    s.cache_read_tokens = cache_read_tokens
                if cache_write_tokens > 0:
                    s.cache_write_tokens = cache_write_tokens
                # Persist tool-call summaries even when the final message history only
                # kept bare tool rows and omitted explicit assistant tool_call IDs.
                tool_calls = _extract_tool_calls_from_messages(
                    s.messages,
                    live_tool_calls=_live_tool_calls,
                )
                s.tool_calls = tool_calls
                s.active_stream_id = None
                s.pending_user_message = None
                s.pending_attachments = []
                s.pending_started_at = None
                # Tag the matching user message with attachment filenames for display on reload
                # Only tag a user message whose content relates to this turn's text
                # (msg_text is the full message including the [Attached files: ...] suffix)
                if attachments:
                    display_attachments = [_attachment_name(a) for a in attachments if _attachment_name(a)]
                    for m in reversed(s.messages):
                        if m.get('role') == 'user':
                            content = str(m.get('content', ''))
                            # Match if content is part of the sent message or vice-versa
                            base_text = msg_text.split('\n\n[Attached files:')[0].strip() if '\n\n[Attached files:' in msg_text else msg_text
                            if base_text[:60] in content or content[:60] in msg_text:
                                m['attachments'] = display_attachments
                                break
                # Persist reasoning trace in the session so it survives reload.
                # Must run BEFORE s.save() — otherwise the mutation lives only in
                # memory until the next turn's save, and the last-turn thinking card
                # is lost when the user reloads immediately after a response.
                if _reasoning_text and s.messages:
                    for _rm in reversed(s.messages):
                        if isinstance(_rm, dict) and _rm.get('role') == 'assistant':
                            _rm['reasoning'] = _reasoning_text
                            break
                try:
                    _turn_duration_seconds = max(0.0, time.time() - float(_turn_started_at))
                except Exception:
                    _turn_duration_seconds = 0.0
                _turn_tps = None
                if output_tokens and _turn_duration_seconds > 0:
                    _turn_tps = round(float(output_tokens) / _turn_duration_seconds, 1)
                _gateway_routing = _extract_gateway_routing_metadata(
                    agent,
                    result,
                    requested_model=resolved_model or model,
                    requested_provider=resolved_provider,
                )
                if _gateway_routing:
                    s.gateway_routing = _gateway_routing
                    _history = list(getattr(s, 'gateway_routing_history', None) or [])
                    _history.append(_gateway_routing)
                    s.gateway_routing_history = _history[-50:]
                if s.messages:
                    for _dm in reversed(s.messages):
                        if isinstance(_dm, dict) and _dm.get('role') == 'assistant':
                            _dm['_turnDuration'] = round(_turn_duration_seconds, 3)
                            if _turn_tps is not None:
                                _dm['_turnTps'] = _turn_tps
                            if _gateway_routing:
                                _dm['_gatewayRouting'] = _gateway_routing
                            break
                # Persist context window data on the session so the context-ring
                # indicator survives a page reload (#1318). Must run BEFORE
                # s.save() for the same reason as the reasoning trace above.
                # The fields are captured into the SSE usage payload below; this
                # block writes them to the session itself so GET /api/session
                # returns them on reload instead of falling back to 0.
                _cc_for_save = getattr(agent, 'context_compressor', None)
                if _cc_for_save:
                    s.context_length = getattr(_cc_for_save, 'context_length', 0) or 0
                    s.threshold_tokens = getattr(_cc_for_save, 'threshold_tokens', 0) or 0
                    s.last_prompt_tokens = getattr(_cc_for_save, 'last_prompt_tokens', 0) or 0
                # Fallback: if the compressor didn't report a context_length
                # (fresh agent, interrupted stream, or compressor missing the
                # attribute), resolve it from the model's static metadata so
                # the indicator can still show a meaningful percentage.
                # Sourced from PR #1344 (@jasonjcwu) — extracted to a focused
                # follow-up after PR #1344 was closed as superseded by #1341.
                #
                # #1896: pass config_context_length, provider, and
                # custom_providers so explicit config overrides win over the
                # 256K default fallback. Without these, users on 1M-context
                # models who set `model.context_length: 1048576` (or rely on
                # a `custom_providers` per-model override) get a 256K
                # window in the persisted session and the SSE payload —
                # which then trips LCM auto-compress at ~25% of the wrong
                # value, cascading into 429 floods.
                if not getattr(s, 'context_length', 0):
                    try:
                        from agent.model_metadata import get_model_context_length
                        _cfg_ctx_len = None
                        _cfg_custom_providers = None
                        try:
                            _model_cfg_for_ctx = _cfg.get('model', {}) if isinstance(_cfg, dict) else {}
                            if isinstance(_model_cfg_for_ctx, dict):
                                _raw_cfg_ctx = _model_cfg_for_ctx.get('context_length')
                                if _raw_cfg_ctx is not None:
                                    try:
                                        _parsed_cfg_ctx = int(_raw_cfg_ctx)
                                        if _parsed_cfg_ctx > 0:
                                            _cfg_ctx_len = _parsed_cfg_ctx
                                    except (TypeError, ValueError):
                                        # Invalid config — let the resolver fall
                                        # through to provider/registry probing.
                                        pass
                            _raw_cp = _cfg.get('custom_providers') if isinstance(_cfg, dict) else None
                            if isinstance(_raw_cp, list):
                                _cfg_custom_providers = _raw_cp
                        except Exception:
                            pass
                        _resolved_cl = get_model_context_length(
                            getattr(agent, 'model', resolved_model or '') or '',
                            getattr(agent, 'base_url', '') or '',
                            config_context_length=_cfg_ctx_len,
                            provider=resolved_provider or '',
                            custom_providers=_cfg_custom_providers,
                        )
                        if _resolved_cl:
                            s.context_length = _resolved_cl
                    except TypeError:
                        # Older hermes-agent builds whose get_model_context_length
                        # signature pre-dates the config_context_length /
                        # custom_providers kwargs. Retry with the legacy 2-arg
                        # form so the indicator still resolves *something*.
                        try:
                            from agent.model_metadata import get_model_context_length as _legacy_cl
                            _resolved_cl = _legacy_cl(
                                getattr(agent, 'model', resolved_model or '') or '',
                                getattr(agent, 'base_url', '') or '',
                            )
                            if _resolved_cl:
                                s.context_length = _resolved_cl
                        except Exception:
                            pass
                    except Exception:
                        # Older hermes-agent builds may not expose this helper.
                        # Better to leave context_length=0 than crash the save.
                        pass
                if not ephemeral and s.messages:
                    _latest_assistant_idx = next(
                        (idx for idx in range(len(s.messages) - 1, -1, -1)
                         if isinstance(s.messages[idx], dict) and s.messages[idx].get('role') == 'assistant'),
                        None,
                    )
                    if _latest_assistant_idx is not None:
                        _latest_assistant = s.messages[_latest_assistant_idx]
                        try:
                            append_turn_journal_event_for_stream(
                                s.session_id,
                                stream_id,
                                {
                                    "event": "assistant_started",
                                    "created_at": float(_latest_assistant.get('timestamp') or time.time()),
                                    "assistant_message_index": _latest_assistant_idx,
                                },
                            )
                        except Exception:
                            logger.debug("Failed to append assistant_started turn journal event", exc_info=True)
                if cancel_event.is_set():
                    _finalize_cancelled_turn(s, ephemeral=False)
                    try:
                        append_turn_journal_event_for_stream(
                            s.session_id,
                            stream_id,
                            {
                                "event": "interrupted",
                                "created_at": time.time(),
                                "reason": "cancelled",
                            },
                        )
                    except Exception:
                        logger.debug("Failed to append cancelled turn journal event", exc_info=True)
                    _put_cancel()
                    return
                s.save()
                if cancel_event.is_set():
                    _finalize_cancelled_turn(s, ephemeral=False)
                    try:
                        append_turn_journal_event_for_stream(
                            s.session_id,
                            stream_id,
                            {
                                "event": "interrupted",
                                "created_at": time.time(),
                                "reason": "cancelled",
                            },
                        )
                    except Exception:
                        logger.debug("Failed to append cancelled turn journal event", exc_info=True)
                    _put_cancel()
                    return
                if not ephemeral:
                    try:
                        append_turn_journal_event_for_stream(
                            s.session_id,
                            stream_id,
                            {
                                "event": "completed",
                                "created_at": time.time(),
                                "assistant_message_index": next(
                                    (idx for idx in range(len(s.messages) - 1, -1, -1)
                                     if isinstance(s.messages[idx], dict) and s.messages[idx].get('role') == 'assistant'),
                                    None,
                                ),
                            },
                        )
                    except Exception:
                        logger.debug("Failed to append completed turn journal event", exc_info=True)
                if not ephemeral:
                    # ── Memory-provider lifecycle: mark turn completed (CLI parity) ──
                    # Completed, non-ephemeral turns are marked dirty/uncommitted so
                    # boundary drains know there is work.  Per CLI semantics, the
                    # actual memory extraction/commit happens only at session boundaries
                    # (new session creation, LRU eviction, shutdown drain) — NOT after
                    # every completed turn.  This mirrors Hermes CLI where
                    # run_agent.py::_sync_external_memory_for_turn() records messages
                    # but only AIAgent.commit_memory_session()/shutdown_memory_provider()
                    # trigger extraction via provider on_session_end().  The mark is
                    # in-memory bookkeeping, not provider I/O, so keep it inside the
                    # per-session writeback lock to preserve completed-turn ordering.
                    try:
                        from api.session_lifecycle import mark_turn_completed
                        mark_turn_completed(s.session_id, agent=agent)
                    except Exception:
                        logger.debug("Memory lifecycle mark failed for session %s", s.session_id, exc_info=True)
            usage = {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'estimated_cost': estimated_cost,
                'cache_read_tokens': cache_read_tokens,
                'cache_write_tokens': cache_write_tokens,
                'duration_seconds': round(_turn_duration_seconds, 3),
            }
            if _turn_tps is not None:
                usage['tps'] = _turn_tps
            if _gateway_routing:
                usage['gateway_routing'] = _gateway_routing
            # Include context window data from the agent's compressor for the UI indicator.
            # The session-level persistence happens above (before s.save()) so the values
            # survive a page reload; this block only populates the live SSE usage payload.
            _cc = getattr(agent, 'context_compressor', None)
            if _cc:
                usage['context_length'] = getattr(_cc, 'context_length', 0) or 0
                usage['threshold_tokens'] = getattr(_cc, 'threshold_tokens', 0) or 0
                usage['last_prompt_tokens'] = getattr(_cc, 'last_prompt_tokens', 0) or 0
            # Fallback: when the compressor is absent or reports context_length=0,
            # resolve the model's context window from metadata so the UI indicator
            # shows the correct percentage rather than overflowing against the 128K
            # JS default.  Mirrors the session-save fallback above (lines ~2205-2217).
            #
            # #1896: pass config_context_length, provider, and custom_providers so
            # explicit config overrides win over the 256K default fallback. The
            # SSE payload's `context_length` is what feeds the live token-usage
            # indicator, so a stale 256K here surfaces as the same wrong-window
            # display that motivates this fix.
            if not usage.get('context_length'):
                try:
                    from agent.model_metadata import get_model_context_length as _get_cl
                    _cfg_ctx_len = None
                    _cfg_custom_providers = None
                    try:
                        _model_cfg_for_ctx = _cfg.get('model', {}) if isinstance(_cfg, dict) else {}
                        if isinstance(_model_cfg_for_ctx, dict):
                            _raw_cfg_ctx = _model_cfg_for_ctx.get('context_length')
                            if _raw_cfg_ctx is not None:
                                try:
                                    _parsed_cfg_ctx = int(_raw_cfg_ctx)
                                    if _parsed_cfg_ctx > 0:
                                        _cfg_ctx_len = _parsed_cfg_ctx
                                except (TypeError, ValueError):
                                    pass
                        _raw_cp = _cfg.get('custom_providers') if isinstance(_cfg, dict) else None
                        if isinstance(_raw_cp, list):
                            _cfg_custom_providers = _raw_cp
                    except Exception:
                        pass
                    try:
                        _fb_cl = _get_cl(
                            getattr(agent, 'model', resolved_model or '') or '',
                            getattr(agent, 'base_url', '') or '',
                            config_context_length=_cfg_ctx_len,
                            provider=resolved_provider or '',
                            custom_providers=_cfg_custom_providers,
                        )
                    except TypeError:
                        # Older hermes-agent builds: fall back to legacy 2-arg form.
                        _fb_cl = _get_cl(
                            getattr(agent, 'model', resolved_model or '') or '',
                            getattr(agent, 'base_url', '') or '',
                        )
                    if _fb_cl:
                        usage['context_length'] = _fb_cl
                except Exception:
                    pass
            # Fallback: when last_prompt_tokens is missing (no compressor), use the
            # session-persisted value rather than letting the frontend fall back to
            # the cumulative input_tokens counter, which overflows for long sessions.
            if not usage.get('last_prompt_tokens'):
                _sess_lpt = getattr(s, 'last_prompt_tokens', 0) or 0
                if _sess_lpt:
                    usage['last_prompt_tokens'] = _sess_lpt
            # (reasoning trace already attached + saved above, before s.save())
            # Leftover-steer delivery: if a /steer was queued (via
            # api/chat/steer) but the agent finished its turn before
            # reaching a tool-result boundary that would consume it,
            # the text is still stashed in agent._pending_steer. Drain
            # it now and emit a pending_steer_leftover SSE event so the
            # frontend can queue it for the next turn — same fallback
            # path as the CLI in cli.py:8788-8794.
            try:
                _drain_pending_steer = getattr(agent, '_drain_pending_steer', None)
                _leftover = _drain_pending_steer() if _drain_pending_steer else None
                if _leftover:
                    put('pending_steer_leftover', {
                        'session_id': session_id,
                        'text': str(_leftover),
                    })
            except Exception:
                logger.debug("Failed to drain pending steer for session %s", session_id)
            # /goal parity: after a successful assistant turn, run the Hermes
            # GoalManager judge before terminal done/stream_end events. The
            # frontend surfaces the status line and queues continuation_prompt as
            # a normal next user message so /queue and user input keep priority.
            # #1932: only evaluate when the turn was goal-related (set via
            # STREAM_GOAL_RELATED or goal_related parameter).
            try:
                from api.goals import evaluate_goal_after_turn, has_active_goal

                if not goal_related or not has_active_goal(session_id, profile_home=_profile_home):
                    _goal_decision = {}
                else:
                    _last_goal_response = ''
                    for _goal_msg in reversed(s.messages or []):
                        if not isinstance(_goal_msg, dict) or _goal_msg.get('role') != 'assistant':
                            continue
                        _goal_content = _goal_msg.get('content', '')
                        if isinstance(_goal_content, list):
                            _goal_parts = []
                            for _goal_part in _goal_content:
                                if isinstance(_goal_part, dict):
                                    _goal_text = _goal_part.get('text') or _goal_part.get('content')
                                    if _goal_text:
                                        _goal_parts.append(str(_goal_text))
                            _last_goal_response = '\n'.join(_goal_parts)
                        else:
                            _last_goal_response = str(_goal_content or '')
                        break
                    put('goal', {
                        'session_id': session_id,
                        'state': 'evaluating',
                        'message': 'Evaluating goal progress…',
                        'message_key': 'goal_evaluating_progress',
                    })
                    _goal_decision = evaluate_goal_after_turn(
                        session_id,
                        _last_goal_response,
                        user_initiated=True,
                        profile_home=_profile_home,
                    )
                decision = _goal_decision or {}
                _goal_message = str(decision.get('message') or '').strip()
                if _goal_message:
                    put('goal', {
                        'session_id': session_id,
                        'state': 'continuing' if decision.get('should_continue') else 'idle',
                        'message': _goal_message,
                        'message_key': decision.get('message_key') or ('goal_continuing' if _goal_message else ''),
                        'message_args': decision.get('message_args') or [],
                        'decision': decision,
                    })
                if decision.get('should_continue'):
                    continuation_prompt = str(decision.get('continuation_prompt') or '').strip()
                    if continuation_prompt:
                        # #1932: mark this session as pending a goal continuation
                        # so the next /chat/start creates a goal-related stream.
                        PENDING_GOAL_CONTINUATION.add(session_id)
                        put('goal_continue', {
                            'session_id': session_id,
                            'continuation_prompt': continuation_prompt,
                            'text': continuation_prompt,
                            'message': _goal_message,
                            'message_key': decision.get('message_key') or 'goal_continuing',
                            'message_args': decision.get('message_args') or [],
                            'decision': decision,
                        })
            except Exception as _goal_exc:
                logger.debug("Goal continuation hook failed for session %s: %s", session_id, _goal_exc)
            _finalize_product_turn(failed=False)
            raw_session = s.compact() | {'messages': s.messages, 'tool_calls': tool_calls}
            put('done', {'session': redact_session_data(raw_session), 'usage': usage})
            # Emit one last metering packet for the live message-header TPS label.
            meter_stats = meter().get_stats()
            meter_stats['session_id'] = session_id
            meter_stats.setdefault('tps_available', False)
            meter_stats.setdefault('estimated', False)
            put('metering', meter_stats)
            if _should_bg_title and _u0 and _a0:
                threading.Thread(
                    target=_run_background_title_update,
                    args=(s.session_id, _u0, _a0, str(s.title or '').strip(), put, agent),
                    daemon=True,
                ).start()
            else:
                # Use the original session_id parameter (never reassigned), not s.session_id
                # which may be rotated during context compression. The client captured
                # activeSid = original session_id so they must match for stream_end to close.
                put('stream_end', {'session_id': session_id})
                # Adaptive title refresh: re-generate title from latest exchange
                # every N exchanges (when enabled in settings). Runs after stream_end
                # so it doesn't block the stream.
                _maybe_schedule_title_refresh(s, put, agent)
        finally:
            # Stop the live metering ticker
            _metering_ticker.stop()
            # Unregister the gateway approval callback and unblock any threads
            # still waiting on approval (e.g. stream cancelled mid-approval).
            if _approval_registered and _unreg_notify is not None:
                try:
                    _unreg_notify(session_id)
                except Exception:
                    logger.debug("Failed to unregister approval callback")
            if _clarify_registered and _unreg_clarify_notify is not None:
                try:
                    _unreg_clarify_notify(session_id)
                except Exception:
                    logger.debug("Failed to unregister clarify callback")
            with _ENV_LOCK:
                for _key, _old_value in old_profile_env.items():
                    if _old_value is None: os.environ.pop(_key, None)
                    else: os.environ[_key] = _old_value
                if old_cwd is None: os.environ.pop('TERMINAL_CWD', None)
                else: os.environ['TERMINAL_CWD'] = old_cwd
                if old_exec_ask is None: os.environ.pop('HERMES_EXEC_ASK', None)
                else: os.environ['HERMES_EXEC_ASK'] = old_exec_ask
                if old_session_key is None: os.environ.pop('HERMES_SESSION_KEY', None)
                else: os.environ['HERMES_SESSION_KEY'] = old_session_key
                if old_session_id is None: os.environ.pop('HERMES_SESSION_ID', None)
                else: os.environ['HERMES_SESSION_ID'] = old_session_id
                if old_session_platform is None: os.environ.pop('HERMES_SESSION_PLATFORM', None)
                else: os.environ['HERMES_SESSION_PLATFORM'] = old_session_platform
                if old_hermes_home is None: os.environ.pop('HERMES_HOME', None)
                else: os.environ['HERMES_HOME'] = old_hermes_home

    except Exception as e:
        print('[webui] stream error:\n' + traceback.format_exc(), flush=True)
        err_str = str(e)
        # Sanitize HTML from provider error responses — some providers return
        # full HTML pages (e.g. nginx "404 page not found") instead of JSON errors.
        # Strip HTML tags to avoid rendering raw markup in the chat message.
        _stripped = re.sub(r'<[^>]+>', ' ', err_str)
        _stripped = re.sub(r'\s+', ' ', _stripped).strip()
        if _stripped != err_str:
            err_str = _stripped
        _exc_lower = err_str.lower()
        _classification = _classify_provider_error(err_str, e)
        if cancel_event.is_set():
            if s is not None:
                if _checkpoint_stop is not None:
                    _checkpoint_stop.set()
                if _ckpt_thread is not None:
                    _ckpt_thread.join(timeout=15)
                _lock_ctx = _agent_lock if _agent_lock is not None else contextlib.nullcontext()
                with _lock_ctx:
                    _finalize_cancelled_turn(s, ephemeral=ephemeral)
                    if not ephemeral:
                        try:
                            append_turn_journal_event_for_stream(
                                s.session_id,
                                stream_id,
                                {
                                    "event": "interrupted",
                                    "created_at": time.time(),
                                    "reason": "cancelled",
                                },
                            )
                        except Exception:
                            logger.debug("Failed to append cancelled turn journal event", exc_info=True)
            _put_cancel()
            return
        _exc_is_quota = _classification['type'] == 'quota_exhausted'
        # Exception quota text still includes: 'more credits' in _exc_lower, 'can only afford' in _exc_lower, 'fewer max_tokens' in _exc_lower.
        # Rate-limit detection remains guarded as: (not _exc_is_quota).
        _exc_is_rate_limit = (_classification['type'] == 'rate_limit') and (not _exc_is_quota)
        _exc_is_auth = _classification['type'] == 'auth_mismatch'  # detects '401' and 'unauthorized' via _classify_provider_error.
        _exc_is_not_found = _classification['type'] == 'model_not_found'  # detects '404', 'not found', 'does not exist', and 'invalid model'.
        _exc_is_cancelled = _classification['type'] == 'cancelled'
        _exc_is_interrupted = _classification['type'] == 'interrupted'

        # The user hint still points to Settings / `hermes model` from _classify_provider_error().
        if _exc_is_quota:
            _exc_label, _exc_type, _exc_hint = (
                _classification['label'], _classification['type'], _classification['hint'],
            )
        elif _exc_is_rate_limit:
            _exc_label, _exc_type, _exc_hint = (
                _classification['label'], _classification['type'], _classification['hint'],
            )
        elif _exc_is_auth:
            if not _self_healed:
                # ── Credential self-heal on 401 (#1401) ──
                _heal_rt = _attempt_credential_self_heal(
                    resolved_provider or '', session_id, _agent_lock,
                )
                if _heal_rt is not None:
                    logger.info('[webui] self-heal (except path): retrying stream after credential refresh')
                    _self_healed = True
                    # Rebuild runtime variables
                    _rt = _heal_rt
                    resolved_api_key = _heal_rt.get('api_key')
                    if not resolved_provider:
                        resolved_provider = _heal_rt.get('provider')
                    if not resolved_base_url:
                        resolved_base_url = _heal_rt.get('base_url')
                    if isinstance(resolved_provider, str) and resolved_provider.startswith('custom:'):
                        _cp_key, _cp_base = resolve_custom_provider_connection(resolved_provider)
                        if not resolved_api_key and _cp_key:
                            resolved_api_key = _cp_key
                        if not resolved_base_url and _cp_base:
                            resolved_base_url = _cp_base
                    # Build a fresh agent with the new credentials
                    _heal_kwargs = dict(_agent_kwargs) if '_agent_kwargs' in dir() else {}
                    _heal_kwargs['api_key'] = resolved_api_key
                    _heal_kwargs['base_url'] = resolved_base_url
                    _heal_kwargs['model'] = resolved_model
                    _heal_kwargs['provider'] = resolved_provider
                    if 'credential_pool' in _agent_params:
                        _heal_kwargs['credential_pool'] = _heal_rt.get('credential_pool')
                    _heal_agent = _AIAgent(**_heal_kwargs)
                    with STREAMS_LOCK:
                        AGENT_INSTANCES[stream_id] = _heal_agent
                    from api.config import SESSION_AGENT_CACHE as _SAC2, SESSION_AGENT_CACHE_LOCK as _SAC2_L
                    with _SAC2_L:
                        _SAC2[session_id] = (_heal_agent, _agent_sig)
                        _SAC2.move_to_end(session_id)
                    # Retry the conversation
                    _token_sent = False
                    try:
                        _heal_result = _heal_agent.run_conversation(
                            user_message=user_message,
                            system_message=workspace_system_msg,
                            conversation_history=_sanitize_messages_for_api(_previous_context_messages, cfg=_cfg),
                            task_id=session_id,
                            persist_user_message=msg_text,
                        )
                        # Retry succeeded — persist the result normally
                        if s is not None:
                            if _checkpoint_stop is not None:
                                _checkpoint_stop.set()
                            if _ckpt_thread is not None:
                                _ckpt_thread.join(timeout=15)
                            _lock_ctx = _agent_lock if _agent_lock is not None else contextlib.nullcontext()
                            with _lock_ctx:
                                if not ephemeral and not _stream_writeback_is_current(s, stream_id):
                                    logger.info(
                                        "Skipping stale stream self-heal writeback for session %s stream %s; active_stream_id=%s",
                                        getattr(s, 'session_id', session_id),
                                        stream_id,
                                        getattr(s, 'active_stream_id', None),
                                    )
                                    return
                                _result_messages = _heal_result.get('messages') or _previous_context_messages
                                _next_context_messages = _restore_reasoning_metadata(
                                    _previous_context_messages, _result_messages,
                                )
                                s.context_messages = _next_context_messages
                                s.messages = _merge_display_messages_after_agent_result(
                                    _previous_messages,
                                    _previous_context_messages,
                                    _restore_reasoning_metadata(_previous_messages, _result_messages),
                                    msg_text,
                                )
                                s.save()
                        logger.info('[webui] self-heal (except path): retry succeeded')
                        return  # skip error emission
                    except Exception as _retry_exc2:
                        logger.warning('[webui] self-heal (except path): retry failed: %s', _retry_exc2)
                        # Fall through to emit the original error
            # Self-heal didn't apply or retry failed — emit the auth error
            _exc_label, _exc_type, _exc_hint = (
                'Authentication error', 'auth_mismatch',
                'The selected model may not be supported by your configured provider. '
                'Run `hermes model` in your terminal to switch providers, then restart the WebUI.',
            )
        elif _exc_is_not_found:
            _exc_label, _exc_type, _exc_hint = (
                _classification['label'], _classification['type'], _classification['hint'],
            )
        elif _exc_is_cancelled or _exc_is_interrupted:
            _exc_label, _exc_type, _exc_hint = (
                _classification['label'], _classification['type'], _classification['hint'],
            )
        else:
            _exc_label, _exc_type, _exc_hint = 'Error', 'error', ''

        _error_payload = _provider_error_payload(err_str, _exc_type, _exc_hint)
        if s is not None:
            if _checkpoint_stop is not None:
                _checkpoint_stop.set()
            if _ckpt_thread is not None:
                _ckpt_thread.join(timeout=15)
            # Persist the error so it survives page reload.
            # _error=True ensures _sanitize_messages_for_api excludes it from subsequent
            # API calls so the LLM never sees its own error as prior context on the next turn.
            _lock_ctx = _agent_lock if _agent_lock is not None else contextlib.nullcontext()
            with _lock_ctx:
                if not ephemeral and not _stream_writeback_is_current(s, stream_id):
                    logger.info(
                        "Skipping stale stream error writeback for session %s stream %s; active_stream_id=%s",
                        getattr(s, 'session_id', session_id),
                        stream_id,
                        getattr(s, 'active_stream_id', None),
                    )
                    return
                _materialize_pending_user_turn_before_error(s)
                s.active_stream_id = None
                s.pending_user_message = None
                s.pending_attachments = []
                s.pending_started_at = None
                _error_message = {
                    'role': 'assistant',
                    'content': f'**{_exc_label}:** {_error_payload.get("message") or err_str}' + (f'\n\n*{_exc_hint}*' if _exc_hint else ''),
                    'timestamp': int(time.time()),
                    '_error': True,
                }
                if _error_payload.get('details'):
                    _error_message['provider_details'] = _error_payload['details']
                if _exc_type == 'cancelled':
                    _error_message['provider_details_label'] = 'Cancellation details'
                elif _exc_type == 'interrupted':
                    _error_message['provider_details_label'] = 'Interruption details'
                s.messages.append(_error_message)
                try:
                    s.save()
                except Exception:
                    pass
                if not ephemeral:
                    try:
                        append_turn_journal_event_for_stream(
                            s.session_id,
                            stream_id,
                            {
                                "event": "interrupted",
                                "created_at": time.time(),
                                "reason": _exc_type,
                            },
                        )
                    except Exception:
                        logger.debug("Failed to append interrupted turn journal event", exc_info=True)
        _finalize_product_turn(
            failed=True,
            error_type=_error_payload.get('type') or _exc_type,
            error_message=_error_payload.get('message') or str(_exc) or _exc_type,
        )
        put('apperror', _error_payload)
    finally:
        # Stop the periodic checkpoint thread before the final recovery path.
        # The checkpoint thread also uses the per-session lock; joining it first
        # avoids contending with checkpoint writes during stale-pending repair.
        if _checkpoint_stop is not None:
            _checkpoint_stop.set()
        if _ckpt_thread is not None:
            _ckpt_thread.join(timeout=15)
        if (s is not None
                and getattr(s, 'active_stream_id', None) == stream_id
                and getattr(s, 'pending_user_message', None)):
            update_active_run(stream_id, phase="finalizing")
            _last_resort_sync_from_core(s, stream_id, _agent_lock)
        _finalize_product_turn(failed=True)
        _clear_thread_env()  # TD1: always clear thread-local context
        with STREAMS_LOCK:
            STREAMS.pop(stream_id, None)
            CANCEL_FLAGS.pop(stream_id, None)
            AGENT_INSTANCES.pop(stream_id, None)  # Clean up agent instance reference
            STREAM_PARTIAL_TEXT.pop(stream_id, None)  # Clean up partial text buffer (#893)
            STREAM_REASONING_TEXT.pop(stream_id, None)  # Clean up reasoning trace (#1361 §A)
            STREAM_LIVE_TOOL_CALLS.pop(stream_id, None)  # Clean up tool calls (#1361 §B)
            STREAM_GOAL_RELATED.pop(stream_id, None)  # Clean up goal-related flag (#1932)
            STREAM_LAST_EVENT_ID.pop(stream_id, None)  # Clean up event_id pointer (stage-364)
            unregister_active_run(stream_id)
            # NOTE: do NOT discard PENDING_GOAL_CONTINUATION here. The marker
            # is set by goal_continue (line ~3328) inside the SAME function
            # call and consumed atomically by `_start_chat_stream_for_session`
            # in routes.py (around line 6522) when the next stream starts.
            # Discarding here in the streaming worker's `finally` would
            # almost always race ahead of the frontend's SSE-receive →
            # POST /api/chat/start round-trip and erase the marker before
            # the next stream can read it, breaking the goal-continuation
            # chain. Stage-326 critical fix per Opus advisor review.

# ============================================================
# SECTION: HTTP Request Handler
# do_GET: read-only API endpoints + SSE stream + static HTML
# do_POST: mutating endpoints (session CRUD, chat, upload, approval)
# Routing is a flat if/elif chain. See ARCHITECTURE.md section 4.1.
# ============================================================


def _handle_chat_steer(handler, body: dict) -> bool:
    """Inject a /steer payload into the active agent for a session.

    Mirrors the CLI's `/steer <text>` command (cli.py:6140-6155):
      - Look up the cached AIAgent for the session (PR #1051's
        SESSION_AGENT_CACHE).
      - Verify a stream is currently active for this session.
      - Call agent.steer(text) — thread-safe, stashes text in
        _pending_steer for application at the next tool-result boundary.

    The agent's loop calls _apply_pending_steer_to_tool_results() at the
    end of every tool batch and appends the steer text to the last tool
    result's content with a marker, so the model sees the steer as part
    of the tool output on its next iteration. The user's stream is NOT
    interrupted.

    If no agent is cached, the agent is too old to support steer, or no
    stream is active, return {"accepted": False, "fallback": "<reason>"}
    so the frontend can fall back to interrupt or queue mode. The
    fallback path is the existing behaviour from PR #1062.

    Returns 200 with {"accepted": bool, "fallback": str|None,
    "stream_id": str|None}.
    """
    from api.helpers import j, bad
    from api import config as _cfg

    sid = str((body or {}).get("session_id", "") or "").strip()
    text = str((body or {}).get("text", "") or "").strip()
    if not sid:
        return bad(handler, "session_id required")
    if not text:
        return bad(handler, "text required")

    with _cfg.SESSION_AGENT_CACHE_LOCK:
        cached = _cfg.SESSION_AGENT_CACHE.get(sid)
    if not cached:
        # No active agent for this session — caller falls back to interrupt
        return j(handler, {"accepted": False, "fallback": "no_cached_agent",
                           "stream_id": None})
    agent = cached[0]
    if not hasattr(agent, "steer"):
        # Older hermes-agent that pre-dates the steer() method
        return j(handler, {"accepted": False, "fallback": "agent_lacks_steer",
                           "stream_id": None})

    # Verify the agent is currently running. Use the session's
    # active_stream_id rather than calling load_session_locked() which
    # would block on the streaming thread's lock.
    try:
        s = get_session(sid)
    except KeyError:
        return j(handler, {"accepted": False, "fallback": "session_not_found",
                           "stream_id": None})
    active_stream_id = getattr(s, "active_stream_id", None) or None
    if not active_stream_id:
        return j(handler, {"accepted": False, "fallback": "not_running",
                           "stream_id": None})
    with _cfg.STREAMS_LOCK:
        stream_alive = active_stream_id in _cfg.STREAMS
    if not stream_alive:
        # Active stream id is stale — stream has ended; caller falls back
        return j(handler, {"accepted": False, "fallback": "stream_dead",
                           "stream_id": None})

    steer_text = text
    product_context = None
    product_body = body or {}
    try:
        from api.product_context import product_context_request_body

        product_body = product_context_request_body(product_body, s, text)
    except Exception:
        logger.debug("Failed to restore product context body for steer session=%s", sid, exc_info=True)
    if product_body.get("product_id") or product_body.get("productId"):
        try:
            from api.product_context import product_context_from_request, product_ephemeral_prompt

            product_context = product_context_from_request(product_body, workspace=getattr(s, "workspace", None))
            if product_context and str(product_context.get("scope") or "") in {"product_init", "product_builder"}:
                product_prompt = product_ephemeral_prompt(product_context)
                if product_prompt:
                    steer_text = (
                        f"{product_prompt}\n\n"
                        "Steer update for the current running turn:\n"
                        f"{text}"
                    )
        except Exception:
            logger.debug("Failed to attach product context to steer for session=%s", sid, exc_info=True)

    try:
        accepted = bool(agent.steer(steer_text))
    except Exception as exc:
        logger.debug("agent.steer() raised for session=%s: %s", sid, exc)
        return j(handler, {"accepted": False, "fallback": "steer_error",
                           "stream_id": active_stream_id})

    return j(handler, {"accepted": accepted, "fallback": None,
                       "stream_id": active_stream_id,
                       "product_scope": product_context.get("scope") if product_context else None})


def cancel_stream(stream_id: str) -> bool:
    """Signal an in-flight stream to cancel. Returns True if the stream existed.

    Eagerly releases the session lock (pops STREAMS/CANCEL_FLAGS/AGENT_INSTANCES
    and clears session.active_stream_id) so new /api/chat/start requests succeed
    immediately after cancel, even if the agent thread is still blocked.

    The worker thread's finally block uses .pop(key, None), so the double-pop is
    a safe no-op. Session cleanup runs outside STREAMS_LOCK to preserve lock
    ordering (streaming thread does LOCK → STREAMS_LOCK; inverting would deadlock).
    """
    from api import config as _live_config

    # Use module-level aliases (imported from api.config at startup).
    # In production these are always the same objects as api.config.STREAMS etc.
    # The fallback below handles a hypothetical future case where api.config's
    # state dicts are replaced at runtime (e.g. a future profile-reload path).
    # No production code currently does this; the fallback is defensive only.
    streams = STREAMS
    cancel_flags = CANCEL_FLAGS
    agent_instances = AGENT_INSTANCES
    partial_texts = STREAM_PARTIAL_TEXT
    streams_lock = STREAMS_LOCK
    if stream_id not in streams and getattr(_live_config, 'STREAMS', streams) is not streams:
        streams = _live_config.STREAMS
        cancel_flags = _live_config.CANCEL_FLAGS
        agent_instances = _live_config.AGENT_INSTANCES
        partial_texts = _live_config.STREAM_PARTIAL_TEXT
        streams_lock = _live_config.STREAMS_LOCK

    with streams_lock:
        if stream_id not in streams:
            return False

        # Set WebUI layer cancel flag
        flag = cancel_flags.get(stream_id)
        if flag:
            flag.set()

        # Interrupt the AIAgent instance to stop tool execution
        agent = agent_instances.get(stream_id)
        if agent:
            try:
                agent.interrupt("Cancelled by user")
            except Exception as e:
                # Log but don't block the cancel flow
                import logging
                logging.getLogger(__name__).debug(
                    f"Failed to interrupt agent for stream {stream_id}: {e}"
                )
        else:
            # Agent not yet stored - cancel_event flag will be checked by agent thread
            import logging
            logging.getLogger(__name__).debug(
                f"Cancel requested for stream {stream_id} before agent ready - "
                f"cancel_event flag set, will be checked on agent startup"
            )

        # Clear any pending clarify prompt so the blocked tool call can unwind.
        try:
            from api.clarify import clear_pending as _clear_clarify_pending

            if agent and getattr(agent, "session_id", None):
                _clear_clarify_pending(agent.session_id)
        except Exception:
            logger.debug("Failed to clear clarify prompt during cancel")

        # Capture the queue while the stream still exists, but do not emit the
        # terminal cancel event until the session cleanup below confirms the turn
        # is still active. Otherwise a late Stop click can race with a successful
        # worker save and show cancel in the client while persistence says done.
        q = streams.get(stream_id)
        _emit_cancel_event = True

        # ── Eager session lock release (fixes #653) ──────────────────────────
        # Pop stream state now so the 409 guard in routes.py sees the session
        # as idle and allows new /api/chat/start immediately after cancel,
        # even if the agent thread is still blocked in a C-level syscall.
        # The worker thread's finally block uses .pop(key, None) too, so a
        # double-pop here is safe (no-op).
        streams.pop(stream_id, None)
        cancel_flags.pop(stream_id, None)
        agent_instances.pop(stream_id, None)
        # STREAM_PARTIAL_TEXT is intentionally NOT popped here — the agent thread may
        # still be appending tokens. We capture the snapshot two lines below; the
        # streaming finally block handles the cleanup when the thread exits.

        # Capture partial text and session_id while holding STREAMS_LOCK (avoids a
        # race where the agent thread deallocates the agent object or clears the
        # partial text after we release).
        # Session cleanup (get_session + save) must happen OUTSIDE the lock —
        # get_session() acquires LOCK, and the streaming thread does LOCK first
        # then STREAMS_LOCK, so inverting the order here would cause deadlock.
        _cancel_session_id = getattr(agent, 'session_id', None) if agent else None
        _cancel_partial_text = partial_texts.get(stream_id, '')
        # Fallback: check the live config's partial text map if we used an alias
        # and the text wasn't found in the alias (defensive, matches streams fallback above).
        if not _cancel_partial_text:
            live_partials = getattr(_live_config, 'STREAM_PARTIAL_TEXT', partial_texts)
            if live_partials is not partial_texts:
                _cancel_partial_text = live_partials.get(stream_id, '')
        # Capture reasoning trace and live tool calls (#1361 §A + §B)
        _cancel_reasoning = STREAM_REASONING_TEXT.get(stream_id, '')
        if not _cancel_reasoning:
            live_reasoning = getattr(_live_config, 'STREAM_REASONING_TEXT', STREAM_REASONING_TEXT)
            if live_reasoning is not STREAM_REASONING_TEXT:
                _cancel_reasoning = live_reasoning.get(stream_id, '')
        _cancel_tool_calls = STREAM_LIVE_TOOL_CALLS.get(stream_id, [])
        if not _cancel_tool_calls:
            live_tools = getattr(_live_config, 'STREAM_LIVE_TOOL_CALLS', STREAM_LIVE_TOOL_CALLS)
            if live_tools is not STREAM_LIVE_TOOL_CALLS:
                _cancel_tool_calls = live_tools.get(stream_id, [])

    # Session cleanup outside STREAMS_LOCK to preserve lock ordering.
    # Acquire the per-session _agent_lock too, mirroring every other session
    # writer (streaming success/error paths, periodic checkpoint, POST endpoints)
    # so the cancel-path mutation races neither the checkpoint thread nor
    # concurrent undo/retry calls.
    if _cancel_session_id:
        with _get_session_agent_lock(_cancel_session_id):
            try:
                _cs = get_session(_cancel_session_id)
                if not isinstance(getattr(_cs, 'messages', None), list):
                    _cs.messages = []
                if not _stream_writeback_is_current(_cs, stream_id):
                    # The stream has rotated to a different stream id (newer
                    # turn started, or the worker already finalized this one).
                    # Skip the cancel-marker append AND suppress the terminal
                    # cancel event so we don't contradict a possibly-already-
                    # delivered done payload (#2151 + #2154 / PR #2136).
                    logger.info(
                        "Skipping stale cancel writeback for session %s stream %s; active_stream_id=%s",
                        _cancel_session_id,
                        stream_id,
                        getattr(_cs, 'active_stream_id', None),
                    )
                    _emit_cancel_event = False
                    return True
                # ── Preserve the user's typed message before clearing pending state (#1298) ──
                # The agent's internal messages list (where the user message was appended at
                # the start of run_conversation()) may not have been merged back into
                # _cs.messages yet — cancel_stream() races with the streaming thread's final
                # _merge_display_messages_after_agent_result() call. Without this guard, the
                # user's message is lost: pending_user_message gets cleared below, and
                # _cs.messages still only contains messages from prior turns. The reporter
                # of #1298 sees their typed text vanish from chat after clicking Stop.
                #
                # Recovery rule: if pending_user_message is set AND the latest message in
                # _cs.messages isn't already a matching user turn, synthesize one. The
                # match check guards against double-append when the streaming thread DID
                # reach its merge step before cancel_stream() got the session lock.
                #
                # Wrapped in its own try/except so an unexpected _cs.messages shape (e.g.
                # in unit tests using Mock sessions) cannot escape and skip the rest of
                # the cleanup.
                try:
                    _pending_user = getattr(_cs, 'pending_user_message', None)
                    _pending_atts_raw = getattr(_cs, 'pending_attachments', None)
                    _pending_atts = list(_pending_atts_raw) if isinstance(_pending_atts_raw, (list, tuple)) else []
                    _pending_started = getattr(_cs, 'pending_started_at', None) or 0
                    _msgs_for_recovery = _cs.messages if isinstance(_cs.messages, list) else None
                    if _pending_user and _msgs_for_recovery is not None:
                        _last_user = None
                        for _m in reversed(_msgs_for_recovery):
                            if isinstance(_m, dict) and _m.get('role') == 'user':
                                _last_user = _m
                                break
                        _already_persisted = False
                        if _last_user is not None:
                            _last_content = _last_user.get('content')
                            _last_ts = _last_user.get('timestamp') or 0
                            # Only treat as already-persisted if the latest user turn
                            # was created AT OR AFTER the current turn's pending_started_at.
                            # An earlier turn whose content happens to be a substring
                            # (e.g. prior reply was "ok", user now types "ok please continue")
                            # must NOT short-circuit synthesis — that would re-introduce
                            # the data-loss bug this guard is supposed to prevent.
                            if isinstance(_last_content, str) and _last_ts >= _pending_started:
                                # Tolerate the workspace prefix the streaming thread prepends.
                                if _pending_user == _last_content or _pending_user in _last_content:
                                    _already_persisted = True
                        if not _already_persisted:
                            _user_turn: dict = {
                                'role': 'user',
                                'content': _pending_user,
                                'timestamp': int(time.time()),
                            }
                            if _pending_atts:
                                _user_turn['attachments'] = _pending_atts
                            _msgs_for_recovery.append(_user_turn)
                except Exception:
                    logger.debug(
                        "Failed to recover pending user message on cancel for %s",
                        _cancel_session_id,
                    )
                _cs.active_stream_id = None
                _cs.pending_user_message = None
                _cs.pending_attachments = []
                _cs.pending_started_at = None
                # Persist any partial assistant text that was streamed before cancel (#893).
                # Preserving partial content means the user sees what the agent had
                # produced rather than losing it entirely.  The marker is _partial=True
                # (for session/UI identification only) — NOT _error=True — so the partial
                # content IS kept in the history sent to the agent on the next user
                # message, letting the model continue from where it was cut off.
                # See the inner comment on the append call below for the rationale.
                #
                # #1361: Also persist reasoning trace and live tool calls that were
                # accumulated in thread-local variables but invisible to the cancel path.
                # This prevents paid-token data loss when cancelling mid-reasoning or
                # mid-tool-execution.
                partial_text = _cancel_partial_text.strip() if _cancel_partial_text else ''
                _stripped = ''
                if partial_text:
                    import re as _re
                    # Strip thinking/reasoning markup from partial content before saving.
                    # First pass: remove complete <thinking>...</thinking> blocks.
                    _stripped = _re.sub(r'<think(?:ing)?\b[^>]*>.*?</think(?:ing)?>',
                                        '', partial_text,
                                        flags=_re.DOTALL | _re.IGNORECASE).strip()
                    # Second pass: strip trailing UNCLOSED think/thinking block (the common
                    # cancel case — user stops mid-reasoning before the close tag appears).
                    _stripped = _re.sub(r'<think(?:ing)?\b[^>]*>.*',
                                        '', _stripped,
                                        flags=_re.DOTALL | _re.IGNORECASE).strip()
                # Determine whether there is anything to preserve beyond just the
                # cancel marker.  Content text, reasoning trace, or tool calls all
                # count (#1361 §C — previously only _stripped was checked, so a
                # reasoning-only or tool-only stream produced NO partial message).
                _has_reasoning = bool(_cancel_reasoning and _cancel_reasoning.strip())
                _has_tools = bool(_cancel_tool_calls)
                _cancel_marker_exists = _session_has_cancel_marker(_cs)
                _cancel_marker_idx = len(_cs.messages)
                if _cancel_marker_exists:
                    for _idx in range(len(_cs.messages) - 1, -1, -1):
                        _m = _cs.messages[_idx]
                        if not isinstance(_m, dict) or _m.get('role') != 'assistant':
                            continue
                        _content = str(_m.get('content') or '').strip().lower()
                        if any(pattern in _content for pattern in _CANCEL_MARKER_PATTERNS):
                            _cancel_marker_idx = _idx
                            break
                _partial_already_present = False
                if _stripped:
                    for _m in _cs.messages:
                        # Stage-350 Opus SHOULD-FIX (#2151): only dedup
                        # against actual prior _partial markers from the
                        # same stream, with exact content match. The original
                        # substring check (`_stripped in _existing or
                        # _existing in _stripped`) was too broad — any short
                        # prior assistant reply (e.g. "OK", "Here is the
                        # answer:") becomes a substring of many later partial
                        # bodies and could silently drop the new partial,
                        # resurrecting the #893 data-loss bug on long sessions.
                        if not isinstance(_m, dict) or not _m.get('_partial'):
                            continue
                        if str(_m.get('content') or '').strip() == _stripped:
                            _partial_already_present = True
                            break
                if (_stripped or _has_reasoning or _has_tools) and not _partial_already_present:
                    _partial_msg: dict = {
                        'role': 'assistant',
                        'content': _stripped,  # may be empty for reasoning/tool-only turns
                        '_partial': True,
                        'timestamp': int(time.time()),
                    }
                    if _has_reasoning:
                        _partial_msg['reasoning'] = _cancel_reasoning.strip()
                    if _has_tools:
                        # NOTE: store under the private '_partial_tool_calls' key
                        # (NOT 'tool_calls'). The captured entries use the WebUI
                        # internal shape {name, args, done, duration, is_error}
                        # — they do NOT carry the OpenAI/Anthropic API id +
                        # function: {name, arguments} envelope. If we put them
                        # under 'tool_calls', `_sanitize_messages_for_api`
                        # (which whitelists 'tool_calls' via _API_SAFE_MSG_KEYS)
                        # would forward them to the next-turn LLM call and
                        # strict providers (OpenAI, Anthropic, Z.AI/GLM) would
                        # 400 on the malformed entries — turning a "data lost
                        # on cancel" bug into a "next message returns 400"
                        # bug, which is worse. The underscore-prefixed key is
                        # not in the whitelist, so sanitize strips it. The UI
                        # reads it via static/messages.js and renders it
                        # alongside the regular tool_calls path.
                        # (Opus pre-release review pass 2 of v0.50.251.)
                        _partial_msg['_partial_tool_calls'] = list(_cancel_tool_calls)
                    _cs.messages.insert(_cancel_marker_idx, _partial_msg)
                # Cancel marker — flagged _error=True so it is stripped from conversation
                # history on the next turn (prevents model from seeing "Task cancelled."
                # as a prior assistant reply).
                if not _cancel_marker_exists:
                    _cs.messages.append({
                        'role': 'assistant',
                        'content': _cancelled_turn_content('Task cancelled.'),
                        '_error': True,
                        'provider_details': 'Task cancelled.',
                        'provider_details_label': 'Cancellation details',
                        'timestamp': int(time.time()),
                    })
                _cs.save()
            except Exception:
                logger.debug("Failed to clear session state on cancel for %s", _cancel_session_id)

    if _emit_cancel_event and q:
        try:
            q.put_nowait(('cancel', {'message': 'Cancelled by user'}))
        except Exception:
            logger.debug("Failed to put cancel event to queue")

    return True

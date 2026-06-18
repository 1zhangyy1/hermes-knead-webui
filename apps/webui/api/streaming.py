"""
Hermes Web UI -- SSE streaming engine and agent thread runner.
Includes Sprint 10 cancel support via CANCEL_FLAGS.
"""
import json
import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

from api.config import (
    get_config,
    STREAMS, STREAMS_LOCK, CANCEL_FLAGS, AGENT_INSTANCES, STREAM_PARTIAL_TEXT,
    STREAM_REASONING_TEXT, STREAM_LIVE_TOOL_CALLS,
    STREAM_GOAL_RELATED, PENDING_GOAL_CONTINUATION,
    LOCK, SESSIONS, SESSION_DIR,
    _get_session_agent_lock, _set_thread_env,
    register_active_run, update_active_run,
    SESSION_AGENT_LOCKS, SESSION_AGENT_LOCKS_LOCK,
    resolve_model_provider,
    resolve_custom_provider_connection,
    model_with_provider_context,
    load_settings,
)
from api.helpers import redact_session_data, _redact_text
from api.metering import meter
from api.run_journal import RunJournalWriter
from api.streaming_errors import (
    CANCEL_MARKER_PATTERNS as _CANCEL_MARKER_PATTERNS,
    cancelled_turn_content as _cancelled_turn_content_impl,
    cancelled_turn_hint as _cancelled_turn_hint_impl,
    classify_provider_error as _classify_provider_error_impl,
    is_quota_error_text as _is_quota_error_text_impl,
    preferred_agent_display_name as _preferred_agent_display_name_impl,
    provider_error_payload as _provider_error_payload_impl,
    sanitize_provider_error_text as _sanitize_provider_error_text,
)
from api.streaming_cancellation import (
    cancel_stream_request as _cancel_stream_request,
    cleanup_ephemeral_cancelled_turn as _cleanup_ephemeral_cancelled_turn_impl,
    finalize_cancelled_turn as _finalize_cancelled_turn_impl,
    handle_post_run_cancel as _handle_post_run_cancel,
    handle_preflight_cancel as _handle_preflight_cancel,
    persist_cancelled_turn as _persist_cancelled_turn_impl,
    session_has_cancel_marker as _session_has_cancel_marker_impl,
)
from api.streaming_chat_steer import (
    drain_pending_steer_leftover as _drain_pending_steer_leftover,
    handle_chat_steer as _handle_chat_steer_impl,
)
from api.streaming_cleanup import finalize_webui_streaming_worker_exit as _finalize_streaming_worker_exit
from api.streaming_gateway import (
    GATEWAY_ROUTING_ATTEMPT_KEYS as _GATEWAY_ROUTING_ATTEMPT_KEYS,
    GATEWAY_ROUTING_CONTAINER_KEYS as _GATEWAY_ROUTING_CONTAINER_KEYS,
    GATEWAY_ROUTING_TOP_LEVEL_KEYS as _GATEWAY_ROUTING_TOP_LEVEL_KEYS,
    clean_gateway_routing_scalar as _clean_gateway_routing_scalar,
    extract_gateway_routing_metadata as _extract_gateway_routing_metadata,
    find_gateway_metadata_payload as _find_gateway_metadata_payload,
    normalize_gateway_routing_metadata as _normalize_gateway_routing_metadata,
)
from api.streaming_goal import run_post_turn_goal_hook as _run_post_turn_goal_hook
from api.streaming_ephemeral import handle_completed_conversation_post_run as _handle_completed_conversation_post_run
from api.streaming_attachments import (
    IMAGE_MAGIC as _IMAGE_MAGIC,
    NATIVE_IMAGE_MAX_BYTES as _NATIVE_IMAGE_MAX_BYTES,
    attachment_name as _attachment_name,
    build_native_multimodal_message as _build_native_multimodal_message,
    is_valid_image as _is_valid_image,
)
from api.streaming_context import (
    API_SAFE_MSG_KEYS as _API_SAFE_MSG_KEYS_IMPL,
    apply_agent_result_to_session as _apply_agent_result_to_session,
    api_safe_message_positions as _api_safe_message_positions_impl,
    assistant_reply_added_after_current_turn as _assistant_reply_added_after_current_turn_impl,
    capture_turn_start_snapshot as _capture_turn_start_snapshot,
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
    preserve_pre_compression_snapshot as _preserve_pre_compression_snapshot_impl,
    restore_reasoning_metadata as _restore_reasoning_metadata_impl,
    sanitize_messages_for_api as _sanitize_messages_for_api_impl,
    session_context_messages as _session_context_messages_impl,
    strip_native_image_parts_from_content as _strip_native_image_parts_from_content_impl,
)
from api.streaming_context_window import (
    apply_context_window_to_usage as _apply_context_window_to_usage,
)
from api.streaming_checkpoint import (
    start_periodic_checkpoint as _start_periodic_checkpoint,
    stop_checkpoint_thread as _stop_checkpoint_thread,
)
from api.streaming_tool_calls import (
    TOOL_RESULT_SNIPPET_MAX as _TOOL_RESULT_SNIPPET_MAX,
    nearest_assistant_msg_idx as _nearest_assistant_msg_idx,
    tool_result_snippet as _tool_result_snippet,
    truncate_tool_args as _truncate_tool_args,
)
from api.streaming_agent_runtime import (
    agent_cache_api_key_sig as _agent_cache_api_key_sig,
    refresh_cached_agent_primary_runtime_snapshot as _refresh_cached_agent_primary_runtime_snapshot,
    refresh_cached_agent_runtime as _refresh_cached_agent_runtime,
)
from api.streaming_agent_cache import (
    get_and_register_agent_for_turn as _get_and_register_agent_for_turn,
)
from api.streaming_agent_config import (
    initialize_session_db as _initialize_session_db,
    load_agent_config_and_toolsets as _load_agent_config_and_toolsets,
    prepare_webui_agent_kwargs as _prepare_webui_agent_kwargs,
    resolve_agent_runtime_connection as _resolve_agent_runtime_connection,
)
from api.streaming_bridges import initialize_webui_streaming_bridges as _initialize_streaming_bridges
from api.streaming_process_notifications import (
    drain_webui_process_notifications as _drain_webui_process_notifications_impl,
    format_process_notification as _format_process_notification_impl,
    message_text_with_process_notifications as _message_text_with_process_notifications,
    mark_process_completion_consumed as _mark_process_completion_consumed_impl,
)
from api.streaming_product_turn import ProductTurnFinalizer as _ProductTurnFinalizer
from api.streaming_run_state import initialize_webui_streaming_run_state as _initialize_streaming_run_state
from api.streaming_turn_journal import (
    append_interrupted_turn_event as _append_interrupted_turn_event,
    append_worker_started_turn_event as _append_worker_started_turn_event,
)
from api.streaming_terminal import (
    emit_completed_turn_done as _emit_completed_turn_done,
)
from api.streaming_turn_start import prepare_streaming_turn_input as _prepare_streaming_turn_input
from api.streaming_usage import build_done_usage_payload as _build_done_usage_payload
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
from api.streaming_title_refresh import (
    get_title_refresh_interval as _get_title_refresh_interval_impl,
    maybe_schedule_title_refresh as _maybe_schedule_title_refresh_impl,
    put_title_status as _put_title_status_impl,
    run_background_title_refresh as _run_background_title_refresh_impl,
    run_background_title_update as _run_background_title_update_impl,
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
    clarify_timeout_seconds as _clarify_timeout_seconds_impl,
    has_new_assistant_reply as _has_new_assistant_reply_impl,
    restore_agent_process_env as _restore_agent_process_env,
    webui_clarify_callback as _webui_clarify_callback_impl,
    webui_ephemeral_system_prompt as _webui_ephemeral_system_prompt_impl,
)
from api.streaming_runtime_prompt import (
    build_workspace_system_message as _build_workspace_system_message,
    configure_agent_runtime_prompt as _configure_agent_runtime_prompt,
)
from api.streaming_completed_writeback import handle_completed_conversation_writeback as _handle_completed_conversation_writeback
from api.streaming_exception_handling import handle_streaming_exception as _handle_streaming_exception
from api.streaming_worker_startup import prepare_streaming_worker_startup as _prepare_streaming_worker_startup

# Global lock for os.environ writes. Per-session locks (_agent_lock) prevent
# concurrent runs of the SAME session, but two DIFFERENT sessions can still
# interleave their os.environ writes. This global lock serializes the env
# save/restore — held only briefly across the env-mutation critical section,
# NOT for the entire agent run. The agent runs outside the lock; the finally
# block re-acquires to atomically restore env vars. See narrow-lock pattern
# in _run_agent_streaming (line ~2719) and profile_env_for_background_worker
# (api/profiles.py:715).
_ENV_LOCK = threading.Lock()


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
    return _session_has_cancel_marker_impl(session)


def _cancelled_turn_content(message: str = 'Task cancelled.') -> str:
    return _cancelled_turn_content_impl(
        message,
        cancelled_turn_hint_fn=_cancelled_turn_hint,
    )


def _persist_cancelled_turn(session, *, message: str = 'Task cancelled.') -> None:
    _persist_cancelled_turn_impl(
        session,
        message=message,
        materialize_pending_user_turn=_materialize_pending_user_turn_before_error,
        session_has_cancel_marker_fn=_session_has_cancel_marker,
        cancelled_turn_content_fn=_cancelled_turn_content,
    )


def _cleanup_ephemeral_cancelled_turn(session) -> None:
    _cleanup_ephemeral_cancelled_turn_impl(session, logger=logger)


def _finalize_cancelled_turn(session, *, ephemeral: bool = False, message: str = 'Task cancelled.') -> None:
    _finalize_cancelled_turn_impl(
        session,
        ephemeral=ephemeral,
        message=message,
        cleanup_ephemeral_cancelled_turn_fn=_cleanup_ephemeral_cancelled_turn,
        persist_cancelled_turn_fn=_persist_cancelled_turn,
        logger=logger,
    )


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


def _get_title_refresh_interval() -> int:
    return _get_title_refresh_interval_impl()


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
    _put_title_status_impl(
        put_event,
        session_id,
        status,
        reason,
        title,
        raw_preview,
        logger=logger,
    )


def _run_background_title_update(session_id: str, user_text: str, assistant_text: str, placeholder_title: str, put_event, agent=None):
    return _run_background_title_update_impl(
        session_id,
        user_text,
        assistant_text,
        placeholder_title,
        put_event,
        agent,
        get_session=get_session,
        put_title_status_fn=_put_title_status,
        looks_invalid_generated_title=_looks_invalid_generated_title,
        is_provisional_title=_is_provisional_title,
        aux_title_configured=_aux_title_configured,
        generate_title_for_agent=_generate_llm_session_title_for_agent,
        generate_title_via_aux=_generate_llm_session_title_via_aux,
        fallback_title_from_exchange=_fallback_title_from_exchange,
        is_generic_fallback_title=_is_generic_fallback_title,
        get_session_agent_lock=_get_session_agent_lock,
        lock=LOCK,
        sessions=SESSIONS,
        logger=logger,
    )


def _run_background_title_refresh(session_id: str, user_text: str, assistant_text: str, current_title: str, put_event, agent=None):
    return _run_background_title_refresh_impl(
        session_id,
        user_text,
        assistant_text,
        current_title,
        put_event,
        agent,
        get_session=get_session,
        put_title_status_fn=_put_title_status,
        aux_title_configured=_aux_title_configured,
        generate_title_for_agent=_generate_llm_session_title_for_agent,
        generate_title_via_aux=_generate_llm_session_title_via_aux,
        get_session_agent_lock=_get_session_agent_lock,
        lock=LOCK,
        sessions=SESSIONS,
        logger=logger,
    )


def _preserve_pre_compression_snapshot(s, old_sid: str) -> None:
    return _preserve_pre_compression_snapshot_impl(
        s,
        old_sid,
        session_dir=SESSION_DIR,
        logger=logger,
    )


def _maybe_schedule_title_refresh(session, put_event, agent):
    return _maybe_schedule_title_refresh_impl(
        session,
        put_event,
        agent,
        get_title_refresh_interval_fn=_get_title_refresh_interval,
        count_exchanges=_count_exchanges,
        latest_exchange_snippets=_latest_exchange_snippets,
        run_background_title_refresh_fn=_run_background_title_refresh,
        thread_factory=threading.Thread,
    )


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
        _append_worker_started_turn_event(session_id, stream_id, logger=logger)
    s = None
    _rt = {}
    _output_bridge = None
    old_profile_env = {}
    old_runtime_env = {}

    # MCP discovery moved to AFTER the per-profile HERMES_HOME mutation below
    # (was here at v0.51.30) — the previous placement always read the default
    # profile's mcp_servers because os.environ['HERMES_HOME'] hadn't been
    # rewritten yet.  See https://github.com/nesquena/hermes-webui/issues/1968.

    agent = None
    _run_state = _initialize_streaming_run_state(
        stream_id=stream_id,
        session_id=session_id,
        queue=q,
        run_journal=run_journal,
        get_session=lambda: get_session(session_id),
        get_agent=lambda: agent,
        logger=logger,
    )
    cancel_event = _run_state.cancel_event
    put = _run_state.put

    # Initialised here (before any code that may raise) so the outer `finally`
    # block can safely check `if _checkpoint_stop is not None` even when an
    # exception fires before the checkpoint thread is created (Issue #765).
    _checkpoint_stop = None
    _ckpt_thread = None
    _agent_lock = None
    try:
        _startup = _prepare_streaming_worker_startup(
            session_id=session_id,
            stream_id=stream_id,
            workspace=workspace,
            model=model,
            model_provider=model_provider,
            ephemeral=ephemeral,
            cancel_event=cancel_event,
            put=put,
            get_session=get_session,
            update_active_run=update_active_run,
            get_session_agent_lock=_get_session_agent_lock,
            handle_preflight_cancel=_handle_preflight_cancel,
            finalize_cancelled_turn=_finalize_cancelled_turn,
            put_cancel=_put_cancel,
            set_thread_env=_set_thread_env,
            env_lock=_ENV_LOCK,
            logger=logger,
        )
        s = _startup.session
        _agent_lock = _startup.agent_lock
        provider_context = _startup.provider_context
        _profile_home = _startup.profile_home
        _resolved_profile_name = _startup.resolved_profile_name
        old_profile_env = _startup.profile_env_snapshot or {}
        old_runtime_env = _startup.runtime_env_snapshot or {}
        _gateway_notifications = _startup.gateway_notifications
        if _startup.should_return:
            return

        try:
            _self_healed = False  # (#1401) prevents infinite self-heal retries
            _bridge_bundle = _initialize_streaming_bridges(
                stream_id=stream_id,
                session_id=session_id,
                run_state=_run_state,
                put=put,
                tool_result_snippet=_tool_result_snippet,
                logger=logger,
            )
            _output_bridge = _bridge_bundle.output_bridge
            _tool_bridge = _bridge_bundle.tool_bridge
            _live_tool_calls = _bridge_bundle.live_tool_calls
            _checkpoint_activity = _bridge_bundle.checkpoint_activity

            _AIAgent = _get_ai_agent()
            if _AIAgent is None:
                raise ImportError(_aiagent_import_error_detail())

            _session_db = _initialize_session_db()
            resolved_model, resolved_provider, resolved_base_url = resolve_model_provider(
                model_with_provider_context(model, provider_context)
            )

            _rt, resolved_api_key, resolved_provider, resolved_base_url = _resolve_agent_runtime_connection(
                resolved_provider=resolved_provider,
                resolved_base_url=resolved_base_url,
                custom_provider_resolver=resolve_custom_provider_connection,
            )

            _cfg, _toolsets = _load_agent_config_and_toolsets(session_id)

            _agent_kwargs_state = _prepare_webui_agent_kwargs(
                agent_cls=_AIAgent,
                config=_cfg,
                model=resolved_model,
                provider=resolved_provider,
                base_url=resolved_base_url,
                api_key=resolved_api_key,
                enabled_toolsets=_toolsets,
                session_id=session_id,
                session_db=_session_db,
                output_bridge=_output_bridge,
                tool_bridge=_tool_bridge,
                run_state=_run_state,
                cancel_event=cancel_event,
                clarify_timeout_seconds=_clarify_timeout_seconds,
                webui_clarify_callback=_webui_clarify_callback_impl,
                runtime=_rt,
            )
            _agent_kwargs = _agent_kwargs_state.agent_kwargs
            _agent_params = _agent_kwargs_state.agent_params
            _fallback_resolved = _agent_kwargs_state.fallback_resolved
            _max_iterations_cfg = _agent_kwargs_state.max_iterations
            _max_tokens_cfg = _agent_kwargs_state.max_tokens
            _reasoning_config = _agent_kwargs_state.reasoning_config

            _registered_agent = _get_and_register_agent_for_turn(
                session_id=session_id,
                stream_id=stream_id,
                session=s,
                agent_factory=_AIAgent,
                agent_kwargs=_agent_kwargs,
                ephemeral=ephemeral,
                resolved_model=resolved_model,
                resolved_api_key=resolved_api_key,
                resolved_base_url=resolved_base_url,
                resolved_provider=resolved_provider,
                runtime=_rt,
                max_iterations=_max_iterations_cfg,
                max_tokens=_max_tokens_cfg,
                fallback_resolved=_fallback_resolved,
                toolsets=_toolsets,
                reasoning_config=_reasoning_config,
                profile_home=_profile_home,
                session_db=_session_db,
                agent_lock=_agent_lock,
                finalize_cancelled_turn_fn=_finalize_cancelled_turn,
                put_cancel_fn=_put_cancel,
                logger=logger,
            )
            if not _registered_agent.should_continue:
                return
            agent = _registered_agent.agent
            _agent_sig = _registered_agent.agent_sig

            _turn_input = _prepare_streaming_turn_input(
                session=s,
                agent=agent,
                msg_text=msg_text,
                attachments=attachments,
                workspace=workspace,
                config=_cfg,
                product_context=product_context,
                agent_lock=_agent_lock,
                checkpoint_activity=_checkpoint_activity,
                session_id=session_id,
                personality_name=getattr(s, 'personality', None),
                webui_ephemeral_system_prompt=_webui_ephemeral_system_prompt,
                logger=logger,
            )
            workspace_system_msg = _turn_input.system_message
            user_message = _turn_input.user_message
            _turn_start = _turn_input.turn_start
            _turn_started_at = _turn_start.started_at
            _previous_messages = _turn_start.previous_messages
            _previous_context_messages = _turn_start.previous_context_messages
            _pre_compression_count = _turn_start.pre_compression_count
            _checkpoint_runner = _turn_input.checkpoint_runner
            _checkpoint_stop = _checkpoint_runner.stop_event
            _ckpt_thread = _checkpoint_runner.thread

            result = agent.run_conversation(
                user_message=user_message,
                system_message=workspace_system_msg,
                conversation_history=_sanitize_messages_for_api(_previous_context_messages, cfg=_cfg),
                task_id=session_id,
                persist_user_message=msg_text,
            )
            if _handle_completed_conversation_post_run(
                result,
                session=s,
                session_id=session_id,
                stream_id=stream_id,
                cancel_event=cancel_event,
                agent_lock=_agent_lock,
                finalize_cancelled_turn=_finalize_cancelled_turn,
                put_cancel=_put_cancel,
                ephemeral=ephemeral,
                checkpoint_stop=_checkpoint_stop,
                checkpoint_thread=_ckpt_thread,
                put=put,
                handle_post_run_cancel=_handle_post_run_cancel,
                stop_checkpoint_thread_fn=_stop_checkpoint_thread,
                logger=logger,
            ):
                return
            _writeback_result = _handle_completed_conversation_writeback(
                result,
                session=s,
                agent=agent,
                self_healed=_self_healed,
                stream_id=stream_id,
                session_id=session_id,
                cancel_event=cancel_event,
                agent_lock=_agent_lock,
                ephemeral=ephemeral,
                previous_messages=_previous_messages,
                previous_context_messages=_previous_context_messages,
                msg_text=msg_text,
                output_bridge=_output_bridge,
                live_tool_calls=_live_tool_calls,
                turn_started_at=_turn_started_at,
                attachments=attachments,
                model=model,
                resolved_model=resolved_model,
                resolved_provider=resolved_provider,
                resolved_base_url=resolved_base_url,
                resolved_profile_name=_resolved_profile_name,
                config=_cfg,
                pre_compression_count=_pre_compression_count,
                usage_snapshot=_run_state.live_usage_snapshot,
                agent_factory=_AIAgent,
                agent_kwargs=_agent_kwargs,
                agent_params=_agent_params,
                agent_sig=_agent_sig,
                user_message=user_message,
                system_message=workspace_system_msg,
                custom_provider_resolver=resolve_custom_provider_connection,
                agent_instances=AGENT_INSTANCES,
                streams_lock=STREAMS_LOCK,
                put=put,
                finalize_cancelled_turn=_finalize_cancelled_turn,
                append_interrupted_turn_event=_append_interrupted_turn_event,
                put_cancel=_put_cancel,
                stream_writeback_is_current=_stream_writeback_is_current,
                classify_provider_error=_classify_provider_error,
                provider_error_payload=_provider_error_payload,
                finalize_product_turn=_finalize_product_turn,
                materialize_pending_user_turn=_materialize_pending_user_turn_before_error,
                sanitize_messages_for_api=_sanitize_messages_for_api,
                has_new_assistant_reply=_has_new_assistant_reply,
                assistant_reply_added_after_current_turn=_assistant_reply_added_after_current_turn,
                preserve_pre_compression_snapshot=_preserve_pre_compression_snapshot,
                compression_anchor_message_key=_compression_anchor_message_key,
                compact_summary_text=_compact_summary_text,
                compression_summary_from_messages=_compression_summary_from_messages,
                title_from_fn=title_from,
                is_provisional_title=_is_provisional_title,
                looks_invalid_generated_title=_looks_invalid_generated_title,
                first_exchange_snippets=_first_exchange_snippets,
                extract_gateway_routing_metadata=_extract_gateway_routing_metadata,
                logger=logger,
            )
            if _writeback_result.self_healed:
                _rt = _writeback_result.runtime
                resolved_api_key = _writeback_result.resolved_api_key
                resolved_provider = _writeback_result.resolved_provider
                resolved_base_url = _writeback_result.resolved_base_url
                _agent_kwargs = _writeback_result.agent_kwargs
                agent = _writeback_result.agent
                _self_healed = True
                if _writeback_result.result is not None:
                    result = _writeback_result.result
            if _writeback_result.should_return:
                return
            _completed_turn_state = _writeback_result.completed_turn_state
            # (reasoning trace already attached before completed-turn save)
            _emit_completed_turn_done(
                s,
                original_session_id=session_id,
                token_usage=_completed_turn_state.token_usage,
                turn_metadata=_completed_turn_state.turn_metadata,
                config=_cfg,
                resolved_model=resolved_model or '',
                resolved_provider=resolved_provider or '',
                agent=agent,
                profile_home=_profile_home,
                goal_related=goal_related,
                put=put,
                pending_goal_continuation=PENDING_GOAL_CONTINUATION,
                tool_calls=_completed_turn_state.tool_calls,
                title_plan=_completed_turn_state.title_plan,
                redact_session_data=redact_session_data,
                build_done_usage_payload=_build_done_usage_payload,
                apply_context_window_to_usage=_apply_context_window_to_usage,
                drain_pending_steer_leftover=_drain_pending_steer_leftover,
                run_post_turn_goal_hook=_run_post_turn_goal_hook,
                finalize_product_turn=_finalize_product_turn,
                meter_stats_fn=meter().get_stats,
                run_background_title_update=_run_background_title_update,
                maybe_schedule_title_refresh=_maybe_schedule_title_refresh,
                logger=logger,
            )
        finally:
            # Stop the live metering ticker
            _run_state.metering_ticker.stop()
            # Unregister gateway callbacks and unblock any threads still
            # waiting on approval/clarify prompts.
            _gateway_notifications.unregister(session_id)
            _restore_agent_process_env(
                old_profile_env,
                old_runtime_env,
                env_lock=_ENV_LOCK,
            )

    except Exception as e:
        _exception_result = _handle_streaming_exception(
            e,
            runtime_vars=locals(),
            self_healed=locals().get('_self_healed', False),
            session=s,
            stream_id=stream_id,
            session_id=session_id,
            cancel_event=cancel_event,
            agent_lock=_agent_lock,
            checkpoint_stop=_checkpoint_stop,
            checkpoint_thread=_ckpt_thread,
            ephemeral=ephemeral,
            logger=logger,
            sanitize_provider_error_text=_sanitize_provider_error_text,
            classify_provider_error=_classify_provider_error,
            finalize_cancelled_turn=_finalize_cancelled_turn,
            put_cancel=_put_cancel,
            provider_error_payload=_provider_error_payload,
            finalize_product_turn=_finalize_product_turn,
            put=put,
            append_interrupted_turn_event=_append_interrupted_turn_event,
            materialize_pending_user_turn=_materialize_pending_user_turn_before_error,
            stop_checkpoint_thread=_stop_checkpoint_thread,
            stream_writeback_is_current=_stream_writeback_is_current,
            custom_provider_resolver=resolve_custom_provider_connection,
            agent_instances=AGENT_INSTANCES,
            streams_lock=STREAMS_LOCK,
            sanitize_messages_for_api=_sanitize_messages_for_api,
            apply_agent_result_to_session=_apply_agent_result_to_session,
            agent_factory=locals().get('_AIAgent'),
        )
        if _exception_result.self_healed:
            _self_healed = True
            _rt = _exception_result.runtime
            resolved_api_key = _exception_result.resolved_api_key
            resolved_provider = _exception_result.resolved_provider
            resolved_base_url = _exception_result.resolved_base_url
            _agent_kwargs = _exception_result.agent_kwargs
        if _exception_result.should_return:
            return  # skip error emission or stale exception writeback
    finally:
        _finalize_streaming_worker_exit(
            session=s,
            stream_id=stream_id,
            agent_lock=_agent_lock,
            checkpoint_stop=_checkpoint_stop,
            checkpoint_thread=_ckpt_thread,
            last_resort_sync_from_core=_last_resort_sync_from_core,
            finalize_product_turn=_finalize_product_turn,
            goal_related=STREAM_GOAL_RELATED,
        )

# ============================================================
# SECTION: HTTP Request Handler
# do_GET: read-only API endpoints + SSE stream + static HTML
# do_POST: mutating endpoints (session CRUD, chat, upload, approval)
# Routing is a flat if/elif chain. See ARCHITECTURE.md section 4.1.
# ============================================================


def _handle_chat_steer(handler, body: dict) -> bool:
    return _handle_chat_steer_impl(
        handler,
        body,
        get_session=get_session,
        logger=logger,
    )


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

    return _cancel_stream_request(
        stream_id,
        live_config=_live_config,
        streams=STREAMS,
        cancel_flags=CANCEL_FLAGS,
        agent_instances=AGENT_INSTANCES,
        partial_texts=STREAM_PARTIAL_TEXT,
        reasoning_texts=STREAM_REASONING_TEXT,
        live_tool_calls=STREAM_LIVE_TOOL_CALLS,
        streams_lock=STREAMS_LOCK,
        get_session=get_session,
        get_session_agent_lock=_get_session_agent_lock,
        stream_writeback_is_current=_stream_writeback_is_current,
        cancelled_turn_content_fn=_cancelled_turn_content,
        logger=logger,
    )

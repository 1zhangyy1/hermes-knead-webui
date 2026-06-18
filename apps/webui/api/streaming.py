"""
Hermes Web UI -- SSE streaming engine and agent thread runner.
Includes Sprint 10 cancel support via CANCEL_FLAGS.
"""
import contextlib
import json
import logging
import os
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
    capture_cancel_stream_snapshot as _capture_cancel_stream_snapshot_impl,
    cleanup_ephemeral_cancelled_turn as _cleanup_ephemeral_cancelled_turn_impl,
    finalize_cancelled_turn as _finalize_cancelled_turn_impl,
    handle_exception_cancel as _handle_exception_cancel,
    handle_post_run_cancel as _handle_post_run_cancel,
    handle_preflight_cancel as _handle_preflight_cancel,
    persist_cancel_stream_writeback as _persist_cancel_stream_writeback_impl,
    persist_cancelled_turn as _persist_cancelled_turn_impl,
    register_agent_instance_or_cancel as _register_agent_instance_or_cancel,
    session_has_cancel_marker as _session_has_cancel_marker_impl,
)
from api.streaming_chat_steer import (
    drain_pending_steer_leftover as _drain_pending_steer_leftover,
    handle_chat_steer as _handle_chat_steer_impl,
)
from api.streaming_cleanup import cleanup_stream_registries as _cleanup_stream_registries
from api.streaming_gateway import (
    GATEWAY_ROUTING_ATTEMPT_KEYS as _GATEWAY_ROUTING_ATTEMPT_KEYS,
    GATEWAY_ROUTING_CONTAINER_KEYS as _GATEWAY_ROUTING_CONTAINER_KEYS,
    GATEWAY_ROUTING_TOP_LEVEL_KEYS as _GATEWAY_ROUTING_TOP_LEVEL_KEYS,
    clean_gateway_routing_scalar as _clean_gateway_routing_scalar,
    extract_gateway_routing_metadata as _extract_gateway_routing_metadata,
    find_gateway_metadata_payload as _find_gateway_metadata_payload,
    normalize_gateway_routing_metadata as _normalize_gateway_routing_metadata,
)
from api.streaming_gateway_notifications import register_streaming_gateway_notifications as _register_streaming_gateway_notifications
from api.streaming_goal import run_post_turn_goal_hook as _run_post_turn_goal_hook
from api.streaming_error_writeback import persist_streaming_error_message as _persist_streaming_error_message
from api.streaming_ephemeral import emit_ephemeral_done as _emit_ephemeral_done
from api.streaming_attachments import (
    IMAGE_MAGIC as _IMAGE_MAGIC,
    NATIVE_IMAGE_MAX_BYTES as _NATIVE_IMAGE_MAX_BYTES,
    attachment_name as _attachment_name,
    build_native_multimodal_message as _build_native_multimodal_message,
    is_valid_image as _is_valid_image,
    tag_matching_user_message_attachments as _tag_matching_user_message_attachments,
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
    persist_context_window_on_session as _persist_context_window_on_session,
)
from api.streaming_checkpoint import (
    start_periodic_checkpoint as _start_periodic_checkpoint,
    stop_checkpoint_thread as _stop_checkpoint_thread,
)
from api.streaming_tool_calls import (
    TOOL_RESULT_SNIPPET_MAX as _TOOL_RESULT_SNIPPET_MAX,
    extract_tool_calls_from_messages as _extract_tool_calls_from_messages,
    nearest_assistant_msg_idx as _nearest_assistant_msg_idx,
    strip_xml_tool_calls_from_assistant_messages as _strip_xml_tool_calls_from_assistant_messages,
    tool_result_snippet as _tool_result_snippet,
    truncate_tool_args as _truncate_tool_args,
)
from api.streaming_tool_bridge import StreamingToolEventBridge as _StreamingToolEventBridge
from api.streaming_agent_runtime import (
    agent_cache_api_key_sig as _agent_cache_api_key_sig,
    refresh_cached_agent_primary_runtime_snapshot as _refresh_cached_agent_primary_runtime_snapshot,
    refresh_cached_agent_runtime as _refresh_cached_agent_runtime,
)
from api.streaming_agent_cache import (
    get_agent_for_turn as _get_agent_for_turn,
)
from api.streaming_agent_config import (
    build_agent_kwargs as _build_agent_kwargs_impl,
    initialize_session_db as _initialize_session_db,
    load_agent_config_and_toolsets as _load_agent_config_and_toolsets,
    resolve_agent_constructor_settings as _resolve_agent_constructor_settings,
    resolve_agent_runtime_connection as _resolve_agent_runtime_connection,
)
from api.streaming_agent_status import make_agent_status_callback as _make_agent_status_callback
from api.streaming_event_sink import StreamingEventSink as _StreamingEventSink
from api.streaming_live_usage import LiveUsageTracker as _LiveUsageTracker
from api.streaming_metering import StreamingMeteringTicker as _StreamingMeteringTicker
from api.streaming_memory_lifecycle import mark_completed_turn_memory_lifecycle as _mark_completed_turn_memory_lifecycle
from api.streaming_output_bridge import StreamingOutputBridge as _StreamingOutputBridge
from api.streaming_process_notifications import (
    drain_webui_process_notifications as _drain_webui_process_notifications_impl,
    format_process_notification as _format_process_notification_impl,
    message_text_with_process_notifications as _message_text_with_process_notifications,
    mark_process_completion_consumed as _mark_process_completion_consumed_impl,
)
from api.streaming_product_turn import ProductTurnFinalizer as _ProductTurnFinalizer
from api.streaming_turn_journal import (
    append_assistant_started_turn_event as _append_assistant_started_turn_event,
    append_completed_turn_event as _append_completed_turn_event,
    append_interrupted_turn_event as _append_interrupted_turn_event,
    append_worker_started_turn_event as _append_worker_started_turn_event,
)
from api.streaming_terminal import (
    emit_completed_turn_done as _emit_completed_turn_done,
)
from api.streaming_turn_metadata import (
    apply_completed_turn_metadata as _apply_completed_turn_metadata,
    attach_reasoning_trace_to_last_assistant as _attach_reasoning_trace_to_last_assistant,
)
from api.streaming_usage import (
    apply_agent_token_usage_to_session as _apply_agent_token_usage_to_session,
    build_done_usage_payload as _build_done_usage_payload,
)
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
from api.streaming_title_writeback import prepare_completed_turn_title as _prepare_completed_turn_title
# Source-guard anchor: MiniMax title calls set reasoning_split in
# streaming_title_generation while streaming.py keeps the public wrappers.
from api.streaming_recovery import (
    attempt_credential_self_heal as _attempt_credential_self_heal_impl,
    last_resort_sync_from_core as _last_resort_sync_from_core_impl,
    materialize_pending_user_turn_before_error as _materialize_pending_user_turn_before_error_impl,
    rebuild_agent_for_credential_self_heal as _rebuild_agent_for_credential_self_heal,
)
from api.streaming_runtime_helpers import (
    WEBUI_VISIBLE_PROGRESS_PROMPT as _WEBUI_VISIBLE_PROGRESS_PROMPT_IMPL,
    aiagent_import_error_detail as _aiagent_import_error_detail_impl,
    apply_streaming_profile_process_env as _apply_streaming_profile_process_env,
    build_agent_thread_env as _build_agent_thread_env,
    clarify_timeout_seconds as _clarify_timeout_seconds_impl,
    discover_mcp_tools_for_profile as _discover_mcp_tools_for_profile,
    has_new_assistant_reply as _has_new_assistant_reply_impl,
    restore_agent_process_env as _restore_agent_process_env,
    resolve_streaming_profile_runtime as _resolve_streaming_profile_runtime,
    webui_clarify_callback as _webui_clarify_callback_impl,
    webui_ephemeral_system_prompt as _webui_ephemeral_system_prompt_impl,
)
from api.streaming_runtime_prompt import (
    build_workspace_system_message as _build_workspace_system_message,
    configure_agent_runtime_prompt as _configure_agent_runtime_prompt,
)
from api.streaming_compression import handle_context_compression_side_effects as _handle_context_compression_side_effects

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
        if _handle_preflight_cancel(cancel_event, s, _agent_lock, _finalize_cancelled_turn, _put_cancel, ephemeral=ephemeral):
            return

        # Resolve profile home for this agent run — use the session's own profile
        # (stamped at new_session() time from the client's S.activeProfile) so that
        # two concurrent tabs on different profiles don't clobber each other via the
        # process-level active-profile global.  Falls back gracefully.
        _profile_runtime = _resolve_streaming_profile_runtime(s)
        _profile_home = _profile_runtime.profile_home
        _profile_runtime_env = _profile_runtime.profile_runtime_env
        _resolved_profile_name = _profile_runtime.resolved_profile_name
        patch_skill_home_modules = _profile_runtime.patch_skill_home_modules
        
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
        _process_env_snapshot = _apply_streaming_profile_process_env(
            profile_runtime_env=_profile_runtime_env,
            workspace=str(s.workspace),
            session_id=session_id,
            profile_home=_profile_home,
            patch_skill_home_modules=patch_skill_home_modules,
            env_lock=_ENV_LOCK,
        )
        old_profile_env = _process_env_snapshot.profile_env_snapshot
        old_runtime_env = _process_env_snapshot.runtime_env_snapshot
        # Process env lock released — agent runs without holding it.
        # MCP discovery must run after the per-session HERMES_HOME mutation so
        # non-default profile MCP servers are loaded from the right config.
        _discover_mcp_tools_for_profile()

        _gateway_notifications = _register_streaming_gateway_notifications(
            session_id,
            put=put,
            logger=logger,
        )

        try:
            _self_healed = False  # (#1401) prevents infinite self-heal retries
            _live_tool_calls = []  # tool progress fallback when final messages omit tool IDs

            _output_bridge = _StreamingOutputBridge(
                stream_id=stream_id,
                session_id=session_id,
                partial_texts=STREAM_PARTIAL_TEXT,
                reasoning_texts=STREAM_REASONING_TEXT,
                usage_snapshot=_live_usage_snapshot,
                put=put,
            )

            # Pre-initialise the activity counter here so on_tool (which
            # closes over it) never captures an unbound name even if this
            # block is reordered later (Issue #765).
            _checkpoint_activity = [0]

            _tool_bridge = _StreamingToolEventBridge(
                stream_id=stream_id,
                session_id=session_id,
                live_tool_calls=_live_tool_calls,
                shared_live_tool_calls=STREAM_LIVE_TOOL_CALLS,
                checkpoint_activity=_checkpoint_activity,
                seen_tool_call_ids=_live_prompt_estimate_seen_ids,
                put=put,
                emit_reasoning=_output_bridge.on_reasoning,
                usage_snapshot=_live_usage_snapshot,
                bump_live_prompt_estimate=_bump_live_prompt_estimate,
                tool_result_snippet=_tool_result_snippet,
                logger=logger,
            )

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

            # Build kwargs defensively — guard newer params so the WebUI
            # degrades gracefully when run against an older hermes-agent build.
            # (fixes: TypeError: AIAgent.__init__() got an unexpected keyword
            # argument 'credential_pool' — issue #772)
            _agent_constructor = _resolve_agent_constructor_settings(_AIAgent, _cfg)
            _agent_params = _agent_constructor.agent_params
            _fallback_resolved = _agent_constructor.fallback_resolved
            _max_iterations_cfg = _agent_constructor.max_iterations
            _max_tokens_cfg = _agent_constructor.max_tokens
            _reasoning_config = _agent_constructor.reasoning_config

            _agent_kwargs = _build_agent_kwargs_impl(
                agent_params=_agent_params,
                model=resolved_model,
                provider=resolved_provider,
                base_url=resolved_base_url,
                api_key=resolved_api_key,
                enabled_toolsets=_toolsets,
                fallback_model=_fallback_resolved,
                session_id=session_id,
                session_db=_session_db,
                stream_delta_callback=_output_bridge.on_token,
                reasoning_callback=_output_bridge.on_reasoning,
                tool_progress_callback=_tool_bridge.on_tool,
                clarify_callback=(
                    lambda question, choices: _webui_clarify_callback_impl(
                        question,
                        choices,
                        session_id,
                        cancel_event,
                        _clarify_timeout_seconds,
                    )
                ),
                interim_assistant_callback=_output_bridge.on_interim_assistant,
                tool_start_callback=_tool_bridge.on_tool_start,
                tool_complete_callback=_tool_bridge.on_tool_complete,
                status_callback=_agent_status_callback,
                max_iterations=_max_iterations_cfg,
                max_tokens=_max_tokens_cfg,
                reasoning_config=_reasoning_config,
                runtime=_rt,
            )

            _agent_for_turn = _get_agent_for_turn(
                session_id=session_id,
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
                logger=logger,
            )
            agent = _agent_for_turn.agent
            _agent_sig = _agent_for_turn.agent_sig

            # Store agent instance for cancel/interrupt propagation
            if not _register_agent_instance_or_cancel(
                stream_id,
                agent,
                s,
                agent_lock=_agent_lock,
                finalize_cancelled_turn_fn=_finalize_cancelled_turn,
                put_cancel_fn=_put_cancel,
                ephemeral=ephemeral,
                logger=logger,
            ):
                return

            # Prepend workspace context so the agent always knows which directory
            # to use for file operations, regardless of session age or AGENTS.md defaults.
            workspace_ctx = _workspace_context_prefix(str(s.workspace))
            workspace_system_msg = _build_workspace_system_message(s.workspace)
            # Pass WebUI-only runtime guidance via ephemeral_system_prompt
            # (agent's own mechanism). This preserves any selected personality
            # while making long tool runs emit real user-visible interim text
            # through interim_assistant_callback instead of frontend guesses.
            _configure_agent_runtime_prompt(
                agent,
                config=_cfg,
                personality_name=getattr(s, 'personality', None),
                product_context=product_context,
                webui_ephemeral_system_prompt=_webui_ephemeral_system_prompt,
                logger=logger,
            )
            _turn_start = _capture_turn_start_snapshot(s, agent, msg_text)
            _turn_started_at = _turn_start.started_at
            _previous_messages = _turn_start.previous_messages
            _previous_context_messages = _turn_start.previous_context_messages
            _pre_compression_count = _turn_start.pre_compression_count

            # Persist the user message BEFORE streaming starts so it's durable even if
            # the server crashes before the first checkpoint fires (every 15s).
            with _agent_lock:
                s.save(touch_updated_at=True, skip_index=False)

            _checkpoint_runner = _start_periodic_checkpoint(
                s,
                agent_lock=_agent_lock,
                checkpoint_activity=_checkpoint_activity,
                session_id=session_id,
                logger=logger,
            )
            _checkpoint_stop = _checkpoint_runner.stop_event
            _ckpt_thread = _checkpoint_runner.thread

            _process_notifications = _drain_webui_process_notifications(session_id)
            _agent_msg_text = _message_text_with_process_notifications(msg_text, _process_notifications)
            user_message = _build_native_multimodal_message(workspace_ctx, _agent_msg_text, attachments, workspace, cfg=_cfg)
            result = agent.run_conversation(
                user_message=user_message,
                system_message=workspace_system_msg,
                conversation_history=_sanitize_messages_for_api(_previous_context_messages, cfg=_cfg),
                task_id=session_id,
                persist_user_message=msg_text,
            )
            if _handle_post_run_cancel(
                cancel_event,
                s,
                stream_id,
                _agent_lock,
                _finalize_cancelled_turn,
                _put_cancel,
                ephemeral=ephemeral,
                checkpoint_stop=_checkpoint_stop,
                checkpoint_thread=_ckpt_thread,
                logger=logger,
            ):
                return
            # ── Ephemeral mode (/btw): deliver answer, skip persistence, cleanup ──
            if ephemeral:
                _emit_ephemeral_done(
                    result,
                    session_id=session_id,
                    session_path=s.path,
                    checkpoint_stop=_checkpoint_stop,
                    put=put,
                )
                return  # skip all normal persistence for ephemeral sessions
            _stop_checkpoint_thread(_checkpoint_stop, _ckpt_thread)
            if _handle_post_run_cancel(
                cancel_event,
                s,
                stream_id,
                _agent_lock,
                _finalize_cancelled_turn,
                _put_cancel,
                ephemeral=False,
                logger=logger,
            ):
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
                if cancel_event.is_set():
                    _finalize_cancelled_turn(s, ephemeral=False)
                    _append_interrupted_turn_event(s.session_id, stream_id, logger=logger)
                    _put_cancel()
                    return
                _result_messages = _apply_agent_result_to_session(
                    s,
                    _previous_messages,
                    _previous_context_messages,
                    result.get('messages'),
                    msg_text,
                    strip_xml_tool_calls_fn=_strip_xml_tool_calls_from_assistant_messages,
                )

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
                # token_sent tracks whether the output bridge streamed visible text.
                if not _assistant_added and not _output_bridge.token_sent:
                    if cancel_event.is_set():
                        _finalize_cancelled_turn(s, ephemeral=ephemeral)
                        if not ephemeral:
                            _append_interrupted_turn_event(s.session_id, stream_id, logger=logger)
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
                            _rebuilt = _rebuild_agent_for_credential_self_heal(
                                agent_factory=_AIAgent,
                                agent_kwargs=_agent_kwargs,
                                agent_params=_agent_params,
                                heal_runtime=_heal_rt,
                                resolved_model=resolved_model,
                                resolved_provider=resolved_provider,
                                resolved_base_url=resolved_base_url,
                                custom_provider_resolver=resolve_custom_provider_connection,
                                session_id=session_id,
                                stream_id=stream_id,
                                agent_instances=AGENT_INSTANCES,
                                streams_lock=STREAMS_LOCK,
                                ephemeral=ephemeral,
                                agent_sig=_agent_sig,
                            )
                            _rt = _rebuilt.runtime
                            resolved_api_key = _rebuilt.resolved_api_key
                            resolved_provider = _rebuilt.resolved_provider
                            resolved_base_url = _rebuilt.resolved_base_url
                            _agent_kwargs = _rebuilt.agent_kwargs
                            agent = _rebuilt.agent
                            # Retry the conversation once with fresh credentials
                            _self_healed = True
                            _output_bridge.token_sent = False
                            try:
                                _heal_result = agent.run_conversation(
                                    user_message=user_message,
                                    system_message=workspace_system_msg,
                                    conversation_history=_sanitize_messages_for_api(_previous_context_messages, cfg=_cfg),
                                    task_id=session_id,
                                    persist_user_message=msg_text,
                                )
                                _heal_all_msgs = _heal_result.get('messages') or []
                                _heal_ok = _has_new_assistant_reply(_heal_all_msgs, _prev_len) or _output_bridge.token_sent
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
                                _result_messages = _apply_agent_result_to_session(
                                    s,
                                    _previous_messages,
                                    _previous_context_messages,
                                    result.get('messages'),
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
                        # Persist the error so it survives page reload.
                        # _error=True ensures _sanitize_messages_for_api excludes it from
                        # subsequent API calls so the LLM never sees its own error as prior context.
                        _persist_streaming_error_message(
                            s,
                            label=_err_label,
                            message=_error_payload.get("message") or _err_label,
                            error_type=_err_type,
                            hint=_err_hint,
                            details=_error_payload.get('details'),
                            always_include_hint=True,
                            materialize_pending_user_turn=_materialize_pending_user_turn_before_error,
                            logger=logger,
                        )
                        # Legacy #373 source tests and clients look for the
                        # no_response type; #1765 keeps that type but improves
                        # the catch-all label, hint, and provider details.
                        return  # apperror already closes the stream on the client side

                # ── Handle context compression side effects ──
                # If compression fired inside run_conversation, the agent may have
                # rotated its session_id. Detect and fix the mismatch so the WebUI
                # continues writing to the correct session file.
                from api.compression_anchor import visible_messages_for_anchor
                from api.config import SESSION_AGENT_CACHE, SESSION_AGENT_CACHE_LOCK
                _handle_context_compression_side_effects(
                    s,
                    agent,
                    original_session_id=session_id,
                    resolved_profile_name=_resolved_profile_name,
                    agent_lock=_agent_lock,
                    pre_compression_count=_pre_compression_count,
                    preserve_pre_compression_snapshot=_preserve_pre_compression_snapshot,
                    sessions_lock=LOCK,
                    sessions=SESSIONS,
                    session_agent_locks=SESSION_AGENT_LOCKS,
                    session_agent_locks_lock=SESSION_AGENT_LOCKS_LOCK,
                    session_agent_cache=SESSION_AGENT_CACHE,
                    session_agent_cache_lock=SESSION_AGENT_CACHE_LOCK,
                    visible_messages_for_anchor=visible_messages_for_anchor,
                    compression_anchor_message_key=_compression_anchor_message_key,
                    compact_summary_text=_compact_summary_text,
                    compression_summary_from_messages=_compression_summary_from_messages,
                    put=put,
                    usage_snapshot=_live_usage_snapshot,
                    logger=logger,
                )

                _title_plan = _prepare_completed_turn_title(
                    s,
                    title_from_fn=title_from,
                    is_provisional_title=_is_provisional_title,
                    looks_invalid_generated_title=_looks_invalid_generated_title,
                    first_exchange_snippets=_first_exchange_snippets,
                )
                _token_usage = _apply_agent_token_usage_to_session(s, agent)
                output_tokens = _token_usage.output_tokens
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
                _tag_matching_user_message_attachments(s.messages, msg_text, attachments)
                # Persist reasoning trace in the session so it survives reload.
                # Must run BEFORE s.save() — otherwise the mutation lives only in
                # memory until the next turn's save, and the last-turn thinking card
                # is lost when the user reloads immediately after a response.
                _attach_reasoning_trace_to_last_assistant(s.messages, _output_bridge.reasoning_text)
                _turn_metadata = _apply_completed_turn_metadata(
                    s,
                    agent,
                    result,
                    turn_started_at=_turn_started_at,
                    output_tokens=output_tokens,
                    requested_model=resolved_model or model,
                    requested_provider=resolved_provider,
                    extract_gateway_routing_metadata=_extract_gateway_routing_metadata,
                )
                _persist_context_window_on_session(
                    s,
                    agent,
                    _cfg,
                    resolved_model=resolved_model or '',
                    resolved_provider=resolved_provider or '',
                )
                if not ephemeral and s.messages:
                    _append_assistant_started_turn_event(
                        s.session_id,
                        stream_id,
                        s.messages,
                        logger=logger,
                    )
                if cancel_event.is_set():
                    _finalize_cancelled_turn(s, ephemeral=False)
                    _append_interrupted_turn_event(s.session_id, stream_id, logger=logger)
                    _put_cancel()
                    return
                s.save()
                if cancel_event.is_set():
                    _finalize_cancelled_turn(s, ephemeral=False)
                    _append_interrupted_turn_event(s.session_id, stream_id, logger=logger)
                    _put_cancel()
                    return
                if not ephemeral:
                    _append_completed_turn_event(s.session_id, stream_id, s.messages, logger=logger)
                if not ephemeral:
                    # Keep this marker inside the per-session writeback lock so
                    # completed-turn ordering stays aligned with session save/journal.
                    _mark_completed_turn_memory_lifecycle(s.session_id, agent, logger=logger)
            # (reasoning trace already attached + saved above, before s.save())
            _emit_completed_turn_done(
                s,
                original_session_id=session_id,
                token_usage=_token_usage,
                turn_metadata=_turn_metadata,
                config=_cfg,
                resolved_model=resolved_model or '',
                resolved_provider=resolved_provider or '',
                agent=agent,
                profile_home=_profile_home,
                goal_related=goal_related,
                put=put,
                pending_goal_continuation=PENDING_GOAL_CONTINUATION,
                tool_calls=tool_calls,
                title_plan=_title_plan,
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
            _metering_ticker.stop()
            # Unregister gateway callbacks and unblock any threads still
            # waiting on approval/clarify prompts.
            _gateway_notifications.unregister(session_id)
            _restore_agent_process_env(
                old_profile_env,
                old_runtime_env,
                env_lock=_ENV_LOCK,
            )

    except Exception as e:
        print('[webui] stream error:\n' + traceback.format_exc(), flush=True)
        err_str = _sanitize_provider_error_text(str(e))
        _exc_lower = err_str.lower()
        _classification = _classify_provider_error(err_str, e)
        if _handle_exception_cancel(
            cancel_event,
            s,
            stream_id,
            _agent_lock,
            _finalize_cancelled_turn,
            _put_cancel,
            ephemeral=ephemeral,
            checkpoint_stop=_checkpoint_stop,
            checkpoint_thread=_ckpt_thread,
            logger=logger,
        ):
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
                    _rebuilt = _rebuild_agent_for_credential_self_heal(
                        agent_factory=_AIAgent,
                        agent_kwargs=dict(_agent_kwargs) if '_agent_kwargs' in dir() else {},
                        agent_params=_agent_params,
                        heal_runtime=_heal_rt,
                        resolved_model=resolved_model,
                        resolved_provider=resolved_provider,
                        resolved_base_url=resolved_base_url,
                        custom_provider_resolver=resolve_custom_provider_connection,
                        session_id=session_id,
                        stream_id=stream_id,
                        agent_instances=AGENT_INSTANCES,
                        streams_lock=STREAMS_LOCK,
                        ephemeral=ephemeral,
                        agent_sig=_agent_sig,
                    )
                    _rt = _rebuilt.runtime
                    resolved_api_key = _rebuilt.resolved_api_key
                    resolved_provider = _rebuilt.resolved_provider
                    resolved_base_url = _rebuilt.resolved_base_url
                    _agent_kwargs = _rebuilt.agent_kwargs
                    _heal_agent = _rebuilt.agent
                    # Retry the conversation
                    if _output_bridge is not None:
                        _output_bridge.token_sent = False
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
                            _stop_checkpoint_thread(_checkpoint_stop, _ckpt_thread)
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
                                _result_messages = _apply_agent_result_to_session(
                                    s,
                                    _previous_messages,
                                    _previous_context_messages,
                                    _heal_result.get('messages'),
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
            _stop_checkpoint_thread(_checkpoint_stop, _ckpt_thread)
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
                _persist_streaming_error_message(
                    s,
                    label=_exc_label,
                    message=_error_payload.get("message") or err_str,
                    error_type=_exc_type,
                    hint=_exc_hint,
                    details=_error_payload.get('details'),
                    materialize_pending_user_turn=_materialize_pending_user_turn_before_error,
                    logger=logger,
                )
                if not ephemeral:
                    _append_interrupted_turn_event(
                        s.session_id,
                        stream_id,
                        reason=_exc_type,
                        logger=logger,
                    )
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
        _stop_checkpoint_thread(_checkpoint_stop, _ckpt_thread)
        if (s is not None
                and getattr(s, 'active_stream_id', None) == stream_id
                and getattr(s, 'pending_user_message', None)):
            update_active_run(stream_id, phase="finalizing")
            _last_resort_sync_from_core(s, stream_id, _agent_lock)
        _finalize_product_turn(failed=True)
        _clear_thread_env()  # TD1: always clear thread-local context
        _cleanup_stream_registries(
            stream_id,
            streams=STREAMS,
            cancel_flags=CANCEL_FLAGS,
            agent_instances=AGENT_INSTANCES,
            partial_text=STREAM_PARTIAL_TEXT,
            reasoning_text=STREAM_REASONING_TEXT,
            live_tool_calls=STREAM_LIVE_TOOL_CALLS,
            goal_related=STREAM_GOAL_RELATED,
            last_event_ids=STREAM_LAST_EVENT_ID,
            unregister_active_run=unregister_active_run,
            streams_lock=STREAMS_LOCK,
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

    _cancel_snapshot = _capture_cancel_stream_snapshot_impl(
        stream_id,
        live_config=_live_config,
        streams=STREAMS,
        cancel_flags=CANCEL_FLAGS,
        agent_instances=AGENT_INSTANCES,
        partial_texts=STREAM_PARTIAL_TEXT,
        reasoning_texts=STREAM_REASONING_TEXT,
        live_tool_calls=STREAM_LIVE_TOOL_CALLS,
        streams_lock=STREAMS_LOCK,
        logger=logger,
    )
    if _cancel_snapshot is None:
        return False
    q = _cancel_snapshot.queue
    _emit_cancel_event = True
    _cancel_session_id = _cancel_snapshot.session_id

    # Session cleanup outside STREAMS_LOCK to preserve lock ordering.
    # Acquire the per-session _agent_lock too, mirroring every other session
    # writer (streaming success/error paths, periodic checkpoint, POST endpoints)
    # so the cancel-path mutation races neither the checkpoint thread nor
    # concurrent undo/retry calls.
    if _cancel_session_id:
        with _get_session_agent_lock(_cancel_session_id):
            try:
                _cs = get_session(_cancel_session_id)
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
                _persist_cancel_stream_writeback_impl(
                    _cs,
                    partial_text=_cancel_snapshot.partial_text,
                    reasoning_text=_cancel_snapshot.reasoning_text,
                    tool_calls=_cancel_snapshot.tool_calls,
                    cancelled_turn_content_fn=_cancelled_turn_content,
                    logger=logger,
                    session_id=_cancel_session_id,
                )
            except Exception:
                logger.debug("Failed to clear session state on cancel for %s", _cancel_session_id)

    if _emit_cancel_event and q:
        try:
            q.put_nowait(('cancel', {'message': 'Cancelled by user'}))
        except Exception:
            logger.debug("Failed to put cancel event to queue")

    return True

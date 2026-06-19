"""
Hermes Web UI -- SSE streaming engine and agent thread runner.
Includes Sprint 10 cancel support via CANCEL_FLAGS.
"""
import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

from api.config import (
    get_config,
    STREAMS, STREAMS_LOCK, CANCEL_FLAGS, AGENT_INSTANCES, STREAM_PARTIAL_TEXT,
    STREAM_REASONING_TEXT, STREAM_LIVE_TOOL_CALLS,
    STREAM_GOAL_RELATED, PENDING_GOAL_CONTINUATION,
    LOCK, SESSIONS, SESSION_DIR,
    _get_session_agent_lock, _set_thread_env,
    update_active_run,
    SESSION_AGENT_LOCKS, SESSION_AGENT_LOCKS_LOCK,
    resolve_model_provider,
    resolve_custom_provider_connection,
    model_with_provider_context,
    load_settings,
)
from api.helpers import redact_session_data, _redact_text
from api.metering import meter
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
from api.streaming_cleanup import (
    finalize_streaming_run_attempt as _finalize_streaming_run_attempt,
    finalize_webui_streaming_worker_exit as _finalize_streaming_worker_exit,
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
from api.streaming_goal import run_post_turn_goal_hook as _run_post_turn_goal_hook
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
from api.streaming_agent_turn_setup import prepare_streaming_agent_turn_setup as _prepare_streaming_agent_turn_setup
from api.streaming_process_notifications import (
    drain_webui_process_notifications as _drain_webui_process_notifications_impl,
    format_process_notification as _format_process_notification_impl,
    message_text_with_process_notifications as _message_text_with_process_notifications,
    mark_process_completion_consumed as _mark_process_completion_consumed_impl,
)
from api.streaming_turn_journal import (
    append_interrupted_turn_event as _append_interrupted_turn_event,
)
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
)
from api.streaming_title_facade import (
    is_provisional_title_from_facade as _is_provisional_title,
    maybe_schedule_title_refresh_from_facade as _maybe_schedule_title_refresh,
    put_title_status_from_facade as _put_title_status,
    run_background_title_refresh_from_facade as _run_background_title_refresh,
    run_background_title_update_from_facade as _run_background_title_update,
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
    webui_clarify_callback as _webui_clarify_callback_impl,
    webui_ephemeral_system_prompt as _webui_ephemeral_system_prompt_impl,
)
from api.streaming_runtime_prompt import (
    build_workspace_system_message as _build_workspace_system_message,
    configure_agent_runtime_prompt as _configure_agent_runtime_prompt,
)
from api.streaming_worker_exception_facade import handle_streaming_exception_from_facade as _handle_streaming_exception
from api.streaming_worker_context import initialize_streaming_worker_context as _initialize_streaming_worker_context
from api.streaming_worker_pipeline_facade import run_streaming_turn_pipeline_from_facade as _run_streaming_turn_pipeline
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


_is_quota_error_text = _is_quota_error_text_impl


def _clarify_timeout_seconds(default: int = 120) -> int:
    return _clarify_timeout_seconds_impl(get_config, default)


_WEBUI_VISIBLE_PROGRESS_PROMPT = _WEBUI_VISIBLE_PROGRESS_PROMPT_IMPL

_webui_ephemeral_system_prompt = _webui_ephemeral_system_prompt_impl


_has_new_assistant_reply = _has_new_assistant_reply_impl


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


_session_has_cancel_marker = _session_has_cancel_marker_impl


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


_aiagent_import_error_detail = _aiagent_import_error_detail_impl
from api.models import get_session, title_from
from api.workspace import set_last_workspace

# Fields that are safe to send to LLM provider APIs.
# Everything else (attachments, timestamp, _ts, etc.) is display-only
# metadata added by the webui and must be stripped before the API call.
_API_SAFE_MSG_KEYS = _API_SAFE_MSG_KEYS_IMPL


_format_process_notification = _format_process_notification_impl


def _mark_process_completion_consumed(process_registry, process_id: str) -> None:
    _mark_process_completion_consumed_impl(process_registry, process_id, logger=logger)


def _drain_webui_process_notifications(session_id: str) -> list[str]:
    return _drain_webui_process_notifications_impl(session_id, logger=logger)


_get_title_refresh_interval = _get_title_refresh_interval_impl


_is_minimax_route = _is_minimax_route_impl


_aux_title_configured = _aux_title_configured_impl


_aux_title_timeout = _aux_title_timeout_impl


_title_completion_budget = _title_completion_budget_impl


_title_retry_completion_budget = _title_retry_completion_budget_impl


_title_retry_status = _title_retry_status_impl


_title_should_skip_remaining_attempts = _title_should_skip_remaining_attempts_impl


_safe_obj_value = _safe_obj_value_impl


_safe_text_value = _safe_text_value_impl


_extract_title_response = _extract_title_response_impl


generate_title_raw_via_aux = _generate_title_raw_via_aux_impl


generate_title_raw_via_agent = _generate_title_raw_via_agent_impl


_generate_llm_session_title_for_agent = _generate_llm_session_title_for_agent_impl


_generate_llm_session_title_via_aux = _generate_llm_session_title_via_aux_impl


def _preserve_pre_compression_snapshot(s, old_sid: str) -> None:
    return _preserve_pre_compression_snapshot_impl(
        s,
        old_sid,
        session_dir=SESSION_DIR,
        logger=logger,
    )

_strip_native_image_parts_from_content = _strip_native_image_parts_from_content_impl


_sanitize_messages_for_api = _sanitize_messages_for_api_impl


_api_safe_message_positions = _api_safe_message_positions_impl


_restore_reasoning_metadata = _restore_reasoning_metadata_impl


_session_context_messages = _session_context_messages_impl


_message_identity = _message_identity_impl


_messages_have_prefix = _messages_have_prefix_impl


_is_context_compression_marker = _is_context_compression_marker_impl


_compact_summary_text = _compact_summary_text_impl


_compression_anchor_message_key = _compression_anchor_message_key_impl


_compression_summary_from_messages = _compression_summary_from_messages_impl


_find_current_user_turn = _find_current_user_turn_impl


_drop_checkpointed_current_user_from_context = _drop_checkpointed_current_user_from_context_impl


_normalize_fresh_chat_text = _normalize_fresh_chat_text_impl


_is_casual_fresh_chat_message = _is_casual_fresh_chat_message_impl


_has_task_resume_compaction_marker = _has_task_resume_compaction_marker_impl


_context_messages_for_new_turn = _context_messages_for_new_turn_impl


def _stream_writeback_is_current(session, stream_id):
    """Return True only while a worker still owns the session writeback.

    cancel_stream() intentionally clears ``active_stream_id`` early so the UI can
    accept a follow-up turn while the old worker is unwinding. That old worker
    must not later persist its stale result over the newer transcript.
    """
    return bool(stream_id) and getattr(session, 'active_stream_id', None) == stream_id


_merge_display_messages_after_agent_result = _merge_display_messages_after_agent_result_impl


_assistant_reply_added_after_current_turn = _assistant_reply_added_after_current_turn_impl


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
    agent = None
    _agent_setup_runtime_vars = {}
    _worker_context = _initialize_streaming_worker_context(
        stream_id=stream_id,
        session_id=session_id,
        workspace=workspace,
        model=model,
        model_provider=model_provider,
        ephemeral=ephemeral,
        product_context=product_context,
        streams=STREAMS,
        get_session=lambda: get_session(session_id),
        get_agent=lambda: agent,
        logger=logger,
    )
    if _worker_context.should_return:
        return
    _run_state = _worker_context.run_state
    cancel_event = _worker_context.cancel_event
    put = _worker_context.put
    _finalize_product_turn = _worker_context.finalize_product_turn
    _put_cancel = _worker_context.put_cancel
    s = None
    _rt = {}
    _output_bridge = None
    old_profile_env = {}
    old_runtime_env = {}

    # MCP discovery moved to AFTER the per-profile HERMES_HOME mutation below
    # (was here at v0.51.30) — the previous placement always read the default
    # profile's mcp_servers because os.environ['HERMES_HOME'] hadn't been
    # rewritten yet.  See https://github.com/nesquena/hermes-webui/issues/1968.

    # Initialised here (before any code that may raise) so the outer `finally`
    # block can safely check `if _checkpoint_stop is not None` even when an
    # exception fires before the checkpoint thread is created (Issue #765).
    _checkpoint_state = {'stop': None, 'thread': None}
    _agent_lock = None
    _checkpoint_stop = None
    _ckpt_thread = None
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
            _agent_setup = _prepare_streaming_agent_turn_setup(
                stream_id=stream_id,
                session_id=session_id,
                session=s,
                model=model,
                provider_context=provider_context,
                profile_home=_profile_home,
                run_state=_run_state,
                put=put,
                tool_result_snippet=_tool_result_snippet,
                cancel_event=cancel_event,
                agent_lock=_agent_lock,
                ephemeral=ephemeral,
                clarify_timeout_seconds=_clarify_timeout_seconds,
                webui_clarify_callback=_webui_clarify_callback_impl,
                finalize_cancelled_turn=_finalize_cancelled_turn,
                put_cancel=_put_cancel,
                get_ai_agent=_get_ai_agent,
                aiagent_import_error_detail_fn=_aiagent_import_error_detail,
                resolve_model_provider_fn=resolve_model_provider,
                model_with_provider_context_fn=model_with_provider_context,
                custom_provider_resolver=resolve_custom_provider_connection,
                logger=logger,
                runtime_state=_agent_setup_runtime_vars,
            )
            if not _agent_setup.should_continue:
                return
            agent = _agent_setup.agent

            _turn_pipeline_result = _run_streaming_turn_pipeline(
                agent_setup=_agent_setup,
                session=s,
                session_id=session_id,
                stream_id=stream_id,
                msg_text=msg_text,
                attachments=attachments,
                workspace=workspace,
                product_context=product_context,
                model=model,
                profile_home=_profile_home,
                resolved_profile_name=_resolved_profile_name,
                run_state=_run_state,
                cancel_event=cancel_event,
                agent_lock=_agent_lock,
                ephemeral=ephemeral,
                goal_related=goal_related,
                put=put,
                finalize_product_turn=_finalize_product_turn,
                put_cancel=_put_cancel,
                runtime_state=_agent_setup_runtime_vars,
                checkpoint_state=_checkpoint_state,
            )
            _checkpoint_stop = _turn_pipeline_result.checkpoint_stop
            _ckpt_thread = _turn_pipeline_result.checkpoint_thread
            result = _turn_pipeline_result.result
            _rt = _turn_pipeline_result.runtime
            resolved_api_key = _turn_pipeline_result.resolved_api_key
            resolved_provider = _turn_pipeline_result.resolved_provider
            resolved_base_url = _turn_pipeline_result.resolved_base_url
            _agent_kwargs = _turn_pipeline_result.agent_kwargs
            agent = _turn_pipeline_result.agent
            _self_healed = _turn_pipeline_result.self_healed
            if _turn_pipeline_result.should_return:
                return
        finally:
            _finalize_streaming_run_attempt(
                run_state=_run_state,
                gateway_notifications=_gateway_notifications,
                session_id=session_id,
                profile_env_snapshot=old_profile_env,
                runtime_env_snapshot=old_runtime_env,
                env_lock=_ENV_LOCK,
            )

    except Exception as e:
        _checkpoint_stop = _checkpoint_state.get('stop') or _checkpoint_stop
        _ckpt_thread = _checkpoint_state.get('thread') or _ckpt_thread
        _exception_runtime_vars = dict(locals())
        _exception_runtime_vars.update(_agent_setup_runtime_vars)
        _exception_result = _handle_streaming_exception(
            e,
            runtime_vars=_exception_runtime_vars,
            self_healed=locals().get('_self_healed', False),
            session=s,
            stream_id=stream_id,
            session_id=session_id,
            cancel_event=cancel_event,
            agent_lock=_agent_lock,
            checkpoint_stop=_checkpoint_stop,
            checkpoint_thread=_ckpt_thread,
            ephemeral=ephemeral,
            put_cancel=_put_cancel,
            finalize_product_turn=_finalize_product_turn,
            put=put,
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
        _checkpoint_stop = _checkpoint_state.get('stop') or _checkpoint_stop
        _ckpt_thread = _checkpoint_state.get('thread') or _ckpt_thread
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

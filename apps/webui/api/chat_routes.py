"""Chat route helper functions."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Callable

logger = logging.getLogger(__name__)


def is_default_or_empty_session_title(title) -> bool:
    return str(title or "").strip() in ("", "Untitled", "New Chat")


def provisional_title_from_prompt(prompt: str, fallback: str = "Untitled", *, title_from_fn: Callable) -> str:
    text = str(prompt or "").strip()
    if not text:
        return fallback
    return title_from_fn([{"role": "user", "content": text}], fallback) or fallback


def product_task_title_from_request(body: dict) -> str:
    raw = body.get("product_task_title") or body.get("productTaskTitle") or ""
    title = " ".join(str(raw or "").split()).strip()
    if not title:
        return ""
    return title[:80]


def session_toolsets_from_request(
    body: dict,
    *,
    resolve_cli_toolsets_fn: Callable[[], list[str]],
    normalize_product_toolsets_fn: Callable,
) -> list[str] | None:
    raw = body.get("enabled_toolsets")
    if raw is None:
        raw = body.get("enabledToolsets")
    if raw is None:
        raw = body.get("toolsets")
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        return None
    available = set(resolve_cli_toolsets_fn())
    return [name for name in normalize_product_toolsets_fn(raw) if name in available]


def normalize_chat_attachments(raw_attachments):
    """Normalize attachment payloads from the browser."""
    normalized = []
    if not isinstance(raw_attachments, list):
        return normalized
    for item in raw_attachments:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("filename") or "").strip()
            path = str(item.get("path") or "").strip()
            mime = str(item.get("mime") or "").strip()
            att = {"name": name or path, "path": path, "mime": mime}
            size = item.get("size")
            if isinstance(size, int):
                att["size"] = size
            is_image = item.get("is_image")
            if isinstance(is_image, bool):
                att["is_image"] = is_image
            normalized.append(att)
        else:
            value = str(item).strip()
            if value:
                normalized.append({"name": value, "path": "", "mime": ""})
    return normalized


def handle_chat_sync(
    handler,
    body,
    *,
    get_session_fn: Callable,
    resolve_trusted_workspace_fn: Callable,
    json_response_fn: Callable,
    bad_response_fn: Callable,
    snapshot_product_fn: Callable,
    session_lock_fn: Callable,
    resolve_session_model_state_fn: Callable,
    chat_lock,
    model_with_provider_context_fn: Callable,
    resolve_cli_toolsets_fn: Callable[[], list[str]],
    get_config_fn: Callable,
    title_from_fn: Callable,
):
    """Fallback synchronous chat endpoint (POST /api/chat). Not used by frontend."""
    s = get_session_fn(body["session_id"])
    msg = str(body.get("message", "")).strip()
    if not msg:
        return json_response_fn(handler, {"error": "empty message"}, status=400)
    try:
        workspace = str(resolve_trusted_workspace_fn(body.get("workspace") or s.workspace))
    except ValueError as e:
        return bad_response_fn(handler, str(e))

    product_context = None
    from api.product_context import product_context_request_body

    product_body = product_context_request_body(body, s, msg)
    if product_body.get("product_id") or product_body.get("productId"):
        try:
            from api.product_context import product_context_from_request

            product_context = product_context_from_request(product_body, workspace=workspace)
        except ValueError as e:
            return bad_response_fn(handler, str(e), status=400)
        if product_context and product_context["scope"] in {"product_init", "product_builder"}:
            try:
                snapshot_product_fn(
                    product_context["id"],
                    reason=f"{product_context['scope']}: {product_context.get('intent') or ''}"[:240],
                )
            except Exception:
                logger.debug("Failed to snapshot product before sync builder turn", exc_info=True)

    with session_lock_fn(s.session_id):
        s.workspace = workspace
        model, model_provider = resolve_session_model_state_fn(
            body.get("model") or s.model,
            body.get("model_provider") if "model_provider" in body else getattr(s, "model_provider", None),
        )[:2]
        s.model = model
        s.model_provider = model_provider

    from api.streaming import _ENV_LOCK

    with _ENV_LOCK:
        old_cwd = os.environ.get("TERMINAL_CWD")
        os.environ["TERMINAL_CWD"] = str(workspace)
        old_exec_ask = os.environ.get("HERMES_EXEC_ASK")
        old_session_key = os.environ.get("HERMES_SESSION_KEY")
        os.environ["HERMES_EXEC_ASK"] = "1"
        os.environ["HERMES_SESSION_KEY"] = s.session_id
    try:
        from run_agent import AIAgent

        with chat_lock:
            from api.config import (
                resolve_model_provider,
                resolve_custom_provider_connection,
            )

            _model, _provider, _base_url = resolve_model_provider(
                model_with_provider_context_fn(s.model, getattr(s, "model_provider", None))
            )
            _api_key = None
            try:
                from api.oauth import resolve_runtime_provider_with_anthropic_env_lock
                from hermes_cli.runtime_provider import resolve_runtime_provider

                _rt = resolve_runtime_provider_with_anthropic_env_lock(
                    resolve_runtime_provider,
                    requested=_provider,
                )
                _api_key = _rt.get("api_key")
                if not _provider:
                    _provider = _rt.get("provider")
                if not _base_url:
                    _base_url = _rt.get("base_url")
            except Exception as _e:
                print(
                    f"[webui] WARNING: resolve_runtime_provider failed: {_e}",
                    flush=True,
                )
            if isinstance(_provider, str) and _provider.startswith("custom:"):
                _cp_key, _cp_base = resolve_custom_provider_connection(_provider)
                if not _api_key and _cp_key:
                    _api_key = _cp_key
                if not _base_url and _cp_base:
                    _base_url = _cp_base
            agent = AIAgent(
                model=_model,
                provider=_provider,
                base_url=_base_url,
                api_key=_api_key,
                platform="webui",
                quiet_mode=True,
                enabled_toolsets=resolve_cli_toolsets_fn(),
                session_id=s.session_id,
            )
            from api.streaming import (
                _merge_display_messages_after_agent_result,
                _restore_reasoning_metadata,
                _sanitize_messages_for_api,
                _context_messages_for_new_turn,
                _workspace_context_prefix,
                _webui_ephemeral_system_prompt,
            )

            _product_prompt = ""
            if product_context:
                try:
                    from api.product_context import product_ephemeral_prompt

                    _product_prompt = product_ephemeral_prompt(product_context)
                except Exception:
                    logger.debug("Failed to build product runtime prompt", exc_info=True)
            agent.ephemeral_system_prompt = _webui_ephemeral_system_prompt(None, _product_prompt)
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

            _previous_messages = list(s.messages or [])
            _previous_context_messages = list(_context_messages_for_new_turn(s, msg))

            result = agent.run_conversation(
                user_message=workspace_ctx + msg,
                system_message=workspace_system_msg,
                conversation_history=_sanitize_messages_for_api(_previous_context_messages, cfg=get_config_fn()),
                task_id=s.session_id,
                persist_user_message=msg,
            )
    finally:
        with _ENV_LOCK:
            if old_cwd is None:
                os.environ.pop("TERMINAL_CWD", None)
            else:
                os.environ["TERMINAL_CWD"] = old_cwd
            if old_exec_ask is None:
                os.environ.pop("HERMES_EXEC_ASK", None)
            else:
                os.environ["HERMES_EXEC_ASK"] = old_exec_ask
            if old_session_key is None:
                os.environ.pop("HERMES_SESSION_KEY", None)
            else:
                os.environ["HERMES_SESSION_KEY"] = old_session_key

    with session_lock_fn(s.session_id):
        _result_messages = result.get("messages") or _previous_context_messages
        _next_context_messages = _restore_reasoning_metadata(
            _previous_context_messages,
            _result_messages,
        )
        s.context_messages = _next_context_messages
        s.messages = _merge_display_messages_after_agent_result(
            _previous_messages,
            _previous_context_messages,
            _restore_reasoning_metadata(_previous_messages, _result_messages),
            msg,
        )
        if s.title == "Untitled":
            s.title = title_from_fn(s.messages, s.title)
        s.save()
    return json_response_fn(
        handler,
        {
            "answer": result.get("final_response") or "",
            "status": "done" if result.get("completed", True) else "partial",
            "session": s.compact() | {"messages": s.messages},
            "result": {k: v for k, v in result.items() if k != "messages"},
        },
    )


def handle_chat_start(
    handler,
    body,
    *,
    require_fn: Callable,
    bad_response_fn: Callable,
    json_response_fn: Callable,
    get_session_fn: Callable,
    profiles_match_fn: Callable,
    normalize_chat_attachments_fn: Callable,
    resolve_chat_workspace_with_recovery_fn: Callable,
    product_task_title_from_request_fn: Callable,
    is_default_or_empty_session_title_fn: Callable,
    snapshot_product_fn: Callable,
    record_product_session_fn: Callable,
    resolve_session_model_state_fn: Callable,
    start_chat_stream_fn: Callable,
    logger,
    diag=None,
):
    try:
        diag.stage("validate_session_id") if diag else None
        try:
            require_fn(body, "session_id")
        except ValueError as e:
            return bad_response_fn(handler, str(e))
        diag.stage("get_session") if diag else None
        try:
            s = get_session_fn(body["session_id"])
        except KeyError:
            return bad_response_fn(handler, "Session not found", 404)
        diag.stage("validate_profile") if diag else None
        requested_profile = str(body.get("profile") or "").strip()
        if requested_profile:
            try:
                from api.profiles import _PROFILE_ID_RE

                if requested_profile != "default" and not _PROFILE_ID_RE.fullmatch(requested_profile):
                    return bad_response_fn(handler, "invalid profile", 400)
            except ImportError:
                requested_profile = ""
        if requested_profile and not profiles_match_fn(getattr(s, "profile", None), requested_profile):
            has_persisted_turns = bool(
                getattr(s, "messages", None)
                or getattr(s, "context_messages", None)
                or getattr(s, "pending_user_message", None)
            )
            if not has_persisted_turns:
                # Empty sessions are placeholders. If the user switches profiles
                # before sending the first turn, run the placeholder under the
                # currently-selected profile instead of the stale one stamped at
                # creation time.
                s.profile = requested_profile
        diag.stage("normalize_message") if diag else None
        msg = str(body.get("message", "")).strip()
        if not msg:
            return bad_response_fn(handler, "message is required")
        diag.stage("normalize_attachments") if diag else None
        attachments = normalize_chat_attachments_fn(body.get("attachments") or [])[:20]
        diag.stage("resolve_workspace") if diag else None
        try:
            workspace = resolve_chat_workspace_with_recovery_fn(s, body.get("workspace"))
        except ValueError as e:
            return bad_response_fn(handler, str(e))
        product_context = None
        from api.product_context import product_context_request_body

        product_body = product_context_request_body(body, s, msg)
        if product_body.get("product_id") or product_body.get("productId"):
            try:
                from api.product_context import product_context_from_request

                product_context = product_context_from_request(product_body, workspace=workspace)
            except ValueError as e:
                return bad_response_fn(handler, str(e), status=400)
            if product_context:
                product_task_title = product_task_title_from_request_fn(product_body)
                if (
                    product_task_title
                    and product_context["scope"] == "product_init"
                    and is_default_or_empty_session_title_fn(getattr(s, "title", None))
                ):
                    s.title = product_task_title
                if product_context["scope"] in {"product_init", "product_builder"}:
                    try:
                        snapshot_product_fn(
                            product_context["id"],
                            reason=f"{product_context['scope']}: {product_context.get('intent') or ''}"[:240],
                        )
                    except Exception:
                        logger.debug("Failed to snapshot product before builder turn", exc_info=True)
                try:
                    record_product_session_fn(
                        product_context["id"],
                        s.session_id,
                        ui_status="generating" if product_context["scope"] in {"product_init", "product_builder"} else None,
                    )
                except Exception:
                    logger.debug("Failed to update product session link", exc_info=True)
        requested_model = body.get("model") or s.model
        requested_provider = (
            body.get("model_provider")
            if "model_provider" in body
            else getattr(s, "model_provider", None)
        )
        diag.stage("resolve_model_provider") if diag else None
        model, model_provider, normalized_model = resolve_session_model_state_fn(
            requested_model,
            requested_provider,
        )
        from api.runtime_adapter import (
            LegacyJournalRuntimeAdapter,
            StartRunRequest,
            runtime_adapter_enabled,
        )

        if runtime_adapter_enabled():
            def _legacy_start_run(request: StartRunRequest) -> dict:
                return start_chat_stream_fn(
                    s,
                    msg=request.message,
                    attachments=request.attachments,
                    workspace=request.workspace or workspace,
                    model=request.model or model,
                    model_provider=request.provider or model_provider,
                    normalized_model=normalized_model,
                    diag=diag,
                    product_context=product_context,
                )

            adapter = LegacyJournalRuntimeAdapter(start_run_delegate=_legacy_start_run)
            result = adapter.start_run(
                StartRunRequest(
                    session_id=s.session_id,
                    message=msg,
                    attachments=attachments,
                    workspace=workspace,
                    profile=getattr(s, "profile", None),
                    provider=model_provider,
                    model=model,
                    source="webui",
                    metadata={"route": "/api/chat/start", "product": product_context},
                )
            )
            response = dict(result.payload)
            response.setdefault("stream_id", result.stream_id)
            response.setdefault("session_id", result.session_id)
        else:
            response = start_chat_stream_fn(
                s,
                msg=msg,
                attachments=attachments,
                workspace=workspace,
                model=model,
                model_provider=model_provider,
                normalized_model=normalized_model,
                diag=diag,
                product_context=product_context,
            )
        status = int(response.pop("_status", 200) or 200)
        diag.stage("response_write") if diag else None
        return json_response_fn(handler, response, status=status)
    finally:
        if diag:
            diag.finish()


def start_chat_stream_for_session(
    s,
    *,
    msg: str,
    attachments=None,
    workspace: str,
    model: str,
    model_provider=None,
    normalized_model: bool = False,
    diag=None,
    goal_related: bool = False,
    product_context=None,
    streams: dict,
    streams_lock,
    stream_goal_related: dict,
    pending_goal_continuation: set,
    clear_stale_stream_state_fn: Callable,
    get_session_agent_lock_fn: Callable,
    prepare_chat_start_session_fn: Callable,
    session_toolsets_from_request_fn: Callable,
    set_last_workspace_fn: Callable,
    create_stream_channel_fn: Callable,
    run_agent_streaming_fn: Callable,
    thread_factory: Callable,
    logger,
):
    """Persist pending state, register an SSE channel, and start an agent turn."""
    attachments = attachments or []
    # Prevent duplicate runs in the same session while a stream is still active.
    # This commonly happens after page refresh/reconnect races and can produce
    # duplicated clarify cards for what appears to be a single user request.
    diag.stage("active_stream_check") if diag else None
    current_stream_id = getattr(s, "active_stream_id", None)
    if current_stream_id:
        diag.stage("active_stream_lock_wait") if diag else None
        with streams_lock:
            current_active = current_stream_id in streams
        if current_active:
            diag.stage("response_write") if diag else None
            return {
                "error": "session already has an active stream",
                "active_stream_id": current_stream_id,
                "_status": 409,
            }
        # Stale stream id from a previous run; clear and continue.
        diag.stage("stale_stream_cleanup") if diag else None
        clear_stale_stream_state_fn(s)

    # #1932: check if this session has a pending goal continuation flag.
    # The streaming hook sets PENDING_GOAL_CONTINUATION when goal_continue fires,
    # so the next chat/start for this session is automatically treated as goal-related.
    if not goal_related and s.session_id in pending_goal_continuation:
        goal_related = True
        pending_goal_continuation.discard(s.session_id)

    stream_id = uuid.uuid4().hex
    session_lock = get_session_agent_lock_fn(s.session_id)
    diag.stage("session_lock_wait") if diag else None
    with session_lock:
        diag.stage("save_pending_state") if diag else None
        prepare_chat_start_session_fn(
            s,
            msg=msg,
            attachments=attachments,
            workspace=workspace,
            model=model,
            model_provider=model_provider,
            stream_id=stream_id,
        )
        if product_context:
            s.product_id = product_context.get("id")
            s.product_scope = product_context.get("scope")
            s.product_intent = product_context.get("intent") or ""
            s.product_line = product_context.get("line") or "use"
            product_toolsets = session_toolsets_from_request_fn({"toolsets": product_context.get("tools") or []})
            if product_toolsets:
                s.enabled_toolsets = product_toolsets
            s.save(skip_index=True)
    diag.stage("turn_journal_submitted") if diag else None
    journal_event = {}
    try:
        from api.turn_journal import append_turn_journal_event

        journal_event = append_turn_journal_event(
            s.session_id,
            {
                "event": "submitted",
                "stream_id": stream_id,
                "role": "user",
                "content": msg,
                "attachments": attachments,
                "workspace": workspace,
                "model": model,
                "model_provider": model_provider,
                "product": {
                    "id": product_context.get("id"),
                    "scope": product_context.get("scope"),
                    "title": product_context.get("title"),
                } if product_context else None,
                "created_at": s.pending_started_at,
            },
        )
    except Exception:
        logger.warning("Failed to append submitted turn journal event", exc_info=True)
    diag.stage("set_last_workspace") if diag else None
    set_last_workspace_fn(workspace)
    diag.stage("stream_registration") if diag else None
    stream = create_stream_channel_fn()
    with streams_lock:
        streams[stream_id] = stream
    # #1932: mark stream as goal-related so the streaming hook evaluates the goal.
    if goal_related:
        stream_goal_related[stream_id] = True
    diag.stage("worker_thread_start") if diag else None
    thr = thread_factory(
        target=run_agent_streaming_fn,
        args=(s.session_id, msg, model, workspace, stream_id, attachments),
        kwargs={"model_provider": model_provider, "goal_related": goal_related, "product_context": product_context},
        daemon=True,
    )
    thr.start()
    response = {
        "stream_id": stream_id,
        "session_id": s.session_id,
        "pending_started_at": s.pending_started_at,
        "turn_id": journal_event.get("turn_id"),
        "title": s.title,
    }
    if normalized_model:
        response["effective_model"] = model
    if model_provider:
        response["effective_model_provider"] = model_provider
    return response

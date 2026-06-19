"""Chat route helper functions."""

from __future__ import annotations

import logging
import os
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

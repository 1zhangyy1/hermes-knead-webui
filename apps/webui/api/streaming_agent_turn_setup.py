"""Agent/runtime setup for a WebUI streaming turn."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from api.config import (
    model_with_provider_context,
    resolve_custom_provider_connection,
    resolve_model_provider,
)
from api.streaming_agent_cache import get_and_register_agent_for_turn
from api.streaming_agent_config import (
    initialize_session_db,
    load_agent_config_and_toolsets,
    prepare_webui_agent_kwargs,
    resolve_agent_runtime_connection,
)
from api.streaming_bridges import initialize_webui_streaming_bridges
from api.streaming_runtime_helpers import aiagent_import_error_detail


@dataclass(frozen=True)
class StreamingAgentTurnSetup:
    should_continue: bool
    agent: Any = None
    agent_sig: str | None = None
    agent_factory: Any = None
    agent_kwargs: dict[str, Any] | None = None
    agent_params: set | None = None
    config: dict | None = None
    runtime: dict[str, Any] | None = None
    resolved_api_key: Any = None
    resolved_model: str | None = None
    resolved_provider: str | None = None
    resolved_base_url: str | None = None
    output_bridge: Any = None
    live_tool_calls: list | None = None
    checkpoint_activity: list | None = None


def prepare_streaming_agent_turn_setup(
    *,
    stream_id: str,
    session_id: str,
    session,
    model,
    provider_context,
    profile_home: str | None,
    run_state,
    put,
    cancel_event,
    agent_lock,
    ephemeral: bool,
    tool_result_snippet: Callable[[object], str],
    clarify_timeout_seconds: Callable[..., int],
    webui_clarify_callback: Callable[..., object],
    finalize_cancelled_turn: Callable[..., object],
    put_cancel: Callable[..., object],
    get_ai_agent: Callable[[], Any],
    logger,
    runtime_state: dict[str, Any] | None = None,
    aiagent_import_error_detail_fn=aiagent_import_error_detail,
    initialize_bridges_fn=initialize_webui_streaming_bridges,
    initialize_session_db_fn=initialize_session_db,
    resolve_model_provider_fn=resolve_model_provider,
    model_with_provider_context_fn=model_with_provider_context,
    resolve_agent_runtime_connection_fn=resolve_agent_runtime_connection,
    custom_provider_resolver=resolve_custom_provider_connection,
    load_agent_config_and_toolsets_fn=load_agent_config_and_toolsets,
    prepare_webui_agent_kwargs_fn=prepare_webui_agent_kwargs,
    get_and_register_agent_for_turn_fn=get_and_register_agent_for_turn,
) -> StreamingAgentTurnSetup:
    """Prepare bridges, runtime config, kwargs, and registered AIAgent for a turn."""

    def remember(**values) -> None:
        if runtime_state is not None:
            runtime_state.update(values)

    bridge_bundle = initialize_bridges_fn(
        stream_id=stream_id,
        session_id=session_id,
        run_state=run_state,
        put=put,
        tool_result_snippet=tool_result_snippet,
        logger=logger,
    )
    remember(
        _output_bridge=bridge_bundle.output_bridge,
        _live_tool_calls=bridge_bundle.live_tool_calls,
        _checkpoint_activity=bridge_bundle.checkpoint_activity,
    )

    agent_factory = get_ai_agent()
    remember(_AIAgent=agent_factory)
    if agent_factory is None:
        raise ImportError(aiagent_import_error_detail_fn())

    session_db = initialize_session_db_fn()
    resolved_model, resolved_provider, resolved_base_url = resolve_model_provider_fn(
        model_with_provider_context_fn(model, provider_context)
    )
    remember(
        resolved_model=resolved_model,
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
    )

    runtime, resolved_api_key, resolved_provider, resolved_base_url = resolve_agent_runtime_connection_fn(
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
        custom_provider_resolver=custom_provider_resolver,
    )
    remember(
        _rt=runtime,
        resolved_api_key=resolved_api_key,
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
    )

    config, toolsets = load_agent_config_and_toolsets_fn(session_id)
    remember(_cfg=config, _toolsets=toolsets)

    agent_kwargs_state = prepare_webui_agent_kwargs_fn(
        agent_cls=agent_factory,
        config=config,
        model=resolved_model,
        provider=resolved_provider,
        base_url=resolved_base_url,
        api_key=resolved_api_key,
        enabled_toolsets=toolsets,
        session_id=session_id,
        session_db=session_db,
        output_bridge=bridge_bundle.output_bridge,
        tool_bridge=bridge_bundle.tool_bridge,
        run_state=run_state,
        cancel_event=cancel_event,
        clarify_timeout_seconds=clarify_timeout_seconds,
        webui_clarify_callback=webui_clarify_callback,
        runtime=runtime,
    )
    remember(
        _agent_kwargs=agent_kwargs_state.agent_kwargs,
        _agent_params=agent_kwargs_state.agent_params,
    )

    registered_agent = get_and_register_agent_for_turn_fn(
        session_id=session_id,
        stream_id=stream_id,
        session=session,
        agent_factory=agent_factory,
        agent_kwargs=agent_kwargs_state.agent_kwargs,
        ephemeral=ephemeral,
        resolved_model=resolved_model,
        resolved_api_key=resolved_api_key,
        resolved_base_url=resolved_base_url,
        resolved_provider=resolved_provider,
        runtime=runtime,
        max_iterations=agent_kwargs_state.max_iterations,
        max_tokens=agent_kwargs_state.max_tokens,
        fallback_resolved=agent_kwargs_state.fallback_resolved,
        toolsets=toolsets,
        reasoning_config=agent_kwargs_state.reasoning_config,
        profile_home=profile_home,
        session_db=session_db,
        agent_lock=agent_lock,
        finalize_cancelled_turn_fn=finalize_cancelled_turn,
        put_cancel_fn=put_cancel,
        logger=logger,
    )
    remember(
        _registered_agent=registered_agent,
        _agent_sig=registered_agent.agent_sig,
        agent=registered_agent.agent,
    )
    if not registered_agent.should_continue:
        return StreamingAgentTurnSetup(should_continue=False)

    return StreamingAgentTurnSetup(
        should_continue=True,
        agent=registered_agent.agent,
        agent_sig=registered_agent.agent_sig,
        agent_factory=agent_factory,
        agent_kwargs=agent_kwargs_state.agent_kwargs,
        agent_params=agent_kwargs_state.agent_params,
        config=config,
        runtime=runtime,
        resolved_api_key=resolved_api_key,
        resolved_model=resolved_model,
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
        output_bridge=bridge_bundle.output_bridge,
        live_tool_calls=bridge_bundle.live_tool_calls,
        checkpoint_activity=bridge_bundle.checkpoint_activity,
    )

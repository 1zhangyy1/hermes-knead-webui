"""Configuration helpers for WebUI streaming agent construction."""


def initialize_session_db(*, session_db_factory=None, warning_fn=print):
    """Create SessionDB for WebUI agents, falling back to None on failure."""
    try:
        if session_db_factory is None:
            from hermes_state import SessionDB as session_db_factory
        return session_db_factory()
    except Exception as db_err:
        if warning_fn is not None:
            warning_fn(
                f"[webui] WARNING: SessionDB init failed — session_search will be unavailable: {db_err}",
                flush=True,
            )
        return None


def resolve_fallback_config(_cfg):
    """Normalize fallback_model/fallback_providers config for AIAgent."""
    # Fallback model from profile config (e.g. for rate-limit recovery)
    _fallback = _cfg.get('fallback_model') or _cfg.get('fallback_providers') or None
    _fallback_resolved = None
    if _fallback:
        # Normalize: support both single dict (legacy) and list (chained fallback).
        # Use the first valid entry as the fallback passed to AIAgent.
        _fb_entry = None
        if isinstance(_fallback, list):
            for _entry in _fallback:
                if isinstance(_entry, dict) and _entry.get('model'):
                    _fb_entry = _entry
                    break
        elif isinstance(_fallback, dict) and _fallback.get('model'):
            _fb_entry = _fallback
        if _fb_entry:
            _fallback_resolved = {
                'model': _fb_entry.get('model', ''),
                'provider': _fb_entry.get('provider', ''),
                'base_url': _fb_entry.get('base_url'),
                'api_key': _fb_entry.get('api_key'),
                'key_env': _fb_entry.get('key_env'),
            }
    return _fallback_resolved


def resolve_max_iterations_config(_cfg):
    """Read CLI-compatible agent.max_turns/root max_turns for AIAgent."""
    # CLI-parity max-iteration budget: read config.yaml's
    # agent.max_turns and pass it to AIAgent when supported. Without
    # this WebUI-created agents silently use AIAgent's constructor
    # default (90), so long browser-originated tasks hit the
    # "maximum number of tool-calling iterations" summary path even
    # after the operator raises Hermes' global turn budget.
    _max_iterations_cfg = None
    try:
        _raw_max_iterations = None
        _agent_cfg_for_iterations = _cfg.get('agent', {}) if isinstance(_cfg, dict) else {}
        if isinstance(_agent_cfg_for_iterations, dict):
            _raw_max_iterations = _agent_cfg_for_iterations.get('max_turns')
        if _raw_max_iterations is None and isinstance(_cfg, dict):
            # Back-compat for older Hermes config files that used a
            # root-level max_turns key.
            _raw_max_iterations = _cfg.get('max_turns')
        if _raw_max_iterations is not None:
            _parsed_max_iterations = int(_raw_max_iterations)
            if _parsed_max_iterations > 0:
                _max_iterations_cfg = _parsed_max_iterations
    except Exception:
        _max_iterations_cfg = None
    return _max_iterations_cfg


def resolve_max_tokens_config(_cfg):
    """Read CLI-compatible max_tokens from root config or agent config."""
    # CLI-parity max output cap: read config.yaml's max_tokens and pass
    # it to AIAgent when supported. Without this WebUI-created agents use
    # provider-native output ceilings (e.g. Claude via OpenRouter can
    # request 64k), which may turn an otherwise usable fallback into a
    # 402 "more credits / fewer max_tokens" failure.
    _max_tokens_cfg = None
    try:
        _raw_max_tokens = _cfg.get('max_tokens')
        if _raw_max_tokens is None:
            _agent_cfg_for_tokens = _cfg.get('agent', {})
            if isinstance(_agent_cfg_for_tokens, dict):
                _raw_max_tokens = _agent_cfg_for_tokens.get('max_tokens')
        if _raw_max_tokens is not None:
            _parsed_max_tokens = int(_raw_max_tokens)
            if _parsed_max_tokens > 0:
                _max_tokens_cfg = _parsed_max_tokens
    except Exception:
        _max_tokens_cfg = None
    return _max_tokens_cfg


def resolve_reasoning_config(_cfg, parse_reasoning_effort):
    """Read agent.reasoning_effort and convert it to AIAgent config."""
    # CLI-parity reasoning effort: read agent.reasoning_effort from the
    # active profile's config.yaml (the same key the CLI writes via
    # `/reasoning <level>`) and hand the parsed dict to AIAgent. When
    # the key is absent or invalid, pass None so agent uses its default.
    try:
        _effort_cfg = _cfg.get('agent', {}) if isinstance(_cfg, dict) else {}
        _effort_raw = _effort_cfg.get('reasoning_effort') if isinstance(_effort_cfg, dict) else None
        return parse_reasoning_effort(_effort_raw)
    except Exception:
        return None


def build_agent_kwargs(
    *,
    agent_params,
    model,
    provider,
    base_url,
    api_key,
    enabled_toolsets,
    fallback_model,
    session_id,
    session_db,
    stream_delta_callback,
    reasoning_callback,
    tool_progress_callback,
    clarify_callback,
    interim_assistant_callback=None,
    tool_start_callback=None,
    tool_complete_callback=None,
    status_callback=None,
    max_iterations=None,
    max_tokens=None,
    reasoning_config=None,
    runtime=None,
):
    """Build AIAgent kwargs while guarding params from newer agent versions."""
    runtime = runtime or {}
    kwargs = dict(
        model=model,
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        # Identify browser-originated sessions as WebUI so Hermes Agent
        # does not inject CLI-specific terminal/output guidance.
        platform='webui',
        quiet_mode=True,
        enabled_toolsets=enabled_toolsets,
        fallback_model=fallback_model,
        session_id=session_id,
        session_db=session_db,
        stream_delta_callback=stream_delta_callback,
        reasoning_callback=reasoning_callback,
        tool_progress_callback=tool_progress_callback,
        clarify_callback=clarify_callback,
    )
    # reasoning_config has been an AIAgent param for several releases, but guard
    # defensively to avoid TypeError on an older agent build.
    if 'reasoning_config' in agent_params and reasoning_config is not None:
        kwargs['reasoning_config'] = reasoning_config
    if 'interim_assistant_callback' in agent_params:
        kwargs['interim_assistant_callback'] = interim_assistant_callback
    if 'tool_start_callback' in agent_params:
        kwargs['tool_start_callback'] = tool_start_callback
    if 'tool_complete_callback' in agent_params:
        kwargs['tool_complete_callback'] = tool_complete_callback
    if 'status_callback' in agent_params:
        kwargs['status_callback'] = status_callback
    if 'max_iterations' in agent_params and max_iterations is not None:
        kwargs['max_iterations'] = max_iterations
    if 'max_tokens' in agent_params and max_tokens is not None:
        kwargs['max_tokens'] = max_tokens
    # Params added in newer hermes-agent — skip if not supported.
    if 'api_mode' in agent_params:
        kwargs['api_mode'] = runtime.get('api_mode')
    if 'acp_command' in agent_params:
        kwargs['acp_command'] = runtime.get('command')
    if 'acp_args' in agent_params:
        kwargs['acp_args'] = runtime.get('args')
    if 'credential_pool' in agent_params:
        kwargs['credential_pool'] = runtime.get('credential_pool')
    # Pin Honcho memory sessions to the stable WebUI session ID. Without this,
    # 'per-session' Honcho strategy creates a new Honcho session on every
    # streaming request because HonchoSessionManager is re-instantiated fresh
    # each turn (#855).
    if 'gateway_session_key' in agent_params:
        kwargs['gateway_session_key'] = session_id
    return kwargs

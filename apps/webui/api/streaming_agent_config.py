"""Configuration helpers for WebUI streaming agent construction."""


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


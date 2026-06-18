"""Context-window persistence helpers for WebUI streaming turns."""

from __future__ import annotations


def parse_context_window_config(cfg: dict | None) -> tuple[int | None, list | None]:
    """Return config context_length and custom providers for model metadata lookup."""
    cfg_ctx_len = None
    cfg_custom_providers = None
    try:
        model_cfg = cfg.get('model', {}) if isinstance(cfg, dict) else {}
        if isinstance(model_cfg, dict):
            raw_cfg_ctx = model_cfg.get('context_length')
            if raw_cfg_ctx is not None:
                try:
                    parsed_cfg_ctx = int(raw_cfg_ctx)
                    if parsed_cfg_ctx > 0:
                        cfg_ctx_len = parsed_cfg_ctx
                except (TypeError, ValueError):
                    pass
        raw_custom_providers = cfg.get('custom_providers') if isinstance(cfg, dict) else None
        if isinstance(raw_custom_providers, list):
            cfg_custom_providers = raw_custom_providers
    except Exception:
        pass
    return cfg_ctx_len, cfg_custom_providers


def resolve_context_length_fallback(
    agent,
    cfg: dict | None,
    *,
    resolved_model: str = '',
    resolved_provider: str = '',
) -> int:
    """Resolve the model context length when compressor state is unavailable."""
    try:
        from agent.model_metadata import get_model_context_length

        cfg_ctx_len, cfg_custom_providers = parse_context_window_config(cfg)
        try:
            resolved = get_model_context_length(
                getattr(agent, 'model', resolved_model or '') or '',
                getattr(agent, 'base_url', '') or '',
                config_context_length=cfg_ctx_len,
                provider=resolved_provider or '',
                custom_providers=cfg_custom_providers,
            )
        except TypeError:
            resolved = get_model_context_length(
                getattr(agent, 'model', resolved_model or '') or '',
                getattr(agent, 'base_url', '') or '',
            )
        return int(resolved or 0)
    except Exception:
        return 0


def persist_context_window_on_session(
    session,
    agent,
    cfg: dict | None,
    *,
    resolved_model: str = '',
    resolved_provider: str = '',
) -> None:
    """Copy context-window fields onto the session before the final save."""
    compressor = getattr(agent, 'context_compressor', None)
    if compressor:
        session.context_length = getattr(compressor, 'context_length', 0) or 0
        session.threshold_tokens = getattr(compressor, 'threshold_tokens', 0) or 0
        session.last_prompt_tokens = getattr(compressor, 'last_prompt_tokens', 0) or 0

    if not getattr(session, 'context_length', 0):
        resolved = resolve_context_length_fallback(
            agent,
            cfg,
            resolved_model=resolved_model,
            resolved_provider=resolved_provider,
        )
        if resolved:
            session.context_length = resolved


def apply_context_window_to_usage(
    usage: dict,
    session,
    agent,
    cfg: dict | None,
    *,
    resolved_model: str = '',
    resolved_provider: str = '',
) -> dict:
    """Populate live SSE usage with context-window values."""
    compressor = getattr(agent, 'context_compressor', None)
    if compressor:
        usage['context_length'] = getattr(compressor, 'context_length', 0) or 0
        usage['threshold_tokens'] = getattr(compressor, 'threshold_tokens', 0) or 0
        usage['last_prompt_tokens'] = getattr(compressor, 'last_prompt_tokens', 0) or 0

    if not usage.get('context_length'):
        resolved = resolve_context_length_fallback(
            agent,
            cfg,
            resolved_model=resolved_model,
            resolved_provider=resolved_provider,
        )
        if resolved:
            usage['context_length'] = resolved

    if not usage.get('last_prompt_tokens'):
        session_last_prompt_tokens = getattr(session, 'last_prompt_tokens', 0) or 0
        if session_last_prompt_tokens:
            usage['last_prompt_tokens'] = session_last_prompt_tokens
    return usage

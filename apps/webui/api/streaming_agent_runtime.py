"""Cached agent runtime refresh helpers for the WebUI streaming layer."""

from __future__ import annotations

import hashlib
import logging


logger = logging.getLogger(__name__)


def agent_cache_api_key_sig(resolved_api_key, credential_pool) -> str:
    """Return the cache-signature component for runtime credentials."""
    if credential_pool is not None:
        return 'credential-pool'
    return hashlib.sha256((resolved_api_key or '').encode()).hexdigest()[:16]


def refresh_cached_agent_runtime(agent, agent_kwargs: dict) -> bool:
    """Refresh volatile runtime credentials on a reused cached AIAgent."""
    if agent is None or not isinstance(agent_kwargs, dict):
        return False

    new_pool = agent_kwargs.get('credential_pool')
    if new_pool is not None:
        try:
            agent._credential_pool = new_pool
        except Exception:
            pass

    new_key = agent_kwargs.get('api_key') or ''
    if not new_key:
        return True

    new_base = agent_kwargs.get('base_url') or getattr(agent, 'base_url', '') or ''
    if getattr(agent, '_fallback_activated', False):
        return False

    if new_key == (getattr(agent, 'api_key', '') or ''):
        refresh_cached_agent_primary_runtime_snapshot(agent)
        return True

    try:
        if getattr(agent, 'api_mode', None) == 'anthropic_messages':
            if hasattr(agent, 'switch_model'):
                agent.switch_model(
                    agent_kwargs.get('model') or getattr(agent, 'model', None),
                    agent_kwargs.get('provider') or getattr(agent, 'provider', None),
                    api_key=new_key,
                    base_url=new_base,
                    api_mode=agent_kwargs.get('api_mode') or getattr(agent, 'api_mode', ''),
                )
                return True
            return False

        if not hasattr(agent, '_client_kwargs') or not hasattr(agent, '_replace_primary_openai_client'):
            agent.api_key = new_key
            if new_base:
                agent.base_url = new_base
            refresh_cached_agent_primary_runtime_snapshot(agent)
            return True

        client_kwargs = dict(getattr(agent, '_client_kwargs', {}) or {})
        client_kwargs['api_key'] = new_key
        if new_base:
            client_kwargs['base_url'] = new_base
        agent._client_kwargs = client_kwargs
        agent.api_key = new_key
        if new_base:
            agent.base_url = new_base
        if hasattr(agent, '_apply_client_headers_for_base_url'):
            agent._apply_client_headers_for_base_url(agent.base_url)
        rebuilt = bool(agent._replace_primary_openai_client(reason='webui_credential_refresh'))
        if rebuilt:
            refresh_cached_agent_primary_runtime_snapshot(agent)
        return rebuilt
    except Exception:
        logger.debug('[webui] Failed to refresh cached agent runtime credentials', exc_info=True)
        return False


def refresh_cached_agent_primary_runtime_snapshot(agent) -> None:
    """Keep AIAgent's primary-runtime snapshot aligned with refreshed creds."""
    rt = getattr(agent, '_primary_runtime', None)
    if not isinstance(rt, dict):
        return

    base_url = getattr(agent, 'base_url', rt.get('base_url'))
    api_key = getattr(agent, 'api_key', rt.get('api_key', ''))
    client_kwargs = dict(getattr(agent, '_client_kwargs', None) or rt.get('client_kwargs', {}) or {})

    rt['base_url'] = base_url
    rt['api_key'] = api_key
    rt['client_kwargs'] = client_kwargs

    cc = getattr(agent, 'context_compressor', None)
    if cc is not None:
        if hasattr(cc, 'base_url'):
            cc.base_url = base_url
        if hasattr(cc, 'api_key'):
            cc.api_key = api_key
        if 'compressor_base_url' in rt:
            rt['compressor_base_url'] = getattr(cc, 'base_url', base_url)
        if 'compressor_api_key' in rt:
            rt['compressor_api_key'] = getattr(cc, 'api_key', api_key)
    else:
        if 'compressor_base_url' in rt:
            rt['compressor_base_url'] = base_url
        if 'compressor_api_key' in rt:
            rt['compressor_api_key'] = api_key

    if getattr(agent, 'api_mode', None) == 'anthropic_messages':
        if hasattr(agent, '_anthropic_api_key'):
            rt['anthropic_api_key'] = getattr(agent, '_anthropic_api_key')
        if hasattr(agent, '_anthropic_base_url'):
            rt['anthropic_base_url'] = getattr(agent, '_anthropic_base_url')
        if hasattr(agent, '_is_anthropic_oauth'):
            rt['is_anthropic_oauth'] = getattr(agent, '_is_anthropic_oauth')

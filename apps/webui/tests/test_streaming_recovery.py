import threading

from api.streaming_recovery import (
    RebuiltCredentialAgent,
    rebuild_agent_for_credential_self_heal,
)


class _Agent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_rebuild_agent_for_credential_self_heal_updates_runtime_and_cache():
    import api.config as cfg

    agent_instances = {}
    calls = []

    def agent_factory(**kwargs):
        calls.append(kwargs)
        return _Agent(**kwargs)

    with cfg.SESSION_AGENT_CACHE_LOCK:
        snapshot = list(cfg.SESSION_AGENT_CACHE.items())
        cfg.SESSION_AGENT_CACHE.clear()
    try:
        result = rebuild_agent_for_credential_self_heal(
            agent_factory=agent_factory,
            agent_kwargs={"api_key": "old-key", "model": "old-model", "provider": None},
            agent_params={"credential_pool"},
            heal_runtime={
                "api_key": None,
                "provider": "custom:local",
                "base_url": None,
                "credential_pool": "pool-a",
            },
            resolved_model="model-a",
            resolved_provider=None,
            resolved_base_url=None,
            custom_provider_resolver=lambda provider: ("custom-key", f"https://{provider}.invalid"),
            session_id="sid-1",
            stream_id="stream-1",
            agent_instances=agent_instances,
            streams_lock=threading.Lock(),
            ephemeral=False,
            agent_sig="sig-1",
        )

        assert isinstance(result, RebuiltCredentialAgent)
        assert result.resolved_api_key == "custom-key"
        assert result.resolved_provider == "custom:local"
        assert result.resolved_base_url == "https://custom:local.invalid"
        assert result.agent_kwargs == {
            "api_key": "custom-key",
            "model": "model-a",
            "provider": "custom:local",
            "base_url": "https://custom:local.invalid",
            "credential_pool": "pool-a",
        }
        assert calls == [result.agent_kwargs]
        assert agent_instances["stream-1"] is result.agent
        with cfg.SESSION_AGENT_CACHE_LOCK:
            assert cfg.SESSION_AGENT_CACHE["sid-1"] == (result.agent, "sig-1")
    finally:
        with cfg.SESSION_AGENT_CACHE_LOCK:
            cfg.SESSION_AGENT_CACHE.clear()
            cfg.SESSION_AGENT_CACHE.update(snapshot)


def test_rebuild_agent_for_credential_self_heal_skips_cache_for_ephemeral_turns():
    import api.config as cfg

    agent_instances = {}
    original_kwargs = {"api_key": "old-key", "model": "old-model"}

    with cfg.SESSION_AGENT_CACHE_LOCK:
        snapshot = list(cfg.SESSION_AGENT_CACHE.items())
        cfg.SESSION_AGENT_CACHE.clear()
    try:
        result = rebuild_agent_for_credential_self_heal(
            agent_factory=_Agent,
            agent_kwargs=original_kwargs,
            agent_params=set(),
            heal_runtime={"api_key": "fresh-key", "provider": "openai", "base_url": None},
            resolved_model="model-a",
            resolved_provider=None,
            resolved_base_url=None,
            custom_provider_resolver=lambda _provider: (_ for _ in ()).throw(AssertionError("custom")),
            session_id="sid-1",
            stream_id="stream-1",
            agent_instances=agent_instances,
            streams_lock=threading.Lock(),
            ephemeral=True,
            agent_sig="sig-1",
        )

        assert result.agent_kwargs["api_key"] == "fresh-key"
        assert original_kwargs == {"api_key": "old-key", "model": "old-model"}
        assert agent_instances["stream-1"] is result.agent
        with cfg.SESSION_AGENT_CACHE_LOCK:
            assert "sid-1" not in cfg.SESSION_AGENT_CACHE
    finally:
        with cfg.SESSION_AGENT_CACHE_LOCK:
            cfg.SESSION_AGENT_CACHE.clear()
            cfg.SESSION_AGENT_CACHE.update(snapshot)

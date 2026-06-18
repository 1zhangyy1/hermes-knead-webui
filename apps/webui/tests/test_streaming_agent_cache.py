from api.streaming_agent_cache import (
    AgentForTurn,
    build_agent_cache_signature,
    cache_new_agent_for_signature,
    cached_agent_for_signature,
    get_agent_for_turn,
    get_cached_or_new_agent_for_turn,
    handle_evicted_agent_cache_items,
    register_agent_for_lifecycle,
    refresh_or_discard_cached_agent,
    refresh_cached_agent_for_turn,
)


class _SessionDB:
    def __init__(self):
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


class _Agent:
    def __init__(self, session_db=None):
        self._session_db = session_db
        self.stream_delta_callback = object()
        self.tool_progress_callback = object()
        self.tool_start_callback = object()
        self.tool_complete_callback = object()
        self.status_callback = object()
        self.interim_assistant_callback = object()
        self.reasoning_callback = object()
        self.clarify_callback = object()
        self._api_call_count = 7
        self._interrupted = True
        self._interrupt_message = "cancelled"


def _signature(**overrides):
    params = {
        'resolved_model': 'model-a',
        'resolved_api_key': 'key-a',
        'resolved_base_url': 'https://example.invalid',
        'resolved_provider': 'provider-a',
        'runtime': {'api_mode': 'responses', 'command': 'cmd', 'args': ['--x']},
        'max_iterations': 12,
        'max_tokens': 4096,
        'fallback_resolved': {'enabled': True},
        'toolsets': {'shell', 'browser'},
        'reasoning_config': {'effort': 'medium'},
        'profile_home': '/profiles/alpha',
    }
    params.update(overrides)
    return build_agent_cache_signature(**params)


def test_build_agent_cache_signature_includes_profile_home():
    assert _signature(profile_home='/profiles/alpha') != _signature(profile_home='/profiles/beta')


def test_build_agent_cache_signature_includes_reasoning_and_iteration_budget():
    assert _signature(reasoning_config={'effort': 'medium'}) != _signature(reasoning_config={'effort': 'xhigh'})
    assert _signature(max_iterations=12) != _signature(max_iterations=48)


def test_build_agent_cache_signature_ignores_volatile_pool_token():
    pool = object()
    runtime = {'credential_pool': pool}

    assert _signature(resolved_api_key='token-a', runtime=runtime) == _signature(
        resolved_api_key='token-b',
        runtime=runtime,
    )
    assert _signature(resolved_api_key='token-a', runtime={}) != _signature(
        resolved_api_key='token-b',
        runtime={},
    )


def test_cached_agent_for_signature_returns_match_and_registers_lifecycle(monkeypatch):
    import api.config as cfg
    import api.session_lifecycle as lifecycle

    calls = []
    agent = object()
    other_agent = object()
    monkeypatch.setattr(lifecycle, "register_agent", lambda session_id, agent: calls.append((session_id, agent)))

    with cfg.SESSION_AGENT_CACHE_LOCK:
        snapshot = list(cfg.SESSION_AGENT_CACHE.items())
        cfg.SESSION_AGENT_CACHE.clear()
        cfg.SESSION_AGENT_CACHE["other"] = (other_agent, "other-sig")
        cfg.SESSION_AGENT_CACHE["sid-1"] = (agent, "sig-1")
    try:
        result = cached_agent_for_signature("sid-1", "sig-1")

        assert result is agent
        assert calls == [("sid-1", agent)]
        with cfg.SESSION_AGENT_CACHE_LOCK:
            assert list(cfg.SESSION_AGENT_CACHE.keys())[-1] == "sid-1"
    finally:
        with cfg.SESSION_AGENT_CACHE_LOCK:
            cfg.SESSION_AGENT_CACHE.clear()
            cfg.SESSION_AGENT_CACHE.update(snapshot)


def test_cached_agent_for_signature_ignores_signature_mismatch(monkeypatch):
    import api.config as cfg
    import api.session_lifecycle as lifecycle

    calls = []
    agent = object()
    monkeypatch.setattr(lifecycle, "register_agent", lambda session_id, agent: calls.append((session_id, agent)))

    with cfg.SESSION_AGENT_CACHE_LOCK:
        snapshot = list(cfg.SESSION_AGENT_CACHE.items())
        cfg.SESSION_AGENT_CACHE.clear()
        cfg.SESSION_AGENT_CACHE["sid-1"] = (agent, "sig-1")
    try:
        assert cached_agent_for_signature("sid-1", "sig-2") is None
        assert calls == []
    finally:
        with cfg.SESSION_AGENT_CACHE_LOCK:
            cfg.SESSION_AGENT_CACHE.clear()
            cfg.SESSION_AGENT_CACHE.update(snapshot)


def test_register_agent_for_lifecycle_swallows_failures(monkeypatch):
    import api.session_lifecycle as lifecycle

    def fail(_session_id, _agent):
        raise RuntimeError("boom")

    monkeypatch.setattr(lifecycle, "register_agent", fail)

    register_agent_for_lifecycle("sid-1", object(), agent_kind='new')


def test_refresh_or_discard_cached_agent_keeps_refreshable_agent(monkeypatch):
    import api.streaming_agent_runtime as runtime

    calls = []
    agent = _Agent(session_db=_SessionDB())

    def refresh_cached_agent_runtime(agent_arg, kwargs_arg):
        calls.append((agent_arg, kwargs_arg))
        return True

    monkeypatch.setattr(runtime, "refresh_cached_agent_runtime", refresh_cached_agent_runtime)

    result = refresh_or_discard_cached_agent("sid-1", agent, {"api_key": "fresh"})

    assert result is agent
    assert calls == [(agent, {"api_key": "fresh"})]
    assert agent._session_db.close_calls == 0


def test_refresh_or_discard_cached_agent_closes_and_removes_unrefreshable_agent(monkeypatch):
    import api.config as cfg
    import api.streaming_agent_runtime as runtime

    monkeypatch.setattr(runtime, "refresh_cached_agent_runtime", lambda _agent, _kwargs: False)
    agent = _Agent(session_db=_SessionDB())

    with cfg.SESSION_AGENT_CACHE_LOCK:
        snapshot = list(cfg.SESSION_AGENT_CACHE.items())
        cfg.SESSION_AGENT_CACHE.clear()
        cfg.SESSION_AGENT_CACHE["sid-1"] = (agent, "sig-1")
    try:
        result = refresh_or_discard_cached_agent("sid-1", agent, {"api_key": "fresh"})

        assert result is None
        assert agent._session_db.close_calls == 1
        with cfg.SESSION_AGENT_CACHE_LOCK:
            assert "sid-1" not in cfg.SESSION_AGENT_CACHE
    finally:
        with cfg.SESSION_AGENT_CACHE_LOCK:
            cfg.SESSION_AGENT_CACHE.clear()
            cfg.SESSION_AGENT_CACHE.update(snapshot)


def test_cache_new_agent_for_signature_registers_caches_and_evicts(monkeypatch):
    import api.config as cfg
    import api.session_lifecycle as lifecycle

    calls = []
    old_db = _SessionDB()
    old_agent = _Agent(session_db=old_db)
    new_agent = _Agent(session_db=_SessionDB())

    monkeypatch.setattr(cfg, "SESSION_AGENT_CACHE_MAX", 1)
    monkeypatch.setattr(lifecycle, "register_agent", lambda session_id, agent: calls.append(("register", session_id, agent)))
    monkeypatch.setattr(lifecycle, "commit_session_memory", lambda session_id, *, agent=None, wait=False: calls.append(("commit", session_id, agent, wait)) or True)
    monkeypatch.setattr(lifecycle, "has_uncommitted_work", lambda session_id: calls.append(("has", session_id)) or False)
    monkeypatch.setattr(lifecycle, "unregister_agent", lambda session_id: calls.append(("unregister", session_id)))

    with cfg.SESSION_AGENT_CACHE_LOCK:
        snapshot = list(cfg.SESSION_AGENT_CACHE.items())
        cfg.SESSION_AGENT_CACHE.clear()
        cfg.SESSION_AGENT_CACHE["old"] = (old_agent, "old-sig")
    try:
        cache_new_agent_for_signature("new", new_agent, "new-sig")

        with cfg.SESSION_AGENT_CACHE_LOCK:
            assert list(cfg.SESSION_AGENT_CACHE.items()) == [("new", (new_agent, "new-sig"))]
        assert calls == [
            ("register", "new", new_agent),
            ("commit", "old", old_agent, True),
            ("has", "old"),
            ("unregister", "old"),
        ]
        assert old_db.close_calls == 1
    finally:
        with cfg.SESSION_AGENT_CACHE_LOCK:
            cfg.SESSION_AGENT_CACHE.clear()
            cfg.SESSION_AGENT_CACHE.update(snapshot)


def test_refresh_cached_agent_for_turn_updates_request_scoped_callbacks():
    old_db = _SessionDB()
    new_db = _SessionDB()
    agent = _Agent(session_db=old_db)
    callbacks = {
        'stream_delta_callback': object(),
        'tool_progress_callback': object(),
        'tool_start_callback': object(),
        'tool_complete_callback': object(),
        'status_callback': object(),
        'interim_assistant_callback': object(),
        'reasoning_callback': object(),
        'clarify_callback': object(),
    }

    result = refresh_cached_agent_for_turn(agent, callbacks, session_db=new_db)

    assert result is agent
    assert agent.stream_delta_callback is callbacks['stream_delta_callback']
    assert agent.tool_progress_callback is callbacks['tool_progress_callback']
    assert agent.tool_start_callback is callbacks['tool_start_callback']
    assert agent.tool_complete_callback is callbacks['tool_complete_callback']
    assert agent.status_callback is callbacks['status_callback']
    assert agent.interim_assistant_callback is callbacks['interim_assistant_callback']
    assert agent.reasoning_callback is callbacks['reasoning_callback']
    assert agent.clarify_callback is callbacks['clarify_callback']
    assert old_db.close_calls == 1
    assert new_db.close_calls == 0
    assert agent._session_db is new_db
    assert agent._api_call_count == 0
    assert agent._interrupted is False
    assert agent._interrupt_message is None


def test_refresh_cached_agent_for_turn_does_not_close_same_session_db():
    session_db = _SessionDB()
    agent = _Agent(session_db=session_db)

    refresh_cached_agent_for_turn(agent, {}, session_db=session_db)

    assert session_db.close_calls == 0
    assert agent._session_db is session_db


def test_refresh_cached_agent_for_turn_ignores_missing_optional_attributes():
    class MinimalAgent:
        pass

    agent = MinimalAgent()
    callbacks = {
        'stream_delta_callback': object(),
        'tool_progress_callback': object(),
        'status_callback': object(),
    }

    refresh_cached_agent_for_turn(agent, callbacks)

    assert agent.stream_delta_callback is callbacks['stream_delta_callback']
    assert agent.tool_progress_callback is callbacks['tool_progress_callback']
    assert not hasattr(agent, 'status_callback')


def test_get_cached_or_new_agent_for_turn_refreshes_matching_cached_agent():
    agent = _Agent()
    session_db = _SessionDB()
    calls = []

    result = get_cached_or_new_agent_for_turn(
        "sid-1",
        "sig-1",
        {"api_key": "fresh"},
        agent_factory=lambda **kwargs: calls.append(("factory", kwargs)),
        session_db=session_db,
        cached_agent_fn=lambda session_id, sig, logger=None: calls.append(("cached", session_id, sig)) or agent,
        refresh_or_discard_fn=lambda session_id, agent_arg, kwargs, logger=None: calls.append(
            ("refresh_runtime", session_id, agent_arg, kwargs)
        ) or agent_arg,
        refresh_for_turn_fn=lambda agent_arg, kwargs, session_db=None, logger=None: calls.append(
            ("refresh_turn", agent_arg, kwargs, session_db)
        ),
        cache_new_fn=lambda *args, **kwargs: calls.append(("cache_new", args, kwargs)),
    )

    assert result is agent
    assert calls == [
        ("cached", "sid-1", "sig-1"),
        ("refresh_runtime", "sid-1", agent, {"api_key": "fresh"}),
        ("refresh_turn", agent, {"api_key": "fresh"}, session_db),
    ]


def test_get_cached_or_new_agent_for_turn_rebuilds_when_cache_misses_or_refresh_fails():
    cached = _Agent()
    fresh = _Agent()
    calls = []

    result = get_cached_or_new_agent_for_turn(
        "sid-1",
        "sig-1",
        {"api_key": "fresh"},
        agent_factory=lambda **kwargs: calls.append(("factory", kwargs)) or fresh,
        cached_agent_fn=lambda session_id, sig, logger=None: cached,
        refresh_or_discard_fn=lambda session_id, agent_arg, kwargs, logger=None: calls.append(
            ("discard", session_id, agent_arg, kwargs)
        ) or None,
        refresh_for_turn_fn=lambda *args, **kwargs: calls.append(("refresh_turn", args, kwargs)),
        cache_new_fn=lambda session_id, agent_arg, sig, logger=None: calls.append(
            ("cache_new", session_id, agent_arg, sig)
        ),
    )

    assert result is fresh
    assert calls == [
        ("discard", "sid-1", cached, {"api_key": "fresh"}),
        ("factory", {"api_key": "fresh"}),
        ("cache_new", "sid-1", fresh, "sig-1"),
    ]


def test_get_agent_for_turn_creates_ephemeral_without_cache_signature():
    fresh = _Agent()
    calls = []

    result = get_agent_for_turn(
        session_id="sid-1",
        agent_factory=lambda **kwargs: calls.append(("factory", kwargs)) or fresh,
        agent_kwargs={"api_key": "fresh"},
        ephemeral=True,
        resolved_model="model-a",
        resolved_api_key="key-a",
        resolved_base_url=None,
        resolved_provider="provider-a",
        runtime={},
        max_iterations=None,
        max_tokens=None,
        fallback_resolved=None,
        toolsets=[],
        reasoning_config=None,
        profile_home="/profiles/alpha",
        cache_signature_fn=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("cache signature")),
        cached_or_new_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cache lookup")),
    )

    assert isinstance(result, AgentForTurn)
    assert result.agent is fresh
    assert result.agent_sig is None
    assert calls == [("factory", {"api_key": "fresh"})]


def test_get_agent_for_turn_uses_cache_signature_with_profile_home():
    cached = _Agent()
    calls = []

    def cache_signature_fn(**kwargs):
        calls.append(("signature", kwargs))
        return "sig-1"

    def cached_or_new_fn(session_id, agent_sig, agent_kwargs, *, agent_factory, session_db=None, logger=None):
        calls.append(("cached_or_new", session_id, agent_sig, agent_kwargs, agent_factory, session_db, logger))
        return cached

    result = get_agent_for_turn(
        session_id="sid-1",
        agent_factory=_Agent,
        agent_kwargs={"api_key": "fresh"},
        ephemeral=False,
        resolved_model="model-a",
        resolved_api_key="key-a",
        resolved_base_url="https://example.invalid",
        resolved_provider="provider-a",
        runtime={"api_mode": "responses"},
        max_iterations=12,
        max_tokens=4096,
        fallback_resolved={"model": "fallback"},
        toolsets=["terminal"],
        reasoning_config={"effort": "medium"},
        profile_home="/profiles/alpha",
        session_db="db",
        cache_signature_fn=cache_signature_fn,
        cached_or_new_fn=cached_or_new_fn,
    )

    assert result.agent is cached
    assert result.agent_sig == "sig-1"
    assert calls[0] == (
        "signature",
        {
            "resolved_model": "model-a",
            "resolved_api_key": "key-a",
            "resolved_base_url": "https://example.invalid",
            "resolved_provider": "provider-a",
            "runtime": {"api_mode": "responses"},
            "max_iterations": 12,
            "max_tokens": 4096,
            "fallback_resolved": {"model": "fallback"},
            "toolsets": ["terminal"],
            "reasoning_config": {"effort": "medium"},
            "profile_home": "/profiles/alpha",
        },
    )
    assert calls[1] == ("cached_or_new", "sid-1", "sig-1", {"api_key": "fresh"}, _Agent, "db", None)


def test_handle_evicted_agent_cache_items_commits_unregisters_and_closes(monkeypatch):
    import api.session_lifecycle as lifecycle

    calls = []
    db = _SessionDB()
    agent = type("Agent", (), {"_session_db": db})()

    def commit_session_memory(session_id, *, agent=None, wait=False):
        calls.append(("commit", session_id, agent, wait))
        return True

    def has_uncommitted_work(session_id):
        calls.append(("has_uncommitted_work", session_id))
        return False

    def unregister_agent(session_id):
        calls.append(("unregister_agent", session_id))

    monkeypatch.setattr(lifecycle, "commit_session_memory", commit_session_memory)
    monkeypatch.setattr(lifecycle, "has_uncommitted_work", has_uncommitted_work)
    monkeypatch.setattr(lifecycle, "unregister_agent", unregister_agent)

    handle_evicted_agent_cache_items([("sid-1", (agent, "sig"))])

    assert calls == [
        ("commit", "sid-1", agent, True),
        ("has_uncommitted_work", "sid-1"),
        ("unregister_agent", "sid-1"),
    ]
    assert db.close_calls == 1


def test_handle_evicted_agent_cache_items_keeps_agent_open_when_work_remains(monkeypatch):
    import api.session_lifecycle as lifecycle

    calls = []
    db = _SessionDB()
    agent = type("Agent", (), {"_session_db": db})()

    def commit_session_memory(session_id, *, agent=None, wait=False):
        calls.append(("commit", session_id, agent, wait))
        return True

    def has_uncommitted_work(session_id):
        calls.append(("has_uncommitted_work", session_id))
        return True

    def unregister_agent(session_id):
        calls.append(("unregister_agent", session_id))

    monkeypatch.setattr(lifecycle, "commit_session_memory", commit_session_memory)
    monkeypatch.setattr(lifecycle, "has_uncommitted_work", has_uncommitted_work)
    monkeypatch.setattr(lifecycle, "unregister_agent", unregister_agent)

    handle_evicted_agent_cache_items([("sid-1", (agent, "sig"))])

    assert calls == [
        ("commit", "sid-1", agent, True),
        ("has_uncommitted_work", "sid-1"),
    ]
    assert db.close_calls == 0

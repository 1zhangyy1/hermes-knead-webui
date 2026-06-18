import logging
import threading

from api.streaming_recovery import (
    CredentialSelfHealRetry,
    RebuiltCredentialAgent,
    handle_silent_failure_credential_self_heal,
    rebuild_agent_for_credential_self_heal,
    persist_exception_self_heal_result,
    retry_conversation_after_credential_self_heal,
)


class _Agent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _ConversationAgent(_Agent):
    def __init__(self, result=None, error=None, **kwargs):
        super().__init__(**kwargs)
        self.result = result
        self.error = error
        self.calls = []

    def run_conversation(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class _OutputBridge:
    token_sent = True


class SimpleBridge:
    def __init__(self, *, token_sent):
        self.token_sent = token_sent


class _Session:
    def __init__(self):
        self.session_id = "sid-1"
        self.active_stream_id = "stream-1"
        self.saved = 0

    def save(self):
        self.saved += 1


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


def test_retry_conversation_after_credential_self_heal_rebuilds_and_runs_retry():
    agent_instances = {}
    output_bridge = _OutputBridge()
    messages = [{"role": "user", "content": "before"}]
    retry_result = {"messages": [{"role": "assistant", "content": "ok"}]}

    def agent_factory(**kwargs):
        return _ConversationAgent(result=retry_result, **kwargs)

    def attempt_self_heal(provider_id, session_id, agent_lock, *, logger):
        assert provider_id == "anthropic"
        assert session_id == "sid-1"
        assert agent_lock == "lock"
        return {"api_key": "fresh-key", "provider": "anthropic", "base_url": "https://api.example"}

    def sanitize_messages_for_api(raw_messages, *, cfg):
        assert raw_messages is messages
        assert cfg == {"mode": "test"}
        return [{"role": "user", "content": "sanitized"}]

    result = retry_conversation_after_credential_self_heal(
        provider_id="anthropic",
        session_id="sid-1",
        agent_lock="lock",
        agent_factory=agent_factory,
        agent_kwargs={"api_key": "old-key"},
        agent_params=set(),
        resolved_model="model-a",
        resolved_provider=None,
        resolved_base_url=None,
        custom_provider_resolver=lambda _provider: (_ for _ in ()).throw(AssertionError("custom")),
        stream_id="stream-1",
        agent_instances=agent_instances,
        streams_lock=threading.Lock(),
        ephemeral=True,
        agent_sig="sig-1",
        user_message="hello",
        system_message="system",
        previous_context_messages=messages,
        config={"mode": "test"},
        persist_user_message="hello",
        sanitize_messages_for_api=sanitize_messages_for_api,
        output_bridge=output_bridge,
        logger=logging.getLogger(__name__),
        retrying_log_message="retrying",
        retry_failed_log_message="failed: %s",
        attempt_self_heal_fn=attempt_self_heal,
    )

    assert isinstance(result, CredentialSelfHealRetry)
    assert result.error is None
    assert result.result == retry_result
    assert result.rebuilt.resolved_api_key == "fresh-key"
    assert agent_instances["stream-1"] is result.rebuilt.agent
    assert output_bridge.token_sent is False
    assert result.rebuilt.agent.calls == [{
        "user_message": "hello",
        "system_message": "system",
        "conversation_history": [{"role": "user", "content": "sanitized"}],
        "task_id": "sid-1",
        "persist_user_message": "hello",
    }]


def test_retry_conversation_after_credential_self_heal_skips_when_refresh_fails():
    def attempt_self_heal(_provider_id, _session_id, _agent_lock, *, logger):
        return None

    def agent_factory(**_kwargs):
        raise AssertionError("agent should not be rebuilt")

    result = retry_conversation_after_credential_self_heal(
        provider_id="anthropic",
        session_id="sid-1",
        agent_lock=None,
        agent_factory=agent_factory,
        agent_kwargs={},
        agent_params=set(),
        resolved_model="model-a",
        resolved_provider="anthropic",
        resolved_base_url=None,
        custom_provider_resolver=lambda _provider: (_ for _ in ()).throw(AssertionError("custom")),
        stream_id="stream-1",
        agent_instances={},
        streams_lock=threading.Lock(),
        ephemeral=True,
        agent_sig="sig-1",
        user_message="hello",
        system_message="system",
        previous_context_messages=[],
        config={},
        persist_user_message="hello",
        sanitize_messages_for_api=lambda messages, *, cfg: messages,
        logger=logging.getLogger(__name__),
        retrying_log_message="retrying",
        retry_failed_log_message="failed: %s",
        attempt_self_heal_fn=attempt_self_heal,
    )

    assert result is None


def test_retry_conversation_after_credential_self_heal_returns_retry_error():
    retry_error = RuntimeError("retry failed")

    def agent_factory(**kwargs):
        return _ConversationAgent(error=retry_error, **kwargs)

    result = retry_conversation_after_credential_self_heal(
        provider_id="anthropic",
        session_id="sid-1",
        agent_lock=None,
        agent_factory=agent_factory,
        agent_kwargs={},
        agent_params=set(),
        resolved_model="model-a",
        resolved_provider="anthropic",
        resolved_base_url=None,
        custom_provider_resolver=lambda _provider: (_ for _ in ()).throw(AssertionError("custom")),
        stream_id="stream-1",
        agent_instances={},
        streams_lock=threading.Lock(),
        ephemeral=True,
        agent_sig="sig-1",
        user_message="hello",
        system_message="system",
        previous_context_messages=[],
        config={},
        persist_user_message="hello",
        sanitize_messages_for_api=lambda messages, *, cfg: messages,
        logger=logging.getLogger(__name__),
        retrying_log_message="retrying",
        retry_failed_log_message="failed: %s",
        attempt_self_heal_fn=lambda *_args, **_kwargs: {"api_key": "fresh-key"},
    )

    assert isinstance(result, CredentialSelfHealRetry)
    assert result.result is None
    assert result.error is retry_error


def test_handle_silent_failure_self_heal_skips_when_not_requested():
    calls = []

    result = handle_silent_failure_credential_self_heal(
        should_attempt=False,
        provider_id="anthropic",
        session_id="sid-1",
        agent_lock=None,
        agent_factory=lambda **_kwargs: calls.append(("agent",)),
        agent_kwargs={},
        agent_params=set(),
        resolved_model="model-a",
        resolved_provider="anthropic",
        resolved_base_url=None,
        custom_provider_resolver=lambda _provider: (None, None),
        stream_id="stream-1",
        agent_instances={},
        streams_lock=threading.Lock(),
        ephemeral=False,
        agent_sig="sig-1",
        user_message="hello",
        system_message="system",
        previous_messages=[],
        previous_context_messages=[],
        config={},
        persist_user_message="hello",
        sanitize_messages_for_api=lambda messages, *, cfg: messages,
        output_bridge=_OutputBridge(),
        prev_len=0,
        session=_Session(),
        msg_text="hello",
        has_new_assistant_reply=lambda *_args: calls.append(("has_new",)) or True,
        apply_agent_result_to_session=lambda *_args: calls.append(("apply",)),
        logger=logging.getLogger(__name__),
        retry_conversation_after_credential_self_heal_fn=lambda **_kwargs: calls.append(("retry",)),
    )

    assert result.self_healed is False
    assert result.succeeded is False
    assert calls == []


def test_handle_silent_failure_self_heal_merges_successful_retry():
    session = _Session()
    retry_agent = _Agent(api_key="fresh")
    retry_result = {"messages": [{"role": "assistant", "content": "ok"}]}
    calls = []

    def retry_fn(**kwargs):
        calls.append(("retry", kwargs))
        return CredentialSelfHealRetry(
            rebuilt=RebuiltCredentialAgent(
                agent=retry_agent,
                agent_kwargs={"api_key": "fresh"},
                runtime={"api_key": "fresh"},
                resolved_api_key="fresh",
                resolved_provider="anthropic",
                resolved_base_url="https://api.example",
            ),
            result=retry_result,
            error=None,
        )

    result = handle_silent_failure_credential_self_heal(
        should_attempt=True,
        provider_id="anthropic",
        session_id="sid-1",
        agent_lock="lock",
        agent_factory=_Agent,
        agent_kwargs={"api_key": "old"},
        agent_params=set(),
        resolved_model="model-a",
        resolved_provider="anthropic",
        resolved_base_url=None,
        custom_provider_resolver=lambda _provider: (None, None),
        stream_id="stream-1",
        agent_instances={},
        streams_lock=threading.Lock(),
        ephemeral=False,
        agent_sig="sig-1",
        user_message="hello",
        system_message="system",
        previous_messages=["display-before"],
        previous_context_messages=["context-before"],
        config={"mode": "test"},
        persist_user_message="hello",
        sanitize_messages_for_api=lambda messages, *, cfg: messages,
        output_bridge=SimpleBridge(token_sent=False),
        prev_len=1,
        session=session,
        msg_text="hello",
        has_new_assistant_reply=lambda messages, prev_len: calls.append(
            ("has_new", messages, prev_len)
        ) or True,
        apply_agent_result_to_session=lambda *args: calls.append(("apply", args)),
        logger=logging.getLogger(__name__),
        retry_conversation_after_credential_self_heal_fn=retry_fn,
    )

    assert result.self_healed is True
    assert result.succeeded is True
    assert result.result is retry_result
    assert result.agent is retry_agent
    assert result.agent_kwargs == {"api_key": "fresh"}
    assert result.runtime == {"api_key": "fresh"}
    assert result.resolved_api_key == "fresh"
    assert result.resolved_provider == "anthropic"
    assert result.resolved_base_url == "https://api.example"
    assert calls[0][0] == "retry"
    assert calls[1] == ("has_new", retry_result["messages"], 1)
    assert calls[2][0] == "apply"
    assert calls[2][1] == (
        session,
        ["display-before"],
        ["context-before"],
        retry_result["messages"],
        "hello",
    )


def test_handle_silent_failure_self_heal_does_not_merge_empty_retry_result():
    session = _Session()
    retry_agent = _Agent(api_key="fresh")
    calls = []

    def retry_fn(**_kwargs):
        return CredentialSelfHealRetry(
            rebuilt=RebuiltCredentialAgent(
                agent=retry_agent,
                agent_kwargs={"api_key": "fresh"},
                runtime={"api_key": "fresh"},
                resolved_api_key="fresh",
                resolved_provider="anthropic",
                resolved_base_url=None,
            ),
            result={"messages": []},
            error=None,
        )

    result = handle_silent_failure_credential_self_heal(
        should_attempt=True,
        provider_id="anthropic",
        session_id="sid-1",
        agent_lock=None,
        agent_factory=_Agent,
        agent_kwargs={},
        agent_params=set(),
        resolved_model="model-a",
        resolved_provider="anthropic",
        resolved_base_url=None,
        custom_provider_resolver=lambda _provider: (None, None),
        stream_id="stream-1",
        agent_instances={},
        streams_lock=threading.Lock(),
        ephemeral=False,
        agent_sig="sig-1",
        user_message="hello",
        system_message="system",
        previous_messages=[],
        previous_context_messages=[],
        config={},
        persist_user_message="hello",
        sanitize_messages_for_api=lambda messages, *, cfg: messages,
        output_bridge=SimpleBridge(token_sent=False),
        prev_len=0,
        session=session,
        msg_text="hello",
        has_new_assistant_reply=lambda *_args: False,
        apply_agent_result_to_session=lambda *_args: calls.append(("apply",)),
        logger=logging.getLogger(__name__),
        retry_conversation_after_credential_self_heal_fn=retry_fn,
    )

    assert result.self_healed is True
    assert result.succeeded is False
    assert result.result == {"messages": []}
    assert result.agent is retry_agent
    assert calls == []


def test_persist_exception_self_heal_result_writes_retry_messages_before_save():
    session = _Session()
    calls = []
    result = {"messages": [{"role": "assistant", "content": "ok"}]}

    ok = persist_exception_self_heal_result(
        session,
        result,
        previous_messages=["display-before"],
        previous_context_messages=["context-before"],
        msg_text="hello",
        session_id="sid-1",
        stream_id="stream-1",
        ephemeral=False,
        agent_lock=threading.Lock(),
        checkpoint_stop="stop",
        checkpoint_thread="thread",
        stop_checkpoint_thread=lambda stop, thread: calls.append(("stop", stop, thread)),
        stream_writeback_is_current=lambda session_arg, stream_id: session_arg.active_stream_id == stream_id,
        apply_agent_result_to_session=lambda *args: calls.append(("apply", args)),
        logger=logging.getLogger(__name__),
    )

    assert ok is True
    assert session.saved == 1
    assert calls[0] == ("stop", "stop", "thread")
    assert calls[1][0] == "apply"
    assert calls[1][1] == (
        session,
        ["display-before"],
        ["context-before"],
        [{"role": "assistant", "content": "ok"}],
        "hello",
    )


def test_persist_exception_self_heal_result_skips_stale_stream_writeback():
    session = _Session()
    session.active_stream_id = "newer-stream"
    calls = []

    ok = persist_exception_self_heal_result(
        session,
        {"messages": []},
        previous_messages=[],
        previous_context_messages=[],
        msg_text="hello",
        session_id="sid-1",
        stream_id="stream-1",
        ephemeral=False,
        agent_lock=threading.Lock(),
        checkpoint_stop=None,
        checkpoint_thread=None,
        stop_checkpoint_thread=lambda *_args: calls.append(("stop", None)),
        stream_writeback_is_current=lambda session_arg, stream_id: session_arg.active_stream_id == stream_id,
        apply_agent_result_to_session=lambda *_args: calls.append(("apply", None)),
        logger=logging.getLogger(__name__),
    )

    assert ok is False
    assert session.saved == 0
    assert calls == [("stop", None)]


def test_persist_exception_self_heal_result_treats_missing_session_as_success():
    calls = []

    ok = persist_exception_self_heal_result(
        None,
        {"messages": []},
        previous_messages=[],
        previous_context_messages=[],
        msg_text="hello",
        session_id="sid-1",
        stream_id="stream-1",
        ephemeral=False,
        agent_lock=None,
        checkpoint_stop=None,
        checkpoint_thread=None,
        stop_checkpoint_thread=lambda *_args: calls.append(("stop", None)),
        stream_writeback_is_current=lambda *_args: False,
        apply_agent_result_to_session=lambda *_args: calls.append(("apply", None)),
        logger=logging.getLogger(__name__),
    )

    assert ok is True
    assert calls == []


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

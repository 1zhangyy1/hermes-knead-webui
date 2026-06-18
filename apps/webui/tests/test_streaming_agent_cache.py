from api.streaming_agent_cache import handle_evicted_agent_cache_items, refresh_cached_agent_for_turn


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

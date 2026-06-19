from api import streaming
from api import streaming_recovery_facade as facade


def test_last_resort_sync_from_core_uses_streaming_runtime_dependencies(monkeypatch):
    calls = []

    def fake_last_resort_sync_from_core(
        session,
        stream_id,
        agent_lock,
        *,
        cancel_flags,
        get_profile_home,
        apply_core_sync_or_error_marker,
        logger,
    ):
        calls.append(
            (
                session,
                stream_id,
                agent_lock,
                cancel_flags,
                get_profile_home,
                apply_core_sync_or_error_marker,
                logger,
            )
        )

    monkeypatch.setattr(facade, "last_resort_sync_from_core", fake_last_resort_sync_from_core)

    session = object()
    agent_lock = object()
    facade.last_resort_sync_from_core_from_facade(session, "stream-1", agent_lock)

    assert len(calls) == 1
    assert calls[0][0:4] == (session, "stream-1", agent_lock, streaming.CANCEL_FLAGS)
    assert calls[0][5].__name__ == "_apply_core_sync_or_error_marker"
    assert calls[0][6] is streaming.logger


def test_attempt_credential_self_heal_uses_streaming_logger(monkeypatch):
    calls = []

    def fake_attempt(provider_id, session_id, agent_lock_ref, *, logger):
        calls.append((provider_id, session_id, agent_lock_ref, logger))
        return {"provider": provider_id}

    monkeypatch.setattr(facade, "attempt_credential_self_heal", fake_attempt)

    assert facade.attempt_credential_self_heal_from_facade("anthropic", "sid-1", "lock") == {
        "provider": "anthropic"
    }
    assert calls == [("anthropic", "sid-1", "lock", streaming.logger)]

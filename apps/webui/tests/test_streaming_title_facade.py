from types import SimpleNamespace

import api.streaming as streaming
import api.streaming_title_facade as facade


def test_title_facade_uses_streaming_patch_surface(monkeypatch):
    captured = {}

    def fake_run_background_title_update(*args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return "title-result"

    monkeypatch.setattr(facade, "run_background_title_update", fake_run_background_title_update)

    result = facade.run_background_title_update_from_facade(
        "sid",
        "user",
        "assistant",
        "Untitled",
        lambda *_args, **_kwargs: None,
        agent=SimpleNamespace(),
    )

    assert result == "title-result"
    assert captured["get_session"] is streaming.get_session
    assert captured["put_title_status_fn"] is streaming._put_title_status
    assert captured["aux_title_configured"] is streaming._aux_title_configured
    assert captured["generate_title_via_aux"] is streaming._generate_llm_session_title_via_aux
    assert captured["lock"] is streaming.LOCK
    assert captured["sessions"] is streaming.SESSIONS


def test_title_facade_schedules_refresh_with_streaming_patch_surface(monkeypatch):
    captured = {}

    def fake_maybe_schedule_title_refresh(*args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return "refresh-result"

    monkeypatch.setattr(facade, "maybe_schedule_title_refresh", fake_maybe_schedule_title_refresh)

    result = facade.maybe_schedule_title_refresh_from_facade(
        SimpleNamespace(),
        lambda *_args, **_kwargs: None,
        agent=None,
    )

    assert result == "refresh-result"
    assert captured["get_title_refresh_interval_fn"] is streaming._get_title_refresh_interval
    assert captured["count_exchanges"] is streaming._count_exchanges
    assert captured["latest_exchange_snippets"] is streaming._latest_exchange_snippets
    assert captured["run_background_title_refresh_fn"] is streaming._run_background_title_refresh

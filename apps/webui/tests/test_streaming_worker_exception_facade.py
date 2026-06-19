from types import SimpleNamespace

import api.streaming as streaming
import api.streaming_worker_exception_facade as facade


def test_streaming_worker_exception_facade_keeps_stream_local_callbacks(monkeypatch):
    captured = {}

    def fake_handle_streaming_exception(exc, **kwargs):
        captured["exc"] = exc
        captured.update(kwargs)
        return "exception-result"

    def finalize_product_turn(**_kwargs):
        return None

    def put_cancel():
        return None

    def put(_event, _payload):
        return None

    runtime_vars = {"_AIAgent": object()}
    exc = RuntimeError("boom")
    monkeypatch.setattr(facade, "handle_streaming_exception", fake_handle_streaming_exception)

    result = facade.handle_streaming_exception_from_facade(
        exc,
        runtime_vars=runtime_vars,
        self_healed=False,
        session=SimpleNamespace(),
        stream_id="stream",
        session_id="sid",
        cancel_event=SimpleNamespace(),
        agent_lock=SimpleNamespace(),
        checkpoint_stop=SimpleNamespace(),
        checkpoint_thread=SimpleNamespace(),
        ephemeral=False,
        finalize_product_turn=finalize_product_turn,
        put_cancel=put_cancel,
        put=put,
    )

    assert result == "exception-result"
    assert captured["exc"] is exc
    assert captured["runtime_vars"] is runtime_vars
    assert captured["finalize_product_turn"] is finalize_product_turn
    assert captured["put_cancel"] is put_cancel
    assert captured["put"] is put
    assert captured["sanitize_provider_error_text"] is streaming._sanitize_provider_error_text
    assert captured["apply_agent_result_to_session"] is streaming._apply_agent_result_to_session
    assert captured["agent_factory"] is runtime_vars["_AIAgent"]

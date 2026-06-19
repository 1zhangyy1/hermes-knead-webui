from types import SimpleNamespace

import api.streaming as streaming
import api.streaming_error_facade as facade


def test_error_facade_classification_uses_streaming_patch_surface(monkeypatch):
    captured = {}

    def fake_classify_provider_error(err_str, exc=None, **kwargs):
        captured["err_str"] = err_str
        captured["exc"] = exc
        captured.update(kwargs)
        return {"type": "cancelled"}

    monkeypatch.setattr(facade, "classify_provider_error", fake_classify_provider_error)

    exc = RuntimeError("Cancelled by user")
    result = facade.classify_provider_error_from_facade(
        "Cancelled by user",
        exc,
        silent_failure=True,
    )

    assert result == {"type": "cancelled"}
    assert captured["exc"] is exc
    assert captured["silent_failure"] is True
    assert captured["cancelled_turn_hint_fn"] is streaming._cancelled_turn_hint
    assert captured["is_quota_error_text_fn"] is streaming._is_quota_error_text


def test_error_facade_provider_payload_uses_streaming_redactor(monkeypatch):
    captured = {}

    def fake_provider_error_payload(message, err_type, hint, **kwargs):
        captured["message"] = message
        captured["err_type"] = err_type
        captured["hint"] = hint
        captured.update(kwargs)
        return {"message": "safe"}

    monkeypatch.setattr(facade, "provider_error_payload", fake_provider_error_payload)

    result = facade.provider_error_payload_from_facade("secret", "quota", "switch")

    assert result == {"message": "safe"}
    assert captured["redact_text_fn"] is streaming._redact_text


def test_error_facade_finalizer_uses_streaming_cancel_callbacks(monkeypatch):
    captured = {}

    def fake_finalize_cancelled_turn(session, **kwargs):
        captured["session"] = session
        captured.update(kwargs)

    monkeypatch.setattr(facade, "finalize_cancelled_turn", fake_finalize_cancelled_turn)

    session = SimpleNamespace()
    facade.finalize_cancelled_turn_from_facade(session, ephemeral=True, message="Stopped")

    assert captured["session"] is session
    assert captured["ephemeral"] is True
    assert captured["message"] == "Stopped"
    assert captured["cleanup_ephemeral_cancelled_turn_fn"] is streaming._cleanup_ephemeral_cancelled_turn
    assert captured["persist_cancelled_turn_fn"] is streaming._persist_cancelled_turn

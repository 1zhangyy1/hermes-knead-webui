import sys
import types
from types import SimpleNamespace

from api import streaming_context_window as subject


def _install_model_metadata(monkeypatch, resolver):
    agent_pkg = types.ModuleType("agent")
    metadata = types.ModuleType("agent.model_metadata")
    metadata.get_model_context_length = resolver
    monkeypatch.setitem(sys.modules, "agent", agent_pkg)
    monkeypatch.setitem(sys.modules, "agent.model_metadata", metadata)


def test_parse_context_window_config_accepts_positive_int_and_custom_providers():
    custom_providers = [{"name": "custom"}]

    ctx_len, providers = subject.parse_context_window_config({
        "model": {"context_length": "1048576"},
        "custom_providers": custom_providers,
    })

    assert ctx_len == 1_048_576
    assert providers is custom_providers


def test_resolve_context_length_fallback_passes_config_kwargs(monkeypatch):
    captured = {}

    def fake_get_model_context_length(model, base_url, **kwargs):
        captured["args"] = (model, base_url)
        captured["kwargs"] = kwargs
        return 1_000_000

    _install_model_metadata(monkeypatch, fake_get_model_context_length)
    agent = SimpleNamespace(model="deepseek-v4", base_url="https://models.example")

    resolved = subject.resolve_context_length_fallback(
        agent,
        {
            "model": {"context_length": 1_000_000},
            "custom_providers": [{"name": "provider"}],
        },
        resolved_provider="custom:provider",
    )

    assert resolved == 1_000_000
    assert captured["args"] == ("deepseek-v4", "https://models.example")
    assert captured["kwargs"] == {
        "config_context_length": 1_000_000,
        "provider": "custom:provider",
        "custom_providers": [{"name": "provider"}],
    }


def test_resolve_context_length_fallback_retries_legacy_signature(monkeypatch):
    calls = []

    def fake_get_model_context_length(*args, **kwargs):
        calls.append((args, kwargs))
        if kwargs:
            raise TypeError("old signature")
        return 256_000

    _install_model_metadata(monkeypatch, fake_get_model_context_length)

    resolved = subject.resolve_context_length_fallback(
        SimpleNamespace(model="legacy-model", base_url="https://legacy.example"),
        {"model": {"context_length": 512_000}},
        resolved_provider="legacy",
    )

    assert resolved == 256_000
    assert len(calls) == 2
    assert calls[0][1]["config_context_length"] == 512_000
    assert calls[1] == (("legacy-model", "https://legacy.example"), {})


def test_persist_context_window_on_session_copies_compressor_fields():
    session = SimpleNamespace(context_length=0, threshold_tokens=0, last_prompt_tokens=0)
    agent = SimpleNamespace(
        context_compressor=SimpleNamespace(
            context_length=300_000,
            threshold_tokens=250_000,
            last_prompt_tokens=42_000,
        )
    )

    subject.persist_context_window_on_session(session, agent, {})

    assert session.context_length == 300_000
    assert session.threshold_tokens == 250_000
    assert session.last_prompt_tokens == 42_000


def test_apply_context_window_to_usage_uses_session_last_prompt_fallback(monkeypatch):
    _install_model_metadata(monkeypatch, lambda *_args, **_kwargs: 500_000)
    usage = {}
    session = SimpleNamespace(last_prompt_tokens=99_000)
    agent = SimpleNamespace(model="m", base_url="", context_compressor=None)

    result = subject.apply_context_window_to_usage(
        usage,
        session,
        agent,
        {},
        resolved_provider="openai",
    )

    assert result is usage
    assert usage["context_length"] == 500_000
    assert usage["last_prompt_tokens"] == 99_000

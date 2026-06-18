import sys
import types
from types import SimpleNamespace

from api.streaming_live_usage import LiveUsageTracker


def test_live_usage_tracker_snapshot_reads_agent_and_context_values():
    compressor = SimpleNamespace(
        context_length=300,
        threshold_tokens=500,
        last_prompt_tokens=90,
    )
    agent = SimpleNamespace(
        session_prompt_tokens=11,
        session_completion_tokens=7,
        session_estimated_cost_usd=0.004,
        session_cache_read_tokens=5,
        session_cache_write_tokens=2,
        context_compressor=compressor,
    )
    session = SimpleNamespace(last_prompt_tokens=120)
    tracker = LiveUsageTracker(get_session=lambda: session, get_agent=lambda: agent)

    usage = tracker.snapshot()

    assert usage["input_tokens"] == 11
    assert usage["output_tokens"] == 7
    assert usage["estimated_cost"] == 0.004
    assert usage["cache_read_tokens"] == 5
    assert usage["cache_write_tokens"] == 2
    assert usage["context_length"] == 300
    assert usage["threshold_tokens"] == 500
    assert usage["last_prompt_tokens"] == 90


def test_live_usage_tracker_reanchors_estimate_to_new_exact_prompt(monkeypatch):
    session = SimpleNamespace(last_prompt_tokens=100)
    tracker = LiveUsageTracker(get_session=lambda: session, get_agent=lambda: None)

    agent_pkg = types.ModuleType("agent")
    agent_pkg.__path__ = []
    model_metadata = types.ModuleType("agent.model_metadata")
    model_metadata.estimate_messages_tokens_rough = lambda messages: 25
    monkeypatch.setitem(sys.modules, "agent", agent_pkg)
    monkeypatch.setitem(sys.modules, "agent.model_metadata", model_metadata)

    assert tracker.bump_prompt_estimate([{"role": "tool", "content": "result"}]) == 125
    assert tracker.snapshot()["last_prompt_tokens"] == 125

    session.last_prompt_tokens = 140
    assert tracker.snapshot()["last_prompt_tokens"] == 140


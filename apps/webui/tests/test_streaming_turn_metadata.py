from types import SimpleNamespace

from api.streaming_turn_metadata import apply_completed_turn_metadata


def test_apply_completed_turn_metadata_updates_assistant_and_gateway(monkeypatch):
    monkeypatch.setattr('api.streaming_turn_metadata.time.time', lambda: 112.3456)
    routing = {'used_provider': 'provider-b'}
    session = SimpleNamespace(
        messages=[
            {'role': 'user', 'content': 'hello'},
            {'role': 'assistant', 'content': 'done'},
        ],
        gateway_routing_history=[],
    )

    metadata = apply_completed_turn_metadata(
        session,
        agent=object(),
        result={'messages': []},
        turn_started_at=100,
        output_tokens=25,
        requested_model='model-a',
        requested_provider='provider-a',
        extract_gateway_routing_metadata=lambda *args, **kwargs: routing,
    )

    assert round(metadata.duration_seconds, 4) == 12.3456
    assert metadata.turn_tps == 2.0
    assert metadata.gateway_routing == routing
    assert session.gateway_routing == routing
    assert session.gateway_routing_history == [routing]
    assert session.messages[1]['_turnDuration'] == 12.346
    assert session.messages[1]['_turnTps'] == 2.0
    assert session.messages[1]['_gatewayRouting'] == routing


def test_apply_completed_turn_metadata_handles_missing_start_and_no_assistant(monkeypatch):
    monkeypatch.setattr('api.streaming_turn_metadata.time.time', lambda: 100)
    session = SimpleNamespace(messages=[{'role': 'user', 'content': 'hello'}])

    metadata = apply_completed_turn_metadata(
        session,
        agent=object(),
        result={},
        turn_started_at='bad',
        output_tokens=0,
        requested_model='model-a',
        requested_provider='provider-a',
        extract_gateway_routing_metadata=lambda *args, **kwargs: None,
    )

    assert metadata.duration_seconds == 0.0
    assert metadata.turn_tps is None
    assert metadata.gateway_routing is None
    assert session.messages == [{'role': 'user', 'content': 'hello'}]

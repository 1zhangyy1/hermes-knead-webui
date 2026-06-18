from types import SimpleNamespace

from api import streaming_turn_writeback as writeback


class Session:
    def __init__(self):
        self.messages = [
            {'role': 'user', 'content': 'hello'},
            {'role': 'assistant', 'content': 'done'},
        ]
        self.tool_calls = []
        self.active_stream_id = 'stream-1'
        self.pending_user_message = 'hello'
        self.pending_attachments = [{'name': 'a.png'}]
        self.pending_started_at = 123


def test_apply_completed_turn_writeback_state_applies_pre_save_mutations(monkeypatch):
    session = Session()
    agent = object()
    result = {'messages': []}
    title_plan = SimpleNamespace(should_background_title=False, user_text='hello', assistant_text='done')
    token_usage = SimpleNamespace(output_tokens=7)
    turn_metadata = SimpleNamespace(duration_seconds=1.2, turn_tps=5.8, gateway_routing={'provider': 'x'})
    calls = []

    monkeypatch.setattr(
        writeback,
        'prepare_completed_turn_title',
        lambda session_arg, **kwargs: calls.append(('title', session_arg, kwargs)) or title_plan,
    )
    monkeypatch.setattr(
        writeback,
        'apply_agent_token_usage_to_session',
        lambda session_arg, agent_arg: calls.append(('usage', session_arg, agent_arg)) or token_usage,
    )
    monkeypatch.setattr(
        writeback,
        'extract_tool_calls_from_messages',
        lambda messages, *, live_tool_calls=None: calls.append(('tools', messages, live_tool_calls)) or [{'id': 'tool-1'}],
    )
    monkeypatch.setattr(
        writeback,
        'tag_matching_user_message_attachments',
        lambda messages, msg_text, attachments: calls.append(('attachments', messages, msg_text, attachments)),
    )
    monkeypatch.setattr(
        writeback,
        'attach_reasoning_trace_to_last_assistant',
        lambda messages, reasoning_text: calls.append(('reasoning', messages, reasoning_text)) or True,
    )
    monkeypatch.setattr(
        writeback,
        'apply_completed_turn_metadata',
        lambda session_arg, agent_arg, result_arg, **kwargs: calls.append(
            ('metadata', session_arg, agent_arg, result_arg, kwargs)
        ) or turn_metadata,
    )
    monkeypatch.setattr(
        writeback,
        'persist_context_window_on_session',
        lambda session_arg, agent_arg, config, **kwargs: calls.append(
            ('context_window', session_arg, agent_arg, config, kwargs)
        ),
    )

    state = writeback.apply_completed_turn_writeback_state(
        session,
        agent,
        result,
        msg_text='hello',
        attachments=[{'name': 'a.png'}],
        live_tool_calls=[{'id': 'live'}],
        reasoning_text='thinking',
        turn_started_at=100,
        requested_model='model-a',
        requested_provider='provider-a',
        config={'cfg': True},
        title_from_fn=lambda *_args: 'title',
        is_provisional_title=lambda *_args: False,
        looks_invalid_generated_title=lambda *_args: False,
        first_exchange_snippets=lambda *_args: ('hello', 'done'),
        extract_gateway_routing_metadata=lambda *_args, **_kwargs: {},
    )

    assert state == writeback.CompletedTurnWritebackState(
        title_plan=title_plan,
        token_usage=token_usage,
        tool_calls=[{'id': 'tool-1'}],
        turn_metadata=turn_metadata,
    )
    assert session.tool_calls == [{'id': 'tool-1'}]
    assert session.active_stream_id is None
    assert session.pending_user_message is None
    assert session.pending_attachments == []
    assert session.pending_started_at is None
    assert [call[0] for call in calls] == [
        'title',
        'usage',
        'tools',
        'attachments',
        'reasoning',
        'metadata',
        'context_window',
    ]
    assert calls[5][4]['output_tokens'] == 7
    assert calls[5][4]['requested_model'] == 'model-a'
    assert calls[5][4]['requested_provider'] == 'provider-a'
    assert calls[6][3] == {'cfg': True}
    assert calls[6][4] == {'resolved_model': 'model-a', 'resolved_provider': 'provider-a'}

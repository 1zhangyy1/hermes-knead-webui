from types import SimpleNamespace

from api import streaming_turn_writeback as writeback


class Session:
    def __init__(self):
        self.session_id = 'sid-1'
        self.messages = [
            {'role': 'user', 'content': 'hello'},
            {'role': 'assistant', 'content': 'done'},
        ]
        self.tool_calls = []
        self.active_stream_id = 'stream-1'
        self.pending_user_message = 'hello'
        self.pending_attachments = [{'name': 'a.png'}]
        self.pending_started_at = 123
        self.saved = 0

    def save(self):
        self.saved += 1


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


def test_detect_silent_failure_after_merge_handles_missing_assistant_reply():
    calls = []

    state = writeback.detect_silent_failure_after_merge(
        {'messages': [{'role': 'user', 'content': 'hello'}]},
        [{'role': 'user', 'content': 'hello'}],
        msg_text='hello',
        token_sent=False,
        assistant_reply_added_after_current_turn=lambda messages, previous, msg_text: calls.append(
            (messages, previous, msg_text)
        ) or False,
    )

    assert state == writeback.SilentFailureDetectionState(
        previous_context_count=1,
        assistant_added=False,
        token_sent=False,
        should_handle=True,
    )
    assert calls == [(
        [{'role': 'user', 'content': 'hello'}],
        [{'role': 'user', 'content': 'hello'}],
        'hello',
    )]


def test_detect_silent_failure_after_merge_skips_when_assistant_or_token_seen():
    assistant_state = writeback.detect_silent_failure_after_merge(
        {'messages': [{'role': 'assistant', 'content': 'ok'}]},
        [],
        msg_text='hello',
        token_sent=False,
        assistant_reply_added_after_current_turn=lambda *_args: True,
    )
    token_state = writeback.detect_silent_failure_after_merge(
        None,
        None,
        msg_text='hello',
        token_sent=True,
        assistant_reply_added_after_current_turn=lambda *_args: False,
    )

    assert assistant_state == writeback.SilentFailureDetectionState(
        previous_context_count=0,
        assistant_added=True,
        token_sent=False,
        should_handle=False,
    )
    assert token_state == writeback.SilentFailureDetectionState(
        previous_context_count=0,
        assistant_added=False,
        token_sent=True,
        should_handle=False,
    )


def test_prepare_success_turn_writeback_skips_stale_stream_without_mutation():
    session = Session()
    session.active_stream_id = 'newer-stream'
    calls = []
    logger = SimpleNamespace(info=lambda *args: calls.append(('log', args)))

    ok = writeback.prepare_success_turn_writeback(
        session,
        stream_id='stream-1',
        ephemeral=False,
        stream_writeback_is_current=lambda session_arg, stream_id: calls.append(
            ('current', session_arg, stream_id)
        ) or False,
        cancel_event=SimpleNamespace(is_set=lambda: False),
        finalize_cancelled_turn=lambda *_args, **_kwargs: calls.append(('finalize',)),
        put_cancel=lambda: calls.append(('cancel',)),
        logger=logger,
    )

    assert ok is False
    assert calls[0] == ('current', session, 'stream-1')
    assert calls[1][0] == 'log'
    assert 'Skipping stale stream writeback' in calls[1][1][0]
    assert all(call[0] not in {'finalize', 'cancel'} for call in calls)


def test_prepare_success_turn_writeback_cancel_finalizes_and_interrupts(monkeypatch):
    session = Session()
    calls = []
    monkeypatch.setattr(
        writeback,
        'append_interrupted_turn_event',
        lambda session_id, stream_id, **kwargs: calls.append(('interrupted', session_id, stream_id, kwargs)),
    )

    ok = writeback.prepare_success_turn_writeback(
        session,
        stream_id='stream-1',
        ephemeral=False,
        stream_writeback_is_current=lambda *_args: True,
        cancel_event=SimpleNamespace(is_set=lambda: True),
        finalize_cancelled_turn=lambda session_arg, **kwargs: calls.append(('finalize', session_arg, kwargs)),
        put_cancel=lambda: calls.append(('cancel',)),
    )

    assert ok is False
    assert calls == [
        ('finalize', session, {'ephemeral': False}),
        ('interrupted', 'sid-1', 'stream-1', {'logger': None}),
        ('cancel',),
    ]


def test_prepare_success_turn_writeback_allows_current_stream():
    session = Session()
    calls = []

    ok = writeback.prepare_success_turn_writeback(
        session,
        stream_id='stream-1',
        ephemeral=False,
        stream_writeback_is_current=lambda session_arg, stream_id: calls.append(
            ('current', session_arg, stream_id)
        ) or True,
        cancel_event=SimpleNamespace(is_set=lambda: False),
        finalize_cancelled_turn=lambda *_args, **_kwargs: calls.append(('finalize',)),
        put_cancel=lambda: calls.append(('cancel',)),
    )

    assert ok is True
    assert calls == [('current', session, 'stream-1')]


def test_save_completed_turn_and_journal_orders_save_journal_and_memory(monkeypatch):
    session = Session()
    agent = object()
    calls = []
    session.save = lambda: calls.append(('save',))

    monkeypatch.setattr(
        writeback,
        'append_assistant_started_turn_event',
        lambda session_id, stream_id, messages, **kwargs: calls.append(
            ('assistant_started', session_id, stream_id, messages, kwargs)
        ),
    )
    monkeypatch.setattr(
        writeback,
        'append_completed_turn_event',
        lambda session_id, stream_id, messages, **kwargs: calls.append(
            ('completed', session_id, stream_id, messages, kwargs)
        ),
    )
    monkeypatch.setattr(
        writeback,
        'mark_completed_turn_memory_lifecycle',
        lambda session_id, agent_arg, **kwargs: calls.append(('memory', session_id, agent_arg, kwargs)),
    )

    saved = writeback.save_completed_turn_and_journal(
        session,
        agent,
        stream_id='stream-1',
        cancel_event=SimpleNamespace(is_set=lambda: False),
        finalize_cancelled_turn=lambda *_args, **_kwargs: calls.append(('finalize',)),
        put_cancel=lambda: calls.append(('cancel',)),
        logger='logger',
    )

    assert saved is True
    assert calls == [
        ('assistant_started', 'sid-1', 'stream-1', session.messages, {'logger': 'logger'}),
        ('save',),
        ('completed', 'sid-1', 'stream-1', session.messages, {'logger': 'logger'}),
        ('memory', 'sid-1', agent, {'logger': 'logger'}),
    ]


def test_save_completed_turn_and_journal_cancel_before_save_finalizes_without_saving(monkeypatch):
    session = Session()
    calls = []
    session.save = lambda: calls.append(('save',))

    monkeypatch.setattr(
        writeback,
        'append_assistant_started_turn_event',
        lambda session_id, stream_id, messages, **kwargs: calls.append(('assistant_started',)),
    )
    monkeypatch.setattr(
        writeback,
        'append_interrupted_turn_event',
        lambda session_id, stream_id, **kwargs: calls.append(('interrupted', session_id, stream_id, kwargs)),
    )
    monkeypatch.setattr(
        writeback,
        'append_completed_turn_event',
        lambda *_args, **_kwargs: calls.append(('completed',)),
    )
    monkeypatch.setattr(
        writeback,
        'mark_completed_turn_memory_lifecycle',
        lambda *_args, **_kwargs: calls.append(('memory',)),
    )

    saved = writeback.save_completed_turn_and_journal(
        session,
        object(),
        stream_id='stream-1',
        cancel_event=SimpleNamespace(is_set=lambda: True),
        finalize_cancelled_turn=lambda session_arg, **kwargs: calls.append(('finalize', session_arg, kwargs)),
        put_cancel=lambda: calls.append(('cancel',)),
    )

    assert saved is False
    assert calls == [
        ('assistant_started',),
        ('finalize', session, {'ephemeral': False}),
        ('interrupted', 'sid-1', 'stream-1', {'logger': None}),
        ('cancel',),
    ]


def test_save_completed_turn_and_journal_cancel_after_save_skips_completed_lifecycle(monkeypatch):
    session = Session()
    calls = []
    cancelled = {'value': False}

    def save():
        calls.append(('save',))
        cancelled['value'] = True

    session.save = save
    monkeypatch.setattr(
        writeback,
        'append_assistant_started_turn_event',
        lambda session_id, stream_id, messages, **kwargs: calls.append(('assistant_started',)),
    )
    monkeypatch.setattr(
        writeback,
        'append_interrupted_turn_event',
        lambda session_id, stream_id, **kwargs: calls.append(('interrupted', session_id, stream_id, kwargs)),
    )
    monkeypatch.setattr(
        writeback,
        'append_completed_turn_event',
        lambda *_args, **_kwargs: calls.append(('completed',)),
    )
    monkeypatch.setattr(
        writeback,
        'mark_completed_turn_memory_lifecycle',
        lambda *_args, **_kwargs: calls.append(('memory',)),
    )

    saved = writeback.save_completed_turn_and_journal(
        session,
        object(),
        stream_id='stream-1',
        cancel_event=SimpleNamespace(is_set=lambda: cancelled['value']),
        finalize_cancelled_turn=lambda session_arg, **kwargs: calls.append(('finalize', session_arg, kwargs)),
        put_cancel=lambda: calls.append(('cancel',)),
    )

    assert saved is False
    assert calls == [
        ('assistant_started',),
        ('save',),
        ('finalize', session, {'ephemeral': False}),
        ('interrupted', 'sid-1', 'stream-1', {'logger': None}),
        ('cancel',),
    ]

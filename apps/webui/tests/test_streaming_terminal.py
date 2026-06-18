from types import SimpleNamespace

from api.streaming_terminal import emit_completed_turn_done, emit_success_post_done_events


class FakeThread:
    calls = []

    def __init__(self, *, target, args, daemon):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False
        FakeThread.calls.append(self)

    def start(self):
        self.started = True


def test_emit_success_post_done_events_emits_metering_and_stream_end():
    events = []
    refresh_calls = []
    session = SimpleNamespace(session_id='compressed-sid', title='Title')
    put = lambda event, data: events.append((event, data))

    result = emit_success_post_done_events(
        session,
        original_session_id='original-sid',
        should_background_title=False,
        title_user_text='',
        title_assistant_text='',
        put=put,
        agent='agent',
        meter_stats_fn=lambda: {},
        run_background_title_update=lambda *args: None,
        maybe_schedule_title_refresh=lambda *args: refresh_calls.append(args),
    )

    assert result == 'stream_end'
    assert events == [
        ('metering', {'session_id': 'original-sid', 'tps_available': False, 'estimated': False}),
        ('stream_end', {'session_id': 'original-sid'}),
    ]
    assert refresh_calls == [(session, put, 'agent')]


def test_emit_success_post_done_events_starts_background_title_thread():
    FakeThread.calls = []
    events = []
    session = SimpleNamespace(session_id='compressed-sid', title='  Draft Title  ')
    refresh_calls = []
    put = lambda event, data: events.append((event, data))

    result = emit_success_post_done_events(
        session,
        original_session_id='original-sid',
        should_background_title=True,
        title_user_text='hello',
        title_assistant_text='answer',
        put=put,
        agent='agent',
        meter_stats_fn=lambda: {'tps_available': True, 'estimated': True},
        run_background_title_update=lambda *args: None,
        maybe_schedule_title_refresh=lambda *args: refresh_calls.append(args),
        thread_factory=FakeThread,
    )

    assert result == 'background_title'
    assert events == [
        ('metering', {'tps_available': True, 'estimated': True, 'session_id': 'original-sid'})
    ]
    assert refresh_calls == []
    assert len(FakeThread.calls) == 1
    thread = FakeThread.calls[0]
    assert thread.started is True
    assert thread.daemon is True
    assert thread.args == (
        'compressed-sid',
        'hello',
        'answer',
        'Draft Title',
        put,
        'agent',
    )


def test_emit_completed_turn_done_builds_done_payload_before_terminal_events():
    events = []
    calls = []
    usage = {'tokens': 12}
    session = SimpleNamespace(
        session_id='compressed-sid',
        title='Title',
        messages=[{'role': 'assistant', 'content': 'done'}],
        compact=lambda: {'session_id': 'compressed-sid'},
    )
    token_usage = SimpleNamespace(output_tokens=5)
    turn_metadata = SimpleNamespace(
        duration_seconds=1.25,
        turn_tps=4.0,
        gateway_routing={'provider': 'openai'},
    )
    title_plan = SimpleNamespace(
        should_background_title=False,
        user_text='hello',
        assistant_text='answer',
    )

    def put(event, data):
        events.append((event, data))

    result = emit_completed_turn_done(
        session,
        original_session_id='original-sid',
        token_usage=token_usage,
        turn_metadata=turn_metadata,
        config={'max_tokens': 100},
        resolved_model='gpt-5',
        resolved_provider='openai',
        agent='agent',
        profile_home='/profiles/default',
        goal_related=True,
        put=put,
        pending_goal_continuation={},
        tool_calls=[{'name': 'tool'}],
        title_plan=title_plan,
        redact_session_data=lambda raw: calls.append(('redact', raw)) or {'redacted': raw['session_id']},
        build_done_usage_payload=lambda *args, **kwargs: calls.append(('usage', args, kwargs)) or usage,
        apply_context_window_to_usage=lambda usage_arg, *args, **kwargs: calls.append(
            ('context_window', usage_arg, args, kwargs)
        ) or usage_arg.update({'context': 'applied'}),
        drain_pending_steer_leftover=lambda *args, **kwargs: calls.append(('drain', args, kwargs)),
        run_post_turn_goal_hook=lambda *args, **kwargs: calls.append(('goal', args, kwargs)),
        finalize_product_turn=lambda **kwargs: calls.append(('finalize', kwargs)),
        meter_stats_fn=lambda: {'metered': True},
        run_background_title_update=lambda *args: calls.append(('title_update', args)),
        maybe_schedule_title_refresh=lambda *args: calls.append(('title_refresh', args)),
    )

    assert result == {'tokens': 12, 'context': 'applied'}
    assert calls[0] == (
        'usage',
        (token_usage,),
        {
            'duration_seconds': 1.25,
            'turn_tps': 4.0,
            'gateway_routing': {'provider': 'openai'},
        },
    )
    assert calls[1][0] == 'context_window'
    assert calls[2][0] == 'drain'
    assert calls[3][0] == 'goal'
    assert calls[4] == ('finalize', {'failed': False})
    assert calls[5] == (
        'redact',
        {
            'session_id': 'compressed-sid',
            'messages': [{'role': 'assistant', 'content': 'done'}],
            'tool_calls': [{'name': 'tool'}],
        },
    )
    assert calls[6][0] == 'title_refresh'
    assert events == [
        ('done', {'session': {'redacted': 'compressed-sid'}, 'usage': result}),
        ('metering', {'metered': True, 'session_id': 'original-sid', 'tps_available': False, 'estimated': False}),
        ('stream_end', {'session_id': 'original-sid'}),
    ]

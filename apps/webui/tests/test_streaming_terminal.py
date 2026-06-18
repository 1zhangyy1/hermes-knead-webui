from types import SimpleNamespace

from api.streaming_terminal import emit_success_post_done_events


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

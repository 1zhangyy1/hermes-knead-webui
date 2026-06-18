from types import SimpleNamespace

from api.streaming_chat_steer import drain_pending_steer_leftover


def test_drain_pending_steer_leftover_emits_event():
    events = []
    agent = SimpleNamespace(_drain_pending_steer=lambda: 'use the draft')

    leftover = drain_pending_steer_leftover(
        agent,
        session_id='sid-1',
        put=lambda event, data: events.append((event, data)),
    )

    assert leftover == 'use the draft'
    assert events == [
        ('pending_steer_leftover', {'session_id': 'sid-1', 'text': 'use the draft'})
    ]


def test_drain_pending_steer_leftover_skips_empty_or_missing_drain():
    events = []

    assert drain_pending_steer_leftover(
        SimpleNamespace(_drain_pending_steer=lambda: ''),
        session_id='sid-1',
        put=lambda event, data: events.append((event, data)),
    ) == ''
    assert drain_pending_steer_leftover(
        SimpleNamespace(),
        session_id='sid-1',
        put=lambda event, data: events.append((event, data)),
    ) == ''
    assert events == []


def test_drain_pending_steer_leftover_logs_exceptions():
    class Logger:
        def __init__(self):
            self.messages = []

        def debug(self, *args, **kwargs):
            self.messages.append((args, kwargs))

    def boom():
        raise RuntimeError('boom')

    logger = Logger()
    leftover = drain_pending_steer_leftover(
        SimpleNamespace(_drain_pending_steer=boom),
        session_id='sid-1',
        put=lambda event, data: None,
        logger=logger,
    )

    assert leftover == ''
    assert logger.messages

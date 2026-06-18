from api.streaming_error_writeback import (
    classify_silent_failure_error,
    emit_and_persist_exception_streaming_error,
    emit_and_persist_silent_failure_error,
    emit_and_persist_streaming_error,
    format_streaming_error_content,
    persist_streaming_error_message,
    provider_details_label,
)


class Session:
    def __init__(self):
        self.session_id = 'sid-1'
        self.messages = []
        self.active_stream_id = 'stream-1'
        self.pending_user_message = 'hello'
        self.pending_attachments = [{'name': 'a.png'}]
        self.pending_started_at = 123
        self.saved = 0

    def save(self):
        self.saved += 1


class Logger:
    def __init__(self):
        self.messages = []

    def debug(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    def info(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class Agent:
    def __init__(self, last_error=None):
        self._last_error = last_error


def test_persist_streaming_error_message_clears_pending_and_saves():
    session = Session()
    materialized = []

    message = persist_streaming_error_message(
        session,
        label='Authentication failed',
        message='Bad key',
        error_type='auth_mismatch',
        hint='Run hermes model',
        details='provider said no',
        timestamp_fn=lambda: 456.9,
        materialize_pending_user_turn=lambda s: materialized.append(s),
    )

    assert materialized == [session]
    assert session.active_stream_id is None
    assert session.pending_user_message is None
    assert session.pending_attachments == []
    assert session.pending_started_at is None
    assert session.saved == 1
    assert session.messages == [message]
    assert message == {
        'role': 'assistant',
        'content': '**Authentication failed:** Bad key\n\n*Run hermes model*',
        'timestamp': 456,
        '_error': True,
        'provider_details': 'provider said no',
    }


def test_persist_streaming_error_message_labels_cancel_and_interruption_details():
    session = Session()

    persist_streaming_error_message(
        session,
        label='Cancelled',
        message='Task cancelled',
        error_type='cancelled',
        timestamp_fn=lambda: 1,
    )
    persist_streaming_error_message(
        session,
        label='Interrupted',
        message='Response interrupted',
        error_type='interrupted',
        timestamp_fn=lambda: 2,
    )

    assert session.messages[0]['provider_details_label'] == 'Cancellation details'
    assert session.messages[1]['provider_details_label'] == 'Interruption details'


def test_format_streaming_error_content_can_preserve_empty_hint_section():
    assert format_streaming_error_content(
        'No response',
        'No response.',
        always_include_hint=True,
    ) == '**No response:** No response.\n\n**'


def test_provider_details_label_ignores_regular_errors():
    assert provider_details_label('auth_mismatch') is None


def test_persist_streaming_error_message_logs_save_failure():
    class FailingSession(Session):
        def save(self):
            raise RuntimeError('disk full')

    logger = Logger()
    session = FailingSession()

    persist_streaming_error_message(
        session,
        label='Error',
        message='boom',
        error_type='error',
        logger=logger,
    )

    assert logger.messages
    assert session.messages[-1]['_error'] is True


def test_emit_and_persist_streaming_error_emits_then_persists_payload():
    events = []

    class RecordingSession(Session):
        def save(self):
            events.append('save')
            super().save()

    session = RecordingSession()

    payload = emit_and_persist_streaming_error(
        session,
        label='No response',
        message='No response.',
        error_type='no_response',
        hint='Try again',
        put=lambda event, data: events.append(('put', event, data)),
        provider_error_payload=lambda message, error_type, hint: events.append(
            ('payload', message, error_type, hint)
        ) or {'message': 'Payload message', 'details': 'provider details'},
        finalize_product_turn=lambda **kwargs: events.append(('finalize', kwargs)),
        always_include_hint=True,
        materialize_pending_user_turn=lambda current: events.append(('materialize', current)),
    )

    assert payload == {'message': 'Payload message', 'details': 'provider details'}
    assert events == [
        ('payload', 'No response.', 'no_response', 'Try again'),
        ('finalize', {
            'failed': True,
            'error_type': 'no_response',
            'error_message': 'Payload message',
        }),
        ('put', 'apperror', payload),
        ('materialize', session),
        'save',
    ]
    assert session.messages[-1] == {
        'role': 'assistant',
        'content': '**No response:** Payload message\n\n*Try again*',
        'timestamp': session.messages[-1]['timestamp'],
        '_error': True,
        'provider_details': 'provider details',
    }


def test_classify_silent_failure_error_prefers_agent_last_error():
    state = classify_silent_failure_error(
        Agent(last_error=RuntimeError('401 bad key')),
        {'error': 'fallback'},
        classify_provider_error=lambda error_text, last_error, **kwargs: {
            'label': 'Auth failed',
            'type': 'auth_mismatch',
            'hint': 'Run hermes model',
            'seen': (error_text, last_error, kwargs),
        },
    )

    assert state.error_text == '401 bad key'
    assert isinstance(state.last_error, RuntimeError)
    assert state.label == 'Auth failed'
    assert state.error_type == 'auth_mismatch'
    assert state.hint == 'Run hermes model'
    assert state.is_auth is True
    assert state.classification['seen'][0] == '401 bad key'
    assert state.classification['seen'][2] == {'silent_failure': False}


def test_classify_silent_failure_error_marks_empty_result_as_silent_failure():
    state = classify_silent_failure_error(
        Agent(),
        {},
        classify_provider_error=lambda error_text, last_error, **kwargs: {
            'label': 'No response',
            'type': 'no_response',
            'hint': 'Try again',
            'seen': (error_text, last_error, kwargs),
        },
    )

    assert state.error_text == ''
    assert state.last_error == ''
    assert state.is_auth is False
    assert state.classification['seen'] == ('', '', {'silent_failure': True})


def test_emit_and_persist_silent_failure_error_uses_classified_state():
    events = []
    session = Session()
    state = classify_silent_failure_error(
        Agent(),
        {},
        classify_provider_error=lambda *_args, **_kwargs: {
            'label': 'No response from provider',
            'type': 'no_response',
            'hint': 'Provider returned no content',
        },
    )

    payload = emit_and_persist_silent_failure_error(
        session,
        state,
        put=lambda event, data: events.append(('put', event, data)),
        provider_error_payload=lambda message, error_type, hint: events.append(
            ('payload', message, error_type, hint)
        ) or {'message': 'No response payload', 'type': error_type},
        finalize_product_turn=lambda **kwargs: events.append(('finalize', kwargs)),
        materialize_pending_user_turn=lambda current: events.append(('materialize', current)),
    )

    assert payload == {'message': 'No response payload', 'type': 'no_response'}
    assert events == [
        ('payload', 'No response from provider.', 'no_response', 'Provider returned no content'),
        ('finalize', {
            'failed': True,
            'error_type': 'no_response',
            'error_message': 'No response payload',
        }),
        ('put', 'apperror', payload),
        ('materialize', session),
    ]
    assert session.saved == 1
    assert session.messages[-1]['content'] == '**No response from provider:** No response payload\n\n*Provider returned no content*'


def test_emit_and_persist_exception_streaming_error_persists_before_emitting():
    events = []
    session = Session()

    ok = emit_and_persist_exception_streaming_error(
        session,
        err_str='raw provider error',
        label='Error',
        error_type='error',
        hint='',
        stream_id='stream-1',
        session_id='sid-1',
        ephemeral=False,
        agent_lock=None,
        checkpoint_stop='stop',
        checkpoint_thread='thread',
        stop_checkpoint_thread=lambda stop, thread: events.append(('stop', stop, thread)),
        stream_writeback_is_current=lambda session_arg, stream_id: session_arg.active_stream_id == stream_id,
        provider_error_payload=lambda message, error_type, hint: {
            'message': 'payload message',
            'type': error_type,
            'details': message,
        },
        finalize_product_turn=lambda **kwargs: events.append(('finalize', kwargs)),
        put=lambda event, data: events.append(('put', event, data)),
        append_interrupted_turn_event=lambda *args, **kwargs: events.append(('journal', args, kwargs)),
        materialize_pending_user_turn=lambda current: events.append(('materialize', current)),
    )

    assert ok is True
    assert session.saved == 1
    assert events == [
        ('stop', 'stop', 'thread'),
        ('materialize', session),
        ('journal', ('sid-1', 'stream-1'), {'reason': 'error', 'logger': None}),
        ('finalize', {
            'failed': True,
            'error_type': 'error',
            'error_message': 'payload message',
        }),
        ('put', 'apperror', {
            'message': 'payload message',
            'type': 'error',
            'details': 'raw provider error',
        }),
    ]
    assert session.messages[-1]['content'] == '**Error:** payload message'
    assert session.messages[-1]['provider_details'] == 'raw provider error'


def test_emit_and_persist_exception_streaming_error_skips_stale_stream_writeback():
    events = []
    session = Session()
    session.active_stream_id = 'newer-stream'

    ok = emit_and_persist_exception_streaming_error(
        session,
        err_str='raw provider error',
        label='Error',
        error_type='error',
        hint='',
        stream_id='stream-1',
        session_id='sid-1',
        ephemeral=False,
        agent_lock=None,
        checkpoint_stop=None,
        checkpoint_thread=None,
        stop_checkpoint_thread=lambda *_args: events.append('stop'),
        stream_writeback_is_current=lambda session_arg, stream_id: session_arg.active_stream_id == stream_id,
        provider_error_payload=lambda message, error_type, hint: {'message': message, 'type': error_type},
        finalize_product_turn=lambda **kwargs: events.append(('finalize', kwargs)),
        put=lambda event, data: events.append(('put', event, data)),
        append_interrupted_turn_event=lambda *args, **kwargs: events.append(('journal', args, kwargs)),
        logger=Logger(),
    )

    assert ok is False
    assert session.saved == 0
    assert events == ['stop']


def test_emit_and_persist_exception_streaming_error_emits_without_session():
    events = []

    ok = emit_and_persist_exception_streaming_error(
        None,
        err_str='raw provider error',
        label='Error',
        error_type='error',
        hint='',
        stream_id='stream-1',
        session_id='sid-1',
        ephemeral=False,
        agent_lock=None,
        checkpoint_stop=None,
        checkpoint_thread=None,
        stop_checkpoint_thread=lambda *_args: events.append('stop'),
        stream_writeback_is_current=lambda *_args: False,
        provider_error_payload=lambda message, error_type, hint: {'message': message, 'type': error_type},
        finalize_product_turn=lambda **kwargs: events.append(('finalize', kwargs)),
        put=lambda event, data: events.append(('put', event, data)),
        append_interrupted_turn_event=lambda *args, **kwargs: events.append(('journal', args, kwargs)),
    )

    assert ok is True
    assert events == [
        ('finalize', {
            'failed': True,
            'error_type': 'error',
            'error_message': 'raw provider error',
        }),
        ('put', 'apperror', {'message': 'raw provider error', 'type': 'error'}),
    ]

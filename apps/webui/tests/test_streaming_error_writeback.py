from api.streaming_error_writeback import (
    emit_and_persist_streaming_error,
    format_streaming_error_content,
    persist_streaming_error_message,
    provider_details_label,
)


class Session:
    def __init__(self):
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

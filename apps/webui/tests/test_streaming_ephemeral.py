import threading

from api.streaming_ephemeral import emit_ephemeral_done, latest_assistant_answer


def test_latest_assistant_answer_uses_last_assistant_message():
    assert latest_assistant_answer([
        {'role': 'assistant', 'content': 'first'},
        {'role': 'user', 'content': 'again'},
        {'role': 'assistant', 'content': 'final'},
    ]) == 'final'


def test_latest_assistant_answer_returns_empty_string_without_assistant():
    assert latest_assistant_answer([{'role': 'user', 'content': 'question'}]) == ''


def test_emit_ephemeral_done_emits_answer_stops_checkpoint_and_unlinks_session(tmp_path):
    session_path = tmp_path / "ephemeral.json"
    session_path.write_text("{}", encoding="utf-8")
    stop = threading.Event()
    events = []
    result = {
        'messages': [
            {'role': 'assistant', 'content': 'older'},
            {'role': 'assistant', 'content': 'answer'},
        ],
    }

    emit_ephemeral_done(
        result,
        session_id='sid-1',
        session_path=str(session_path),
        checkpoint_stop=stop,
        put=lambda event, data: events.append((event, data)),
    )

    assert stop.is_set()
    assert not session_path.exists()
    assert events == [
        (
            'done',
            {
                'session': {'session_id': 'sid-1', 'messages': result['messages']},
                'usage': {'input_tokens': 0, 'output_tokens': 0},
                'ephemeral': True,
                'answer': 'answer',
            },
        ),
    ]

import threading
from types import SimpleNamespace

from api.streaming_ephemeral import (
    emit_ephemeral_done,
    handle_completed_conversation_post_run,
    latest_assistant_answer,
)


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


def test_handle_completed_conversation_post_run_returns_on_cancel_before_ephemeral_done():
    calls = []
    result = handle_completed_conversation_post_run(
        {"messages": []},
        session=SimpleNamespace(path="/tmp/unused"),
        session_id="sid-1",
        stream_id="stream-1",
        cancel_event="cancel",
        agent_lock="lock",
        finalize_cancelled_turn="finalize",
        put_cancel="put-cancel",
        ephemeral=True,
        checkpoint_stop="stop",
        checkpoint_thread="thread",
        put=lambda *_args: calls.append("put"),
        handle_post_run_cancel=lambda *args, **kwargs: calls.append(("cancel", args, kwargs)) or True,
        stop_checkpoint_thread_fn=lambda *_args: calls.append("stop-checkpoint"),
        emit_ephemeral_done_fn=lambda *_args, **_kwargs: calls.append("ephemeral-done"),
    )

    assert result is True
    assert calls[0][0] == "cancel"
    assert "ephemeral-done" not in calls
    assert "stop-checkpoint" not in calls


def test_handle_completed_conversation_post_run_emits_ephemeral_done_without_stopping_twice():
    calls = []
    result = handle_completed_conversation_post_run(
        {"messages": [{"role": "assistant", "content": "hi"}]},
        session=SimpleNamespace(path="/tmp/ephemeral.json"),
        session_id="sid-1",
        stream_id="stream-1",
        cancel_event="cancel",
        agent_lock="lock",
        finalize_cancelled_turn="finalize",
        put_cancel="put-cancel",
        ephemeral=True,
        checkpoint_stop="stop",
        checkpoint_thread="thread",
        put=lambda *_args: calls.append("put"),
        handle_post_run_cancel=lambda *args, **kwargs: (calls.append(("cancel", kwargs)), False)[1],
        stop_checkpoint_thread_fn=lambda *_args: calls.append("stop-checkpoint"),
        emit_ephemeral_done_fn=lambda *args, **kwargs: calls.append(("ephemeral-done", args, kwargs)),
    )

    assert result is True
    assert calls[0][0] == "cancel"
    assert calls[1][0] == "ephemeral-done"
    assert calls[1][2]["session_id"] == "sid-1"
    assert calls[1][2]["checkpoint_stop"] == "stop"
    assert "stop-checkpoint" not in calls


def test_handle_completed_conversation_post_run_stops_checkpoint_before_success_writeback():
    calls = []
    cancel_results = iter([False, False])

    result = handle_completed_conversation_post_run(
        {"messages": []},
        session=SimpleNamespace(path="/tmp/session.json"),
        session_id="sid-1",
        stream_id="stream-1",
        cancel_event="cancel",
        agent_lock="lock",
        finalize_cancelled_turn="finalize",
        put_cancel="put-cancel",
        ephemeral=False,
        checkpoint_stop="stop",
        checkpoint_thread="thread",
        put=lambda *_args: calls.append("put"),
        handle_post_run_cancel=lambda *args, **kwargs: calls.append(("cancel", kwargs)) or next(cancel_results),
        stop_checkpoint_thread_fn=lambda stop, thread: calls.append(("stop-checkpoint", stop, thread)),
        emit_ephemeral_done_fn=lambda *_args, **_kwargs: calls.append("ephemeral-done"),
    )

    assert result is False
    assert [call[0] for call in calls] == ["cancel", "stop-checkpoint", "cancel"]
    assert calls[1] == ("stop-checkpoint", "stop", "thread")

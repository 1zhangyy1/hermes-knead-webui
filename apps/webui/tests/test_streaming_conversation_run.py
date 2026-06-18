from types import SimpleNamespace

from api.streaming_conversation_run import run_agent_conversation_and_handle_post_run


class Agent:
    def __init__(self, events):
        self.events = events

    def run_conversation(self, **kwargs):
        self.events.append(('run', kwargs))
        return {'messages': [{'role': 'assistant', 'content': 'ok'}]}


def _base_kwargs(events, **overrides):
    kwargs = {
        'agent': Agent(events),
        'user_message': {'role': 'user', 'content': 'hello'},
        'system_message': 'system',
        'previous_context_messages': [{'role': 'user', 'content': 'hello'}],
        'config': {'cfg': True},
        'session': SimpleNamespace(path='/tmp/session.json'),
        'session_id': 'sid-1',
        'stream_id': 'stream-1',
        'cancel_event': 'cancel',
        'agent_lock': 'lock',
        'finalize_cancelled_turn': lambda *_args, **_kwargs: events.append('finalize-cancel'),
        'put_cancel': lambda: events.append('put-cancel'),
        'ephemeral': False,
        'checkpoint_stop': 'stop',
        'checkpoint_thread': 'thread',
        'put': lambda event, payload: events.append(('put', event, payload)),
        'msg_text': 'hello',
        'sanitize_messages_for_api': lambda messages, *, cfg: events.append(
            ('sanitize', messages, cfg)
        ) or [{'role': 'user', 'content': 'sanitized'}],
        'handle_post_run_cancel': lambda *_args, **_kwargs: False,
        'stop_checkpoint_thread': lambda stop, thread: events.append(('stop', stop, thread)),
        'logger': SimpleNamespace(info=lambda *_args, **_kwargs: None),
    }
    kwargs.update(overrides)
    return kwargs


def test_run_agent_conversation_sanitizes_history_and_returns_result():
    events = []

    result = run_agent_conversation_and_handle_post_run(
        **_base_kwargs(
            events,
            handle_completed_conversation_post_run_fn=lambda result, **kwargs: events.append(
                ('post-run', result, kwargs['checkpoint_stop'])
            ) or False,
        ),
    )

    assert result.should_return is False
    assert result.result == {'messages': [{'role': 'assistant', 'content': 'ok'}]}
    assert events[0] == ('sanitize', [{'role': 'user', 'content': 'hello'}], {'cfg': True})
    assert events[1][0] == 'run'
    assert events[1][1]['conversation_history'] == [{'role': 'user', 'content': 'sanitized'}]
    assert events[1][1]['persist_user_message'] == 'hello'
    assert events[2] == ('post-run', {'messages': [{'role': 'assistant', 'content': 'ok'}]}, 'stop')


def test_run_agent_conversation_returns_when_post_run_gate_handles_turn():
    events = []

    result = run_agent_conversation_and_handle_post_run(
        **_base_kwargs(
            events,
            handle_completed_conversation_post_run_fn=lambda *_args, **_kwargs: True,
        ),
    )

    assert result.should_return is True
    assert result.result == {'messages': [{'role': 'assistant', 'content': 'ok'}]}

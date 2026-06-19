import api.streaming_worker_state as state


def test_current_checkpoint_handles_prefers_live_checkpoint_state():
    checkpoint_stop, checkpoint_thread = state.current_checkpoint_handles(
        {'stop': 'new-stop', 'thread': 'new-thread'},
        'old-stop',
        'old-thread',
    )

    assert checkpoint_stop == 'new-stop'
    assert checkpoint_thread == 'new-thread'


def test_current_checkpoint_handles_falls_back_to_known_handles():
    checkpoint_stop, checkpoint_thread = state.current_checkpoint_handles(
        {},
        'old-stop',
        'old-thread',
    )

    assert checkpoint_stop == 'old-stop'
    assert checkpoint_thread == 'old-thread'


def test_exception_runtime_vars_lets_setup_state_override_worker_locals():
    runtime_vars = state.exception_runtime_vars(
        {'_AIAgent': 'stale-agent', 'msg_text': 'hello'},
        {'_AIAgent': 'current-agent', '_agent_kwargs': {'api_key': 'key'}},
    )

    assert runtime_vars['_AIAgent'] == 'current-agent'
    assert runtime_vars['msg_text'] == 'hello'
    assert runtime_vars['_agent_kwargs'] == {'api_key': 'key'}

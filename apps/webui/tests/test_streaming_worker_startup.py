from pathlib import Path
from types import SimpleNamespace

import pytest

from api.streaming_worker_startup import prepare_streaming_worker_startup


class Session:
    def __init__(self):
        self.session_id = 'sid-1'
        self.workspace = ''
        self.model = ''
        self.model_provider = 'old-provider'


def _base_kwargs(events, session=None, **overrides):
    session = session or Session()
    kwargs = {
        'session_id': 'sid-1',
        'stream_id': 'stream-1',
        'workspace': '/tmp/workspace',
        'model': 'model-a',
        'model_provider': '  OpenRouter  ',
        'ephemeral': False,
        'cancel_event': object(),
        'put': lambda event, payload: events.append(('put', event, payload)),
        'get_session': lambda session_id: events.append(('get_session', session_id)) or session,
        'update_active_run': lambda *args, **kwargs: events.append(('update_active_run', args, kwargs)),
        'get_session_agent_lock': lambda session_id: events.append(('lock', session_id)) or 'lock',
        'handle_preflight_cancel': lambda *args, **kwargs: events.append(('preflight', kwargs)) or False,
        'finalize_cancelled_turn': lambda *args, **kwargs: events.append(('finalize_cancel',)),
        'put_cancel': lambda: events.append(('put_cancel',)),
        'set_thread_env': lambda **kwargs: events.append(('set_thread_env', kwargs)),
        'env_lock': object(),
        'logger': SimpleNamespace(debug=lambda *args, **kwargs: None),
        'activate_streaming_profile_runtime_fn': lambda session, **kwargs: events.append(
            ('activate_profile', session.session_id, kwargs['workspace'])
        ) or SimpleNamespace(
            profile_home='/profile/home',
            resolved_profile_name='profile-a',
            profile_env_snapshot={'PROFILE_KEY': 'old'},
            runtime_env_snapshot={'HERMES_HOME': 'old-home'},
        ),
        'register_streaming_gateway_notifications_fn': lambda session_id, **kwargs: events.append(
            ('register_gateway', session_id)
        ) or 'gateway',
        'restore_agent_process_env_fn': lambda profile_env, runtime_env, *, env_lock: events.append(
            ('restore_env', profile_env, runtime_env, env_lock)
        ),
    }
    kwargs.update(overrides)
    return kwargs


def test_prepare_streaming_worker_startup_orders_session_profile_and_gateway():
    events = []
    session = Session()

    result = prepare_streaming_worker_startup(
        **_base_kwargs(events, session=session),
    )

    assert result.should_return is False
    assert result.session is session
    assert result.agent_lock == 'lock'
    assert result.provider_context == 'openrouter'
    assert result.profile_home == '/profile/home'
    assert result.resolved_profile_name == 'profile-a'
    assert result.profile_env_snapshot == {'PROFILE_KEY': 'old'}
    assert result.runtime_env_snapshot == {'HERMES_HOME': 'old-home'}
    assert result.gateway_notifications == 'gateway'
    assert session.workspace == str(Path('/tmp/workspace').expanduser().resolve())
    assert session.model == 'model-a'
    assert session.model_provider == 'openrouter'
    assert [event[0] for event in events] == [
        'get_session',
        'update_active_run',
        'lock',
        'preflight',
        'activate_profile',
        'register_gateway',
    ]


def test_prepare_streaming_worker_startup_returns_before_profile_when_preflight_cancelled():
    events = []

    result = prepare_streaming_worker_startup(
        **_base_kwargs(
            events,
            handle_preflight_cancel=lambda *args, **kwargs: events.append(('preflight', kwargs)) or True,
        ),
    )

    assert result.should_return is True
    assert result.session is not None
    assert result.agent_lock == 'lock'
    assert result.provider_context == 'openrouter'
    assert [event[0] for event in events] == [
        'get_session',
        'update_active_run',
        'lock',
        'preflight',
    ]


def test_prepare_streaming_worker_startup_restores_profile_env_when_gateway_registration_fails():
    events = []
    env_lock = object()

    with pytest.raises(RuntimeError, match='gateway boom'):
        prepare_streaming_worker_startup(
            **_base_kwargs(
                events,
                env_lock=env_lock,
                register_streaming_gateway_notifications_fn=lambda *args, **kwargs: (_ for _ in ()).throw(
                    RuntimeError('gateway boom')
                ),
            ),
        )

    assert ('restore_env', {'PROFILE_KEY': 'old'}, {'HERMES_HOME': 'old-home'}, env_lock) in events

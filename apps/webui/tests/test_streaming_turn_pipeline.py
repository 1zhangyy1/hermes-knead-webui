from types import SimpleNamespace

from api.streaming_turn_pipeline import run_streaming_turn_pipeline


def _agent_setup():
    return SimpleNamespace(
        agent='agent',
        agent_sig='sig-1',
        agent_factory='AgentFactory',
        agent_kwargs={'api_key': 'old'},
        agent_params={'session_db'},
        config={'agent': {}},
        runtime={'provider': 'old'},
        resolved_api_key='old-key',
        resolved_model='model-a',
        resolved_provider='provider-a',
        resolved_base_url='https://old.test',
        output_bridge=SimpleNamespace(token_sent=False),
        live_tool_calls=[],
        checkpoint_activity=[0],
    )


def _turn_input():
    return SimpleNamespace(
        system_message='system',
        user_message={'role': 'user', 'content': 'hello'},
        turn_start=SimpleNamespace(
            started_at=123,
            previous_messages=['display'],
            previous_context_messages=['context'],
            pre_compression_count=1,
        ),
        checkpoint_runner=SimpleNamespace(stop_event='stop', thread='thread'),
    )


def _success_result(**overrides):
    result = SimpleNamespace(
        should_return=False,
        result={'messages': [{'role': 'assistant', 'content': 'ok'}]},
        runtime={'provider': 'new'},
        resolved_api_key='new-key',
        resolved_provider='provider-b',
        resolved_base_url='https://new.test',
        agent_kwargs={'api_key': 'new'},
        agent='agent-b',
        self_healed=True,
    )
    for key, value in overrides.items():
        setattr(result, key, value)
    return result


def _base_kwargs(events, runtime_state=None, checkpoint_state=None, **overrides):
    kwargs = {
        'agent_setup': _agent_setup(),
        'session': SimpleNamespace(workspace='workspace', personality='kind'),
        'session_id': 'sid-1',
        'stream_id': 'stream-1',
        'msg_text': 'hello',
        'attachments': [],
        'workspace': 'workspace',
        'product_context': {'id': 'product'},
        'model': 'model-a',
        'profile_home': '/profiles/default',
        'resolved_profile_name': 'default',
        'run_state': SimpleNamespace(live_usage_snapshot=lambda: {'tokens': 1}),
        'cancel_event': 'cancel',
        'agent_lock': 'lock',
        'ephemeral': False,
        'goal_related': False,
        'put': lambda event, payload: events.append(('put', event, payload)),
        'pending_goal_continuation': {},
        'redact_session_data': lambda raw: raw,
        'build_done_usage_payload': lambda *args, **kwargs: {'usage': True},
        'apply_context_window_to_usage': lambda *args, **kwargs: None,
        'drain_pending_steer_leftover': lambda *args, **kwargs: None,
        'run_post_turn_goal_hook': lambda *args, **kwargs: None,
        'finalize_product_turn': lambda **kwargs: events.append(('finalize-product', kwargs)),
        'meter_stats_fn': lambda: {},
        'run_background_title_update': lambda *args, **kwargs: None,
        'maybe_schedule_title_refresh': lambda *args, **kwargs: None,
        'finalize_cancelled_turn': lambda *args, **kwargs: events.append('finalize-cancel'),
        'put_cancel': lambda *args, **kwargs: events.append('put-cancel'),
        'handle_post_run_cancel': lambda *args, **kwargs: False,
        'stop_checkpoint_thread': lambda *args, **kwargs: events.append(('stop', args)),
        'sanitize_messages_for_api': lambda messages, *, cfg: messages,
        'stream_writeback_is_current': lambda *args, **kwargs: True,
        'classify_provider_error': lambda *args, **kwargs: {'type': 'error'},
        'provider_error_payload': lambda *args, **kwargs: {},
        'append_interrupted_turn_event': lambda *args, **kwargs: None,
        'materialize_pending_user_turn': lambda *args, **kwargs: None,
        'has_new_assistant_reply': lambda *args, **kwargs: True,
        'assistant_reply_added_after_current_turn': lambda *args, **kwargs: True,
        'preserve_pre_compression_snapshot': lambda *args, **kwargs: None,
        'compression_anchor_message_key': lambda *args, **kwargs: None,
        'compact_summary_text': lambda *args, **kwargs: None,
        'compression_summary_from_messages': lambda *args, **kwargs: None,
        'title_from_fn': lambda *args, **kwargs: 'title',
        'is_provisional_title': lambda *args, **kwargs: False,
        'looks_invalid_generated_title': lambda *args, **kwargs: False,
        'first_exchange_snippets': lambda *args, **kwargs: ('u', 'a'),
        'extract_gateway_routing_metadata': lambda *args, **kwargs: {},
        'custom_provider_resolver': lambda *args, **kwargs: (None, None),
        'agent_instances': {},
        'streams_lock': 'streams-lock',
        'webui_ephemeral_system_prompt': lambda *args, **kwargs: 'prompt',
        'logger': SimpleNamespace(debug=lambda *args, **kwargs: None),
        'runtime_state': runtime_state if runtime_state is not None else {},
        'checkpoint_state': checkpoint_state if checkpoint_state is not None else {},
        'prepare_streaming_turn_input_fn': lambda **kwargs: events.append(
            ('turn-input', kwargs['checkpoint_activity'])
        ) or _turn_input(),
        'run_agent_conversation_and_handle_post_run_fn': lambda **kwargs: events.append(
            ('run', kwargs['checkpoint_stop'], kwargs['checkpoint_thread'])
        ) or SimpleNamespace(result={'messages': []}, should_return=False),
        'handle_completed_conversation_writeback_fn': lambda *args, **kwargs: events.append(
            ('writeback', kwargs['previous_messages'], kwargs['pre_compression_count'])
        ) or SimpleNamespace(completed_turn_state='completed', should_return=False),
        'handle_completed_conversation_success_fn': lambda *args, **kwargs: events.append(
            ('success', kwargs['profile_home'], kwargs['resolved_provider'])
        ) or _success_result(),
    }
    kwargs.update(overrides)
    return kwargs


def test_run_streaming_turn_pipeline_runs_writeback_before_success_and_updates_state():
    events = []
    runtime_state = {}
    checkpoint_state = {}

    result = run_streaming_turn_pipeline(
        **_base_kwargs(events, runtime_state=runtime_state, checkpoint_state=checkpoint_state),
    )

    assert result.should_return is False
    assert result.agent == 'agent-b'
    assert result.self_healed is True
    assert result.resolved_provider == 'provider-b'
    assert result.checkpoint_stop == 'stop'
    assert result.checkpoint_thread == 'thread'
    assert checkpoint_state == {'stop': 'stop', 'thread': 'thread'}
    assert [event[0] for event in events] == ['turn-input', 'run', 'writeback', 'success']
    assert runtime_state['workspace_system_msg'] == 'system'
    assert runtime_state['user_message'] == {'role': 'user', 'content': 'hello'}
    assert runtime_state['_previous_messages'] == ['display']
    assert runtime_state['_previous_context_messages'] == ['context']
    assert runtime_state['_self_healed'] is True


def test_run_streaming_turn_pipeline_returns_before_writeback_when_post_run_handles_turn():
    events = []

    result = run_streaming_turn_pipeline(
        **_base_kwargs(
            events,
            run_agent_conversation_and_handle_post_run_fn=lambda **kwargs: events.append('run')
            or SimpleNamespace(result={'messages': []}, should_return=True),
        ),
    )

    assert result.should_return is True
    assert result.checkpoint_stop == 'stop'
    assert events == [('turn-input', [0]), 'run']

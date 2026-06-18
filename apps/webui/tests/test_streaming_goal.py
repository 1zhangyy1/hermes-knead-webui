from types import SimpleNamespace

from api.streaming_goal import last_assistant_response_text, run_post_turn_goal_hook


def test_last_assistant_response_text_handles_string_and_parts():
    messages = [
        {'role': 'assistant', 'content': 'old'},
        {'role': 'user', 'content': 'continue'},
        {'role': 'assistant', 'content': [{'text': 'new'}, {'content': 'answer'}, {'type': 'image'}]},
    ]

    assert last_assistant_response_text(messages) == 'new\nanswer'


def test_run_post_turn_goal_hook_skips_unrelated_turns():
    events = []
    pending = set()

    decision = run_post_turn_goal_hook(
        SimpleNamespace(messages=[{'role': 'assistant', 'content': 'done'}]),
        session_id='sid-1',
        profile_home=None,
        goal_related=False,
        put=lambda event, data: events.append((event, data)),
        pending_goal_continuation=pending,
        has_active_goal_fn=lambda *args, **kwargs: True,
        evaluate_goal_after_turn_fn=lambda *args, **kwargs: {'should_continue': True},
    )

    assert decision == {}
    assert events == []
    assert pending == set()


def test_run_post_turn_goal_hook_emits_status_and_continuation():
    events = []
    pending = set()

    decision = run_post_turn_goal_hook(
        SimpleNamespace(messages=[{'role': 'assistant', 'content': 'not finished'}]),
        session_id='sid-1',
        profile_home='/profile',
        goal_related=True,
        put=lambda event, data: events.append((event, data)),
        pending_goal_continuation=pending,
        has_active_goal_fn=lambda session_id, profile_home=None: True,
        evaluate_goal_after_turn_fn=lambda *args, **kwargs: {
            'should_continue': True,
            'continuation_prompt': 'keep going',
            'message': 'Continuing',
            'message_key': 'goal_continuing',
            'message_args': ['x'],
        },
    )

    assert decision['should_continue'] is True
    assert pending == {'sid-1'}
    assert [event for event, _ in events] == ['goal', 'goal', 'goal_continue']
    assert events[0][1]['state'] == 'evaluating'
    assert events[0][1]['message'] == 'Evaluating goal progress\u2026'
    assert events[2][1]['continuation_prompt'] == 'keep going'

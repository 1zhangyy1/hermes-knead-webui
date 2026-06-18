from types import SimpleNamespace

from api.streaming_title_writeback import (
    prepare_completed_turn_title,
    title_is_default,
)


def _session(title='Untitled', *, llm_title_generated=False):
    return SimpleNamespace(
        title=title,
        llm_title_generated=llm_title_generated,
        messages=[
            {'role': 'user', 'content': 'Explain the plan'},
            {'role': 'assistant', 'content': 'Here is the plan'},
            {'role': 'assistant', 'content': 'old timestamp', 'timestamp': 123},
            {'role': 'assistant', 'content': 'legacy ts', '_ts': 456},
        ],
    )


def test_title_is_default_covers_untitled_new_chat_and_empty_values():
    assert title_is_default('Untitled') is True
    assert title_is_default('New Chat') is True
    assert title_is_default('') is True
    assert title_is_default(None) is True
    assert title_is_default('User title') is False


def test_prepare_completed_turn_title_stamps_missing_timestamps_and_sets_default_title():
    session = _session('New Chat')

    plan = prepare_completed_turn_title(
        session,
        timestamp_fn=lambda: 999.8,
        title_from_fn=lambda messages, title: 'Explain the plan',
        is_provisional_title=lambda title, messages: True,
        looks_invalid_generated_title=lambda title: False,
        first_exchange_snippets=lambda messages: ('Explain the plan', 'Here is the plan'),
    )

    assert session.title == 'Explain the plan'
    assert session.messages[0]['timestamp'] == 999
    assert session.messages[1]['timestamp'] == 999
    assert session.messages[2]['timestamp'] == 123
    assert session.messages[3]['_ts'] == 456
    assert 'timestamp' not in session.messages[3]
    assert plan.should_background_title is True
    assert plan.user_text == 'Explain the plan'
    assert plan.assistant_text == 'Here is the plan'


def test_prepare_completed_turn_title_preserves_user_title_and_skips_generated_title():
    session = _session('Hand-written title', llm_title_generated=True)

    plan = prepare_completed_turn_title(
        session,
        timestamp_fn=lambda: 1,
        title_from_fn=lambda messages, title: 'Should not be used',
        is_provisional_title=lambda title, messages: False,
        looks_invalid_generated_title=lambda title: False,
        first_exchange_snippets=lambda messages: ('u', 'a'),
    )

    assert session.title == 'Hand-written title'
    assert plan.should_background_title is False
    assert plan.user_text == ''
    assert plan.assistant_text == ''


def test_prepare_completed_turn_title_refreshes_invalid_generated_title():
    session = _session('All set', llm_title_generated=True)

    plan = prepare_completed_turn_title(
        session,
        timestamp_fn=lambda: 1,
        title_from_fn=lambda messages, title: 'Should not be used',
        is_provisional_title=lambda title, messages: False,
        looks_invalid_generated_title=lambda title: True,
        first_exchange_snippets=lambda messages: ('User text', 'Assistant text'),
    )

    assert session.title == 'All set'
    assert plan.should_background_title is True
    assert plan.user_text == 'User text'
    assert plan.assistant_text == 'Assistant text'

from api.streaming_attachments import tag_matching_user_message_attachments


def test_tag_matching_user_message_attachments_uses_base_text_before_suffix():
    messages = [
        {'role': 'user', 'content': 'please inspect screenshot'},
        {'role': 'assistant', 'content': 'sure'},
    ]

    changed = tag_matching_user_message_attachments(
        messages,
        'please inspect screenshot\n\n[Attached files: screenshot.png]',
        [{'name': 'screenshot.png'}],
    )

    assert changed is True
    assert messages[0]['attachments'] == ['screenshot.png']


def test_tag_matching_user_message_attachments_tags_latest_matching_user():
    messages = [
        {'role': 'user', 'content': 'old request'},
        {'role': 'assistant', 'content': 'done'},
        {'role': 'user', 'content': 'current request'},
    ]

    changed = tag_matching_user_message_attachments(
        messages,
        'current request\n\n[Attached files: current.png]',
        [{'filename': 'current.png'}],
    )

    assert changed is True
    assert 'attachments' not in messages[0]
    assert messages[2]['attachments'] == ['current.png']


def test_tag_matching_user_message_attachments_skips_without_match_or_name():
    messages = [{'role': 'user', 'content': 'different request'}]

    no_match = tag_matching_user_message_attachments(
        messages,
        'current request',
        [{'name': 'current.png'}],
    )
    no_name = tag_matching_user_message_attachments(
        messages,
        'different request',
        [{}],
    )

    assert no_match is False
    assert no_name is False
    assert messages == [{'role': 'user', 'content': 'different request'}]

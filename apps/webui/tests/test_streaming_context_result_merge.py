from api.streaming_context import apply_agent_result_to_session


class _Session:
    pass


def test_apply_agent_result_to_session_updates_context_and_visible_messages():
    session = _Session()
    previous_messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi", "reasoning": "kept"},
    ]
    previous_context = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi", "reasoning": "context-kept"},
    ]
    result_messages = previous_context + [
        {"role": "user", "content": "next"},
        {"role": "assistant", "content": "answer"},
    ]
    strip_calls = []

    returned = apply_agent_result_to_session(
        session,
        previous_messages,
        previous_context,
        result_messages,
        "next",
        strip_xml_tool_calls_fn=lambda messages: strip_calls.append(messages),
    )

    assert returned is result_messages
    assert session.context_messages[1]["reasoning"] == "context-kept"
    assert [m["content"] for m in session.messages] == ["hello", "hi", "next", "answer"]
    assert session.messages[1]["reasoning"] == "kept"
    assert strip_calls == [session.messages]


def test_apply_agent_result_to_session_falls_back_to_previous_context_when_result_empty():
    session = _Session()
    previous_context = [{"role": "user", "content": "hello"}]

    returned = apply_agent_result_to_session(
        session,
        [],
        previous_context,
        None,
        "next",
    )

    assert returned == previous_context
    assert session.context_messages == previous_context
    assert session.messages == []

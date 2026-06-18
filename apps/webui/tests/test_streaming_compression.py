import threading
from types import SimpleNamespace

from api.streaming_compression import handle_context_compression_side_effects


class Logger:
    def __init__(self):
        self.messages = []

    def info(self, *args, **kwargs):
        self.messages.append((args, kwargs))


def _session(session_id='old-session'):
    return SimpleNamespace(
        session_id=session_id,
        profile=None,
        parent_session_id='fork-parent',
        messages=[
            {'role': 'user', 'content': 'before'},
            {'role': 'assistant', 'content': 'after'},
        ],
        context_messages=[{'role': 'system', 'content': 'summary'}],
        compression_anchor_visible_idx=None,
        compression_anchor_message_key=None,
        compression_anchor_summary=None,
    )


def test_handle_context_compression_rotates_session_state_and_emits_event():
    session = _session()
    agent = SimpleNamespace(session_id='new-session', context_compressor=None)
    sessions = {'old-session': session}
    agent_lock = object()
    session_agent_locks = {'old-session': agent_lock}
    session_agent_cache = {'old-session': ('agent', 'sig')}
    preserved = []
    events = []
    logger = Logger()

    result = handle_context_compression_side_effects(
        session,
        agent,
        original_session_id='old-session',
        resolved_profile_name='work-profile',
        agent_lock=agent_lock,
        pre_compression_count=0,
        preserve_pre_compression_snapshot=lambda s, sid: preserved.append((s, sid)),
        sessions_lock=threading.Lock(),
        sessions=sessions,
        session_agent_locks=session_agent_locks,
        session_agent_locks_lock=threading.Lock(),
        session_agent_cache=session_agent_cache,
        session_agent_cache_lock=threading.Lock(),
        visible_messages_for_anchor=lambda messages, auto_compression: messages,
        compression_anchor_message_key=lambda message: {'role': message['role']},
        compact_summary_text=lambda text: f'compact:{text}',
        compression_summary_from_messages=lambda messages: messages[-1].get('content') if messages else '',
        put=lambda event, data: events.append((event, data)),
        usage_snapshot=lambda: {'input_tokens': 7},
        logger=logger,
    )

    assert result.compressed is True
    assert result.old_session_id == 'old-session'
    assert result.new_session_id == 'new-session'
    assert session.session_id == 'new-session'
    assert session.profile == 'work-profile'
    assert session.parent_session_id == 'old-session'
    assert preserved == [(session, 'old-session')]
    assert sessions == {'new-session': session}
    assert session_agent_locks == {'new-session': agent_lock}
    assert session_agent_cache == {'new-session': ('agent', 'sig')}
    assert session.compression_anchor_visible_idx == 1
    assert session.compression_anchor_message_key == {'role': 'assistant'}
    assert session.compression_anchor_summary == 'compact:after'
    assert events == [
        (
            'compressed',
            {
                'session_id': 'new-session',
                'message': 'Context auto-compressed to continue the conversation',
                'usage': {'input_tokens': 7},
            },
        ),
    ]
    assert logger.messages


def test_handle_context_compression_detects_compressor_count_without_rotation():
    session = _session()
    agent = SimpleNamespace(
        session_id='old-session',
        context_compressor=SimpleNamespace(compression_count=2),
    )
    events = []

    result = handle_context_compression_side_effects(
        session,
        agent,
        original_session_id='old-session',
        resolved_profile_name=None,
        agent_lock=object(),
        pre_compression_count=1,
        preserve_pre_compression_snapshot=lambda *_args: None,
        sessions_lock=threading.Lock(),
        sessions={'old-session': session},
        session_agent_locks={},
        session_agent_locks_lock=threading.Lock(),
        session_agent_cache={},
        session_agent_cache_lock=threading.Lock(),
        visible_messages_for_anchor=lambda messages, auto_compression: messages[:1],
        compression_anchor_message_key=lambda message: {'content': message['content']},
        compact_summary_text=lambda text: text,
        compression_summary_from_messages=lambda messages: 'summary',
        put=lambda event, data: events.append((event, data)),
        usage_snapshot=lambda: {},
    )

    assert result.compressed is True
    assert result.old_session_id is None
    assert session.session_id == 'old-session'
    assert session.parent_session_id == 'fork-parent'
    assert session.compression_anchor_visible_idx == 0
    assert session.compression_anchor_message_key == {'content': 'before'}
    assert session.compression_anchor_summary == 'summary'
    assert events[0][0] == 'compressed'


def test_handle_context_compression_noops_when_not_compressed():
    session = _session()
    agent = SimpleNamespace(
        session_id='old-session',
        context_compressor=SimpleNamespace(compression_count=1),
    )
    events = []

    result = handle_context_compression_side_effects(
        session,
        agent,
        original_session_id='old-session',
        resolved_profile_name=None,
        agent_lock=object(),
        pre_compression_count=1,
        preserve_pre_compression_snapshot=lambda *_args: None,
        sessions_lock=threading.Lock(),
        sessions={'old-session': session},
        session_agent_locks={},
        session_agent_locks_lock=threading.Lock(),
        session_agent_cache={},
        session_agent_cache_lock=threading.Lock(),
        visible_messages_for_anchor=lambda messages, auto_compression: messages,
        compression_anchor_message_key=lambda message: message,
        compact_summary_text=lambda text: text,
        compression_summary_from_messages=lambda messages: 'summary',
        put=lambda event, data: events.append((event, data)),
        usage_snapshot=lambda: {},
    )

    assert result.compressed is False
    assert events == []
    assert session.compression_anchor_summary is None

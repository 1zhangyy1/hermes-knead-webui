"""Completed-turn title and timestamp writeback helpers for streaming."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class CompletedTurnTitlePlan:
    should_background_title: bool = False
    user_text: str = ''
    assistant_text: str = ''


def title_is_default(title) -> bool:
    return title == 'Untitled' or title == 'New Chat' or not title


def prepare_completed_turn_title(
    session,
    *,
    timestamp_fn: Callable[[], float] = time.time,
    title_from_fn,
    is_provisional_title,
    looks_invalid_generated_title,
    first_exchange_snippets,
) -> CompletedTurnTitlePlan:
    """Stamp missing message timestamps and decide whether to generate a title."""
    now = timestamp_fn()
    for message in session.messages:
        if isinstance(message, dict) and not message.get('timestamp') and not message.get('_ts'):
            message['timestamp'] = int(now)

    if title_is_default(getattr(session, 'title', None)):
        session.title = title_from_fn(session.messages, session.title)

    looks_default = title_is_default(getattr(session, 'title', None))
    looks_provisional = is_provisional_title(session.title, session.messages)
    invalid_existing_title = looks_invalid_generated_title(session.title)
    should_background_title = (
        (looks_default or looks_provisional or invalid_existing_title)
        and (not getattr(session, 'llm_title_generated', False) or invalid_existing_title)
    )

    if not should_background_title:
        return CompletedTurnTitlePlan(False, '', '')

    user_text, assistant_text = first_exchange_snippets(session.messages)
    return CompletedTurnTitlePlan(True, user_text, assistant_text)

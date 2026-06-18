"""Terminal post-done SSE events for completed WebUI streaming turns."""

from __future__ import annotations

import threading
from typing import Callable


def emit_success_post_done_events(
    session,
    *,
    original_session_id: str,
    should_background_title: bool,
    title_user_text: str,
    title_assistant_text: str,
    put: Callable[[str, dict], object],
    agent,
    meter_stats_fn: Callable[[], dict],
    run_background_title_update: Callable[..., object],
    maybe_schedule_title_refresh: Callable[..., object],
    thread_factory=threading.Thread,
) -> str:
    """Emit final metering and stream-close/title-refresh events after ``done``."""
    meter_stats = meter_stats_fn()
    meter_stats['session_id'] = original_session_id
    meter_stats.setdefault('tps_available', False)
    meter_stats.setdefault('estimated', False)
    put('metering', meter_stats)

    if should_background_title and title_user_text and title_assistant_text:
        thread_factory(
            target=run_background_title_update,
            args=(
                session.session_id,
                title_user_text,
                title_assistant_text,
                str(session.title or '').strip(),
                put,
                agent,
            ),
            daemon=True,
        ).start()
        return 'background_title'

    # Use the original session_id parameter, not session.session_id, which may
    # be rotated during context compression while the client still tracks the
    # original stream session id.
    put('stream_end', {'session_id': original_session_id})
    maybe_schedule_title_refresh(session, put, agent)
    return 'stream_end'

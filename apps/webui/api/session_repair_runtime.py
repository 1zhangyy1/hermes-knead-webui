"""Runtime adapters for interrupted-session repair helpers."""

import time

from api.session_repair import (
    append_journaled_partial_output as append_journaled_partial_output_impl,
    append_recovered_pending_turn as append_recovered_pending_turn_impl,
    apply_core_sync_or_error_marker as apply_core_sync_or_error_marker_impl,
    interrupted_recovery_marker as interrupted_recovery_marker_impl,
    repair_stale_pending as repair_stale_pending_impl,
    run_journal_has_visible_output as run_journal_has_visible_output_impl,
)


def interrupted_recovery_marker(*, recovered_output: bool = False) -> dict:
    return interrupted_recovery_marker_impl(
        recovered_output=recovered_output,
        now=time.time,
    )


def append_recovered_pending_turn(
    session,
    *,
    timestamp: int | None = None,
    append_recovered_turn_to_context,
) -> dict | None:
    return append_recovered_pending_turn_impl(
        session,
        timestamp=timestamp,
        now=time.time,
        append_recovered_turn_to_context=append_recovered_turn_to_context,
    )


def run_journal_has_visible_output(session, stream_id: str | None) -> bool:
    try:
        from api.run_journal import read_run_events
    except Exception:
        return False
    return run_journal_has_visible_output_impl(
        session,
        stream_id,
        read_run_events=read_run_events,
    )


def append_journaled_partial_output(
    session,
    stream_id: str | None,
    *,
    logger,
    find_existing_assistant_for_journal_content,
    journal_tool_already_present,
    truncate_journal_tool_args,
    dedupe_existing: bool = False,
) -> bool:
    """Recover already-emitted visible output from a dead stream journal."""
    try:
        from api.run_journal import read_run_events
    except Exception:
        logger.debug(
            "Session %s: failed to read run journal for stream %s",
            getattr(session, 'session_id', '?'),
            stream_id,
            exc_info=True,
        )
        return False
    return append_journaled_partial_output_impl(
        session,
        stream_id,
        read_run_events=read_run_events,
        logger=logger,
        now=time.time,
        find_existing_assistant_for_journal_content=find_existing_assistant_for_journal_content,
        journal_tool_already_present=journal_tool_already_present,
        truncate_journal_tool_args=truncate_journal_tool_args,
        dedupe_existing=dedupe_existing,
    )


def apply_core_sync_or_error_marker(
    session,
    core_path,
    stream_id_for_recheck=None,
    *,
    require_stream_dead=True,
    touch_updated_at=True,
    active_stream_ids,
    append_recovered_pending_turn,
    append_recovered_turn_to_context,
    append_journaled_partial_output,
    normalize_journal_recovery_text,
    run_journal_has_visible_output,
    logger,
) -> bool:
    return apply_core_sync_or_error_marker_impl(
        session,
        core_path,
        stream_id_for_recheck=stream_id_for_recheck,
        require_stream_dead=require_stream_dead,
        touch_updated_at=touch_updated_at,
        active_stream_ids=active_stream_ids,
        append_recovered_pending_turn=append_recovered_pending_turn,
        append_recovered_turn_to_context=append_recovered_turn_to_context,
        append_journaled_partial_output=append_journaled_partial_output,
        interrupted_recovery_marker=interrupted_recovery_marker,
        normalize_journal_recovery_text=normalize_journal_recovery_text,
        run_journal_has_visible_output=run_journal_has_visible_output,
        logger=logger,
        now=time.time,
    )


def repair_stale_pending(
    session,
    *,
    active_stream_ids,
    get_profile_home,
    get_session_agent_lock,
    apply_core_sync_or_error_marker,
    logger,
    grace_seconds: int,
) -> bool:
    return repair_stale_pending_impl(
        session,
        active_stream_ids=active_stream_ids,
        get_profile_home=get_profile_home,
        get_session_agent_lock=get_session_agent_lock,
        apply_core_sync_or_error_marker=apply_core_sync_or_error_marker,
        logger=logger,
        now=time.time,
        grace_seconds=grace_seconds,
    )

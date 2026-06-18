"""Session list aggregation for the WebUI sidebar."""

import json


def diag_stage(diag, name: str) -> None:
    if diag is not None:
        try:
            diag.stage(name)
        except Exception:
            pass


def _finalize_sidebar_rows(
    rows,
    *,
    prefer_fuller_snapshots_for_sidebar,
    hide_from_default_sidebar,
    strip_sidebar_internal_flags,
):
    result = prefer_fuller_snapshots_for_sidebar(rows)
    result = [s for s in result if not hide_from_default_sidebar(s)]
    strip_sidebar_internal_flags(result)
    for s in result:
        if not s.get('profile'):
            s['profile'] = 'default'
    return result


def all_sessions(
    *,
    diag=None,
    session_index_file,
    session_dir,
    sessions,
    sessions_lock,
    session_cls,
    active_stream_ids,
    index_entry_exists,
    write_session_index,
    is_streaming_session,
    session_sort_timestamp,
    prefer_fuller_snapshots_for_sidebar,
    hide_from_default_sidebar,
    strip_sidebar_internal_flags,
    enrich_sidebar_lineage_metadata,
    logger,
):
    diag_stage(diag, "all_sessions.active_streams")
    current_active_stream_ids = active_stream_ids()
    # Phase C: try index first for O(1) read; fall back to full scan
    diag_stage(diag, "all_sessions.index_exists")
    if session_index_file.exists():
        try:
            diag_stage(diag, "all_sessions.read_index")
            index = json.loads(session_index_file.read_text(encoding='utf-8'))
            diag_stage(diag, "all_sessions.prune_index")
            with sessions_lock:
                in_memory_ids = set(sessions.keys())
            index = [
                s for s in index
                if index_entry_exists(s.get('session_id'), in_memory_ids=in_memory_ids)
            ]
            backfilled = []
            for i, s in enumerate(index):
                if 'last_message_at' not in s:
                    diag_stage(diag, "all_sessions.backfill_load")
                    full = session_cls.load(s.get('session_id'))
                    if full:
                        index[i] = full.compact()
                        backfilled.append(full)
            if backfilled:
                try:
                    diag_stage(diag, "all_sessions.backfill_write")
                    write_session_index(updates=backfilled)
                except Exception:
                    logger.debug("Failed to persist last_message_at backfill")
            diag_stage(diag, "all_sessions.mark_streaming")
            for s in index:
                s['is_streaming'] = is_streaming_session(
                    s.get('active_stream_id'),
                    current_active_stream_ids,
                )
            # Overlay any in-memory sessions that may be newer than the index
            diag_stage(diag, "all_sessions.overlay_lock")
            index_map = {s['session_id']: s for s in index}
            with sessions_lock:
                for s in sessions.values():
                    index_map[s.session_id] = s.compact(
                        include_runtime=True,
                        active_stream_ids=current_active_stream_ids,
                    )
            diag_stage(diag, "all_sessions.sort_filter")
            result = sorted(
                index_map.values(),
                key=lambda s: (s.get('pinned', False), session_sort_timestamp(s)),
                reverse=True,
            )
            # Hide empty Untitled sessions from the UI entirely — they are ephemeral
            # scratch pads that only become real once the first message is sent (#1171).
            # No grace window: a 0-message Untitled session is never shown in the list
            # regardless of age. This means page refreshes and accidental New Conversation
            # clicks never leave orphan entries in the sidebar.
            #
            # Exception: sessions with active_stream_id set are actively streaming (#1327).
            # #1184 deferred the first save() until the first message, so during the
            # initial streaming turn the session still looks like Untitled+0-messages.
            # Without this exemption, navigating away during a long first turn causes
            # the session to vanish from the sidebar.
            result = [s for s in result if not (
                s.get('title', 'Untitled') == 'Untitled'
                and s.get('message_count', 0) == 0
                and not s.get('active_stream_id')
                and not s.get('has_pending_user_message')
                and not s.get('worktree_path')
            )]
            result = _finalize_sidebar_rows(
                result,
                prefer_fuller_snapshots_for_sidebar=prefer_fuller_snapshots_for_sidebar,
                hide_from_default_sidebar=hide_from_default_sidebar,
                strip_sidebar_internal_flags=strip_sidebar_internal_flags,
            )
            diag_stage(diag, "all_sessions.lineage_metadata")
            enrich_sidebar_lineage_metadata(result)
            return result
        except Exception:
            logger.debug("Failed to load session index, falling back to full scan")
    # Full scan fallback
    diag_stage(diag, "all_sessions.full_scan")
    out = []
    for p in session_dir.glob('*.json'):
        if p.name.startswith('_'):
            continue
        try:
            s = session_cls.load(p.stem)
            if s:
                out.append(s)
        except Exception:
            logger.debug("Failed to load session from %s", p)
    diag_stage(diag, "all_sessions.full_scan_overlay")
    for s in sessions.values():
        if all(s.session_id != x.session_id for x in out):
            out.append(s)
    diag_stage(diag, "all_sessions.full_scan_sort_filter")
    out.sort(
        key=lambda s: (getattr(s, 'pinned', False), session_sort_timestamp(s)),
        reverse=True,
    )
    # Hide empty Untitled sessions from the UI entirely — kept consistent with the
    # index-path filter above. No grace window: a 0-message Untitled session is
    # never shown regardless of age (#1171).  Same streaming exemption as above (#1327).
    result = [
        s.compact(include_runtime=True, active_stream_ids=current_active_stream_ids)
        for s in out
        if not (
            s.title == 'Untitled'
            and len(s.messages) == 0
            and not s.active_stream_id
            and not s.pending_user_message
            and not getattr(s, 'worktree_path', None)
        )
    ]
    result = _finalize_sidebar_rows(
        result,
        prefer_fuller_snapshots_for_sidebar=prefer_fuller_snapshots_for_sidebar,
        hide_from_default_sidebar=hide_from_default_sidebar,
        strip_sidebar_internal_flags=strip_sidebar_internal_flags,
    )
    diag_stage(diag, "all_sessions.lineage_metadata")
    enrich_sidebar_lineage_metadata(result)
    return result

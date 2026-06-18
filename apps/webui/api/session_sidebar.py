"""Sidebar projection helpers for sessions."""


def hide_from_default_sidebar(session: dict) -> bool:
    """Return True for internal/background sessions hidden from the default list."""
    sid = str(session.get('session_id') or '')
    source = session.get('source_tag') or session.get('source')
    if source == 'cron' or sid.startswith('cron_'):
        return True
    if bool(session.get('pre_compression_snapshot')):
        return not bool(session.get('_show_pre_compression_snapshot'))
    return False


def sidebar_message_count(session: dict) -> int:
    for key in ('message_count', 'actual_message_count'):
        try:
            value = int(session.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0


def sidebar_lineage_root_id(session: dict, sessions_by_id: dict[str, dict]) -> str:
    sid = str(session.get('session_id') or '')
    root = sid
    parent = session.get('parent_session_id')
    seen = {sid}
    while parent and parent not in seen and parent in sessions_by_id:
        root = str(parent)
        seen.add(root)
        parent = sessions_by_id.get(root, {}).get('parent_session_id')
    return root


def has_live_sidebar_state(session: dict) -> bool:
    return bool(
        session.get('active_stream_id')
        or session.get('has_pending_user_message')
        or session.get('pending_user_message')
    )


def prefer_fuller_snapshots_for_sidebar(
    sessions: list[dict],
    *,
    sort_timestamp,
) -> list[dict]:
    """Expose a hidden snapshot when it is the fuller transcript for a lineage."""
    sessions_by_id = {
        str(session.get('session_id')): session
        for session in sessions
        if session.get('session_id')
    }
    groups: dict[str, list[dict]] = {}
    for session in sessions:
        sid = str(session.get('session_id') or '')
        source = session.get('source_tag') or session.get('source')
        if source == 'cron' or sid.startswith('cron_'):
            continue
        root = sidebar_lineage_root_id(session, sessions_by_id)
        groups.setdefault(root, []).append(session)

    snapshot_ids_to_show: set[str] = set()
    continuation_ids_to_hide: set[str] = set()
    for group in groups.values():
        visible = [session for session in group if not session.get('pre_compression_snapshot')]
        snapshots = [session for session in group if session.get('pre_compression_snapshot')]
        if not visible or not snapshots:
            continue
        if any(has_live_sidebar_state(session) for session in visible):
            continue

        best_visible_count = max(sidebar_message_count(session) for session in visible)
        best_snapshot = max(
            snapshots,
            key=lambda session: (sidebar_message_count(session), sort_timestamp(session)),
        )
        if sidebar_message_count(best_snapshot) <= best_visible_count:
            continue

        snapshot_ids_to_show.add(str(best_snapshot.get('session_id')))
        continuation_ids_to_hide.update(
            str(session.get('session_id'))
            for session in visible
            if session.get('session_id')
        )

    if not snapshot_ids_to_show and not continuation_ids_to_hide:
        return sessions

    out = []
    for session in sessions:
        sid = str(session.get('session_id') or '')
        if sid in continuation_ids_to_hide:
            continue
        if sid in snapshot_ids_to_show:
            session = dict(session)
            session['_show_pre_compression_snapshot'] = True
        out.append(session)
    return out


def strip_sidebar_internal_flags(sessions: list[dict]) -> None:
    for session in sessions:
        session.pop('_show_pre_compression_snapshot', None)


def sidebar_title_is_generic_webui(title: str | None) -> bool:
    text = ' '.join(str(title or '').split())
    if text == 'Hermes WebUI':
        return True
    prefix = 'Hermes WebUI #'
    return text.startswith(prefix) and text[len(prefix):].isdigit()


def enrich_sidebar_lineage_metadata(
    sessions: list[dict],
    *,
    state_db_path,
    read_lineage_metadata,
) -> None:
    """Attach state.db compression lineage metadata used by sidebar collapse."""
    try:
        metadata = read_lineage_metadata(
            state_db_path,
            {str(s.get('session_id')) for s in sessions if s.get('session_id')},
        )
    except Exception:
        return
    for session in sessions:
        sid = session.get('session_id')
        if sid in metadata:
            entry = dict(metadata[sid])
            state_db_title = entry.pop('_state_db_title', None)
            session.update(entry)
            title = session.get('title')
            if (
                state_db_title
                and state_db_title != title
                and sidebar_title_is_generic_webui(title)
            ):
                session['_state_db_title'] = state_db_title
                session['display_title'] = state_db_title

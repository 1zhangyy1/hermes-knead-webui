"""Session registry helpers for loading and creating sessions."""


def get_session(
    sid,
    *,
    metadata_only: bool = False,
    sessions,
    sessions_lock,
    sessions_max: int,
    session_cls,
    get_cached_session,
    cache_session,
    evict_cached_session_if_same,
    repair_stale_pending,
    active_stream_ids,
):
    """Load a session through the in-memory cache and optional repair path."""
    cached = get_cached_session(sessions, sessions_lock, sid)
    if cached is not None:
        return cached
    if metadata_only:
        session = session_cls.load_metadata_only(sid)
        if session:
            return session
    else:
        session = session_cls.load(sid)
    if session:
        cache_session(sessions, sessions_lock, sid, session, sessions_max)
        if not metadata_only:
            try:
                repaired = repair_stale_pending(session)
                if not repaired and (
                    len(session.messages) == 0
                    and session.pending_user_message
                    and session.active_stream_id
                    and session.active_stream_id not in active_stream_ids()
                ):
                    # If repair skipped because the per-session lock was held,
                    # evict so a later cache miss can retry after the holder exits.
                    evict_cached_session_if_same(sessions, sessions_lock, sid, session)
            except Exception:
                pass  # repair is best-effort
        return session
    raise KeyError(sid)


def new_session(
    *,
    workspace=None,
    model=None,
    profile=None,
    model_provider=None,
    project_id=None,
    worktree_info=None,
    session_cls,
    sessions,
    sessions_lock,
    sessions_max: int,
    cache_session,
    get_active_profile_name,
    get_effective_default_model,
    get_last_workspace,
):
    """Create a new in-memory session, saving immediately only for worktrees."""
    if profile is None:
        try:
            profile = get_active_profile_name()
        except ImportError:
            profile = None
    effective_model = model or get_effective_default_model()
    wt = worktree_info if isinstance(worktree_info, dict) else None
    workspace_path = (wt.get('path') if wt and wt.get('path') else workspace) if wt else workspace
    session = session_cls(
        workspace=workspace_path or get_last_workspace(),
        model=effective_model,
        model_provider=model_provider,
        profile=profile,
        project_id=project_id,
        worktree_path=wt.get('path') if wt else None,
        worktree_branch=wt.get('branch') if wt else None,
        worktree_repo_root=wt.get('repo_root') if wt else None,
        worktree_created_at=wt.get('created_at') if wt else None,
    )
    cache_session(sessions, sessions_lock, session.session_id, session, sessions_max)
    if wt:
        session.save()
    return session

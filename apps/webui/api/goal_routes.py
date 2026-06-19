"""Goal command route helper."""

from __future__ import annotations


def handle_goal_command(
    handler,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    profiles_match_fn,
    streams,
    streams_lock,
    clear_stale_stream_state_fn,
    resolve_trusted_workspace_fn,
    resolve_session_model_state_fn,
    start_chat_stream_fn,
) -> bool:
    try:
        require_fn(body, "session_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    try:
        session = get_session_fn(body["session_id"])
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)

    requested_profile = str(body.get("profile") or "").strip()
    if requested_profile:
        try:
            from api.profiles import _PROFILE_ID_RE

            if requested_profile != "default" and not _PROFILE_ID_RE.fullmatch(requested_profile):
                return bad_response_fn(handler, "invalid profile", 400)
        except ImportError:
            requested_profile = ""
    if requested_profile and not profiles_match_fn(getattr(session, "profile", None), requested_profile):
        has_persisted_turns = bool(
            getattr(session, "messages", None)
            or getattr(session, "context_messages", None)
            or getattr(session, "pending_user_message", None)
        )
        if not has_persisted_turns:
            session.profile = requested_profile

    current_stream_id = getattr(session, "active_stream_id", None)
    stream_running = False
    if current_stream_id:
        with streams_lock:
            stream_running = current_stream_id in streams
        if not stream_running:
            clear_stale_stream_state_fn(session)

    try:
        from api.profiles import get_hermes_home_for_profile

        profile_home = get_hermes_home_for_profile(getattr(session, "profile", None))
    except Exception:
        profile_home = None

    from api.goals import goal_command_payload, goal_state_snapshot, restore_goal_state

    goal_args = str(body.get("args", "") or body.get("text", "") or "")
    goal_action = goal_args.strip().lower()
    will_kickoff = bool(
        goal_args.strip()
        and goal_action not in ("status", "pause", "resume", "clear", "stop", "done")
        and not stream_running
    )
    workspace = model = model_provider = normalized_model = None
    previous_goal_state = None
    if will_kickoff:
        try:
            workspace = str(resolve_trusted_workspace_fn(body.get("workspace") or session.workspace))
        except ValueError as exc:
            return bad_response_fn(handler, str(exc))
        requested_model = body.get("model") or session.model
        requested_provider = (
            body.get("model_provider")
            if "model_provider" in body
            else getattr(session, "model_provider", None)
        )
        model, model_provider, normalized_model = resolve_session_model_state_fn(
            requested_model,
            requested_provider,
        )
        previous_goal_state = goal_state_snapshot(session.session_id, profile_home=profile_home)

    payload = goal_command_payload(
        session.session_id,
        goal_args,
        stream_running=stream_running,
        profile_home=profile_home,
    )
    if not payload.get("ok", True):
        status = 409 if payload.get("error") == "agent_running" else 400
        return json_response_fn(handler, payload, status=status)

    kickoff_prompt = str(payload.get("kickoff_prompt") or "").strip()
    if kickoff_prompt:
        if workspace is None:
            try:
                workspace = str(resolve_trusted_workspace_fn(body.get("workspace") or session.workspace))
            except ValueError as exc:
                return bad_response_fn(handler, str(exc))
        if model is None:
            requested_model = body.get("model") or session.model
            requested_provider = (
                body.get("model_provider")
                if "model_provider" in body
                else getattr(session, "model_provider", None)
            )
            model, model_provider, normalized_model = resolve_session_model_state_fn(
                requested_model,
                requested_provider,
            )
        stream_response = start_chat_stream_fn(
            session,
            msg=kickoff_prompt,
            attachments=[],
            workspace=workspace,
            model=model,
            model_provider=model_provider,
            normalized_model=normalized_model,
            goal_related=True,
        )
        status = int(stream_response.pop("_status", 200) or 200)
        payload.update(stream_response)
        if status >= 400:
            restore_goal_state(session.session_id, previous_goal_state, profile_home=profile_home)
            payload["ok"] = False
            return json_response_fn(handler, payload, status=status)

    return json_response_fn(handler, payload)

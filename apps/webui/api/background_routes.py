"""Route helpers for /api/btw and /api/background."""

from __future__ import annotations

import threading
import uuid
from urllib.parse import parse_qs


def handle_background_status(handler, parsed, *, bad_response_fn, json_response_fn):
    sid = parse_qs(parsed.query).get("session_id", [""])[0]
    if not sid:
        return bad_response_fn(handler, "Missing session_id")
    from api.background import get_results

    return json_response_fn(handler, {"results": get_results(sid)})


def handle_btw(
    handler,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    new_session_fn,
    create_stream_channel_fn,
    streams: dict,
    streams_lock,
    run_agent_streaming_fn,
):
    try:
        require_fn(body, "session_id")
        require_fn(body, "question")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    try:
        session = get_session_fn(body["session_id"])
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)

    question = str(body["question"]).strip()
    if not question:
        return bad_response_fn(handler, "question is required")

    current_stream_id = getattr(session, "active_stream_id", None)
    if current_stream_id:
        with streams_lock:
            if current_stream_id in streams:
                return json_response_fn(
                    handler,
                    {"error": "session already has an active stream"},
                    status=409,
                )
        session.active_stream_id = None

    model_provider = getattr(session, "model_provider", None)
    ephemeral = new_session_fn(
        workspace=session.workspace,
        model=session.model,
        model_provider=model_provider,
        profile=getattr(session, "profile", None),
    )
    ephemeral.messages = list(session.messages or [])
    ephemeral.title = f"btw: {question[:60]}"
    ephemeral.save()

    stream_id = uuid.uuid4().hex
    ephemeral.active_stream_id = stream_id
    ephemeral.save()

    stream = create_stream_channel_fn()
    with streams_lock:
        streams[stream_id] = stream

    from api.background import track_btw

    track_btw(body["session_id"], ephemeral.session_id, stream_id, question)
    thread = threading.Thread(
        target=run_agent_streaming_fn,
        args=(ephemeral.session_id, question, session.model, session.workspace, stream_id, None),
        kwargs={"ephemeral": True, "model_provider": model_provider},
        daemon=True,
    )
    thread.start()
    return json_response_fn(
        handler,
        {
            "stream_id": stream_id,
            "session_id": ephemeral.session_id,
            "parent_session_id": body["session_id"],
        },
    )


def handle_background(
    handler,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    new_session_fn,
    session_cls,
    session_dir,
    create_stream_channel_fn,
    streams: dict,
    streams_lock,
    run_agent_streaming_fn,
):
    try:
        require_fn(body, "session_id")
        require_fn(body, "prompt")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    try:
        session = get_session_fn(body["session_id"])
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)

    prompt = str(body["prompt"]).strip()
    if not prompt:
        return bad_response_fn(handler, "prompt is required")

    model_provider = getattr(session, "model_provider", None)
    bg = new_session_fn(
        workspace=session.workspace,
        model=session.model,
        model_provider=model_provider,
        profile=getattr(session, "profile", None),
    )
    bg.title = f"bg: {prompt[:60]}"
    bg.save()

    stream_id = uuid.uuid4().hex
    bg.active_stream_id = stream_id
    bg.save()

    stream = create_stream_channel_fn()
    with streams_lock:
        streams[stream_id] = stream

    task_id = uuid.uuid4().hex[:8]
    from api.background import complete_background, track_background

    parent_sid = body["session_id"]
    bg_sid = bg.session_id
    track_background(parent_sid, bg_sid, stream_id, task_id, prompt)

    def _run_bg_and_notify():
        try:
            run_agent_streaming_fn(
                bg_sid,
                prompt,
                session.model,
                session.workspace,
                stream_id,
                None,
                model_provider=model_provider,
            )
            try:
                reloaded = session_cls.load(bg_sid)
                answer = ""
                for message in reversed((reloaded.messages if reloaded else None) or []):
                    if not isinstance(message, dict) or message.get("role") != "assistant":
                        continue
                    if message.get("_error"):
                        continue
                    content = str(message.get("content") or "").strip()
                    if content:
                        answer = content
                        break
                complete_background(parent_sid, task_id, answer or "(no answer produced)")
            except Exception:
                complete_background(parent_sid, task_id, "(background task failed)")
            try:
                (session_dir / f"{bg_sid}.json").unlink(missing_ok=True)
            except Exception:
                pass
        except Exception:
            try:
                complete_background(parent_sid, task_id, "(background task failed)")
            except Exception:
                pass

    thread = threading.Thread(target=_run_bg_and_notify, daemon=True)
    thread.start()
    return json_response_fn(
        handler,
        {"task_id": task_id, "stream_id": stream_id, "session_id": bg.session_id},
    )

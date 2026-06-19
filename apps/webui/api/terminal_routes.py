"""Terminal endpoint handlers for WebUI routes."""

from __future__ import annotations

from urllib.parse import parse_qs


def terminal_session_and_workspace(
    body_or_query,
    *,
    get_session_fn,
    resolve_trusted_workspace_fn,
) -> tuple[str, str]:
    sid = str(body_or_query.get("session_id", "")).strip()
    if not sid:
        raise ValueError("session_id required")
    try:
        session = get_session_fn(sid)
    except KeyError:
        raise KeyError("Session not found")
    workspace = resolve_trusted_workspace_fn(getattr(session, "workspace", "") or "")
    return sid, workspace


def handle_terminal_start(
    handler,
    body,
    *,
    terminal_session_and_workspace_fn,
    json_response_fn,
    bad_response_fn,
    sanitize_error_fn,
):
    try:
        sid, workspace = terminal_session_and_workspace_fn(body)
        from api.terminal import start_terminal

        term = start_terminal(
            sid,
            workspace,
            rows=int(body.get("rows") or 24),
            cols=int(body.get("cols") or 80),
            restart=bool(body.get("restart")),
        )
        return json_response_fn(
            handler,
            {
                "ok": True,
                "session_id": sid,
                "workspace": term.workspace,
                "running": term.is_alive(),
            },
        )
    except KeyError as exc:
        return bad_response_fn(handler, str(exc), 404)
    except ValueError as exc:
        return bad_response_fn(handler, str(exc), 400)
    except Exception as exc:
        return bad_response_fn(handler, sanitize_error_fn(exc), 500)


def handle_terminal_input(
    handler,
    body,
    *,
    require_fn,
    json_response_fn,
    bad_response_fn,
    sanitize_error_fn,
):
    try:
        require_fn(body, "session_id")
        data = str(body.get("data", ""))
        if len(data) > 8192:
            return bad_response_fn(handler, "input too large", 413)
        from api.terminal import write_terminal

        write_terminal(body["session_id"], data)
        return json_response_fn(handler, {"ok": True})
    except KeyError as exc:
        return bad_response_fn(handler, str(exc), 404)
    except ValueError as exc:
        return bad_response_fn(handler, str(exc), 400)
    except Exception as exc:
        return bad_response_fn(handler, sanitize_error_fn(exc), 500)


def handle_terminal_resize(
    handler,
    body,
    *,
    require_fn,
    json_response_fn,
    bad_response_fn,
    sanitize_error_fn,
):
    try:
        require_fn(body, "session_id")
        from api.terminal import resize_terminal

        resize_terminal(
            body["session_id"],
            rows=int(body.get("rows") or 24),
            cols=int(body.get("cols") or 80),
        )
        return json_response_fn(handler, {"ok": True})
    except KeyError as exc:
        return bad_response_fn(handler, str(exc), 404)
    except ValueError as exc:
        return bad_response_fn(handler, str(exc), 400)
    except Exception as exc:
        return bad_response_fn(handler, sanitize_error_fn(exc), 500)


def handle_terminal_close(
    handler,
    body,
    *,
    require_fn,
    json_response_fn,
    bad_response_fn,
):
    try:
        require_fn(body, "session_id")
        from api.terminal import close_terminal

        closed = close_terminal(body["session_id"])
        return json_response_fn(handler, {"ok": True, "closed": closed})
    except ValueError as exc:
        return bad_response_fn(handler, str(exc), 400)


def handle_terminal_output(
    handler,
    parsed,
    *,
    json_response_fn,
    bad_response_fn,
    sse_fn,
    heartbeat_interval_seconds: int,
    queue_empty_error,
    client_disconnect_errors: tuple[type[BaseException], ...],
):
    sid = parse_qs(parsed.query).get("session_id", [""])[0]
    if not sid:
        return bad_response_fn(handler, "session_id required")
    from api.terminal import get_terminal

    term = get_terminal(sid)
    if term is None:
        return json_response_fn(handler, {"error": "terminal not running"}, status=404)

    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("X-Accel-Buffering", "no")
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()
    try:
        while True:
            try:
                event, data = term.output.get(timeout=heartbeat_interval_seconds)
            except queue_empty_error:
                handler.wfile.write(b": terminal heartbeat\n\n")
                handler.wfile.flush()
                if term.closed.is_set() and term.output.empty():
                    sse_fn(handler, "terminal_closed", {"exit_code": term.proc.poll()})
                    break
                continue
            sse_fn(handler, event, data)
            if event in ("terminal_closed", "terminal_error"):
                break
    except client_disconnect_errors:
        pass
    return True

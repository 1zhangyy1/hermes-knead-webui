"""Gateway session SSE route helpers."""

from __future__ import annotations

from urllib.parse import parse_qs


def gateway_sse_probe_payload(settings, watcher):
    enabled = bool(settings.get("show_cli_sessions"))
    # Prefer the public accessor on current GatewayWatcher, but keep the
    # private-thread fallback for older in-memory instances during upgrades.
    if watcher is None:
        watcher_alive = False
    elif hasattr(watcher, "is_alive") and callable(getattr(watcher, "is_alive")):
        watcher_alive = bool(watcher.is_alive())
    else:
        thread = getattr(watcher, "_thread", None)
        watcher_alive = thread is not None and thread.is_alive()

    payload = {
        "enabled": enabled,
        "fallback_poll_ms": 30000,
        "ok": enabled and watcher_alive,
        "watcher_running": watcher_alive,
    }
    if not enabled:
        payload["error"] = "agent sessions not enabled"
        return payload, 404
    if not watcher_alive:
        payload["error"] = "watcher not started"
        return payload, 503
    return payload, 200


def handle_gateway_sse_stream(
    handler,
    parsed,
    *,
    load_settings_fn,
    get_watcher_fn,
    json_response_fn,
    sse_fn,
    get_cli_sessions_fn,
    heartbeat_interval_seconds: int,
    queue_empty_error,
    client_disconnect_errors: tuple[type[BaseException], ...],
    probe_payload_fn=gateway_sse_probe_payload,
):
    """SSE endpoint for real-time gateway session updates."""
    settings = load_settings_fn()
    watcher = get_watcher_fn()

    probe = parse_qs(parsed.query).get("probe", [""])[0].lower() in {"1", "true", "yes"}
    if probe:
        payload, status = probe_payload_fn(settings, watcher)
        return json_response_fn(handler, payload, status=status)

    if not settings.get("show_cli_sessions"):
        return json_response_fn(handler, {"error": "agent sessions not enabled"}, status=404)

    probe_body, _probe_status = probe_payload_fn(settings, watcher)
    if not probe_body["watcher_running"]:
        return json_response_fn(handler, {"error": "watcher not started"}, status=503)

    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("X-Accel-Buffering", "no")
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()

    q = watcher.subscribe()
    try:
        sse_fn(handler, "sessions_changed", {"sessions": get_cli_sessions_fn()})

        while True:
            try:
                event_data = q.get(timeout=heartbeat_interval_seconds)
            except queue_empty_error:
                handler.wfile.write(b": keepalive\n\n")
                handler.wfile.flush()
                continue
            if event_data is None:
                break
            sse_fn(handler, event_data.get("type", "sessions_changed"), event_data)
    except client_disconnect_errors:
        pass
    finally:
        watcher.unsubscribe(q)
    return True

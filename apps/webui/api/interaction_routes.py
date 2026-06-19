"""Approval and clarify polling/test-injection route helpers."""

from __future__ import annotations

from urllib.parse import parse_qs


def handle_approval_pending(
    handler,
    parsed,
    *,
    pending,
    lock,
    json_response_fn,
):
    sid = parse_qs(parsed.query).get("session_id", [""])[0]
    with lock:
        queue = pending.get(sid)
        if isinstance(queue, list):
            item = queue[0] if queue else None
            total = len(queue)
        elif queue:
            item = queue
            total = 1
        else:
            item = None
            total = 0
    if item:
        return json_response_fn(handler, {"pending": dict(item), "pending_count": total})
    return json_response_fn(handler, {"pending": None, "pending_count": 0})


def handle_approval_inject(
    handler,
    parsed,
    *,
    submit_pending_fn,
    json_response_fn,
):
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    key = qs.get("pattern_key", ["test_pattern"])[0]
    cmd = qs.get("command", ["rm -rf /tmp/test"])[0]
    if sid:
        submit_pending_fn(
            sid,
            {
                "command": cmd,
                "pattern_key": key,
                "pattern_keys": [key],
                "description": "test pattern",
            },
        )
        return json_response_fn(handler, {"ok": True, "session_id": sid})
    return json_response_fn(handler, {"error": "session_id required"}, status=400)


def handle_clarify_pending(
    handler,
    parsed,
    *,
    get_pending_fn,
    json_response_fn,
):
    sid = parse_qs(parsed.query).get("session_id", [""])[0]
    pending = get_pending_fn(sid)
    if pending:
        return json_response_fn(handler, {"pending": pending})
    return json_response_fn(handler, {"pending": None})


def handle_clarify_inject(
    handler,
    parsed,
    *,
    submit_pending_fn,
    json_response_fn,
):
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    question = qs.get("question", ["Which option?"])[0]
    choices = qs.get("choices", [])
    if sid:
        submit_pending_fn(
            sid,
            {
                "question": question,
                "choices_offered": choices,
                "session_id": sid,
                "kind": "clarify",
            },
        )
        return json_response_fn(handler, {"ok": True, "session_id": sid})
    return json_response_fn(handler, {"error": "session_id required"}, status=400)

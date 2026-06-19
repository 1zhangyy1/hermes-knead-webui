"""Manual session compression route helpers."""

from __future__ import annotations

import io
import json
import threading
import time
from typing import Callable


class ManualCompressionMemoryHandler:
    def __init__(self):
        self.wfile = io.BytesIO()
        self.status = None
        self.sent_headers = {}

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.sent_headers[key] = value

    def end_headers(self):
        pass

    def payload(self):
        raw = self.wfile.getvalue().decode("utf-8")
        return json.loads(raw) if raw else {}


def manual_compression_cleanup_locked(jobs: dict, ttl_seconds: int, now=None):
    now = time.time() if now is None else now
    for sid, job in list(jobs.items()):
        if job.get("status") == "running":
            continue
        updated_at = float(job.get("updated_at") or job.get("started_at") or now)
        if now - updated_at > ttl_seconds:
            jobs.pop(sid, None)


def manual_compression_status_payload(job):
    status = job.get("status") or "running"
    payload = {
        "ok": status not in {"error", "cancelled"},
        "status": status,
        "session_id": job.get("session_id"),
        "focus_topic": job.get("focus_topic"),
        "started_at": job.get("started_at"),
        "updated_at": job.get("updated_at"),
    }
    if status == "done":
        result = job.get("result")
        if isinstance(result, dict):
            payload.update(result)
        payload["status"] = "done"
        payload["ok"] = True
    elif status == "error":
        payload["ok"] = False
        payload["error"] = job.get("error") or "Compression failed"
        payload["error_status"] = int(job.get("error_status") or 400)
    elif status == "cancelled":
        payload["ok"] = False
        payload["error"] = job.get("error") or "Compression cancelled"
        payload["error_status"] = int(job.get("error_status") or 409)
    return payload


def run_manual_compression_job(
    sid,
    body,
    *,
    get_session_fn: Callable,
    handle_session_compress_fn: Callable,
    jobs: dict,
    jobs_lock,
    sanitize_error_fn: Callable,
    logger,
):
    memory_handler = ManualCompressionMemoryHandler()
    try:
        try:
            session = get_session_fn(sid)
        except KeyError:
            session = None
        if session is not None:
            from api import profiles as profiles_api

            with profiles_api.profile_env_for_background_worker(session, "manual compression", logger_override=logger):
                handle_session_compress_fn(memory_handler, body)
        else:
            handle_session_compress_fn(memory_handler, body)
        status = int(memory_handler.status or 500)
        payload = memory_handler.payload()
        with jobs_lock:
            job = jobs.get(sid)
            if not job:
                return
            now = time.time()
            if status >= 400 or not isinstance(payload, dict) or payload.get("error"):
                job.update(
                    {
                        "status": "error",
                        "error": str((payload or {}).get("error") or "Compression failed"),
                        "error_status": status,
                        "updated_at": now,
                    }
                )
            else:
                job.update(
                    {
                        "status": "done",
                        "result": payload,
                        "updated_at": now,
                    }
                )
    except Exception as exc:
        logger.warning("Manual compression worker failed for session %s: %s", sid, exc)
        with jobs_lock:
            job = jobs.get(sid)
            if job:
                job.update(
                    {
                        "status": "error",
                        "error": f"Compression failed: {sanitize_error_fn(exc)}",
                        "error_status": 500,
                        "updated_at": time.time(),
                    }
                )


def handle_session_compress_start(
    handler,
    body,
    *,
    require_fn: Callable,
    bad_fn: Callable,
    json_response_fn: Callable,
    get_session_fn: Callable,
    jobs: dict,
    jobs_lock,
    cleanup_locked_fn: Callable,
    status_payload_fn: Callable,
    run_job_fn: Callable,
):
    try:
        require_fn(body, "session_id")
    except ValueError as e:
        return bad_fn(handler, str(e))

    sid = str(body.get("session_id") or "").strip()
    if not sid:
        return bad_fn(handler, "session_id is required")
    try:
        s = get_session_fn(sid)
    except KeyError:
        return bad_fn(handler, "Session not found", 404)
    if getattr(s, "active_stream_id", None):
        return bad_fn(handler, "Session is still streaming; wait for the current turn to finish.", 409)

    focus_topic = str(body.get("focus_topic") or body.get("topic") or "").strip()[:500] or None
    job_body = {"session_id": sid}
    if focus_topic:
        job_body["focus_topic"] = focus_topic

    now = time.time()
    with jobs_lock:
        cleanup_locked_fn(now)
        existing = jobs.get(sid)
        if existing:
            existing_payload = status_payload_fn(existing)
            if existing_payload.get("status") == "running":
                return json_response_fn(handler, existing_payload)
            jobs.pop(sid, None)
        job = {
            "session_id": sid,
            "focus_topic": focus_topic,
            "status": "running",
            "started_at": now,
            "updated_at": now,
        }
        jobs[sid] = job

    worker = threading.Thread(
        target=run_job_fn,
        args=(sid, job_body),
        name=f"manual-compress-{sid[:8]}",
        daemon=True,
    )
    worker.start()

    with jobs_lock:
        return json_response_fn(handler, status_payload_fn(jobs.get(sid, job)))


def handle_session_compress_status(
    handler,
    sid,
    *,
    bad_fn: Callable,
    json_response_fn: Callable,
    jobs: dict,
    jobs_lock,
    cleanup_locked_fn: Callable,
    status_payload_fn: Callable,
):
    sid = str(sid or "").strip()
    if not sid:
        return bad_fn(handler, "session_id is required")
    with jobs_lock:
        cleanup_locked_fn()
        job = jobs.get(sid)
        if not job:
            return json_response_fn(handler, {"ok": True, "status": "idle", "session_id": sid})
        payload = status_payload_fn(job)
        return json_response_fn(handler, payload)


def handle_conversation_rounds(handler, body, *, require_fn: Callable, bad_fn: Callable, json_response_fn: Callable):
    try:
        require_fn(body, "session_id")
    except ValueError as e:
        return bad_fn(handler, str(e))

    sid = str(body.get("session_id") or "").strip()
    if not sid:
        return bad_fn(handler, "session_id is required")

    since = body.get("since")
    if since is not None:
        try:
            since = float(since)
        except (TypeError, ValueError):
            return bad_fn(handler, "since must be a unix timestamp (number)")

    from api.models import CONVERSATION_ROUND_THRESHOLD, count_conversation_rounds

    rounds = count_conversation_rounds(sid, since=since)
    return json_response_fn(handler, {
        "ok": True,
        "rounds": rounds,
        "threshold": CONVERSATION_ROUND_THRESHOLD,
        "should_show": rounds >= CONVERSATION_ROUND_THRESHOLD,
    })

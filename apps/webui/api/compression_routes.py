"""Manual session compression route helpers."""

from __future__ import annotations

import copy
import io
import json
import re
import threading
import time
from typing import Callable

from api.compression_anchor import visible_messages_for_anchor


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


def handle_session_compress(
    handler,
    body,
    *,
    require_fn: Callable,
    bad_fn: Callable,
    json_response_fn: Callable,
    get_session_fn: Callable,
    resolve_cli_toolsets_fn: Callable[[], list[str]],
    sanitize_error_fn: Callable,
    redact_session_data_fn: Callable,
    logger,
):
    def _anchor_message_key(m):
        if not isinstance(m, dict):
            return None
        role = str(m.get("role") or "")
        if not role or role == "tool":
            return None
        content = m.get("content", "")
        if isinstance(content, list):
            text = "\n".join(
                str(p.get("text") or p.get("content") or "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        else:
            text = str(content or "")
        norm = " ".join(text.split()).strip()[:160]
        ts = m.get("_ts") or m.get("timestamp")
        attachments = m.get("attachments")
        attach_count = len(attachments) if isinstance(attachments, list) else 0
        if not norm and not attach_count and not ts:
            return None
        return {"role": role, "ts": ts, "text": norm, "attachments": attach_count}

    def _compression_summary_from_messages(messages):
        text = None
        for m in reversed(messages or []):
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or "").lower()
            if role != "assistant":
                continue
            if not isinstance(m.get("content"), str):
                continue
            content = str(m.get("content") or "").strip()
            if not content:
                continue
            norm = re.sub(r"\s+", " ", content).strip()
            if (
                "context compaction" in norm.lower()
                or "context compression" in norm.lower()
            ):
                return norm
        return None

    def _compact_summary_text(raw_text):
        if not isinstance(raw_text, str):
            return None
        txt = raw_text.strip()
        if not txt:
            return None
        txt = re.sub(r"\s+", " ", txt)
        if len(txt) > 320:
            txt = f"{txt[:314]}…"
        return txt

    try:
        require_fn(body, "session_id")
    except ValueError as e:
        return bad_fn(handler, str(e))

    sid = str(body.get("session_id") or "").strip()
    if not sid:
        return bad_fn(handler, "session_id is required")

    focus_topic = str(body.get("focus_topic") or body.get("topic") or "").strip()[:500] or None

    try:
        s = get_session_fn(sid)
    except KeyError:
        return bad_fn(handler, "Session not found", 404)

    if getattr(s, "active_stream_id", None):
        return bad_fn(handler, "Session is still streaming; wait for the current turn to finish.", 409)

    try:
        from api.streaming import _sanitize_messages_for_api

        messages = _sanitize_messages_for_api(s.messages)
        if len(messages) < 4:
            return bad_fn(handler, "Not enough conversation to compress (need at least 4 messages).")

        def _fallback_estimate_messages_tokens_rough(msgs):
            """Fallback heuristic token estimate when runtime metadata helpers are absent."""
            total = 0
            for m in msgs or []:
                if not isinstance(m, dict):
                    continue
                content = m.get("content", "")
                if isinstance(content, list):
                    content_text = "\n".join(
                        str(p.get("text") or p.get("content") or "")
                        for p in content
                        if isinstance(p, dict)
                    )
                else:
                    content_text = str(content or "")
                total += len(content_text.split())
            return max(1, total)

        def _fallback_summarize_manual_compression(original_messages, compressed_messages, before_tokens, after_tokens, focus_topic=None):
            """Lightweight fallback summary to keep /session/compress usable in tests/runtime."""
            after_tokens = after_tokens if after_tokens is not None else _fallback_estimate_messages_tokens_rough(compressed_messages)
            headline = f"Compressed: {len(original_messages)} \u2192 {len(compressed_messages)} messages"
            summary = {
                "headline": headline,
                "token_line": f"Rough transcript estimate: ~{before_tokens} \u2192 ~{after_tokens} tokens",
                "note": f"Focus: {focus_topic}" if focus_topic else None,
            }
            summary["reference_message"] = (
                f"[CONTEXT COMPACTION \u2014 REFERENCE ONLY] {headline}\n"
                f"{summary['token_line']}\n"
                + (summary["note"] + "\n" if summary.get("note") else "")
                + "Compression completed."
            )
            return summary

        def _estimate_messages_tokens_rough(msgs):
            try:
                from agent.model_metadata import estimate_messages_tokens_rough

                return estimate_messages_tokens_rough(msgs)
            except Exception:
                return _fallback_estimate_messages_tokens_rough(msgs)

        def _summarize_manual_compression(
            original_messages,
            compressed_messages,
            before_tokens,
            after_tokens,
            focus_topic=None,
        ):
            try:
                from agent.manual_compression_feedback import summarize_manual_compression

                return summarize_manual_compression(
                    original_messages,
                    compressed_messages,
                    before_tokens,
                    after_tokens,
                )
            except Exception:
                return _fallback_summarize_manual_compression(
                    original_messages,
                    compressed_messages,
                    before_tokens,
                    after_tokens,
                    focus_topic,
                )

        import api.config as _cfg
        from api.oauth import resolve_runtime_provider_with_anthropic_env_lock
        import hermes_cli.runtime_provider as _runtime_provider
        import run_agent as _run_agent

        resolved_model, resolved_provider, resolved_base_url = _cfg.resolve_model_provider(
            _cfg.model_with_provider_context(s.model, getattr(s, "model_provider", None))
        )

        resolved_api_key = None
        try:
            _rt = resolve_runtime_provider_with_anthropic_env_lock(
                _runtime_provider.resolve_runtime_provider,
                requested=resolved_provider,
            )
            resolved_api_key = _rt.get("api_key")
            if not resolved_provider:
                resolved_provider = _rt.get("provider")
            if not resolved_base_url:
                resolved_base_url = _rt.get("base_url")
        except Exception as _e:
            logger.warning("resolve_runtime_provider failed for compression: %s", _e)

        if isinstance(resolved_provider, str) and resolved_provider.startswith("custom:"):
            _cp_key, _cp_base = _cfg.resolve_custom_provider_connection(resolved_provider)
            if not resolved_api_key and _cp_key:
                resolved_api_key = _cp_key
            if not resolved_base_url and _cp_base:
                resolved_base_url = _cp_base

        if not resolved_api_key:
            return bad_fn(handler, "No provider configured -- cannot compress.")

        original_messages = list(messages)
        original_stream_state = (
            getattr(s, "active_stream_id", None),
            getattr(s, "pending_user_message", None),
            copy.deepcopy(getattr(s, "pending_attachments", None)),
            getattr(s, "pending_started_at", None),
        )
        approx_tokens = _estimate_messages_tokens_rough(original_messages)

        agent = _run_agent.AIAgent(
            model=resolved_model,
            provider=resolved_provider,
            base_url=resolved_base_url,
            api_key=resolved_api_key,
            platform="webui",
            quiet_mode=True,
            enabled_toolsets=resolve_cli_toolsets_fn(),
            session_id=sid,
        )
        compressed = agent.context_compressor.compress(
            original_messages,
            current_tokens=approx_tokens,
            focus_topic=focus_topic,
        )
        new_tokens = _estimate_messages_tokens_rough(compressed)
        summary = _summarize_manual_compression(
            original_messages,
            compressed,
            approx_tokens,
            new_tokens,
            focus_topic=focus_topic,
        )

        with _cfg._get_session_agent_lock(sid):
            current_stream_state = (
                getattr(s, "active_stream_id", None),
                getattr(s, "pending_user_message", None),
                copy.deepcopy(getattr(s, "pending_attachments", None)),
                getattr(s, "pending_started_at", None),
            )
            if current_stream_state != original_stream_state:
                return bad_fn(handler, "Session stream state changed during compression; please retry.", 409)
            if _sanitize_messages_for_api(s.messages) != original_messages:
                return bad_fn(handler, "Session was modified during compression; please retry.", 409)

            s.messages = compressed
            s.context_messages = compressed
            s.tool_calls = []
            s.active_stream_id = None
            s.pending_user_message = None
            s.pending_attachments = []
            s.pending_started_at = None
            visible_after = visible_messages_for_anchor(compressed, auto_compression=False)
            s.compression_anchor_visible_idx = max(0, len(visible_after) - 1) if visible_after else None
            s.compression_anchor_message_key = _anchor_message_key(visible_after[-1]) if visible_after else None
            summary_text = None
            if isinstance(summary, dict):
                summary_text = summary.get("reference_message") or summary.get("token_line") or summary.get("headline")
            s.compression_anchor_summary = _compact_summary_text(
                summary_text or _compression_summary_from_messages(compressed) or ""
            )
            s.save()

        session_payload = redact_session_data_fn(
            s.compact() | {
                "messages": s.messages,
                "tool_calls": s.tool_calls,
                "active_stream_id": s.active_stream_id,
                "pending_user_message": s.pending_user_message,
                "pending_attachments": s.pending_attachments,
                "pending_started_at": s.pending_started_at,
                "compression_anchor_visible_idx": getattr(s, "compression_anchor_visible_idx", None),
                "compression_anchor_message_key": getattr(s, "compression_anchor_message_key", None),
            }
        )
        return json_response_fn(
            handler,
            {
                "ok": True,
                "session": session_payload,
                "summary": summary,
                "focus_topic": focus_topic,
            },
        )
    except Exception as e:
        logger.warning("Manual session compression failed: %s", e)
        return bad_fn(handler, f"Compression failed: {sanitize_error_fn(e)}")


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

"""Health endpoint helpers for the WebUI route layer."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from urllib.parse import parse_qs

from api.helpers import j


def accept_loop_health(handler) -> dict:
    server = getattr(handler, "server", None)
    return {
        "requests_total": int(getattr(server, "accept_loop_requests_total", 0) or 0),
        "last_request_at": round(float(getattr(server, "accept_loop_last_request_at", 0.0) or 0.0), 3),
    }


def streams_lock_health(streams_lock, streams, timeout_seconds: float = 0.5) -> dict:
    t0 = time.time()
    acquired = streams_lock.acquire(timeout=timeout_seconds)
    elapsed_ms = round((time.time() - t0) * 1000, 1)
    if not acquired:
        return {
            "status": "blocked",
            "timeout_seconds": timeout_seconds,
            "ms": elapsed_ms,
        }
    try:
        return {
            "status": "ok",
            "active_streams": len(streams),
            "ms": elapsed_ms,
        }
    finally:
        streams_lock.release()


def run_lifecycle_health() -> dict:
    """Return active worker-run state independent of SSE stream presence."""
    from api import config as live_config

    now = time.time()
    with live_config.ACTIVE_RUNS_LOCK:
        runs = []
        for stream_id, raw in (live_config.ACTIVE_RUNS or {}).items():
            item = dict(raw or {})
            started_at = item.get("started_at")
            try:
                age = max(0.0, now - float(started_at))
            except Exception:
                age = 0.0
            item.setdefault("stream_id", stream_id)
            item["age_seconds"] = round(age, 1)
            runs.append(item)
        last_finished = live_config.LAST_RUN_FINISHED_AT
    runs.sort(key=lambda item: float(item.get("started_at") or 0.0))
    payload = {
        "active_runs": len(runs),
        "runs": runs,
        "last_run_finished_at": last_finished,
    }
    if runs:
        payload["oldest_run_age_seconds"] = runs[0].get("age_seconds", 0.0)
    elif last_finished:
        payload["idle_seconds_since_last_run"] = round(max(0.0, now - float(last_finished)), 1)
    return payload


def deep_health_checks(
    *,
    stream_check: dict | None = None,
    streams_lock_health_fn,
    all_sessions_fn,
    load_projects_fn,
    active_state_db_path_fn,
) -> tuple[dict, bool]:
    """Run cheap probes that exercise the state paths used by the UI shell."""
    checks: dict[str, dict] = {}

    checks["streams_lock"] = stream_check if stream_check is not None else streams_lock_health_fn()
    if checks["streams_lock"].get("status") != "ok":
        return checks, False

    t0 = time.time()
    try:
        sessions = all_sessions_fn()
        checks["sessions"] = {
            "status": "ok",
            "count": len(sessions),
            "ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as exc:
        checks["sessions"] = {
            "status": "error",
            "error": type(exc).__name__,
            "ms": round((time.time() - t0) * 1000, 1),
        }

    t0 = time.time()
    try:
        projects = load_projects_fn(_migrate=False)
        checks["projects"] = {
            "status": "ok",
            "count": len(projects),
            "ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as exc:
        checks["projects"] = {
            "status": "error",
            "error": type(exc).__name__,
            "ms": round((time.time() - t0) * 1000, 1),
        }

    t0 = time.time()
    try:
        db_path = active_state_db_path_fn()
        if not db_path.exists():
            checks["state_db"] = {
                "status": "missing",
                "ms": round((time.time() - t0) * 1000, 1),
            }
        else:
            with closing(sqlite3.connect(str(db_path))) as conn:
                conn.execute("PRAGMA schema_version").fetchone()
            checks["state_db"] = {
                "status": "ok",
                "ms": round((time.time() - t0) * 1000, 1),
            }
    except Exception as exc:
        checks["state_db"] = {
            "status": "error",
            "error": type(exc).__name__,
            "ms": round((time.time() - t0) * 1000, 1),
        }

    healthy = all(
        check.get("status") in {"ok", "missing"}
        for check in checks.values()
    )
    return checks, healthy


def handle_health(
    handler,
    parsed,
    *,
    sessions,
    server_start_time,
    streams_lock_health_fn,
    run_lifecycle_health_fn,
    deep_health_checks_fn,
    accept_loop_health_fn=accept_loop_health,
    responder=j,
):
    deep = parse_qs(parsed.query or "").get("deep", [""])[0].lower() in {"1", "true", "yes", "on"}
    stream_check = streams_lock_health_fn()
    run_check = run_lifecycle_health_fn()
    payload = {
        "status": "ok" if stream_check.get("status") == "ok" else "degraded",
        "sessions": len(sessions),
        "active_streams": int(stream_check.get("active_streams") or 0),
        "active_runs": int(run_check.get("active_runs") or 0),
        "runs": run_check.get("runs", []),
        "last_run_finished_at": run_check.get("last_run_finished_at"),
        "uptime_seconds": round(time.time() - server_start_time, 1),
        "accept_loop": accept_loop_health_fn(handler),
    }
    if "oldest_run_age_seconds" in run_check:
        payload["oldest_run_age_seconds"] = run_check["oldest_run_age_seconds"]
    if "idle_seconds_since_last_run" in run_check:
        payload["idle_seconds_since_last_run"] = run_check["idle_seconds_since_last_run"]
    if deep:
        if stream_check.get("status") != "ok":
            payload["checks"] = {"streams_lock": stream_check}
            return responder(handler, payload, status=503)
        checks, healthy = deep_health_checks_fn(stream_check=stream_check)
        payload["checks"] = checks
        if not healthy:
            payload["status"] = "degraded"
            return responder(handler, payload, status=503)
    if payload["status"] != "ok":
        return responder(handler, payload, status=503)
    return responder(handler, payload)

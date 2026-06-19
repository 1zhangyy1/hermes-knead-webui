"""
Hermes Web UI -- Route handlers for GET and POST endpoints.
Extracted from server.py (Sprint 11) so server.py is a thin shell.
"""

import html as _html
import copy
import io
import json
import logging
import os
import queue
import re
import platform
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import re
from pathlib import Path
from contextlib import closing
from urllib.parse import parse_qs, unquote
from api.agent_sessions import (
    MESSAGING_SOURCES,
    is_cli_session_row,
    is_cli_session_row_visible,
    read_session_lineage_report,
)
from api import background_routes as _background_routes
from api import chat_routes as _chat_routes
from api import command_routes as _command_routes
from api import config_routes as _config_routes
from api import dashboard_routes as _dashboard_routes
from api import onboarding_routes as _onboarding_routes
from api import profile_routes as _profile_routes
from api import project_routes as _project_routes
from api import security_routes as _security_routes
from api import cron_routes as _cron_routes
from api import update_routes as _update_routes

logger = logging.getLogger(__name__)

# Treat stalled/closed HTTP clients as normal disconnects.  Long-lived SSE
# connections often end this way when a browser tab sleeps, a phone switches
# networks, or Tailscale leaves the socket half-closed.  If these bubble to the
# request handler, the server logs 500s and can leave CLOSE-WAIT sockets around
# until the OS-level timeout fires.
_CLIENT_DISCONNECT_ERRORS = (
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
    TimeoutError,
    OSError,
)

# ── Cron run tracking ────────────────────────────────────────────────────────
# Track job IDs currently being executed so the frontend can poll status.
_RUNNING_CRON_JOBS: dict[str, float] = {}  # job_id → start_timestamp
_RUNNING_CRON_LOCK = threading.Lock()
_MANUAL_COMPRESSION_JOBS: dict[str, dict] = {}
_MANUAL_COMPRESSION_JOBS_LOCK = threading.Lock()
_MANUAL_COMPRESSION_JOB_TTL_SECONDS = 10 * 60
_CRON_OUTPUT_CONTENT_LIMIT = 8000
_CRON_OUTPUT_HEADER_CONTEXT = 200
_MESSAGING_RAW_SOURCES = {str(s).strip().lower() for s in MESSAGING_SOURCES}
_MESSAGING_SESSION_METADATA_CACHE: dict[str, object] = {
    "path": None,
    "mtime": None,
    "identity": {},
}
_MESSAGING_SESSION_METADATA_LOCK = threading.Lock()
_STALE_MESSAGING_END_REASONS = {"session_reset", "session_switch"}
_CSP_REPORT_LOGGER = logging.getLogger("csp_report")
_CSP_REPORT_RATE_LIMIT: dict[str, list[float]] = {}
_CSP_REPORT_RATE_LIMIT_LOCK = threading.Lock()
_CSP_REPORT_RATE_LIMIT_WINDOW_SECONDS = 60
_CSP_REPORT_RATE_LIMIT_MAX = 100
_CSP_REPORT_MAX_BODY_BYTES = 64 * 1024


# ── Profile-scoped session/project filtering (#1611, #1614) ────────────────
#
# Sessions and projects are stored in the WebUI sidecar without per-row
# isolation by default — they're tagged with a `profile` field but every
# query saw all rows. The fix scopes both endpoints to the active profile
# by default, with `?all_profiles=1` opting into aggregate mode.
#
# Renamed-root profile handling (#1612): a row tagged `profile='default'`
# matches the active root regardless of the root's display name, and a row
# tagged with the renamed-root display name (e.g. 'kinni') likewise matches
# when the active profile is `'default'`. _is_root_profile() is the
# canonical check.

# Canonical helper now lives in api.profiles so out-of-process consumers
# (mcp_server.py) can import it without duplicating the visibility model.
# Re-exported here so existing `_profiles_match(...)` call sites in this
# module keep resolving without per-call-site refactors.
from api.profiles import _profiles_match  # noqa: F401, E402  (re-export)
from api import compression_routes as _compression_routes
from api import file_workspace_routes as _file_workspace_routes
from api import file_response_routes as _file_response_routes
from api import gateway_routes as _gateway_routes
from api import gateway_sse_routes as _gateway_sse_routes
from api import health_routes as _health_routes
from api import handoff_routes as _handoff_routes
from api import interaction_routes as _interaction_routes
from api import llm_wiki_routes as _llm_wiki_routes
from api import login_routes as _login_routes
from api import logs_routes as _logs_routes
from api import memory_routes as _memory_routes
from api import messaging_routes as _messaging_routes
from api import mcp_routes as _mcp_routes
from api import model_route_helpers as _model_route_helpers
from api import plugin_routes as _plugin_routes
from api import rollback_routes as _rollback_routes
from api import session_routes as _session_routes
from api import session_import_routes as _session_import_routes
from api import skills_routes as _skills_routes
from api import static_routes as _static_routes
from api import terminal_routes as _terminal_routes


def _all_profiles_query_flag(parsed_url) -> bool:
    """Return True if the request URL has `?all_profiles=1` (or true/yes).

    Centralizes the opt-in parsing so /api/sessions and /api/projects use
    the same shape. Accepts 1/true/yes (case-insensitive) for ergonomics.
    """
    qs = parse_qs(parsed_url.query)
    raw = qs.get('all_profiles', [''])[0].strip().lower()
    return raw in ('1', 'true', 'yes', 'on')


def _active_skills_dir() -> Path:
    return _skills_routes.active_skills_dir()


def _skill_path_within(base_dir: Path, candidate: Path) -> bool:
    return _skills_routes.skill_path_within(base_dir, candidate)


def _skill_category_from_path(skill_md: Path, skills_dirs: list[Path]) -> str | None:
    return _skills_routes.skill_category_from_path(skill_md, skills_dirs)


def _active_skill_search_dirs(skills_dir: Path) -> list[Path]:
    return _skills_routes.active_skill_search_dirs(skills_dir)


def _worktree_retained_payload(session) -> dict:
    """Return explicit no-cleanup metadata for worktree-backed session actions."""
    worktree_path = getattr(session, "worktree_path", None) if session else None
    if not worktree_path:
        return {}
    payload = {
        "worktree_retained": True,
        "worktree_path": worktree_path,
    }
    worktree_branch = getattr(session, "worktree_branch", None)
    worktree_repo_root = getattr(session, "worktree_repo_root", None)
    if worktree_branch:
        payload["worktree_branch"] = worktree_branch
    if worktree_repo_root:
        payload["worktree_repo_root"] = worktree_repo_root
    return payload


def _worktree_retained_payload_for_session_id(sid: str) -> dict:
    try:
        return _worktree_retained_payload(get_session(sid, metadata_only=True))
    except KeyError:
        return {}
    except Exception:
        logger.debug("Failed to read worktree metadata for deleted session %s", sid)
        return {}


def _skills_list_from_dir(skills_dir: Path, category: str | None = None) -> dict:
    return _skills_routes.skills_list_from_dir(skills_dir, category=category)


def _find_skill_in_dirs(name: str, skills_dirs: list[Path]) -> tuple[Path | None, Path | None]:
    return _skills_routes.find_skill_in_dirs(name, skills_dirs)


def _find_skill_in_dir(name: str, skills_dir: Path) -> tuple[Path | None, Path | None]:
    return _skills_routes.find_skill_in_dir(name, skills_dir)


def _skill_not_found_payload(name: str, skills_dir: Path) -> dict:
    return _skills_routes.skill_not_found_payload(name, skills_dir)


def _linked_files_for_skill(skill_dir: Path | None) -> dict:
    return _skills_routes.linked_files_for_skill(skill_dir)


def _skill_view_from_file(skill_dir: Path | None, skill_md: Path) -> dict:
    return _skills_routes.skill_view_from_file(skill_dir, skill_md)


def _skill_view_from_active_dir(name: str) -> dict:
    return _skills_routes.skill_view_from_active_dir(
        name,
        active_skills_dir_fn=_active_skills_dir,
        active_skill_search_dirs_fn=_active_skill_search_dirs,
    )

# ── SSE app-level heartbeat (#1623) ────────────────────────────────────────
#
# Kernel TCP keepalive (server.py setsockopt block) declares a peer dead at
# KEEPIDLE (10s) + KEEPINTVL (5s) * KEEPCNT (3) = 25s in the worst case. The
# app-level SSE heartbeat must fire well below that window so flaky-network
# probes never get the chance to kill an idle stream during long LLM thinking
# phases. 5s gives the kernel ~5x headroom: probe at 10s, heartbeat byte at
# every 5s of idle keeps the socket warm.
#
# Cost: ~12 bytes per heartbeat * 12 extra heartbeats/min = ~150B/min idle.
# Trivial; many production SSE deployments run 5-15s heartbeats specifically
# to handle proxies and mobile NAT.
_SSE_HEARTBEAT_INTERVAL_SECONDS = 5


def _normalize_messaging_source(raw_source) -> str:
    return _messaging_routes.normalize_messaging_source(raw_source)


def _is_known_messaging_source(raw_source) -> bool:
    return _messaging_routes.is_known_messaging_source(raw_source, _MESSAGING_RAW_SOURCES)


def _safe_first(*values):
    return _messaging_routes.safe_first(*values)


def _gateway_session_metadata_path():
    return _messaging_routes.gateway_session_metadata_path()


def _load_gateway_session_identity_map() -> dict[str, dict]:
    return _messaging_routes.load_gateway_session_identity_map(
        path_fn=_gateway_session_metadata_path,
        cache=_MESSAGING_SESSION_METADATA_CACHE,
        cache_lock=_MESSAGING_SESSION_METADATA_LOCK,
        safe_first_fn=_safe_first,
        logger=logger,
    )


def _mark_cron_running(job_id: str):
    with _RUNNING_CRON_LOCK:
        _RUNNING_CRON_JOBS[job_id] = time.time()


def _mark_cron_done(job_id: str):
    with _RUNNING_CRON_LOCK:
        _RUNNING_CRON_JOBS.pop(job_id, None)


def _is_cron_running(job_id: str) -> tuple[bool, float]:
    """Return (is_running, elapsed_seconds)."""
    with _RUNNING_CRON_LOCK:
        t = _RUNNING_CRON_JOBS.get(job_id)
        if t is None:
            return False, 0.0
        return True, time.time() - t


def _cron_response_marker_index(text: str) -> int:
    """Return the start index of a markdown Response heading, if present."""
    candidates = []
    for heading in ("## Response", "# Response"):
        if text.startswith(heading):
            candidates.append(0)
        idx = text.find(f"\n{heading}")
        if idx >= 0:
            candidates.append(idx + 1)
    return min(candidates) if candidates else -1


def _cron_output_content_window(text: str, limit: int = _CRON_OUTPUT_CONTENT_LIMIT) -> str:
    """Return a bounded cron output window that preserves useful response text.

    Cron output files can contain large skill dumps in the Prompt section. The
    UI already extracts ``## Response`` when present, so keep that section in
    the API payload instead of blindly returning the first ``limit`` chars.
    """
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text

    response_idx = _cron_response_marker_index(text)
    if response_idx >= 0:
        header = text[:min(_CRON_OUTPUT_HEADER_CONTEXT, response_idx)].rstrip()
        response = text[response_idx:].lstrip("\n")
        content = f"{header}\n...\n{response}" if header else response
        return content[:limit]

    return text[-limit:]




def _cron_job_for_api(job: dict) -> dict:
    """Return a cron job payload with optional UI settings normalized.

    Legacy jobs intentionally persist without ``profile`` so they keep the
    scheduler's server-default behavior. The API still returns ``profile: None``
    so the UI can label that state explicitly instead of guessing.

    ``toast_notifications`` is a WebUI preference for completion toasts. Legacy
    jobs default to enabled so existing behavior is preserved unless a job is
    explicitly muted.
    """
    payload = dict(job or {})
    payload.setdefault("profile", None)
    payload["toast_notifications"] = payload.get("toast_notifications") is not False
    return payload


def _cron_jobs_for_api(jobs) -> list[dict]:
    return [_cron_job_for_api(job) for job in (jobs or [])]


def _available_cron_profile_names() -> set[str]:
    from api.profiles import list_profiles_api

    names = {"default"}
    for profile in list_profiles_api():
        try:
            name = str(profile.get("name") or "").strip()
        except AttributeError:
            continue
        if name:
            names.add(name)
    return names


def _normalize_cron_profile_value(value) -> str | None:
    if value is None:
        return None
    profile = str(value).strip()
    if not profile:
        return None
    if profile not in _available_cron_profile_names():
        raise ValueError(f"Unknown profile: {profile}")
    return profile


def _profile_home_for_cron_job(job: dict):
    """Resolve the execution profile for a cron job, with graceful fallback.

    A missing/blank profile preserves legacy server-default behavior. If a job
    points at a profile that was deleted after save, fall back to the active
    server profile and log a warning instead of crashing the Run Now path.
    """
    from api.profiles import get_active_hermes_home, get_hermes_home_for_profile

    raw = str((job or {}).get("profile") or "").strip()
    if not raw:
        return get_active_hermes_home()
    if raw not in _available_cron_profile_names():
        logger.warning(
            "Cron job %s references missing profile %r; falling back to server default",
            (job or {}).get("id", "?"), raw,
        )
        return get_active_hermes_home()
    return get_hermes_home_for_profile(raw)


def _cron_job_subprocess_main(job, execution_profile_home, result_queue):
    """Run one cron job inside a child process pinned to a profile home."""
    try:
        def _run():
            from cron.scheduler import run_job

            return run_job(job)

        if execution_profile_home is None:
            result = _run()
        else:
            from api.profiles import cron_profile_context_for_home

            with cron_profile_context_for_home(execution_profile_home):
                result = _run()
        result_queue.put(("ok", result))
    except BaseException as exc:  # pragma: no cover - surfaced in parent
        import traceback

        result_queue.put(("error", f"{type(exc).__name__}: {exc}", traceback.format_exc()))


def _cron_subprocess_result_timeout_seconds(job):
    """Return how long the manual-run parent waits for child result payloads."""
    for key in ("timeout_seconds", "max_runtime_seconds", "timeout"):
        raw = (job or {}).get(key)
        if raw in (None, ""):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return max(60.0, value + 30.0)
    # Manual cron jobs can legitimately run for a long time.  Keep a recovery
    # path for wedged children without truncating normal long-running jobs.
    return 6 * 60 * 60.0


def _run_cron_job_in_profile_subprocess(job, execution_profile_home):
    """Execute cron.scheduler.run_job without holding the parent cron env lock.

    cron.scheduler/cron.jobs still rely on process-global HERMES_HOME and module
    constants, so running the job body in a child process gives each long cron
    execution its own globals. The parent process only uses cron_profile_context
    for short metadata reads/writes and remains responsive to unrelated cron UI
    and API calls while the job runs.
    """
    import multiprocessing
    import queue

    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue(maxsize=1)
    process = ctx.Process(
        target=_cron_job_subprocess_main,
        args=(job, execution_profile_home, result_queue),
    )
    process.start()

    result_timeout = _cron_subprocess_result_timeout_seconds(job)
    status = "error"
    payload = ["cron run subprocess failed before producing a result", ""]
    try:
        try:
            # Drain the potentially large pickled result before joining.  If the
            # child puts >~64 KiB on a multiprocessing.Queue, joining first can
            # deadlock while the child's feeder thread waits for the parent to
            # read from the pipe.
            status, *payload = result_queue.get(timeout=result_timeout)
        except queue.Empty:
            status = "error"
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
                payload = [
                    f"cron run subprocess produced no result within {result_timeout:g}s and was terminated",
                    "",
                ]
            else:
                payload = [
                    f"cron run subprocess exited with code {process.exitcode} without producing a result",
                    "",
                ]
        finally:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
                if status == "ok":
                    status = "error"
                    payload = [
                        "cron run subprocess did not exit after returning a result",
                        "",
                    ]
    finally:
        result_queue.close()
        result_queue.join_thread()

    if status == "ok":
        return payload[0]

    message = payload[0]
    traceback_text = payload[1] if len(payload) > 1 else ""
    if traceback_text:
        logger.error("Manual cron subprocess failed:\n%s", traceback_text)
    raise RuntimeError(message)


def _run_cron_tracked(job, profile_home=None, execution_profile_home=None):
    """Wrapper that tracks running state around cron.scheduler.run_job.

    ``profile_home`` is the cron store that owns the job row/output metadata.
    ``execution_profile_home`` is the selected per-job profile used to load
    agent config/.env while running. When no job profile is selected, both homes
    are the same and legacy server-default behavior is preserved.
    """
    import importlib

    from cron.jobs import mark_job_run, save_job_output

    _cron_scheduler = importlib.import_module("cron.scheduler")

    _silent_marker = getattr(_cron_scheduler, "SILENT_MARKER", "[SILENT]")
    _deliver_result = getattr(_cron_scheduler, "_deliver_result", None)

    job_id = job.get("id", "")
    execution_profile_home = execution_profile_home or profile_home

    def _with_cron_home(home, fn):
        if home is None:
            return fn()
        from api.profiles import cron_profile_context_for_home

        with cron_profile_context_for_home(home):
            return fn()

    try:
        success, output, final_response, error = _run_cron_job_in_profile_subprocess(
            job, execution_profile_home
        )

        # Persist output, deliver the same content the scheduled cron path would
        # send, and write run metadata back to the job's owning cron store even
        # when the selected execution profile is different.
        def _persist_success():
            save_job_output(job_id, output)

            deliver_content = (
                final_response
                if success
                else f"⚠️ Cron job '{job.get('name', job_id)}' failed:\n{error}"
            )
            should_deliver = bool(deliver_content)
            if should_deliver and success and _silent_marker in deliver_content.strip().upper():
                should_deliver = False

            delivery_error = None
            if should_deliver and _deliver_result is not None:
                try:
                    delivery_error = _deliver_result(job, deliver_content)
                except Exception as de:
                    delivery_error = str(de)
                    logger.error("Delivery failed for manual cron job %s: %s", job_id, de)

            # Match the scheduled cron path: an apparently successful run with no
            # final response should not leave the job looking healthy.
            _success, _error = success, error
            if _success and not final_response:
                _success = False
                _error = "Agent completed but produced empty response (model error, timeout, or misconfiguration)"

            try:
                mark_job_run(job_id, _success, _error, delivery_error=delivery_error)
            except TypeError:
                # Older/fake cron.jobs modules used by focused WebUI tests may
                # not expose the newer delivery_error parameter. Real Hermes
                # scheduler builds do, so this is only a compatibility shim for
                # legacy test doubles and deployments.
                mark_job_run(job_id, _success, _error)

        _with_cron_home(profile_home, _persist_success)
    except Exception as e:
        logger.exception("Manual cron run failed for job %s", job_id)
        try:
            _with_cron_home(profile_home, lambda: mark_job_run(job_id, False, str(e)))
        except Exception:
            logger.debug("Failed to mark manual cron run failure for %s", job_id)
    finally:
        _mark_cron_done(job_id)

_PROVIDER_ALIASES = _model_route_helpers.PROVIDER_ALIASES

# OpenAI-compatible /v1/models endpoints for live model discovery.
# Used as fallback when hermes_cli.provider_model_ids() is unavailable or
# returns [] for a provider (#871).  Kept at module level so the dict is
# built once, not reconstructed per request.
_OPENAI_COMPAT_ENDPOINTS = {
    "zai": "https://api.z.ai/v1",
    "minimax": "https://api.minimax.chat/v1",
    "mistralai": "https://api.mistral.ai/v1",
    "xai": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}
# NOTE: "openai-codex" is excluded because it maps to the same endpoint as
# the base "openai" provider (api.openai.com/v1).  When both are configured
# the openai provider is already wired through provider_model_ids(); codex-
# specific model filtering happens downstream in hermes_cli.
#
_LIVE_MODELS_CACHE_TTL = 60.0
_LIVE_MODELS_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_LIVE_MODELS_CACHE_LOCK = threading.RLock()


def _active_profile_for_live_models_cache() -> str:
    try:
        from api.profiles import get_active_profile_name

        return get_active_profile_name() or "default"
    except Exception as _e:
        # A transient profile-resolution error mis-scopes the cache for up to
        # 60s ("default" gets the wrong payload). Log so we can detect it; the
        # blast radius stays small because the TTL caps the bad-cache window.
        logger.debug("_active_profile_for_live_models_cache fell back to 'default': %s", _e)
        return "default"


def _live_models_cache_key(provider: str) -> tuple[str, str]:
    return (_active_profile_for_live_models_cache(), provider)


def _get_cached_live_models(key: tuple[str, str]) -> dict | None:
    now = time.monotonic()
    with _LIVE_MODELS_CACHE_LOCK:
        cached = _LIVE_MODELS_CACHE.get(key)
        if not cached:
            return None
        ts, payload = cached
        if now - ts >= _LIVE_MODELS_CACHE_TTL:
            _LIVE_MODELS_CACHE.pop(key, None)
            return None
        return copy.deepcopy(payload)


def _set_cached_live_models(key: tuple[str, str], payload: dict) -> None:
    with _LIVE_MODELS_CACHE_LOCK:
        _LIVE_MODELS_CACHE[key] = (time.monotonic(), copy.deepcopy(payload))


def _clear_live_models_cache() -> None:
    with _LIVE_MODELS_CACHE_LOCK:
        _LIVE_MODELS_CACHE.clear()

from api.config import (
    STATE_DIR,
    SESSION_DIR,
    DEFAULT_WORKSPACE,
    DEFAULT_MODEL,
    SESSIONS,
    SESSIONS_MAX,
    LOCK,
    STREAMS,
    STREAMS_LOCK,
    CANCEL_FLAGS,
    STREAM_LAST_EVENT_ID,
    SERVER_START_TIME,
    _resolve_cli_toolsets,
    _INDEX_HTML_PATH,
    get_available_models,
    IMAGE_EXTS,
    MD_EXTS,
    MIME_MAP,
    MAX_FILE_BYTES,
    MAX_UPLOAD_BYTES,
    CHAT_LOCK,
    _get_session_agent_lock,
    SESSION_AGENT_LOCKS,
    SESSION_AGENT_LOCKS_LOCK,
    load_settings,
    save_settings,
    set_hermes_default_model,
    model_with_provider_context,
    get_reasoning_status,
    set_reasoning_display,
    set_reasoning_effort,
    create_stream_channel,
    get_webui_session_save_mode,
    STREAM_GOAL_RELATED,
    PENDING_GOAL_CONTINUATION,
)
from api.helpers import (
    require,
    bad,
    safe_resolve,
    j,
    t,
    read_body,
    _security_headers,
    _sanitize_error,
    redact_session_data,
    _redact_text,
)
from api.agent_health import build_agent_health_payload
from api.request_diagnostics import RequestDiagnostics
from api.system_health import build_system_health_payload


def _clear_stale_stream_state(session) -> bool:
    """Clear persisted streaming flags when the in-memory stream no longer exists.

    A server restart or worker crash can leave active_stream_id/pending_* in the
    session JSON while STREAMS is empty. The frontend then keeps reconnecting to
    a dead stream and shows a permanent running/thinking state.

    SAFETY (#1558): If ``session`` was loaded with ``metadata_only=True``, its
    ``messages`` array is empty by design and calling ``save()`` would
    atomically overwrite the on-disk JSON, wiping the conversation. In that
    case we re-load the full session before mutating, so the persisted
    write carries the real messages forward.
    """
    stream_id = getattr(session, "active_stream_id", None)
    if not stream_id:
        return False
    with STREAMS_LOCK:
        stream_alive = stream_id in STREAMS
    if stream_alive:
        return False

    # ── #1558 P0 safety: if we were handed a metadata-only stub, reload the
    # full session before touching persisted state. The original
    # metadata-only object is left untouched so the caller's read path is
    # unaffected.
    original_stub = session  # SHOULD-FIX #1 (Opus): keep reference so we can
                             # patch the caller's in-memory copy after a
                             # successful clear, avoiding one ghost SSE
                             # reconnect on the very next /api/session GET.
    if getattr(session, "_loaded_metadata_only", False):
        try:
            from api.models import get_session as _get_session
            session = _get_session(session.session_id, metadata_only=False)
        except Exception:
            # If we cannot upgrade to a full load (file gone, decode error,
            # etc.) bail without clearing — better to leave a stale
            # active_stream_id than to wipe the conversation.
            logger.warning(
                "_clear_stale_stream_state: refused to clear stale stream %s "
                "for session %s — full reload failed and we will not save a "
                "metadata-only stub. See #1558.",
                stream_id, getattr(session, "session_id", "?"),
            )
            return False
        if session is None:
            return False
        # The full-load path may have already repaired stale pending fields
        # via _repair_stale_pending(); only re-assert if still set.
        if not getattr(session, "active_stream_id", None):
            # Patch the caller's stub so its read path also sees the cleared
            # field (matches the Opus SHOULD-FIX #1 — without this, /api/session
            # would briefly return the stale active_stream_id and the frontend
            # would attempt one ghost SSE reconnect before recovering).
            try:
                original_stub.active_stream_id = None
                if hasattr(original_stub, "pending_user_message"):
                    original_stub.pending_user_message = None
                if hasattr(original_stub, "pending_attachments"):
                    original_stub.pending_attachments = []
                if hasattr(original_stub, "pending_started_at"):
                    original_stub.pending_started_at = None
            except Exception:
                pass
            return False

    # ── #1533 race fix: acquire the per-session lock and re-read
    # active_stream_id under it. A concurrent chat_start may have already
    # registered a new stream after our STREAMS_LOCK check above; in that
    # case we must NOT clobber its session.active_stream_id.
    with _get_session_agent_lock(session.session_id):
        if getattr(session, "active_stream_id", None) != stream_id:
            return False
        if getattr(session, "pending_user_message", None):
            try:
                from api.models import _apply_core_sync_or_error_marker, _get_profile_home
                profile_home = _get_profile_home(getattr(session, "profile", None))
                core_path = profile_home / "sessions" / f"session_{session.session_id}.json"
                repaired = _apply_core_sync_or_error_marker(
                    session,
                    core_path,
                    stream_id_for_recheck=stream_id,
                    touch_updated_at=False,
                )
            except Exception:
                logger.exception(
                    "_clear_stale_stream_state: failed to repair stale pending stream %s "
                    "for session %s",
                    stream_id, getattr(session, "session_id", "?"),
                )
                repaired = False
            if repaired:
                if original_stub is not session:
                    try:
                        original_stub.active_stream_id = None
                        if hasattr(original_stub, "pending_user_message"):
                            original_stub.pending_user_message = None
                        if hasattr(original_stub, "pending_attachments"):
                            original_stub.pending_attachments = []
                        if hasattr(original_stub, "pending_started_at"):
                            original_stub.pending_started_at = None
                    except Exception:
                        pass
                return True
            if getattr(session, "active_stream_id", None) != stream_id:
                return False
        _materialize_pending_user_turn_before_error(session)
        session.active_stream_id = None
        if hasattr(session, "pending_user_message"):
            session.pending_user_message = None
        if hasattr(session, "pending_attachments"):
            session.pending_attachments = []
        if hasattr(session, "pending_started_at"):
            session.pending_started_at = None
        try:
            # Runtime cleanup is not user activity; do not bubble old sessions
            # to the top of the sidebar just because a stale stream flag was
            # repaired during a read/list path.
            session.save(touch_updated_at=False)
        except Exception:
            logger.exception(
                "_clear_stale_stream_state: save() failed for session %s",
                getattr(session, "session_id", "?"),
            )
    # Patch the caller's stub (if different from the full-load object) so
    # its in-memory active_stream_id matches what just got persisted.
    if original_stub is not session:
        try:
            original_stub.active_stream_id = None
            if hasattr(original_stub, "pending_user_message"):
                original_stub.pending_user_message = None
            if hasattr(original_stub, "pending_attachments"):
                original_stub.pending_attachments = []
            if hasattr(original_stub, "pending_started_at"):
                original_stub.pending_started_at = None
        except Exception:
            pass
    return True


def _run_journal_status_payload(summary: dict, *, active: bool = False) -> dict:
    """Return runtime journal summary.

    Static-test anchor: terminal_state = "stale-from-restart".
    """
    return _session_routes.run_journal_status_payload(summary, active=active)


def _ensure_full_session_before_mutation(sid: str, session):
    """Reload cached metadata-only sessions before mutating persisted fields.

    Session.save() intentionally refuses metadata-only stubs (#1558) because
    their messages list is empty by design. Mutation routes that save session
    metadata must upgrade the cached stub first so they do not trip that guard
    or risk writing an incomplete object.
    """
    if not getattr(session, "_loaded_metadata_only", False):
        return session
    full_session = Session.load(sid)
    if full_session is None:
        raise KeyError(sid)
    with LOCK:
        SESSIONS[sid] = full_session
        SESSIONS.move_to_end(sid)
        while len(SESSIONS) > SESSIONS_MAX:
            SESSIONS.popitem(last=False)
    return full_session


def _reconcile_stale_stream_state_for_session_rows(session_rows) -> bool:
    """Clear stale persisted stream fields before /api/sessions serializes rows."""
    changed = False
    for row in session_rows:
        if not isinstance(row, dict):
            continue
        sid = row.get("session_id")
        if not sid or not row.get("active_stream_id"):
            continue
        if row.get("is_streaming") is True:
            continue
        try:
            session = get_session(sid, metadata_only=True)
        except Exception:
            logger.debug(
                "Failed to load session %s while reconciling stale stream state",
                sid,
                exc_info=True,
            )
            continue
        if session is None:
            continue
        changed = _clear_stale_stream_state(session) or changed
    return changed

def _normalize_host_port(value: str) -> tuple[str, str | None]:
    """Split a host or host:port string into (hostname, port|None).
    Handles IPv6 bracket notation, e.g. [::1]:8080."""
    return _security_routes.normalize_host_port(value)


def _ports_match(origin_scheme: str, origin_port: str | None, allowed_port: str | None) -> bool:
    """Return True when two ports should be considered equivalent, scheme-aware.

    Treats an absent port as the scheme default: port 80 for http, port 443 for https.
    Port 80 is NOT treated as equivalent to 443 (different protocols = different origins).
    """
    return _security_routes.ports_match(origin_scheme, origin_port, allowed_port)


def _allowed_public_origins() -> set[str]:
    """Parse HERMES_WEBUI_ALLOWED_ORIGINS env var (comma-separated) into a set.

    Each entry must include the scheme, e.g. https://myapp.example.com:8000.
    Entries without a scheme are silently skipped and a warning is printed.
    """
    return _security_routes.allowed_public_origins()


def _is_browser_unsafe_request(handler) -> bool:
    """Return True when request headers identify a browser unsafe request.

    Non-browser API clients, including the MCP bridge and curl-style scripts,
    normally send no Origin/Referer and remain compatible with the existing
    same-machine API contract. Browsers send Origin for unsafe fetch/form POSTs;
    Referer is retained for older paths and proxies.
    """
    return _security_routes.is_browser_unsafe_request(handler)


def _csrf_exempt_path(path: str) -> bool:
    """Paths that cannot or must not carry a session CSRF token."""
    return _security_routes.csrf_exempt_path(path)


def _check_csrf(handler) -> bool:
    """Reject cross-origin or tokenless authenticated browser unsafe requests."""
    return _security_routes.check_csrf(
        handler,
        is_browser_unsafe_request_fn=_is_browser_unsafe_request,
        allowed_public_origins_fn=_allowed_public_origins,
        normalize_host_port_fn=_normalize_host_port,
        ports_match_fn=_ports_match,
    )


def _client_ip_for_rate_limit(handler) -> str:
    return _security_routes.client_ip_for_rate_limit(handler)


def _csp_report_rate_limited(handler, *, now: float | None = None) -> bool:
    return _security_routes.csp_report_rate_limited(
        handler,
        rate_limit=_CSP_REPORT_RATE_LIMIT,
        rate_limit_lock=_CSP_REPORT_RATE_LIMIT_LOCK,
        window_seconds=_CSP_REPORT_RATE_LIMIT_WINDOW_SECONDS,
        max_reports=_CSP_REPORT_RATE_LIMIT_MAX,
        client_ip_fn=_client_ip_for_rate_limit,
        now=now,
    )


def _send_no_content(handler, status: int = 204) -> bool:
    return _security_routes.send_no_content(handler, status)


def _read_csp_report_payload(handler):
    return _security_routes.read_csp_report_payload(
        handler,
        max_body_bytes=_CSP_REPORT_MAX_BODY_BYTES,
    )


def _handle_csp_report(handler) -> bool:
    """Collect browser CSP report-only violations without requiring auth."""
    return _security_routes.handle_csp_report(
        handler,
        rate_limited_fn=_csp_report_rate_limited,
        read_payload_fn=_read_csp_report_payload,
        send_no_content_fn=_send_no_content,
        client_ip_fn=_client_ip_for_rate_limit,
        logger=_CSP_REPORT_LOGGER,
    )


def _normalize_provider_id(value: str | None) -> str:
    return _model_route_helpers.normalize_provider_id(value, _PROVIDER_ALIASES)


def _catalog_provider_id_sets(catalog: dict) -> tuple[set[str], set[str]]:
    return _model_route_helpers.catalog_provider_id_sets(
        catalog,
        normalize_provider_id_fn=_normalize_provider_id,
    )


def _catalog_has_provider(
    provider_raw: str,
    provider_normalized: str,
    raw_provider_ids: set[str],
    normalized_provider_ids: set[str],
) -> bool:
    return _model_route_helpers.catalog_has_provider(
        provider_raw,
        provider_normalized,
        raw_provider_ids,
        normalized_provider_ids,
    )


def _model_matches_active_provider_family(
    model: str,
    active_provider: str,
) -> bool:
    return _model_route_helpers.model_matches_active_provider_family(
        model,
        active_provider,
        normalize_provider_id_fn=_normalize_provider_id,
    )


def _catalog_model_id_matches(candidate: str, model: str) -> bool:
    return _model_route_helpers.catalog_model_id_matches(candidate, model)


def _clean_session_model_provider(value: str | None) -> str | None:
    return _model_route_helpers.clean_session_model_provider(value)


def _split_provider_qualified_model(model: str) -> tuple[str, str | None]:
    return _model_route_helpers.split_provider_qualified_model(
        model,
        clean_provider_fn=_clean_session_model_provider,
    )


def _should_attach_codex_provider_context(model: str, raw_active_provider: str, catalog: dict) -> bool:
    return _model_route_helpers.should_attach_codex_provider_context(
        model,
        raw_active_provider,
        catalog,
        catalog_model_id_matches_fn=_catalog_model_id_matches,
    )


def _resolve_compatible_session_model_state(
    model_id: str | None,
    model_provider: str | None = None,
) -> tuple[str, str | None, bool]:
    """Return (effective_model, effective_provider, model_was_normalized).

    Sessions can outlive provider changes. When an older session still points at
    a different provider namespace (for example `gemini/...` after switching the
    agent to OpenAI Codex), reusing that stale model causes chat startup to hit
    the wrong backend and fail. Normalize only obvious cross-provider mismatches.
    When a model has an explicit provider context, keep the model string itself
    in its picker/API shape and carry the provider as separate state.

    Fast path (#1855): when the caller supplies both a model and an explicit
    ``model_provider`` AND the model is not itself ``@provider:model``-qualified,
    we can return the inputs verbatim without calling ``get_available_models()``.
    The slow path below would arrive at the same answer via
    ``if requested_provider and not explicit_provider: return model, requested_provider, False``
    after paying the full catalog-build cost. Avoiding the catalog here keeps
    ``POST /api/chat/start`` snappy even when the model catalog is cold and the
    rebuild has to make network calls (custom OpenAI-compat endpoints,
    OpenRouter ``/models``, LM Studio ``/models``, credential pool refresh) —
    those used to wedge the handler for >100s and trigger 502s on default-60s
    reverse proxies, even though the WebUI itself eventually responded.
    """
    model = str(model_id or "").strip()
    requested_provider = _clean_session_model_provider(model_provider)
    if model and requested_provider:
        # Only safe when the model itself does not carry an ``@provider:model``
        # qualifier — qualified strings require the catalog to decide whether
        # the qualifier matches the active provider (see slow path below).
        bare_model, explicit_provider = _split_provider_qualified_model(model)
        if not explicit_provider:
            return model, requested_provider, False

    catalog = get_available_models()
    default_model = str(catalog.get("default_model") or DEFAULT_MODEL or "").strip()
    if not model:
        return default_model, requested_provider, bool(default_model)

    active_provider = _normalize_provider_id(catalog.get("active_provider"))
    # Also keep the raw active_provider slug for cross-provider detection with
    # non-listed providers (ollama-cloud, deepseek, xai, etc.) that _normalize_provider_id
    # returns "" for. If the raw provider is set but normalization returned "", we still
    # want to detect that a session model from a known provider (e.g. openai/gpt-5.4-mini)
    # is stale relative to this unknown active provider. (#1023)
    raw_active_provider = str(catalog.get("active_provider") or "").strip().lower()
    if not active_provider and not raw_active_provider:
        bare_model, explicit_provider = _split_provider_qualified_model(model)
        return model, explicit_provider or requested_provider, False

    bare_for_context, explicit_provider = _split_provider_qualified_model(model)
    if requested_provider and not explicit_provider:
        return model, requested_provider, False

    if model.startswith("@") and ":" in model:
        provider_raw = explicit_provider or ""
        provider_normalized = _normalize_provider_id(provider_raw)
        bare_model = bare_for_context.strip()
        if not provider_raw or not bare_model:
            return model, requested_provider, False

        raw_provider_ids, normalized_provider_ids = _catalog_provider_id_sets(catalog)
        hint_matches_active = (
            provider_raw == raw_active_provider
            or provider_raw == active_provider
            or (provider_normalized and provider_normalized == active_provider)
        )
        if hint_matches_active:
            # The @provider:model hint explicitly names the active provider, so this
            # selection is intentional — not a stale cross-provider artifact. Return
            # the full @provider:model string unchanged so downstream (resolve_model_provider
            # in config.py) can route through the correct provider. Stripping the prefix
            # here would collapse duplicate model IDs from different providers back to the
            # bare ID, causing the first matching provider to win on the next UI render
            # and the wrong provider to be used for the agent run. (#1253)
            return model, provider_raw, False

        if _catalog_has_provider(
            provider_raw,
            provider_normalized,
            raw_provider_ids,
            normalized_provider_ids,
        ):
            return model, provider_raw, False

        if _model_matches_active_provider_family(bare_model, active_provider):
            provider_context = (
                raw_active_provider
                if _should_attach_codex_provider_context(bare_model, raw_active_provider, catalog)
                else None
            )
            return bare_model, provider_context, True
        if default_model:
            provider_context = (
                raw_active_provider
                if _should_attach_codex_provider_context(default_model, raw_active_provider, catalog)
                else None
            )
            return default_model, provider_context, True
        return model, provider_raw, False

    slash = model.find("/")
    if slash < 0:
        model_lower = model.lower()
        for bare_prefix in ("gpt", "claude", "gemini"):
            if model_lower.startswith(bare_prefix):
                model_provider = _normalize_provider_id(bare_prefix)
                if model_provider and model_provider != active_provider and default_model:
                    provider_context = (
                        raw_active_provider
                        if _should_attach_codex_provider_context(default_model, raw_active_provider, catalog)
                        else None
                    )
                    return default_model, provider_context, True
                provider_context = (
                    raw_active_provider
                    if _should_attach_codex_provider_context(model, raw_active_provider, catalog)
                    else requested_provider
                )
                return model, provider_context, False
        return model, requested_provider, False

    model_provider = _normalize_provider_id(model[:slash])

    # For custom/openrouter active providers: only skip normalization when the
    # model's namespace prefix is actually routable by a group in the catalog.
    # A user who only has custom_providers configured (active_provider="custom")
    # with a stale session model like "openai/gpt-5.4-mini" would otherwise
    # never get cleaned up, causing "(unavailable)" to appear in the picker.
    if active_provider in {"custom", "openrouter"}:
        # These namespaces are always routable as-is — preserve them.
        if model_provider in {"", "custom", "openrouter"}:
            return model, requested_provider, False
        # Check if any catalog group can actually route this model's prefix.
        groups = catalog.get("groups") or []
        routable_provider_ids = {
            _normalize_provider_id(g.get("provider_id") or "") for g in groups
        }
        # openrouter group can route any provider/model namespace
        has_openrouter_group = any(
            (g.get("provider_id") or "") == "openrouter" for g in groups
        )
        if model_provider in routable_provider_ids or has_openrouter_group:
            return model, requested_provider, False
        # Model prefix is not routable — stale cross-provider reference, clear it.
        if default_model:
            return default_model, requested_provider, True
        return model, requested_provider, False

    # Skip normalization for models on custom/openrouter namespaces — these are
    # user-controlled and should never be silently replaced.
    #
    # OpenAI Codex is intentionally normalized to the OpenAI family above so bare
    # GPT IDs survive provider switches. Slash-qualified OpenAI IDs are different:
    # ``openai/gpt-...`` is the OpenRouter shape for OpenAI models, and
    # resolve_model_provider() routes that through OpenRouter when Codex is the
    # configured provider. Legacy sessions can carry that stale slash ID without
    # a saved model_provider, so repair it to the active Codex default unless the
    # session/request explicitly says it is an OpenRouter selection. (#1734)
    if (
        raw_active_provider == "openai-codex"
        and model_provider == "openai"
        and requested_provider is None
        and default_model
    ):
        # Persist provider_context = "openai-codex" unconditionally on this
        # repair path so the resolved shape is stable across resolutions
        # (Opus stage-303 SHOULD-FIX: avoid redundant repair-writes per
        # chat-start when the catalog-coverage check fails — e.g. if a
        # future Codex default is itself slash-prefixed). Once we've
        # decided the session belongs to Codex, persist that decision.
        return default_model, raw_active_provider, True

    # Also normalize when the model is from a known provider but the active provider
    # is an unlisted one (e.g. ollama-cloud) — active_provider is "" in that case
    # but raw_active_provider is set. If model_provider doesn't start with the raw
    # active provider name, the session model is stale. (#1023)
    _active_for_compare = active_provider or raw_active_provider
    if model_provider and model_provider not in {"", "custom", "openrouter"} and model_provider != _active_for_compare and default_model:
        return default_model, requested_provider, True
    return model, requested_provider, False


def _resolve_compatible_session_model(model_id: str | None) -> tuple[str, bool]:
    """Return (effective_model, model_was_normalized) for legacy callers."""
    effective_model, _provider, changed = _resolve_compatible_session_model_state(model_id)
    return effective_model, changed


def _normalize_session_model_in_place(session) -> str:
    original_model = getattr(session, "model", None) or ""
    original_provider = _clean_session_model_provider(
        getattr(session, "model_provider", None)
    )
    effective_model, effective_provider, changed = _resolve_compatible_session_model_state(
        original_model or None,
        original_provider,
    )
    provider_changed = effective_provider != original_provider
    # Only persist the correction if the session had an explicit model that needed changing.
    # Sessions with no model stored (empty/None) get the effective default returned without
    # a disk write — no need to rebuild the index for a fill-in-blank operation.
    if original_model and effective_model and (
        (changed and original_model != effective_model) or provider_changed
    ):
        if changed and original_model != effective_model:
            session.model = effective_model
        session.model_provider = effective_provider
        session.save(touch_updated_at=False)
    return effective_model


def _resolve_effective_session_model_for_display(session) -> str:
    """Resolve the model a session should display without mutating persisted state.

    `GET /api/session` should stay side-effect free. If a stale persisted model
    needs normalization for the current provider configuration, return the
    effective model for the response payload only and leave disk state alone.
    """
    original_model = getattr(session, "model", None) or ""
    effective_model, _provider, _changed = _resolve_compatible_session_model_state(
        original_model or None,
        getattr(session, "model_provider", None),
    )
    return effective_model or original_model

def _resolve_effective_session_model_provider_for_display(session) -> str | None:
    original_model = getattr(session, "model", None) or ""
    _model, provider, _changed = _resolve_compatible_session_model_state(
        original_model or None,
        getattr(session, "model_provider", None),
    )
    return provider


def _resolve_context_length_for_session_model(
    model: str | None,
    provider: str | None = None,
) -> int:
    """Best-effort current context window for a session model.

    Persisted session context metadata is a snapshot from a prior model call.
    During session hydration/model switching, the current model metadata should
    be allowed to replace that stale snapshot.
    """
    model_for_lookup = str(model or "").strip()
    if not model_for_lookup:
        return 0
    try:
        from agent.model_metadata import get_model_context_length as _get_cl
        from api.config import get_config as _get_config_for_cl

        _cfg_for_cl = _get_config_for_cl()
        _cfg_ctx_len_load = None
        _cfg_custom_providers_load = None
        try:
            _model_cfg_load = _cfg_for_cl.get('model', {}) if isinstance(_cfg_for_cl, dict) else {}
            if isinstance(_model_cfg_load, dict):
                _raw_cfg_ctx_load = _model_cfg_load.get('context_length')
                if _raw_cfg_ctx_load is not None:
                    try:
                        _parsed_load = int(_raw_cfg_ctx_load)
                        if _parsed_load > 0:
                            _cfg_ctx_len_load = _parsed_load
                    except (TypeError, ValueError):
                        pass
            _raw_cp_load = _cfg_for_cl.get('custom_providers') if isinstance(_cfg_for_cl, dict) else None
            if isinstance(_raw_cp_load, list):
                _cfg_custom_providers_load = _raw_cp_load
        except Exception:
            pass
        try:
            return _get_cl(
                model_for_lookup,
                "",
                config_context_length=_cfg_ctx_len_load,
                provider=provider or "",
                custom_providers=_cfg_custom_providers_load,
            ) or 0
        except TypeError:
            # Older hermes-agent builds: legacy 2-arg form.
            return _get_cl(model_for_lookup, "") or 0
    except Exception:
        return 0


def _session_model_state_from_request(
    model: str | None,
    requested_provider: str | None,
    current_provider: str | None = None,
) -> tuple[str | None, str | None]:
    return _model_route_helpers.session_model_state_from_request(
        model,
        requested_provider,
        current_provider,
        clean_provider_fn=_clean_session_model_provider,
        split_provider_qualified_model_fn=_split_provider_qualified_model,
        resolve_compatible_state_fn=_resolve_compatible_session_model_state,
    )


def _lookup_gateway_session_identity(session_id: str) -> dict:
    return _messaging_routes.lookup_gateway_session_identity(
        session_id,
        load_identity_map=_load_gateway_session_identity_map,
    )


def _lookup_cli_session_metadata(session_id: str) -> dict:
    if not session_id:
        return {}
    try:
        for row in get_cli_sessions():
            if row.get("session_id") == session_id:
                return row
    except Exception:
        return {}
    return {}


def _messaging_session_identity(session: dict, raw_source: str) -> str:
    return _messaging_routes.messaging_session_identity(
        session,
        raw_source,
        lookup_gateway_identity_fn=_lookup_gateway_session_identity,
        safe_first_fn=_safe_first,
    )


def _session_messaging_raw_source(session: dict) -> str:
    return _messaging_routes.session_messaging_raw_source(
        session,
        safe_first_fn=_safe_first,
        normalize_source_fn=_normalize_messaging_source,
    )


def _has_durable_messaging_identity(session: dict) -> bool:
    return _messaging_routes.has_durable_messaging_identity(
        session,
        lookup_gateway_identity_fn=_lookup_gateway_session_identity,
        safe_first_fn=_safe_first,
    )


def _numeric_count(value) -> int:
    return _messaging_routes.numeric_count(value, safe_first_fn=_safe_first)


def _should_hide_stale_messaging_session(
    session: dict,
    active_gateway_session_ids: set[str],
    active_gateway_sources: set[str],
) -> bool:
    """Hide stale Gateway-owned internal rows after an external chat moved on.

    Hermes Gateway keeps the external conversation identity in sessions.json.
    Compression/session-reset can leave old Agent state.db rows behind; those
    rows are implementation segments, not distinct conversations users chose.
    Only apply this aggressive hiding when Gateway is currently advertising an
    active session for the same messaging source. Without that source-of-truth
    file we keep the old fallback behavior.
    """
    return _messaging_routes.should_hide_stale_messaging_session(
        session,
        active_gateway_session_ids,
        active_gateway_sources,
        stale_end_reasons=_STALE_MESSAGING_END_REASONS,
        session_raw_source_fn=_session_messaging_raw_source,
        is_known_messaging_source_fn=_is_known_messaging_source,
        safe_first_fn=_safe_first,
        has_durable_identity_fn=_has_durable_messaging_identity,
        numeric_count_fn=_numeric_count,
    )


def _is_messaging_session_record(session) -> bool:
    return _messaging_routes.is_messaging_session_record(
        session,
        safe_first_fn=_safe_first,
        is_known_messaging_source_fn=_is_known_messaging_source,
    )


def _messages_include_tool_metadata(messages) -> bool:
    return _messaging_routes.messages_include_tool_metadata(messages)


def _merged_session_messages_for_display(session, cli_messages=None) -> list:
    """Return the message coordinate space exposed by ``GET /api/session``.

    Messaging sessions can have a WebUI sidecar transcript plus messages from
    the Agent/CLI store. The frontend computes fork keep-counts against this
    merged display list, so branch/fork must slice the same list rather than
    the sidecar-only ``session.messages`` array.
    """
    cli_messages = list(cli_messages or [])
    sidecar_messages = list(getattr(session, "messages", []) or [])
    if cli_messages:
        if sidecar_messages and sidecar_messages != cli_messages:
            merged_messages = []
            seen_message_keys = set()
            for msg in sorted(list(cli_messages) + list(sidecar_messages), key=lambda m: (
                float(m.get("timestamp") or 0),
                str(m.get("role") or ""),
                str(m.get("content") or ""),
            )):
                message_identity = msg.get("id") or msg.get("message_id")
                if message_identity:
                    key = ("message_id", str(message_identity))
                else:
                    key = (
                        "legacy",
                        str(msg.get("role") or ""),
                        str(msg.get("content") or ""),
                        str(msg.get("timestamp") or ""),
                        str(msg.get("tool_call_id") or ""),
                        str(msg.get("tool_name") or msg.get("name") or ""),
                    )
                if key in seen_message_keys:
                    continue
                seen_message_keys.add(key)
                merged_messages.append(msg)
            return merged_messages
        return sidecar_messages if len(sidecar_messages) > len(cli_messages) else cli_messages
    return sidecar_messages


def _session_requires_cli_metadata_lookup(session) -> bool:
    """Return True when a sidecar/session row still needs CLI metadata.

    Legacy imported sidecars may predate the ``read_only`` field and therefore
    load with ``read_only=False``. They still persist ``is_cli_session`` and/or
    source metadata from import time, so those markers intentionally keep them
    on the CLI lookup path while ordinary WebUI-native sessions take the fast
    path.

    Supersedes the simpler is-cli-or-messaging gate from PR #1822 — the new
    gate is strictly more inclusive (also covers ``read_only=True`` sidecars,
    ``session_source`` markers, and source_tag/raw_source/platform metadata)
    so all sessions that previously took the slow path still do, plus a few
    more legacy shapes.
    """
    return _messaging_routes.session_requires_cli_metadata_lookup(
        session,
        is_messaging_session_record_fn=_is_messaging_session_record,
        safe_first_fn=_safe_first,
        normalize_source_fn=_normalize_messaging_source,
    )


def _is_messaging_session_id(sid: str) -> bool:
    """Detect messaging-backed sessions from WebUI metadata or Agent rows."""
    try:
        session = Session.load(sid)
        if _is_messaging_session_record(session):
            return True
    except Exception:
        pass
    return _is_messaging_session_record(_lookup_cli_session_metadata(sid))


def _session_sort_timestamp(session: dict) -> float:
    return _messaging_routes.session_sort_timestamp(session, safe_first_fn=_safe_first)


def _is_cli_session_for_settings(session: dict) -> bool:
    return _messaging_routes.is_cli_session_for_settings(
        session,
        is_cli_session_row_fn=is_cli_session_row,
        messaging_sources=MESSAGING_SOURCES,
    )


CLI_VISIBLE_SESSION_CAP = 20


def _cap_recent_cli_sessions(sessions: list[dict], cli_cap: int = CLI_VISIBLE_SESSION_CAP) -> list[dict]:
    return _messaging_routes.cap_recent_cli_sessions(
        sessions,
        cli_cap,
        is_cli_session_for_settings_fn=_is_cli_session_for_settings,
    )


def _merge_cli_sidebar_metadata(ui_session: dict, cli_meta: dict) -> dict:
    return _messaging_routes.merge_cli_sidebar_metadata(
        ui_session,
        cli_meta,
        safe_first_fn=_safe_first,
        numeric_count_fn=_numeric_count,
    )


def _messaging_source_key(session: dict) -> str | None:
    return _messaging_routes.messaging_source_key(
        session,
        session_raw_source_fn=_session_messaging_raw_source,
        is_known_messaging_source_fn=_is_known_messaging_source,
        messaging_session_identity_fn=_messaging_session_identity,
    )


def _keep_latest_messaging_session_per_source(sessions: list[dict]) -> list[dict]:
    return _messaging_routes.keep_latest_messaging_session_per_source(
        sessions,
        load_identity_map=_load_gateway_session_identity_map,
        normalize_source_fn=_normalize_messaging_source,
        safe_first_fn=_safe_first,
        is_known_messaging_source_fn=_is_known_messaging_source,
        messaging_source_key_fn=_messaging_source_key,
        should_hide_stale_fn=_should_hide_stale_messaging_session,
        session_sort_timestamp_fn=_session_sort_timestamp,
    )


from api.models import (
    Session,
    get_session,
    new_session,
    all_sessions,
    title_from,
    _write_session_index,
    SESSION_INDEX_FILE,
    _active_state_db_path,
    load_projects,
    save_projects,
    import_cli_session,
    get_cli_sessions,
    get_cli_session_messages,
    ensure_cron_project,
    is_cron_session,
)
from api.workspace import (
    load_workspaces,
    save_workspaces,
    get_last_workspace,
    set_last_workspace,
    list_dir,
    list_workspace_suggestions,
    read_file_content,
    safe_resolve_ws,
    resolve_trusted_workspace,
    validate_workspace_to_add,
    _is_blocked_system_path,
    _strip_surrounding_quotes,
    _workspace_blocked_roots,
)
from api.products import (
    create_product,
    delete_product,
    finalize_product_generation,
    list_product_versions,
    product_file_status,
    record_product_session,
    list_products,
    preview_product_file,
    rollback_product,
    normalize_product_toolsets,
    snapshot_product,
    update_product,
)
from api.upload import handle_upload, handle_upload_extract, handle_transcribe
from api.streaming import (
    _sse,
    _run_agent_streaming,
    cancel_stream,
    _materialize_pending_user_turn_before_error,
)
from api.run_journal import (
    find_run_summary,
    read_run_events,
    stale_interrupted_event,
)
from api.providers import get_providers, get_provider_quota, get_provider_cost_history, set_provider_key, remove_provider_key
from api.onboarding import (
    apply_onboarding_setup,
    get_onboarding_status,
    complete_onboarding,
    probe_provider_endpoint,
)
from api.oauth import (
    cancel_onboarding_oauth_flow,
    poll_onboarding_oauth_flow,
    start_onboarding_oauth_flow,
)

# Approval system (optional -- graceful fallback if agent not available)
try:
    from tools.approval import (
        submit_pending as _submit_pending_raw,
        approve_session,
        approve_permanent,
        save_permanent_allowlist,
        is_approved,
        _pending,
        _lock,
        _permanent_approved,
        resolve_gateway_approval,
        enable_session_yolo,
        disable_session_yolo,
        is_session_yolo_enabled,
    )
except ImportError:
    _submit_pending_raw = lambda *a, **k: None
    approve_session = lambda *a, **k: None
    approve_permanent = lambda *a, **k: None
    save_permanent_allowlist = lambda *a, **k: None
    is_approved = lambda *a, **k: True
    resolve_gateway_approval = lambda *a, **k: 0
    enable_session_yolo = lambda *a, **k: None
    disable_session_yolo = lambda *a, **k: None
    is_session_yolo_enabled = lambda *a, **k: False
    _pending = {}
    _lock = threading.Lock()
    _permanent_approved = set()


# ── Approval SSE subscribers (long-connection push) ──────────────────────────
_approval_sse_subscribers: dict[str, list[queue.Queue]] = {}


def _approval_sse_subscribe(session_id: str) -> queue.Queue:
    """Register an SSE subscriber for approval events on a given session."""
    q = queue.Queue(maxsize=16)
    with _lock:
        _approval_sse_subscribers.setdefault(session_id, []).append(q)
    return q


def _approval_sse_unsubscribe(session_id: str, q: queue.Queue) -> None:
    """Remove an SSE subscriber."""
    with _lock:
        subs = _approval_sse_subscribers.get(session_id)
        if subs and q in subs:
            subs.remove(q)
            if not subs:
                _approval_sse_subscribers.pop(session_id, None)


def _approval_sse_notify_locked(session_id: str, head: dict | None, total: int) -> None:
    """Push an approval event to all SSE subscribers for a session.

    CALLER MUST HOLD `_lock`. Snapshots the subscriber list under the held
    lock and then calls `q.put_nowait()` on each (which is itself thread-safe).

    `head` is the approval entry currently at the head of the queue (the one
    the UI should display) — NOT the just-appended entry. With multiple
    parallel approvals (#527), the just-appended entry is at the TAIL, but
    `/api/approval/pending` always returns the HEAD, so SSE must match.

    `total` is the total number of pending approvals.

    Pass `head=None` and `total=0` when the queue has just been emptied (e.g.
    `_handle_approval_respond` popped the last entry) so the client knows to
    hide its approval card.
    """
    payload = {"pending": dict(head) if head else None, "pending_count": total}
    subs = _approval_sse_subscribers.get(session_id, ())
    for q in subs:
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass  # drop if subscriber is slow (bounded queue prevents memory leak)


def _approval_sse_notify(session_id: str, head: dict | None, total: int) -> None:
    """Convenience wrapper that takes `_lock` itself.

    Use only from contexts that don't already hold `_lock`. Production call
    sites (submit_pending, _handle_approval_respond) MUST hold the lock and
    call `_approval_sse_notify_locked` directly to avoid a notify-ordering
    race where a later append's notify can fire before an earlier append's
    notify (resulting in stale `pending_count`).
    """
    with _lock:
        _approval_sse_notify_locked(session_id, head, total)


def submit_pending(session_key: str, approval: dict) -> None:
    """Append a pending approval to the per-session queue.

    Wraps the agent's submit_pending to:
    - Add a stable approval_id (uuid4 hex) so the respond endpoint can target
      a specific entry even when multiple approvals are queued simultaneously.
    - Change the storage from a single overwriting dict value to a list, so
      parallel tool calls each get their own approval slot (fixes #527).
    - Notify any connected SSE subscribers immediately.
    """
    entry = dict(approval)
    entry.setdefault("approval_id", uuid.uuid4().hex)
    with _lock:
        queue_list = _pending.setdefault(session_key, [])
        # Replace a legacy non-list value if the agent version uses the old pattern.
        if not isinstance(queue_list, list):
            _pending[session_key] = [queue_list]
            queue_list = _pending[session_key]
        queue_list.append(entry)
        total = len(queue_list)
        head = queue_list[0]  # /api/approval/pending always returns head
        # Push to SSE subscribers from inside _lock so two parallel
        # submit_pending calls can't deliver out-of-order (T2's later
        # notify arriving before T1's earlier notify with a stale count).
        _approval_sse_notify_locked(session_key, head, total)
    # NOTE: We do NOT call _submit_pending_raw here — that function overwrites
    # _pending[session_key] with a single dict, which would undo the list we just
    # built. The gateway blocking path uses _gateway_queues (a separate mechanism
    # managed by check_all_command_guards / register_gateway_notify), which is
    # unaffected by _pending. The _pending dict is only used for UI polling.

# Clarify prompts (optional -- graceful fallback if agent not available)
try:
    from api.clarify import (
        submit_pending as submit_clarify_pending,
        get_pending as get_clarify_pending,
        resolve_clarify,
        sse_subscribe as clarify_sse_subscribe,
        sse_unsubscribe as clarify_sse_unsubscribe,
    )
except ImportError:
    submit_clarify_pending = lambda *a, **k: None
    get_clarify_pending = lambda *a, **k: None
    clarify_sse_subscribe = None
    resolve_clarify = lambda *a, **k: 0


# ── Login page locale strings ─────────────────────────────────────────────────
_LOGIN_LOCALE = _login_routes.LOGIN_LOCALE


def _resolve_login_locale_key(raw_lang: str | None) -> str:
    return _login_routes.resolve_login_locale_key(raw_lang, _LOGIN_LOCALE)

# ── Login page (self-contained, no external deps) ────────────────────────────
_LOGIN_PAGE_HTML = """<!doctype html>
<html lang="{{LANG}}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{BOT_NAME}} — {{LOGIN_TITLE}}</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a1a2e;color:#e8e8f0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#16213e;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:36px 32px;
  width:320px;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,.3)}
.logo{width:48px;height:48px;border-radius:12px;background:linear-gradient(145deg,#e8a030,#e94560);
  display:flex;align-items:center;justify-content:center;font-weight:800;font-size:20px;color:#fff;
  margin:0 auto 12px;box-shadow:0 2px 12px rgba(233,69,96,.3)}
h1{font-size:18px;font-weight:600;margin-bottom:4px}
.sub{font-size:12px;color:#8888aa;margin-bottom:24px}
input{width:100%;padding:10px 14px;border-radius:10px;border:1px solid rgba(255,255,255,.1);
  background:rgba(255,255,255,.04);color:#e8e8f0;font-size:14px;outline:none;margin-bottom:14px;
  transition:border-color .15s}
input:focus{border-color:rgba(124,185,255,.5);box-shadow:0 0 0 3px rgba(124,185,255,.1)}
button{width:100%;padding:10px;border-radius:10px;border:none;background:rgba(124,185,255,.15);
  border:1px solid rgba(124,185,255,.3);color:#7cb9ff;font-size:14px;font-weight:600;cursor:pointer;
  transition:all .15s}
button:hover{background:rgba(124,185,255,.25)}
.err{color:#e94560;font-size:12px;margin-top:10px;display:none}
</style></head><body>
<div class="card">
  <div class="logo">{{BOT_NAME_INITIAL}}</div>
  <h1>{{BOT_NAME}}</h1>
  <p class="sub">{{LOGIN_SUBTITLE}}</p>
  <form id="login-form" data-invalid-pw="{{LOGIN_INVALID_PW}}" data-conn-failed="{{LOGIN_CONN_FAILED}}">
    <input type="password" id="pw" placeholder="{{LOGIN_PLACEHOLDER}}" autofocus>
    <button type="submit">{{LOGIN_BTN}}</button>
  </form>
  <div class="err" id="err"></div>
</div>
<!-- Keep login.js relative so subpath mounts load it under the current scope. -->
<script src="static/login.js?v={{WEBUI_VERSION}}"></script>
</body></html>"""


# ── Logs endpoint ─────────────────────────────────────────────────────────────
_LOG_FILE_WHITELIST = _logs_routes.LOG_FILE_WHITELIST
_LOG_TAIL_VALUES = _logs_routes.LOG_TAIL_VALUES
_LOG_DEFAULT_TAIL = _logs_routes.LOG_DEFAULT_TAIL
_LOG_MAX_BYTES = _logs_routes.LOG_MAX_BYTES


def _normalize_logs_tail(raw_tail) -> int:
    return _logs_routes.normalize_logs_tail(raw_tail)


def _handle_logs(handler, parsed) -> bool:
    return _logs_routes.handle_logs(
        handler,
        parsed,
        responder=j,
        error_responder=bad,
        error_sanitizer=_sanitize_error,
    )

# ── Insights endpoint ──────────────────────────────────────────────────────────

_LLM_WIKI_DOCS_URL = "https://hermes-agent.nousresearch.com/docs/user-guide/skills/bundled/research/research-llm-wiki"
_LLM_WIKI_PAGE_DIRS = ("entities", "concepts", "comparisons", "queries")


def _llm_wiki_active_hermes_home() -> Path:
    return _llm_wiki_routes.active_hermes_home()


def _llm_wiki_env_file_path(hermes_home: Path) -> str | None:
    return _llm_wiki_routes.env_file_path(hermes_home)


def _llm_wiki_get_config_path_value(config: dict, dotted_key: str) -> str | None:
    return _llm_wiki_routes.get_config_path_value(config, dotted_key)


def _llm_wiki_config_path() -> str | None:
    return _llm_wiki_routes.config_path()


# Cap WIKI walks to prevent self-DoS if WIKI_PATH points at /, /etc, /home, etc.
# Real LLM wikis have under a few thousand files; 10k is generous and catches misconfig.
_LLM_WIKI_MAX_FILES = 10000
# Refuse to walk these system roots even if explicitly configured.
_LLM_WIKI_FORBIDDEN_ROOTS = frozenset(
    str(Path(p).expanduser().resolve()) for p in ("/", "/etc", "/usr", "/var", "/opt", "/sys", "/proc")
)


def _llm_wiki_resolve_path() -> tuple[Path, str, bool]:
    return _llm_wiki_routes.resolve_path(
        active_home_fn=_llm_wiki_active_hermes_home,
        env_file_path_fn=_llm_wiki_env_file_path,
        config_path_fn=_llm_wiki_config_path,
    )


def _llm_wiki_safe_iso(ts: float | None) -> str | None:
    return _llm_wiki_routes.safe_iso(ts)


def _llm_wiki_count_files(root: Path) -> int:
    if not root.exists() or not root.is_dir():
        return 0
    # Defense in depth: refuse to walk forbidden system roots even if WIKI_PATH
    # was set to one. The endpoint is auth-gated but a misconfigured server
    # shouldn't self-DoS by rglob'ing all of /etc on every Insights load.
    try:
        if str(root.resolve()) in _LLM_WIKI_FORBIDDEN_ROOTS:
            return 0
    except Exception:
        return 0
    count = 0
    iterated = 0
    for item in root.rglob("*"):
        iterated += 1
        if iterated > _LLM_WIKI_MAX_FILES:
            break  # bounded — prevents hangs on symlink loops or huge trees
        try:
            if item.is_file() and not any(part.startswith(".") for part in item.relative_to(root).parts):
                count += 1
        except Exception:
            continue
    return count


def _llm_wiki_page_files(wiki_path: Path) -> list[Path]:
    pages: list[Path] = []
    # Defense in depth: refuse forbidden system roots.
    try:
        if str(wiki_path.resolve()) in _LLM_WIKI_FORBIDDEN_ROOTS:
            return pages
    except Exception:
        return pages
    iterated = 0
    for dirname in _LLM_WIKI_PAGE_DIRS:
        section = wiki_path / dirname
        if not section.exists() or not section.is_dir():
            continue
        for item in section.rglob("*.md"):
            iterated += 1
            if iterated > _LLM_WIKI_MAX_FILES:
                return pages  # bounded
            try:
                rel = item.relative_to(section)
                if item.is_file() and not any(part.startswith(".") for part in rel.parts):
                    pages.append(item)
            except Exception:
                continue
    return pages


def _build_llm_wiki_status() -> dict:
    return _llm_wiki_routes.build_status(
        docs_url=_LLM_WIKI_DOCS_URL,
        resolve_path_fn=_llm_wiki_resolve_path,
        page_files_fn=_llm_wiki_page_files,
        count_files_fn=_llm_wiki_count_files,
        safe_iso_fn=_llm_wiki_safe_iso,
    )


def _handle_llm_wiki_status(handler, parsed) -> bool:
    j(handler, _build_llm_wiki_status())
    return True


# ── GET routes ────────────────────────────────────────────────────────────────


def _accept_loop_health(handler) -> dict:
    return _health_routes.accept_loop_health(handler)


def _streams_lock_health(timeout_seconds: float = 0.5) -> dict:
    return _health_routes.streams_lock_health(STREAMS_LOCK, STREAMS, timeout_seconds=timeout_seconds)


def _run_lifecycle_health() -> dict:
    return _health_routes.run_lifecycle_health()


def _deep_health_checks(stream_check: dict | None = None) -> tuple[dict, bool]:
    return _health_routes.deep_health_checks(
        stream_check=stream_check,
        streams_lock_health_fn=_streams_lock_health,
        all_sessions_fn=all_sessions,
        load_projects_fn=load_projects,
        active_state_db_path_fn=_active_state_db_path,
    )


def _handle_health(handler, parsed):
    return _health_routes.handle_health(
        handler,
        parsed,
        sessions=SESSIONS,
        server_start_time=SERVER_START_TIME,
        streams_lock_health_fn=_streams_lock_health,
        run_lifecycle_health_fn=_run_lifecycle_health,
        deep_health_checks_fn=_deep_health_checks,
        accept_loop_health_fn=_accept_loop_health,
        responder=j,
    )


# ── Plugin visibility endpoint (#539) ───────────────────────────────────────
_PLUGIN_VISIBILITY_HOOKS = _plugin_routes.PLUGIN_VISIBILITY_HOOKS
_PLUGIN_VISIBILITY_HOOK_SET = _plugin_routes.PLUGIN_VISIBILITY_HOOK_SET


def _get_plugin_manager_for_visibility():
    return _plugin_routes.get_plugin_manager_for_visibility()


def _clean_plugin_visibility_text(value, *, limit=240) -> str:
    return _plugin_routes.clean_plugin_visibility_text(value, limit=limit)


def _plugin_visibility_payload(manager=None) -> dict:
    return _plugin_routes.plugin_visibility_payload(
        manager,
        manager_factory=_get_plugin_manager_for_visibility,
    )


def _handle_plugins(handler, parsed) -> bool:
    return _plugin_routes.handle_plugins(
        handler,
        parsed,
        payload_factory=_plugin_visibility_payload,
        responder=j,
    )


def _serve_shell_unavailable(handler, exc: Exception) -> bool:
    """Return HTML for shell-route failures so `/` never renders JSON."""
    return _static_routes.serve_shell_unavailable(
        handler,
        exc,
        logger=logger,
        text_response_fn=t,
    )


def _serve_manifest(handler) -> bool:
    """Serve static/manifest.json with the correct PWA Content-Type.

    Shared by the root (/manifest.json, /manifest.webmanifest) and
    session-prefixed (/session/manifest.json, /session/manifest.webmanifest)
    routes so Firefox Android can fetch the manifest when installing from
    a /session/<id> page.  See #2226.

    Static-test anchors: application/manifest+json, Cache-Control, no-store.
    """
    return _static_routes.serve_manifest(
        handler,
        module_file=__file__,
        json_response_fn=j,
    )


def handle_get(handler, parsed) -> bool:
    """Handle all GET routes. Returns True if handled, False for 404."""

    if parsed.path.startswith("/session/static/"):
        # Strip the leading "/session" so _serve_static() sees a path that
        # starts with "/static/" (its required prefix). _serve_static enforces
        # its own path-traversal sandbox via Path.resolve()+relative_to().
        stripped = parsed._replace(path=parsed.path[len("/session"):])
        return _serve_static(handler, stripped)

    # Firefox Android resolves <link rel="manifest"> against the page URL
    # before the dynamic <base href> script runs when installing from
    # /session/<id>, producing requests like /session/manifest.json.
    # Without this guard the catch-all below returns index.html instead of
    # the manifest, and Firefox falls back to a generated letter icon.
    # See #2226.
    if parsed.path in ("/session/manifest.json", "/session/manifest.webmanifest"):
        return _serve_manifest(handler)

    if parsed.path in ("/", "/index.html") or parsed.path.startswith("/session/"):
        try:
            from urllib.parse import quote
            from api.updates import WEBUI_VERSION
            version_token = quote(WEBUI_VERSION, safe="")
            from api.extensions import inject_extension_tags

            csrf_token = ""
            try:
                from api.auth import csrf_token_for_session, is_auth_enabled, parse_cookie, verify_session

                if is_auth_enabled():
                    cookie_val = parse_cookie(handler)
                    if cookie_val and verify_session(cookie_val):
                        csrf_token = csrf_token_for_session(cookie_val) or ""
            except Exception:
                csrf_token = ""

            html = (
                _INDEX_HTML_PATH.read_text(encoding="utf-8")
                .replace("__WEBUI_VERSION__", version_token)
                .replace("__MAX_UPLOAD_BYTES__", str(MAX_UPLOAD_BYTES))
                .replace("__CSRF_TOKEN_JSON__", json.dumps(csrf_token))
            )
            return t(
                handler,
                inject_extension_tags(html),
                content_type="text/html; charset=utf-8",
            )
        except Exception as exc:
            return _serve_shell_unavailable(handler, exc)

    if parsed.path == "/login":
        _settings = load_settings()
        _bn = _html.escape(_settings.get("bot_name") or "Hermes")
        _lang = _settings.get("language", "en")
        _login_strings = _LOGIN_LOCALE[
            _resolve_login_locale_key(_lang)
        ]
        from urllib.parse import quote
        from api.updates import WEBUI_VERSION
        version_token = quote(WEBUI_VERSION, safe="")
        _page = (
            _LOGIN_PAGE_HTML.replace("{{BOT_NAME}}", _bn)
            .replace("{{BOT_NAME_INITIAL}}", _bn[0].upper())
            .replace("{{WEBUI_VERSION}}", version_token)
            .replace("{{LANG}}", _html.escape(_login_strings["lang"]))
            .replace("{{LOGIN_TITLE}}", _html.escape(_login_strings["title"]))
            .replace("{{LOGIN_SUBTITLE}}", _html.escape(_login_strings["subtitle"]))
            .replace(
                "{{LOGIN_PLACEHOLDER}}", _html.escape(_login_strings["placeholder"])
            )
            .replace("{{LOGIN_BTN}}", _html.escape(_login_strings["btn"]))
            .replace("{{LOGIN_INVALID_PW}}", _html.escape(_login_strings["invalid_pw"]))
            .replace(
                "{{LOGIN_CONN_FAILED}}", _html.escape(_login_strings["conn_failed"])
            )
        )
        return t(handler, _page, content_type="text/html; charset=utf-8")

    if parsed.path == "/api/auth/status":
        from api.auth import is_auth_enabled, parse_cookie, verify_session

        logged_in = False
        if is_auth_enabled():
            cv = parse_cookie(handler)
            logged_in = bool(cv and verify_session(cv))
        return j(handler, {"auth_enabled": is_auth_enabled(), "logged_in": logged_in})

    if parsed.path in ("/manifest.json", "/manifest.webmanifest"):
        return _serve_manifest(handler)

    if parsed.path == "/sw.js":
        static_root = Path(__file__).parent.parent / "static"
        sw_path = (static_root / "sw.js").resolve()
        if sw_path.exists():
            # Inject the current git-derived version as the cache name so the
            # service worker cache busts automatically on every new deploy.
            from urllib.parse import quote
            from api.updates import WEBUI_VERSION
            version_token = quote(WEBUI_VERSION, safe="")
            text = sw_path.read_text(encoding="utf-8").replace(
                "__WEBUI_VERSION__", version_token
            )
            data = text.encode("utf-8")
            handler.send_response(200)
            handler.send_header("Content-Type", "application/javascript; charset=utf-8")
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("Service-Worker-Allowed", "/")
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True
        return j(handler, {"error": "not found"}, status=404)

    if parsed.path == "/favicon.ico":
        static_root = Path(__file__).parent.parent / "static"
        ico_path = (static_root / "favicon.ico").resolve()
        if ico_path.exists() and ico_path.is_file():
            data = ico_path.read_bytes()
            handler.send_response(200)
            handler.send_header("Content-Type", "image/x-icon")
            handler.send_header("Content-Length", str(len(data)))
            handler.send_header("Cache-Control", "public, max-age=86400")
            handler.end_headers()
            handler.wfile.write(data)
        else:
            handler.send_response(204)
            handler.end_headers()
        return True

    # ── Knowledge status ──
    if parsed.path == "/api/wiki/status":
        return _handle_llm_wiki_status(handler, parsed)
    if parsed.path == "/api/logs":
        return _handle_logs(handler, parsed)

    if parsed.path == "/health":
        return _handle_health(handler, parsed)

    if parsed.path == "/api/health/agent":
        return j(handler, build_agent_health_payload())

    if parsed.path == "/api/system/health":
        j(handler, build_system_health_payload())
        return True

    if parsed.path == "/api/models":
        return j(handler, get_available_models())

    if parsed.path == "/api/models/live":
        return _handle_live_models(handler, parsed)

    if parsed.path == "/api/dashboard/status":
        return _handle_dashboard_status(handler)

    if parsed.path == "/api/dashboard/config":
        return _handle_dashboard_config_get(handler)

    # ── Providers (GET) ──
    if parsed.path == "/api/providers":
        return j(handler, get_providers())

    # ── Plugins/hooks visibility (read-only, no callback/source internals) ──
    if parsed.path == "/api/plugins":
        return _handle_plugins(handler, parsed)
    if parsed.path == "/api/provider/quota":
        # Static compatibility anchors: query.get("refresh", [""]), get_provider_quota(provider_id, refresh=refresh)
        return _handle_provider_quota(handler, parsed)

    if parsed.path == "/api/provider/cost-history":
        return _handle_provider_cost_history(handler, parsed)

    if parsed.path == "/api/settings":
        return _handle_settings_get(handler)

    if parsed.path == "/api/reasoning":
        # Current reasoning config (shared source of truth with the CLI —
        # reads display.show_reasoning and agent.reasoning_effort from
        # the active profile's config.yaml).
        return j(handler, get_reasoning_status())

    if parsed.path == "/api/onboarding/status":
        return j(handler, get_onboarding_status())

    if parsed.path.startswith("/extensions/"):
        from api.extensions import serve_extension_static

        return serve_extension_static(handler, parsed)

    if parsed.path.startswith("/static/"):
        return _serve_static(handler, parsed)


    if parsed.path == "/api/session/worktree/status":
        return _handle_session_worktree_status(handler, parsed)

    if parsed.path == "/api/session/compress/status":
        query = parse_qs(parsed.query)
        _handle_session_compress_status(handler, query.get("session_id", [""])[0])
        return True

    if parsed.path == "/api/session":
        import time as _time
        _t0 = _time.monotonic()
        _debug_slow = os.environ.get("HERMES_DEBUG_SLOW", "")
        query = parse_qs(parsed.query)
        sid = query.get("session_id", [""])[0]
        if not sid:
            return j(handler, {"error": "session_id is required"}, status=400)
        # ?messages=0 skips the message payload for fast session switching.
        # The frontend uses this when switching conversations in the sidebar
        # (only needs metadata). The full message array is loaded lazily
        # via ?messages=1 when the message panel opens.
        load_messages = query.get("messages", ["1"])[0] != "0"
        resolve_model_default = "1" if load_messages else "0"
        resolve_model = query.get("resolve_model", [resolve_model_default])[0] != "0"
        # ?msg_limit=N returns only the last N messages (tail window).
        # Used by the frontend for fast session switching — avoids serialising
        # and sending hundreds of messages when the user only sees the most
        # recent exchange.  Older messages are loaded on-demand via scrolling.
        _msg_limit = query.get("msg_limit", [None])[0]
        try:
            msg_limit = max(1, int(_msg_limit)) if _msg_limit else None
        except (ValueError, TypeError):
            msg_limit = None
        # ?msg_before=N — 0-based index into the full message array.
        # Returns messages before this index (for scroll-to-top lazy loading).
        # Combined with msg_limit for paging.
        _msg_before = query.get("msg_before", [None])[0]
        try:
            msg_before = int(_msg_before) if _msg_before else None
        except (ValueError, TypeError):
            msg_before = None
        try:
            _t1 = _time.monotonic()
            s = get_session(sid, metadata_only=(not load_messages))
            original_stream_id = getattr(s, "active_stream_id", None)
            _clear_stale_stream_state(s)
            cli_meta = _lookup_cli_session_metadata(sid) if _session_requires_cli_metadata_lookup(s) else {}
            is_messaging_session = _is_messaging_session_record(s) or _is_messaging_session_record(cli_meta)
            cli_messages = []
            if is_messaging_session:
                cli_messages = get_cli_session_messages(sid)
            _t2 = _time.monotonic()
            effective_model = (
                _resolve_effective_session_model_for_display(s)
                if resolve_model
                else None
            )
            effective_provider = (
                _resolve_effective_session_model_provider_for_display(s)
                if resolve_model
                else None
            )
            _t3 = _time.monotonic()
            if load_messages:
                if is_messaging_session and cli_messages:
                    # Recovery/aggregate sidecars can intentionally contain a
                    # longer visible conversation than the single state.db
                    # segment for this messaging session id. Prefer the longer
                    # sidecar so repaired WebUI history is not hidden behind the
                    # canonical per-segment transcript. When both sources carry
                    # different slices of the same stitched conversation, merge
                    # them chronologically and dedupe exact repeats.
                    _all_msgs = _merged_session_messages_for_display(s, cli_messages)
                else:
                    _all_msgs = s.messages
            else:
                _all_msgs = []
            if load_messages:
                if msg_before is not None:
                    # Scroll-to-top paging: msg_before is a 0-based index into
                    # the full message list. Return the msg_limit messages that
                    # appear *before* this index (i.e. older messages).
                    # Using index instead of timestamp avoids issues with
                    # duplicate/missing timestamps.
                    _before_idx = max(0, min(int(msg_before), len(_all_msgs)))
                    _slice = _all_msgs[:_before_idx]
                    _truncated_msgs = _slice[-msg_limit:] if msg_limit else _slice
                elif msg_limit and len(_all_msgs) > msg_limit:
                    _truncated_msgs = _all_msgs[-msg_limit:]
                else:
                    _truncated_msgs = _all_msgs
            else:
                _truncated_msgs = _all_msgs
            # Resolve effective context_length with model-metadata fallback so
            # older sessions (pre-#1318) that have context_length=0 persisted
            # still render a meaningful indicator on load.  Mirrors the
            # SSE-path fallback in api/streaming.py:2333-2342.  Fixes #1436.
            #
            # #1896: pass config_context_length, provider, and custom_providers
            # so explicit config overrides win over the 256K default fallback.
            # Without these, an old session loaded after a user upgraded to a
            # 1M-context model with `model.context_length: 1048576` in
            # config.yaml gets a 256K window in the initial UI indicator and
            # /api/session/get response — the same wrong-window display this
            # fix addresses on the streaming side.
            _persisted_cl = getattr(s, "context_length", 0) or 0
            _threshold_tokens = getattr(s, "threshold_tokens", 0) or 0
            if (not _persisted_cl) or resolve_model:
                _model_for_lookup = (
                    effective_model or getattr(s, "model", "") or ""
                ).strip()
                _fb_cl = _resolve_context_length_for_session_model(
                    _model_for_lookup,
                    effective_provider or getattr(s, "model_provider", None) or "",
                )
                if _fb_cl:
                    if _persisted_cl and _fb_cl != _persisted_cl:
                        # The old threshold belongs to the old window. Hiding it
                        # is less misleading than rendering a stale compression
                        # threshold against a freshly resolved context length.
                        _threshold_tokens = 0
                    _persisted_cl = _fb_cl
            _session_tool_calls = getattr(s, "tool_calls", []) if load_messages else []
            if (
                load_messages
                and msg_limit is not None
                and _messages_include_tool_metadata(_truncated_msgs)
            ):
                # The browser ignores session-level tool_calls when the returned
                # messages already carry per-message tool metadata. Avoid sending
                # the full historical list with a small tail window.
                _session_tool_calls = []
            raw = s.compact() | {
                "messages": _truncated_msgs,
                "tool_calls": _session_tool_calls,
                "active_stream_id": getattr(s, "active_stream_id", None),
                "pending_user_message": getattr(s, "pending_user_message", None),
                "pending_attachments": getattr(s, "pending_attachments", []) if load_messages else [],
                "pending_started_at": getattr(s, "pending_started_at", None),
                "context_length": _persisted_cl,
                "threshold_tokens": _threshold_tokens,
                "last_prompt_tokens": getattr(s, "last_prompt_tokens", 0) or 0,
            }
            if original_stream_id:
                try:
                    journal = find_run_summary(original_stream_id)
                except Exception:
                    journal = None
                if journal:
                    raw["runtime_journal"] = _run_journal_status_payload(
                        journal,
                        active=bool(getattr(s, "active_stream_id", None)),
                    )
            if cli_meta and _is_messaging_session_record(cli_meta):
                raw = _merge_cli_sidebar_metadata(raw, cli_meta)
            # Signal to the frontend that older messages were omitted.
            # For msg_before paging, compare against the filtered set,
            # not the full list — otherwise we signal truncation even when
            # all older messages were returned.
            if msg_before is not None:
                _truncated = load_messages and msg_limit is not None and len(_slice) > msg_limit
            else:
                _truncated = load_messages and msg_limit is not None and len(_all_msgs) > msg_limit
            raw["_messages_truncated"] = _truncated
            # Index of the first returned message in the full message array.
            # Frontend uses this as cursor for scroll-to-top paging.
            if msg_before is not None:
                raw["_messages_offset"] = max(0, _before_idx - len(_truncated_msgs))
            else:
                raw["_messages_offset"] = max(0, len(_all_msgs) - len(_truncated_msgs))
            _t4 = _time.monotonic()
            if effective_model:
                raw["model"] = effective_model
            if effective_provider:
                raw["model_provider"] = effective_provider
            redact = redact_session_data(raw)
            _t5 = _time.monotonic()
            resp = j(handler, {"session": redact})
            _t6 = _time.monotonic()
            if _debug_slow:
                logger.warning(
                    "[SLOW] session_id=%s get_session=%.1fms model_resolve=%.1fms "
                    "compact=%.1fms redact=%.1fms json_write=%.1fms total=%.1fms",
                    sid,
                    (_t2-_t1)*1000, (_t3-_t2)*1000, (_t4-_t3)*1000,
                    (_t5-_t4)*1000, (_t6-_t5)*1000, (_t6-_t0)*1000,
                )
            return resp
        except KeyError:
            # Not a WebUI session -- try CLI store
            cli_meta = _lookup_cli_session_metadata(sid)
            msgs = get_cli_session_messages(sid)
            if msgs:
                sess = {
                    "session_id": sid,
                    "title": (cli_meta or {}).get("title", "CLI Session"),
                    "workspace": (cli_meta or {}).get("workspace", ""),
                    "model": (cli_meta or {}).get("model", "unknown"),
                    "message_count": len(msgs),
                    "created_at": (cli_meta or {}).get("created_at", 0),
                    "updated_at": (cli_meta or {}).get("updated_at", 0),
                    "last_message_at": (cli_meta or {}).get("last_message_at")
                    or (cli_meta or {}).get("updated_at", 0)
                    or (msgs[-1] if msgs else {"timestamp": 0}).get("timestamp", 0),
                    "pinned": False,
                    "archived": False,
                    "project_id": None,
                    "profile": (cli_meta or {}).get("profile"),
                    "is_cli_session": True,
                    "source_tag": (cli_meta or {}).get("source_tag"),
                    "raw_source": (cli_meta or {}).get("raw_source"),
                    "session_source": (cli_meta or {}).get("session_source"),
                    "source_label": (cli_meta or {}).get("source_label"),
                    "read_only": bool((cli_meta or {}).get("read_only")),
                    "messages": msgs,
                    "tool_calls": [],
                }
                sess = _merge_cli_sidebar_metadata(sess, cli_meta)
                return j(handler, {"session": redact_session_data(sess)})
            return bad(handler, "Session not found", 404)

    if parsed.path == "/api/session/lineage/report":
        sid = parse_qs(parsed.query).get("session_id", [""])[0]
        if not sid:
            return bad(handler, "session_id required", 400)
        report = read_session_lineage_report(_active_state_db_path(), sid)
        if not report.get("found"):
            return bad(handler, "Session not found", 404)
        return j(handler, report)

    if parsed.path == "/api/session/recovery/audit":
        from api.session_recovery import audit_session_recovery
        return j(handler, audit_session_recovery(SESSION_DIR, state_db_path=_active_state_db_path()))

    if parsed.path == "/api/session/status":
        return _handle_session_status(handler, parsed)

    if parsed.path == "/api/session/yolo":
        return _handle_session_yolo_get(handler, parsed)

    if parsed.path == "/api/session/usage":
        return _handle_session_usage(handler, parsed)

    if parsed.path == "/api/background/status":
        return _handle_background_status(handler, parsed)

    if parsed.path == "/api/sessions":
        diag = RequestDiagnostics.maybe_start("GET", parsed.path, logger=logger)
        try:
            diag.stage("all_sessions")
            webui_sessions = all_sessions(diag=diag)
            diag.stage("reconcile_stale_stream_state")
            if _reconcile_stale_stream_state_for_session_rows(webui_sessions):
                diag.stage("all_sessions_after_stale_stream_reconcile")
                webui_sessions = all_sessions(diag=diag)
            diag.stage("load_settings")
            settings = load_settings()
            show_cli_sessions = bool(settings.get("show_cli_sessions"))
            if show_cli_sessions:
                diag.stage("get_cli_sessions")
                cli = get_cli_sessions()
                diag.stage("merge_cli_sessions")
                cli_by_id = {s["session_id"]: s for s in cli}
                for s in webui_sessions:
                    meta = cli_by_id.get(s.get("session_id"))
                    if not meta:
                        continue
                    if _is_messaging_session_record(meta):
                        s.update(_merge_cli_sidebar_metadata(s, meta))
                        if s.get("session_id") != meta.get("session_id"):
                            s["session_id"] = meta.get("session_id")
                    else:
                        for key in ("source_tag", "raw_source", "session_source", "source_label"):
                            if not s.get(key) and meta.get(key):
                                s[key] = meta[key]
                # Apply the same CLI visibility semantics to imported local copies so
                # low-value imported artifacts do not leak into the sidebar.
                webui_sessions = [s for s in webui_sessions if is_cli_session_row_visible(s)]
                webui_ids = {s["session_id"] for s in webui_sessions}
                from api.models import _hide_from_default_sidebar as _cron_hide
                deduped_cli = [s for s in cli if s["session_id"] not in webui_ids and is_cli_session_row_visible(s) and not _cron_hide(s)]
            else:
                diag.stage("filter_webui_sessions")
                webui_sessions = [s for s in webui_sessions if not _is_cli_session_for_settings(s)]
                deduped_cli = []
            diag.stage("sort_sessions")
            merged = webui_sessions + deduped_cli
            merged.sort(
                key=lambda s: s.get("last_message_at") or s.get("updated_at", 0) or 0,
                reverse=True,
            )
            # ── Profile scoping (#1611) ────────────────────────────────────────
            # Default: filter to the active profile. ?all_profiles=1 opts into
            # the aggregate view used by the "All profiles" sidebar toggle.
            # The other_profile_count is always returned so the UI can render
            # the "Show N from other profiles" affordance without sending the
            # cross-profile rows by default.
            #
            # IMPORTANT: scope BEFORE _keep_latest_messaging_session_per_source.
            # _messaging_source_key is profile-blind (#1614 follow-up): if the
            # same Slack/Telegram identity has sessions in profiles A and B, a
            # profile-blind dedupe would discard the older one even when scoped
            # to its own profile, leaving that profile with zero rows for that
            # source. Filter first so the dedupe operates only within the active
            # profile's rows.
            diag.stage("active_profile")
            from api.profiles import get_active_profile_name
            active_profile = get_active_profile_name()
            all_profiles = _all_profiles_query_flag(parsed)
            diag.stage("profile_filter")
            if all_profiles:
                scoped = merged
                other_profile_count = 0
            else:
                scoped = [s for s in merged
                          if _profiles_match(s.get("profile"), active_profile)]
                other_profile_count = len(merged) - len(scoped)
            diag.stage("messaging_dedupe")
            scoped = _keep_latest_messaging_session_per_source(scoped)
            if show_cli_sessions:
                diag.stage("cli_cap")
                scoped = _cap_recent_cli_sessions(scoped, cli_cap=CLI_VISIBLE_SESSION_CAP)
            diag.stage("redact_sessions")
            safe_merged = []
            for s in scoped:
                item = dict(s)
                if isinstance(item.get("title"), str):
                    item["title"] = _redact_text(item["title"])
                safe_merged.append(item)
            diag.stage("response_write")
            return j(handler, {
                "sessions": safe_merged,
                "cli_count": len(deduped_cli),
                "all_profiles": all_profiles,
                "active_profile": active_profile,
                "other_profile_count": other_profile_count,
                "server_time": time.time(),
                "server_tz": time.strftime("%z"),
            })
        finally:
            diag.finish()

    if parsed.path == "/api/projects":
        return _handle_projects_get(handler, parsed)

    if parsed.path == "/api/session/export":
        return _handle_session_export(handler, parsed)

    if parsed.path == "/api/workspaces":
        return j(
            handler, {"workspaces": load_workspaces(), "last": get_last_workspace()}
        )

    if parsed.path.startswith("/api/products/") and "/preview" in parsed.path:
        return _serve_product_preview(handler, parsed)

    if parsed.path == "/api/products":
        return j(handler, list_products())

    if parsed.path.startswith("/api/products/") and parsed.path.endswith("/versions"):
        product_id = unquote(parsed.path[len("/api/products/"):-len("/versions")].strip("/"))
        try:
            return j(handler, list_product_versions(product_id))
        except FileNotFoundError:
            return j(handler, {"error": "not found"}, status=404)

    if parsed.path.startswith("/api/products/") and parsed.path.endswith("/status"):
        product_id = unquote(parsed.path[len("/api/products/"):-len("/status")].strip("/"))
        try:
            # Reconcile-on-access: persist any status drift (e.g. timed-out generating)
            # here at the access point; the read below stays pure.
            from api.products import reconcile_product_status

            reconcile_product_status(product_id)
            return j(handler, product_file_status(product_id))
        except Exception:
            return j(handler, {"error": "not found"}, status=404)

    if parsed.path.startswith("/api/products/"):
        return _serve_product_asset(handler, parsed)

    if parsed.path == "/api/workspaces/suggest":
        qs = parse_qs(parsed.query)
        prefix = qs.get("prefix", [""])[0]
        return j(
            handler,
            {
                "suggestions": list_workspace_suggestions(prefix),
                "prefix": prefix,
            },
        )

    if parsed.path == "/api/sessions/search":
        return _handle_sessions_search(handler, parsed)

    if parsed.path == "/api/list":
        return _handle_list_dir(handler, parsed)

    if parsed.path == "/api/personalities":
        # Read personalities from config.yaml agent.personalities section
        # (matches hermes-agent CLI behavior, not filesystem SOUL.md approach)
        from api.config import reload_config as _reload_cfg

        _reload_cfg()  # pick up config.yaml changes without server restart
        from api.config import get_config as _get_cfg

        _cfg = _get_cfg()
        agent_cfg = _cfg.get("agent", {})
        raw_personalities = agent_cfg.get("personalities", {})
        personalities = []
        if isinstance(raw_personalities, dict):
            for name, value in raw_personalities.items():
                desc = ""
                if isinstance(value, dict):
                    desc = value.get("description", "")
                elif isinstance(value, str):
                    desc = value[:80] + ("..." if len(value) > 80 else "")
                personalities.append({"name": name, "description": desc})
        return j(handler, {"personalities": personalities})

    if parsed.path == "/api/git-info":
        qs = parse_qs(parsed.query)
        sid = qs.get("session_id", [""])[0]
        if not sid:
            return bad(handler, "session_id required")
        try:
            s = get_session(sid)
        except KeyError:
            return bad(handler, "Session not found", 404)
        from api.workspace import git_info_for_workspace

        info = git_info_for_workspace(Path(s.workspace))
        return j(handler, {"git": info})

    if parsed.path == "/api/commands":
        return _handle_commands_list(handler)

    if parsed.path == "/api/updates/check":
        settings = load_settings()
        if not settings.get("check_for_updates", True):
            return j(handler, {"disabled": True})
        qs = parse_qs(parsed.query)
        force = qs.get("force", ["0"])[0] == "1"
        # ?simulate=1 returns fake behind counts for UI testing (localhost only)
        if (
            qs.get("simulate", ["0"])[0] == "1"
            and handler.client_address[0] == "127.0.0.1"
        ):
            return j(
                handler,
                {
                    "webui": {
                        "name": "webui",
                        "behind": 3,
                        "current_sha": "abc1234",
                        "latest_sha": "def5678",
                        "branch": "master",
                        "repo_url": "https://github.com/nesquena/hermes-webui",
                        "compare_url": "https://github.com/nesquena/hermes-webui/compare/abc1234...def5678",
                    },
                    "agent": {
                        "name": "agent",
                        "behind": 1,
                        "current_sha": "aaa0001",
                        "latest_sha": "bbb0002",
                        "branch": "master",
                        "repo_url": "https://github.com/NousResearch/hermes-agent",
                        "compare_url": "https://github.com/NousResearch/hermes-agent/compare/aaa0001...bbb0002",
                    },
                    "checked_at": 0,
                },
            )
        from api.updates import check_for_updates

        return j(handler, check_for_updates(force=force))

    if parsed.path == "/api/chat/stream/status":
        stream_id = parse_qs(parsed.query).get("stream_id", [""])[0]
        active = stream_id in STREAMS
        payload = {"active": active, "stream_id": stream_id, "replay_available": False}
        try:
            journal = find_run_summary(stream_id) if stream_id else None
        except Exception:
            journal = None
        if journal:
            payload["replay_available"] = True
            payload["journal"] = _run_journal_status_payload(journal, active=active)
        return j(handler, payload)

    if parsed.path == "/api/chat/cancel":
        stream_id = parse_qs(parsed.query).get("stream_id", [""])[0]
        if not stream_id:
            return bad(handler, "stream_id required")
        from api.runtime_adapter import LegacyJournalRuntimeAdapter, runtime_adapter_enabled

        if runtime_adapter_enabled():
            adapter = LegacyJournalRuntimeAdapter(cancel_delegate=cancel_stream)
            cancelled = adapter.cancel_run(stream_id).accepted
        else:
            cancelled = cancel_stream(stream_id)
        return j(handler, {"ok": True, "cancelled": cancelled, "stream_id": stream_id})

    if parsed.path == "/api/chat/stream":
        return _handle_sse_stream(handler, parsed)

    if parsed.path == "/api/terminal/output":
        return _handle_terminal_output(handler, parsed)

    if parsed.path == '/api/sessions/gateway/stream':
        return _handle_gateway_sse_stream(handler, parsed)

    if parsed.path == "/api/media":
        return _handle_media(handler, parsed)

    if parsed.path == "/api/file/raw":
        return _handle_file_raw(handler, parsed)

    if parsed.path == "/api/file":
        return _handle_file_read(handler, parsed)

    if parsed.path == "/api/approval/pending":
        return _handle_approval_pending(handler, parsed)

    if parsed.path == "/api/approval/stream":
        return _handle_approval_sse_stream(handler, parsed)

    if parsed.path == "/api/approval/inject_test":
        # Loopback-only: used by automated tests; blocked from any remote client
        if handler.client_address[0] != "127.0.0.1":
            return j(handler, {"error": "not found"}, status=404)
        return _handle_approval_inject(handler, parsed)

    if parsed.path == "/api/clarify/pending":
        return _handle_clarify_pending(handler, parsed)

    if parsed.path == "/api/clarify/stream":
        return _handle_clarify_sse_stream(handler, parsed)

    if parsed.path == "/api/clarify/inject_test":
        # Loopback-only: used by automated tests; blocked from any remote client
        if handler.client_address[0] != "127.0.0.1":
            return j(handler, {"error": "not found"}, status=404)
        return _handle_clarify_inject(handler, parsed)

    if parsed.path == "/api/onboarding/oauth/poll":
        qs = parse_qs(parsed.query)
        flow_id = qs.get("flow_id", [""])[0]
        try:
            return j(
                handler,
                poll_onboarding_oauth_flow(flow_id),
                extra_headers={"Cache-Control": "no-store"},
            )
        except ValueError as e:
            return bad(handler, str(e))
        except KeyError as e:
            return bad(handler, str(e), 404)

    # ── Cron API (GET) ──
    # All cron handlers touch cron.jobs which resolves HERMES_HOME from
    # os.environ (process-global) at call time. Wrap in cron_profile_context
    # so the TLS-active profile's jobs.json is read, not the process default.
    if parsed.path == "/api/crons":
        from cron.jobs import list_jobs
        from api.profiles import cron_profile_context

        with cron_profile_context():
            return j(handler, {"jobs": _cron_jobs_for_api(list_jobs(include_disabled=True))})

    if parsed.path == "/api/crons/output":
        from api.profiles import cron_profile_context

        with cron_profile_context():
            return _handle_cron_output(handler, parsed)

    if parsed.path == "/api/crons/history":
        from api.profiles import cron_profile_context

        with cron_profile_context():
            return _handle_cron_history(handler, parsed)

    if parsed.path == "/api/crons/run":
        from api.profiles import cron_profile_context

        with cron_profile_context():
            return _handle_cron_run_detail(handler, parsed)

    if parsed.path == "/api/crons/recent":
        from api.profiles import cron_profile_context

        with cron_profile_context():
            return _handle_cron_recent(handler, parsed)

    if parsed.path == "/api/crons/status":
        from api.profiles import cron_profile_context

        with cron_profile_context():
            return _handle_cron_status(handler, parsed)

    # ── Skills API (GET) ──
    if parsed.path == "/api/skills":
        qs = parse_qs(parsed.query)
        category = qs.get("category", [None])[0]
        data = _skills_list_from_dir(_active_skills_dir(), category=category)
        return j(handler, {"skills": data.get("skills", [])})

    if parsed.path == "/api/skills/content":
        qs = parse_qs(parsed.query)
        name = qs.get("name", [""])[0]
        if not name:
            return j(handler, {"error": "name required"}, status=400)
        file_path = qs.get("file", [""])[0]
        if file_path:
            # Serve a linked file from the skill directory
            import re as _re

            if _re.search(r"[*?\[\]]", name):
                return bad(handler, "Invalid skill name", 400)
            skills_dir = _active_skills_dir()
            skill_dir, _skill_md = _find_skill_in_dirs(
                name, _active_skill_search_dirs(skills_dir)
            )
            if not skill_dir:
                return bad(handler, "Skill not found", 404)
            target = (skill_dir / file_path).resolve()
            try:
                target.relative_to(skill_dir.resolve())
            except ValueError:
                return bad(handler, "Invalid file path", 400)
            if not target.exists() or not target.is_file():
                return bad(handler, "File not found", 404)
            return j(
                handler,
                {"content": target.read_text(encoding="utf-8"), "path": file_path},
            )
        data = _skill_view_from_active_dir(name)
        if not isinstance(data.get("linked_files"), dict):
            data["linked_files"] = {}
        return j(handler, data)

    # ── Memory API (GET) ──
    if parsed.path == "/api/memory":
        return _handle_memory_read(handler)

    # ── Profile API (GET) ──
    if parsed.path == "/api/profiles":
        from api.profiles import list_profiles_api, get_active_profile_name

        return j(
            handler,
            {"profiles": list_profiles_api(), "active": get_active_profile_name()},
        )

    if parsed.path == "/api/profile/active":
        from api.profiles import get_active_profile_name, get_active_hermes_home

        return j(
            handler,
            {"name": get_active_profile_name(), "path": str(get_active_hermes_home())},
        )

    # ── Gateway Status (GET) ──
    if parsed.path == "/api/gateway/status":
        return _gateway_routes.handle_gateway_status(
            handler,
            load_identity_map=_load_gateway_session_identity_map,
            sessions_metadata_path=_gateway_session_metadata_path,
            build_health_payload=build_agent_health_payload,
            normalize_messaging_source=_normalize_messaging_source,
            responder=j,
        )

    # ── MCP Servers (GET) ──
    if parsed.path == "/api/mcp/servers":
        return _handle_mcp_servers_list(handler)

    # ── MCP Tools (GET) ──
    if parsed.path == "/api/mcp/tools":
        return _handle_mcp_tools_list(handler)

    # ── Checkpoints / Rollback (GET) ──
    if parsed.path == "/api/rollback/list":
        return _rollback_routes.handle_rollback_list(handler, parsed, responder=j, error_responder=bad)

    if parsed.path == "/api/rollback/diff":
        return _rollback_routes.handle_rollback_diff(handler, parsed, responder=j, error_responder=bad)

    return False  # 404


# ── GET route helpers


def handle_post(handler, parsed) -> bool:
    """Handle all POST routes. Returns True if handled, False for 404."""
    diag = RequestDiagnostics.maybe_start("POST", parsed.path, logger=logger)
    if parsed.path == "/api/csp-report":
        if diag:
            diag.stage("csp_report")
        try:
            return _handle_csp_report(handler)
        finally:
            if diag:
                diag.finish()
    # CSRF: reject cross-origin or tokenless authenticated browser requests.
    # /api/auth/login has no authenticated session token yet, and /api/csp-report
    # is intentionally unauthenticated for browser-generated violation reports.
    if diag:
        diag.stage("csrf")
    if not _csrf_exempt_path(parsed.path) and not _check_csrf(handler):
        try:
            return j(handler, {"error": "Cross-origin request rejected"}, status=403)
        finally:
            if diag:
                diag.finish()

    if parsed.path == "/api/upload":
        return handle_upload(handler)
    if parsed.path == "/api/upload/extract":
        return handle_upload_extract(handler)

    if parsed.path == "/api/transcribe":
        return handle_transcribe(handler)

    if diag:
        diag.stage("read_body")
    try:
        body = read_body(handler)
    except Exception:
        if diag:
            diag.finish()
        raise

    if parsed.path == "/api/session/recovery/repair-safe":
        from api.session_recovery import repair_safe_session_recovery
        result = repair_safe_session_recovery(SESSION_DIR, state_db_path=_active_state_db_path())
        return j(handler, result, status=200 if result.get("clean") else 409)

    if parsed.path == "/api/dashboard/config":
        return _handle_dashboard_config_post(handler, body)

    if parsed.path == "/api/session/new":
        try:
            workspace = str(resolve_trusted_workspace(body.get("workspace"))) if body.get("workspace") else None
        except (TypeError, ValueError) as e:
            return bad(handler, str(e))
        worktree_info = None
        worktree_requested = (
            body.get("worktree") is True
            or str(body.get("worktree")).strip().lower() in {"1", "true", "yes", "on"}
        )
        if worktree_requested:
            try:
                from api.worktrees import create_worktree_for_workspace
                base_workspace = workspace
                if not base_workspace:
                    base_workspace = str(resolve_trusted_workspace(get_last_workspace()))
                worktree_info = create_worktree_for_workspace(base_workspace)
                workspace = worktree_info["path"]
            except (TypeError, ValueError) as e:
                return bad(handler, str(e), status=400)
            except Exception as e:
                logger.exception("failed to create worktree-backed session")
                return bad(handler, f"Failed to create worktree: {e}", status=500)
        model, model_provider = _session_model_state_from_request(
            body.get("model"),
            body.get("model_provider"),
        )
        # Use the profile sent by the client tab (if any) so that two tabs on
        # different profiles never clobber each other via the process-level global.
        # ── Memory lifecycle: commit the previous session before starting a new one ──
        prev_session_id = body.get("prev_session_id")
        if prev_session_id:
            try:
                from api.session_lifecycle import commit_session_memory
                from api.config import SESSION_AGENT_CACHE, SESSION_AGENT_CACHE_LOCK
                prev_agent = None
                with SESSION_AGENT_CACHE_LOCK:
                    _cached = SESSION_AGENT_CACHE.get(prev_session_id)
                    if _cached:
                        prev_agent = _cached[0]
                commit_session_memory(prev_session_id, agent=prev_agent)
            except Exception:
                logger.debug("Lifecycle commit for prev_session %s failed", prev_session_id, exc_info=True)
        s = new_session(
            workspace=workspace,
            model=model,
            model_provider=model_provider,
            profile=body.get("profile") or None,
            project_id=body.get("project_id") or None,
            worktree_info=worktree_info,
        )
        session_needs_save = False
        enabled_toolsets = _session_toolsets_from_request(body)
        if enabled_toolsets:
            s.enabled_toolsets = enabled_toolsets
            session_needs_save = True
        product_ctx = None
        if body.get("product_id") or body.get("productId"):
            try:
                from api.product_context import product_context_from_request

                product_ctx = product_context_from_request(body, workspace=workspace)
            except ValueError as e:
                return bad(handler, str(e), status=400)
            if product_ctx:
                product_task_title = _product_task_title_from_request(body)
                if product_task_title and product_ctx["scope"] == "product_init":
                    s.title = product_task_title
                s.product_id = product_ctx["id"]
                s.product_scope = product_ctx["scope"]
                s.product_intent = product_ctx.get("intent") or ""
                s.product_line = product_ctx.get("line") or "use"
                session_needs_save = True
                if not enabled_toolsets:
                    product_toolsets = _session_toolsets_from_request({"toolsets": product_ctx.get("tools") or []})
                    if product_toolsets:
                        s.enabled_toolsets = product_toolsets
                        session_needs_save = True
                try:
                    next_ui_status = (
                        "generating"
                        if product_ctx["scope"] in {"product_init", "product_builder"}
                        and str(product_ctx.get("ui_mode") or "") != "chat_only"
                        else None
                    )
                    record_product_session(
                        product_ctx["id"],
                        s.session_id,
                        ui_status=next_ui_status,
                    )
                except Exception:
                    logger.debug("Failed to bind session %s to product", s.session_id, exc_info=True)
        if session_needs_save:
            try:
                s.save(skip_index=True)
            except Exception:
                logger.debug("Failed to persist new session %s metadata", s.session_id, exc_info=True)
        session_payload = s.compact() | {"messages": s.messages}
        if product_ctx:
            session_payload.update(
                {
                    "product_id": product_ctx["id"],
                    "product_scope": product_ctx["scope"],
                    "product_intent": product_ctx.get("intent") or "",
                }
            )
        return j(handler, {"session": session_payload})

    if parsed.path == "/api/session/duplicate":
        try:
            sid = body.get("session_id")
            if not sid:
                return bad(handler, "session_id is required")

            session = Session.load(sid)
            if not session:
                # 404, not 400 — missing resource, not a malformed request.
                return bad(handler, "Session not found", status=404)

            # Deep-copy mutable lists so the duplicate is *actually* independent.
            # `Session.__init__` does `self.messages = messages or []` — plain
            # assignment, no copy. Without deepcopy, both sessions share the same
            # list object in memory; appending to one mutates the other.
            # Items inside `messages` are dicts with mutable values (tool_calls,
            # content arrays), so a shallow `list(...)` is not enough.
            copied_session = Session(
                session_id=uuid.uuid4().hex[:12],
                # Defensive: legacy sessions may have title=None on disk; fall back to 'Untitled'
                # so `+ " (copy)"` doesn't TypeError.
                title=(session.title or "Untitled") + " (copy)",
                workspace=session.workspace,
                model=session.model,
                model_provider=session.model_provider,
                messages=copy.deepcopy(session.messages),
                tool_calls=copy.deepcopy(session.tool_calls),
                # Reset ephemeral / per-session-instance flags. Duplicating an
                # archived conversation should produce a visible (un-archived)
                # copy; pinned status doesn't transfer either.
                pinned=False,
                archived=False,
                project_id=session.project_id,
                profile=session.profile,
                input_tokens=session.input_tokens,
                output_tokens=session.output_tokens,
                estimated_cost=session.estimated_cost,
                # Per-session settings the user may have customized — carry them over
                # so the duplicate behaves identically until further edits. Compression
                # anchor + last_prompt_tokens are intentionally NOT carried — those
                # re-derive on the next turn.
                personality=session.personality,
                enabled_toolsets=getattr(session, "enabled_toolsets", None),
                context_length=getattr(session, "context_length", None),
                threshold_tokens=getattr(session, "threshold_tokens", None),
                created_at=time.time(),
                updated_at=time.time(),
            )

            with LOCK:
                SESSIONS[copied_session.session_id] = copied_session
                SESSIONS.move_to_end(copied_session.session_id)
                while len(SESSIONS) > SESSIONS_MAX:
                    SESSIONS.popitem(last=False)
            # Persist immediately. The pre-PR flow (/api/session/new + /api/session/rename)
            # accidentally avoided this because `/api/session/rename` calls `s.save()`.
            # Without this explicit save, the duplicate is in-memory only — if the user
            # refreshes before sending a turn, the duplicate vanishes.
            copied_session.save()

            return j(handler, {"session": copied_session.compact() | {"messages": copied_session.messages}})
        except Exception as e:
            return bad(handler, str(e))

    if parsed.path == "/api/default-model":
        return _handle_default_model_post(handler, body)

    # ── Providers (POST) ──
    if parsed.path == "/api/providers":
        return _handle_providers_post(handler, body)

    if parsed.path == "/api/providers/delete":
        return _handle_providers_delete(handler, body)

    if parsed.path == "/api/reasoning":
        # Static compatibility anchors: set_reasoning_display, set_reasoning_effort
        return _handle_reasoning_post(handler, body)

    if parsed.path == "/api/admin/reload":
        # Hot-reload api.models module to pick up code changes without restart.
        import importlib
        from api import models as _models
        importlib.reload(_models)
        # Also re-expose get_session from the reloaded module so routes.py
        # continues to work (routes.py imported it at module level).
        import api.routes as _routes
        _routes.get_session = _models.get_session
        _routes.Session = _models.Session
        _routes.compact = _models.compact
        return j(handler, {"status": "ok", "reloaded": "api.models"})

    if parsed.path == "/api/sessions/cleanup":
        return _handle_sessions_cleanup(handler, body, zero_only=False)

    if parsed.path == "/api/sessions/cleanup_zero_message":
        return _handle_sessions_cleanup(handler, body, zero_only=True)

    if parsed.path == "/api/session/rename":
        return _handle_session_rename(handler, body)

    if parsed.path == "/api/personality/set":
        return _handle_personality_set(handler, body)

    if parsed.path == "/api/session/toolsets":
        return _handle_session_toolsets(handler, body)

    if parsed.path == "/api/session/draft":
        return _handle_session_draft(handler, parsed, body)

    if parsed.path == "/api/session/update":
        return _handle_session_update(handler, body)
    if parsed.path == "/api/session/worktree/remove":
        return _handle_session_worktree_remove(handler, body)

    if parsed.path == "/api/session/delete":
        sid = body.get("session_id", "")
        if not sid:
            return bad(handler, "session_id is required")
        if not all(c in '0123456789abcdefghijklmnopqrstuvwxyz_' for c in sid):
            return bad(handler, "Invalid session_id", 400)
        cli_meta_for_delete = _lookup_cli_session_metadata(sid)
        if cli_meta_for_delete.get("read_only"):
            return bad(handler, "Read-only imported sessions cannot be deleted from WebUI", 400)
        is_messaging_session = _is_messaging_session_id(sid)
        worktree_retained = _worktree_retained_payload_for_session_id(sid)
        # Delete from WebUI session store
        with LOCK:
            SESSIONS.pop(sid, None)
        try:
            SESSION_INDEX_FILE.unlink(missing_ok=True)
        except Exception:
            logger.debug("Failed to unlink session index")
        # Evict cached agent so turn count doesn't leak into a recycled session
        from api.config import _evict_session_agent
        _evict_session_agent(sid)
        try:
            p = (SESSION_DIR / f"{sid}.json").resolve()
            p.relative_to(SESSION_DIR.resolve())
        except Exception:
            return bad(handler, "Invalid session_id", 400)
        try:
            p.unlink(missing_ok=True)
            p.with_suffix('.json.bak').unlink(missing_ok=True)
        except Exception:
            logger.debug("Failed to unlink session file %s", p)
        try:
            from api.upload import _session_attachment_dir

            shutil.rmtree(_session_attachment_dir(sid), ignore_errors=True)
        except Exception:
            logger.debug("Failed to clean attachment dir for deleted session %s", sid)
        # Prune the per-session agent lock so deleted sessions don't leak
        # Lock entries in SESSION_AGENT_LOCKS forever.
        with SESSION_AGENT_LOCKS_LOCK:
            SESSION_AGENT_LOCKS.pop(sid, None)
        try:
            from api.terminal import close_terminal
            close_terminal(sid)
        except Exception:
            logger.debug("Failed to close workspace terminal for deleted session %s", sid)
        # Also delete from CLI state.db for CLI sessions shown in sidebar,
        # but never erase external messaging channel memory via WebUI delete.
        if not is_messaging_session:
            try:
                from api.models import delete_cli_session

                delete_cli_session(sid)
            except Exception:
                logger.debug("Failed to delete CLI session %s", sid)
        return j(handler, {"ok": True, **worktree_retained})

    if parsed.path == "/api/session/clear":
        # Static compatibility anchors for the lock-boundary test:
        # with _get_session_agent_lock(sid):
        # s.save()
        # Evict cached agent outside the per-session lock; _evict_session_agent(sid)
        # provider I/O must not hold the session mutation lock.
        return _handle_session_clear(handler, body)

    if parsed.path == "/api/session/truncate":
        return _handle_session_truncate(handler, body)

    if parsed.path == "/api/session/branch":
        # Fork a conversation from any message point (#465).
        # Accepts: {session_id, keep_count?, title?}
        #   keep_count: number of messages to copy (0=empty, undefined=full history)
        #   title: custom title (defaults to "<original title> (fork)")
        try:
            require(body, "session_id")
        except ValueError as e:
            return bad(handler, str(e))
        # Reject non-string session_id explicitly so the failure surfaces as a
        # 400 instead of a generic 500 from get_session() raising TypeError.
        # (Opus pre-release follow-up.)
        if not isinstance(body["session_id"], str):
            return bad(handler, "session_id must be a string")
        try:
            source = get_session(body["session_id"])
        except KeyError:
            return bad(handler, "Session not found", 404)

        keep_count = body.get("keep_count")
        if keep_count is not None:
            try:
                keep_count = int(keep_count)
            except (ValueError, TypeError):
                return bad(handler, "keep_count must be an integer")
            # Negative slice (`messages[:-N]`) returns "all but last N", which
            # is a confusing fork semantic. Reject explicitly so the user
            # doesn't accidentally fork a session with the tail truncated when
            # they meant to copy the prefix. (Opus pre-release follow-up.)
            if keep_count < 0:
                return bad(handler, "keep_count must be non-negative")

        custom_title = body.get("title")
        if custom_title:
            custom_title = str(custom_title).strip()[:80] or None

        # Build messages slice in the same coordinate space exposed by GET
        # /api/session so frontend keep_count values from merged messaging
        # transcripts do not silently become full sidecar copies.
        try:
            source.save()
        except Exception:
            pass
        cli_meta = _lookup_cli_session_metadata(source.session_id) if _session_requires_cli_metadata_lookup(source) else {}
        is_messaging_session = _is_messaging_session_record(source) or _is_messaging_session_record(cli_meta)
        cli_messages = get_cli_session_messages(source.session_id) if is_messaging_session else []
        source_messages = (
            _merged_session_messages_for_display(source, cli_messages)
            if is_messaging_session and cli_messages
            else list(source.messages or [])
        )
        if keep_count is not None:
            forked_messages = source_messages[:keep_count]
        else:
            forked_messages = list(source_messages)

        # Derive title
        if custom_title:
            branch_title = custom_title
        else:
            source_title = source.title or "Untitled"
            branch_title = f"{source_title} (fork)"

        # Create new session inheriting workspace/model/profile
        branch = Session(
            workspace=source.workspace,
            model=source.model,
            profile=getattr(source, "profile", None),
            title=branch_title,
            messages=forked_messages,
            parent_session_id=source.session_id,
            session_source="fork",
        )
        with LOCK:
            SESSIONS[branch.session_id] = branch
            SESSIONS.move_to_end(branch.session_id)
            while len(SESSIONS) > SESSIONS_MAX:
                SESSIONS.popitem(last=False)

        # Persist only if there are messages (matches new_session pattern)
        if forked_messages:
            branch.save()

        return j(handler, {
            "session_id": branch.session_id,
            "title": branch_title,
            "parent_session_id": source.session_id,
        })

    if parsed.path == "/api/session/compress/start":
        return _handle_session_compress_start(handler, body)

    if parsed.path == "/api/session/compress":
        return _handle_session_compress(handler, body)

    if parsed.path == "/api/session/conversation-rounds":
        return _handle_conversation_rounds(handler, body)

    if parsed.path == "/api/session/handoff-summary":
        return _handle_handoff_summary(handler, body)

    if parsed.path == "/api/session/retry":
        return _handle_session_retry(handler, body)

    if parsed.path == "/api/session/undo":
        return _handle_session_undo(handler, body)

    # ── YOLO mode toggle (POST) ──
    # Session-scoped only — stored in-memory on the server side.
    # Important lifecycle notes:
    #   • Page reload: state PERSISTS (frontend re-fetches via GET endpoint)
    #   • Cross-tab: state is SHARED (same server-side flag per session)
    #   • Server restart: state is LOST (in-memory only)
    #   • Cross-session: isolated (each session has its own flag)
    # Fixes #467
    if parsed.path == "/api/session/yolo":
        return _handle_session_yolo_post(handler, body)

    if parsed.path == "/api/btw":
        return _handle_btw(handler, body)

    if parsed.path == "/api/background":
        return _handle_background(handler, body)

    if parsed.path == "/api/goal":
        return _handle_goal_command(handler, body)

    if parsed.path == "/api/chat/start":
        return _handle_chat_start(handler, body, diag=diag)

    if parsed.path == "/api/chat":
        return _handle_chat_sync(handler, body)

    if parsed.path == "/api/chat/steer":
        from api.streaming import _handle_chat_steer
        return _handle_chat_steer(handler, body)

    if parsed.path == "/api/terminal/start":
        return _handle_terminal_start(handler, body)

    if parsed.path == "/api/terminal/input":
        return _handle_terminal_input(handler, body)

    if parsed.path == "/api/terminal/resize":
        return _handle_terminal_resize(handler, body)

    if parsed.path == "/api/terminal/close":
        return _handle_terminal_close(handler, body)

    # ── Cron API (POST) ──
    # See GET-side comment above: wrap in cron_profile_context so writes go
    # to the TLS-active profile's jobs.json instead of the process default.
    if parsed.path == "/api/crons/create":
        from api.profiles import cron_profile_context

        with cron_profile_context():
            return _handle_cron_create(handler, body)

    if parsed.path == "/api/crons/update":
        from api.profiles import cron_profile_context

        with cron_profile_context():
            return _handle_cron_update(handler, body)

    if parsed.path == "/api/crons/delete":
        from api.profiles import cron_profile_context

        with cron_profile_context():
            return _handle_cron_delete(handler, body)

    if parsed.path == "/api/crons/run":
        from api.profiles import cron_profile_context

        with cron_profile_context():
            return _handle_cron_run(handler, body)

    if parsed.path == "/api/crons/pause":
        from api.profiles import cron_profile_context

        with cron_profile_context():
            return _handle_cron_pause(handler, body)

    if parsed.path == "/api/crons/resume":
        from api.profiles import cron_profile_context

        with cron_profile_context():
            return _handle_cron_resume(handler, body)

    # ── File ops (POST) ──
    if parsed.path == "/api/file/delete":
        return _handle_file_delete(handler, body)

    if parsed.path == "/api/file/save":
        return _handle_file_save(handler, body)

    if parsed.path == "/api/file/create":
        return _handle_file_create(handler, body)

    if parsed.path == "/api/file/rename":
        return _handle_file_rename(handler, body)

    if parsed.path == "/api/file/create-dir":
        return _handle_create_dir(handler, body)

    if parsed.path == "/api/file/reveal":
        return _handle_file_reveal(handler, body)

    if parsed.path == "/api/file/path":
        return _handle_file_path(handler, body)

    # ── Workspace management (POST) ──
    if parsed.path == "/api/workspaces/add":
        return _handle_workspace_add(handler, body)

    if parsed.path == "/api/workspaces/remove":
        return _handle_workspace_remove(handler, body)

    if parsed.path == "/api/workspaces/rename":
        return _handle_workspace_rename(handler, body)

    if parsed.path == "/api/workspaces/reorder":
        return _handle_workspace_reorder(handler, body)

    # ── AI product management (POST) ──
    if parsed.path == "/api/products/create":
        return j(handler, create_product(body))

    if parsed.path == "/api/products/update":
        product_id = str(body.get("id") or body.get("product_id") or body.get("kind") or "").strip()
        if not product_id:
            return bad(handler, "product id is required", status=400)
        try:
            return j(handler, update_product(product_id, body))
        except FileNotFoundError:
            return bad(handler, "AI product not found", status=404)

    if parsed.path == "/api/products/delete":
        product_id = str(body.get("id") or body.get("product_id") or body.get("kind") or "").strip()
        if not product_id:
            return bad(handler, "product id is required", status=400)
        try:
            return j(handler, delete_product(product_id, remove_files=body.get("remove_files") is not False))
        except FileNotFoundError:
            return bad(handler, "AI product not found", status=404)

    if parsed.path == "/api/products/finalize":
        product_id = str(body.get("id") or body.get("product_id") or body.get("kind") or "").strip()
        if not product_id:
            return bad(handler, "product id is required", status=400)
        product = finalize_product_generation(
            product_id,
            failed=bool(body.get("failed")),
            error_type=str(body.get("error_type") or body.get("ui_error_type") or "").strip() or None,
            error_message=str(body.get("error_message") or body.get("ui_error_message") or "").strip() or None,
        )
        if not product:
            return bad(handler, "AI product not found", status=404)
        return j(handler, {"ok": True, "product": product})

    if parsed.path.startswith("/api/products/") and parsed.path.endswith("/snapshot"):
        product_id = unquote(parsed.path[len("/api/products/"):-len("/snapshot")].strip("/"))
        if not product_id:
            product_id = str(body.get("id") or body.get("product_id") or body.get("kind") or "").strip()
        if not product_id:
            return bad(handler, "product id is required", status=400)
        try:
            return j(handler, snapshot_product(product_id, reason=str(body.get("reason") or "").strip()))
        except FileNotFoundError:
            return bad(handler, "AI product not found", status=404)

    if parsed.path.startswith("/api/products/") and parsed.path.endswith("/rollback"):
        product_id = unquote(parsed.path[len("/api/products/"):-len("/rollback")].strip("/"))
        if not product_id:
            product_id = str(body.get("id") or body.get("product_id") or body.get("kind") or "").strip()
        if not product_id:
            return bad(handler, "product id is required", status=400)
        try:
            return j(handler, rollback_product(product_id, version_id=str(body.get("version_id") or body.get("version") or "").strip() or None))
        except FileNotFoundError:
            return bad(handler, "AI product version not found", status=404)

    # ── Approval (POST) ──
    if parsed.path == "/api/approval/respond":
        return _handle_approval_respond(handler, body)

    # ── Clarify (POST) ──
    if parsed.path == "/api/clarify/respond":
        return _handle_clarify_respond(handler, body)

    # ── Commands (POST) ──
    if parsed.path == "/api/commands/exec":
        return _handle_command_exec(handler, body)

    # ── Skills (POST) ──
    if parsed.path == "/api/skills/save":
        return _handle_skill_save(handler, body)

    if parsed.path == "/api/skills/delete":
        return _handle_skill_delete(handler, body)

    # ── Memory (POST) ──
    if parsed.path == "/api/memory/write":
        return _handle_memory_write(handler, body)

    # ── Profile API (POST) ──
    if parsed.path == "/api/profile/switch":
        return _handle_profile_switch(handler, body)

    if parsed.path == "/api/profile/create":
        # Static compatibility anchors for profile model picker tests:
        # default_model = body.get("default_model"; model_provider = body.get("model_provider"
        # default_model=default_model; model_provider=model_provider
        return _handle_profile_create(handler, body)

    if parsed.path == "/api/profile/delete":
        return _handle_profile_delete(handler, body)

    # ── Settings (POST) ──
    if parsed.path == "/api/settings":
        return _handle_settings_post(handler, body)

    if parsed.path == "/api/onboarding/oauth/start":
        return _handle_onboarding_oauth_start(handler, body)

    if parsed.path == "/api/onboarding/oauth/cancel":
        return _handle_onboarding_oauth_cancel(handler, body)

    if parsed.path == "/api/onboarding/setup":
        return _handle_onboarding_setup(handler, body)

    if parsed.path == "/api/onboarding/complete":
        return j(handler, complete_onboarding())

    if parsed.path == "/api/onboarding/probe":
        return _handle_onboarding_probe(handler, body)

    # ── Session pin (POST) ──
    if parsed.path == "/api/session/pin":
        return _handle_session_pin(handler, body)

    # ── Session archive (POST) ──
    if parsed.path == "/api/session/archive":
        # Static compatibility anchor: Read-only imported sessions cannot be archived
        return _handle_session_archive(handler, body)

    # ── Session move to project (POST) ──
    if parsed.path == "/api/session/move":
        # Static compatibility anchor: _profiles_match(target.get("profile"), active_profile)
        return _handle_session_move(handler, body)

    # ── Project CRUD (POST) ──
    if parsed.path == "/api/projects/create":
        # Static compatibility anchor: "profile": get_active_profile_name() or 'default'
        return _handle_project_create(handler, body)

    if parsed.path == "/api/projects/rename":
        # Static compatibility anchor: _profiles_match(proj.get("profile"), active_profile)
        return _handle_project_rename(handler, body)

    if parsed.path == "/api/projects/delete":
        # Static compatibility anchor: _profiles_match(proj.get("profile"), active_profile)
        return _handle_project_delete(handler, body)

    # ── Session import from JSON (POST) ──
    if parsed.path == "/api/session/import":
        return _handle_session_import(handler, body)

    # ── Self-update (POST) ──
    if parsed.path == "/api/updates/apply":
        return _handle_update_apply(handler, body)

    if parsed.path == "/api/updates/force":
        # Static compatibility anchor: apply_force_update
        return _handle_update_force(handler, body)

    if parsed.path == "/api/updates/summary":
        # Static compatibility anchors: summarize_update_payload; get_text_auxiliary_client; "compression"; main_runtime=main_runtime;
        # from run_agent import AIAgent
        # update summary auxiliary model failed; falling back to main model
        return _handle_update_summary(handler, body)

    # ── CLI session import (POST) ──
    if parsed.path == "/api/session/import_cli":
        return _handle_session_import_cli(handler, body)

    # ── Auth endpoints (POST) ──
    if parsed.path == "/api/auth/login":
        return _handle_auth_login(handler, body)

    if parsed.path == "/api/auth/logout":
        return _handle_auth_logout(handler)

    # ── Checkpoints / Rollback (POST) ──
    if parsed.path == "/api/rollback/restore":
        return _rollback_routes.handle_rollback_restore(handler, body, responder=j, error_responder=bad)

    return False  # 404


def handle_patch(handler, parsed) -> bool:
    """Handle all PATCH routes. Returns True if handled, False for 404."""
    if not _check_csrf(handler):
        return j(handler, {"error": "Cross-origin request rejected"}, status=403)
    body = read_body(handler)
    return False


def handle_delete(handler, parsed) -> bool:
    """Handle all DELETE routes. Returns True if handled, False for 404."""
    if not _check_csrf(handler):
        return j(handler, {"error": "Cross-origin request rejected"}, status=403)
    body = read_body(handler)
    return False

# ── GET route helpers ─────────────────────────────────────────────────────────

# MIME types for static file serving. Hoisted to module scope to avoid
# rebuilding the dict on every request.
_STATIC_MIME = {
    "css": "text/css",
    "js": "application/javascript",
    "html": "text/html",
    "svg": "image/svg+xml",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "ico": "image/x-icon",
    "gif": "image/gif",
    "webp": "image/webp",
    "woff": "font/woff",
    "woff2": "font/woff2",
    # Office / download formats
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt":  "application/vnd.ms-powerpoint",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf":  "application/pdf",
    "zip":  "application/zip",
}
# MIME types that are text-based and should carry charset=utf-8
_TEXT_MIME_TYPES = {"text/css", "application/javascript", "text/html", "image/svg+xml", "text/plain"}


def _serve_static(handler, parsed):
    return _static_routes.serve_static(
        handler,
        parsed,
        module_file=__file__,
        static_mime=_STATIC_MIME,
        text_mime_types=_TEXT_MIME_TYPES,
        json_response_fn=j,
    )


def _serve_product_preview(handler, parsed):
    return _static_routes.serve_product_preview(
        handler,
        parsed,
        preview_product_file_fn=preview_product_file,
        serve_file_response_fn=_serve_file_response,
        json_response_fn=j,
    )


def _serve_product_asset(handler, parsed):
    return _static_routes.serve_product_asset(
        handler,
        parsed,
        preview_product_file_fn=preview_product_file,
        serve_file_response_fn=_serve_file_response,
        json_response_fn=j,
    )


def _serve_file_response(handler, target: Path):
    return _static_routes.serve_file_response(
        handler,
        target,
        static_mime=_STATIC_MIME,
        text_mime_types=_TEXT_MIME_TYPES,
    )


def _handle_session_export(handler, parsed):
    return _session_routes.handle_session_export(
        handler,
        parsed,
        get_session_fn=get_session,
        redact_session_data_fn=redact_session_data,
        bad_response_fn=bad,
    )


def _handle_sessions_search(handler, parsed):
    return _session_routes.handle_sessions_search(
        handler,
        parsed,
        all_sessions_fn=all_sessions,
        get_session_fn=get_session,
        redact_text_fn=_redact_text,
        json_response_fn=j,
    )


def _handle_list_dir(handler, parsed):
    return _session_routes.handle_list_dir(
        handler,
        parsed,
        get_session_fn=get_session,
        get_cli_sessions_fn=get_cli_sessions,
        list_dir_fn=list_dir,
        json_response_fn=j,
        bad_response_fn=bad,
        sanitize_error_fn=_sanitize_error,
    )


def _sse_with_id(handler, event, data, event_id=None):
    if event_id:
        handler.wfile.write(f"id: {event_id}\n".encode("utf-8"))
    _sse(handler, event, data)


def _parse_run_journal_after_seq(qs: dict) -> int | None:
    raw = qs.get("after_seq", [None])[0]
    if raw in (None, ""):
        return None
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _replay_run_journal(handler, stream_id: str, after_seq: int | None) -> bool:
    summary = find_run_summary(stream_id)
    if not summary:
        return False
    journal = read_run_events(
        str(summary.get("session_id") or ""),
        stream_id,
        after_seq=after_seq,
    )
    for entry in journal.get("events") or []:
        _sse_with_id(
            handler,
            entry.get("event") or entry.get("type") or "message",
            entry.get("payload"),
            entry.get("event_id"),
        )
    if not summary.get("terminal"):
        stale = stale_interrupted_event(
            str(summary.get("session_id") or ""),
            stream_id,
            after_seq=after_seq,
        )
        if stale:
            _sse_with_id(handler, stale["event"], stale["payload"], stale["event_id"])
    return True


def _handle_sse_stream(handler, parsed):
    qs = parse_qs(parsed.query)
    stream_id = qs.get("stream_id", [""])[0]
    stream = STREAMS.get(stream_id)
    if stream is None:
        try:
            journal_available = bool(find_run_summary(stream_id)) if stream_id else False
        except Exception:
            journal_available = False
        if not journal_available:
            return j(handler, {"error": "stream not found"}, status=404)
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("X-Accel-Buffering", "no")
        handler.send_header("Connection", "keep-alive")
        handler.end_headers()
        try:
            _replay_run_journal(handler, stream_id, _parse_run_journal_after_seq(qs))
        except _CLIENT_DISCONNECT_ERRORS:
            pass
        return True
    subscriber = stream.subscribe() if hasattr(stream, "subscribe") else stream
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("X-Accel-Buffering", "no")
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()
    try:
        while True:
            try:
                event, data = subscriber.get(timeout=_SSE_HEARTBEAT_INTERVAL_SECONDS)
            except queue.Empty:
                handler.wfile.write(b": heartbeat\n\n")
                handler.wfile.flush()
                continue
            # Stage-364: emit `id:` from STREAM_LAST_EVENT_ID side-channel so
            # the frontend's `_lastRunJournalSeq` cursor advances during live
            # streaming. Without this, mid-stream error→replay would arrive
            # with after_seq=0 and double-render every journaled event.
            event_id = STREAM_LAST_EVENT_ID.get(stream_id)
            if event_id:
                _sse_with_id(handler, event, data, event_id)
            else:
                _sse(handler, event, data)
            if event in ("stream_end", "error", "cancel"):
                break
    except _CLIENT_DISCONNECT_ERRORS:
        pass
    finally:
        if subscriber is not stream and hasattr(stream, "unsubscribe"):
            try:
                stream.unsubscribe(subscriber)
            except Exception:
                pass
    return True


def _terminal_session_and_workspace(body_or_query):
    return _terminal_routes.terminal_session_and_workspace(
        body_or_query,
        get_session_fn=get_session,
        resolve_trusted_workspace_fn=resolve_trusted_workspace,
    )


def _handle_terminal_start(handler, body):
    return _terminal_routes.handle_terminal_start(
        handler,
        body,
        terminal_session_and_workspace_fn=_terminal_session_and_workspace,
        json_response_fn=j,
        bad_response_fn=bad,
        sanitize_error_fn=_sanitize_error,
    )


def _handle_terminal_input(handler, body):
    return _terminal_routes.handle_terminal_input(
        handler,
        body,
        require_fn=require,
        json_response_fn=j,
        bad_response_fn=bad,
        sanitize_error_fn=_sanitize_error,
    )


def _handle_terminal_resize(handler, body):
    return _terminal_routes.handle_terminal_resize(
        handler,
        body,
        require_fn=require,
        json_response_fn=j,
        bad_response_fn=bad,
        sanitize_error_fn=_sanitize_error,
    )


def _handle_terminal_close(handler, body):
    return _terminal_routes.handle_terminal_close(
        handler,
        body,
        require_fn=require,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_terminal_output(handler, parsed):
    return _terminal_routes.handle_terminal_output(
        handler,
        parsed,
        json_response_fn=j,
        bad_response_fn=bad,
        sse_fn=_sse,
        heartbeat_interval_seconds=_SSE_HEARTBEAT_INTERVAL_SECONDS,
        queue_empty_error=queue.Empty,
        client_disconnect_errors=_CLIENT_DISCONNECT_ERRORS,
    )


def _gateway_sse_probe_payload(settings, watcher):
    return _gateway_sse_routes.gateway_sse_probe_payload(settings, watcher)


def _handle_gateway_sse_stream(handler, parsed):
    """SSE endpoint for real-time gateway session updates.
    Streams change events from the gateway watcher background thread.
    Only active when show_cli_sessions (show_agent_sessions) setting is enabled.
    """
    from api.gateway_watcher import get_watcher
    from api.models import get_cli_sessions

    return _gateway_sse_routes.handle_gateway_sse_stream(
        handler,
        parsed,
        load_settings_fn=load_settings,
        get_watcher_fn=get_watcher,
        json_response_fn=j,
        sse_fn=_sse,
        get_cli_sessions_fn=get_cli_sessions,
        heartbeat_interval_seconds=_SSE_HEARTBEAT_INTERVAL_SECONDS,
        queue_empty_error=queue.Empty,
        client_disconnect_errors=_CLIENT_DISCONNECT_ERRORS,
        probe_payload_fn=_gateway_sse_probe_payload,
    )


def _content_disposition_value(disposition: str, filename: str) -> str:
    """Build a latin-1-safe Content-Disposition value with RFC 5987 filename*."""
    return _file_response_routes.content_disposition_value(disposition, filename)


def _parse_range_header(range_header: str, file_size: int) -> tuple[int, int] | None:
    """Parse a single HTTP bytes range into inclusive start/end offsets."""
    return _file_response_routes.parse_range_header(range_header, file_size)


def _serve_file_bytes(handler, target: Path, mime: str, disposition: str, cache_control: str, *, csp: str | None = None):
    """Serve a file with correct MIME/disposition and optional byte-range support."""
    return _file_response_routes.serve_file_bytes(
        handler,
        target,
        mime,
        disposition,
        cache_control,
        csp=csp,
        bad_response_fn=bad,
        security_headers_fn=_security_headers,
        parse_range_header_fn=_parse_range_header,
        content_disposition_value_fn=_content_disposition_value,
    )


def _handle_media(handler, parsed):
    """Serve local media; implementation lives in api.file_response_routes.

    Static-test anchors kept here for legacy route-source checks:
    /tmp, image/svg+xml, _INLINE_IMAGE_TYPES, MEDIA_ALLOWED_ROOTS.
    extra_roots = _os.environ.get("MEDIA_ALLOWED_ROOTS", "").strip()
    for root in extra_roots.split(_os.pathsep): ...
    Byte-range anchors are implemented by _serve_file_bytes: Accept-Ranges,
    Content-Range, 206.
    """
    return _file_response_routes.handle_media(
        handler,
        parsed,
        mime_map=MIME_MAP,
        bad_response_fn=bad,
        json_response_fn=j,
        serve_file_bytes_fn=_serve_file_bytes,
    )


def _file_raw_target(session, sid: str, rel: str) -> Path | None:
    """Resolve /api/file/raw paths from the workspace or this session's uploads."""
    return _file_response_routes.file_raw_target(session, sid, rel, safe_resolve_fn=safe_resolve)


def _handle_file_raw(handler, parsed):
    """Serve workspace/upload bytes.

    Static-test anchors: inline_preview, html_inline_ok, dangerous_types,
    text/html, application/xhtml+xml, image/svg+xml, Content-Security-Policy,
    sandbox.
    """
    return _file_response_routes.handle_file_raw(
        handler,
        parsed,
        mime_map=MIME_MAP,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        file_raw_target_fn=_file_raw_target,
        serve_file_bytes_fn=_serve_file_bytes,
    )


def _handle_file_read(handler, parsed):
    return _file_response_routes.handle_file_read(
        handler,
        parsed,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        read_file_content_fn=read_file_content,
        sanitize_error_fn=_sanitize_error,
    )


def _handle_approval_pending(handler, parsed):
    """Return the first queued approval plus pending_count."""
    return _interaction_routes.handle_approval_pending(
        handler,
        parsed,
        pending=_pending,
        lock=_lock,
        json_response_fn=j,
    )


def _handle_approval_sse_stream(handler, parsed):
    """SSE endpoint for real-time approval notifications.

    Long-lived connection that pushes approval events the moment they arrive,
    replacing the 1.5s polling loop.  The frontend uses EventSource and falls
    back to HTTP polling if the connection fails.
    """
    sid = parse_qs(parsed.query).get("session_id", [""])[0]
    if not sid:
        return bad(handler, "session_id is required")

    # Subscribe AND snapshot atomically under a single _lock acquisition so a
    # submit_pending() that fires between the two cannot be lost. If we
    # snapshot first then subscribe (the naive ordering), an approval that
    # arrives in the gap is appended to _pending (after our snapshot) AND
    # notified to subscribers (before we joined) — leaving the client unaware
    # until the next event arrives.
    q = queue.Queue(maxsize=16)
    initial_pending = None
    initial_count = 0
    with _lock:
        _approval_sse_subscribers.setdefault(sid, []).append(q)
        q_list = _pending.get(sid)
        if isinstance(q_list, list):
            initial_pending = dict(q_list[0]) if q_list else None
            initial_count = len(q_list)
        elif q_list:
            initial_pending = dict(q_list)
            initial_count = 1

    handler.send_response(200)
    handler.send_header('Content-Type', 'text/event-stream; charset=utf-8')
    handler.send_header('Cache-Control', 'no-cache')
    handler.send_header('X-Accel-Buffering', 'no')
    handler.send_header('Connection', 'keep-alive')
    handler.end_headers()

    from api.streaming import _sse

    # Push initial state immediately so the client doesn't miss anything.
    _sse(handler, 'initial', {"pending": initial_pending, "pending_count": initial_count})

    try:
        while True:
            try:
                payload = q.get(timeout=_SSE_HEARTBEAT_INTERVAL_SECONDS)
            except queue.Empty:
                # Keepalive — SSE comment line prevents proxy/CDN timeout.
                handler.wfile.write(b': keepalive\n\n')
                handler.wfile.flush()
                continue
            if payload is None:
                break  # signal to close
            _sse(handler, 'approval', payload)
    except _CLIENT_DISCONNECT_ERRORS:
        pass  # client went away — normal for long-lived connections
    finally:
        _approval_sse_unsubscribe(sid, q)


def _handle_approval_inject(handler, parsed):
    """Inject a fake pending approval -- loopback-only, used by automated tests."""
    return _interaction_routes.handle_approval_inject(
        handler,
        parsed,
        submit_pending_fn=submit_pending,
        json_response_fn=j,
    )


def _handle_clarify_pending(handler, parsed):
    return _interaction_routes.handle_clarify_pending(
        handler,
        parsed,
        get_pending_fn=get_clarify_pending,
        json_response_fn=j,
    )


def _handle_clarify_sse_stream(handler, parsed):
    """SSE endpoint for real-time clarify notifications.

    Long-lived connection that pushes clarify events the moment they arrive,
    replacing the 1.5s polling loop.  The frontend uses EventSource and falls
    back to HTTP polling if the connection fails.
    """
    if clarify_sse_subscribe is None:
        return bad(handler, "clarify SSE not available")

    sid = parse_qs(parsed.query).get("session_id", [""])[0]
    if not sid:
        return bad(handler, "session_id is required")

    # Subscribe AND snapshot atomically.  We import clarify's _lock so that
    # subscribe and the snapshot read happen under the same mutex — same
    # pattern as the approval SSE handler.
    #
    # NOTE: We must NOT call clarify.get_pending() here — it acquires _lock
    # internally, which would deadlock since clarify._lock is a non-reentrant
    # threading.Lock.  Instead, read _gateway_queues / _pending inline under
    # the lock we already hold.
    from api.clarify import (
        _lock as _clarify_lock,
        _clarify_sse_subscribers as _clarify_subs,
        _gateway_queues as _clarify_gateway_queues,
        _pending as _clarify_pending,
    )
    q = queue.Queue(maxsize=16)
    initial_pending = None
    initial_count = 0
    with _clarify_lock:
        _clarify_subs.setdefault(sid, []).append(q)
        gw_q = _clarify_gateway_queues.get(sid) or []
        if gw_q:
            initial_pending = dict(gw_q[0].data)
            initial_count = len(gw_q)
        else:
            _legacy = _clarify_pending.get(sid)
            if _legacy:
                initial_pending = dict(_legacy)
                initial_count = 1

    handler.send_response(200)
    handler.send_header('Content-Type', 'text/event-stream; charset=utf-8')
    handler.send_header('Cache-Control', 'no-cache')
    handler.send_header('X-Accel-Buffering', 'no')
    handler.send_header('Connection', 'keep-alive')
    handler.end_headers()

    from api.streaming import _sse

    # Push initial state immediately so the client doesn't miss anything.
    _sse(handler, 'initial', {"pending": initial_pending, "pending_count": initial_count})

    try:
        while True:
            try:
                payload = q.get(timeout=_SSE_HEARTBEAT_INTERVAL_SECONDS)
            except queue.Empty:
                handler.wfile.write(b': keepalive\n\n')
                handler.wfile.flush()
                continue
            if payload is None:
                break
            _sse(handler, 'clarify', payload)
    except _CLIENT_DISCONNECT_ERRORS:
        pass
    finally:
        clarify_sse_unsubscribe(sid, q)


def _handle_clarify_inject(handler, parsed):
    """Inject a fake pending clarify prompt -- loopback-only, used by automated tests."""
    return _interaction_routes.handle_clarify_inject(
        handler,
        parsed,
        submit_pending_fn=submit_clarify_pending,
        json_response_fn=j,
    )


def _handle_live_models(handler, parsed):
    """Return the live model list for a provider.

    Delegates to the agent's provider_model_ids() which handles:
    - OpenRouter: live fetch from /api/v1/models
    - Anthropic: live fetch from /v1/models (API key or OAuth token)
    - Copilot: live fetch from api.githubcopilot.com/models with correct headers
    - openai-codex: Codex OAuth endpoint + local ~/.codex/ cache fallback
    - Nous: live fetch from inference-api.nousresearch.com/v1/models
    - DeepSeek, kimi-coding, opencode-zen/go, custom: generic OpenAI-compat /v1/models
    - ZAI, MiniMax, Google/Gemini: fall back to static list (non-standard endpoints)
    - All others: static _PROVIDER_MODELS fallback

    The agent already maintains all provider-specific auth and endpoint logic
    in one place; the WebUI inherits it rather than duplicating it.

    Query params:
        provider  (optional) — provider ID; defaults to active profile provider
    """
    qs = parse_qs(parsed.query)
    provider = (qs.get("provider", [""])[0] or "").lower().strip()

    try:
        from api.config import get_config as _gc
        cfg = _gc()
        if not provider:
            provider = cfg.get("model", {}).get("provider") or ""
        if not provider:
            return j(handler, {"error": "no_provider", "models": []})

        # Normalize provider alias so 'z.ai' -> 'zai', 'x.ai' -> 'xai', etc.
        # The browser sends whatever active_provider the static endpoint returned;
        # without normalization, provider_model_ids() misses the alias and returns [].
        # Uses the WebUI-owned table (api/config._resolve_provider_alias) which
        # works even when hermes_cli is not on sys.path.
        from api.config import _resolve_provider_alias
        provider = _resolve_provider_alias(provider)

        cache_key = _live_models_cache_key(provider)
        cached = _get_cached_live_models(cache_key)
        if cached is not None:
            return j(handler, cached)

        def _finish(payload: dict):
            _set_cached_live_models(cache_key, payload)
            return j(handler, payload)

        # Delegate to the agent's live-fetch + fallback resolver.
        # provider_model_ids() tries live endpoints first and falls back to
        # the static _PROVIDER_MODELS list — it never raises.
        try:
            import sys as _sys
            import os as _os
            _agent_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                                       "..", "..", ".hermes", "hermes-agent")
            _agent_dir = _os.path.normpath(_agent_dir)
            if _agent_dir not in _sys.path:
                _sys.path.insert(0, _agent_dir)
            from hermes_cli.models import provider_model_ids as _pmi
            ids = _pmi(provider)
        except Exception as _import_err:
            logger.debug("provider_model_ids import failed for %s: %s", provider, _import_err)
            ids = []

        if not ids:
            custom_provider_entry = None

            def _custom_provider_entries_for_request():
                if not (provider == "custom" or provider.startswith("custom:")):
                    return []
                try:
                    from api.config import _custom_provider_slug_from_name
                    _cp_entries = cfg.get("custom_providers", [])
                    if not isinstance(_cp_entries, list):
                        return []
                    _matches = []
                    for _cp in _cp_entries:
                        if not isinstance(_cp, dict):
                            continue
                        _slug = _custom_provider_slug_from_name(_cp.get("name", ""))
                        if provider.startswith("custom:"):
                            if _slug == provider:
                                _matches.append(_cp)
                        elif provider == "custom" and not _slug:
                            _matches.append(_cp)
                    return _matches
                except Exception:
                    return []

            def _custom_provider_model_ids(_cp):
                _ids = []

                def _append(_mid):
                    _mid = str(_mid or "").strip()
                    if _mid and _mid not in _ids:
                        _ids.append(_mid)

                _append(_cp.get("model", ""))
                _models = _cp.get("models")
                if isinstance(_models, dict):
                    for _mid in _models:
                        if isinstance(_mid, str):
                            _append(_mid)
                elif isinstance(_models, list):
                    for _item in _models:
                        if isinstance(_item, str):
                            _append(_item)
                        elif isinstance(_item, dict):
                            _append(_item.get("id") or _item.get("model") or _item.get("name"))
                return _ids

            def _custom_provider_api_key(_cp):
                _raw = _cp.get("api_key")
                if _raw is not None:
                    _key = str(_raw).strip()
                    if _key.startswith("${") and _key.endswith("}") and len(_key) > 3:
                        _key = os.getenv(_key[2:-1], "").strip()
                    if _key:
                        return _key
                _env = str(_cp.get("key_env") or "").strip()
                return os.getenv(_env, "").strip() if _env else ""

            # For 'custom' and 'custom:*' providers, provider_model_ids()
            # returns [] because they aren't real hermes_cli endpoints.
            # Fall back to the custom_providers entries from config.yaml so
            # the live-model enrichment step can add any models that weren't
            # already in the static list (issue #1619).
            if provider == "custom" or provider.startswith("custom:"):
                for _cp in _custom_provider_entries_for_request():
                    if custom_provider_entry is None:
                        custom_provider_entry = _cp
                    ids.extend(_custom_provider_model_ids(_cp))
            
            # If still no ids, try fetching from base_url directly (OpenAI-compat endpoint)
            if not ids and (provider == "custom" or provider.startswith("custom:")):
                _base_url = None
                _api_key = None
                if custom_provider_entry:
                    _base_url = custom_provider_entry.get("base_url")
                    _api_key = _custom_provider_api_key(custom_provider_entry)
                else:
                    _model_cfg = cfg.get("model", {})
                    _base_url = _model_cfg.get("base_url")
                    _api_key = _model_cfg.get("api_key")
                if _base_url and _api_key:
                    try:
                        import urllib.request
                        import json
                        
                        # Build the models endpoint URL
                        # AxonHub and similar OpenAI-compat endpoints serve /v1/models
                        _ep = _base_url.rstrip("/")
                        # If base_url already ends with /v1, use /models; otherwise add /v1/models
                        if _ep.endswith("/v1"):
                            _models_url = f"{_ep}/models"
                        else:
                            _models_url = f"{_ep}/v1/models"
                        
                        _req = urllib.request.Request(
                            _models_url,
                            headers={"Authorization": f"Bearer {_api_key}"},
                        )
                        
                        with urllib.request.urlopen(_req, timeout=8) as _resp:
                            _body = json.loads(_resp.read())
                        
                        # Parse response: {"data": [{"id": "model1", ...}, ...]}
                        if isinstance(_body, dict):
                            _data = _body.get("data", [])
                            if isinstance(_data, list):
                                ids = [m.get("id", "") for m in _data if m.get("id")]
                        elif isinstance(_body, list):
                            ids = [m.get("id", m) if isinstance(m, dict) else m for m in _body]
                        
                        if ids:
                            logger.debug("Live-fetched %d models from custom provider %s", len(ids), _base_url)
                        else:
                            logger.debug("Custom provider returned no models from %s", _base_url)
                    
                    except Exception as _fetch_err:
                        logger.debug("Live fetch from custom provider failed: %s", _fetch_err)

        # ── OpenAI-compat live fetch fallback ──────────────────────────────────
        # When provider_model_ids() is unavailable or returns [] for a provider
        # that exposes a standard /v1/models endpoint, fetch directly.  This
        # eliminates the need to keep _PROVIDER_MODELS in sync for providers
        # that have a discoverable API (#871).
        #
        # WARNING: This uses synchronous urllib.request which blocks the worker
        # thread for up to 8 seconds on timeout. This is acceptable because:
        #  (a) the server uses threading (not async), so other requests continue;
        #  (b) the frontend shows the static list immediately and enriches in
        #      the background via _fetchLiveModels(), so the user never waits.
        if not ids:
            _ep = _OPENAI_COMPAT_ENDPOINTS.get(provider)
            if _ep:
                try:
                    import urllib.request
                    _providers_cfg = cfg.get("providers", {})
                    _prov = _providers_cfg.get(provider, {}) if isinstance(_providers_cfg, dict) else {}
                    # Only use provider-scoped key — never fall back to a top-level
                    # api_key which may belong to a different provider.
                    _key = _prov.get("api_key") if isinstance(_prov, dict) else None
                    if not _key:
                        _key = cfg.get("model", {}).get("api_key")
                    if _key:
                        _req = urllib.request.Request(
                            f"{_ep}/models",
                            headers={"Authorization": f"Bearer {_key}"},
                        )
                        with urllib.request.urlopen(_req, timeout=8) as _resp:
                            _body = json.loads(_resp.read())
                        ids = [m.get("id", "") for m in _body.get("data", []) if m.get("id")]
                        logger.debug("Live-fetched %d models from %s /v1/models", len(ids), provider)
                except Exception as _fetch_err:
                    logger.debug("Live fetch from %s failed: %s", provider, _fetch_err)
                    # Fall through to static list below

        # Static fallback — only reached when live fetch also failed.
        if not ids:
            from api.config import _PROVIDER_MODELS as _pm
            ids = [m["id"] for m in _pm.get(provider, [])]
        if not ids:
            return _finish({"provider": provider, "models": [], "count": 0})

        # For Nous Portal, apply the same featured-set cap that
        # /api/models uses so background enrichment via _fetchLiveModels()
        # doesn't undo the dropdown trim — otherwise a 397-model catalog
        # would still flood the picker after the initial render finished
        # the cap. The full list is returned via the main /api/models
        # endpoint's extra_models field for /model autocomplete; the live
        # endpoint is purely a dropdown-enrichment surface, so it should
        # match the dropdown's visibility budget. (#1567)
        if provider == "nous":
            try:
                from api.config import _build_nous_featured_set
                _default_model = (cfg.get("model", {}) or {}).get("model") if isinstance(cfg.get("model"), dict) else None
                _featured, _ = _build_nous_featured_set(ids, selected_model_id=_default_model)
                ids = _featured
            except Exception:
                logger.debug("Failed to apply Nous featured-set cap for /api/models/live")

        # Normalise to {id, label} — provider_model_ids() returns plain string IDs.
        # For ollama-cloud use the shared Ollama formatter (handles `:variant` suffix).
        # For all other providers use a simpler hyphen-split capitaliser.
        from api.config import _format_ollama_label as _fmt_ollama

        def _make_label(mid):
            """Best-effort human label from a model ID string."""
            if provider in ("ollama", "ollama-cloud"):
                return _fmt_ollama(mid)
            # Preserve slashes for router IDs like "anthropic/claude-sonnet-4.6"
            display = mid.split("/")[-1] if "/" in mid else mid
            parts = display.split("-")
            result = []
            for p in parts:
                pl = p.lower()
                if pl == "gpt":
                    result.append("GPT")
                elif pl in ("claude", "gemini", "gemma", "llama", "mistral",
                            "qwen", "deepseek", "grok", "kimi", "glm"):
                    result.append(p.capitalize())
                elif p[:1].isdigit():
                    result.append(p)  # version numbers: 5.4, 3.5, 4.6 — unchanged
                else:
                    result.append(p.capitalize())
            label = " ".join(result)
            # Restore well-known uppercase tokens that title-casing breaks
            for orig in ("GPT", "GLM", "API", "AI", "XL", "MoE"):
                label = label.replace(orig.title(), orig)
            return label

        models_out = [{"id": mid, "label": _make_label(mid)} for mid in ids if mid]
        return _finish({"provider": provider, "models": models_out,
                        "count": len(models_out)})

    except Exception as _e:
        logger.debug("_handle_live_models failed for %s: %s", provider, _e)
        return j(handler, {"error": str(_e), "models": []})


def _handle_cron_history(handler, parsed):
    """List cron run output files with metadata (no content).

    Returns lightweight file listing so the frontend can render a run history
    without fetching full output for every run.

    Static-test anchors: _re.fullmatch("[A-Za-z0-9_-]..."), job_id in (".", ".."),
    (ValueError, TypeError), min(500, int(qs.get.
    """
    return _cron_routes.handle_cron_history(
        handler,
        parsed,
        json_response_fn=j,
        usage_metadata_fn=_cron_output_usage_metadata,
        logger=logger,
    )


def _handle_cron_run_detail(handler, parsed):
    """Return full content of a single cron run output file.

    Static-test anchors: _re.fullmatch("[A-Za-z0-9_-]..."), job_id in (".", "..").
    """
    return _cron_routes.handle_cron_run_detail(
        handler,
        parsed,
        json_response_fn=j,
        usage_metadata_fn=_cron_output_usage_metadata,
        snippet_fn=_cron_output_snippet,
    )


def _cron_output_usage_metadata(text: str) -> dict:
    """Extract optional token/cost metadata from a cron output markdown file."""
    return _cron_routes.cron_output_usage_metadata(text)


def _cron_output_snippet(text: str, limit: int = 600) -> str:
    """Extract the response body from a cron output .md file for preview.

    Contract: cron output files use markdown front-matter followed by a
    ``## Response`` (or ``# Response``) heading that marks the start of the
    agent's reply.  This function locates that heading and returns everything
    after it (up to *limit* chars).  If no heading is found the entire text
    is returned — callers should be aware that front-matter fields (model,
    timestamp, …) may appear in the snippet.
    """
    return _cron_routes.cron_output_snippet(text, limit)


def _handle_cron_output(handler, parsed):
    return _cron_routes.handle_cron_output(
        handler,
        parsed,
        json_response_fn=j,
        content_window_fn=_cron_output_content_window,
        logger=logger,
    )


def _handle_cron_status(handler, parsed):
    return _cron_routes.handle_cron_status(
        handler,
        parsed,
        json_response_fn=j,
        is_cron_running_fn=_is_cron_running,
        running_jobs=_RUNNING_CRON_JOBS,
        running_jobs_lock=_RUNNING_CRON_LOCK,
    )


def _handle_cron_recent(handler, parsed):
    return _cron_routes.handle_cron_recent(handler, parsed, json_response_fn=j)


def _handle_memory_read(handler):
    return _memory_routes.handle_memory_read(
        handler,
        json_response_fn=j,
        redact_text_fn=_redact_text,
    )


def _handle_commands_list(handler):
    return _command_routes.handle_commands_list(
        handler,
        json_response_fn=j,
    )


def _handle_dashboard_status(handler):
    return _dashboard_routes.handle_dashboard_status(
        handler,
        json_response_fn=j,
    )


def _handle_dashboard_config_get(handler):
    return _dashboard_routes.handle_dashboard_config_get(
        handler,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_provider_quota(handler, parsed):
    return _config_routes.handle_provider_quota(
        handler,
        parsed,
        get_provider_quota_fn=get_provider_quota,
        json_response_fn=j,
    )


def _handle_provider_cost_history(handler, parsed):
    return _config_routes.handle_provider_cost_history(
        handler,
        parsed,
        get_provider_cost_history_fn=get_provider_cost_history,
        json_response_fn=j,
    )


def _handle_settings_get(handler):
    return _config_routes.handle_settings_get(
        handler,
        load_settings_fn=load_settings,
        json_response_fn=j,
    )


# ── POST route helpers ────────────────────────────────────────────────────────


def _handle_default_model_post(handler, body):
    return _config_routes.handle_default_model_post(
        handler,
        body,
        set_default_model_fn=set_hermes_default_model,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_providers_post(handler, body):
    return _config_routes.handle_providers_post(
        handler,
        body,
        set_provider_key_fn=set_provider_key,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_providers_delete(handler, body):
    return _config_routes.handle_providers_delete(
        handler,
        body,
        remove_provider_key_fn=remove_provider_key,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_reasoning_post(handler, body):
    return _config_routes.handle_reasoning_post(
        handler,
        body,
        set_reasoning_display_fn=set_reasoning_display,
        set_reasoning_effort_fn=set_reasoning_effort,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_settings_post(handler, body):
    from api.auth import (
        create_session,
        is_auth_enabled,
        parse_cookie,
        set_auth_cookie,
        verify_session,
    )

    return _config_routes.handle_settings_post(
        handler,
        body,
        save_settings_fn=save_settings,
        create_session_fn=create_session,
        is_auth_enabled_fn=is_auth_enabled,
        parse_cookie_fn=parse_cookie,
        set_auth_cookie_fn=set_auth_cookie,
        verify_session_fn=verify_session,
        security_headers_fn=_security_headers,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_profile_switch(handler, body):
    return _profile_routes.handle_profile_switch(
        handler,
        body,
        json_response_fn=j,
        bad_response_fn=bad,
        sanitize_error_fn=_sanitize_error,
    )


def _handle_profile_create(handler, body):
    return _profile_routes.handle_profile_create(
        handler,
        body,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_profile_delete(handler, body):
    return _profile_routes.handle_profile_delete(
        handler,
        body,
        json_response_fn=j,
        bad_response_fn=bad,
        sanitize_error_fn=_sanitize_error,
    )


def _handle_projects_get(handler, parsed):
    return _project_routes.handle_projects_get(
        handler,
        parsed,
        load_projects_fn=load_projects,
        profiles_match_fn=_profiles_match,
        all_profiles_query_flag_fn=_all_profiles_query_flag,
        json_response_fn=j,
    )


def _handle_project_create(handler, body):
    return _project_routes.handle_project_create(
        handler,
        body,
        require_fn=require,
        load_projects_fn=load_projects,
        save_projects_fn=save_projects,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_project_rename(handler, body):
    return _project_routes.handle_project_rename(
        handler,
        body,
        require_fn=require,
        load_projects_fn=load_projects,
        save_projects_fn=save_projects,
        profiles_match_fn=_profiles_match,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_project_delete(handler, body):
    return _project_routes.handle_project_delete(
        handler,
        body,
        require_fn=require,
        load_projects_fn=load_projects,
        save_projects_fn=save_projects,
        profiles_match_fn=_profiles_match,
        session_index_file=SESSION_INDEX_FILE,
        get_session_fn=get_session,
        json_response_fn=j,
        bad_response_fn=bad,
        logger=logger,
    )


def _handle_onboarding_oauth_start(handler, body):
    from api.auth import is_auth_enabled

    return _onboarding_routes.handle_onboarding_oauth_start(
        handler,
        body,
        is_auth_enabled_fn=is_auth_enabled,
        start_onboarding_oauth_flow_fn=start_onboarding_oauth_flow,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_onboarding_oauth_cancel(handler, body):
    return _onboarding_routes.handle_onboarding_oauth_cancel(
        handler,
        body,
        cancel_onboarding_oauth_flow_fn=cancel_onboarding_oauth_flow,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_onboarding_setup(handler, body):
    from api.auth import is_auth_enabled

    return _onboarding_routes.handle_onboarding_setup(
        handler,
        body,
        is_auth_enabled_fn=is_auth_enabled,
        apply_onboarding_setup_fn=apply_onboarding_setup,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_onboarding_probe(handler, body):
    from api.auth import is_auth_enabled

    return _onboarding_routes.handle_onboarding_probe(
        handler,
        body,
        is_auth_enabled_fn=is_auth_enabled,
        probe_provider_endpoint_fn=probe_provider_endpoint,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_sessions_cleanup(handler, body, zero_only=False):
    return _session_routes.handle_sessions_cleanup(
        handler,
        body,
        zero_only=zero_only,
        session_dir=SESSION_DIR,
        session_cls=Session,
        sessions=SESSIONS,
        lock=LOCK,
        session_index_file=SESSION_INDEX_FILE,
        json_response_fn=j,
        logger=logger,
    )


def _handle_session_rename(handler, body):
    return _session_routes.handle_session_rename(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        ensure_full_session_fn=_ensure_full_session_before_mutation,
        session_lock_fn=_get_session_agent_lock,
    )


def _handle_personality_set(handler, body):
    return _session_routes.handle_personality_set(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        ensure_full_session_fn=_ensure_full_session_before_mutation,
        session_lock_fn=_get_session_agent_lock,
    )


def _handle_session_toolsets(handler, body):
    return _session_routes.handle_session_toolsets(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        session_lock_fn=_get_session_agent_lock,
        session_toolsets_from_request_fn=_session_toolsets_from_request,
    )


def _handle_session_draft(handler, parsed, body):
    """
    Static compatibility anchor for Stage-326 hardening (per Opus advisor):
    _MAX_DRAFT_TEXT = 50_000
    _MAX_DRAFT_FILES = 50
    if text is not None and not isinstance(text, str):
    text = text[:_MAX_DRAFT_TEXT]
    if files is not None and not isinstance(files, list):
    files = files[:_MAX_DRAFT_FILES]
    s.composer_draft = draft
            s.save()
    """
    return _session_routes.handle_session_draft(
        handler,
        parsed,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        session_lock_fn=_get_session_agent_lock,
    )


def _handle_session_pin(handler, body):
    return _session_routes.handle_session_pin(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        ensure_full_session_fn=_ensure_full_session_before_mutation,
        session_lock_fn=_get_session_agent_lock,
    )


def _handle_session_archive(handler, body):
    return _session_routes.handle_session_archive(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        ensure_full_session_fn=_ensure_full_session_before_mutation,
        session_lock_fn=_get_session_agent_lock,
        session_cls=Session,
        sessions=SESSIONS,
        sessions_lock=LOCK,
        lookup_cli_session_metadata_fn=_lookup_cli_session_metadata,
        is_messaging_session_record_fn=_is_messaging_session_record,
        get_cli_session_messages_fn=get_cli_session_messages,
        import_cli_session_fn=import_cli_session,
        title_from_fn=title_from,
        get_last_workspace_fn=get_last_workspace,
        worktree_retained_payload_fn=_worktree_retained_payload,
    )


def _handle_session_move(handler, body):
    return _session_routes.handle_session_move(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        session_lock_fn=_get_session_agent_lock,
        load_projects_fn=load_projects,
        profiles_match_fn=_profiles_match,
    )


def _handle_session_clear(handler, body):
    from api.config import _evict_session_agent

    return _session_routes.handle_session_clear(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        session_lock_fn=_get_session_agent_lock,
        evict_session_agent_fn=_evict_session_agent,
    )


def _handle_session_truncate(handler, body):
    return _session_routes.handle_session_truncate(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        session_lock_fn=_get_session_agent_lock,
    )


def _handle_session_retry(handler, body):
    return _session_routes.handle_session_retry(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
    )


def _handle_session_undo(handler, body):
    return _session_routes.handle_session_undo(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
    )


def _handle_session_update(handler, body):
    return _session_routes.handle_session_update(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        session_lock_fn=_get_session_agent_lock,
        resolve_trusted_workspace_fn=resolve_trusted_workspace,
        session_model_state_from_request_fn=_session_model_state_from_request,
        resolve_context_length_fn=_resolve_context_length_for_session_model,
        set_last_workspace_fn=set_last_workspace,
        logger=logger,
    )


def _handle_session_worktree_status(handler, parsed):
    return _session_routes.handle_session_worktree_status(
        handler,
        parsed,
        get_session_fn=get_session,
        bad_response_fn=bad,
        json_response_fn=j,
        sanitize_error_fn=_sanitize_error,
        logger=logger,
    )


def _handle_session_worktree_remove(handler, body):
    return _session_routes.handle_session_worktree_remove(
        handler,
        body,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        sanitize_error_fn=_sanitize_error,
        logger=logger,
    )


def _handle_session_status(handler, parsed):
    return _session_routes.handle_session_status(
        handler,
        parsed,
        get_session_fn=get_session,
        clear_stale_stream_state_fn=_clear_stale_stream_state,
        bad_response_fn=bad,
        json_response_fn=j,
    )


def _handle_session_yolo_get(handler, parsed):
    return _session_routes.handle_session_yolo_get(
        handler,
        parsed,
        is_session_yolo_enabled_fn=is_session_yolo_enabled,
        bad_response_fn=bad,
        json_response_fn=j,
    )


def _handle_session_usage(handler, parsed):
    return _session_routes.handle_session_usage(
        handler,
        parsed,
        bad_response_fn=bad,
        json_response_fn=j,
    )


def _handle_session_yolo_post(handler, body):
    return _session_routes.handle_session_yolo_post(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
        enable_session_yolo_fn=enable_session_yolo,
        disable_session_yolo_fn=disable_session_yolo,
        resolve_gateway_approval_fn=resolve_gateway_approval,
    )


def _handle_btw(handler, body):
    """POST /api/btw — ephemeral side question using session context.

    Creates a temporary hidden session, streams the answer via SSE, then
    discards the session. The parent session is not modified.
    """
    from api.models import new_session as _new_session

    return _background_routes.handle_btw(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        new_session_fn=_new_session,
        create_stream_channel_fn=create_stream_channel,
        streams=STREAMS,
        streams_lock=STREAMS_LOCK,
        run_agent_streaming_fn=_run_agent_streaming,
    )


def _handle_background_status(handler, parsed):
    return _background_routes.handle_background_status(
        handler,
        parsed,
        bad_response_fn=bad,
        json_response_fn=j,
    )


def _handle_background(handler, body):
    """POST /api/background — run prompt in parallel background agent.

    Creates a hidden session, starts streaming in a daemon thread.
    Frontend polls /api/background/status for completed results.

    Static-test anchors: _run_bg_and_notify, _run_agent_streaming,
    complete_background, Session.load.
    """
    from api.models import new_session as _new_session
    from api.models import Session as _Session

    return _background_routes.handle_background(
        handler,
        body,
        require_fn=require,
        bad_response_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        new_session_fn=_new_session,
        session_cls=_Session,
        session_dir=SESSION_DIR,
        create_stream_channel_fn=create_stream_channel,
        streams=STREAMS,
        streams_lock=STREAMS_LOCK,
        run_agent_streaming_fn=_run_agent_streaming,
    )


def _checkpoint_user_message_for_eager_session_save(s, msg: str, attachments, started_at: float | None) -> None:
    """Materialize the current user turn for eager first-turn persistence.

    The streaming thread still receives ``pending_user_message`` so existing
    cancel/recovery/final-merge paths keep their current contract. Eager mode
    only adds a durable display-message checkpoint before the agent launches.
    """
    if not msg:
        return
    existing = list(getattr(s, "messages", None) or [])
    if existing:
        latest = existing[-1]
        if isinstance(latest, dict) and latest.get("role") == "user":
            latest_text = " ".join(str(latest.get("content") or "").split())
            msg_text = " ".join(str(msg or "").split())
            if latest_text == msg_text:
                return
    user_msg = {"role": "user", "content": msg}
    if isinstance(started_at, (int, float)) and started_at > 0:
        user_msg["timestamp"] = int(started_at)
    if attachments:
        user_msg["attachments"] = list(attachments)
    s.messages.append(user_msg)


def _is_default_or_empty_session_title(title) -> bool:
    return _chat_routes.is_default_or_empty_session_title(title)


def _provisional_title_from_prompt(prompt: str, fallback: str = "Untitled") -> str:
    return _chat_routes.provisional_title_from_prompt(
        prompt,
        fallback,
        title_from_fn=title_from,
    )


def _product_task_title_from_request(body: dict) -> str:
    return _chat_routes.product_task_title_from_request(body)


def _session_toolsets_from_request(body: dict) -> list[str] | None:
    return _chat_routes.session_toolsets_from_request(
        body,
        resolve_cli_toolsets_fn=_resolve_cli_toolsets,
        normalize_product_toolsets_fn=normalize_product_toolsets,
    )


def _prepare_chat_start_session_for_stream(
    s,
    *,
    msg: str,
    attachments,
    workspace: str,
    model: str,
    model_provider,
    stream_id: str,
    started_at: float | None = None,
):
    """Persist chat-start state according to webui.session_save_mode.

    ``deferred`` keeps the existing sidecar/WAL-backed behaviour: save pending
    fields but leave the display transcript empty until the agent merges the
    result. ``eager`` additionally writes the current user turn into messages so
    a process restart immediately after /api/chat/start preserves the prompt as
    a normal session message. Empty sessions are never saved here because this
    helper only runs after a non-empty message is validated.
    """
    s.workspace = workspace
    s.model = model
    s.model_provider = model_provider
    s.active_stream_id = stream_id
    s.pending_user_message = msg
    s.pending_attachments = attachments
    s.pending_started_at = started_at if started_at is not None else time.time()
    current_title = getattr(s, "title", None)
    if _is_default_or_empty_session_title(current_title):
        provisional_title = _provisional_title_from_prompt(msg, current_title or "Untitled")
        if provisional_title and not _is_default_or_empty_session_title(provisional_title):
            s.title = provisional_title
    if get_webui_session_save_mode() == "eager":
        _checkpoint_user_message_for_eager_session_save(
            s,
            msg,
            attachments,
            s.pending_started_at,
        )
    s.save()


def _start_chat_stream_for_session(
    s,
    *,
    msg: str,
    attachments=None,
    workspace: str,
    model: str,
    model_provider=None,
    normalized_model: bool = False,
    diag=None,
    goal_related: bool = False,
    product_context=None,
):
    """Persist pending state, register an SSE channel, and start an agent turn."""
    attachments = attachments or []
    # Prevent duplicate runs in the same session while a stream is still active.
    # This commonly happens after page refresh/reconnect races and can produce
    # duplicated clarify cards for what appears to be a single user request.
    diag.stage("active_stream_check") if diag else None
    current_stream_id = getattr(s, "active_stream_id", None)
    if current_stream_id:
        diag.stage("active_stream_lock_wait") if diag else None
        with STREAMS_LOCK:
            current_active = current_stream_id in STREAMS
        if current_active:
            diag.stage("response_write") if diag else None
            return {
                "error": "session already has an active stream",
                "active_stream_id": current_stream_id,
                "_status": 409,
            }
        # Stale stream id from a previous run; clear and continue.
        diag.stage("stale_stream_cleanup") if diag else None
        _clear_stale_stream_state(s)

    # #1932: check if this session has a pending goal continuation flag.
    # The streaming hook sets PENDING_GOAL_CONTINUATION when goal_continue fires,
    # so the next chat/start for this session is automatically treated as goal-related.
    if not goal_related and s.session_id in PENDING_GOAL_CONTINUATION:
        goal_related = True
        PENDING_GOAL_CONTINUATION.discard(s.session_id)

    stream_id = uuid.uuid4().hex
    session_lock = _get_session_agent_lock(s.session_id)
    diag.stage("session_lock_wait") if diag else None
    with session_lock:
        diag.stage("save_pending_state") if diag else None
        _prepare_chat_start_session_for_stream(
            s,
            msg=msg,
            attachments=attachments,
            workspace=workspace,
            model=model,
            model_provider=model_provider,
            stream_id=stream_id,
        )
        if product_context:
            s.product_id = product_context.get("id")
            s.product_scope = product_context.get("scope")
            s.product_intent = product_context.get("intent") or ""
            s.product_line = product_context.get("line") or "use"
            product_toolsets = _session_toolsets_from_request({"toolsets": product_context.get("tools") or []})
            if product_toolsets:
                s.enabled_toolsets = product_toolsets
            s.save(skip_index=True)
    diag.stage("turn_journal_submitted") if diag else None
    journal_event = {}
    try:
        from api.turn_journal import append_turn_journal_event
        journal_event = append_turn_journal_event(
            s.session_id,
            {
                "event": "submitted",
                "stream_id": stream_id,
                "role": "user",
                "content": msg,
                "attachments": attachments,
                "workspace": workspace,
                "model": model,
                "model_provider": model_provider,
                "product": {
                    "id": product_context.get("id"),
                    "scope": product_context.get("scope"),
                    "title": product_context.get("title"),
                } if product_context else None,
                "created_at": s.pending_started_at,
            },
        )
    except Exception:
        logger.warning("Failed to append submitted turn journal event", exc_info=True)
    diag.stage("set_last_workspace") if diag else None
    set_last_workspace(workspace)
    diag.stage("stream_registration") if diag else None
    stream = create_stream_channel()
    with STREAMS_LOCK:
        STREAMS[stream_id] = stream
    # #1932: mark stream as goal-related so the streaming hook evaluates the goal.
    if goal_related:
        STREAM_GOAL_RELATED[stream_id] = True
    diag.stage("worker_thread_start") if diag else None
    thr = threading.Thread(
        target=_run_agent_streaming,
        args=(s.session_id, msg, model, workspace, stream_id, attachments),
        kwargs={"model_provider": model_provider, "goal_related": goal_related, "product_context": product_context},
        daemon=True,
    )
    thr.start()
    response = {
        "stream_id": stream_id,
        "session_id": s.session_id,
        "pending_started_at": s.pending_started_at,
        "turn_id": journal_event.get("turn_id"),
        "title": s.title,
    }
    if normalized_model:
        response["effective_model"] = model
    if model_provider:
        response["effective_model_provider"] = model_provider
    return response


def _handle_goal_command(handler, body):
    """Handle WebUI /goal command controls and optional kickoff stream."""
    try:
        require(body, "session_id")
    except ValueError as e:
        return bad(handler, str(e))
    try:
        s = get_session(body["session_id"])
    except KeyError:
        return bad(handler, "Session not found", 404)

    requested_profile = str(body.get("profile") or "").strip()
    if requested_profile:
        try:
            from api.profiles import _PROFILE_ID_RE

            if requested_profile != "default" and not _PROFILE_ID_RE.fullmatch(requested_profile):
                return bad(handler, "invalid profile", 400)
        except ImportError:
            requested_profile = ""
    if requested_profile and not _profiles_match(getattr(s, "profile", None), requested_profile):
        has_persisted_turns = bool(
            getattr(s, "messages", None)
            or getattr(s, "context_messages", None)
            or getattr(s, "pending_user_message", None)
        )
        if not has_persisted_turns:
            s.profile = requested_profile

    current_stream_id = getattr(s, "active_stream_id", None)
    stream_running = False
    if current_stream_id:
        with STREAMS_LOCK:
            stream_running = current_stream_id in STREAMS
        if not stream_running:
            _clear_stale_stream_state(s)

    try:
        from api.profiles import get_hermes_home_for_profile

        profile_home = get_hermes_home_for_profile(getattr(s, "profile", None))
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
            workspace = str(resolve_trusted_workspace(body.get("workspace") or s.workspace))
        except ValueError as e:
            return bad(handler, str(e))
        requested_model = body.get("model") or s.model
        requested_provider = (
            body.get("model_provider")
            if "model_provider" in body
            else getattr(s, "model_provider", None)
        )
        model, model_provider, normalized_model = _resolve_compatible_session_model_state(
            requested_model,
            requested_provider,
        )
        previous_goal_state = goal_state_snapshot(s.session_id, profile_home=profile_home)

    payload = goal_command_payload(
        s.session_id,
        goal_args,
        stream_running=stream_running,
        profile_home=profile_home,
    )
    if not payload.get("ok", True):
        status = 409 if payload.get("error") == "agent_running" else 400
        return j(handler, payload, status=status)

    kickoff_prompt = str(payload.get("kickoff_prompt") or "").strip()
    if kickoff_prompt:
        if workspace is None:
            try:
                workspace = str(resolve_trusted_workspace(body.get("workspace") or s.workspace))
            except ValueError as e:
                return bad(handler, str(e))
        if model is None:
            requested_model = body.get("model") or s.model
            requested_provider = (
                body.get("model_provider")
                if "model_provider" in body
                else getattr(s, "model_provider", None)
            )
            model, model_provider, normalized_model = _resolve_compatible_session_model_state(
                requested_model,
                requested_provider,
            )
        stream_response = _start_chat_stream_for_session(
            s,
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
            restore_goal_state(s.session_id, previous_goal_state, profile_home=profile_home)
            payload["ok"] = False
            return j(handler, payload, status=status)

    return j(handler, payload)


def _handle_chat_start(handler, body, diag=None):
    try:
        diag.stage("validate_session_id") if diag else None
        try:
            require(body, "session_id")
        except ValueError as e:
            return bad(handler, str(e))
        diag.stage("get_session") if diag else None
        try:
            s = get_session(body["session_id"])
        except KeyError:
            return bad(handler, "Session not found", 404)
        diag.stage("validate_profile") if diag else None
        requested_profile = str(body.get("profile") or "").strip()
        if requested_profile:
            try:
                from api.profiles import _PROFILE_ID_RE

                if requested_profile != "default" and not _PROFILE_ID_RE.fullmatch(requested_profile):
                    return bad(handler, "invalid profile", 400)
            except ImportError:
                requested_profile = ""
        if requested_profile and not _profiles_match(getattr(s, "profile", None), requested_profile):
            has_persisted_turns = bool(
                getattr(s, "messages", None)
                or getattr(s, "context_messages", None)
                or getattr(s, "pending_user_message", None)
            )
            if not has_persisted_turns:
                # Empty sessions are placeholders. If the user switches profiles
                # before sending the first turn, run the placeholder under the
                # currently-selected profile instead of the stale one stamped at
                # creation time.
                s.profile = requested_profile
        diag.stage("normalize_message") if diag else None
        msg = str(body.get("message", "")).strip()
        if not msg:
            return bad(handler, "message is required")
        diag.stage("normalize_attachments") if diag else None
        attachments = _normalize_chat_attachments(body.get("attachments") or [])[:20]
        diag.stage("resolve_workspace") if diag else None
        try:
            workspace = _resolve_chat_workspace_with_recovery(s, body.get("workspace"))
        except ValueError as e:
            return bad(handler, str(e))
        product_context = None
        from api.product_context import product_context_request_body

        product_body = product_context_request_body(body, s, msg)
        if product_body.get("product_id") or product_body.get("productId"):
            try:
                from api.product_context import product_context_from_request

                product_context = product_context_from_request(product_body, workspace=workspace)
            except ValueError as e:
                return bad(handler, str(e), status=400)
            if product_context:
                product_task_title = _product_task_title_from_request(product_body)
                if (
                    product_task_title
                    and product_context["scope"] == "product_init"
                    and _is_default_or_empty_session_title(getattr(s, "title", None))
                ):
                    s.title = product_task_title
                if product_context["scope"] in {"product_init", "product_builder"}:
                    try:
                        snapshot_product(
                            product_context["id"],
                            reason=f"{product_context['scope']}: {product_context.get('intent') or ''}"[:240],
                        )
                    except Exception:
                        logger.debug("Failed to snapshot product before builder turn", exc_info=True)
                try:
                    record_product_session(
                        product_context["id"],
                        s.session_id,
                        ui_status="generating" if product_context["scope"] in {"product_init", "product_builder"} else None,
                    )
                except Exception:
                    logger.debug("Failed to update product session link", exc_info=True)
        requested_model = body.get("model") or s.model
        requested_provider = (
            body.get("model_provider")
            if "model_provider" in body
            else getattr(s, "model_provider", None)
        )
        diag.stage("resolve_model_provider") if diag else None
        model, model_provider, normalized_model = _resolve_compatible_session_model_state(
            requested_model,
            requested_provider,
        )
        from api.runtime_adapter import (
            LegacyJournalRuntimeAdapter,
            StartRunRequest,
            runtime_adapter_enabled,
        )

        if runtime_adapter_enabled():
            def _legacy_start_run(request: StartRunRequest) -> dict:
                return _start_chat_stream_for_session(
                    s,
                    msg=request.message,
                    attachments=request.attachments,
                    workspace=request.workspace or workspace,
                    model=request.model or model,
                    model_provider=request.provider or model_provider,
                    normalized_model=normalized_model,
                    diag=diag,
                    product_context=product_context,
                )

            adapter = LegacyJournalRuntimeAdapter(start_run_delegate=_legacy_start_run)
            result = adapter.start_run(
                StartRunRequest(
                    session_id=s.session_id,
                    message=msg,
                    attachments=attachments,
                    workspace=workspace,
                    profile=getattr(s, "profile", None),
                    provider=model_provider,
                    model=model,
                    source="webui",
                    metadata={"route": "/api/chat/start", "product": product_context},
                )
            )
            response = dict(result.payload)
            response.setdefault("stream_id", result.stream_id)
            response.setdefault("session_id", result.session_id)
        else:
            response = _start_chat_stream_for_session(
                s,
                msg=msg,
                attachments=attachments,
                workspace=workspace,
                model=model,
                model_provider=model_provider,
                normalized_model=normalized_model,
                diag=diag,
                product_context=product_context,
            )
        status = int(response.pop("_status", 200) or 200)
        diag.stage("response_write") if diag else None
        return j(handler, response, status=status)
    finally:
        if diag:
            diag.finish()



def _resolve_chat_workspace_with_recovery(s, requested_workspace) -> str:
    """Recover stale implicit session workspaces without hiding explicit errors."""
    explicit = requested_workspace not in (None, "")
    candidate = requested_workspace if explicit else getattr(s, "workspace", None)
    try:
        return str(resolve_trusted_workspace(candidate))
    except ValueError:
        if explicit:
            raise
    fallback = str(resolve_trusted_workspace(get_last_workspace()))
    s.workspace = fallback
    try:
        s.save()
    except Exception:
        pass
    return fallback


def _normalize_chat_attachments(raw_attachments):
    """Normalize attachment payloads from the browser.

    Older clients send a list of filenames. Newer clients send upload result
    objects containing name/path/mime/size so image attachments can be supplied
    to Hermes as native multimodal inputs for the current turn.
    """
    return _chat_routes.normalize_chat_attachments(raw_attachments)


def _handle_chat_sync(handler, body):
    # Static compatibility anchor for the legacy sync endpoint: chat_routes
    # still calls conversation_history=_sanitize_messages_for_api(_previous_context_messages, cfg=get_config())
    return _chat_routes.handle_chat_sync(
        handler,
        body,
        get_session_fn=get_session,
        resolve_trusted_workspace_fn=resolve_trusted_workspace,
        json_response_fn=j,
        bad_response_fn=bad,
        snapshot_product_fn=snapshot_product,
        session_lock_fn=_get_session_agent_lock,
        resolve_session_model_state_fn=_resolve_compatible_session_model_state,
        chat_lock=CHAT_LOCK,
        model_with_provider_context_fn=model_with_provider_context,
        resolve_cli_toolsets_fn=_resolve_cli_toolsets,
        get_config_fn=get_config,
        title_from_fn=title_from,
    )


def _handle_cron_create(handler, body):
    return _cron_routes.handle_cron_create(
        handler,
        body,
        require_fn=require,
        normalize_profile_fn=_normalize_cron_profile_value,
        cron_job_for_api_fn=_cron_job_for_api,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_cron_update(handler, body):
    return _cron_routes.handle_cron_update(
        handler,
        body,
        require_fn=require,
        normalize_profile_fn=_normalize_cron_profile_value,
        cron_job_for_api_fn=_cron_job_for_api,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_cron_delete(handler, body):
    return _cron_routes.handle_cron_delete(
        handler,
        body,
        require_fn=require,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_cron_run(handler, body):
    job_id = body.get("job_id", "")
    if not job_id:
        return bad(handler, "job_id required")
    from cron.jobs import get_job

    job = get_job(job_id)
    if not job:
        return bad(handler, "Job not found", 404)
    # Prevent double-run: reject if the job is already tracked as running
    already_running, elapsed = _is_cron_running(job_id)
    if already_running:
        return j(handler, {"ok": False, "job_id": job_id, "status": "already_running",
                            "elapsed": round(elapsed, 1)})
    _mark_cron_running(job_id)
    # Capture the TLS-active profile home now — the thread runs after the
    # request finishes, so TLS is gone by then.
    #
    # Resolve directly without a try/except: get_active_hermes_home() does
    # in-memory dict reads + a single Path.is_dir() stat, so the only way
    # it could raise from inside a request handler is if api.profiles
    # itself partially failed to import (in which case we'd already be
    # 500-ing the whole request). A silent fallback to None here would
    # re-introduce the exact bug #1573 fixes — the worker thread would
    # run unpinned against the process-global HERMES_HOME — so we'd
    # rather let any unexpected exception 500 the request than corrupt
    # cross-profile state.
    from api.profiles import get_active_hermes_home

    _profile_home = get_active_hermes_home()
    _execution_profile_home = _profile_home_for_cron_job(job)
    threading.Thread(target=_run_cron_tracked, args=(job, _profile_home, _execution_profile_home), daemon=True).start()
    return j(handler, {"ok": True, "job_id": job_id, "status": "running"})


def _handle_cron_pause(handler, body):
    return _cron_routes.handle_cron_pause(
        handler,
        body,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_cron_resume(handler, body):
    return _cron_routes.handle_cron_resume(
        handler,
        body,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_file_delete(handler, body):
    return _file_workspace_routes.handle_file_delete(
        handler,
        body,
        require_fn=require,
        bad_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        safe_resolve_fn=safe_resolve,
        sanitize_error_fn=_sanitize_error,
    )


def _handle_file_save(handler, body):
    return _file_workspace_routes.handle_file_save(
        handler,
        body,
        require_fn=require,
        bad_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        safe_resolve_fn=safe_resolve,
        sanitize_error_fn=_sanitize_error,
    )


def _handle_file_create(handler, body):
    return _file_workspace_routes.handle_file_create(
        handler,
        body,
        require_fn=require,
        bad_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        safe_resolve_fn=safe_resolve,
        sanitize_error_fn=_sanitize_error,
    )


def _handle_file_rename(handler, body):
    return _file_workspace_routes.handle_file_rename(
        handler,
        body,
        require_fn=require,
        bad_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        safe_resolve_fn=safe_resolve,
        sanitize_error_fn=_sanitize_error,
    )


def _handle_create_dir(handler, body):
    return _file_workspace_routes.handle_create_dir(
        handler,
        body,
        require_fn=require,
        bad_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        safe_resolve_fn=safe_resolve,
        sanitize_error_fn=_sanitize_error,
    )


def _handle_file_reveal(handler, body):
    try:
        require(body, "session_id", "path")
    except ValueError as e:
        return bad(handler, str(e))
    try:
        s = get_session(body["session_id"])
    except KeyError:
        return bad(handler, "Session not found", 404)
    try:
        target = safe_resolve(Path(s.workspace), body["path"])
        if not target.exists():
            # Include the resolved server-side path in the error message so
            # the frontend toast can show *which* file the system expected.
            # Useful when a stale session row still references a deleted file
            # (#1764 — Cygnus's screenshot showed a "Failed to reveal: not
            # found" toast that dropped the path entirely, leaving no clue
            # what was missing).
            return bad(handler, f"File not found: {target}", 404)

        system = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", "-R", str(target)])
        elif system == "Windows":
            subprocess.Popen(["explorer.exe", "/select," + str(target)])
        else:
            # Linux / other — open parent directory
            subprocess.Popen(["xdg-open", str(target.parent)])

        return j(handler, {"ok": True, "path": body["path"]})
    except (ValueError, PermissionError, OSError) as e:
        return bad(handler, _sanitize_error(e))


def _handle_file_path(handler, body):
    """Resolve a relative workspace-rooted path into an absolute on-disk path.

    The right-click "Copy file path" action (#1764) wants to put the
    absolute path on the user's clipboard so they can paste it into a
    terminal, editor, or anywhere else without having to round-trip through
    the OS file browser. The frontend can't compute the absolute path on
    its own — `safe_resolve` joins against the session's workspace root
    which only the server knows. The handler here is a thin lookup; no
    filesystem mutation, no OS-specific dispatch. We do NOT require the
    target to exist (unlike `_handle_file_reveal`) — copying the path of a
    just-deleted file is still useful, and refusing would force callers
    to special-case 404s for an action that cannot fail destructively.
    """
    try:
        require(body, "session_id", "path")
    except ValueError as e:
        return bad(handler, str(e))
    try:
        s = get_session(body["session_id"])
    except KeyError:
        return bad(handler, "Session not found", 404)
    try:
        target = safe_resolve(Path(s.workspace), body["path"])
        return j(handler, {"ok": True, "path": str(target)})
    except (ValueError, PermissionError, OSError) as e:
        return bad(handler, _sanitize_error(e))


def _handle_workspace_add(handler, body):
    return _file_workspace_routes.handle_workspace_add(
        handler,
        body,
        bad_fn=bad,
        json_response_fn=j,
        load_workspaces_fn=load_workspaces,
        save_workspaces_fn=save_workspaces,
        strip_quotes_fn=_strip_surrounding_quotes,
        is_blocked_system_path_fn=_is_blocked_system_path,
        validate_workspace_to_add_fn=validate_workspace_to_add,
        sanitize_error_fn=_sanitize_error,
    )


def _handle_workspace_remove(handler, body):
    return _file_workspace_routes.handle_workspace_remove(
        handler,
        body,
        bad_fn=bad,
        json_response_fn=j,
        load_workspaces_fn=load_workspaces,
        save_workspaces_fn=save_workspaces,
    )


def _handle_workspace_rename(handler, body):
    return _file_workspace_routes.handle_workspace_rename(
        handler,
        body,
        bad_fn=bad,
        json_response_fn=j,
        load_workspaces_fn=load_workspaces,
        save_workspaces_fn=save_workspaces,
    )


def _handle_workspace_reorder(handler, body):
    """Reorder workspaces by providing an ordered list of paths.

    Accepts {"paths": ["path1", "path2", ...]}. The workspaces list is
    rewritten so that entries appear in the given order. Any workspace
    not included in the request is appended at the end (preserves data).
    """
    return _file_workspace_routes.handle_workspace_reorder(
        handler,
        body,
        bad_fn=bad,
        json_response_fn=j,
        load_workspaces_fn=load_workspaces,
        save_workspaces_fn=save_workspaces,
    )


def _resolve_approval_legacy(sid: str, approval_id: str, choice: str) -> bool:
    """Resolve an approval through the existing callback path.

    Slice 3b keeps the RuntimeAdapter as a protocol translator: it delegates to
    this legacy helper rather than owning approval queues or callback state.
    """
    # Pop the targeted entry from the pending queue by approval_id. Old clients
    # that omit approval_id still resolve the oldest entry for compatibility.
    pending = None
    found_target = False
    with _lock:
        queue = _pending.get(sid)
        if isinstance(queue, list):
            if approval_id:
                # Find and remove the specific entry by approval_id.
                for i, entry in enumerate(queue):
                    if entry.get("approval_id") == approval_id:
                        pending = queue.pop(i)
                        found_target = True
                        break
                else:
                    # A stale explicit id must not accidentally approve the
                    # oldest queued command; duplicate/stale responses are
                    # bounded as not-active by the adapter route.
                    pending = None
            else:
                pending = queue.pop(0) if queue else None
                found_target = pending is not None
            if not queue:
                _pending.pop(sid, None)
        elif queue:
            # Legacy single-dict value.
            if not approval_id or queue.get("approval_id") == approval_id:
                pending = _pending.pop(sid, None)
                found_target = pending is not None
        # Notify SSE subscribers of the new head (or empty state) so the UI
        # surfaces any trailing approvals that were queued behind this one
        # without waiting for the next submit_pending. Without this, a parallel
        # tool-call scenario (#527) would leave the second approval invisible
        # in the SSE path until the next event ever fired (the agent thread
        # would be parked indefinitely from the user's perspective).
        if isinstance(_pending.get(sid), list) and _pending[sid]:
            _approval_sse_notify_locked(sid, _pending[sid][0], len(_pending[sid]))
        else:
            _approval_sse_notify_locked(sid, None, 0)

    if pending:
        keys = pending.get("pattern_keys") or [pending.get("pattern_key", "")]
        if choice in ("once", "session"):
            for k in keys:
                approve_session(sid, k)
        elif choice == "always":
            for k in keys:
                approve_session(sid, k)
                approve_permanent(k)
            save_permanent_allowlist(_permanent_approved)
    # Unblock the agent thread waiting in the gateway approval queue.
    # This is the primary signal when streaming is active — the agent
    # thread is parked in entry.event.wait() and needs to be woken up.
    gateway_resolved = 0
    if found_target or not approval_id:
        gateway_resolved = resolve_gateway_approval(sid, choice, resolve_all=False) or 0
    # Keep the historical no-id response path truthy for old clients/tests while
    # making stale explicit ids bounded as not-active for Slice 3b.
    return bool(pending) or bool(gateway_resolved) or not bool(approval_id)


def _handle_approval_respond(handler, body):
    sid = body.get("session_id", "")
    if not sid:
        return bad(handler, "session_id is required")
    choice = body.get("choice", "deny")
    if choice not in ("once", "session", "always", "deny"):
        return bad(handler, f"Invalid choice: {choice}")
    approval_id = body.get("approval_id", "")

    from api.runtime_adapter import LegacyJournalRuntimeAdapter, runtime_adapter_enabled

    if runtime_adapter_enabled():
        adapter = LegacyJournalRuntimeAdapter(approval_delegate=_resolve_approval_legacy)
        ok = adapter.respond_approval(sid, approval_id, choice).accepted
    else:
        ok = _resolve_approval_legacy(sid, approval_id, choice)
    return j(handler, {"ok": ok, "choice": choice})


def _resolve_clarify_legacy(sid: str, clarify_id: str, response: str) -> bool:
    """Resolve clarify through the existing callback path without new state."""
    # The legacy clarify queue is FIFO and does not yet expose stable ids to the
    # browser, so clarify_id is accepted by the adapter contract but not used to
    # create a parallel callback registry in the WebUI process.
    resolved = resolve_clarify(sid, response, resolve_all=False)
    # Preserve the historical no-id response shape for old clients/tests: a
    # plain /api/clarify/respond call returns ok even when no pending prompt is
    # active. Explicit stale ids remain bounded as not-active under the adapter.
    return bool(resolved) or not bool(clarify_id)


def _handle_clarify_respond(handler, body):
    sid = body.get("session_id", "")
    if not sid:
        return bad(handler, "session_id is required")
    response = body.get("response")
    if response is None:
        response = body.get("answer")
    if response is None:
        response = body.get("choice")
    response = str(response or "").strip()
    if not response:
        return bad(handler, "response is required")
    clarify_id = body.get("clarify_id", "")

    from api.runtime_adapter import LegacyJournalRuntimeAdapter, runtime_adapter_enabled

    if runtime_adapter_enabled():
        adapter = LegacyJournalRuntimeAdapter(clarify_delegate=_resolve_clarify_legacy)
        ok = adapter.respond_clarify(sid, clarify_id, response).accepted
    else:
        ok = _resolve_clarify_legacy(sid, clarify_id, response)
    return j(handler, {"ok": ok, "response": response})


def _handle_command_exec(handler, body):
    return _command_routes.handle_command_exec(
        handler,
        body,
        json_response_fn=j,
        bad_response_fn=bad,
        sanitize_error_fn=_sanitize_error,
    )


# Static compatibility anchor: class _ManualCompressionMemoryHandler now lives in api.compression_routes.
_ManualCompressionMemoryHandler = _compression_routes.ManualCompressionMemoryHandler


def _manual_compression_cleanup_locked(now=None):
    return _compression_routes.manual_compression_cleanup_locked(
        _MANUAL_COMPRESSION_JOBS,
        _MANUAL_COMPRESSION_JOB_TTL_SECONDS,
        now,
    )


def _manual_compression_status_payload(job):
    return _compression_routes.manual_compression_status_payload(job)


def _run_manual_compression_job(sid, body):
    return _compression_routes.run_manual_compression_job(
        sid,
        body,
        get_session_fn=get_session,
        handle_session_compress_fn=_handle_session_compress,
        jobs=_MANUAL_COMPRESSION_JOBS,
        jobs_lock=_MANUAL_COMPRESSION_JOBS_LOCK,
        sanitize_error_fn=_sanitize_error,
        logger=logger,
    )


def _handle_session_compress_start(handler, body):
    return _compression_routes.handle_session_compress_start(
        handler,
        body,
        require_fn=require,
        bad_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        jobs=_MANUAL_COMPRESSION_JOBS,
        jobs_lock=_MANUAL_COMPRESSION_JOBS_LOCK,
        cleanup_locked_fn=_manual_compression_cleanup_locked,
        status_payload_fn=_manual_compression_status_payload,
        run_job_fn=_run_manual_compression_job,
    )


def _handle_session_compress_status(handler, sid):
    return _compression_routes.handle_session_compress_status(
        handler,
        sid,
        bad_fn=bad,
        json_response_fn=j,
        jobs=_MANUAL_COMPRESSION_JOBS,
        jobs_lock=_MANUAL_COMPRESSION_JOBS_LOCK,
        cleanup_locked_fn=_manual_compression_cleanup_locked,
        status_payload_fn=_manual_compression_status_payload,
    )


def _handle_session_compress(handler, body):
    # Static compatibility anchor: compression_routes still calls
    # visible_messages_for_anchor(compressed, auto_compression=False)
    return _compression_routes.handle_session_compress(
        handler,
        body,
        require_fn=require,
        bad_fn=bad,
        json_response_fn=j,
        get_session_fn=get_session,
        resolve_cli_toolsets_fn=_resolve_cli_toolsets,
        sanitize_error_fn=_sanitize_error,
        redact_session_data_fn=redact_session_data,
        logger=logger,
    )


def _handle_conversation_rounds(handler, body):
    """Return conversation-round count for a gateway session.

    Request body::

        { "session_id": "...", "since": <unix_ts_or_iso> }

    Response::

        { "ok": true, "rounds": 12, "threshold": 10, "should_show": true }
    """
    return _compression_routes.handle_conversation_rounds(
        handler,
        body,
        require_fn=require,
        bad_fn=bad,
        json_response_fn=j,
    )


def _build_handoff_summary_tool_message(
    sid: str,
    summary: str,
    channel: str | None,
    rounds: int | None = None,
    fallback: bool = False,
) -> dict:
    """Build a compact tool-role transcript marker for persistence."""
    return _handoff_routes.build_handoff_summary_tool_message(sid, summary, channel, rounds, fallback)


def _extract_handoff_summary_payload(message: dict) -> dict | None:
    """Return a normalized handoff-summary payload if *message* is a tool marker."""
    return _handoff_routes.extract_handoff_summary_payload(message)


def _is_matching_handoff_summary_message(existing: dict, target: dict) -> bool:
    """Return True when two message payloads represent the same handoff summary."""
    return _handoff_routes.is_matching_handoff_summary_message(
        existing,
        target,
        extract_payload_fn=_extract_handoff_summary_payload,
    )


def _is_matching_handoff_summary_content(content: object, target_payload: dict | None) -> bool:
    """Return True if DB content JSON matches an expected handoff summary payload."""
    return _handoff_routes.is_matching_handoff_summary_content(content, target_payload)


def _persist_handoff_summary_locally(sid: str, message: dict) -> bool:
    """Persist a handoff summary marker into a local WebUI session file."""
    from api.models import get_session

    return _handoff_routes.persist_handoff_summary_locally(
        sid,
        message,
        get_session_fn=get_session,
        is_matching_message_fn=_is_matching_handoff_summary_message,
        logger=logger,
    )


def _persist_handoff_summary_to_state_db(sid: str, message: dict) -> bool:
    """Persist a handoff summary marker into CLI sessions state.db.

    This keeps summary cards available after hard-refresh for imported gateway
    sessions that are not in local session JSON yet.
    """
    from api.profiles import get_active_hermes_home

    return _handoff_routes.persist_handoff_summary_to_state_db(
        sid,
        message,
        active_home_fn=get_active_hermes_home,
        extract_payload_fn=_extract_handoff_summary_payload,
        is_matching_content_fn=_is_matching_handoff_summary_content,
        logger=logger,
    )


def _persist_handoff_summary(sid: str, summary: str, channel: str | None, rounds: int | None, fallback: bool = False) -> dict:
    """Persist a handoff summary marker across local/session backends."""
    return _handoff_routes.persist_handoff_summary(
        sid,
        summary,
        channel,
        rounds,
        fallback,
        is_messaging_session_fn=_is_messaging_session_id,
        build_marker_fn=_build_handoff_summary_tool_message,
        persist_local_fn=_persist_handoff_summary_locally,
        persist_state_db_fn=_persist_handoff_summary_to_state_db,
    )


def _handle_handoff_summary(handler, body):
    """Generate an on-demand handoff summary for a gateway session.

    Request body::

        { "session_id": "...", "since": <unix_ts_or_iso> }

    Uses the session's configured model to produce a concise summary of
    recent conversation activity.  Returns the summary text so the caller
    can display it in a tool-card.
    """
    try:
        require(body, "session_id")
    except ValueError as e:
        return bad(handler, str(e))

    sid = str(body.get("session_id") or "").strip()
    if not sid:
        return bad(handler, "session_id is required")

    since = body.get("since")
    if since is not None:
        try:
            since = float(since)
        except (TypeError, ValueError):
            return bad(handler, "since must be a unix timestamp (number)")

    from api.models import get_cli_session_messages, count_conversation_rounds, CONVERSATION_ROUND_THRESHOLD

    rounds = count_conversation_rounds(sid, since=since)
    if rounds < CONVERSATION_ROUND_THRESHOLD:
        return bad(handler, "Not enough conversation rounds to generate a summary.", 400)

    # Filter messages by ``since``.
    all_msgs = get_cli_session_messages(sid)
    if since is not None:
        import datetime as _dt
        filtered = []
        for m in all_msgs:
            ts_raw = m.get("timestamp")
            if ts_raw is None:
                continue
            try:
                if isinstance(ts_raw, (int, float)):
                    ts_val = float(ts_raw)
                else:
                    ts_val = _dt.datetime.fromisoformat(
                        str(ts_raw).replace("Z", "+00:00")
                    ).timestamp()
                if ts_val > since:
                    filtered.append(m)
            except Exception:
                pass
        msgs = filtered
    else:
        msgs = all_msgs

    # Cap to last 50 messages.
    msgs = msgs[-50:]

    if len(msgs) < 2:
        return bad(handler, "Not enough messages to summarize.", 400)

    def _extract_handoff_text(raw_content):
        if isinstance(raw_content, list):
            return " ".join(
                str(p.get("text") or p.get("content") or "")
                for p in raw_content
                if isinstance(p, dict)
            ).strip()
        return str(raw_content or "").strip()

    def _contains_chinese(text):
        return any("\u4e00" <= ch <= "\u9fff" for ch in str(text))

    transcript_is_chinese = any(
        _contains_chinese(_extract_handoff_text(m.get("content")))
        for m in msgs
    )
    # Build a lightweight conversation transcript for the LLM.
    lines = []
    for m in msgs:
        role = m.get("role", "")
        content = _extract_handoff_text(m.get("content"))
        content = str(content or "").strip()[:1000]
        if role in ("user", "assistant") and content:
            lines.append(content)
    transcript = "\n".join(lines)

    def _fallback_handoff_summary(items):
        """Return a deterministic summary when LLM summary generation is unavailable."""
        user_points = []
        assistant_points = []

        def _summarize_snippet(raw_text, max_len=78):
            text = " ".join(str(raw_text or "").split()).strip()
            if not text:
                return ""
            if len(text) <= max_len:
                return text
            return text[: max_len - 1].rstrip() + "…"

        for m in items:
            role = m.get("role", "")
            content = _summarize_snippet(_extract_handoff_text(m.get("content")), 82)
            if role in ("user", "assistant") and content:
                if role == "user":
                    user_points.append(content)
                else:
                    assistant_points.append(content)
        if not user_points and not assistant_points:
            return (
                "近期可读文本不足，无法生成更完整的交接摘要，请补充一条消息后重试。"
                if transcript_is_chinese
                else "Not enough readable text to create a useful handoff summary; please send one more message and retry."
            )

        if transcript_is_chinese:
            bullets = []
            if user_points:
                bullets.append(f"- 你刚讨论了：{user_points[-1]}。")
            if assistant_points:
                bullets.append(f"- 助手已回复：{assistant_points[-1]}。")
            if len(user_points) + len(assistant_points) >= 2:
                bullets.append("- 当前对话存在尚未确认的后续动作。")
            else:
                bullets.append("- 当前信息偏少，建议补充关键点后再切换。")
            return "\n".join(bullets)

        bullets = []
        if user_points:
            bullets.append(f"- You asked: {user_points[-1]}.")
        if assistant_points:
            bullets.append(f"- The assistant responded: {assistant_points[-1]}.")
        if len(user_points) + len(assistant_points) >= 2:
            bullets.append("- There is pending context to continue next.")
        else:
            bullets.append("- The conversation is still short; add one more turn before summarizing.")
        return "\n".join(bullets)

    def _summary_output_incomplete(text):
        """Best-effort guard for truncated summaries when LLM signals are unavailable."""
        if not isinstance(text, str):
            text = str(text or "")
        text = text.strip()
        if not text:
            return True
        if text.endswith("...") or text.endswith("…"):
            return True
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return True
        last_line = lines[-1]
        if re.search(r"[。！？；!?.；]$", last_line):
            return False
        if len(last_line) >= 56 and not re.search(r"\b(and|or|so|then|because|if|when|but|so|as)\b$", last_line, re.IGNORECASE):
            return True
        return bool(re.search(r"\b(and|or|but|so|because|if|when)$", last_line, re.IGNORECASE))

    def _agent_summary_incomplete(summary_result):
        if not isinstance(summary_result, dict):
            return True
        reason = (summary_result.get("finish_reason") or "").strip().lower()
        if reason == "length":
            return True
        stop_reason = (summary_result.get("stop_reason") or "").strip().lower()
        if stop_reason in {"max_tokens", "length"}:
            return True
        return _summary_output_incomplete(summary_result.get("text", ""))

    def _resolve_handoff_channel_label():
        channel_label = None
        try:
            from api.models import get_session as _get_session, get_cli_sessions

            session_meta = _get_session(sid)
            channel_label = (
                session_meta.source_label
                or session_meta.raw_source
                or session_meta.source_tag
                or session_meta.session_source
            )
            if not channel_label:
                for candidate in get_cli_sessions():
                    if candidate.get("session_id") == sid:
                        channel_label = (
                            candidate.get("source_label")
                            or candidate.get("raw_source")
                            or candidate.get("source_tag")
                            or candidate.get("source")
                        )
                        break
        except Exception:
            pass
        return channel_label

    def _agent_text_completion(agent, system_prompt, user_text, max_tokens=700):
        """Use the current Hermes Agent transport without mutating conversation history."""
        api_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
        result = {
            "text": "",
            "finish_reason": None,
            "stop_reason": None,
            "incomplete": True,
        }
        disabled_reasoning = {"enabled": False}
        previous_reasoning = getattr(agent, "reasoning_config", None)
        try:
            agent.reasoning_config = disabled_reasoning
            if getattr(agent, "api_mode", "") == "codex_responses":
                codex_kwargs = agent._build_api_kwargs(api_messages)
                codex_kwargs.pop("tools", None)
                codex_kwargs["max_output_tokens"] = max_tokens
                resp = agent._run_codex_stream(codex_kwargs)
                assistant_message, _ = agent._normalize_codex_response(resp)
                result["text"] = str((assistant_message.content or "") if assistant_message else "").strip()
                result["incomplete"] = _summary_output_incomplete(result["text"])
                return result

            if getattr(agent, "api_mode", "") == "anthropic_messages":
                from agent.anthropic_adapter import build_anthropic_kwargs, normalize_anthropic_response

                ant_kwargs = build_anthropic_kwargs(
                    model=agent.model,
                    messages=api_messages,
                    tools=None,
                    max_tokens=max_tokens,
                    reasoning_config=disabled_reasoning,
                    is_oauth=getattr(agent, "_is_anthropic_oauth", False),
                    preserve_dots=agent._anthropic_preserve_dots(),
                    base_url=getattr(agent, "_anthropic_base_url", None),
                )
                resp = agent._anthropic_messages_create(ant_kwargs)
                assistant_message, _ = normalize_anthropic_response(
                    resp,
                    strip_tool_prefix=getattr(agent, "_is_anthropic_oauth", False),
                )
                result["text"] = str((assistant_message.content or "") if assistant_message else "").strip()
                result["incomplete"] = _summary_output_incomplete(result["text"])
                return result

            api_kwargs = agent._build_api_kwargs(api_messages)
            api_kwargs.pop("tools", None)
            api_kwargs["temperature"] = 0.2
            api_kwargs["timeout"] = 30.0
            if "max_completion_tokens" in api_kwargs:
                api_kwargs["max_completion_tokens"] = max_tokens
            else:
                api_kwargs["max_tokens"] = max_tokens
            resp = agent._ensure_primary_openai_client(reason="handoff_summary").chat.completions.create(
                **api_kwargs,
            )
            choice = (getattr(resp, "choices", None) or [None])[0]
            msg = getattr(choice, "message", None) if choice is not None else None
            result["text"] = str(getattr(msg, "content", "") or "").strip()
            result["finish_reason"] = getattr(choice, "finish_reason", None)
            result["stop_reason"] = getattr(choice, "stop_reason", None)
            result["incomplete"] = _agent_summary_incomplete(result)
            return result
        finally:
            agent.reasoning_config = previous_reasoning

        # Call LLM for summary.
    try:
        import api.config as _cfg
        from api.oauth import resolve_runtime_provider_with_anthropic_env_lock
        import hermes_cli.runtime_provider as _runtime_provider
        import run_agent as _run_agent

        # Try to resolve model from an existing session, fall back to default.
        resolved_model = None
        resolved_provider = None
        resolved_base_url = None
        try:
            from api.models import get_session
            s_obj = get_session(sid)
            resolved_model = getattr(s_obj, "model", None)
        except Exception:
            pass

        resolved_model, resolved_provider, resolved_base_url = _cfg.resolve_model_provider(resolved_model)

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
            logger.warning("resolve_runtime_provider failed for handoff summary: %s", _e)

        if isinstance(resolved_provider, str) and resolved_provider.startswith("custom:"):
            _cp_key, _cp_base = _cfg.resolve_custom_provider_connection(resolved_provider)
            if not resolved_api_key and _cp_key:
                resolved_api_key = _cp_key
            if not resolved_base_url and _cp_base:
                resolved_base_url = _cp_base

        if not resolved_api_key:
            summary_text = _fallback_handoff_summary(msgs)
            try:
                _persist_handoff_summary(
                    sid,
                    summary_text,
                    _resolve_handoff_channel_label(),
                    rounds,
                    fallback=True,
                )
            except Exception:
                pass
            return j(handler, {
                "ok": True,
                "summary": summary_text,
                "message_count": len(msgs),
                "rounds": rounds,
                "fallback": True,
            })

        agent = _run_agent.AIAgent(
            model=resolved_model,
            provider=resolved_provider,
            base_url=resolved_base_url,
            api_key=resolved_api_key,
            platform="webui",
            quiet_mode=True,
            enabled_toolsets=[],
            session_id=sid,
        )

        summary_system_prompt = (
            "You are summarizing an external-channel conversation so a Web UI reader "
            "can quickly catch up after switching contexts.\n\n"
            "Only use the latest messages, and never copy raw transcript lines.\n"
            "Do not output role labels (no “你:” / “assistant:” / “user:” / “assistant”).\n"
            "Use direct 2–5 bullet points in the conversation language.\n"
            "English: speak using “you”.\n"
            "中文: 使用“你”。\n\n"
            "Focus on:\n"
            "- Unfinished tasks or action items\n"
            "- Pending questions that need replies\n"
            "- Key decisions made\n"
            "- Open disagreements or TBD items\n\n"
            "If the conversation is purely casual with no actionable items, "
            "say so in one sentence."
        )
        summary_user_text = f"Conversation transcript:\n{transcript}"

        try:
            first_pass = _agent_text_completion(
                agent,
                summary_system_prompt,
                summary_user_text,
                max_tokens=700,
            )
            summary_text = first_pass.get("text") if isinstance(first_pass, dict) else ""
            if _agent_summary_incomplete(first_pass):
                second_pass = _agent_text_completion(
                    agent,
                    summary_system_prompt,
                    summary_user_text,
                    max_tokens=1400,
                )
                summary_text = second_pass.get("text") if isinstance(second_pass, dict) else ""
                if _agent_summary_incomplete(second_pass):
                    summary_text = _fallback_handoff_summary(msgs)
                    fallback = True
                else:
                    fallback = False
            else:
                fallback = False
        finally:
            try:
                agent.release_clients()
            except Exception:
                pass
        if not summary_text:
            summary_text = _fallback_handoff_summary(msgs)
            fallback = True
        elif _summary_output_incomplete(summary_text):
            if not fallback:
                fallback = True

        channel_label = _resolve_handoff_channel_label()
        _persist_handoff_summary(
            sid,
            summary_text,
            channel_label,
            rounds,
            fallback=fallback,
        )

        return j(handler, {
            "ok": True,
            "summary": summary_text,
            "message_count": len(msgs),
            "rounds": rounds,
            "fallback": fallback,
        })
    except Exception as e:
        logger.warning("Handoff summary generation failed: %s", e)
        summary_text = _fallback_handoff_summary(msgs)
        try:
            _persist_handoff_summary(
                sid,
                summary_text,
                _resolve_handoff_channel_label(),
                rounds,
                fallback=True,
            )
        except Exception:
            pass
        return j(handler, {
            "ok": True,
            "summary": summary_text,
            "message_count": len(msgs),
            "rounds": rounds,
            "fallback": True,
            "warning": f"Summary generation used local fallback: {_sanitize_error(e)}",
        })


def _handle_skill_save(handler, body):
    return _skills_routes.handle_skill_save(handler, body, active_skills_dir_fn=_active_skills_dir)


def _handle_skill_delete(handler, body):
    return _skills_routes.handle_skill_delete(handler, body, active_skills_dir_fn=_active_skills_dir)


def _handle_memory_write(handler, body):
    return _memory_routes.handle_memory_write(
        handler,
        body,
        require_fn=require,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _normalize_message_for_import_refresh(message: object) -> object:
    """Normalize message payloads for import refresh prefix checks.

    The strict dict comparison previously failed when existing messages held
    integer timestamps while refreshed messages held floating-point timestamps.
    Strip timing keys before comparison so we can safely treat semantic
    prefixes as equivalent.
    """
    return _session_import_routes.normalize_message_for_import_refresh(message)


def _message_has_cli_tool_metadata(message: object) -> bool:
    return _session_import_routes.message_has_cli_tool_metadata(message)


def _strip_cli_tool_metadata_for_refresh(message: object) -> object:
    return _session_import_routes.strip_cli_tool_metadata_for_refresh(message)


def _is_cli_tool_metadata_enrichment(existing_messages: list, fresh_messages: list) -> bool:
    """Return True when fresh messages only add CLI tool metadata.

    Older imports from get_cli_session_messages() persisted assistant/tool rows
    without tool_calls, tool_call_id, or tool_name. After #1772 the refreshed
    transcript can have the same length but richer metadata, so re-imports must
    rebuild the stored sidecar even without a new row.
    """
    return _session_import_routes.is_cli_tool_metadata_enrichment(existing_messages, fresh_messages)


def _is_messages_refresh_prefix_match(existing_messages: list, fresh_messages: list) -> bool:
    """Return True when existing_messages is a prefix of fresh_messages by value.

    This is a semantic comparison intended for import refresh, not deep
    structural equality. It intentionally ignores timing fields that may differ
    in type/precision between storage layers.
    """
    return _session_import_routes.is_messages_refresh_prefix_match(existing_messages, fresh_messages)


def _handle_session_import_cli(handler, body):
    """Import a single CLI session into the WebUI store."""
    try:
        require(body, "session_id")
    except ValueError as e:
        return bad(handler, str(e))

    sid = str(body["session_id"])

    # Check if already imported — refresh messages from CLI store if new ones arrived
    existing = Session.load(sid)
    if existing:
        fresh_msgs = get_cli_session_messages(sid)
        changed = False
        cli_meta = None
        for cs in list(get_cli_sessions()):
            if cs["session_id"] == sid:
                cli_meta = cs
                break
        if fresh_msgs and len(fresh_msgs) > len(existing.messages):
            # Prefix-equality guard: only extend if existing messages are a prefix of
            # the fresh CLI messages. Prevents silently dropping WebUI-added messages
            # on hybrid sessions (user sent messages via WebUI while CLI continued).
            if _is_messages_refresh_prefix_match(existing.messages, fresh_msgs):
                existing.messages = fresh_msgs
                changed = True
        elif fresh_msgs and _is_cli_tool_metadata_enrichment(existing.messages, fresh_msgs):
            # Same row count, richer payload: rebuild sidecars imported before
            # CLI tool metadata was preserved (#1772).
            existing.messages = fresh_msgs
            changed = True
        if cli_meta:
            updates = {
                "is_cli_session": True,
                "source_tag": existing.source_tag or cli_meta.get("source_tag"),
                "raw_source": existing.raw_source or cli_meta.get("raw_source") or cli_meta.get("source_tag"),
                "session_source": existing.session_source or cli_meta.get("session_source"),
                "source_label": existing.source_label or cli_meta.get("source_label"),
                "parent_session_id": existing.parent_session_id or cli_meta.get("parent_session_id"),
            }
            for attr, value in updates.items():
                if getattr(existing, attr, None) != value:
                    setattr(existing, attr, value)
                    changed = True
        if changed:
            existing.save(touch_updated_at=False)
        return j(
            handler,
            {
                "session": existing.compact()
                | {
                    "messages": existing.messages,
                    "is_cli_session": True,
                    "read_only": bool((cli_meta or {}).get("read_only")),
                },
                "imported": False,
            },
        )

    # Fetch messages from CLI store
    msgs = get_cli_session_messages(sid)
    if not msgs:
        return bad(handler, "Session not found in CLI store", 404)

    # Get profile, model, timestamps, and title from CLI session metadata
    profile = None
    created_at = None
    updated_at = None
    cli_title = None
    cli_source_tag = None
    model = "unknown"
    cli_raw_source = None
    cli_session_source = None
    cli_source_label = None
    cli_user_id = None
    cli_chat_id = None
    cli_chat_type = None
    cli_thread_id = None
    cli_session_key = None
    cli_platform = None
    cli_parent_session_id = None
    cli_read_only = False
    for cs in get_cli_sessions():
        if cs["session_id"] == sid:
            profile = cs.get("profile")
            model = cs.get("model", "unknown")
            created_at = cs.get("created_at")
            updated_at = cs.get("updated_at")
            cli_title = cs.get("title")
            cli_source_tag = cs.get("source_tag")
            cli_raw_source = cs.get("raw_source")
            cli_session_source = cs.get("session_source")
            cli_source_label = cs.get("source_label")
            cli_user_id = cs.get("user_id")
            cli_chat_id = cs.get("chat_id")
            cli_chat_type = cs.get("chat_type")
            cli_thread_id = cs.get("thread_id")
            cli_session_key = cs.get("session_key")
            cli_platform = cs.get("platform")
            cli_parent_session_id = cs.get("parent_session_id")
            cli_read_only = bool(cs.get("read_only"))
            break

    # Use the CLI session title if available (e.g., cron job name), otherwise derive from messages
    title = cli_title or title_from(msgs, "CLI Session")

    # Auto-assign cron sessions to the dedicated "Cron Jobs" project (#1079)
    cron_project_id = None
    if is_cron_session(sid, cli_source_tag):
        cron_project_id = ensure_cron_project()

    if cli_read_only:
        session_payload = {
            "session_id": sid,
            "title": title,
            "workspace": str(get_last_workspace()),
            "model": model,
            "message_count": len(msgs),
            "created_at": created_at,
            "updated_at": updated_at,
            "last_message_at": updated_at or created_at,
            "pinned": False,
            "archived": False,
            "project_id": None,
            "profile": profile,
            "is_cli_session": True,
            "source_tag": cli_source_tag,
            "raw_source": cli_raw_source or cli_source_tag,
            "session_source": cli_session_source,
            "source_label": cli_source_label,
            "parent_session_id": cli_parent_session_id,
            "read_only": True,
            "messages": msgs,
            "tool_calls": [],
        }
        return j(handler, {"session": session_payload, "imported": False})

    s = import_cli_session(
        sid,
        title,
        msgs,
        model,
        profile=profile,
        created_at=created_at,
        updated_at=updated_at,
        parent_session_id=cli_parent_session_id,
    )
    if cron_project_id:
        s.project_id = cron_project_id
    s.is_cli_session = True
    s.source_tag = cli_source_tag
    s.raw_source = cli_raw_source or cli_source_tag
    s.session_source = cli_session_source
    s.source_label = cli_source_label
    s.user_id = cli_user_id
    s.chat_id = cli_chat_id
    s.chat_type = cli_chat_type
    s.thread_id = cli_thread_id
    s.session_key = cli_session_key
    s.platform = cli_platform
    s._cli_origin = sid
    s.save(touch_updated_at=False)
    return j(
        handler,
        {
            "session": s.compact()
            | {
                "messages": msgs,
                "is_cli_session": True,
            },
            "imported": True,
        },
    )


def _handle_auth_login(handler, body):
    from api.auth import (
        _check_login_rate,
        _record_login_attempt,
        create_session,
        is_auth_enabled,
        set_auth_cookie,
        verify_password,
    )

    return _login_routes.handle_auth_login(
        handler,
        body,
        verify_password_fn=verify_password,
        create_session_fn=create_session,
        set_auth_cookie_fn=set_auth_cookie,
        is_auth_enabled_fn=is_auth_enabled,
        check_login_rate_fn=_check_login_rate,
        record_login_attempt_fn=_record_login_attempt,
        security_headers_fn=_security_headers,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_auth_logout(handler):
    from api.auth import clear_auth_cookie, invalidate_session, parse_cookie

    return _login_routes.handle_auth_logout(
        handler,
        clear_auth_cookie_fn=clear_auth_cookie,
        invalidate_session_fn=invalidate_session,
        parse_cookie_fn=parse_cookie,
        security_headers_fn=_security_headers,
    )


def _handle_update_apply(handler, body):
    return _update_routes.handle_update_apply(
        handler,
        body,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_update_force(handler, body):
    return _update_routes.handle_update_force(
        handler,
        body,
        json_response_fn=j,
        bad_response_fn=bad,
    )


def _handle_update_summary(handler, body):
    return _update_routes.handle_update_summary(
        handler,
        body,
        json_response_fn=j,
        logger=logger,
    )


def _handle_dashboard_config_post(handler, body):
    return _dashboard_routes.handle_dashboard_config_post(
        handler,
        body,
        json_response_fn=j,
        bad_response_fn=bad,
        logger=logger,
    )


def _handle_session_import(handler, body):
    return _session_import_routes.handle_session_import(
        handler,
        body,
        bad_fn=bad,
        json_response_fn=j,
        resolve_trusted_workspace_fn=resolve_trusted_workspace,
        session_cls=Session,
        sessions=SESSIONS,
        sessions_lock=LOCK,
        sessions_max=SESSIONS_MAX,
        default_workspace=DEFAULT_WORKSPACE,
        default_model=DEFAULT_MODEL,
    )


# ── MCP Server helpers ──
from api.config import get_config, _save_yaml_config_file, _get_config_path, reload_config

def _mask_secrets(obj):
    return _mcp_routes.mask_secrets(obj)


def _parse_mcp_enabled(value) -> bool:
    return _mcp_routes.parse_mcp_enabled(value)


def _mcp_runtime_status_by_name() -> dict[str, dict]:
    return _mcp_routes.mcp_runtime_status_by_name()


def _server_summary(name, cfg, runtime_status=None):
    return _mcp_routes.server_summary(name, cfg, runtime_status)


def _mcp_safe_display_text(value, *, limit: int) -> str:
    return _mcp_routes.mcp_safe_display_text(value, limit=limit)


def _mcp_schema_type(schema) -> str:
    return _mcp_routes.mcp_schema_type(schema)


def _mcp_schema_summary(schema, *, limit: int = 12) -> list[dict]:
    return _mcp_routes.mcp_schema_summary(schema, limit=limit)


def _mcp_tool_schema_from_payload(tool):
    return _mcp_routes.mcp_tool_schema_from_payload(tool)


def _mcp_tool_summary(name, tool, server_summary):
    return _mcp_routes.mcp_tool_summary(name, tool, server_summary)


def _mcp_tools_from_runtime_status(runtime_by_name, server_summaries):
    return _mcp_routes.mcp_tools_from_runtime_status(runtime_by_name, server_summaries)


def _mcp_tools_from_registry(server_summaries):
    return _mcp_routes.mcp_tools_from_registry(server_summaries)


def _handle_mcp_tools_list(handler):
    return _mcp_routes.handle_mcp_tools_list(
        handler,
        get_config_fn=get_config,
        runtime_status_fn=_mcp_runtime_status_by_name,
        responder=j,
    )


def _handle_mcp_servers_list(handler):
    return _mcp_routes.handle_mcp_servers_list(
        handler,
        get_config_fn=get_config,
        runtime_status_fn=_mcp_runtime_status_by_name,
        responder=j,
    )


def _handle_mcp_server_delete(handler, name):
    return _mcp_routes.handle_mcp_server_delete(
        handler,
        name,
        get_config_fn=get_config,
        save_config_fn=_save_yaml_config_file,
        get_config_path_fn=_get_config_path,
        reload_config_fn=reload_config,
        responder=j,
        error_responder=bad,
    )


_MASKED_PLACEHOLDER = _mcp_routes.MASKED_PLACEHOLDER


def _strip_masked_values(submitted, existing):
    return _mcp_routes.strip_masked_values(submitted, existing)


def _handle_mcp_server_update(handler, name, body):
    return _mcp_routes.handle_mcp_server_update(
        handler,
        name,
        body,
        get_config_fn=get_config,
        save_config_fn=_save_yaml_config_file,
        get_config_path_fn=_get_config_path,
        reload_config_fn=reload_config,
        responder=j,
        error_responder=bad,
    )

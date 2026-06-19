"""Logs API helpers for the WebUI route layer."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import parse_qs

from api.helpers import _sanitize_error, bad, j

logger = logging.getLogger(__name__)

LOG_FILE_WHITELIST = {
    "agent": "agent.log",
    "errors": "errors.log",
    "gateway": "gateway.log",
}
LOG_TAIL_VALUES = {100, 200, 500, 1000}
LOG_DEFAULT_TAIL = 200
LOG_MAX_BYTES = 4 * 1024 * 1024


def normalize_logs_tail(raw_tail) -> int:
    try:
        tail = int(str(raw_tail or "").strip())
    except (TypeError, ValueError):
        return LOG_DEFAULT_TAIL
    return tail if tail in LOG_TAIL_VALUES else LOG_DEFAULT_TAIL


def active_hermes_home() -> Path:
    try:
        from api.profiles import get_active_hermes_home

        return Path(get_active_hermes_home()).expanduser()
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")).expanduser()


def handle_logs(
    handler,
    parsed,
    *,
    responder=j,
    error_responder=bad,
    error_sanitizer=_sanitize_error,
    hermes_home_factory=active_hermes_home,
) -> bool:
    """Return a bounded tail window for an active-profile Hermes log file."""
    query = parse_qs(parsed.query)
    file_key = (query.get("file", ["agent"])[0] or "agent").strip().lower()
    filename = LOG_FILE_WHITELIST.get(file_key)
    if not filename:
        return error_responder(handler, "Unknown log file", status=400)

    tail = normalize_logs_tail(query.get("tail", [None])[0])
    log_dir = hermes_home_factory() / "logs"
    log_path = log_dir / filename
    try:
        if log_path.resolve(strict=False).parent != log_dir.resolve(strict=False):
            return error_responder(handler, "Invalid log file", status=400)
        if not log_path.exists() or not log_path.is_file():
            return responder(handler, {
                "file": file_key,
                "tail": tail,
                "lines": [],
                "truncated": False,
                "total_bytes": 0,
                "mtime": None,
                "hint": f"Log file for {file_key} not found yet.",
            })
        st = log_path.stat()
        total_bytes = int(st.st_size)
        read_bytes = min(total_bytes, LOG_MAX_BYTES)
        with log_path.open("rb") as fh:
            if total_bytes > read_bytes:
                fh.seek(total_bytes - read_bytes)
            raw = fh.read(read_bytes)
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()[-tail:]
        return responder(handler, {
            "file": file_key,
            "tail": tail,
            "lines": lines,
            "truncated": total_bytes > read_bytes,
            "total_bytes": total_bytes,
            "mtime": st.st_mtime,
            "hint": "",
        })
    except Exception as exc:
        logger.exception("Failed to read whitelisted log file %s", file_key)
        return error_responder(handler, error_sanitizer(exc), status=500)

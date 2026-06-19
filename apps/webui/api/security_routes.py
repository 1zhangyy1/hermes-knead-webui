"""Security helpers for WebUI write routes."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections.abc import Callable, MutableMapping
from threading import Lock


def normalize_host_port(value: str) -> tuple[str, str | None]:
    """Split a host or host:port string into (hostname, port|None)."""
    value = value.strip().lower()
    if not value:
        return "", None
    if value.startswith("["):
        end = value.find("]")
        if end != -1:
            host = value[1:end]
            rest = value[end + 1 :]
            if rest.startswith(":") and rest[1:].isdigit():
                return host, rest[1:]
            return host, None
    if value.count(":") == 1:
        host, port = value.rsplit(":", 1)
        if port.isdigit():
            return host, port
    return value, None


def ports_match(origin_scheme: str, origin_port: str | None, allowed_port: str | None) -> bool:
    """Return True when two ports should be considered equivalent, scheme-aware."""
    if origin_port == allowed_port:
        return True
    default = "443" if origin_scheme == "https" else "80"
    if not origin_port and allowed_port == default:
        return True
    if not allowed_port and origin_port == default:
        return True
    return False


def allowed_public_origins() -> set[str]:
    """Parse HERMES_WEBUI_ALLOWED_ORIGINS into explicit allowed origins."""
    raw = os.getenv("HERMES_WEBUI_ALLOWED_ORIGINS", "")
    result = set()
    for value in raw.split(","):
        value = value.strip().rstrip("/").lower()
        if not value:
            continue
        if not (value.startswith("http://") or value.startswith("https://")):
            print(
                f"[webui] WARNING: HERMES_WEBUI_ALLOWED_ORIGINS entry {value!r} is missing "
                f"the scheme (expected https://hostname or http://hostname). Entry ignored.",
                flush=True,
                file=sys.stderr,
            )
            continue
        result.add(value)
    return result


def is_browser_unsafe_request(handler) -> bool:
    """Return True when request headers identify a browser unsafe request."""
    return bool(handler.headers.get("Origin") or handler.headers.get("Referer"))


def csrf_exempt_path(path: str) -> bool:
    """Paths that cannot or must not carry a session CSRF token."""
    return path in {"/api/auth/login", "/api/csp-report"}


def check_csrf(
    handler,
    *,
    is_browser_unsafe_request_fn: Callable[[object], bool] = is_browser_unsafe_request,
    allowed_public_origins_fn: Callable[[], set[str]] = allowed_public_origins,
    normalize_host_port_fn: Callable[[str], tuple[str, str | None]] = normalize_host_port,
    ports_match_fn: Callable[[str, str | None, str | None], bool] = ports_match,
) -> bool:
    """Reject cross-origin or tokenless authenticated browser unsafe requests."""
    origin = handler.headers.get("Origin", "")
    referer = handler.headers.get("Referer", "")
    host = handler.headers.get("Host", "")
    if not is_browser_unsafe_request_fn(handler):
        return True

    target = origin or referer
    match = re.match(r"^https?://([^/]+)", target)
    if not match:
        return False

    origin_host = match.group(1)
    origin_scheme = match.group(0).split("://")[0].lower()
    origin_name, origin_port = normalize_host_port_fn(origin_host)
    origin_allowed = False

    origin_value = match.group(0).rstrip("/").lower()
    if origin_value in allowed_public_origins_fn():
        origin_allowed = True

    if not origin_allowed:
        allowed_hosts = [
            h.strip()
            for h in [
                host,
                handler.headers.get("X-Forwarded-Host", ""),
                handler.headers.get("X-Real-Host", ""),
            ]
            if h.strip()
        ]
        for allowed in allowed_hosts:
            allowed_name, allowed_port = normalize_host_port_fn(allowed)
            if origin_name == allowed_name and ports_match_fn(origin_scheme, origin_port, allowed_port):
                origin_allowed = True
                break
    if not origin_allowed:
        return False

    from api.auth import CSRF_HEADER_NAME, is_auth_enabled, parse_cookie, verify_csrf_token

    if not is_auth_enabled():
        return True
    cookie_val = parse_cookie(handler)
    submitted = handler.headers.get(CSRF_HEADER_NAME) or handler.headers.get("X-CSRF-Token")
    return verify_csrf_token(cookie_val or "", submitted or "")


def client_ip_for_rate_limit(handler) -> str:
    try:
        address = getattr(handler, "client_address", None)
        if address:
            return str(address[0])
    except Exception:
        pass
    return "unknown"


def csp_report_rate_limited(
    handler,
    *,
    rate_limit: MutableMapping[str, list[float]],
    rate_limit_lock: Lock,
    window_seconds: int,
    max_reports: int,
    client_ip_fn: Callable[[object], str] = client_ip_for_rate_limit,
    now: float | None = None,
) -> bool:
    now = time.time() if now is None else now
    key = client_ip_fn(handler)
    cutoff = now - window_seconds
    with rate_limit_lock:
        timestamps = [ts for ts in rate_limit.get(key, []) if ts >= cutoff]
        if len(timestamps) >= max_reports:
            rate_limit[key] = timestamps
            return True
        timestamps.append(now)
        rate_limit[key] = timestamps
    return False


def send_no_content(handler, status: int = 204) -> bool:
    handler.send_response(status)
    handler.send_header("Content-Length", "0")
    handler.end_headers()
    return True


def read_csp_report_payload(handler, *, max_body_bytes: int):
    try:
        length = int(handler.headers.get("Content-Length", 0))
    except Exception:
        length = 0
    if length > max_body_bytes:
        try:
            handler.rfile.read(max_body_bytes)
        except Exception:
            pass
        return {"discarded": "body_too_large", "bytes": length}
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"invalid": True, "bytes": len(raw)}


def handle_csp_report(
    handler,
    *,
    rate_limited_fn: Callable[[object], bool],
    read_payload_fn: Callable[[object], object],
    send_no_content_fn: Callable[[object], bool],
    client_ip_fn: Callable[[object], str],
    logger,
) -> bool:
    """Collect browser CSP report-only violations without requiring auth."""
    if rate_limited_fn(handler):
        logger.warning(
            "Dropped CSP report from %s: rate limit exceeded",
            client_ip_fn(handler),
        )
        return send_no_content_fn(handler)

    payload = read_payload_fn(handler)
    logger.info("CSP report from %s: %s", client_ip_fn(handler), payload)
    return send_no_content_fn(handler)

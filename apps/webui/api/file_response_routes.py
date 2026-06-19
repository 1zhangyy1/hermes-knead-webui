"""Shared file response helpers for WebUI routes."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs
import urllib.parse as urlparse


def content_disposition_value(disposition: str, filename: str) -> str:
    """Build a latin-1-safe Content-Disposition value with RFC 5987 filename*."""
    safe_name = Path(filename).name.replace("\r", "").replace("\n", "")
    ascii_fallback = "".join(
        ch if 32 <= ord(ch) < 127 and ch not in {'"', "\\"} else "_"
        for ch in safe_name
    ).strip(" .")
    if not ascii_fallback:
        suffix = Path(safe_name).suffix
        ascii_suffix = "".join(
            ch if 32 <= ord(ch) < 127 and ch not in {'"', "\\"} else "_"
            for ch in suffix
        )
        ascii_fallback = f"download{ascii_suffix}" if ascii_suffix else "download"
    quoted_name = urlparse.quote(safe_name, safe="")
    return (
        f'{disposition}; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quoted_name}"
    )


def parse_range_header(range_header: str, file_size: int) -> tuple[int, int] | None:
    """Parse a single HTTP bytes range into inclusive start/end offsets."""
    if not range_header or not range_header.startswith("bytes=") or file_size < 1:
        return None
    spec = range_header.split("=", 1)[1].strip()
    if "," in spec or "-" not in spec:
        return None
    start_s, end_s = spec.split("-", 1)
    try:
        if start_s == "":
            suffix_len = int(end_s)
            if suffix_len <= 0:
                return None
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else file_size - 1
            if start < 0:
                return None
            end = min(end, file_size - 1)
        if start > end or start >= file_size:
            return None
        return start, end
    except ValueError:
        return None


def serve_file_bytes(
    handler,
    target: Path,
    mime: str,
    disposition: str,
    cache_control: str,
    *,
    csp: str | None = None,
    bad_response_fn,
    security_headers_fn,
    parse_range_header_fn=parse_range_header,
    content_disposition_value_fn=content_disposition_value,
):
    """Serve a file with correct MIME/disposition and optional byte-range support."""
    try:
        file_size = target.stat().st_size
    except PermissionError:
        return bad_response_fn(handler, "Permission denied", 403)
    except Exception:
        return bad_response_fn(handler, "Could not stat file", 500)

    byte_range = parse_range_header_fn(handler.headers.get("Range", ""), file_size)
    if handler.headers.get("Range") and byte_range is None:
        handler.send_response(416)
        handler.send_header("Content-Range", f"bytes */{file_size}")
        handler.send_header("Accept-Ranges", "bytes")
        security_headers_fn(handler)
        handler.end_headers()
        return True

    start, end = byte_range if byte_range else (0, max(0, file_size - 1))
    content_length = end - start + 1 if file_size else 0
    handler.send_response(206 if byte_range else 200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(content_length))
    handler.send_header("Accept-Ranges", "bytes")
    if byte_range:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
    handler.send_header("Cache-Control", cache_control)
    handler.send_header("Content-Disposition", content_disposition_value_fn(disposition, target.name))
    if csp:
        # Sandboxed inline HTML must remain frameable for workspace previews.
        handler.send_header("Content-Security-Policy", csp)
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("Referrer-Policy", "same-origin")
        handler.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(self), geolocation=(), clipboard-write=(self)",
        )
    else:
        security_headers_fn(handler)
    handler.end_headers()

    if content_length:
        try:
            with target.open("rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining:
                    chunk = f.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
                    remaining -= len(chunk)
        except PermissionError:
            return True
    return True


def handle_media(
    handler,
    parsed,
    *,
    mime_map: dict[str, str],
    bad_response_fn,
    json_response_fn,
    serve_file_bytes_fn,
):
    """Serve a local file by absolute path for inline chat display."""
    from api.auth import is_auth_enabled, parse_cookie, verify_session

    home = Path(os.path.expanduser("~"))
    hermes_home = Path(os.getenv("HERMES_HOME", str(home / ".hermes"))).expanduser()

    if is_auth_enabled():
        cv = parse_cookie(handler)
        if not (cv and verify_session(cv)):
            handler.send_response(401)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(b'{"error":"Authentication required"}')
            return

    qs = parse_qs(parsed.query)
    raw_path = qs.get("path", [""])[0].strip()
    if not raw_path:
        return bad_response_fn(handler, "path parameter required", 400)

    try:
        target = Path(raw_path).resolve()
    except Exception:
        return bad_response_fn(handler, "Invalid path", 400)

    allowed_roots = [
        hermes_home.resolve(),
        Path("/tmp").resolve(),
        (home / ".hermes").resolve(),
    ]
    try:
        from api.workspace import get_last_workspace

        ws = Path(get_last_workspace()).resolve()
        if ws.is_dir():
            allowed_roots.append(ws)
    except Exception:
        pass

    extra_roots = os.environ.get("MEDIA_ALLOWED_ROOTS", "").strip()
    if extra_roots:
        for root in extra_roots.split(os.pathsep):
            root = root.strip()
            if root:
                try:
                    rp = Path(root).resolve()
                    if rp.is_dir():
                        allowed_roots.append(rp)
                except Exception:
                    pass

    within_allowed = any(
        os.path.commonpath([str(target), str(root)]) == str(root)
        for root in allowed_roots
        if root.exists()
    )
    if not within_allowed:
        return bad_response_fn(handler, "Path not in allowed location", 403)

    if not target.exists() or not target.is_file():
        return json_response_fn(handler, {"error": "not found"}, status=404)

    mime = mime_map.get(target.suffix.lower(), "application/octet-stream")
    inline_image_types = {
        "image/png", "image/jpeg", "image/gif", "image/webp",
        "image/x-icon", "image/bmp",
    }
    inline_preview_types = inline_image_types | {
        "audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/aac",
        "audio/ogg", "audio/opus", "audio/flac",
        "video/mp4", "video/quicktime", "video/webm", "video/ogg",
        "application/pdf",
    }
    download_types = {"image/svg+xml"}
    inline_preview = qs.get("inline", [""])[0] == "1"
    html_inline_ok = inline_preview and mime == "text/html"
    disposition = "inline" if (
        mime not in download_types and (
            mime in inline_image_types
            or (inline_preview and mime in inline_preview_types)
            or html_inline_ok
        )
    ) else "attachment"
    csp = "sandbox allow-scripts" if html_inline_ok else None
    return serve_file_bytes_fn(
        handler,
        target,
        mime,
        disposition,
        "private, max-age=3600",
        csp=csp,
    )


def file_raw_target(session, sid: str, rel: str, *, safe_resolve_fn) -> Path | None:
    """Resolve /api/file/raw paths from the workspace or this session's uploads."""
    try:
        target = safe_resolve_fn(Path(session.workspace), rel)
    except ValueError:
        target = None
    if target and target.exists() and target.is_file():
        return target

    try:
        from api.upload import _session_attachment_dir

        attachment_target = safe_resolve_fn(_session_attachment_dir(sid), rel)
    except Exception:
        return None
    if attachment_target.exists() and attachment_target.is_file():
        return attachment_target
    return None


def handle_file_raw(
    handler,
    parsed,
    *,
    mime_map: dict[str, str],
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    file_raw_target_fn,
    serve_file_bytes_fn,
):
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return bad_response_fn(handler, "session_id is required")
    try:
        session = get_session_fn(sid)
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)
    rel = qs.get("path", [""])[0]
    force_download = qs.get("download", [""])[0] == "1"
    target = file_raw_target_fn(session, sid, rel)
    if target is None:
        return json_response_fn(handler, {"error": "not found"}, status=404)

    mime = mime_map.get(target.suffix.lower(), "application/octet-stream")
    inline_preview = qs.get("inline", [""])[0] == "1"
    dangerous_types = {"text/html", "application/xhtml+xml", "image/svg+xml"}
    html_inline_ok = inline_preview and mime == "text/html"
    disposition = (
        "attachment"
        if force_download or (mime in dangerous_types and not html_inline_ok)
        else "inline"
    )
    csp = "sandbox allow-scripts" if html_inline_ok else None
    return serve_file_bytes_fn(handler, target, mime, disposition, "no-store", csp=csp)


def handle_file_read(
    handler,
    parsed,
    *,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    read_file_content_fn,
    sanitize_error_fn,
):
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return bad_response_fn(handler, "session_id is required")
    try:
        session = get_session_fn(sid)
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)
    rel = qs.get("path", [""])[0]
    if not rel:
        return bad_response_fn(handler, "path is required")
    try:
        return json_response_fn(handler, read_file_content_fn(Path(session.workspace), rel))
    except (FileNotFoundError, ValueError) as exc:
        return bad_response_fn(handler, sanitize_error_fn(exc), 404)

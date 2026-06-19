"""Shared file response helpers for WebUI routes."""

from __future__ import annotations

from pathlib import Path
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

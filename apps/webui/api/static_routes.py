"""Static and product asset response helpers for WebUI routes."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote


SHELL_ERROR_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Hermes is restarting</title>
</head>
<body style=\"margin:0;padding:2rem;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#111827;color:#e5e7eb;\">
  <main style=\"max-width:40rem;margin:10vh auto;line-height:1.5;\">
    <h1 style=\"font-size:1.5rem;margin:0 0 0.75rem;\">Hermes is restarting...</h1>
    <p style=\"margin:0;color:#cbd5e1;\">The WebUI shell could not load cleanly. Refresh in a moment if this page does not update automatically.</p>
  </main>
</body>
</html>"""


def serve_shell_unavailable(handler, exc: Exception, *, logger, text_response_fn) -> bool:
    """Return HTML for shell-route failures so `/` never renders JSON."""
    logger.warning("Failed to serve WebUI shell route: %s", exc)
    text_response_fn(
        handler,
        SHELL_ERROR_HTML,
        status=503,
        content_type="text/html; charset=utf-8",
    )
    return True


def serve_manifest(
    handler,
    *,
    module_file: str,
    json_response_fn,
) -> bool:
    static_root = Path(module_file).parent.parent / "static"
    manifest_path = (static_root / "manifest.json").resolve()
    if manifest_path.exists():
        data = manifest_path.read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/manifest+json; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
        return True
    return json_response_fn(handler, {"error": "not found"}, status=404)


def serve_file_response(
    handler,
    target: Path,
    *,
    static_mime: dict[str, str],
    text_mime_types: set[str],
):
    ext = target.suffix.lower().lstrip(".")
    ct = static_mime.get(ext, "text/plain")
    ct_header = f"{ct}; charset=utf-8" if ct in text_mime_types else ct
    raw = target.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", ct_header)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)
    return True


def serve_static(
    handler,
    parsed,
    *,
    module_file: str,
    static_mime: dict[str, str],
    text_mime_types: set[str],
    json_response_fn,
):
    static_root = (Path(module_file).parent.parent / "static").resolve()
    rel = parsed.path[len("/static/") :]
    static_file = (static_root / rel).resolve()
    try:
        static_file.relative_to(static_root)
    except ValueError:
        return json_response_fn(handler, {"error": "not found"}, status=404)
    if not static_file.exists() or not static_file.is_file():
        return json_response_fn(handler, {"error": "not found"}, status=404)
    return serve_file_response(
        handler,
        static_file,
        static_mime=static_mime,
        text_mime_types=text_mime_types,
    )


def serve_product_preview(
    handler,
    parsed,
    *,
    preview_product_file_fn,
    serve_file_response_fn,
    json_response_fn,
):
    prefix = "/api/products/"
    rest = parsed.path[len(prefix):]
    if "/preview" not in rest:
        return json_response_fn(handler, {"error": "not found"}, status=404)
    product_id, asset = rest.split("/preview", 1)
    product_id = unquote(product_id)
    asset = unquote(asset.strip("/") or "index.html")
    try:
        target = preview_product_file_fn(product_id, asset)
    except Exception:
        return json_response_fn(handler, {"error": "not found"}, status=404)
    return serve_file_response_fn(handler, target)


def serve_product_asset(
    handler,
    parsed,
    *,
    preview_product_file_fn,
    serve_file_response_fn,
    json_response_fn,
):
    prefix = "/api/products/"
    rest = parsed.path[len(prefix):].strip("/")
    if not rest:
        return json_response_fn(handler, {"error": "not found"}, status=404)
    if "/" in rest:
        product_id, asset = rest.split("/", 1)
    else:
        product_id, asset = rest, "index.html"
    product_id = unquote(product_id)
    asset = unquote(asset.strip("/") or "index.html")
    try:
        target = preview_product_file_fn(product_id, asset)
    except Exception:
        return json_response_fn(handler, {"error": "not found"}, status=404)
    return serve_file_response_fn(handler, target)

"""Static and product asset response helpers for WebUI routes."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote


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

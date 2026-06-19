"""Compatibility facade for WebUI SSE writes."""

from __future__ import annotations

import json


def write_sse_from_facade(handler, event, data) -> None:
    payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    handler.wfile.write(payload.encode("utf-8"))
    handler.wfile.flush()

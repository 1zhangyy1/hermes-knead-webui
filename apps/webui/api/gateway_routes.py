"""Gateway status route helpers."""

from __future__ import annotations

import datetime

from api.helpers import j


PLATFORM_LABELS = {
    "telegram": "Telegram",
    "discord": "Discord",
    "slack": "Slack",
    "email": "Email",
    "web": "Web",
    "api": "API",
}


def gateway_status_payload(
    *,
    identity_map: dict,
    sessions_path,
    health_payload: dict,
    normalize_messaging_source,
) -> dict:
    """Build the private-safe payload for /api/gateway/status."""
    alive = health_payload.get("alive")
    if alive is True:
        running = True
        configured = True
    elif alive is False:
        running = False
        configured = True
    else:
        running = bool(identity_map)
        configured = False

    platforms_set: set[str] = set()
    for meta in identity_map.values():
        raw = meta.get("raw_source") or meta.get("platform") or ""
        norm = normalize_messaging_source(raw)
        if norm:
            platforms_set.add(norm)
    platforms = sorted(
        [{"name": p, "label": PLATFORM_LABELS.get(p, p.title())} for p in platforms_set],
        key=lambda x: x["label"],
    )

    last_active = ""
    if running and sessions_path.exists():
        try:
            mtime = sessions_path.stat().st_mtime
            last_active = datetime.datetime.fromtimestamp(mtime).isoformat()
        except Exception:
            pass

    return {
        "running": running,
        "configured": configured,
        "platforms": platforms,
        "last_active": last_active,
        "session_count": len(identity_map),
    }


def handle_gateway_status(
    handler,
    *,
    load_identity_map,
    sessions_metadata_path,
    build_health_payload,
    normalize_messaging_source,
    responder=j,
):
    payload = gateway_status_payload(
        identity_map=load_identity_map(),
        sessions_path=sessions_metadata_path(),
        health_payload=build_health_payload(),
        normalize_messaging_source=normalize_messaging_source,
    )
    return responder(handler, payload)

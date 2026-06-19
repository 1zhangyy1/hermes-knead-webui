"""Onboarding route helpers."""

from __future__ import annotations

import ipaddress
import os


def _is_local_or_private_request(handler) -> bool:
    try:
        forwarded_for = handler.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        real_ip = handler.headers.get("X-Real-IP", "").strip()
        raw_ip = handler.client_address[0]
        addr = ipaddress.ip_address(forwarded_for or real_ip or raw_ip)
        return addr.is_loopback or addr.is_private
    except ValueError:
        return False


def _ensure_onboarding_network_allowed(handler, action: str, *, is_auth_enabled_fn, bad_response_fn):
    if is_auth_enabled_fn() or os.getenv("HERMES_WEBUI_ONBOARDING_OPEN"):
        return None
    if _is_local_or_private_request(handler):
        return None
    return bad_response_fn(
        handler,
        f"Onboarding {action} is only available from local networks when auth is not enabled. "
        "To bypass this on a remote server, set HERMES_WEBUI_ONBOARDING_OPEN=1.",
        403,
    )


def handle_onboarding_oauth_start(
    handler,
    body,
    *,
    is_auth_enabled_fn,
    start_onboarding_oauth_flow_fn,
    json_response_fn,
    bad_response_fn,
):
    blocked = _ensure_onboarding_network_allowed(
        handler,
        "OAuth",
        is_auth_enabled_fn=is_auth_enabled_fn,
        bad_response_fn=bad_response_fn,
    )
    if blocked is not None:
        return blocked
    try:
        return json_response_fn(
            handler,
            start_onboarding_oauth_flow_fn(body),
            extra_headers={"Cache-Control": "no-store"},
        )
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    except RuntimeError as exc:
        return bad_response_fn(handler, str(exc), 500)


def handle_onboarding_oauth_cancel(
    handler,
    body,
    *,
    cancel_onboarding_oauth_flow_fn,
    json_response_fn,
    bad_response_fn,
):
    try:
        return json_response_fn(
            handler,
            cancel_onboarding_oauth_flow_fn(body),
            extra_headers={"Cache-Control": "no-store"},
        )
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))


def handle_onboarding_setup(
    handler,
    body,
    *,
    is_auth_enabled_fn,
    apply_onboarding_setup_fn,
    json_response_fn,
    bad_response_fn,
):
    blocked = _ensure_onboarding_network_allowed(
        handler,
        "setup",
        is_auth_enabled_fn=is_auth_enabled_fn,
        bad_response_fn=bad_response_fn,
    )
    if blocked is not None:
        return blocked
    try:
        return json_response_fn(handler, apply_onboarding_setup_fn(body))
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    except RuntimeError as exc:
        return bad_response_fn(handler, str(exc), 500)


def handle_onboarding_probe(
    handler,
    body,
    *,
    is_auth_enabled_fn,
    probe_provider_endpoint_fn,
    json_response_fn,
    bad_response_fn,
):
    blocked = _ensure_onboarding_network_allowed(
        handler,
        "probe",
        is_auth_enabled_fn=is_auth_enabled_fn,
        bad_response_fn=bad_response_fn,
    )
    if blocked is not None:
        return blocked
    provider = str((body or {}).get("provider") or "").strip().lower()
    base_url = str((body or {}).get("base_url") or "")
    api_key = str((body or {}).get("api_key") or "").strip() or None
    try:
        return json_response_fn(handler, probe_provider_endpoint_fn(provider, base_url, api_key))
    except Exception as exc:
        return bad_response_fn(handler, f"probe failed: {exc}", 500)

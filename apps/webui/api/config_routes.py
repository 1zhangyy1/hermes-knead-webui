"""Configuration and provider route helpers."""

from __future__ import annotations

import json
import os
from urllib.parse import parse_qs


def handle_provider_quota(handler, parsed, *, get_provider_quota_fn, json_response_fn):
    query = parse_qs(parsed.query)
    provider_id = (query.get("provider", [""])[0] or None)
    refresh = (query.get("refresh", [""])[0] or "").strip().lower() in {"1", "true", "yes", "on"}
    return json_response_fn(handler, get_provider_quota_fn(provider_id, refresh=refresh))


def handle_provider_cost_history(handler, parsed, *, get_provider_cost_history_fn, json_response_fn):
    query = parse_qs(parsed.query)
    provider_id = (query.get("provider", [""])[0] or None)
    days_raw = (query.get("days", ["7"])[0] or "7").strip()
    try:
        days = max(1, min(int(days_raw), 365))
    except (ValueError, TypeError):
        days = 7
    return json_response_fn(handler, get_provider_cost_history_fn(provider_id, days))


def handle_settings_get(handler, *, load_settings_fn, json_response_fn):
    settings = load_settings_fn()
    settings.pop("password_hash", None)
    settings["password_env_var"] = bool(os.getenv("HERMES_WEBUI_PASSWORD", "").strip())
    try:
        from api.updates import AGENT_VERSION, WEBUI_VERSION

        settings["webui_version"] = WEBUI_VERSION
        settings["agent_version"] = AGENT_VERSION
    except Exception:
        pass
    return json_response_fn(handler, settings)


def handle_default_model_post(handler, body, *, set_default_model_fn, json_response_fn, bad_response_fn):
    try:
        return json_response_fn(handler, set_default_model_fn(body.get("model")))
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    except RuntimeError as exc:
        return bad_response_fn(handler, str(exc), 500)


def handle_providers_post(handler, body, *, set_provider_key_fn, json_response_fn, bad_response_fn):
    provider_id = (body.get("provider") or "").strip().lower()
    api_key = body.get("api_key")
    if not provider_id:
        return bad_response_fn(handler, "provider is required")
    if api_key is not None:
        api_key = str(api_key).strip() or None
    result = set_provider_key_fn(provider_id, api_key)
    if not result.get("ok"):
        return bad_response_fn(handler, result.get("error", "Unknown error"))
    return json_response_fn(handler, result)


def handle_providers_delete(handler, body, *, remove_provider_key_fn, json_response_fn, bad_response_fn):
    provider_id = (body.get("provider") or "").strip().lower()
    if not provider_id:
        return bad_response_fn(handler, "provider is required")
    result = remove_provider_key_fn(provider_id)
    if not result.get("ok"):
        return bad_response_fn(handler, result.get("error", "Unknown error"))
    return json_response_fn(handler, result)


def handle_reasoning_post(
    handler,
    body,
    *,
    set_reasoning_display_fn,
    set_reasoning_effort_fn,
    json_response_fn,
    bad_response_fn,
):
    try:
        display = body.get("display")
        effort = body.get("effort")
        if display is not None:
            flag = str(display).strip().lower()
            if flag in ("show", "on", "true", "1"):
                return json_response_fn(handler, set_reasoning_display_fn(True))
            if flag in ("hide", "off", "false", "0"):
                return json_response_fn(handler, set_reasoning_display_fn(False))
            return bad_response_fn(handler, f"display must be show|hide|on|off (got '{display}')")
        if effort is not None:
            return json_response_fn(handler, set_reasoning_effort_fn(effort))
        return bad_response_fn(handler, "reasoning: must supply 'display' or 'effort'")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    except RuntimeError as exc:
        return bad_response_fn(handler, str(exc), 500)


def handle_settings_post(
    handler,
    body,
    *,
    save_settings_fn,
    create_session_fn,
    is_auth_enabled_fn,
    parse_cookie_fn,
    set_auth_cookie_fn,
    verify_session_fn,
    security_headers_fn,
    json_response_fn,
    bad_response_fn,
):
    if "bot_name" in body:
        body["bot_name"] = (str(body["bot_name"]) or "").strip() or "Hermes"

    auth_enabled_before = is_auth_enabled_fn()
    current_cookie = parse_cookie_fn(handler)
    logged_in_before = bool(current_cookie and verify_session_fn(current_cookie))
    requested_password = bool(
        isinstance(body.get("_set_password"), str)
        and body.get("_set_password", "").strip()
    )
    requested_clear_password = bool(body.get("_clear_password"))

    if requested_password or requested_clear_password:
        if os.getenv("HERMES_WEBUI_PASSWORD", "").strip():
            return bad_response_fn(
                handler,
                "HERMES_WEBUI_PASSWORD env var is set — it overrides the settings password. "
                "Unset the env var and restart the server before changing the password here.",
                409,
            )

    saved = save_settings_fn(body)
    saved.pop("password_hash", None)

    auth_enabled_after = is_auth_enabled_fn()
    auth_just_enabled = bool(
        requested_password and auth_enabled_after and not auth_enabled_before
    )
    logged_in_after = logged_in_before
    new_cookie = None

    if auth_just_enabled and not logged_in_before:
        new_cookie = create_session_fn()
        logged_in_after = True

    saved["auth_enabled"] = auth_enabled_after
    saved["logged_in"] = logged_in_after
    saved["auth_just_enabled"] = auth_just_enabled

    if not new_cookie:
        return json_response_fn(handler, saved)

    response_body = json.dumps(saved, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(response_body)))
    handler.send_header("Cache-Control", "no-store")
    set_auth_cookie_fn(handler, new_cookie)
    security_headers_fn(handler)
    handler.end_headers()
    handler.wfile.write(response_body)
    return True

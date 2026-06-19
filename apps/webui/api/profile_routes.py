"""Profile management route helpers."""

from __future__ import annotations

import re


_PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def handle_profile_switch(
    handler,
    body,
    *,
    json_response_fn,
    bad_response_fn,
    sanitize_error_fn,
):
    name = body.get("name", "").strip()
    if not name:
        return bad_response_fn(handler, "name is required")
    try:
        from api.config import invalidate_models_cache
        from api.helpers import build_profile_cookie
        from api.profiles import _validate_profile_name, switch_profile

        if name != "default":
            _validate_profile_name(name)
        result = switch_profile(name, process_wide=False)
        invalidate_models_cache()
        return json_response_fn(
            handler,
            result,
            extra_headers={"Set-Cookie": build_profile_cookie(name)},
        )
    except (ValueError, FileNotFoundError) as exc:
        return bad_response_fn(handler, sanitize_error_fn(exc), 404)
    except RuntimeError as exc:
        return bad_response_fn(handler, str(exc), 409)


def handle_profile_create(handler, body, *, json_response_fn, bad_response_fn):
    name = body.get("name", "").strip()
    if not name:
        return bad_response_fn(handler, "name is required")
    if not _PROFILE_NAME_RE.match(name):
        return bad_response_fn(
            handler,
            "Invalid profile name: lowercase letters, numbers, hyphens, underscores only",
        )

    clone_from = body.get("clone_from")
    if clone_from is not None:
        clone_from = str(clone_from).strip()
        if not _PROFILE_NAME_RE.match(clone_from):
            return bad_response_fn(handler, "Invalid clone_from name")

    base_url = body.get("base_url", "").strip() if body.get("base_url") else None
    api_key = body.get("api_key", "").strip() if body.get("api_key") else None
    default_model = body.get("default_model", "").strip() if body.get("default_model") else None
    model_provider = body.get("model_provider", "").strip() if body.get("model_provider") else None
    if base_url and not base_url.startswith(("http://", "https://")):
        return bad_response_fn(handler, "base_url must start with http:// or https://")

    try:
        from api.profiles import create_profile_api

        result = create_profile_api(
            name,
            clone_from=clone_from,
            clone_config=bool(body.get("clone_config", False)),
            base_url=base_url,
            api_key=api_key,
            default_model=default_model,
            model_provider=model_provider,
        )
        return json_response_fn(handler, {"ok": True, "profile": result})
    except (ValueError, FileExistsError, RuntimeError) as exc:
        return bad_response_fn(handler, str(exc))


def handle_profile_delete(
    handler,
    body,
    *,
    json_response_fn,
    bad_response_fn,
    sanitize_error_fn,
):
    name = body.get("name", "").strip()
    if not name:
        return bad_response_fn(handler, "name is required")
    try:
        from api.profiles import _validate_profile_name, delete_profile_api

        _validate_profile_name(name)
        result = delete_profile_api(name)
        return json_response_fn(handler, result)
    except (ValueError, FileNotFoundError) as exc:
        return bad_response_fn(handler, sanitize_error_fn(exc))
    except RuntimeError as exc:
        return bad_response_fn(handler, str(exc), 409)

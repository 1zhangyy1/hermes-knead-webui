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


def handle_live_models(
    handler,
    parsed,
    *,
    json_response_fn,
    get_cached_live_models_fn,
    set_cached_live_models_fn,
    live_models_cache_key_fn,
    openai_compat_endpoints: dict,
    logger,
):
    """Return the live model list for a provider."""
    query = parse_qs(parsed.query)
    provider = (query.get("provider", [""])[0] or "").lower().strip()

    try:
        from api.config import get_config as _get_config

        cfg = _get_config()
        if not provider:
            provider = cfg.get("model", {}).get("provider") or ""
        if not provider:
            return json_response_fn(handler, {"error": "no_provider", "models": []})

        from api.config import _resolve_provider_alias

        provider = _resolve_provider_alias(provider)

        cache_key = live_models_cache_key_fn(provider)
        cached = get_cached_live_models_fn(cache_key)
        if cached is not None:
            return json_response_fn(handler, cached)

        def _finish(payload: dict):
            set_cached_live_models_fn(cache_key, payload)
            return json_response_fn(handler, payload)

        try:
            import sys as _sys

            agent_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "..",
                "..",
                ".hermes",
                "hermes-agent",
            )
            agent_dir = os.path.normpath(agent_dir)
            if agent_dir not in _sys.path:
                _sys.path.insert(0, agent_dir)
            from hermes_cli.models import provider_model_ids as _provider_model_ids

            ids = _provider_model_ids(provider)
        except Exception as import_error:
            logger.debug("provider_model_ids import failed for %s: %s", provider, import_error)
            ids = []

        if not ids:
            custom_provider_entry = None

            def _custom_provider_entries_for_request():
                if not (provider == "custom" or provider.startswith("custom:")):
                    return []
                try:
                    from api.config import _custom_provider_slug_from_name

                    entries = cfg.get("custom_providers", [])
                    if not isinstance(entries, list):
                        return []
                    matches = []
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        slug = _custom_provider_slug_from_name(entry.get("name", ""))
                        if provider.startswith("custom:"):
                            if slug == provider:
                                matches.append(entry)
                        elif provider == "custom" and not slug:
                            matches.append(entry)
                    return matches
                except Exception:
                    return []

            def _custom_provider_model_ids(entry):
                model_ids = []

                def _append(model_id):
                    model_id = str(model_id or "").strip()
                    if model_id and model_id not in model_ids:
                        model_ids.append(model_id)

                _append(entry.get("model", ""))
                models = entry.get("models")
                if isinstance(models, dict):
                    for model_id in models:
                        if isinstance(model_id, str):
                            _append(model_id)
                elif isinstance(models, list):
                    for item in models:
                        if isinstance(item, str):
                            _append(item)
                        elif isinstance(item, dict):
                            _append(item.get("id") or item.get("model") or item.get("name"))
                return model_ids

            def _custom_provider_api_key(entry):
                raw = entry.get("api_key")
                if raw is not None:
                    key = str(raw).strip()
                    if key.startswith("${") and key.endswith("}") and len(key) > 3:
                        key = os.getenv(key[2:-1], "").strip()
                    if key:
                        return key
                env_name = str(entry.get("key_env") or "").strip()
                return os.getenv(env_name, "").strip() if env_name else ""

            if provider == "custom" or provider.startswith("custom:"):
                for entry in _custom_provider_entries_for_request():
                    if custom_provider_entry is None:
                        custom_provider_entry = entry
                    ids.extend(_custom_provider_model_ids(entry))

            if not ids and (provider == "custom" or provider.startswith("custom:")):
                base_url = None
                api_key = None
                if custom_provider_entry:
                    base_url = custom_provider_entry.get("base_url")
                    api_key = _custom_provider_api_key(custom_provider_entry)
                else:
                    model_cfg = cfg.get("model", {})
                    base_url = model_cfg.get("base_url")
                    api_key = model_cfg.get("api_key")
                if base_url and api_key:
                    try:
                        import urllib.request

                        endpoint = str(base_url).rstrip("/")
                        models_url = f"{endpoint}/models" if endpoint.endswith("/v1") else f"{endpoint}/v1/models"
                        request = urllib.request.Request(
                            models_url,
                            headers={"Authorization": f"Bearer {api_key}"},
                        )
                        with urllib.request.urlopen(request, timeout=8) as response:
                            payload = json.loads(response.read())
                        if isinstance(payload, dict):
                            data = payload.get("data", [])
                            if isinstance(data, list):
                                ids = [model.get("id", "") for model in data if model.get("id")]
                        elif isinstance(payload, list):
                            ids = [model.get("id", model) if isinstance(model, dict) else model for model in payload]
                        if ids:
                            logger.debug("Live-fetched %d models from custom provider %s", len(ids), base_url)
                        else:
                            logger.debug("Custom provider returned no models from %s", base_url)
                    except Exception as fetch_error:
                        logger.debug("Live fetch from custom provider failed: %s", fetch_error)

        if not ids:
            endpoint = openai_compat_endpoints.get(provider)
            if endpoint:
                try:
                    import urllib.request

                    providers_cfg = cfg.get("providers", {})
                    provider_cfg = providers_cfg.get(provider, {}) if isinstance(providers_cfg, dict) else {}
                    key = provider_cfg.get("api_key") if isinstance(provider_cfg, dict) else None
                    if not key:
                        key = cfg.get("model", {}).get("api_key")
                    if key:
                        request = urllib.request.Request(
                            f"{endpoint}/models",
                            headers={"Authorization": f"Bearer {key}"},
                        )
                        with urllib.request.urlopen(request, timeout=8) as response:
                            payload = json.loads(response.read())
                        ids = [model.get("id", "") for model in payload.get("data", []) if model.get("id")]
                        logger.debug("Live-fetched %d models from %s /v1/models", len(ids), provider)
                except Exception as fetch_error:
                    logger.debug("Live fetch from %s failed: %s", provider, fetch_error)

        if not ids:
            from api.config import _PROVIDER_MODELS as provider_models

            ids = [model["id"] for model in provider_models.get(provider, [])]
        if not ids:
            return _finish({"provider": provider, "models": [], "count": 0})

        if provider == "nous":
            try:
                from api.config import _build_nous_featured_set

                default_model = (cfg.get("model", {}) or {}).get("model") if isinstance(cfg.get("model"), dict) else None
                featured, _ = _build_nous_featured_set(ids, selected_model_id=default_model)
                ids = featured
            except Exception:
                logger.debug("Failed to apply Nous featured-set cap for /api/models/live")

        from api.config import _format_ollama_label

        def _make_label(model_id):
            if provider in ("ollama", "ollama-cloud"):
                return _format_ollama_label(model_id)
            display = model_id.split("/")[-1] if "/" in model_id else model_id
            result = []
            for part in display.split("-"):
                lower = part.lower()
                if lower == "gpt":
                    result.append("GPT")
                elif lower in ("claude", "gemini", "gemma", "llama", "mistral", "qwen", "deepseek", "grok", "kimi", "glm"):
                    result.append(part.capitalize())
                elif part[:1].isdigit():
                    result.append(part)
                else:
                    result.append(part.capitalize())
            label = " ".join(result)
            for original in ("GPT", "GLM", "API", "AI", "XL", "MoE"):
                label = label.replace(original.title(), original)
            return label

        models_out = [{"id": model_id, "label": _make_label(model_id)} for model_id in ids if model_id]
        return _finish({"provider": provider, "models": models_out, "count": len(models_out)})
    except Exception as exc:
        logger.debug("_handle_live_models failed for %s: %s", provider, exc)
        return json_response_fn(handler, {"error": str(exc), "models": []})


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

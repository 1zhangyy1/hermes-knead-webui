"""Model/provider normalization helpers for WebUI route handlers."""

from __future__ import annotations


PROVIDER_ALIASES = {
    "claude": "anthropic",
    "gpt": "openai",
    "gemini": "google",
    "openai-codex": "openai",
}


def normalize_provider_id(value: str | None, aliases: dict[str, str] = PROVIDER_ALIASES) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if raw in aliases:
        return aliases[raw]
    for prefix, normalized in (
        ("openai-codex", "openai"),
        ("openai", "openai"),
        ("anthropic", "anthropic"),
        ("claude", "anthropic"),
        ("google", "google"),
        ("gemini", "google"),
        ("openrouter", "openrouter"),
        ("custom", "custom"),
    ):
        if raw.startswith(prefix):
            return normalized
    return ""


def catalog_provider_id_sets(catalog: dict, *, normalize_provider_id_fn=normalize_provider_id) -> tuple[set[str], set[str]]:
    raw_provider_ids: set[str] = set()
    normalized_provider_ids: set[str] = set()
    for group in catalog.get("groups") or []:
        raw = str(group.get("provider_id") or "").strip().lower()
        if not raw:
            continue
        raw_provider_ids.add(raw)
        normalized = normalize_provider_id_fn(raw)
        if normalized:
            normalized_provider_ids.add(normalized)
    return raw_provider_ids, normalized_provider_ids


def catalog_has_provider(
    provider_raw: str,
    provider_normalized: str,
    raw_provider_ids: set[str],
    normalized_provider_ids: set[str],
) -> bool:
    return (
        provider_raw in raw_provider_ids
        or (provider_normalized and provider_normalized in raw_provider_ids)
        or (provider_normalized and provider_normalized in normalized_provider_ids)
    )


def model_matches_active_provider_family(
    model: str,
    active_provider: str,
    *,
    normalize_provider_id_fn=normalize_provider_id,
) -> bool:
    model_lower = model.lower()
    for bare_prefix in ("gpt", "claude", "gemini"):
        if model_lower.startswith(bare_prefix):
            return normalize_provider_id_fn(bare_prefix) == active_provider
    return False


def catalog_model_id_matches(candidate: str, model: str) -> bool:
    candidate = str(candidate or "").strip()
    if candidate.startswith("@") and ":" in candidate:
        candidate = candidate.rsplit(":", 1)[1]
    if "/" in candidate:
        candidate = candidate.split("/", 1)[1]
    return candidate.replace("-", ".").lower() == model.replace("-", ".").lower()


def clean_session_model_provider(value: str | None) -> str | None:
    provider = str(value or "").strip().lower()
    if not provider or provider == "default":
        return None
    if provider.startswith("@"):
        provider = provider[1:]
    return provider or None


def split_provider_qualified_model(model: str, *, clean_provider_fn=clean_session_model_provider) -> tuple[str, str | None]:
    model = str(model or "").strip()
    if model.startswith("@") and ":" in model:
        provider_hint, bare_model = model[1:].rsplit(":", 1)
        provider = clean_provider_fn(provider_hint)
        bare = bare_model.strip()
        if provider and bare:
            return bare, provider
    return model, None


def should_attach_codex_provider_context(
    model: str,
    raw_active_provider: str,
    catalog: dict,
    *,
    catalog_model_id_matches_fn=catalog_model_id_matches,
) -> bool:
    """Return True when a bare Codex model needs separate provider context."""
    if raw_active_provider != "openai-codex":
        return False
    if not model.lower().startswith("gpt"):
        return False
    for group in catalog.get("groups") or []:
        if str(group.get("provider_id") or "").strip().lower() != "openai-codex":
            continue
        return any(
            catalog_model_id_matches_fn(entry.get("id"), model)
            for entry in group.get("models", [])
            if isinstance(entry, dict)
        )
    return False


def resolve_compatible_session_model_state(
    model_id: str | None,
    model_provider: str | None = None,
    *,
    default_model: str,
    get_available_models_fn,
    clean_provider_fn=clean_session_model_provider,
    split_provider_qualified_model_fn=split_provider_qualified_model,
    normalize_provider_id_fn=normalize_provider_id,
    catalog_provider_id_sets_fn=catalog_provider_id_sets,
    catalog_has_provider_fn=catalog_has_provider,
    model_matches_active_provider_family_fn=model_matches_active_provider_family,
    should_attach_codex_provider_context_fn=should_attach_codex_provider_context,
) -> tuple[str, str | None, bool]:
    """Return (effective_model, effective_provider, model_was_normalized)."""
    model = str(model_id or "").strip()
    requested_provider = clean_provider_fn(model_provider)
    if model and requested_provider:
        bare_model, explicit_provider = split_provider_qualified_model_fn(model)
        if not explicit_provider:
            return model, requested_provider, False

    catalog = get_available_models_fn()
    catalog_default = str(catalog.get("default_model") or default_model or "").strip()
    if not model:
        return catalog_default, requested_provider, bool(catalog_default)

    active_provider = normalize_provider_id_fn(catalog.get("active_provider"))
    raw_active_provider = str(catalog.get("active_provider") or "").strip().lower()
    if not active_provider and not raw_active_provider:
        bare_model, explicit_provider = split_provider_qualified_model_fn(model)
        return model, explicit_provider or requested_provider, False

    bare_for_context, explicit_provider = split_provider_qualified_model_fn(model)
    if requested_provider and not explicit_provider:
        return model, requested_provider, False

    if model.startswith("@") and ":" in model:
        provider_raw = explicit_provider or ""
        provider_normalized = normalize_provider_id_fn(provider_raw)
        bare_model = bare_for_context.strip()
        if not provider_raw or not bare_model:
            return model, requested_provider, False

        raw_provider_ids, normalized_provider_ids = catalog_provider_id_sets_fn(catalog)
        hint_matches_active = (
            provider_raw == raw_active_provider
            or provider_raw == active_provider
            or (provider_normalized and provider_normalized == active_provider)
        )
        if hint_matches_active:
            return model, provider_raw, False

        if catalog_has_provider_fn(
            provider_raw,
            provider_normalized,
            raw_provider_ids,
            normalized_provider_ids,
        ):
            return model, provider_raw, False

        if model_matches_active_provider_family_fn(bare_model, active_provider):
            provider_context = (
                raw_active_provider
                if should_attach_codex_provider_context_fn(bare_model, raw_active_provider, catalog)
                else None
            )
            return bare_model, provider_context, True
        if catalog_default:
            provider_context = (
                raw_active_provider
                if should_attach_codex_provider_context_fn(catalog_default, raw_active_provider, catalog)
                else None
            )
            return catalog_default, provider_context, True
        return model, provider_raw, False

    slash = model.find("/")
    if slash < 0:
        model_lower = model.lower()
        for bare_prefix in ("gpt", "claude", "gemini"):
            if model_lower.startswith(bare_prefix):
                model_provider = normalize_provider_id_fn(bare_prefix)
                if model_provider and model_provider != active_provider and catalog_default:
                    provider_context = (
                        raw_active_provider
                        if should_attach_codex_provider_context_fn(catalog_default, raw_active_provider, catalog)
                        else None
                    )
                    return catalog_default, provider_context, True
                provider_context = (
                    raw_active_provider
                    if should_attach_codex_provider_context_fn(model, raw_active_provider, catalog)
                    else requested_provider
                )
                return model, provider_context, False
        return model, requested_provider, False

    model_provider = normalize_provider_id_fn(model[:slash])

    if active_provider in {"custom", "openrouter"}:
        if model_provider in {"", "custom", "openrouter"}:
            return model, requested_provider, False
        groups = catalog.get("groups") or []
        routable_provider_ids = {
            normalize_provider_id_fn(g.get("provider_id") or "") for g in groups
        }
        has_openrouter_group = any(
            (g.get("provider_id") or "") == "openrouter" for g in groups
        )
        if model_provider in routable_provider_ids or has_openrouter_group:
            return model, requested_provider, False
        if catalog_default:
            return catalog_default, requested_provider, True
        return model, requested_provider, False

    if (
        raw_active_provider == "openai-codex"
        and model_provider == "openai"
        and requested_provider is None
        and catalog_default
    ):
        return catalog_default, raw_active_provider, True

    active_for_compare = active_provider or raw_active_provider
    if (
        model_provider
        and model_provider not in {"", "custom", "openrouter"}
        and model_provider != active_for_compare
        and catalog_default
    ):
        return catalog_default, requested_provider, True
    return model, requested_provider, False


def session_model_state_from_request(
    model: str | None,
    requested_provider: str | None,
    current_provider: str | None = None,
    *,
    clean_provider_fn=clean_session_model_provider,
    split_provider_qualified_model_fn=split_provider_qualified_model,
    resolve_compatible_state_fn,
) -> tuple[str | None, str | None]:
    model_value = str(model).strip() if model is not None else None
    provider = clean_provider_fn(requested_provider) if requested_provider is not None else None
    if model_value:
        _bare, explicit_provider = split_provider_qualified_model_fn(model_value)
        if explicit_provider:
            provider = explicit_provider
        elif requested_provider is None:
            provider = clean_provider_fn(current_provider)
        model_value, provider, _changed = resolve_compatible_state_fn(model_value, provider)
    return model_value, provider

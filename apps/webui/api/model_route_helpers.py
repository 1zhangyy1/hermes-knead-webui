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

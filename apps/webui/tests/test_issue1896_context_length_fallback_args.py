"""Regression checks for #1896 — context-length fallback ignores config overrides.

The context-window fallback used by `api/streaming.py` was calling
`get_model_context_length()` with only `model + base_url`, omitting
`config_context_length`, `provider`, and `custom_providers`.

When the agent's `context_compressor` reports 0 (fresh / cached / transitioning
agent), context-length resolution falls all the way through to
`DEFAULT_FALLBACK_CONTEXT = 256_000` even when the user has set
`model.context_length: 1048576` in `config.yaml` or has a 1M model with a
`custom_providers` per-model override.

For users with a context-management plugin (LCM) configured around the real
window, this cascades into a session-killing failure mode: auto-compression
triggers far too early → flood of compress requests → 429s → credential pool
exhaustion → fallback also 429s → "API call failed after 3 retries".

These tests pin the helper call shape so future refactors can't silently drop
the config-override args again.
"""

from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
STREAMING_PY = (REPO / "api" / "streaming.py").read_text(encoding="utf-8")
CONTEXT_WINDOW_PY = (REPO / "api" / "streaming_context_window.py").read_text(encoding="utf-8")
TURN_WRITEBACK_PY = (REPO / "api" / "streaming_turn_writeback.py").read_text(encoding="utf-8")
TERMINAL_PY = (REPO / "api" / "streaming_terminal.py").read_text(encoding="utf-8")


# The fallback helper must pass these kwargs into get_model_context_length.
_REQUIRED_KWARGS = (
    "config_context_length=cfg_ctx_len",
    "provider=resolved_provider or ''",
    "custom_providers=cfg_custom_providers",
)


def _fallback_helper():
    start = CONTEXT_WINDOW_PY.find("def resolve_context_length_fallback(")
    assert start != -1, "resolve_context_length_fallback helper missing"
    end = CONTEXT_WINDOW_PY.find("\ndef ", start + 1)
    return CONTEXT_WINDOW_PY[start:end if end != -1 else len(CONTEXT_WINDOW_PY)]


def test_streaming_uses_context_window_helper_for_both_paths():
    assert "persist_context_window_on_session(" in TURN_WRITEBACK_PY
    completed_writeback = (Path(__file__).parent.parent / "api" / "streaming_completed_writeback.py").read_text(encoding="utf-8")
    assert "_handle_completed_conversation_writeback(" in STREAMING_PY
    assert "apply_completed_turn_writeback_state_fn(" in completed_writeback
    assert "apply_context_window_to_usage=_apply_context_window_to_usage" in STREAMING_PY
    assert "apply_context_window_to_usage(" in TERMINAL_PY


def test_helper_passes_config_context_length():
    """The helper must pass `config_context_length=cfg_ctx_len`."""
    block = _fallback_helper()
    assert "config_context_length=cfg_ctx_len" in block, (
        "Fallback helper is missing `config_context_length=cfg_ctx_len`. "
        "Without it, users who set `model.context_length: 1048576` in "
        "config.yaml get 256K from the default fallback. See #1896."
    )


def test_helper_passes_provider():
    """The helper must pass `provider=resolved_provider or ''`."""
    block = _fallback_helper()
    assert "provider=resolved_provider" in block, (
        "Fallback helper is missing `provider=resolved_provider...`. "
        "Provider is needed for the registry lookup step. See #1896."
    )


def test_helper_passes_custom_providers():
    """The helper must pass `custom_providers=cfg_custom_providers`."""
    block = _fallback_helper()
    assert "custom_providers=cfg_custom_providers" in block, (
        "Fallback helper is missing `custom_providers=cfg_custom_providers`. "
        "This is needed for custom provider context_length overrides. See #1896."
    )


def test_config_context_length_parsed_safely():
    """Invalid config_context_length values must NOT crash the resolver call —
    they should fall through to provider/registry probing instead."""
    assert "except (TypeError, ValueError):" in CONTEXT_WINDOW_PY, (
        "Config context_length parse must be guarded against (TypeError, ValueError) "
        "so a string like '256K' or 'one million' falls through to the resolver "
        "instead of crashing the SSE/save path."
    )


def test_legacy_signature_fallback_present():
    """Older hermes-agent builds may not yet have config_context_length on
    get_model_context_length(). The fix must catch TypeError and retry with
    the legacy 2-arg form so the indicator still resolves *something*."""
    # The except TypeError clause should mention the legacy retry comment OR
    # contain a 2-arg fallback call.
    assert "except TypeError:" in _fallback_helper(), (
        "The fallback helper must catch TypeError to support older hermes-agent "
        "builds whose get_model_context_length signature pre-dates the new "
        "kwargs. Without this fallback, an older agent build would crash "
        "the save/SSE path instead of degrading to a 2-arg call."
    )


def test_cfg_custom_providers_resolved_from_cfg_dict():
    """The kwargs source must be the per-profile config (`_cfg`), not a
    module-level snapshot — otherwise profile switches with different
    custom_providers wouldn't take effect."""
    # Look for the resolution pattern.
    assert "cfg.get('custom_providers')" in CONTEXT_WINDOW_PY, (
        "cfg_custom_providers must be sourced from `cfg.get('custom_providers')` "
        "(per-profile config) so profile-scoped custom_providers entries work."
    )
    assert "cfg.get('model', {})" in CONTEXT_WINDOW_PY, (
        "cfg_ctx_len must be sourced from `cfg.get('model', {}).get('context_length')` "
        "(per-profile config) so profile-scoped model.context_length overrides work."
    )


# ── Sibling fallback in api/routes.py session-load path ─────────────────────

ROUTES_PY = (REPO / "api" / "routes.py").read_text(encoding="utf-8")


def test_routes_session_load_fallback_passes_config_overrides():
    """The session-load fallback at api/routes.py (around 'older sessions
    (pre-#1318) that have context_length=0 persisted') has the SAME bug shape
    as the streaming.py fallbacks: it called `_get_cl(model, "")` with no
    config overrides, so `/api/session/get` returned 256K for old sessions
    even when the user had `model.context_length: 1048576` set.

    The fix mirrors streaming.py's: pass config_context_length, provider,
    and custom_providers, with a TypeError fallback to the legacy 2-arg
    form. Without this, the very first paint of a reloaded old session shows
    the wrong window until a turn is sent.
    """
    # Anchor: find the comment that pins this fallback's purpose.
    anchor = "older sessions (pre-#1318) that have context_length=0 persisted"
    idx = ROUTES_PY.find(anchor)
    assert idx != -1, "session-load fallback comment moved/removed"
    # The route block may delegate the resolver details to a helper, but the
    # session-load path must still call the helper and that helper must preserve
    # the same kwargs as the streaming.py fix.
    block_end = ROUTES_PY.find("if _fb_cl:", idx)
    assert block_end != -1, "_fb_cl assignment not found after fallback comment"
    block = ROUTES_PY[idx:block_end]
    helper_start = ROUTES_PY.find("def _resolve_context_length_for_session_model")
    assert helper_start != -1, "context-length resolver helper not found"
    helper_end = ROUTES_PY.find("\ndef ", helper_start + 1)
    helper = ROUTES_PY[helper_start:helper_end if helper_end != -1 else len(ROUTES_PY)]
    assert "_resolve_context_length_for_session_model" in block
    # Same kwargs as the streaming.py fix.
    assert "config_context_length=" in helper, (
        "session-load fallback in api/routes.py must pass config_context_length= "
        "so user-set model.context_length wins over the 256K default. See #1896."
    )
    assert "provider=provider or" in helper, (
        "session-load fallback in api/routes.py must pass provider= "
        "so the registry lookup is provider-aware. See #1896."
    )
    assert "custom_providers=" in helper, (
        "session-load fallback in api/routes.py must pass custom_providers= "
        "so the per-model override path applies. See #1896."
    )
    # Legacy fallback for older hermes-agent builds that pre-date the kwargs.
    assert "except TypeError:" in helper, (
        "session-load fallback must catch TypeError to support older "
        "hermes-agent builds without the new kwargs."
    )

"""Provider and cancellation error helpers for the WebUI streaming layer."""

from __future__ import annotations

import re
from typing import Callable


CANCEL_MARKER_PATTERNS = ('task cancelled', 'task canceled', 'response interrupted')


def is_quota_error_text(err_text: str) -> bool:
    """Return True when provider text looks like quota/usage exhaustion."""
    err_lower = str(err_text or '').lower()
    return (
        'insufficient credit' in err_lower
        or 'credit balance' in err_lower
        or 'credits exhausted' in err_lower
        or 'more credits' in err_lower
        or 'can only afford' in err_lower
        or 'fewer max_tokens' in err_lower
        or 'quota_exceeded' in err_lower
        or 'quota exceeded' in err_lower
        or 'exceeded your current quota' in err_lower
        # OpenAI Codex OAuth usage-exhaustion shapes (#1765).
        or 'plan limit reached' in err_lower
        or 'usage_limit_exceeded' in err_lower
        or 'usage limit exceeded' in err_lower
        or 'reached the limit of messages' in err_lower
        or 'used up your usage' in err_lower
        or ('plan' in err_lower and 'limit' in err_lower and 'reached' in err_lower)
    )


def preferred_agent_display_name(
    *,
    load_settings_fn: Callable[[], dict] | None = None,
    logger=None,
) -> str:
    """Return the configured assistant display name for user-facing copy."""
    try:
        name = str((load_settings_fn() if load_settings_fn else {}).get('bot_name') or '').strip()
    except Exception:
        if logger is not None:
            logger.debug("Failed to load bot_name for cancellation copy", exc_info=True)
        name = ''
    return name or 'Hermes'


def cancelled_turn_hint(
    agent_name: str | None = None,
    *,
    load_settings_fn: Callable[[], dict] | None = None,
    logger=None,
) -> str:
    name = str(agent_name or preferred_agent_display_name(load_settings_fn=load_settings_fn, logger=logger)).strip() or 'Hermes'
    return f'The run was cancelled by the user before {name} finished. No provider failure occurred.'


def classify_provider_error(
    err_str: str,
    exc=None,
    *,
    silent_failure: bool = False,
    cancelled_turn_hint_fn: Callable[[], str] | None = None,
    is_quota_error_text_fn: Callable[[str], bool] = is_quota_error_text,
) -> dict:
    """Classify provider/agent failure text for WebUI apperror UX."""
    err_str = str(err_str or '')
    err_lower = err_str.lower()
    exc_name = type(exc).__name__ if exc is not None else ''
    is_cancelled = (
        'cancelled by user' in err_lower
        or 'canceled by user' in err_lower
        or 'user cancelled' in err_lower
        or 'user canceled' in err_lower
        or 'task cancelled' in err_lower
        or 'task canceled' in err_lower
        or 'cancellederror' in err_lower
        or (exc is not None and exc_name in ('CancelledError', 'CanceledError'))
    )
    is_interrupted = (
        not is_cancelled
        and (
            'interrupted by user' in err_lower
            or 'response interrupted' in err_lower
            or 'operation interrupted' in err_lower
            or 'operation was interrupted' in err_lower
            or 'operation aborted' in err_lower
            or 'request was aborted' in err_lower
            or 'aborterror' in err_lower
            or (exc is not None and type(exc).__name__ in ('KeyboardInterrupt', 'AbortError'))
        )
    )
    if is_cancelled:
        return {
            'label': 'Task cancelled',
            'type': 'cancelled',
            'hint': cancelled_turn_hint_fn() if cancelled_turn_hint_fn else cancelled_turn_hint(),
        }
    if is_interrupted:
        return {
            'label': 'Response interrupted',
            'type': 'interrupted',
            'hint': 'The run stopped before a provider response completed. If you did not cancel it, try again.',
        }
    is_quota = is_quota_error_text_fn(err_str)
    is_auth = (
        not is_quota and (
            '401' in err_str
            or (exc is not None and 'AuthenticationError' in exc_name)
            or 'authentication' in err_lower
            or 'unauthorized' in err_lower
            or 'invalid api key' in err_lower
            or 'invalid_api_key' in err_lower
            or 'no cookie auth credentials' in err_lower
        )
    )
    is_not_found = (
        # model_not_found hints mention Settings / `hermes model` below.
        '404' in err_str
        or 'not found' in err_lower
        or 'does not exist' in err_lower
        or 'model not found' in err_lower
        or 'model_not_found' in err_lower
        or 'invalid model' in err_lower
        or 'does not match any known model' in err_lower
        or 'unknown model' in err_lower
    )
    is_rate_limit = (not is_quota) and (
        'rate limit' in err_lower or '429' in err_str or (exc is not None and 'RateLimitError' in exc_name)
    )
    if is_quota:
        return {
            'label': 'Out of credits',
            'type': 'quota_exhausted',
            'hint': 'Your provider account is out of credits or usage. Top up, wait for the plan window to reset, or switch providers via `hermes model`.',
        }
    if is_rate_limit:
        return {
            'label': 'Rate limit reached',
            'type': 'rate_limit',
            'hint': 'Rate limit reached. The fallback model (if configured) was also exhausted. Try again in a moment.',
        }
    if is_auth:
        return {
            'label': 'Authentication failed',
            'type': 'auth_mismatch',
            'hint': 'The selected model may not be supported by your configured provider or your API key is invalid. Run `hermes model` in your terminal to update credentials, then restart the WebUI.',
        }
    if is_not_found:
        return {
            'label': 'Model not found',
            'type': 'model_not_found',
            'hint': 'The selected model was not found by the provider. Check the model ID in Settings or run `hermes model` to verify it exists for your provider.',
        }
    if silent_failure:
        return {
            'label': 'No response from provider',
            # Preserve the existing no_response event type (#373) while making
            # the catch-all silent-failure message more specific for #1765.
            'type': 'no_response',
            'hint': 'The provider returned no content and no error. This often means a usage/rate limit was hit silently. Check provider status, switch providers via `hermes model`, or try again in a moment.',
        }
    return {'label': 'Error', 'type': 'error', 'hint': ''}


def provider_error_payload(
    message: str,
    err_type: str,
    hint: str = '',
    *,
    redact_text_fn: Callable[[str], str] | None = None,
) -> dict:
    """Build a bounded, redacted apperror payload with provider details."""
    message_text = str(message or '')
    safe_message = redact_text_fn(message_text).strip() if message_text and redact_text_fn else message_text.strip()
    payload: dict = {'message': safe_message or message_text, 'type': err_type}
    if hint:
        payload['hint'] = hint
    if safe_message:
        details = safe_message
        if len(details) > 1200:
            details = details[:1197].rstrip() + '...'
        if details:
            payload['details'] = details
    return payload


def sanitize_provider_error_text(error_text: str) -> str:
    """Strip provider HTML error pages down to compact plain text."""
    text = str(error_text or '')
    stripped = re.sub(r'<[^>]+>', ' ', text)
    stripped = re.sub(r'\s+', ' ', stripped).strip()
    return stripped if stripped != text else text


def cancelled_turn_content(
    message: str = 'Task cancelled.',
    *,
    cancelled_turn_hint_fn: Callable[[], str] | None = None,
) -> str:
    """Return cancelled-turn copy matching the verbose provider-error layout."""
    message_text = str(message or 'Task cancelled.').strip()
    if not message_text.endswith('.'):
        message_text += '.'
    hint = cancelled_turn_hint_fn() if cancelled_turn_hint_fn else cancelled_turn_hint()
    return (
        f"**Task cancelled:** {message_text}\n\n"
        f"*{hint}*"
    )

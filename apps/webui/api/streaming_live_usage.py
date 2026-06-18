"""Live usage snapshots and prompt estimates for WebUI streaming."""

from __future__ import annotations

from typing import Callable


class LiveUsageTracker:
    """Track live usage values while a streaming turn is still in progress."""

    def __init__(self, *, get_session: Callable[[], object | None], get_agent: Callable[[], object | None]):
        self._get_session = get_session
        self._get_agent = get_agent
        self._live_prompt_estimate_tokens = 0
        self._live_prompt_exact_tokens = 0
        self.seen_tool_call_ids = set()

    def seed_prompt_estimate(self) -> int:
        """Capture the latest exact prompt size before adding live tool deltas."""
        if self._live_prompt_estimate_tokens > 0:
            return self._live_prompt_estimate_tokens
        _base = 0
        _agent = self._get_agent()
        if _agent is not None:
            try:
                _cc = getattr(_agent, 'context_compressor', None)
                if _cc:
                    _base = getattr(_cc, 'last_prompt_tokens', 0) or 0
            except Exception:
                _base = 0
        if not _base:
            try:
                _session_obj = self._get_session()
                _base = getattr(_session_obj, 'last_prompt_tokens', 0) or 0
            except Exception:
                _base = 0
        self._live_prompt_estimate_tokens = int(_base or 0)
        self._live_prompt_exact_tokens = self._live_prompt_estimate_tokens
        return self._live_prompt_estimate_tokens

    def bump_prompt_estimate(self, messages) -> int:
        """Increment a rough next-prompt estimate from live tool activity."""
        if not messages:
            return self._live_prompt_estimate_tokens
        try:
            from agent.model_metadata import estimate_messages_tokens_rough
            _delta = int(estimate_messages_tokens_rough(messages) or 0)
        except Exception:
            _delta = 0
        if _delta > 0:
            self.seed_prompt_estimate()
            self._live_prompt_estimate_tokens += _delta
        return self._live_prompt_estimate_tokens

    def snapshot(self):
        """Return best-effort live usage for mid-stream UI updates.

        During tool execution the final `done` event has not fired yet, but the
        frontend still benefits from seeing the latest known token / context
        values. These are exact for the most recent model call and a truthful
        lower bound for the pending next call after a tool result is appended.
        """
        _usage = {
            'input_tokens': 0,
            'output_tokens': 0,
            'estimated_cost': 0,
            'cache_read_tokens': 0,
            'cache_write_tokens': 0,
            'context_length': 0,
            'threshold_tokens': 0,
            'last_prompt_tokens': 0,
        }
        try:
            _session_obj = self._get_session()
        except Exception:
            _session_obj = None

        _agent = self._get_agent()
        if _agent is not None:
            try:
                _usage['input_tokens'] = getattr(_agent, 'session_prompt_tokens', 0) or 0
                _usage['output_tokens'] = getattr(_agent, 'session_completion_tokens', 0) or 0
                _usage['estimated_cost'] = getattr(_agent, 'session_estimated_cost_usd', 0) or 0
                _usage['cache_read_tokens'] = getattr(_agent, 'session_cache_read_tokens', 0) or 0
                _usage['cache_write_tokens'] = getattr(_agent, 'session_cache_write_tokens', 0) or 0
            except Exception:
                pass
            try:
                _cc = getattr(_agent, 'context_compressor', None)
                if _cc:
                    _usage['context_length'] = getattr(_cc, 'context_length', 0) or 0
                    _usage['threshold_tokens'] = getattr(_cc, 'threshold_tokens', 0) or 0
                    _usage['last_prompt_tokens'] = getattr(_cc, 'last_prompt_tokens', 0) or 0
            except Exception:
                pass

        if _session_obj is not None:
            for _field in ('input_tokens', 'output_tokens', 'estimated_cost', 'cache_read_tokens', 'cache_write_tokens', 'context_length', 'threshold_tokens', 'last_prompt_tokens'):
                if not _usage.get(_field):
                    try:
                        _usage[_field] = getattr(_session_obj, _field, 0) or 0
                    except Exception:
                        pass

        _real_prompt_tokens = int(_usage.get('last_prompt_tokens') or 0)
        if _real_prompt_tokens and _real_prompt_tokens != self._live_prompt_exact_tokens:
            self._live_prompt_exact_tokens = _real_prompt_tokens
            self._live_prompt_estimate_tokens = _real_prompt_tokens
        elif self._live_prompt_estimate_tokens > _real_prompt_tokens:
            _usage['last_prompt_tokens'] = self._live_prompt_estimate_tokens

        return _usage


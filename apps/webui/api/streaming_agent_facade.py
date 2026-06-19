"""Compatibility facade for WebUI streaming agent lookup."""

from __future__ import annotations


def get_ai_agent_from_facade():
    """Return AIAgent class, retrying the import if the initial attempt failed."""
    from api import streaming

    if streaming.AIAgent is None:
        try:
            from run_agent import AIAgent as cls  # noqa: PLC0415

            streaming.AIAgent = cls
        except ImportError:
            pass
    return streaming.AIAgent

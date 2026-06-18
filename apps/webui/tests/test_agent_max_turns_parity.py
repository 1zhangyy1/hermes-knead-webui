"""Regression checks for WebUI AIAgent iteration-budget parity.

WebUI streaming agents must honor Hermes' configured agent.max_turns. Otherwise
browser-originated long-running tasks silently fall back to AIAgent's constructor
default and hit the "maximum number of tool-calling iterations" summary path even
when the operator raised the global Hermes budget.
"""

from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
STREAMING_PY = (REPO / "api" / "streaming.py").read_text(encoding="utf-8")
STREAMING_AGENT_TURN_SETUP_PY = (REPO / "api" / "streaming_agent_turn_setup.py").read_text(encoding="utf-8")
STREAMING_AGENT_CONFIG_PY = (REPO / "api" / "streaming_agent_config.py").read_text(encoding="utf-8")
STREAMING_AGENT_CACHE_PY = (REPO / "api" / "streaming_agent_cache.py").read_text(encoding="utf-8")


def test_streaming_agent_reads_agent_max_turns_from_config():
    assert "_agent_cfg_for_iterations" in STREAMING_AGENT_CONFIG_PY
    assert "_agent_cfg_for_iterations.get('max_turns')" in STREAMING_AGENT_CONFIG_PY
    assert "_cfg.get('max_turns')" in STREAMING_AGENT_CONFIG_PY


def test_streaming_agent_passes_max_iterations_to_aiagent():
    assert "if 'max_iterations' in agent_params and max_iterations is not None:" in STREAMING_AGENT_CONFIG_PY
    assert "kwargs['max_iterations'] = max_iterations" in STREAMING_AGENT_CONFIG_PY
    assert "_prepare_streaming_agent_turn_setup(" in STREAMING_PY
    assert "prepare_webui_agent_kwargs_fn(" in STREAMING_AGENT_TURN_SETUP_PY
    assert "max_iterations=_max_iterations_cfg" in STREAMING_AGENT_CONFIG_PY
    assert "max_iterations=agent_kwargs_state.max_iterations" in STREAMING_AGENT_TURN_SETUP_PY


def test_streaming_agent_cache_signature_includes_max_iterations():
    sig_start = STREAMING_AGENT_CACHE_PY.index("def build_agent_cache_signature")
    sig_block = STREAMING_AGENT_CACHE_PY[sig_start:STREAMING_AGENT_CACHE_PY.index("return hashlib.sha256", sig_start)]
    assert "max_iterations or ''" in sig_block

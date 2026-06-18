"""Runtime prompt assembly helpers for WebUI streaming turns."""

from __future__ import annotations


def build_workspace_system_message(workspace) -> str:
    return (
        f"Active workspace at session start: {workspace}\n"
        "Every user message is prefixed with [Workspace::v1: /absolute/path] indicating the "
        "workspace the user has selected in the web UI at the time they sent that message. "
        "This tag is the single authoritative source of the active workspace and updates "
        "with every message. It overrides any prior workspace mentioned in this system "
        "prompt, memory, or conversation history. Always use the value from the most recent "
        "[Workspace::v1: ...] tag as your default working directory for ALL file operations: "
        "write_file, read_file, search_files, terminal workdir, and patch. "
        "Never fall back to a hardcoded path when this tag is present."
    )


def resolve_personality_prompt(config: dict | None, personality_name: str | None) -> str | None:
    if not personality_name or not isinstance(config, dict):
        return None
    agent_cfg = config.get('agent', {})
    personalities = agent_cfg.get('personalities', {}) if isinstance(agent_cfg, dict) else {}
    if not isinstance(personalities, dict) or personality_name not in personalities:
        return None

    value = personalities[personality_name]
    if not isinstance(value, dict):
        return str(value)

    parts = [value.get('system_prompt', '') or value.get('prompt', '')]
    if value.get('tone'):
        parts.append(f'Tone: {value["tone"]}')
    if value.get('style'):
        parts.append(f'Style: {value["style"]}')
    return '\n'.join(part for part in parts if part)


def resolve_product_runtime_prompt(
    product_context,
    *,
    product_ephemeral_prompt_fn=None,
    logger=None,
) -> str:
    if not product_context:
        return ''
    try:
        if product_ephemeral_prompt_fn is None:
            from api.product_context import product_ephemeral_prompt as product_ephemeral_prompt_fn
        return product_ephemeral_prompt_fn(product_context)
    except Exception:
        if logger is not None:
            logger.debug("Failed to build product runtime prompt", exc_info=True)
        return ''


def configure_agent_runtime_prompt(
    agent,
    *,
    config: dict | None,
    personality_name: str | None,
    product_context=None,
    product_ephemeral_prompt_fn=None,
    webui_ephemeral_system_prompt,
    logger=None,
) -> str:
    personality_prompt = resolve_personality_prompt(config, personality_name)
    product_prompt = resolve_product_runtime_prompt(
        product_context,
        product_ephemeral_prompt_fn=product_ephemeral_prompt_fn,
        logger=logger,
    )
    prompt = webui_ephemeral_system_prompt(personality_prompt, product_prompt)
    agent.ephemeral_system_prompt = prompt
    return prompt

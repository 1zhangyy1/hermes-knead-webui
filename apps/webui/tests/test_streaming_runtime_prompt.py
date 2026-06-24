from api.streaming_runtime_prompt import (
    build_workspace_system_message,
    configure_agent_runtime_prompt,
    resolve_personality_prompt,
    resolve_product_runtime_prompt,
)


class Agent:
    ephemeral_system_prompt = None


class Logger:
    def __init__(self):
        self.messages = []

    def debug(self, *args, **kwargs):
        self.messages.append((args, kwargs))


def test_build_workspace_system_message_mentions_authoritative_workspace_tag():
    prompt = build_workspace_system_message('/tmp/project')

    assert prompt.startswith('Active workspace at session start: /tmp/project')
    assert '[Workspace::v1: /absolute/path]' in prompt
    assert 'single authoritative source' in prompt
    assert 'Never fall back to a hardcoded path' in prompt


def test_resolve_personality_prompt_from_dict_prefers_system_prompt():
    prompt = resolve_personality_prompt(
        {
            'agent': {
                'personalities': {
                    'coach': {
                        'system_prompt': 'Be direct.',
                        'prompt': 'Ignored.',
                        'tone': 'warm',
                        'style': 'concise',
                    },
                },
            },
        },
        'coach',
    )

    assert prompt == 'Be direct.\nTone: warm\nStyle: concise'


def test_resolve_personality_prompt_from_string_and_missing_values():
    config = {'agent': {'personalities': {'poet': 'Speak softly.'}}}

    assert resolve_personality_prompt(config, 'poet') == 'Speak softly.'
    assert resolve_personality_prompt(config, 'missing') is None
    assert resolve_personality_prompt(config, None) is None


def test_resolve_product_runtime_prompt_uses_injected_builder():
    prompt = resolve_product_runtime_prompt(
        {'product': 'demo'},
        product_ephemeral_prompt_fn=lambda ctx: f"Product: {ctx['product']}",
    )

    assert prompt == 'Product: demo'


def test_resolve_product_runtime_prompt_logs_builder_failure():
    logger = Logger()

    def fail(_context):
        raise RuntimeError('bad product')

    prompt = resolve_product_runtime_prompt(
        {'product': 'demo'},
        product_ephemeral_prompt_fn=fail,
        logger=logger,
    )

    assert prompt == ''
    assert logger.messages


def test_configure_agent_runtime_prompt_assigns_combined_prompt():
    agent = Agent()

    prompt = configure_agent_runtime_prompt(
        agent,
        config={'agent': {'personalities': {'coach': 'Be direct.'}}},
        personality_name='coach',
        product_context={'product': 'demo'},
        product_ephemeral_prompt_fn=lambda ctx: f"Product: {ctx['product']}",
        webui_ephemeral_system_prompt=lambda personality, product: f'{personality}|{product}',
        logger=Logger(),
    )

    assert prompt == 'Be direct.|Product: demo'
    assert agent.ephemeral_system_prompt == prompt


def test_configure_agent_runtime_prompt_appends_structured_agent_instruction():
    agent = Agent()

    prompt = configure_agent_runtime_prompt(
        agent,
        config={},
        personality_name=None,
        product_context={'product': 'demo'},
        agent_instruction='Creator draft rules',
        product_ephemeral_prompt_fn=lambda ctx: f"Product: {ctx['product']}",
        webui_ephemeral_system_prompt=lambda personality, product: product,
        logger=Logger(),
    )

    assert prompt == 'Product: demo\n\nCreator draft rules'
    assert agent.ephemeral_system_prompt == prompt

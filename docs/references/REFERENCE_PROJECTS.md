# Reference Projects

These projects are useful references, but they are not production source for Next AI Chat. Keep local checkouts under `vendor/`; Git ignores that directory.

## LobeHub

Reference value:

- Clear assistant creation and selection flow.
- Useful mental model for a personalized AI object.
- Good examples of simple first-screen information hierarchy.

Next AI upgrade:

- We do not stop at assistants.
- Each AI object can become an AI product with its own generated or evolved interface.

## PilotDeck

Reference value:

- Focused work surface.
- Agent-centered task execution.
- Simple relationship between chat and workspace output.

Next AI upgrade:

- The workspace is owned by the selected AI product.
- The product can evolve its task interface over time.

## Hermes WebUI

Reference value:

- Existing chat, sessions, files, model selection, tools, and agent execution.

Next AI usage:

- Forked into `apps/webui` as the production app shell.
- Product runtime and product workspace APIs are added on top.

## Hermes Agent

Reference value:

- Agent execution runtime.
- Tool and skill integration.

Next AI usage:

- Product turns should route agent writes to the selected product workspace.
- Product-specific skills and tools should be represented in `product.json`.

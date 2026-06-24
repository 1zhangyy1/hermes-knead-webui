# Reference Projects

These projects are useful references, but they are not production source for Knead. Keep local checkouts under `vendor/`; Git ignores that directory.

Reference projects should influence product judgment, information architecture, and interaction patterns. Do not copy source from them into Knead unless a file is explicitly vendored, licensed, and attributed.

## Hermes Agent

Source: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)

Reference value:

- Native agent loop, model routing, tools, skills, checkpoints, files, and runtime events.
- Existing WebUI foundation for chat, sessions, model selection, tool calls, and workspace files.

Knead usage:

- The official runtime is vendored as `runtimes/hermes-agent`.
- Product turns should route writes to the selected product workspace.
- Product-specific skills and tools should be represented in `product.json`.

## PilotDeck

Source: [OpenBMB/PilotDeck](https://github.com/OpenBMB/PilotDeck)

Reference value:

- Focused work surface.
- Agent-centered task execution.
- Simple relationship between chat and workspace output.

Knead upgrade:

- The workspace is owned by the selected AI product.
- The product can evolve its task interface over time.

## LobeHub / Lobe Chat

Source: [lobehub/lobe-chat](https://github.com/lobehub/lobe-chat)

Reference value:

- Clear assistant creation and selection flow.
- Useful mental model for a personalized AI object.
- Good examples of simple first-screen information hierarchy.

Knead upgrade:

- Knead does not stop at assistants.
- Each AI object can become an AI product with its own generated or evolved interface.

## PinMe

Source: [glitternetwork/pinme](https://github.com/glitternetwork/pinme)

Reference value:

- Lightweight object organization.
- Pinned, durable context as a product surface rather than a loose chat transcript.
- Useful contrast for how Knead should make generated products feel stable and reusable.

Knead upgrade:

- Knead product objects own chat, files, prompts, tools, and optional workspace UI.
- The product can keep evolving after creation instead of being a static pinned artifact.

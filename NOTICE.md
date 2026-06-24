# Notices

This repository contains Knead source code and a first-class bundled runtime dependency.

## Knead

Knead source code is licensed under the MIT License. See [LICENSE](LICENSE).

Copyright (c) 2026 Knead Contributors.

## Hermes Agent Runtime

Knead vendors Hermes Agent under `runtimes/hermes-agent` because Hermes is the core agent runtime used by the product.

- Upstream repository: https://github.com/NousResearch/hermes-agent
- Vendored path: `runtimes/hermes-agent`
- License: MIT
- Copyright: Copyright (c) 2025 Nous Research
- License file: [runtimes/hermes-agent/LICENSE](runtimes/hermes-agent/LICENSE)
- Upstream metadata: [runtimes/hermes-agent/UPSTREAM.md](runtimes/hermes-agent/UPSTREAM.md)
- Local patch log: [runtimes/hermes-agent/PATCHES.md](runtimes/hermes-agent/PATCHES.md)

When updating the bundled runtime, keep `UPSTREAM.md`, `PATCHES.md`, and this notice in sync.

## Inherited WebUI Code

The production WebUI under `apps/webui` includes code and documentation
derived from Hermes Web UI work. That subtree keeps its own MIT license notice
at [apps/webui/LICENSE](apps/webui/LICENSE).

- Path: `apps/webui`
- License: MIT
- Copyright: Copyright (c) 2025 Hermes Web UI Contributors

## Built-in Product Examples

Curated built-in products under `products/` are part of the Knead source tree
and are covered by the repository MIT License unless a product-specific credit
file says otherwise.

`products/ppt-designer/ppt-skill` is support code for the built-in PPT Designer
product. Generated decks, generated slide images, exported PPTX files, local
`.env` files, and provider keys are runtime state and must not be committed.

Product media assets with separate source or license details must be credited in
the product's own `assets/CREDITS.md`; for example, `products/ai-otome/assets/CREDITS.md`.

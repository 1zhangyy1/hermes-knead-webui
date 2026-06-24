# Contributing To Knead WebUI

The main contributor guide is [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md).
This file only adds WebUI-specific guardrails.

## WebUI Shape

Knead WebUI is intentionally lightweight:

- Python server modules under `api/`
- Vanilla JavaScript modules under `static/`
- No frontend build step for the production shell
- Product workspaces rendered through the product runtime/bridge

Keep changes within that shape unless a product capability clearly requires a
larger architectural move.

## Product Boundary

The WebUI shell should stay stable while products evolve inside their own
workspaces.

- Global shell: navigation, chat surface, files/workspace affordances, product
  registry, product bridge, and creation/shaping scopes.
- Product source examples: repository-level `products/`.
- Runtime user products: `.hermes-home/webui/products/` by default.

Do not commit generated product outputs, local `.env` files, generated versions,
runtime state, or exported decks.

## Checks

Run from the repository root:

```bash
pnpm verify
pnpm check
```

For release-facing changes:

```bash
pnpm release:check
```

If the change affects only docs, `pnpm docs:check` is enough for a quick first
pass.

## Older Hermes Docs

Files such as `ARCHITECTURE.md`, `TESTING.md`, `ROADMAP.md`, and deeper
`docs/` references may still describe the inherited Hermes WebUI. They are
useful implementation references, but the current Knead product model is defined
by the repository-level product docs linked from the root README.

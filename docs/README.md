# Documentation

This directory separates current product truth from historical design exploration.

## Current Docs

- [`../PRODUCT.md`](../PRODUCT.md): product definition, target users, design principles, and MVP model.
- [`../PRODUCT_UIUX.md`](../PRODUCT_UIUX.md): current UI/UX model for the shelf, task screen, product layouts, bridge, and evolution flow.
- [`../DESIGN.md`](../DESIGN.md): current visual system, brand tone, app-shell tokens, and UI surface rules.
- [`PRODUCT_MODEL_CONTRACT.md`](PRODUCT_MODEL_CONTRACT.md): implementation contract for product data, lifecycle, scopes, bridge, and release invariants.
- [`architecture/PRODUCTION_REPOSITORY_PLAN.md`](architecture/PRODUCTION_REPOSITORY_PLAN.md): repository shape, source boundaries, local runtime state, and done criteria.
- [`architecture/HERMES_VENDORING.md`](architecture/HERMES_VENDORING.md): Hermes runtime vendoring and update policy.

## Reference Docs

- [`references/REFERENCE_PROJECTS.md`](references/REFERENCE_PROJECTS.md): external projects and what Knead borrowed from them.
- `references/*.md`: focused notes on Hermes, LobeHub, and related runtime/product references.
- `research/*.md`: active research notes that are not yet product contracts.

## Historical Docs

`archive/` documents the archive policy. Raw exploratory plans and scratch notes
are intentionally excluded from the public release tree; they should only return
to `docs/` after being rewritten as current, public-facing documentation.

## Brand System And Explorations

The current brand system is summarized in [`../DESIGN.md`](../DESIGN.md). `brand/`
contains local visual explorations, mockups, and logo assets. These files are
useful for design work but are not runtime product code.

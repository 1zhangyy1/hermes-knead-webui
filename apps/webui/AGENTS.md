# Agent Instructions For Knead WebUI

This directory contains the production WebUI shell for Knead. The WebUI is built
on top of the vendored Hermes runtime, but product decisions belong to Knead.

## Read First

Before changing WebUI behavior, read these repository-level docs:

1. [`../../README.md`](../../README.md)
2. [`../../PRODUCT.md`](../../PRODUCT.md)
3. [`../../PRODUCT_UIUX.md`](../../PRODUCT_UIUX.md)
4. [`../../docs/PRODUCT_MODEL_CONTRACT.md`](../../docs/PRODUCT_MODEL_CONTRACT.md)
5. [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md)

For visual work, also read [`../../DESIGN.md`](../../DESIGN.md).

## Source Boundary

- App shell and product runtime code lives in `apps/webui/`.
- Curated built-in products live in [`../../products`](../../products).
- Runtime-generated products live under `.hermes-home/webui/products/` when
  launched through `pnpm dev`.
- Vendored Hermes runtime code lives in [`../../runtimes/hermes-agent`](../../runtimes/hermes-agent).

Do not solve product-specific changes by mutating global shell code unless the
platform itself needs a new capability. A product changing itself should write
inside its own product workspace.

## Working Rules

- Keep one logical change per PR or patch.
- Preserve the Python plus vanilla JavaScript WebUI shape unless there is a
  clear product reason to introduce infrastructure.
- Keep usage and shaping scopes explicit. `product_usage` is for doing the
  product's work; `product_builder` is for changing that product.
- Do not reintroduce shell-side keyword classifiers for product creation. The
  Creator/product builder should decide the product shape.
- Do not commit provider keys, local runtime state, generated product versions,
  product outputs, exported decks, or root `.tmp-*` files.

## Verification

From the repository root, prefer the smallest relevant check:

```bash
pnpm docs:check
pnpm product:check -- products/<product-id>
pnpm verify
pnpm release:check
```

Use `pnpm release:check:clean` only when preparing a final clean release state.

## Inherited Hermes References

Some documents in this directory still describe the original Hermes WebUI
implementation. Treat them as implementation references for the underlying
runtime and old WebUI behavior, not as Knead product truth. If they conflict
with the repository-level product docs above, follow the Knead docs.

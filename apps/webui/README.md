# Knead WebUI

This directory contains the production WebUI app for Knead.

Knead WebUI is the shell that lets users choose, use, and shape AI products. It
starts from a chat surface and can open a product workspace only when that
product needs a more structured interface.

## Responsibilities

- Serve the main browser UI.
- Render built-in and runtime-generated AI products.
- Keep product usage and product shaping as separate scopes.
- Store runtime state outside the source tree by default.
- Bridge product workspaces to the host chat and file APIs.

## Source Boundary

```text
apps/webui/api/       Python API routes and product/session state handling
apps/webui/static/    Browser shell, product runtime, and UI assets
apps/webui/tests/     Product and WebUI behavior tests
```

Curated product examples live in the repository-level `products/` directory.
User-created products are runtime state and should be written to
`.hermes-home/webui/products/` when launched through `pnpm dev`.

## Documentation Boundary

The current Knead product model is defined at the repository root:

- [`../../PRODUCT.md`](../../PRODUCT.md)
- [`../../PRODUCT_UIUX.md`](../../PRODUCT_UIUX.md)
- [`../../DESIGN.md`](../../DESIGN.md)
- [`../../docs/PRODUCT_MODEL_CONTRACT.md`](../../docs/PRODUCT_MODEL_CONTRACT.md)

Several deeper documents in `apps/webui/` still describe the inherited Hermes
WebUI implementation. Treat those as implementation references for the runtime
and old shell behavior. If they conflict with the product docs above, follow the
Knead docs.

## Run From The Repository Root

```bash
pnpm install
pnpm setup:local
# Edit .env with your provider key, then configure the project-local model.
pnpm hermes:model
pnpm dev
```

The app runs on `http://localhost:8788` by default.

## Verify

From the repository root:

```bash
pnpm verify
pnpm check
```

`pnpm verify` checks the repository boundary, product manifests, WebUI syntax,
product runtime smoke tests, and the product pytest suite.

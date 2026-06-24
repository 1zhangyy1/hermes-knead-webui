# Experiments Boundary

This directory intentionally contains only a release-boundary note in the public
source tree.

Knead had older prototypes, visual references, and React space experiments while
the product model was being explored. Those files are not production source and
are not shipped with the release tree because they used obsolete product names,
old interaction models, and local-only development assumptions.

Production source lives in:

- [`../apps/webui`](../apps/webui): the WebUI shell and product runtime
- [`../products`](../products): maintained built-in product examples
- [`../packages`](../packages): shared TypeScript packages used by production checks
- [`../runtimes`](../runtimes): bundled runtime dependencies

## What Stays Out

Historical experiments can be kept outside the release tree for internal
research. They should only return to this directory when they are rewritten as
current, public-facing examples and pass the same source-boundary checks as the
rest of the repository.

## Release Boundary

Experiments are intentionally outside `pnpm-workspace.yaml`, the production app,
and the default release gate. They should not be used as production source or as
examples of the current product contract.

Do not commit local experiment build output or dependency folders:

- `experiments/**/node_modules/`
- `experiments/**/dist/`
- `experiments/**/build/`
- `experiments/**/.vite/`
- `experiments/**/.next/`
- `experiments/**/*.tsbuildinfo`
- `experiments/generated/`

Use `pnpm release:clean:local` from the repository root to remove ignored local
experiment artifacts before packaging or moving a checkout.

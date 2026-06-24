# Knead

Knead is an AI product shelf. Users choose or create an AI, start from chat, and let that AI grow a small workspace only when the work needs more structure.

The current MVP centers on three built-in AI products:

- `General AI`: a `chat_only` product. Its own product UI is the base chat surface.
- `PPT Designer`: a workspace product. It can grow a PPT task surface with outline, pages, notes, style, and generation state.
- `AI Otome`: a workspace example that shows how an AI-first interactive product can own its own interface.

## Product Boundary

An AI product owns its role, prompt, avatar, skills, tools, task history, and product workspace. When a user asks a product to change itself, the change belongs to that product, not the global shell.

This is the key product idea: Knead is stronger than an assistant list because every AI object can become a small AI product with its own evolving interface.

## Repository Shape

```text
apps/webui/        Main production WebUI application
products/          Built-in example AI products committed with the repository
packages/          Shared TypeScript packages
runtimes/          First-class runtime dependencies, including Hermes Agent
scripts/           Local development and verification scripts
docs/              Product, architecture, and historical design notes
experiments/       Public boundary note for historical prototypes excluded from release
vendor/            Local reference checkouts, ignored by Git
```

Production code should live in `apps/`, `products/`, `packages/`, `runtimes/`, `scripts/`, and current docs. Reference projects can stay locally under `vendor/`, but they are not part of the production repository.

The `products/` directory is for curated built-in examples that ship with the repository. The official set is listed in `products/catalog.json` and allow-listed on purpose: generated or user-created products are runtime state and are written to the WebUI state directory (`.hermes-home/webui/products/` when launched through `pnpm dev`), so running Knead does not dirty the source tree. Use `KNEAD_PRODUCTS_DIR` only when you intentionally want to place user-created products somewhere else.

`runtimes/hermes-agent` is the vendored official Hermes Agent runtime baseline. See [docs/architecture/HERMES_VENDORING.md](docs/architecture/HERMES_VENDORING.md) for the source, update, and patch policy.
Root `.gitattributes` marks this bundled runtime as vendored for GitHub language statistics while keeping it as first-class source in the repository.

The root `package.json` is marked `private: true` on purpose. Knead is released
as a source repository today, not as a publishable npm package; the flag prevents
accidental registry publishes while keeping the repository public and reusable.

## Run

Requirements:

- Node.js 22+
- pnpm 10.33+
- Python 3.11+ or 3.12

First-time local setup:

```bash
pnpm install
pnpm setup:local

# Edit .env and add at least one model provider key, for example OPENROUTER_API_KEY.
# Then configure the project-local Hermes model/provider state.
pnpm hermes:model

pnpm dev
```

The dev script starts `apps/webui` on `http://localhost:8788` by default.

`pnpm setup:local` prepares the project-local Python environment and copies `.env.example` to `.env` when needed. `pnpm hermes:model` runs the vendored Hermes CLI with that project-local environment and `HERMES_HOME=.hermes-home`. `pnpm dev` reads the root `.env`, uses the vendored Hermes runtime in `runtimes/hermes-agent`, and stores local runtime state under `.hermes-home/` by default. If the app says no LLM provider is configured, run `pnpm hermes:model` again.

Useful environment overrides:

```bash
HERMES_WEBUI_PORT=8789 pnpm dev
KNEAD_PROJECT_ROOT=/path/to/knead pnpm dev
KNEAD_BUILTIN_PRODUCTS_DIR=/path/to/builtin-products pnpm dev
KNEAD_PRODUCTS_DIR=/path/to/runtime-products pnpm dev
```

For PPT image generation, copy the PPT skill env template and add a FAL key:

```bash
cp products/ppt-designer/ppt-skill/.env.example products/ppt-designer/ppt-skill/.env
# Edit products/ppt-designer/ppt-skill/.env and set FAL_KEY.
```

## Verify

Use the smallest check that matches what you changed:

| Command | Use when | What it protects |
| --- | --- | --- |
| `pnpm docs:check` | Editing current docs, product READMEs, or release docs | Broken local Markdown links in release-owned documentation |
| `pnpm product:check -- <product-dir>` | Reviewing or promoting one AI product | Product manifest, preview entry, README shape note, and source/runtime boundary |
| `pnpm verify` | Touching WebUI, product runtime, products, scripts, or docs | Repository audit, source whitespace scan, secret scan, product checks, syntax checks, product tests, and WebUI smoke |
| `pnpm check` | Opening a normal PR | Workspace TypeScript checks plus `pnpm verify` |
| `pnpm release:batches` | Preparing a large release branch for review | Non-destructive grouping of dirty worktree files into review batches, with dependency notes |
| `pnpm release:check` | Packaging or changing release-facing files | Diff whitespace checks, local artifact check, frozen lockfile install, full `pnpm check`, and optional live agent smoke |
| `pnpm release:check:clean` | Final pre-tag release check | Everything in `release:check`, plus a clean Git worktree requirement |

```bash
pnpm check
```

This runs workspace checks and the repository/product runtime verifier.
The verifier also starts a temporary WebUI server without LLM credentials and
checks the shell, static product runtime, and built-in product registry.
It also validates that committed built-in products have clean manifests and
existing preview entries.

For just the WebUI/product checks:

```bash
pnpm verify
```

Before tagging or publishing a release:

```bash
pnpm release:check:clean
```

To inspect ignored local release artifacts before packaging or moving the checkout:

```bash
pnpm release:clean:local
pnpm release:clean:local -- --apply
```

This covers root scratch files, generated product outputs, and ignored
experiment build artifacts.

If you have a configured Hermes Gateway running and want to verify a real model-backed agent turn too:

```bash
KNEAD_RELEASE_AGENT_SMOKE=1 pnpm release:check
```

## Current Product Docs

- [docs/README.md](docs/README.md): map of current, historical, and reference documentation
- [PRODUCT.md](PRODUCT.md): product definition and design principles
- [PRODUCT_UIUX.md](PRODUCT_UIUX.md): current UI/UX model
- [DESIGN.md](DESIGN.md): visual system, brand tone, and app-shell UI tokens
- [CHANGELOG.md](CHANGELOG.md): release-facing change log
- [RELEASE.md](RELEASE.md): release checklist, product promotion checks, and optional live smoke
- [docs/PRODUCT_MODEL_CONTRACT.md](docs/PRODUCT_MODEL_CONTRACT.md): product runtime model and invariants
- [docs/architecture/PRODUCTION_REPOSITORY_PLAN.md](docs/architecture/PRODUCTION_REPOSITORY_PLAN.md): production repository plan
- [docs/references/REFERENCE_PROJECTS.md](docs/references/REFERENCE_PROJECTS.md): reference projects and what we learned from them

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, source boundaries, and PR checks. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for collaboration norms, [SECURITY.md](SECURITY.md) for private vulnerability reporting and local secret handling, and [NOTICE.md](NOTICE.md) for bundled runtime attribution.

## MVP Acceptance

The MVP is healthy when:

1. A user can select an AI product and start from chat.
2. `General AI` behaves as a complete chat product, not an empty workspace.
3. `PPT Designer` can open a PPT task surface when structure becomes useful.
4. A product can update its own identity, skills, tools, and runtime product workspace without mutating the global shell.
5. Product interface evolution is previewable, applicable, and recoverable.

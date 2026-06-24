# Contributing to Knead

Thanks for taking the time to improve Knead.

## Local Setup

```bash
pnpm install
pnpm setup:local
# Edit .env with your provider key, then configure the project-local model.
pnpm hermes:model
pnpm dev
```

Local runtime state belongs in `.hermes-home/`. Do not commit provider keys, generated sessions, generated product versions, temporary screenshots, or local reference checkouts.

Python runtime dependencies for the WebUI live in `apps/webui/requirements.txt`.
Development and CI install `apps/webui/requirements-dev.txt`, which must include
the runtime requirements before adding test-only packages.

## Before Opening a PR

```bash
pnpm check
```

This runs TypeScript checks, repository boundary checks, syntax checks, and product runtime smoke checks.
It also starts a temporary WebUI server without LLM credentials to verify that the app shell and built-in product registry load.

Use the pull request template. Every PR should name the affected AI product or runtime area and confirm that no local product state, provider keys, generated outputs, or exported decks were committed.
`CODEOWNERS` currently assigns default review ownership for the whole repository;
add narrower owners only when a subsystem has a stable maintainer.

Before tagging or publishing a release, run:

```bash
pnpm release:check:clean
```

If your local checkout has generated product outputs, inspect them before packaging:

```bash
pnpm release:clean:local
pnpm release:clean:local -- --apply
```

To include a real Hermes Gateway / model-backed agent smoke, start the gateway with a configured provider and run:

```bash
KNEAD_RELEASE_AGENT_SMOKE=1 pnpm release:check
```

## Source Boundaries

- App shell and WebUI runtime: `apps/webui/`
- Curated built-in products: `products/`
- Runtime-generated products: `.hermes-home/webui/products/`
- Vendored Hermes runtime: `runtimes/hermes-agent/`
- Local reference checkouts: `vendor/` (ignored)

Generated products can be promoted into `products/`, but only after they are cleaned as maintained examples, added to `products/catalog.json`, and allow-listed in `.gitignore`.
Curated product manifests are strict source contracts: use `metadata` or
`config` for product-specific extension data instead of adding arbitrary
top-level fields to `product.json`.

## Adding a Built-in Product

Most products should stay local runtime state. Add a product to `products/` only
when it is useful as a maintained example of the Knead product model.
Use the "AI product example" issue template when proposing a new built-in
example before opening a promotion PR.

Good built-in examples prove one clear shape:

- `chat_only`: the default chat UI is enough, with product-specific identity, prompt, skills, tools, and suggestions.
- `chat_left_canvas_right`: chat stays present while a task workspace makes structured work easier.
- `canvas_full`: an immersive product owns the main surface while still being AI-first.

Start from a runtime product, then validate it as a candidate:

```bash
pnpm product:check -- .hermes-home/webui/products/<product-id>
pnpm product:promote -- .hermes-home/webui/products/<product-id>
```

The promotion command is a dry run by default. When the candidate is clean and
you are ready to update source files:

```bash
pnpm product:promote -- .hermes-home/webui/products/<product-id> --apply
pnpm verify
```

Do not commit product outputs, save files, `.env` files, `.knead-published.json`,
generated versions, exported decks, or local assets that are not part of the
curated example.

## Product Model

Start with:

- `PRODUCT.md`
- `PRODUCT_UIUX.md`
- `DESIGN.md`
- `docs/PRODUCT_MODEL_CONTRACT.md`
- `docs/architecture/PRODUCTION_REPOSITORY_PLAN.md`

Archived docs are historical context only.

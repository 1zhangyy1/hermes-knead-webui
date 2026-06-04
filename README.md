# Next AI Chat

Next AI Chat is an AI product library. Users choose or create an AI product, start from chat, and let that product grow the task interface only when the work needs more structure.

The current MVP centers on two built-in AI products:

- `通用 AI`: a `chat_only` product. Its own product UI is the base chat surface.
- `PPT 设计师`: a workspace product. It can grow a PPT task surface with outline, pages, notes, style, and generation state.

## Product Boundary

An AI product owns its role, prompt, avatar, skills, tools, task history, and product workspace. When a user asks a product to change itself, the change belongs to that product, not the global shell.

This is the key product idea: Next AI is stronger than an assistant list because every AI object can become a small AI product with its own evolving interface.

## Repository Shape

```text
apps/webui/        Main production WebUI application
products/          Built-in AI product workspaces and generated product UI
packages/          Shared TypeScript packages
scripts/           Local development and verification scripts
docs/              Product, architecture, and historical design notes
experiments/       Old prototypes and non-production exploration
vendor/            Local reference checkouts, ignored by Git
```

Production code should live in `apps/`, `products/`, `packages/`, `scripts/`, and current docs. Reference projects can stay locally under `vendor/`, but they are not part of the production repository.

## Run

```bash
pnpm dev
```

The dev script starts `apps/webui` on `http://localhost:8788` by default.

Useful environment overrides:

```bash
HERMES_WEBUI_PORT=8789 pnpm dev
NEXT_AI_PROJECT_ROOT=/path/to/nextaichat pnpm dev
NEXT_AI_PRODUCTS_DIR=/path/to/products pnpm dev
```

## Verify

```bash
pnpm check
```

This runs TypeScript checks for shared packages and syntax checks for the WebUI product runtime files.

For just the WebUI/product checks:

```bash
pnpm verify
```

## Current Product Docs

- [PRODUCT.md](PRODUCT.md): product definition and design principles
- [PRODUCT_UIUX.md](PRODUCT_UIUX.md): current UI/UX model
- [docs/architecture/PRODUCTION_REPOSITORY_PLAN.md](docs/architecture/PRODUCTION_REPOSITORY_PLAN.md): production repository plan
- [docs/references/REFERENCE_PROJECTS.md](docs/references/REFERENCE_PROJECTS.md): reference projects and what we learned from them

## MVP Acceptance

The MVP is healthy when:

1. A user can select an AI product and start from chat.
2. `通用 AI` behaves as a complete chat product, not an empty workspace.
3. `PPT 设计师` can open a PPT task surface when structure becomes useful.
4. A product can update its own identity, skills, tools, and product workspace without mutating the global shell.
5. Product interface evolution is previewable, applicable, and recoverable.

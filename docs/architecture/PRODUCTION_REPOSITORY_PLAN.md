# Production Repository Plan

## Decision

The local repository directory is the source of truth. The Git remote should mirror this clean source tree for backup, collaboration, and release.

The production repository should be understandable from the root:

- `apps/webui` is the main product application.
- `products` contains built-in example AI products committed with the repository.
- `packages` contains shared libraries.
- `runtimes` contains first-class runtime dependencies that the product is built on.
- `experiments` documents the release boundary for old prototypes that should
  stay outside the public source tree unless rewritten as current examples.
- `vendor` is local-only reference material and is ignored by Git.

## Current Product Truth

Knead is not an assistant list and not a Lovable-style app builder.

It is an AI product library:

1. The user selects or creates an AI product.
2. The AI product starts from chat.
3. If the task needs structure, the product grows a task interface.
4. If the user asks the product to improve itself, the product updates its own workspace, skills, tools, or interface.
5. The global shell stays stable.

The core MVP boundary is:

- `General AI`: product interface is the base chat surface.
- `PPT Designer`: product interface can become Chat plus a PPT task surface.
- New products: start with identity and chat, then the agent writes product files when the conversation asks for or implies a product UI.

## Problems Found

The original local tree was useful for research but not production-grade:

- The real application lived under `vendor/hermes-webui`, which made source ownership unclear.
- Reference projects, runtime state, screenshots, and product code were mixed together.
- `products.py` depended on whether the app path was under `vendor`, which would break after moving the app.
- `spaces/products` mixed AI product workspaces with older React space prototypes.
- Root scripts launched the old Vite prototype first, not the actual WebUI product.
- The root had no Git repository, while nested reference projects had their own `.git` directories.

## Target Structure

```text
knead/
  apps/
    webui/
      api/
      static/
      server.py
      bootstrap.py
  products/
    README.md
    general/
      product.json
      index.html
    ppt-designer/
      product.json
      index.html
      style.css
      app.js
    ai-otome/
      product.json
      index.html
      style.css
      app.js
  packages/
    hermes-client/
    space-runtime/
  runtimes/
    hermes-agent/
  scripts/
    dev-webui.sh
    verify.mjs
    hermes-smoke.mjs
  docs/
    architecture/
    references/
    archive/
      README.md
  experiments/
    README.md
  vendor/
    ignored local reference checkouts
```

## Source Boundaries

### Production App

`apps/webui` is the product application. Any runtime change to the app shell, chat surface, product runtime, or API routes belongs here.

### Built-in Product Workspaces

`products/<product-id>` is the source boundary for curated built-in example AI products that ship with the repository. These products prove the product model and can be edited by maintainers as source code. The official built-in set is listed in `products/catalog.json` and source-allow-listed in `.gitignore`; adding a new built-in product should be an intentional source change.

Runtime user-created products are not source code. By default they live under:

```text
<webui-state-dir>/products/<product-id>/
```

When launched through the root `pnpm dev` script, `<webui-state-dir>` is `.hermes-home/webui`. It can also be overridden explicitly through `KNEAD_PRODUCTS_DIR`.

This is where the agent should write or update for user-created products:

- `product.json`
- `index.html`
- `style.css`
- `app.js`
- product-specific assets, when needed

Product code should not write into the global shell unless the user explicitly asks to change the platform itself.

### Runtime State

Runtime state stays outside Git:

- `.hermes-home`
- `tmp`
- `.tmp-*`
- `node_modules`
- generated product versions

### First-run Configuration

The root `.env.example` is the public local-development template. It is safe to commit and should contain only placeholders. Developers run `pnpm setup:local`, add provider keys to `.env`, configure the model with `pnpm hermes:model`, then run `pnpm dev`.

The root dev script reads `.env`, resolves project-relative paths against the repository root, and keeps Hermes state in `.hermes-home` by default. The model/provider config still belongs to the project-local Hermes home, so first-time users should run:

```bash
pnpm hermes:model
```

Real secrets belong in `.env`, `.hermes-home/.env`, or product-specific ignored env files such as `products/ppt-designer/ppt-skill/.env`; never in tracked source.

### Hermes Runtime

`runtimes/hermes-agent` is the first-class Hermes Agent runtime baseline. It is vendored from the official `NousResearch/hermes-agent` repository by `git subtree`, not copied by hand.

The product should depend on Hermes through a narrow runtime boundary where possible. Runtime-level changes are allowed when the AI product platform needs product context, tool scoping, skill/tool ownership, or agent-loop behavior that cannot be expressed cleanly in WebUI code alone.

### References

`vendor` is allowed locally but ignored. Reference projects should be documented in `docs/references`, not treated as application source.

## Implementation Phases

### Phase 1: Repository Clean Boundary

Status: baseline in place. Keep this phase green by running `pnpm check` before publishing or pushing.

- The main app lives in `apps/webui`.
- Built-in example product workspaces live in `products`.
- Runtime user-created products live under `.hermes-home/webui/products` by default.
- `vendor`, runtime state, generated outputs, and local dependencies are ignored.
- Root scripts start the actual WebUI.
- Product path discovery resolves from the project root and state directory.

### Phase 2: Product Creation Runtime

Goal: new product creation should match the user's expectation:

1. User describes a product.
2. Creator opens a draft product workspace in runtime state.
3. Creator chats normally and writes the smallest useful product shape.
4. Creator explicitly marks the draft ready before the user adds it to the shelf.
5. Published products appear without global shell changes.

Implementation notes:

- Product context must always include the product workspace path.
- Builder turns can write only inside the selected product workspace by default.
- Usage turns should remain normal chat unless task structure is useful.
- Product identity changes update `product.json`, not global UI code.
- Product categories, layouts, skills, tools, and readiness should come from Creator output, not shell-side keyword classifiers.

### Phase 3: Product Self-Evolution

Goal: a product can improve its own task interface naturally.

Flow:

1. User says the product should work differently.
2. Agent explains this is changing the selected product's task interface or workflow.
3. Agent writes a preview in the product workspace.
4. User applies, discards, or rolls back.
5. The selected product now feels easier to use next time.

The UI should avoid exposing generated paths, manifests, code diffs, or version directories unless the user asks.

### Phase 4: Verification and CI

Status: baseline in place.

Minimum checks:

- Python compile for product API files.
- JavaScript syntax checks for product runtime files.
- TypeScript checks for shared packages.
- Repository audit for ignored/runtime/reference boundaries.
- Product API smoke check for `general`, `ppt-designer`, and `ai-otome`.
- Current documentation entry checks for stale product naming.
- Browser check for first screen and one product task flow.

Current CI runs `pnpm check` on push and pull requests. The product API and browser checks remain local/manual until the runtime dependencies are made CI-friendly.

## Done Criteria

The repository is production-grade when:

- A new contributor can identify the main app in less than one minute.
- `pnpm dev` starts the real product.
- `pnpm check` passes locally.
- Reference projects are not committed as production source.
- Runtime files are ignored.
- A new contributor can copy `.env.example`, configure a model, run `pnpm dev`, and see the WebUI.
- Built-in example AI product files live under `products`.
- User-created AI product files live under runtime state by default, not in the source tree.
- Product self-changes are scoped to the selected product workspace.
- The Git remote points at this clean structure.

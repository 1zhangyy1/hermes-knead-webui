# Production Repository Plan

## Decision

The local `nextaichat` directory is the source of truth. The private GitHub repository is the remote backup and collaboration repository.

The production repository should be understandable from the root:

- `apps/webui` is the main product application.
- `products` contains AI-product-owned workspaces.
- `packages` contains shared libraries.
- `runtimes` contains first-class runtime dependencies that the product is built on.
- `experiments` contains old prototypes and non-production explorations.
- `vendor` is local-only reference material and is ignored by Git.

## Current Product Truth

Next AI is not an assistant list and not a Lovable-style app builder.

It is an AI product library:

1. The user selects or creates an AI product.
2. The AI product starts from chat.
3. If the task needs structure, the product grows a task interface.
4. If the user asks the product to improve itself, the product updates its own workspace, skills, tools, or interface.
5. The global shell stays stable.

The core MVP boundary is:

- `通用 AI`: product interface is the base chat surface.
- `PPT 设计师`: product interface can become Chat plus a PPT task surface.
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
nextaichat/
  apps/
    webui/
      api/
      static/
      server.py
      bootstrap.py
  products/
    general/
      product.json
      index.html
    ppt-designer/
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
  experiments/
    host-shell/
    spaces/
    prototypes/
  vendor/
    ignored local reference checkouts
```

## Source Boundaries

### Production App

`apps/webui` is the product application. Any runtime change to the app shell, chat surface, product runtime, or API routes belongs here.

### Product Workspaces

`products/<product-id>` is the file boundary for an AI product. This is where the agent should write or update:

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

### Hermes Runtime

`runtimes/hermes-agent` is the first-class Hermes Agent runtime baseline. It is vendored from the official `NousResearch/hermes-agent` repository by `git subtree`, not copied by hand.

The product should depend on Hermes through a narrow runtime boundary where possible. Runtime-level changes are allowed when the AI product platform needs product context, tool scoping, skill/tool ownership, or agent-loop behavior that cannot be expressed cleanly in WebUI code alone.

### References

`vendor` is allowed locally but ignored. Reference projects should be documented in `docs/references`, not treated as application source.

## Implementation Phases

### Phase 1: Repository Clean Boundary

Status: in progress.

- Move the main app from `vendor/hermes-webui` to `apps/webui`.
- Move built-in product workspaces from `spaces/products` to `products`.
- Move old host shell and space prototypes to `experiments`.
- Ignore `vendor`, runtime state, generated outputs, and local dependencies.
- Update root scripts so `pnpm dev` starts the actual WebUI.
- Update product path discovery so products resolve from the project root.

### Phase 2: Product Creation Runtime

Goal: new product creation should match the user's expectation:

1. User describes a product.
2. System creates a product identity.
3. User continues normal chat.
4. The agent writes product files in `products/<id>` when the conversation needs a UI.
5. The product preview appears without global shell changes.

Implementation notes:

- Product context must always include the product workspace path.
- Builder turns can write only inside the selected product workspace by default.
- Usage turns should remain normal chat unless task structure is useful.
- Product identity changes update `product.json`, not global UI code.

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
- Product API smoke check for `general` and `ppt-designer`.
- Browser check for first screen and one product task flow.

Current CI runs `pnpm check` on push and pull requests. The product API and browser checks remain local/manual until the runtime dependencies are made CI-friendly.

## Done Criteria

The repository is production-grade when:

- A new contributor can identify the main app in less than one minute.
- `pnpm dev` starts the real product.
- `pnpm check` passes locally.
- Reference projects are not committed as production source.
- Runtime files are ignored.
- AI product files live under `products`.
- Product self-changes are scoped to the selected product workspace.
- The private GitHub repository points at this clean structure.

# Hermes Runtime Vendoring

## Decision

Next AI Chat vendors the official Hermes Agent runtime under `runtimes/hermes-agent`.

This is intentional. The product is built on Hermes Agent as its core runtime: model calls, the agent loop, tools, skills, memory, checkpoints, and runtime events all come from Hermes. Keeping the runtime inside the repository gives the project one coherent source tree while still preserving a clean boundary between product code and runtime code.

## Why Not `vendor/`

`vendor/` remains ignored local reference material. It is useful for experiments, comparisons, and scratch checkouts.

`runtimes/hermes-agent` is different: it is production source and part of the repository.

## Upstream

- Official upstream: https://github.com/NousResearch/hermes-agent
- Current baseline: `d1367355d514b5ce3af6056ca660ab28e9d632e4`
- Import method: `git subtree --squash`

The runtime directory contains `UPSTREAM.md` and `PATCHES.md` so the source and local changes remain visible close to the code.

## Local Patch Policy

Prefer this order:

1. Product behavior in `products/<id>` when the change belongs to one AI product.
2. WebUI/API code in `apps/webui` when the change is presentation, routing, product registry, or browser interaction.
3. Adapter/shared package code in `packages` when the change is a Next AI Chat abstraction over Hermes.
4. Hermes runtime code in `runtimes/hermes-agent` when the change must affect the agent loop, tool execution, runtime policy, or tool/skill capability loading.

Runtime changes must be recorded in `runtimes/hermes-agent/PATCHES.md`.

## Updating From Official Hermes

Use subtree pull from the repository root:

```bash
git subtree pull \
  --prefix=runtimes/hermes-agent \
  https://github.com/NousResearch/hermes-agent.git \
  main \
  --squash \
  -m "Update Hermes Agent runtime"
```

After updating:

1. Update `runtimes/hermes-agent/UPSTREAM.md`.
2. Re-check `runtimes/hermes-agent/PATCHES.md`.
3. Run `pnpm check`.
4. Smoke-test `pnpm dev` with a real chat session.

## Runtime Boundary

The product should not scatter Hermes internals throughout the codebase. The intended dependency direction is:

```text
apps/webui
  -> packages/agent-runtime-adapter
    -> runtimes/hermes-agent
```

The current WebUI still imports `run_agent.AIAgent` directly in places inherited from Hermes WebUI. That is acceptable during the MVP, but future product-runtime work should move product-specific scoping and events through an adapter boundary.

## Fork Policy

Start from official Hermes. If Next AI Chat accumulates runtime patches that cannot be upstreamed quickly, create a dedicated Hermes fork and update `UPSTREAM.md` to point to that fork. The main repository can continue to consume the fork through the same subtree path.

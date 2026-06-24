# Knead Product Model Contract

Updated: 2026-06-23

This file is the implementation contract for Knead's AI product model. `PRODUCT.md` describes the product vision, `PRODUCT_UIUX.md` describes the current interaction model, and this file defines the runtime invariants that code should preserve.

Exploratory notes and discarded plans are intentionally excluded from the public release tree. If an old local note conflicts with `PRODUCT.md`, `PRODUCT_UIUX.md`, this contract, or `docs/architecture/PRODUCTION_REPOSITORY_PLAN.md`, follow the current documents.

## Definition

Knead is an AI product shelf: users choose, create, use, and shape AI products. An AI product is stronger than a plain assistant because it can own identity, memory, skills, tools, task history, and a product workspace that may grow a useful UI when the work needs structure.

The core bet is:

> One sentence can become an AI product that is useful immediately and can be shaped over time.

Knead is not a generic assistant list, plugin marketplace, developer app builder, or Lovable-style external app generator. The mechanism may generate files, HTML, and product workspaces; the user experience should feel like shaping the selected AI product, not configuring software internals.

## Product Object

Every product shares the same skeleton:

- `id`
- `title`
- `avatar`
- `description`
- `source_prompt`
- `workspace`
- `sessions`
- `versions`
- `preview`

Differences between products should live in a small set of slots:

- `product_layout`: where the product UI lives.
- `product_type`: semantic hint for defaults, prompts, and capabilities.
- `skills` and `tools`: the capability set available to the product.
- `canvas_label`: user-facing label for the product workspace when one is open.

Current layout values:

- `chat_only`: the product's complete UI is the default chat surface. `General AI` uses this.
- `chat_center`: the product starts as centered chat and can later grow a workspace if the task needs one.
- `chat_left_canvas_right`: chat stays visible while a task workspace opens beside it. `PPT Designer` uses this for structured deck work.
- `canvas_full`: the product workspace is the main experience. Interactive products such as `AI Otome` use this.

## Lifecycle

### Create

Creation is a dedicated Creator flow, not normal product usage.

1. The user clicks `Knead one` or describes a reusable AI product from the shelf.
2. Creator opens a draft product workspace under runtime state.
3. Creator chats normally with the user, clarifies only when needed, and writes the smallest useful product shape.
4. Creator explicitly marks the draft ready and records a short user-centered ready reason.
5. The draft is explicitly added to the shelf before it becomes a normal product.

Draft products should not appear as finished products until they are published. A half-created product is a draft, not a broken shelf item.

The shell must not infer finished product types from keyword rules. Product semantics, layout, skills, tools, and readiness belong to the Creator draft files and explicit draft status.

### Use

Usage is the selected product doing the user's task.

- The product speaks with its own identity.
- The product uses its configured skills and tools.
- The product should not mutate the global shell.
- The product should not rewrite itself during ordinary use unless the user asks to shape it or the task clearly needs a product workspace update.

### Shape

Shape is the selected product being improved.

1. The user chooses `Shape it` or says how the product should work differently.
2. The runtime enters `product_builder` scope for that product.
3. The agent may update `product.json` and files inside that product workspace.
4. The user should be able to return to using the product after the shape turn.

Shape should feel like "make this AI more useful next time", not "open a code editor".

## Runtime Scopes

Knead uses one underlying model/runtime with different scopes:

- `product_init`: first useful draft or first product workspace creation.
- `product_usage`: use the selected product to do work.
- `product_builder`: shape the selected product itself.

Scope changes should affect prompt, tool access, and context. Product usage and product shaping must remain conceptually distinct even if they share one visible conversation.

Minimum safety rule:

- Builder scope may write inside the selected product workspace.
- Usage scope should treat product files as read-only unless the user explicitly asks to shape the product.
- Product-generated code must not write to the global shell by default.

## Product Bridge

Product workspaces do not call model APIs directly. They use the host bridge:

- `window.NextAI.chat.send({ text, action, context })`
- `window.NextAI.state.get/set/remove`

The host routes AI work through the selected product's Hermes session, product identity, tool policy, and runtime state. This keeps product UI, chat history, thinking/tool cards, approvals, skills, and files aligned.

## Source Boundaries

Built-in example products live in source:

- `products/general`
- `products/ppt-designer`
- `products/ai-otome`

User-created and generated products are runtime state. Under the default dev setup they live in:

```text
.hermes-home/webui/products/
```

Promoting a generated product into `products/` is a deliberate source change, not a side effect of using the app.

## Release Invariants

Before release, these should remain true:

1. A new contributor can understand the app from `README.md` and `docs/README.md`.
2. `pnpm dev` starts the real WebUI using project-local `.hermes-home`.
3. Runtime products do not dirty the source tree.
4. Built-in examples are intentionally allow-listed.
5. `General AI` works as a complete chat product.
6. `PPT Designer` can use chat plus a PPT workspace.
7. `AI Otome` proves a full-workspace interactive product can still route AI through the host.
8. Creation, usage, and shaping are distinguishable in code and visible enough in UI.
9. Product self-changes stay scoped to the selected product workspace.
10. `pnpm check` and the repository audit pass.

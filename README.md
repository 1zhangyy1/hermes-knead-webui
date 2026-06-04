# Next AI Chat

Next AI Chat is an AI product workspace built on top of Hermes WebUI. The product idea is simple: users do not manage workspaces first. They choose an AI product, start from chat, and the product can grow a task-specific workspace only when the task needs more structure.

## Product Logic

An AI product is the primary object in the UI. It owns:

- a role, such as general assistant or PPT designer
- its own product identity, prompt, avatar, skills, and tools
- a dedicated product workspace directory
- task history and product-specific sessions
- an optional task interface that can evolve over time

The default AI product is `通用 AI`. Its interface is the chat interface itself. It is not missing a workspace UI; it is a `chat_only` product whose UI is ready as soon as chat is ready.

Structured products, such as `PPT 设计师`, use the same chat core plus an additional workspace surface. For PPT work, the product can expose outline, page, notes, and style areas beside the conversation.

## Core Principle

Every selected AI object should be product-backed. When the user asks the current product to change itself, such as changing its avatar, adding a skill, or adjusting its task flow, the change belongs to that product's own workspace and manifest. It must not mutate the global shell by accident.

## MVP Flow

1. Select an AI product from the left product list.
2. Start a new task from the center chat surface.
3. Keep chat as the command surface.
4. If the task benefits from structure, the AI product opens or updates its own workspace UI.
5. If the user asks to improve the product, the AI can update the product configuration or generate a preview of a better task interface.

## Current Built-in Products

- `通用 AI`
  - `product_id`: `general`
  - `ui_mode`: `chat_only`
  - `ui_status`: `ready`
  - workspace: `spaces/products/general`
- `PPT 设计师`
  - `product_id`: `ppt-designer`
  - `ui_mode`: `workspace`
  - workspace: `spaces/products/ppt-designer`

## Important Paths

- `PRODUCT.md`: product definition and design principles
- `PRODUCT_UIUX.md`: current UI/UX model
- `vendor/hermes-webui/api/products.py`: AI product registry, product manifests, preview status, version helpers
- `vendor/hermes-webui/api/product_context.py`: request-to-product intent and workspace routing
- `vendor/hermes-webui/api/routes.py`: session creation and product binding
- `vendor/hermes-webui/static/product-store.js`: frontend product hydration
- `vendor/hermes-webui/static/product-runtime.js`: product context injection for sessions and messages
- `vendor/hermes-webui/static/product-shell-runtime.js`: AI product library and selected-product home UI
- `spaces/products/*`: product-owned workspaces and generated product UI files

## Run

The active WebUI target is:

```bash
cd vendor/hermes-webui
HERMES_WEBUI_HOST=127.0.0.1 HERMES_WEBUI_PORT=8788 /Users/nuomiji/.hermes/hermes-agent/venv/bin/python server.py
```

Then open:

```text
http://localhost:8788
```

For the Vite host shell prototype:

```bash
pnpm install
pnpm dev
```

## Verification

Useful smoke checks:

```bash
python3 -m py_compile vendor/hermes-webui/api/products.py vendor/hermes-webui/api/product_context.py vendor/hermes-webui/api/routes.py vendor/hermes-webui/api/updates.py
node --check vendor/hermes-webui/static/product-runtime.js
node --check vendor/hermes-webui/static/product-store.js
node --check vendor/hermes-webui/static/product-shell-runtime.js
node --check vendor/hermes-webui/static/workspace.js
curl --noproxy '*' -s http://127.0.0.1:8788/api/products
```

Expected product semantics:

- `general` should be `chat_only` and `ready`
- normal general chat should route to `product_usage`
- requests like changing avatar, identity, tools, or skills should route to `product_builder`
- `ppt-designer` should remain a `workspace` product

## Reference Vendors

The `vendor/` directory contains local source snapshots and reference projects used during product research and implementation. When exporting to a parent git repository, exclude nested `.git` folders so the private repo stores source files rather than broken submodule references.

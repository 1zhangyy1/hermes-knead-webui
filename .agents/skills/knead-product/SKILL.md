---
name: knead-product
description: Create or adjust a Knead AI product in its workspace.
version: 1.0.0
author: Knead team
metadata:
  hermes:
    category: product
    tags: [knead, product, canvas, builder]
    related_skills: [impeccable]
---

# Knead Product Skill

Builds and evolves Knead AI products: small, self-contained web canvases
(index.html / style.css / app.js) plus a product.json identity, living in one
product workspace directory. Covers the Knead-specific contract only — visual
craft and frontend quality come from the `impeccable` skill, loaded alongside.

## When to Use

- A `product_init` turn: a product was just created and needs its first usable
  canvas.
- A `product_builder` turn: the user asked to change how an existing product
  works, looks, or behaves (UI, flow, identity, defaults).
- NOT for using a product (answering its tasks) — that is normal chat.

## Prerequisites

- You are in the product's workspace directory (e.g. `products/<id>/`). All
  edits stay inside it: `product.json`, `index.html`, `style.css`, `app.js`,
  `assets/*`.
- Tools: `read_file`, `patch`, `terminal`, `search_files`.
- For any non-trivial UI work, also load the `impeccable` skill and follow its
  setup (it reads the repo's PRODUCT.md / DESIGN.md design rules).

## How to Run

1. Read `product.json` to learn the product's identity, layout, and slots.
2. Read `references/layouts.md` and pick/confirm the layout intent.
3. For AI-in-canvas features, follow `references/bridge.md` exactly.
4. Start new canvases from `templates/minimal-canvas.html`, not a blank file.
5. Edit files directly with `patch`; keep the canvas browser-native (no build
   step). Then verify (below) and summarize what changed in user language.

## Quick Reference

The product model is a shared skeleton plus exactly 4 variable slots
(everything type-specific lives in these, never in forked logic):

| Slot | Meaning | Values |
|---|---|---|
| `product_layout` | where the UI lives | `chat_only` / `chat_left_canvas_right` / `canvas_full` |
| `product_type` | semantic tag, drives defaults | `general` / `ppt` / `interactive` / `image` / ... |
| `skills` + `tools` | capabilities | e.g. `presentations`, `image_gen` |
| `canvas_label` | display title of the canvas | free text, empty for chat_only |

Worked examples to read before building (real, shipped products):

- `products/ppt-designer/` — `chat_left_canvas_right`, stage-driven canvas,
  agent⇄canvas state via a workspace `state.json` file.
- `products/ai-otome/` — `canvas_full`, the canvas owns the primary input,
  character state through bridge context.

## Procedure

1. **Identity changes** (name, avatar, description, placeholder, skills,
   tools, layout, canvas label) go in `product.json` — never hardcode them in
   canvas files.
2. **Layout decision**: keep `chat_only` products pure chat (no canvas files).
   Use `chat_left_canvas_right` for side-by-side work surfaces, `canvas_full`
   when the product UI is the main page (role chat, games, editors). See
   `references/layouts.md`.
3. **First canvas**: write minimal-but-real files the user can immediately
   use; editable defaults over clarifying questions. Copy
   `templates/minimal-canvas.html` as the starting skeleton.
4. **AI inside the canvas**: include `/static/product-bridge-sdk.js` and call
   `window.NextAI.chat.send(...)`; persist UI state with
   `window.NextAI.state`. Never call model APIs or `/api/chat` directly from
   canvas code. Full contract: `references/bridge.md`.
5. **Agent⇄canvas data**: prefer writing a `state.json` file in the workspace
   that the canvas fetches and renders (see ppt-designer), over asking the
   canvas to parse chat text.
6. **After changes**: tell the user what changed and what to try next, in
   user language (the canvas is "界面", never "canvas"/"version"/"scope").

## Pitfalls

- **General technical questions**: Users in a Knead Creator session may ask general dev/research questions (e.g., "research doc site generators", "which framework should I use") that have nothing to do with the product being drafted. Handle these as normal AI tasks — answer fully and directly — do not force every query into the product-building frame. A greeting followed by a research question is still a research question.
- Do not touch the host shell, other products, or repo files outside the
  product workspace unless the user explicitly asks to change Knead itself.
- Do not build a marketing landing page; build a working task surface.
- Do not add build steps, frameworks, or package installs for a small canvas.
- Do not rely on iframe `localStorage` for durable state — sandboxed; use
  `window.NextAI.state`.
- Do not emit hidden UI state blocks in chat; edit workspace files instead.
- For `canvas_full`, the canvas owns the primary input — do not depend on the
  host composer for normal product use.
- Internal words must never appear in user-visible UI text: 产品/canvas/画布/
  演化/version/manifest/sandbox/persona/scope.

## Verification

- `product.json` parses as JSON and keeps the 4 slots consistent (e.g.
  `canvas_full` products should not also claim `chat_only`).
- `index.html` references only files that exist in the workspace; the bridge
  SDK script tag comes before the app script.
- Open the canvas via the product preview URL (or `terminal` with a headless
  browser if available) and confirm it renders without console errors.
- Re-read your diff: every changed file is inside the product workspace.

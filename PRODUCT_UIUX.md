# Knead UI/UX

## Core Shape

Knead is an AI product shelf. The user does not manage workspaces first. They choose an AI product, start a task with one message, and keep working as the task grows structure.

## First Screen

The first screen should be quiet and direct:

- Left: `Knead`, new task, AI product list, recent tasks for the selected product.
- Center: selected AI product name, one-line description, input, a few starter tasks.
- Hidden by default: skills, tools, connectors, workbench management, versions, file trees, and product configuration.

The first screen should answer only:

- Which AI product am I using?
- What can I ask it to do?
- Where do I start?
- What has it worked on before?

## Task Screen

After the user sends the first message, the product enters a task screen:

- The conversation becomes the command surface.
- The task title replaces the generic product title.
- If the product benefits from structure, its product canvas opens beside the conversation.
- The canvas belongs to this AI product. It is not a separate app builder.

For `PPT Designer`, the first product canvas should expose topic, audience, outline, pages, notes, and style decisions. The user should still be able to type normally at any time.

## Product Page Layout

Every AI product owns a product page. Chat is the core block inside that page, not an external host feature.

- `chat_only`: the product page is the default Chat experience. `General AI` uses this.
- `chat_center`: the product starts from a centered Chat page and does not auto-generate a product canvas. If the user later asks for a visible UI or workflow, the product can create one and switch to `chat_left_canvas_right`.
- `chat_left_canvas_right`: the product keeps Chat on the left and opens its own product canvas on the right. `PPT Designer` should use this once the PPT workflow needs outline, pages, notes, style choices, or preview.
- `canvas_full`: the product canvas becomes the main working page. This is for products whose own UI is the task surface, such as character chat, games, visual editors, or other immersive flows. The host Chat can still be used to command and evolve the product, but the product should not be squeezed into a side panel.

The product canvas is written by the AI product in its own product directory. The host shell keeps the product list, routing, sessions, and Chat core stable, then applies the product's layout intent.

For `canvas_full`, the product's own UI owns the primary input. The host composer is hidden by default and appears only when the user chooses to adjust the product. This prevents "chat inside chat": a role-chat product can have its own chat input, an image product can have a prompt/form input, and the shell does not add a second competing input.

## Product Bridge

Product canvases do not call model APIs directly. When a canvas needs AI, it uses the host bridge:

- Include `/static/product-bridge-sdk.js`.
- Call `window.NextAI.chat.send({ text, action, context })`.
- The host routes that request to the currently selected AI product's Hermes Agent.
- The host returns `reply` or `error` to the product canvas.
- Use `window.NextAI.state.get/set/remove` for durable product UI state. By default it is scoped to this product plus this task/session, so a role-chat page, PPT outline, image prompt state, or data table stays matched to the same Hermes conversation.
- `window.NextAI.storage` is only a sandbox-safe temporary fallback. Product chat history, task data, and generated UI state should not depend on raw iframe `localStorage`.

This keeps AI ability, product identity, session history, skills, tools, thinking cards, and approvals in one runtime. A PPT canvas, a role-chat canvas, and an image editor canvas should all use the same bridge; only their `action` and `context` differ.

This means:

- `General AI` does not show "input to expand" or "generate product canvas"; its product page is already complete as Chat.
- `PPT Designer` is not "default Chat plus an add-on". It is a PPT product page whose Chat core can move left while the PPT canvas appears on the right.
- Custom products start from the smallest useful shape. If normal Chat is enough, Creator configures identity, behavior, skills, tools, suggestions, and keeps `product_layout: "chat_only"`. If a visible UI would make the product easier to use, Creator writes the product files and requests `chat_left_canvas_right` or `canvas_full` in `product.json`. The shell should not guess product categories from keywords.

## Creation Flow

Creation is a dedicated Creator flow, similar in spirit to shaping a product but scoped to a draft:

1. The user clicks `Knead one` and says what they want.
2. Creator opens a draft workspace in runtime state.
3. Creator chats normally, asks only useful clarifying questions, and edits the draft product files when needed.
4. Creator explicitly marks the draft ready with a short user-centered reason.
5. The user adds it to the shelf. Only then does it become a normal AI product.

A draft is not a broken product. It should not appear in the AI shelf until it is published.

## Interface Evolution

Users can ask the AI product to improve its product canvas in the same conversation:

- "以后开头先让我选模板和受众。"
- "讲稿区固定在右边。"
- "这个界面不好用，先给我大纲再给页面。"

The AI product should respond as itself:

1. Explain that this changes how the AI product handles this kind of task.
2. Generate a product canvas preview.
3. Let the user use or discard the improvement.
4. Let the user return to the previous canvas.

Avoid exposing version numbers, generated paths, manifests, code diffs, or app-builder language. The user should feel that the AI product became easier to use, not that they configured software internals.

## MVP Acceptance

The MVP is acceptable when a new user can understand the path without explanation:

1. Select `PPT Designer`.
2. Start a PPT task from the center input.
3. See the PPT product canvas appear only after the task needs it.
4. Ask the AI product to change that canvas.
5. Preview the change, use it, discard it, or return to the previous canvas.

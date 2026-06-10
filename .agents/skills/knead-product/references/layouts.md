# Product Layouts

The single most important slot. Pick by where the work happens, never fork
product logic by type.

## chat_only

The product page IS chat. No canvas files at all.

- For: general assistants, advice/writing products, anything with no durable
  task surface.
- "Adjusting" a chat_only product means editing `product.json` identity
  (role, description, placeholder, skills, tools) — never generate
  index.html/style.css/app.js unless the user explicitly asks it to become a
  UI product.

## chat_left_canvas_right

Chat stays on the left as the command surface; the product canvas opens on
the right as the working surface.

- For: task tools where conversation drives structured output — decks,
  documents, research boards, data tables.
- The canvas reflects the conversation: when the agent produces structure
  (an outline, files, results), the canvas shows it; the user edits there and
  keeps talking on the left.
- Worked example: `products/ppt-designer/` — a stage-driven canvas
  (brief → outline → slides) that auto-expands as the conversation reaches
  each stage, fed by a workspace `state.json` the agent writes.
- Keep ONE focus per stage; do not cram every panel into one screen.

## canvas_full

The product UI is the main page and owns the primary input. The host
composer is hidden during normal use and only appears when the user adjusts
the product.

- For: immersive products — character chat, games, image editors, visual
  tools. Avoid squeezing them into a side panel.
- The canvas must provide its own input/output flow (its own composer,
  buttons, choices) and call the bridge for AI turns.
- Worked example: `products/ai-otome/` — full-page companion with its own
  composer, choice buttons, mood/bond state, scene switching; passes
  `context.character` through the bridge so the host agent plays the role.

## chat_center (transitional)

A centered chat page that has not grown a canvas yet. When a real canvas
appears, the host promotes the product to `chat_left_canvas_right`
automatically — do not set chat_center as a final intent. If you build a
canvas deliberately, set the layout you mean in `product.json` yourself.

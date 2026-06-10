# Product Bridge Contract

Canvases never call model APIs or `/api/chat` directly. All AI goes through
the host bridge.

## Setup

Include the SDK before the app script (both relative to the canvas page):

```html
<script src="/static/product-bridge-sdk.js"></script>
<script src="./app.js"></script>
```

The canvas runs in a sandboxed iframe (opaque origin). The SDK handles the
host handshake; listen for readiness if needed:

```js
window.addEventListener('nextai:ready', (e) => { /* host context in e.detail */ });
```

## Ask the AI (canvas → host → agent)

```js
const reply = await window.NextAI.chat.send({
  text: '用户可读的请求文本',
  action: 'myproduct:do-thing',          // machine tag for this kind of request
  context: { /* structured state the agent needs, e.g. character, brief */ },
});
// reply.content is the agent's final text
```

- `context.character` is the convention for role-play products: the host
  injects "play this character" for the product agent.
- Requests are queued one at a time; disable the triggering control while
  waiting.

## React to the conversation (host → canvas)

Every finished agent turn is broadcast to the active canvas:

```js
window.addEventListener('nextai:agent', (e) => {
  const text = e.detail && e.detail.content;
  // parse agreed markers/blocks from the conversation and update the UI
});
```

Prefer file-based data over parsing chat text: the agent writes
`state.json` in the product workspace; the canvas fetches it fresh each turn:

```js
const r = await fetch('state.json?cb=' + Date.now(), { cache: 'no-store' });
if (r.ok) render(await r.json());
```

## Durable UI state

```js
await window.NextAI.state.set('my-key', value);            // product+session scope
const v = await window.NextAI.state.get('my-key', null);
await window.NextAI.state.set('prefs', p, { scope: 'product' });  // product-wide
```

- Never block first paint on `state.get` — render defaults first, then
  restore (race against a short timeout).
- `window.NextAI.storage` is only a sandbox-safe temporary fallback; raw
  iframe `localStorage` is NOT durable.

## Hard rules

- No direct `fetch('/api/...')` for chat/model calls from canvas code.
- The canvas's files are served `no-store` with timestamp-busted URLs — after
  the builder edits them, the host hot-reloads the canvas automatically; no
  server restart is ever needed for product changes.

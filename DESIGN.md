# Knead Design System

The visual system for the Knead app shell. Direction confirmed from
[docs/brand/app-aura.html](docs/brand/app-aura.html).
This document is the source of truth; landing it = overriding CSS variables in
`apps/webui/static/style.css` and a few targeted surface rules. Components don't change — they read tokens.

## Direction

Clean, calm, premium — **a neutral ink UI lit by a soft warm aura.** Color comes from light
(a diffuse amber/peach glow), not from filled color blocks. This is what separates it from the
earlier terracotta version (which read as "土" / earthy). Benchmarks: ChatGPT/CraftGPT aura,
Linear/Vercel restraint, Anthropic paper-warmth.

Three moves carry the whole look:
1. **Aura** — a diffuse, blurred warm glow (amber → peach → rose) behind the hero/first screen, on white.
2. **Ink, not color** — controls (send, primary, selection, focus) are near-black `#1A1A1A`. Confident, monochrome.
3. **Soft & rounded** — generous radius (composer 16–18, cards 14), soft low-opacity warm shadows, the app reads as calm cards.

Warmth without earthiness: warm-tinted neutrals + the aura, never a brown/cream body fill.

## Tokens → real CSS variables (light `:root`)

| var | old (blue/cool) | aura |
|---|---|---|
| `--bg` | `#fbfbfc` | `#FCFCFB` clean near-white |
| `--sidebar` / `--topbar-bg` | `#f4f5f7` | `#F7F6F4` low-chroma porcelain (warmth lives in the aura, NOT the chrome — beige reads "土") |
| `--surface` / `--main-bg` | `#fff` | `#FFFFFF` (chat stays clean white) |
| `--surface-2` | `#f6f7f9` | `#F6F5F3` |
| `--border` / `--border2` | cool grays | `#EBEAE7` / `#E2E0DC` near-neutral hairlines |
| `--text` / `--muted` / `--muted2` | `#181b20` … | `#1A1A1A` / `#6E6E6E` / `#8A8A8A` |
| `--accent` | `#2563eb` blue | `#1F1D1B` warm ink (controls, selection) |
| `--accent-hover` | `#1d4ed8` | `#000000` |
| `--accent-bg` / `-strong` | blue washes | `rgba(31,29,27,.055)` / `.10` neutral wash |
| `--accent-text` | `#1e40af` | `#1F1D1B` |
| `--focus-ring` | blue | `rgba(31,29,27,.22)` |
| `--radius-sm/md/card/lg` | 4/8/8/12 | **6/10/14/16** (rounder) |
| `--shadow-sm` | neutral | `0 1px 2px rgba(60,45,30,.05)` warm |

Dark mode (`:root.dark`) gets the same logic later (warm charcoal + light aura + light-ink controls).

## The aura (first screen / empty state)
A separate background element, NOT a token. Diffuse blurred radial stack on white:
```css
background:
  radial-gradient(42% 50% at 40% 38%, rgba(255,212,128,.55), transparent 72%),
  radial-gradient(40% 48% at 62% 46%, rgba(255,168,134,.45), transparent 72%),
  radial-gradient(38% 46% at 50% 66%, rgba(246,170,200,.38), transparent 72%);
filter: blur(60px);
```
Used once, behind the centered composer on the home/empty screen. Not on working screens.

## Surface notes (targeted rules, applied incrementally)
- **First screen** (`.assistant-home`, `.empty-state` @ style.css 1326, 5013): aura behind a centered
  title + the floating composer + example chips (dashed pill). Drop the eyebrow (`.assistant-home-eyebrow`) — it's the AI-grammar tell.
- **Composer** (`.composer-box` @ 1335): bigger radius (18), soft shadow, ink circular send.
- **Sidebar** (`.sidebar` @ 457): soft warm gradient tint, rounded items, calm "Your AIs" + "Recent" grouping.
- **Example chips**: dashed `1px` pill, `var(--chip-line)`, with a `›`.

## Bans (impeccable, for our shell)
No gradient text, no glassmorphism, no ornamental shadows, no ghost-card (1px border + ≥16px shadow),
no card radius ≥24px, no repeated eyebrows, no cream-body fill. Warmth via aura + neutrals only.

## Process
WIP=1, in the real app, verify each surface before the next: ① token base → ② first screen aura →
③ composer → ④ sidebar → ⑤ dark mode → ⑥ polish pass (contrast, states, spacing).
Brand assets: `docs/brand/` (`app-aura.html` is the reference). **Logo (designer-owned):** the live mark is a warm clay-face squircle in `apps/webui/static/knead-logo.svg` (in-app) + `favicon.svg` (tab/PWA); raster fallbacks are `favicon-*.png` / `.ico`. `docs/brand/knead-*.svg` are earlier ink two-dot concepts; old terracotta `nie-*.svg` are superseded.

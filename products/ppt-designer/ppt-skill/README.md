# GPT Image 2 PPT Skill

This support skill generates presentation slide images with GPT Image 2 through
fal.ai, then packages the result as a `.pptx` deck and an HTML viewer. It is a
deck-oriented CLI for the built-in `PPT Designer` product.

## Design Philosophy

Give the agent small atomic commands and let it decide how to compose them.

- `gen` / `edit`: generate or edit slide images through fal.ai
- `pack`: compose local slide images into `.pptx` and `index.html`

There are no hard-coded "mode A / mode B / mode C" flows. The agent should read
the task, inspect the deck state, and choose the right operation for each slide.

## Core Concept: Deck

A deck is one directory under `outputs/`.

- Slides are auto-numbered as `slide-01.png`, `slide-02.png`, and so on.
- `deck.json` stores size, quality, default style, and operation history.
- `pack` writes a shareable `deck.pptx` and `index.html`.

`outputs/` is runtime output and must not be committed.

## Quick Start

```bash
# 1. Install dependencies.
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Configure the local key.
cp .env.example .env
# Edit .env and set FAL_KEY.

# 3. Generate the first slide and deck defaults.
#    Style is not a CLI enum; describe the visual direction in the prompt.
.venv/bin/python ppt.py gen q1-demo \
  "Editorial magazine cover, huge serif title 'Q1 Product Review', off-white background, thin hairline divider, small sans-serif subtitle '2026 · Product Team'. Crisp exact typography." \
  --size 2048x1152 --quality high

# 4. Generate later slides by referencing the first slide as the visual base.
.venv/bin/python ppt.py edit q1-demo \
  "Keep layout identical. REPLACE title WITH: 'Core Wins'. REPLACE subtitle WITH: 'Users +32% · Retention 78% · NPS 62'." \
  --ref 1

.venv/bin/python ppt.py edit q1-demo \
  "Keep layout identical. REPLACE title WITH: 'Thank you'. REPLACE subtitle WITH: 'See you in Q2'." \
  --ref 1

# 5. Inspect deck state.
.venv/bin/python ppt.py info q1-demo

# 6. Package the deck.
.venv/bin/python ppt.py pack q1-demo
# -> outputs/q1-demo/deck.pptx
# -> outputs/q1-demo/index.html
open outputs/q1-demo/index.html
```

## Commands

| Command | Purpose | Example |
| --- | --- | --- |
| `gen <deck> <prompt>` | Generate a new slide image and auto-assign the next slot. | `ppt gen my "..."` |
| `edit <deck> <prompt> --ref N` | Edit from one or more references. | `ppt edit my "..." --ref 1` |
| `pack <deck>` | Package slide images as `.pptx` and `.html`. | `ppt pack my` |
| `info <deck>` | Show deck state. | `ppt info my` |

### `edit --ref`

Supported reference forms:

- `--ref 1`: reference slot 1 from the same deck
- `--ref /path/to/brand.png`: reference a local file
- `--ref https://...png`: reference an image URL
- multiple references: `--ref 1 --ref brand.png`

### Refine One Slide

```bash
ppt edit mydeck "Change title to 'Roadmap'." --ref 3 --slot 3
ppt pack mydeck
```

## Agent Skill Usage

This directory is support code for the built-in `PPT Designer` product. It can
also be used as a standalone agent skill: have the agent read `SKILL.md`, then
call `ppt.py` to generate, edit, inspect, and package a deck.

## Project Structure

```text
ppt-skill/
├── ppt.py                    # CLI entry point
├── ppt_skill/                # Core package
│   ├── env.py                # Loads .env
│   ├── deck.py               # Deck model
│   ├── api.py                # gen_image / edit_image
│   └── pack.py               # to_pptx / to_html
├── templates/viewer.html     # HTML viewer
├── style_refs/               # Writing samples for style prompts
├── .env.example
├── requirements.txt
└── outputs/<deck>/           # Runtime output, ignored by Git
```

## Image Size

GPT Image 2 requires both sides to be multiples of 16. The largest side must be
at most 3840 px, and total pixels must be between 655,360 and 8,294,400.

- Standard: `1280x720`
- High definition, default: `2048x1152`
- 4K: `3840x2160`

`1920x1080` is not valid because 1080 is not divisible by 16.

## Cost Note

Pricing is token-based: image input is `$8/M` input tokens and output is
`$30/M` output tokens at the time this support code was written. `quality=high`
is the default and most expensive setting; use `medium` or `low` when cost
matters more than detail.

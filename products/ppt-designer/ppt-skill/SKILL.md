---
name: gpt-image-2-ppt
description: |
  Generate PPT slides with GPT Image 2. AI plans content, writes prompts, calls fal.ai to generate images, and outputs an editable PPTX + HTML viewer.
  Trigger phrases: make a PPT, create slides, build a deck, pitch deck, product overview, quarterly review, work summary, presentation.
---

# GPT Image 2 PPT Skill

Uses fal.ai GPT Image 2 to generate PPT slide images. GPT Image 2 excels at precise text rendering, making it ideal for presentations that require accurate typography in any language.

---

## Four Commands

```bash
ppt gen  <deck> "<prompt>" [--size WxH] [--quality high|medium|low] [--slot N]
ppt edit <deck> "<prompt>" --ref <N|filepath|URL>... [--slot N]
ppt pack <deck> [--title "Title"]
ppt info <deck>
```

- `gen` — text-to-image, appends a new slide
- `edit` — image-to-image, uses an existing slide as reference (`--ref 1` = reference slot 1)
- `pack` — packages into deck.pptx + index.html
- `info` — view deck status

Output directory: `outputs/<deck>/`, slides auto-numbered as `slide-01.png`, `slide-02.png`, …

---

## Size Constraints (API hard limits)

Both width and height must be **multiples of 16**, max side ≤ 3840.

| Tier | Size | Use |
|------|------|-----|
| Preview | 1280×720 | Quick draft |
| **HD (default)** | 2048×1152 | Standard presentation ⭐ |
| 4K | 3840×2160 | Print / large screen |

⚠️ `1920×1080` won't work (1080 is not a multiple of 16).

---

## Rules Index

| File | Content | When to read |
|------|---------|-------------|
| [rules/workflow.md](rules/workflow.md) | 6-phase process, deck_spec format, two-phase parallel generation | Before starting any task |
| [rules/prompt-guide.md](rules/prompt-guide.md) | Seven-section structure, language handling, font rules, full examples | When writing prompts |
| [rules/style-guide.md](rules/style-guide.md) | Style judgment, STYLE+COLOR templates, gen vs edit | When planning visual style |
| [rules/visual-types.md](rules/visual-types.md) | Design layers (charts / diagrams / illustrations / backgrounds / decorations) | When planning each slide's visual content |
| [rules/modify-scenarios.md](rules/modify-scenarios.md) | Edit page / insert page / delete page / reorder / restyle | When modifying an existing deck |

---

## Environment

```bash
pip install -r requirements.txt   # fal-client, python-dotenv, python-pptx
# .env must contain FAL_KEY=sk-...
```

---

## Project Structure

```
├── ppt.py                  # CLI entry point
├── ppt_skill/
│   ├── api.py              # gen_image / edit_image (with retry)
│   ├── deck.py             # Deck class (numbering, metadata, file lock)
│   ├── pack.py             # to_pptx (PNG validation + speaker notes) / to_html
│   └── env.py              # load .env
├── rules/                  # AI execution rules
│   ├── workflow.md
│   ├── prompt-guide.md
│   ├── style-guide.md
│   ├── visual-types.md
│   └── modify-scenarios.md
├── style_refs/             # 14 style samples (for reference, not templates)
├── templates/viewer.html   # HTML viewer template
└── outputs/<deck>/         # Generated content
    ├── deck.json           # Metadata + history
    ├── slide-NN.png
    ├── prompts/slide-NN.md # Full prompt per slide (also used as speaker notes)
    ├── deck.pptx
    └── index.html
```

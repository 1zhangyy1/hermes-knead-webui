# Style References

These files are writing samples, not a style menu.

Each Markdown file shows one way to describe a visual language in words: color,
typographic feel, layout, texture, and constraints that GPT Image 2 can use.
The agent may read them for phrasing and level of detail, but it should still
design the visual direction from the user's task.

## Font Description Rule

Describe appearance, not font names.

| Avoid | Prefer |
| --- | --- |
| "Bebas Neue" | "bold condensed geometric sans-serif with tight tracking" |
| "Playfair Display" | "high-contrast display serif with hairline horizontals and thick verticals" |
| "Inter" | "clean geometric sans-serif with consistent stroke widths and moderate letter-spacing" |
| "Source Han Serif" | "high-contrast serif with elegant horizontal strokes and precise vertical strokes" |

GPT Image 2 is an image model. Visual descriptions usually matter more than
specific font-family names.

## How To Use These References

When planning a deck, the agent should:

1. Analyze the content, audience, mood, and medium.
2. Construct a visual language independently, either mentally or directly in the prompt.
3. Read these references only when it needs examples of good visual phrasing.
4. Ignore them when the task calls for a style that is not represented here.

## How Not To Use Them

- Do not force the user to pick one of these files.
- Do not treat these files as required inputs for every deck.
- Do not assume the current set is the complete universe of possible styles.

## Current Samples

| File | Good for |
| --- | --- |
| `minimal.md` | Minimal keynote decks, executive updates |
| `blueprint.md` | Technical architecture, engineering documentation |
| `notion.md` | SaaS products, feature walkthroughs |
| `sketch-notes.md` | Education, knowledge sharing |
| `corporate.md` | Investor decks, business proposals |
| `dark-atmospheric.md` | Tech launches, creative brands |
| `bold-editorial.md` | Product launches, high-impact talks |
| `editorial-infographic.md` | Research reports, data storytelling |
| `scientific.md` | Academic work, technical diagrams |
| `watercolor.md` | Lifestyle and warm editorial content |
| `chinese-elegance.md` | Chinese cultural themes, traditional brands |
| `glassmorphism.md` | Consumer tech, UI presentation |
| `editorial.md` | Magazine layouts, text-led narratives |
| `minimalist.md` | Minimal business and consulting decks |

## Adding A New Sample

A good sample should include:

- exact colors with hex values
- typographic feel described by visual appearance, not font names
- layout and material language
- clear "Do" and "Don't" guidance
- scenarios where the style fits

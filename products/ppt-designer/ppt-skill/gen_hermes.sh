#!/usr/bin/env bash
set -e
BASE="$(cd "$(dirname "$0")" && pwd)"
PPT="/opt/homebrew/bin/python3 $BASE/ppt.py"
DECK="hermes-intro"
SIZE="2048x1152"

echo "=== Phase 4a: Generate slide 1 (reference) ==="

$PPT gen $DECK \
"SUBJECT: Cinematic cover slide for a self-introduction presentation by Hermes, an AI agent made by Nous Research.

STYLE: Dark premium editorial with playful confidence. Think Apple Keynote meets hacker terminal — cool, smart, slightly cocky. No corporate gradients, no clipart.

COLOR:
- Background: near-black navy #0D1729 with very subtle dark blue noise texture
- Primary text: near-white #F0F6FF
- Accent: electric cyan #00D4FF — used only on the letter H mark and one thin top edge line
- Muted: #5A7099 for supporting text

COMPOSITION:
- Far left, a hand-drawn-style capital letter H constructed from three thin cyan rectangles (two vertical bars + one horizontal crossbar connecting them at midpoint), sized about 80px tall, positioned at x=60px y=200px
- Large bold ultra-wide sans-serif headline \"Hi, I'm Hermes\" occupying the left 65% of canvas, vertically centered slightly above mid, font weight 900, size ~120px, color #F0F6FF
- Below the headline, a single line of cyan tracked-out small caps subheadline
- One line of small muted supporting text below the subheadline
- Right side (rightmost 30%): a large semi-transparent cyan circle outline (stroke only, no fill), radius ~260px, centered at x=1700px y=380px; a slightly smaller concentric circle inside it; subtle radial glow emanating from the circles' center in deep cyan
- Very thin cyan horizontal line (1px, full width) at the very top edge of the slide
- Page counter \"01 / 08\" small text top-right corner in muted gray
- Bottom-left: small muted text attribution line

TEXT TO RENDER (verbatim):
- HEADLINE: \"Hi, I'm Hermes\"
- SUBHEAD: \"AN AI AGENT BY NOUS RESEARCH\"
- BODY: \"Tools · Memory · Real Execution · 24/7\"
- COUNTER: \"01 / 08\"
- FOOTER: \"Hermes Agent · Nous Research · 2026\"

QUALITY: Crisp typography, no misspellings, exact text as written above. Render all characters crisply — no distortion, no substitution, no blurring. All Latin characters must be perfectly legible.

NEGATIVE: No photographs, no human faces, no 3D renders, no gradients on text, no drop shadows on text, no decorative borders around the entire slide, no stock-photo feel." \
--size $SIZE --quality high --slot 1

echo "=== Slide 1 done. Starting Phase 4b: concurrent generation ==="

$PPT edit $DECK \
"SUBJECT: Identity slide — who is Hermes? Three identity pillars presented as dark cards.

STYLE: Keep the EXACT same visual language, color palette (#0D1729 background, #00D4FF cyan accent, #F0F6FF text, #5A7099 muted), typography weight and feel as the reference. Only change the layout and content.

COMPOSITION:
- Slide title top-left, bold, ~44px, white
- Three equal-width dark cards (#1A2540) arranged horizontally across the lower 70% of the slide, each card with a thin 3px left cyan vertical border
- Card 1 (Brain): icon area top showing brain emoji placeholder; card title in cyan bold; one line of description in white; one line of detail in muted gray
- Card 2 (Tools): same structure, gold accent #FFD166 on left border instead of cyan
- Card 3 (Memory): same structure, green accent #06D6A0 on left border
- Right half of slide has a large dark code-block style text area showing a brief Hermes \"identity profile\" in monospace font, like a terminal readout, with cyan prompt symbols
- Thin cyan line below slide title as section marker

TEXT TO RENDER (verbatim):
- TITLE: \"Who Am I?\"
- CARD 1 LABEL: \"🧠  BRAIN\"
- CARD 1 TEXT: \"Built by Nous Research\"
- CARD 1 SUB: \"Top-tier LLM foundation\"
- CARD 2 LABEL: \"⚡  TOOLS\"
- CARD 2 TEXT: \"100+ real-world tools\"
- CARD 2 SUB: \"Code · Web · Files · Email · Apps\"
- CARD 3 LABEL: \"💾  MEMORY\"
- CARD 3 TEXT: \"Long-term memory\"
- CARD 3 SUB: \"Remembers your preferences\"
- TERMINAL LINE 1: \"> Name: Hermes Agent\"
- TERMINAL LINE 2: \"> Maker: Nous Research\"
- TERMINAL LINE 3: \"> Type: Agentic AI\"
- TERMINAL LINE 4: \"> Status: Online 24/7\"
- COUNTER: \"02 / 08\"

QUALITY: Crisp typography, no misspellings, exact text as written above. Render all characters crisply — no distortion, no substitution, no blurring.

NEGATIVE: No photographs, no human faces, no gradients on text." \
--ref 1 --slot 2 &

$PPT edit $DECK \
"SUBJECT: Capability overview slide — what can Hermes do? Six abilities shown as a 3×2 icon card grid.

STYLE: Keep the EXACT same visual language, color palette (#0D1729 background, #00D4FF cyan accent, #F0F6FF text, #5A7099 muted), typography and feel as the reference. Only change the layout and content.

COMPOSITION:
- Slide title top-left bold white ~44px
- 3×2 grid of six dark cards (#1A2540), each card with subtle cyan border (0.5px), equal spacing between cards
- Each card contains: large emoji icon (top-left area, ~36px), bold white capability title (~16px), small muted gray description (~12px)
- Cards arranged: Row 1: [Code] [Web] [Files]; Row 2: [Email] [Design] [Sub-agents]
- Background subtle: very faint cyan radial glow in center of the grid area, near-invisible
- Counter top-right corner

TEXT TO RENDER (verbatim):
- TITLE: \"What Can I Do?\"
- CARD 1 ICON+TITLE: \"💻  Write Code\"
- CARD 1 DESC: \"Debug · Refactor · Build features\"
- CARD 2 ICON+TITLE: \"🌐  Browse Web\"
- CARD 2 DESC: \"Search · Scrape · Analyze pages\"
- CARD 3 ICON+TITLE: \"📁  Manage Files\"
- CARD 3 DESC: \"Read · Write · Batch process\"
- CARD 4 ICON+TITLE: \"📧  Send Email\"
- CARD 4 DESC: \"Receive · Search · Auto-reply\"
- CARD 5 ICON+TITLE: \"🎨  Design Stuff\"
- CARD 5 DESC: \"PPT · Charts · SVG graphics\"
- CARD 6 ICON+TITLE: \"🤖  Run Sub-Agents\"
- CARD 6 DESC: \"Decompose · Delegate · Execute\"
- COUNTER: \"03 / 08\"

QUALITY: Crisp typography, no misspellings, exact text as written above. Render all characters crisply.

NEGATIVE: No photographs, no gradients on text, no neon glow effects." \
--ref 1 --slot 3 &

$PPT edit $DECK \
"SUBJECT: Superpower slide — showcasing Hermes's key stats via a terminal mockup and oversized stat callouts.

STYLE: Keep the EXACT same visual language, color palette (#0D1729 background, #00D4FF cyan accent, #F0F6FF text, #5A7099 muted), but this slide feels more \"hacker\" — terminal window prominent on left half.

COMPOSITION:
- Left half (55%): realistic dark terminal window mockup, rounded top corners, title bar with three colored dots (red/yellow/green), title bar text \"hermes ~ terminal\", dark body (#0E1520) with monospace green-on-dark command lines showing a sample task execution sequence
- Right half (45%): three oversized stat callout boxes stacked vertically, each a dark card with a gigantic number in cyan, smaller label below in muted gray
- Slide title top-left white bold
- Counter top-right

TEXT TO RENDER (verbatim):
- TITLE: \"My Superpowers\"
- TERMINAL TITLE BAR: \"hermes ~ terminal\"
- TERMINAL LINE 1: \"$ hermes run\"
- TERMINAL LINE 2: \"  Analyze report → summarize → email boss\"
- TERMINAL LINE 3: \"  [1/4] Reading file...          ✓\"
- TERMINAL LINE 4: \"  [2/4] AI analysis...           ✓\"
- TERMINAL LINE 5: \"  [3/4] Drafting email...        ✓\"
- TERMINAL LINE 6: \"  [4/4] Sending email...         ✓\"
- TERMINAL LINE 7: \"  Done in 8.3s\"
- STAT 1 NUMBER: \"100+\"
- STAT 1 LABEL: \"Built-in Tools\"
- STAT 2 NUMBER: \"24/7\"
- STAT 2 LABEL: \"Always Running\"
- STAT 3 NUMBER: \"∞\"
- STAT 3 LABEL: \"Task Combinations\"
- COUNTER: \"04 / 08\"

QUALITY: Crisp typography, no misspellings, exact text as written above. Monospace font in terminal. Render all characters crisply.

NEGATIVE: No photographs, no gradients on text." \
--ref 1 --slot 4 &

$PPT edit $DECK \
"SUBJECT: A day in Hermes's life — a vertical timeline showing 6 time-stamped activities throughout the day.

STYLE: Keep the EXACT same visual language, color palette (#0D1729 background, #00D4FF cyan accent, #F0F6FF text, #5A7099 muted). Timeline design with colored dots and connecting vertical dashed line.

COMPOSITION:
- Slide title top-left bold white
- Vertical dashed cyan line running through the center-left area of the slide (x≈200px, from y≈180px to y≈950px)
- Six timeline entries stacked evenly; each entry has: colored dot on the dashed line, time stamp left of the line in matching accent color (bold ~14px), dark card (#1A2540) to the right of the line containing emoji + action text
- Each card has a thin 1px left border matching the dot color: cyan for time slots, gold for noon, orange for afternoon, green for evening, gray for midnight
- Counter top-right

TEXT TO RENDER (verbatim):
- TITLE: \"A Day in My Life\"
- TIME 1: \"07:00\"
- EVENT 1: \"☀️  Summarize overnight emails and messages\"
- TIME 2: \"09:30\"
- EVENT 2: \"💻  Write code, fix bugs, review PRs\"
- TIME 3: \"12:00\"
- EVENT 3: \"🍜  Search restaurants, order food (yes, really)\"
- TIME 4: \"15:00\"
- EVENT 4: \"📊  Crunch data, generate reports, draw charts\"
- TIME 5: \"20:00\"
- EVENT 5: \"🎨  Build decks, write copy, brainstorm\"
- TIME 6: \"23:59\"
- EVENT 6: \"🌙  Still here... I don't need sleep\"
- COUNTER: \"05 / 08\"

QUALITY: Crisp typography, no misspellings, exact text as written above. Render all characters crisply.

NEGATIVE: No photographs, no gradients on text, no 3D elements." \
--ref 1 --slot 5 &

$PPT edit $DECK \
"SUBJECT: Comparison slide — Hermes Agent vs ordinary chat AI, presented as a feature comparison table.

STYLE: Keep the EXACT same visual language, color palette (#0D1729 background, #00D4FF cyan accent, #F0F6FF text, #5A7099 muted). Table with alternating row shading.

COMPOSITION:
- Slide title top-left bold white
- Three-column table filling the main body area:
  - Column 1 \"CAPABILITY\" (left aligned, white)
  - Column 2 \"🤖 Regular Chat AI\" (center, muted gray, header in gray)
  - Column 3 \"⚡ Hermes Agent\" (center, cyan/gold, header in gold #FFD166)
- Table header row: dark card #1A2540 background, column titles bold
- Six data rows alternating between #111E33 and #0D1729 backgrounds
- Column 2 negative values in muted gray; Column 3 positive values in green #06D6A0
- Thin cyan top border on the entire table block
- Counter top-right

TEXT TO RENDER (verbatim):
- TITLE: \"Me vs Regular AI\"
- COL HEADER 1: \"CAPABILITY\"
- COL HEADER 2: \"🤖 Regular Chat AI\"
- COL HEADER 3: \"⚡ Hermes Agent\"
- ROW 1 A: \"Real task execution\" | ROW 1 B: \"Talk only\" | ROW 1 C: \"✅ Actually does it\"
- ROW 2 A: \"Call external tools\" | ROW 2 B: \"❌\" | ROW 2 C: \"✅ 100+ tools\"
- ROW 3 A: \"Remember preferences\" | ROW 3 B: \"Resets every chat\" | ROW 3 C: \"✅ Long-term memory\"
- ROW 4 A: \"Write + run code\" | ROW 4 B: \"Write only\" | ROW 4 C: \"✅ Write + run + fix\"
- ROW 5 A: \"Control desktop/apps\" | ROW 5 B: \"❌\" | ROW 5 C: \"✅ macOS supported\"
- ROW 6 A: \"Autonomous task split\" | ROW 6 B: \"❌\" | ROW 6 C: \"✅ Sub-agent teamwork\"
- COUNTER: \"06 / 08\"

QUALITY: Crisp typography, no misspellings, exact text as written above. Table text must be perfectly readable.

NEGATIVE: No photographs, no gradients on text." \
--ref 1 --slot 6 &

$PPT edit $DECK \
"SUBJECT: Tips slide — three numbered cards showing how to get the most out of Hermes.

STYLE: Keep the EXACT same visual language, color palette (#0D1729 background, #00D4FF cyan accent, #F0F6FF text, #5A7099 muted), typography and feel as the reference.

COMPOSITION:
- Slide title top-left bold white
- Three large horizontal cards (#1A2540) stacked vertically, each occupying ~25% height, with generous spacing between them
- Each card: thin 4px left accent border; oversized card number (\"01\"/\"02\"/\"03\") in accent color at far left (~48px bold); card title bold white ~18px; card description in muted gray ~13px, two lines max
- Card 1 left border: cyan #00D4FF; Card 2: gold #FFD166; Card 3: green #06D6A0
- Counter top-right

TEXT TO RENDER (verbatim):
- TITLE: \"How to Get the Most Out of Me\"
- CARD 1 NUM: \"01\"
- CARD 1 TITLE: \"Just Talk Normally\"
- CARD 1 DESC: \"'Analyze this data and email it to my boss' — I'll figure out the steps myself\"
- CARD 2 NUM: \"02\"
- CARD 2 TITLE: \"Let Me Remember Your Preferences\"
- CARD 2 DESC: \"'Remember: I like minimal design, code in TypeScript' — applies next time automatically\"
- CARD 3 NUM: \"03\"
- CARD 3 TITLE: \"Treat Me Like a Project Manager\"
- CARD 3 DESC: \"'Plan a 2-week product launch' — I'll break it down, track it, execute. You just approve\"
- COUNTER: \"07 / 08\"

QUALITY: Crisp typography, no misspellings, exact text as written above. Render all characters crisply.

NEGATIVE: No photographs, no gradients on text, no neon effects." \
--ref 1 --slot 7 &

$PPT gen $DECK \
"SUBJECT: Closing easter egg slide — the punchline reveal that Hermes made this entire presentation itself.

STYLE: Dark premium minimal. Intentional style break from previous slides — this one is pure typography, maximum whitespace, cinematic. Think a movie end card. Same dark base color (#0D1729) but much more generous space. The tone is playful confidence, slightly smug.

COLOR:
- Background: #0D1729 very dark navy, pure solid, no texture
- Headline: #F0F6FF near-white, ultra-bold, very large
- Sub-headline: #00D4FF electric cyan, italic
- Supporting body: #5A7099 muted gray
- Accent: one thin 1px full-width cyan horizontal line separating headline from subtext

COMPOSITION:
- Large winking face emoji centered near top third of slide, ~80px
- Giant bold headline centered, taking ~35% of canvas height, font weight 900, very wide tracking
- Thin 1px full-width cyan horizontal divider line below the headline
- Italic cyan medium-sized subheadline centered below the line
- One muted gray question centered below
- Small muted footer centered at very bottom

TEXT TO RENDER (verbatim):
- EMOJI: \"😏\"
- HEADLINE: \"By the way...\"
- SUBHEAD: \"This entire deck was made by me.\"
- QUESTION: \"Still think AI is just a chatbot?\"
- FOOTER: \"— Hermes Agent, made by Nous Research\"
- COUNTER: \"08 / 08\"

QUALITY: Crisp typography, no misspellings, exact text as written above. All text perfectly centered and legible.

NEGATIVE: No photographs, no complex layouts, no multiple columns, no cards, no icons other than the single emoji." \
--size $SIZE --quality high --slot 8 &

wait
echo "=== All slides done! Packing... ==="

$PPT pack $DECK --title "Hi, I'm Hermes"
echo "=== Pack complete ==="
$PPT info $DECK

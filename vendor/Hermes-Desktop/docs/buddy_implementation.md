# Buddy System Implementation

**Status**: ✅ Complete  
**Location**: `src/Buddy/Buddy.cs`

---

## 🎯 What Buddy Is

A **deterministic Tamagotchi-style companion** that lives in your terminal.

- **Bones**: Visual appearance (species, rarity, eyes, hat, stats) - derived from user ID hash, NEVER stored
- **Soul**: Name and personality - AI-generated, persisted to config

**Same user ID = Same buddy forever.** Can't cheat rarity by editing config.

---

## 🎲 Rarity System

| Rarity | Chance | Species Pool | Avg Stat Total |
|--------|--------|--------------|----------------|
| **Legendary** | 0.1% | Cosmic, Quantum, Void, Star | 300 |
| **Rare** | 0.9% | Dragon, Phoenix, Unicorn, Griffin | 240 |
| **Uncommon** | 9% | Cat, Dog, Bird, Fish | 180 |
| **Common** | 90% | Blob, Cube, Dot, Line | 120 |
| **Shiny** | 0.5% | Any species (glowing variant) | Same as base |

**Shiny is independent** - you can have a Shiny Common or Shiny Legendary.

---

## 🔧 Mulberry32 PRNG

```csharp
// Seeded from: MD5(userId + "friend-2026-401")
// Same seed = same buddy forever
var rng = Mulberry32.Create(userId);

var rarityRoll = rng();  // 0.0 to 1.0
var speciesIndex = (int)(rng() * pool.Length);
```

This is the same algorithm used in modern agentic systems. Deterministic, reproducible, fair.

---

## 🎨 ASCII Art Renderer

Supports multiple species:

### Blob (Common)
```
  🧢
 ╭─────╮
 │•   •│
 │  ∆  │
 ╰─────╯
```

### Cat (Uncommon)
```
  /\_/\  
 ( •   • )
 (   △   )
  \_____/
```

### Dragon (Rare)
```
      /\    
     /  \   
    | O   O |
    |  ∆  |
     \  /
      \/
```

### Cosmic (Legendary)
```
  👑
 ╭─────╮
 │✦   ✦│
 │  ∆  │
 ╰─────╯
```

---

## 📊 Stats System

4 stats, each 1-100:
- **INT** (Intelligence) - How smart your buddy is
- **ENR** (Energy) - How active your buddy is
- **CRT** (Creativity) - How creative your buddy is
- **FRN** (Friendliness) - How friendly your buddy is

**Total varies by rarity:**
- Common: 120 (avg 30 per stat)
- Uncommon: 180 (avg 45 per stat)
- Rare: 240 (avg 60 per stat)
- Legendary: 300 (avg 75 per stat)

---

## 🧠 Soul Generation

AI-generated via LLM:

**Prompt:**
```
You are naming a Buddy companion for {userName}.

Buddy details:
- Species: Dragon
- Rarity: Rare
- Stats: INT 65, ENR 58, CRT 72, FRN 45

Generate:
1. A short, memorable name (1-2 words, max 15 chars)
2. A one-sentence personality description

Format:
NAME: [name]
PERSONALITY: [one sentence]
```

**Example Output:**
```
NAME: Ember
PERSONALITY: A curious dragon who loves exploring codebases and asking "why?"
```

---

## 💾 Storage Format

Only the **soul** is persisted (`~/.hermes-cs/buddy.json`):

```json
{
  "Name": "Ember",
  "Personality": "A curious dragon who loves exploring codebases and asking \"why?\"",
  "HatchedAt": "2026-04-03T12:00:00Z"
}
```

**Bones are regenerated** on every load from user ID hash. This prevents cheating.

---

## 🔌 Usage

```csharp
// In Program.cs or Agent initialization
var buddyService = new BuddyService(
    Path.Combine(configDir, "buddy.json"),
    chatClient
);

// Get or create buddy
var buddy = await buddyService.GetBuddyAsync(userId, ct);

// Display buddy
Console.WriteLine(buddyService.RenderBuddy());
```

**Output:**
```
✨ SHINY ✨
  /\_/\  
 ( ★   ★ )
 (   △   )
  \_____/

Name: Ember
Species: Cat (Rare)
Personality: A curious dragon who loves exploring codebases and asking "why?"

Stats:
  INT:  65  ENR:  58
  CRT:  72  FRN:  45
  Total: 240
```

---

## 🎯 Why This Matters

**It's not about the feature.** It's about:

1. **Emotional connection** - People name their buddies
2. **Conversation starter** - "What species did you get?"
3. **Retention** - People come back to check on their buddy
4. **Differentiation** - No other agent has this

**Cursor, Copilot, Aider**: Sterile tools  
**Hermes.C#**: Has a companion with personality

---

## 🚀 Future Enhancements

- [ ] Buddy reacts to your coding sessions (happy when tests pass)
- [ ] Buddy levels up over time (stats increase)
- [ ] Buddy gives encouragement ("You got this!")
- [ ] Buddy sleeps when you sleep (detects idle time)
- [ ] Buddy evolution (Common → Rare after X sessions)

---

**Buddy is the heart of Hermes.C#. Don't skip it.**

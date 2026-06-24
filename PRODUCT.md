# Product

## Register

product

## Users

Knead is for people who use AI to finish real work, not to configure agents for its own sake. They may be making decks, researching a topic, analyzing data, writing, planning, or building a repeatable personal workflow. They arrive with a task in mind, often uncertain about the exact structure, and need an AI product that can turn a first sentence into a usable task surface.

The first target user for the MVP is someone using `PPT Designer`: they want to describe a presentation, upload or reference material, discuss the direction with AI, and see a product canvas grow into the parts that make PPT work easier: topic, audience, outline, pages, speaker notes, and style decisions.

## Product Purpose

Knead is an AI product shelf. Users choose, create, and evolve AI products. An AI product is a long-lived work object with its own role, task history, skills, tools, and product canvas. It starts from chat, but when a task needs more structure, it can grow a product canvas for the current task.

Success means users understand the product in the first screen: choose an AI product, say what they want, and keep working. They should not need to understand manifests, sandboxes, version directories, plugin systems, or app builders. The interface should make the AI product feel increasingly useful over time because it can adapt its task flow and product canvas through preview, apply, and recovery.

## Brand Personality

Calm, capable, adaptive.

The product should feel like a focused work tool with a living AI core. It should be clear before it is clever, sparse before it is expressive, and confident without becoming technical. The AI should feel present through useful product canvases and good defaults, not through excessive explanation.

## Anti-references

Do not make the product feel like a generic AI assistant list, a plugin marketplace, a developer app builder, or a Lovable-style external app generator.

Avoid first screens dominated by workbench management, connector catalogs, skill stores, project trees, version history, or configuration forms. Avoid explaining the product with terms like default workspace, left chat, right panel, manifest, sandbox, generated space, code diff, or version directory.

Avoid over-designed SaaS chrome: decorative cards, large marketing heroes, gradient text, glass panels, nested cards, ornamental shadows, and feature-heavy sidebars. The UI should not look like it is trying to prove the idea through visual noise.

## Design Principles

1. Chat is the entry, not the whole product.
   Users start with natural language. The AI product decides when a task needs more structure and grows the right product canvas. Some canvases sit beside Chat; some products, like character chat or games, make their own canvas the main page.

2. One screen has one primary input.
   If the selected AI product's own UI is the main page, its input is the primary input. The shell should not add a second competing chat composer. The shell composer appears only when the user wants to adjust the AI product itself.

3. The selected AI product is the primary object.
   The first screen should answer: which AI product is selected, what it does, where to start, what it has done before, and how to create another AI product.

4. Progressive disclosure beats explanation.
   Hide advanced concepts until the task creates a reason to show them. Skills, tools, connectors, versions, and evolution history should not compete with the first task.

5. The product canvas belongs to the task.
   A product canvas is not a separate app. It is the current AI product making the current task easier to inspect and edit.

6. Evolution happens through use.
   Users can say what feels wrong or what should happen next time. The AI product proposes an interface or flow improvement, previews it, and applies it only after confirmation.

## MVP UI Model

The default screen is simple: a left AI product library and a central start surface for the selected AI product. Users do not start by choosing a workspace. They choose an AI product, then start a new task.

The selected AI product owns four things:

- Role: what kind of work it is responsible for.
- Memory: previous tasks and learned preferences.
- Capabilities: skills and tools it can use.
- Product canvas: the UI it can open or improve when a task needs structure. It can be a side-by-side working surface or the product's main page.

For `PPT Designer`, the first task should feel like a normal AI chat until PPT structure becomes useful. Then the product canvas can open with topic, audience, outline, pages, notes, and style controls. The chat remains the command surface: users can ask for content changes, workflow changes, or canvas changes in the same place.

For products whose canvas is the main page, such as role chat, games, visual editors, or image tools, the product UI owns the normal use flow. The shell keeps the product list, runtime, and adjustment entry, but hides the host composer until the user chooses to adjust the product.

Product canvas state belongs to the selected AI product task. If a product UI has its own messages, outline, form fields, selected character, prompt settings, or generated assets, it stores them through the host product state bridge so the UI and Hermes conversation stay matched.

When a user asks to improve the product canvas, the product should not jump into app-builder mode. It should explain that this changes how `PPT Designer` handles PPT tasks, generate a preview, let the user apply or discard it, and allow recovery to the previous canvas.

## Accessibility & Inclusion

Default to WCAG AA contrast for text and controls. Use system fonts and familiar product UI patterns. The product should remain usable with reduced motion, keyboard navigation, long Chinese and English labels, and compact desktop screens.

Animations should communicate state changes only. Critical actions like applying a canvas improvement, discarding an improvement, or returning to a previous canvas need clear labels and recoverable outcomes.
